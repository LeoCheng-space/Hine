#!/usr/bin/env python3
"""Resolve the two literal Compose PostgreSQL targets without executing dotenv."""
import os
import re
import shlex
import sys
from pathlib import Path

IDENTIFIER = re.compile(r"[A-Za-z0-9_]{1,63}\Z")
ASSIGNMENT = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*\Z")
LITERAL = re.compile(r"(?:([A-Za-z0-9_]*)|\"([A-Za-z0-9_]*)\"|'([A-Za-z0-9_]*)')(?:\s+#.*)?\Z")


def targets(path, environment=None):
    environment = os.environ if environment is None else environment
    values = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        assignment = ASSIGNMENT.fullmatch(line)
        if assignment is None:
            # Compose supports additional syntax, including colon-delimited
            # and multiline values. Never scan their continuations as targets.
            raise ValueError("Unsupported dotenv configuration")
        name, value = assignment.groups()
        # An unrelated multiline value must not make its continuation look
        # like a target assignment. Unsupported multiline syntax fails closed.
        shlex.split(value, comments=True, posix=True)
        if name not in {"POSTGRES_DB", "POSTGRES_USER"}:
            continue
        if name in values:
            # Reject duplicate declarations, even if an environment override
            # would happen to hide them; no ambiguous reference is generated.
            raise ValueError("Ambiguous target configuration")
        literal = LITERAL.fullmatch(value)
        if literal is None:
            raise ValueError("Target must be a literal identifier")
        values[name] = next(item for item in literal.groups() if item is not None)
    result = []
    for name in ("POSTGRES_USER", "POSTGRES_DB"):
        # An explicitly empty environment value still overrides dotenv, then
        # Compose's ${NAME:-hine} chooses the default.
        value = (environment[name] if name in environment else values.get(name, "")) or "hine"
        if IDENTIFIER.fullmatch(value) is None:
            raise ValueError("Invalid target identifier")
        result.append(value)
    return tuple(result)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Invalid arguments")
        print(" ".join(targets(sys.argv[1])))
    except (OSError, ValueError):
        print("PostgreSQL target configuration is invalid or ambiguous", file=sys.stderr)
        raise SystemExit(1) from None
