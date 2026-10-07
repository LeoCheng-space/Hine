"""Build and exercise the real product in an isolated, disposable Compose project."""
import argparse
import asyncio
import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "infra/docker/compose.acceptance.yml"
PROTOCOL = ROOT / "tests/load/protocol.py"
DOMAIN = "localhost"


class AcceptanceFailure(Exception):
    def __init__(self, code):
        self.code = code



class AcceptanceUnavailable(AcceptanceFailure):
    pass


def _failure_sites(error):
    sites = []
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == __file__:
            sites.append({"function": trace.tb_frame.f_code.co_name, "line": trace.tb_lineno})
        trace = trace.tb_next
    return sites

def run(command, *, env=None, input_data=None, timeout=900, cwd=ROOT):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, input=input_data,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceFailure("LOCAL_TOOL_FAILED") from None
    if result.returncode:
        raise AcceptanceFailure("DOCKER_OPERATION_FAILED")
    return result.stdout


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def replace_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(fd, 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def owned_network(project, env, docker):
    command = [docker, "network", "ls", "--filter", f"label=com.docker.compose.project={project}",
               "--format", "{{.ID}}"]
    return run(command, env=env).decode().strip()



def isolated_subnets(docker, env):
    identifiers = run([docker, "network", "ls", "-q"], env=env).decode().split()
    occupied = []
    if identifiers:
        networks = json.loads(run([docker, "network", "inspect", *identifiers], env=env))
        for network in networks:
            for config in network.get("IPAM", {}).get("Config", []):
                subnet = config.get("Subnet")
                if subnet:
                    try:
                        occupied.append(ipaddress.ip_network(subnet, strict=False))
                    except ValueError:
                        continue
    selected = []
    for candidate in ipaddress.ip_network("172.29.0.0/16").subnets(new_prefix=24):
        if any(candidate.overlaps(existing) for existing in occupied + selected):
            continue
        selected.append(candidate)
        if len(selected) == 2:
            return selected[0], selected[1]
    raise AcceptanceFailure("NO_ISOLATED_DOCKER_SUBNET_AVAILABLE")


def cleanup_project(docker, project, env):
    label = f"label=com.docker.compose.project={project}"
    failed = False
    deadline = time.monotonic() + 75

    def owned_run(command):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AcceptanceFailure("OWNED_PROJECT_CLEANUP_DEADLINE")
        return run(command, env=env, timeout=min(15, remaining))

    for service in ("realtime", "api", "caddy", "redis", "postgres"):
        service_label = f"label=com.docker.compose.service={service}"
        try:
            identifiers = owned_run([docker, "ps", "-aq", "--filter", label, "--filter", service_label]).decode().split()
            if identifiers:
                owned_run([docker, "stop", "--time", "8", *identifiers])
        except AcceptanceFailure:
            failed = True
    try:
        container_ids = owned_run([docker, "ps", "-aq", "--filter", label]).decode().split()
    except AcceptanceFailure:
        container_ids = []
        failed = True
    if container_ids:
        try:
            owned_run([docker, "rm", *container_ids])
        except AcceptanceFailure:
            try:
                owned_run([docker, "rm", "-f", *container_ids])
            except AcceptanceFailure:
                failed = True
    for kind, command in (
        ("volume", [docker, "volume", "ls", "-q", "--filter", label]),
        ("network", [docker, "network", "ls", "-q", "--filter", label]),
    ):
        try:
            identifiers = owned_run(command).decode().split()
            if identifiers:
                owned_run([docker, kind, "rm", *identifiers])
        except AcceptanceFailure:
            failed = True
    for image in (f"{project}-api", f"{project}-realtime"):
        if time.monotonic() >= deadline:
            failed = True
            break
        try:
            inspected = subprocess.run([docker, "image", "inspect", image], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=max(0.1, min(10, deadline - time.monotonic())), check=False)
        except (OSError, subprocess.SubprocessError):
            failed = True
            continue
        if inspected.returncode == 0:
            try:
                owned_run([docker, "image", "rm", image])
            except AcceptanceFailure:
                failed = True
    if failed:
        raise AcceptanceFailure("OWNED_PROJECT_CLEANUP_FAILED")



def wait_healthy(compose, env, docker, services, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready_services = True
        for service in services:
            container = run(compose + ["ps", "-q", service], env=env).decode().strip()
            if not container:
                ready_services = False
                break
            state = run([docker, "inspect", "--format", "{{.State.Health.Status}}", container],
                        env=env).decode().strip()
            if state != "healthy":
                ready_services = False
                break
        if ready_services:
            return
        time.sleep(2)
    raise AcceptanceFailure("PRODUCT_HEALTHCHECK_TIMEOUT")

def ready(compose, env, docker, ca_path, port):
    import ssl
    import urllib.error
    import urllib.request

    context = ssl.create_default_context(cafile=str(ca_path))
    url = f"https://{DOMAIN}:{port}/api/v1/auth/login"
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, context=context, timeout=3) as response:
                if response.status != 200:
                    raise AcceptanceFailure("TLS_API_EDGE_UNEXPECTED_STATUS")
        except urllib.error.HTTPError as error:
            if error.code in (400, 401, 405, 422):
                return
            raise AcceptanceFailure("TLS_API_EDGE_UNEXPECTED_STATUS") from None
        except (OSError, ssl.SSLError):
            time.sleep(2)
    raise AcceptanceFailure("TLS_API_EDGE_NOT_READY")


def protocol_oracle():
    spec = importlib.util.spec_from_file_location("hine_container_protocol", PROTOCOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def access_claims(session):
    token = session["access_token"].split(".")
    if len(token) != 3:
        raise AcceptanceFailure("SESSION_TOKEN_SHAPE_INVALID")
    payload = token[1] + "=" * (-len(token[1]) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    if not isinstance(claims.get("sid"), str) or not claims["sid"]:
        raise AcceptanceFailure("SESSION_TOKEN_CLAIMS_INVALID")
    return claims


async def assert_histories(protocol, exercise, http, target):
    for index, session in enumerate(exercise.sessions):
        expected = {delivery.ack_id: (delivery.sender_event if delivery.sender == session["user_id"]
                    else delivery.received) for delivery in exercise.deliveries.values()}
        items = await exercise.history_items(http, index)
        protocol.check_history(items, expected, session["user_id"], exercise.rooms[0])
        by_id = {item["id"]: item for item in items}
        for delivery in exercise.deliveries.values():
            item = by_id.get(delivery.ack_id)
            protocol.require(item is not None, "HISTORY_MISSING_PERSISTED_MESSAGE")
            if delivery.sender == session["user_id"]:
                protocol.require(item.get("client_message_id") == delivery.c1, "A19_SENDER_C1_MISMATCH")
                if delivery is target:
                    receipt = item.get("receipt")
                    protocol.require(isinstance(receipt, dict) and receipt.get("kind") == "direct" and
                        receipt.get("message_id") == delivery.ack_id and
                        receipt.get("recipient_id") == delivery.recipient and
                        receipt.get("status") == "read", "PERSISTED_READ_RECEIPT_MISMATCH")
            else:
                protocol.require("client_message_id" not in item and item.get("receipt") is None,
                                 "RECEIVER_PRIVATE_FIELDS_LEAKED")


async def exercise_messages_and_receipts(exercise, protocol, ca_path):
    import ssl

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=20)
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=str(ca_path)))
    async with aiohttp.ClientSession(timeout=timeout, connector=connector,
                                     cookie_jar=aiohttp.DummyCookieJar()) as http:
        clients = [protocol.Client(http, exercise.config["ws_url"], session, 20,
                    exercise.created, exercise.connections.update) for session in exercise.sessions]
        try:
            for client in clients:
                await client.connect()
            target = next(delivery for delivery in exercise.deliveries.values()
                          if delivery.sender == exercise.sessions[0]["user_id"])
            delivered = await clients[1].request("message.received", {"message_id": target.ack_id},
                                                 "receipt.ack", target.conversation)
            protocol.require(delivered.get("payload") == {"message_id": target.ack_id,
                "status": "delivered", "changed": True}, "W08_RECEIPT_ACK_MISMATCH")
            read = await clients[1].request("message.read", {"message_id": target.ack_id},
                                            "receipt.ack", target.conversation)
            protocol.require(read.get("payload") == {"message_id": target.ack_id,
                "status": "read", "changed": True}, "W09_RECEIPT_ACK_MISMATCH")
            await assert_histories(protocol, exercise, http, target)
            return {"messages": len(exercise.deliveries), "receipt_transitions": 2,
                    "sessions": len(exercise.sessions)}, target
        finally:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)


