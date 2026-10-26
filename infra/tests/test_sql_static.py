"""Static guard (SEC-04): backend SQL text is built only from string literals, never from runtime values.

Every asyncpg-style call (`execute`, `fetch*`, `prepare`, `cursor`, `copy_*`) in the API and realtime
packages must receive a first argument that is statically composed of string literals. Values reach
PostgreSQL only as bind parameters (`$1`, `$2`, ...), so no request field can change a statement's shape.
"""
import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
ROOTS = (SOURCE / "backend/api/src", SOURCE / "backend/realtime/src")
DATABASE_METHODS = {"execute", "executemany", "fetch", "fetchrow", "fetchval", "prepare", "cursor"}
# `prepare` also names aiohttp's WebSocketResponse.prepare(request); it is a database call only on connections/pools.
AMBIGUOUS_METHODS = {"prepare", "cursor"}
DATABASE_RECEIVERS = {"conn", "connection", "pool", "tx", "txn"}
# Reviewed exceptions, keyed by (file, query expression). Migrations are checked-in .sql files whose sha256
# is verified against schema_migrations before and after execution; no runtime value is interpolated.
ALLOWED = {("backend/api/src/hine_api/db.py", "raw.decode('utf-8')")}
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def database_call(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in AMBIGUOUS_METHODS:
        receiver = node.func.value
        return (receiver.id if isinstance(receiver, ast.Name) else getattr(receiver, "attr", None)) in DATABASE_RECEIVERS
    return node.func.attr in DATABASE_METHODS or node.func.attr.startswith("copy_")


def query_argument(node):
    if node.args:
        return node.args[0]
    return next((keyword.value for keyword in node.keywords if keyword.arg in {"query", "sql"}), None)


def own_nodes(scope):
    """Every node evaluated in this scope, not descending into nested functions, lambdas or classes."""
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, SCOPES):
            pending.extend(ast.iter_child_nodes(node))