async def verify_restarted_product_state(exercise, protocol, ca_path, target):
    import ssl

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=20)
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=str(ca_path)))
    async with aiohttp.ClientSession(timeout=timeout, connector=connector,
                                     cookie_jar=aiohttp.DummyCookieJar()) as http:
        clients = [protocol.Client(http, exercise.config["ws_url"], session, 20,
                    exercise.created, exercise.connections.update) for session in exercise.sessions]
        try:
            for client in clients:
                await client.connect()
            await assert_histories(protocol, exercise, http, target)
        finally:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)

async def exercise_restored_clone(exercise, protocol, ca_path, target):
    import ssl

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=20)
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=str(ca_path)))
    async with aiohttp.ClientSession(timeout=timeout, connector=connector,
                                     cookie_jar=aiohttp.DummyCookieJar()) as http:
        clients = [protocol.Client(http, exercise.config["ws_url"], session, 20,
                    exercise.created, exercise.connections.update) for session in exercise.sessions]
        try:
            for client in clients:
                await client.connect()
            delivery = exercise.new_delivery(0)
            await exercise.ack(clients[0], delivery)
            await delivery.wait(20, sender_event=True)
            await assert_histories(protocol, exercise, http, target)
            return delivery
        finally:
            await asyncio.gather(*(client.close() for client in clients), return_exceptions=True)


def create_protocol_exercise(config, ca_path):
    previous_ca = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(ca_path)
    try:
        protocol = protocol_oracle()
        args = SimpleNamespace(mode="e2e", users=2, monitor_pid=None, timeout=20,
                               reconnect=False, state=None, duration=600)
        exercise = protocol.Exercise(args, config)
        try:
            asyncio.run(exercise.run())
        except asyncio.CancelledError:
            raise AcceptanceInterrupted() from None
        except (protocol.ProtocolFailure, OSError, TimeoutError):
            raise AcceptanceFailure("AUTHENTICATED_WSS_PROTOCOL_FAILED") from None
    finally:
        if previous_ca is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous_ca
    summary = exercise.report("passed")
    minimum = summary.get("authenticated_connections", {}).get("window_minimum") or {}
    if len(exercise.sessions) != 2 or len(exercise.deliveries) != 2 or minimum.get("wss") != 2:
        raise AcceptanceFailure("TWO_USER_WSS_PROTOCOL_EVIDENCE_MISSING")
    return exercise, protocol, {
        "attempted": summary.get("attempted"),
        "ack_and_receiver_or_sync_success": summary.get("ack_and_receiver_or_sync_success"),
        "authenticated_wss": minimum["wss"],
    }

def sql_literal(value):
    if not isinstance(value, str) or "\x00" in value:
        raise AcceptanceFailure("INVALID_DATABASE_SNAPSHOT_KEY")
    return "'" + value.replace("'", "''") + "'"


def postgres_query(compose, env, password_ref, database, sql):
    command = compose + ["exec", "-T", "postgres", "sh", "-c",
        f'PGPASSWORD="$(cat {password_ref})" psql -X -A -t -U hine -d {database}']
    return run(command, env=env, input_data=(sql + "\n").encode()).decode().strip()


def postgres_snapshot(compose, env, password_ref, database, conversation, session_ids):
    conv = sql_literal(conversation)
    session_values = ",".join(sql_literal(value) for value in session_ids)
    statements = {
        "conversation": f"""SELECT row_to_json(value)::text FROM (
            SELECT conversation_id,type,direct_pair FROM conversations WHERE conversation_id={conv}
        ) AS value""",
        "members": f"""SELECT COALESCE(json_agg(row_to_json(value) ORDER BY value.user_id)::text,'[]')
            FROM (SELECT user_id,role,joined_order,active FROM memberships
            WHERE conversation_id={conv}) AS value""",
        "messages": f"""SELECT COALESCE(json_agg(row_to_json(value) ORDER BY value.message_id)::text,'[]')
            FROM (SELECT m.message_id::text,m.event_id::text,m.client_message_id::text,
            m.conversation_id,m.sender_id,m.recipient_ids,m.payload,m.order_value,m.created_at,
            r.user_id AS receipt_user_id,r.status AS receipt_status,r.updated_at AS receipt_updated_at,
            r.status_event_id::text AS receipt_event_id
            FROM messages AS m LEFT JOIN receipts AS r ON r.message_id=m.message_id
            WHERE m.conversation_id={conv}) AS value""",
        "sessions": f"""SELECT COALESCE(json_agg(row_to_json(value) ORDER BY value.session_id)::text,'[]')
            FROM (SELECT s.session_id,s.subject_id,u.user_id,s.device_id,s.generation,s.revoked,
            s.access_expires_at,s.refresh_expires_at,s.created_at FROM sessions AS s
            JOIN users AS u ON u.subject_id=s.subject_id WHERE s.session_id IN ({session_values})) AS value""",
    }
    result = {}
    for name, sql in statements.items():
        value = postgres_query(compose, env, password_ref, database, sql)
        if name == "conversation":
            result[name] = json.loads(value) if value else None
        else:
            result[name] = json.loads(value)
    return result