def bindings(scope):
    """Name -> list of ("assign", value) | ("augment", value) | ("opaque", None) for one scope."""
    found = {}
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = scope.args
        for argument in arguments.posonlyargs + arguments.args + arguments.kwonlyargs + [a for a in (arguments.vararg, arguments.kwarg) if a]:
            found.setdefault(argument.arg, []).append(("opaque", None))
    for node in own_nodes(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).append(("assign", node.value))
                else:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            found.setdefault(name.id, []).append(("opaque", None))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.setdefault(node.target.id, []).append(("assign", node.value) if node.value is not None else ("opaque", None))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            found.setdefault(node.target.id, []).append(("augment", node.value) if isinstance(node.op, ast.Add) else ("opaque", None))
        elif isinstance(node, ast.NamedExpr):
            found.setdefault(node.target.id, []).append(("assign", node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            for name in ast.walk(node.target):
                if isinstance(name, ast.Name):
                    found.setdefault(name.id, []).append(("opaque", None))
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            for name in ast.walk(node.optional_vars):
                if isinstance(name, ast.Name):
                    found.setdefault(name.id, []).append(("opaque", None))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            found.setdefault(node.name, []).append(("opaque", None))
    return found


def literal_sql(expression, chain, seen=frozenset()):
    """True only when `expression` is built from str literals, `+`, conditional branches and such local names.

    `chain` is the list of binding tables, innermost scope first. Anything else (f-strings, `%`, `.format`,
    calls, attributes, parameters, loop variables) is rejected.
    """
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, str)
    if isinstance(expression, ast.BinOp):
        return isinstance(expression.op, ast.Add) and literal_sql(expression.left, chain, seen) and literal_sql(expression.right, chain, seen)
    if isinstance(expression, ast.IfExp):
        return literal_sql(expression.body, chain, seen) and literal_sql(expression.orelse, chain, seen)
    if isinstance(expression, ast.Name):
        if expression.id in seen:
            return True  # self-reference such as `sql = sql + "..."`; the other assignments are checked.
        table = next((table for table in chain if expression.id in table), None)
        if table is None:
            return False
        return all(kind != "opaque" and literal_sql(value, chain, seen | {expression.id}) for kind, value in table[expression.id])
    return False


def scan(source, filename="<sample>"):
    """Return (offenders, examined): `file:line: message` per database call whose query text is not literal-only."""
    tree = ast.parse(source, filename)
    module_bindings = bindings(tree)
    found, checked = [], 0

    def visit(scope, chain):
        nonlocal checked
        for node in own_nodes(scope):
            if isinstance(node, SCOPES):
                visit_scope(node, chain)
            elif database_call(node):
                argument = query_argument(node)
                if argument is None:
                    continue
                checked += 1
                if not literal_sql(argument, chain) and (filename, ast.unparse(argument)) not in ALLOWED:
                    found.append(f"{filename}:{node.lineno}: .{node.func.attr}() query is not built only from string literals: {ast.unparse(argument)[:120]}")

    def visit_scope(node, chain):
        if isinstance(node, ast.ClassDef):
            visit(node, chain)
        else:
            visit(node, [bindings(node)] + chain)

    visit(tree, [module_bindings])
    return found, checked


class SqlLiteralGuardTests(unittest.TestCase):
    def test_backend_sql_is_never_built_from_runtime_values(self):
        files = sorted(path for root in ROOTS for path in root.rglob("*.py"))
        self.assertTrue(files, "backend source not found; the guard would be vacuous")
        found, calls = [], 0
        for path in files:
            file_found, file_calls = scan(path.read_text(), str(path.relative_to(SOURCE)))
            found += file_found
            calls += file_calls
        self.assertGreater(calls, 50, "implausibly few database calls were examined")
        self.assertEqual(found, [], "SQL must be literal text with bind parameters:\n" + "\n".join(found))

    def test_checker_detects_interpolated_sql(self):
        cases = {
            "f-string": 'async def run(conn, table):\n    await conn.fetch(f"SELECT * FROM {table}")\n',
            "percent": 'async def run(conn, name):\n    await conn.execute("SELECT * FROM users WHERE name=\'%s\'" % name)\n',
            "format": 'async def run(conn, name):\n    await conn.fetchrow("SELECT {}".format(name))\n',
            "parameter": "async def run(conn, sql):\n    await conn.fetchval(sql)\n",
            "function call": 'async def run(conn, column):\n    await conn.fetch(build("SELECT ", column))\n',
            "attribute": "async def run(conn, spec):\n    await conn.execute(spec.sql)\n",
            "concatenated parameter": 'async def run(conn, order):\n    await conn.fetch("SELECT 1 ORDER BY " + order)\n',
            "name with one unsafe assignment": 'async def run(conn, column):\n    sql = "SELECT 1"\n    if column:\n        sql += column\n    await conn.fetch(sql)\n',
            "name rebuilt with f-string": 'async def run(conn, column):\n    sql = "SELECT 1"\n    sql = f"{sql} ORDER BY {column}"\n    await conn.fetch(sql)\n',
            "prepare on a connection": "async def run(conn, text):\n    await conn.prepare(text)\n",
            "copy query": "async def run(conn, text):\n    await conn.copy_from_query(text)\n",
            "keyword query": 'async def run(conn, text):\n    await conn.execute(query=f"SELECT {text}")\n',
            "conditional with unsafe branch": 'async def run(conn, text):\n    await conn.fetch("SELECT 1" if text else text)\n',
        }
        for name, source in cases.items():
            with self.subTest(name):
                found, _ = scan(source)
                self.assertEqual(len(found), 1, found)
                self.assertRegex(found[0], r"^<sample>:\d+: ")

    def test_checker_allows_literal_only_sql(self):
        source = '''
LOOKUP = "SELECT 1 FROM t WHERE a=$1"

async def run(conn, flag, value):
    sql = "SELECT * FROM s WHERE id=$1"
    if flag:
        sql += " FOR SHARE OF s"
    await conn.fetchrow(sql, value)
    await conn.fetch("SELECT * FROM s WHERE id=$1 FOR " + ("UPDATE" if flag else "SHARE"), value)
    await conn.execute(
        "UPDATE s SET a=$1 "
        "WHERE id=$2",
        value, value,
    )
    await conn.fetchval(LOOKUP, value)
    await conn.execute("UPDATE s SET a=1" if flag else "UPDATE s SET a=2")
    await ws.prepare(request)
'''
        self.assertEqual(scan(source), ([], 5))


if __name__ == "__main__":
    unittest.main()