def full_database_state(compose, env, password_ref, database):
    tables = json.loads(postgres_query(compose, env, password_ref, database, """
        SELECT COALESCE(json_agg(table_name ORDER BY table_name)::text, '[]')
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """))
    table_state = {}
    for name in tables:
        identifier = '"' + name.replace('"', '""') + '"'
        rows = postgres_query(compose, env, password_ref, database, f"""
            SELECT COALESCE(json_agg(row_data ORDER BY row_data::text)::text, '[]')
            FROM (SELECT to_jsonb(value) AS row_data FROM public.{identifier} AS value) AS rows
        """)
        table_state[name] = json.loads(rows)
    sequences = json.loads(postgres_query(compose, env, password_ref, database, """
        SELECT COALESCE(json_agg(row_to_json(value) ORDER BY value.schemaname, value.sequencename)::text, '[]')
        FROM (SELECT schemaname,sequencename,data_type,start_value,min_value,max_value,
              increment_by,cycle,cache_size,last_value FROM pg_sequences WHERE schemaname='public') AS value
    """))
    return {"tables": table_state, "sequences": sequences}


def assert_archive_matches(snapshot, exercise, target):
    user_ids = {session["user_id"] for session in exercise.sessions}
    if snapshot["conversation"] is None or snapshot["conversation"].get("type") != "direct":
        raise AcceptanceFailure("ARCHIVE_CONVERSATION_MISSING")
    if len(snapshot["members"]) != 2 or {member["user_id"] for member in snapshot["members"]} != user_ids or \
            len(snapshot["messages"]) != 2 or len(snapshot["sessions"]) != 2:
        raise AcceptanceFailure("ARCHIVE_PRODUCT_STATE_INCOMPLETE")
    by_c1 = {row["client_message_id"]: row for row in snapshot["messages"]}
    for delivery in exercise.deliveries.values():
        row = by_c1.get(delivery.c1)
        if row is None or row["message_id"] != delivery.ack_id or row["event_id"] != delivery.sender_event["event_id"]:
            raise AcceptanceFailure("ARCHIVE_C1_M1_MAPPING_MISMATCH")
        if set(row.get("recipient_ids", [])) != user_ids or row["sender_id"] != delivery.sender:
            raise AcceptanceFailure("ARCHIVE_MESSAGE_RECIPIENT_MISMATCH")
    row = by_c1.get(target.c1)
    if not row or row.get("receipt_user_id") != target.recipient or row.get("receipt_status") != "read" or \
            row.get("receipt_event_id") is None or row.get("receipt_updated_at") is None:
        raise AcceptanceFailure("ARCHIVE_RECEIPT_STATE_MISMATCH")
    claims = [access_claims(session) for session in exercise.sessions]
    sessions = {row["session_id"]: row for row in snapshot["sessions"]}
    for session, claim in zip(exercise.sessions, claims):
        row = sessions.get(claim["sid"])
        if row is None or row["subject_id"] != claim["sub"] or row["user_id"] != session["user_id"] or \
                row["device_id"] != session["device_id"] or row["generation"] != session["session_generation"] or \
                row["revoked"]:
            raise AcceptanceFailure("ARCHIVE_SESSION_STATE_MISMATCH")


def output_report(path, report):
    target = path.expanduser().absolute()
    exit_code = (0 if report["status"] == "passed" else
                 2 if report["status"] == "NOT_EXERCISED" else 1)
    report["exit_code"] = exit_code
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
        os.unlink(temporary)
        temporary = None
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError:
        print("acceptance: REPORT_PATH_EXISTS", file=sys.stderr)
        return 2
    except OSError:
        print("acceptance: REPORT_WRITE_FAILED", file=sys.stderr)
        return 2
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return exit_code



def isolated_environment():
    env = os.environ.copy()
    protected = ("COMPOSE_", "HINE_", "ACCEPTANCE_", "PUBLIC_ORIGIN", "WEB_ROOT", "POSTGRES_",
                "REDIS_", "JWT_", "ACME_", "API_INTERNAL_URL", "TRUSTED_PROXY_NETWORKS",
                "GCS_", "INVALIDATION_RETENTION_SECONDS", "DOCKER_HOST", "DOCKER_CONTEXT")
    for key in tuple(env):
        if key.startswith(protected):
            env.pop(key)
    env["DOCKER_CONTEXT"] = "default"
    return env


class AcceptanceInterrupted(Exception):
    pass


def interrupt_on_termination(_signum, _frame):
    raise AcceptanceInterrupted()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--docker", type=Path)
    result.add_argument("--web-root", type=Path)
    return result


def main():
    owned_project = None
    docker_env = isolated_environment()
    args = parser().parse_args()
    target = args.output.expanduser().absolute()
    if target.exists() or target.is_symlink():
        print("acceptance: REPORT_PATH_EXISTS", file=sys.stderr)
        return 2
    docker = str(args.docker) if args.docker else shutil.which("docker")
    report = {"status": "failed", "failure_code": None,
              "images": ["postgres:17-alpine", "redis:7-alpine", "caddy:2-alpine"],
              "evidence": {"images_built": [], "migration": "not_run", "tls_api": "not_run",
                           "authenticated_wss": "not_run", "restart_persistence": "not_run",
                           "archive_restore": "not_run", "static_web": "not_requested"}}
    if not docker or (args.docker and
                      (not args.docker.is_file() or not os.access(args.docker, os.X_OK))):
        report.update(status="NOT_EXERCISED", failure_code="DOCKER_CLI_UNAVAILABLE")
        return output_report(args.output, report)
    if args.web_root:
        web_root = args.web_root.expanduser().resolve()
        if not web_root.is_dir() or not (web_root / "index.html").is_file():
            report.update(failure_code="WEB_ROOT_NOT_A_BUILT_SITE")
            return output_report(args.output, report)
        report["evidence"]["static_web"] = "requested"
    old_signals = {signum: signal.signal(signum, interrupt_on_termination)
                   for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        with tempfile.TemporaryDirectory(prefix="hine-product-acceptance-") as private:
            os.chmod(private, 0o700)
            private = Path(private)
            secret_dir = private / "secrets"
            secret_dir.mkdir(mode=0o700)
            project = "hine-accept-" + secrets.token_hex(8)
            port = free_port()
            env_path = private / "compose.env"
            db_password, redis_password, signing_key = (
                secrets.token_hex(32), secrets.token_hex(32), secrets.token_hex(32))
            database_url = f"postgresql://hine:{quote(db_password, safe='')}@postgres:5432/hine"
            redis_url = f"redis://:{quote(redis_password, safe='')}@redis:6379/0"
            compose_env = docker_env.copy()
            compose_env.pop("COMPOSE_FILE", None)
            compose_env.pop("COMPOSE_PROFILES", None)
            context_host = run([docker, "context", "inspect", "default", "--format",
                                "{{.Endpoints.docker.Host}}"], env=compose_env).decode().strip()
            if not context_host.startswith(("unix://", "tcp://127.0.0.1:",
                                            "tcp://localhost:", "tcp://[::1]:")):
                raise AcceptanceFailure("LOCAL_DOCKER_CONTEXT_REQUIRED")
            try:
                run([docker, "info", "--format", "{{.ServerVersion}}"], env=compose_env, timeout=20)
            except AcceptanceFailure:
                raise AcceptanceUnavailable("DOCKER_ENGINE_UNAVAILABLE") from None
            edge_cidr, backend_cidr = isolated_subnets(docker, compose_env)
            values = {
                "HINE_SECRET_DIR": str(secret_dir), "POSTGRES_DB": "hine", "POSTGRES_USER": "hine",
                "HINE_DOMAIN": DOMAIN, "PUBLIC_ORIGIN": f"https://{DOMAIN}:{port}",
                "API_INTERNAL_URL": "http://api:8080",
                "TRUSTED_PROXY_NETWORKS": f"{edge_cidr},{backend_cidr}",
                "HINE_RUNTIME_UID": str(os.getuid()), "HINE_RUNTIME_GID": str(os.getgid()),
                "ACCEPTANCE_HTTPS_PORT": str(port),
                "ACCEPTANCE_EDGE_SUBNET": str(edge_cidr), "ACCEPTANCE_BACKEND_SUBNET": str(backend_cidr),
                "HINE_ENV": "production", "JWT_ISSUER": "hine", "JWT_AUDIENCE": "hine-web",
            }
            write_private(env_path, ("\n".join(f"{key}={value}" for key, value in values.items()) + "\n").encode())
            secrets_map = {
                "postgres_password": db_password, "redis_password": redis_password, "redis_url": redis_url,
                "api_internal_token": secrets.token_hex(32), "realtime_internal_token": secrets.token_hex(32),
                "database_url": database_url, "jwt_signing_key": signing_key,
            }
            for name, value in secrets_map.items():
                write_private(secret_dir / name, value.encode())
            base = [docker, "compose", "--project-name", project, "--env-file", str(env_path),
                    "-f", str(ROOT / "docker-compose.yml"), "-f", str(OVERLAY)]
            if args.web_root:
                runtime_config = private / "runtime-config.js"
                origin = f"https://{DOMAIN}:{port}"
                config_js = ("window.HINE_CONFIG=Object.freeze(" + json.dumps({
                    "API_BASE_URL": origin + "/api/v1", "WS_URL": f"wss://{DOMAIN}:{port}/ws/v1",
                    "SYNC_RECONCILE_SECONDS": 10}, separators=(",", ":")) + ");\n").encode()
                write_private(runtime_config, config_js)
                extra = private / "web-root.yml"
                source = json.dumps(str(web_root))
                runtime = json.dumps(str(runtime_config))
                extra_data = ("services:\n  caddy:\n    volumes:\n      - type: bind\n        source: " +
                    source + "\n        target: /srv/hine\n        read_only: true\n        bind:\n          create_host_path: false\n" +
                    "      - type: bind\n        source: " + runtime + "\n        target: /srv/hine/runtime-config.js\n" +
                    "        read_only: true\n        bind:\n          create_host_path: false\n")
                write_private(extra, extra_data.encode())
                base += ["-f", str(extra)]
            compose = base + ["--profile", "product", "--profile", "realtime", "--profile", "acceptance"]
            collision = run([docker, "volume", "ls", "--filter",
                             f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"], env=compose_env)
            containers = run([docker, "ps", "-aq", "--filter",
                              f"label=com.docker.compose.project={project}"], env=compose_env)
            if collision.strip() or containers.strip() or owned_network(project, compose_env, docker):
                raise AcceptanceFailure("PROJECT_NAME_COLLISION")
            for image in (f"{project}-api", f"{project}-realtime"):
                inspected = subprocess.run([docker, "image", "inspect", image], env=compose_env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                if inspected.returncode == 0:
                    raise AcceptanceFailure("PROJECT_NAME_COLLISION")
            owned_project = project
            compose_json = json.loads(run(compose + ["config", "--format", "json"], env=compose_env))
            services = compose_json.get("services", {})
            for service in ("api", "realtime", "postgres", "redis", "caddy"):
                if service not in services:
                    raise AcceptanceFailure("COMPOSE_SERVICE_MISSING")
            networks = compose_json.get("networks", {})
            if networks.get("backend", {}).get("internal") is not True:
                raise AcceptanceFailure("BACKEND_NETWORK_NOT_PRIVATE")
            for service in ("postgres", "redis", "realtime"):
                if set(services[service].get("networks", {})) != {"backend"}:
                    raise AcceptanceFailure("BACKEND_SERVICE_NETWORK_EXPOSED")
            if set(services["api"].get("networks", {})) != {"backend", "edge"} or \
                    set(services["caddy"].get("networks", {})) != {"backend", "edge"}:
                raise AcceptanceFailure("EDGE_SERVICE_NETWORK_TOPOLOGY_INVALID")
            if services["api"].get("environment", {}).get("HINE_ENV") != "production" or \
                    services["realtime"].get("environment", {}).get("HINE_ENV") != "production":
                raise AcceptanceFailure("PRODUCTION_MODE_NOT_SELECTED")
            published = services["caddy"].get("ports", [])
            if len(published) != 1 or published[0].get("target") != 443 or \
                    published[0].get("host_ip") != "127.0.0.1" or published[0].get("protocol", "tcp") != "tcp":
                raise AcceptanceFailure("ACCEPTANCE_EDGE_BINDING_INVALID")
            if not all(services[name].get("build") for name in ("api", "realtime")):
                raise AcceptanceFailure("SOURCE_OWNED_IMAGE_BUILD_MISSING")
            if services["postgres"].get("ports") or services["redis"].get("ports") or \
                    services["api"].get("ports") or services["realtime"].get("ports"):
                raise AcceptanceFailure("PRIVATE_SERVICE_PORT_PUBLISHED")
            run(compose + ["build", "api", "realtime"], env=compose_env, timeout=1800)
            report["evidence"]["images_built"] = ["api", "realtime"]
            run(compose + ["up", "-d", "postgres", "redis"], env=compose_env)
            wait_healthy(compose, compose_env, docker, ("postgres", "redis"))
            run(compose + ["run", "--rm", "--no-deps", "api", "python", "-m", "hine_api", "migrate"],
                env=compose_env)
            report["evidence"]["migration"] = "production_migration_applied"
            run(compose + ["up", "-d", "api", "realtime", "caddy"], env=compose_env)
            wait_healthy(compose, compose_env, docker, ("api", "realtime", "postgres", "redis"))
            deadline = time.monotonic() + 180
            ca = private / "root-ca.pem"
            while time.monotonic() < deadline:
                try:
                    cert = run(compose + ["exec", "-T", "caddy", "cat",
                              "/data/caddy/pki/authorities/local/root.crt"], env=compose_env, timeout=15)
                    if b"BEGIN CERTIFICATE" in cert:
                        write_private(ca, cert)
                        break
                except AcceptanceFailure:
                    time.sleep(2)
            if not ca.exists():
                raise AcceptanceFailure("TLS_CA_NOT_READY")
            ready(compose, compose_env, docker, ca, port)
            wait_healthy(compose, compose_env, docker, ("api", "realtime", "postgres", "redis"))
            report["evidence"]["tls_api"] = "verified_local_ca"
            login = [{"register": True, "display_name": "Acceptance One", "login": {
                          "email": "one@product.test", "password": secrets.token_urlsafe(24), "device_id": None}},
                     {"register": True, "display_name": "Acceptance Two", "login": {
                          "email": "two@product.test", "password": secrets.token_urlsafe(24), "device_id": None}}]
            config = {"api_base_url": f"https://{DOMAIN}:{port}",
                      "ws_url": f"wss://{DOMAIN}:{port}/ws/v1", "users": login}
            exercise, protocol, protocol_summary = create_protocol_exercise(config, ca)
            receipt_summary, target_delivery = asyncio.run(
                exercise_messages_and_receipts(exercise, protocol, ca))
            report["evidence"]["authenticated_wss"] = "two_user_c1_m1_w08_w09_receipt_history"
            report["protocol"] = {**protocol_summary, **receipt_summary}
            run(compose + ["restart", "postgres", "redis", "api", "realtime"], env=compose_env, timeout=240)
            wait_healthy(compose, compose_env, docker, ("api", "realtime", "postgres", "redis"))
            ready(compose, compose_env, docker, ca, port)
            asyncio.run(verify_restarted_product_state(exercise, protocol, ca, target_delivery))
            report["evidence"]["restart_persistence"] = "original_access_sessions_c1_m1_receipt_and_histories_verified"
            password_ref = "/run/secrets/postgres_password"
            session_ids = [access_claims(session)["sid"] for session in exercise.sessions]
            run(compose + ["stop", "--timeout", "20", "realtime", "api", "caddy"],
                env=compose_env, timeout=60)
            original = postgres_snapshot(compose, compose_env, password_ref, "hine",
                                         exercise.rooms[0], session_ids)
            assert_archive_matches(original, exercise, target_delivery)
            original_state = full_database_state(compose, compose_env, password_ref, "hine")
            dump = run(compose + ["exec", "-T", "postgres", "sh", "-c",
                       f'PGPASSWORD="$(cat {password_ref})" pg_dump -U hine -d hine -Fc'],
                       env=compose_env, timeout=240)
            write_private(private / "product.dump", dump)
            run(compose + ["exec", "-T", "postgres", "sh", "-c",
                f'PGPASSWORD="$(cat {password_ref})" createdb -U hine hine_restore'], env=compose_env)
            run(compose + ["exec", "-T", "postgres", "sh", "-c",
                f'PGPASSWORD="$(cat {password_ref})" pg_restore --single-transaction --exit-on-error -U hine -d hine_restore'],
                env=compose_env, input_data=dump, timeout=300)
            restored = postgres_snapshot(compose, compose_env, password_ref, "hine_restore",
                                         exercise.rooms[0], session_ids)
            restored_state = full_database_state(compose, compose_env, password_ref, "hine_restore")
            assert_archive_matches(restored, exercise, target_delivery)
            if original != restored or original_state != restored_state:
                raise AcceptanceFailure("ARCHIVE_RESTORE_PRODUCT_STATE_MISMATCH")
            replace_private(secret_dir / "database_url",
                            (database_url.rsplit("/", 1)[0] + "/hine_restore").encode())
            run(compose + ["up", "-d", "api", "realtime", "caddy"], env=compose_env, timeout=180)
            wait_healthy(compose, compose_env, docker, ("api", "realtime", "postgres", "redis"))
            ready(compose, compose_env, docker, ca, port)
            clone_delivery = asyncio.run(
                exercise_restored_clone(exercise, protocol, ca, target_delivery))
            after_restore = postgres_snapshot(compose, compose_env, password_ref, "hine_restore",
                                              exercise.rooms[0], session_ids)
            by_c1 = {row["client_message_id"]: row for row in after_restore["messages"]}
            new_row = by_c1.get(clone_delivery.c1)
            if len(after_restore["messages"]) != len(original["messages"]) + 1 or \
                    any(by_c1.get(row["client_message_id"]) != row for row in original["messages"]) or \
                    new_row is None or new_row["message_id"] != clone_delivery.ack_id or \
                    new_row["event_id"] != clone_delivery.sender_event["event_id"]:
                raise AcceptanceFailure("RESTORED_DATABASE_WRITE_FAILED")
            report["evidence"]["archive_restore"] = "full_database_clone_bound_to_api_original_sessions_and_new_wss_write"
            report["durable_counts"] = {"conversations": 1, "messages": len(original["messages"]),
                                        "receipts": sum(row["receipt_status"] is not None
                                                        for row in original["messages"]),
                                        "sessions": len(original["sessions"])}
            if args.web_root:
                import ssl
                import urllib.request
                request = urllib.request.Request(f"https://{DOMAIN}:{port}/", method="GET")
                with urllib.request.urlopen(request, context=ssl.create_default_context(cafile=str(ca)), timeout=10) as response:
                    if response.status != 200 or b"<html" not in response.read(65536).lower():
                        raise AcceptanceFailure("STATIC_WEB_EDGE_FAILED")
                runtime_request = urllib.request.Request(f"https://{DOMAIN}:{port}/runtime-config.js")
                with urllib.request.urlopen(runtime_request, context=ssl.create_default_context(cafile=str(ca)), timeout=10) as response:
                    expected = f"https://{DOMAIN}:{port}/api/v1".encode()
                    if response.status != 200 or expected not in response.read(65536):
                        raise AcceptanceFailure("STATIC_RUNTIME_CONFIG_MISMATCH")
                report["evidence"]["static_web"] = "real_build_and_owned_runtime_config_over_verified_tls"
            versions = run([docker, "version", "--format", "{{.Client.Version}}/{{.Server.Version}}"],
                           env=compose_env).decode().strip()
            report["tool_versions"] = {"docker_client_server": versions}
            report["source_sha256"] = {"runner": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "base_compose": hashlib.sha256((ROOT / "docker-compose.yml").read_bytes()).hexdigest(),
                "acceptance_compose": hashlib.sha256(OVERLAY.read_bytes()).hexdigest(),
                "api_dockerfile": hashlib.sha256((ROOT / "backend/api/Dockerfile").read_bytes()).hexdigest(),
                "realtime_dockerfile": hashlib.sha256((ROOT / "backend/realtime/Dockerfile").read_bytes()).hexdigest(),
                "acceptance_caddyfile": hashlib.sha256((ROOT / "infra/docker/Caddyfile.acceptance").read_bytes()).hexdigest(),
                "protocol_oracle": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()}
            report["status"] = "passed"
    except AcceptanceInterrupted:
        report.update(status="cancelled", failure_code="INTERRUPTED")
    except AcceptanceUnavailable as error:
        report.update(status="NOT_EXERCISED", failure_code=error.code)
    except AcceptanceFailure as error:
        report["failure_code"] = error.code
        report["failure_sites"] = _failure_sites(error)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        report["failure_code"] = "INVALID_TOOL_OR_PRODUCT_RESULT"
        report["failure_sites"] = _failure_sites(error)
    except (OSError, subprocess.SubprocessError) as error:
        report["failure_code"] = "LOCAL_TOOL_FAILED"
        report["failure_sites"] = _failure_sites(error)
    except Exception as error:  # noqa: BLE001 - CLI privacy boundary never exposes product credentials or private traceback data.
        report["failure_code"] = "PRODUCT_ACCEPTANCE_FAILED"
        report["failure_sites"] = _failure_sites(error)
    finally:
        for signum in old_signals:
            signal.signal(signum, signal.SIG_IGN)
        if owned_project:
            try:
                cleanup_project(docker, owned_project, docker_env)
            except AcceptanceFailure:
                report.update(status="failed", failure_code="OWNED_PROJECT_CLEANUP_FAILED")
    exit_code = output_report(args.output, report)
    for signum, handler in old_signals.items():
        signal.signal(signum, handler)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
