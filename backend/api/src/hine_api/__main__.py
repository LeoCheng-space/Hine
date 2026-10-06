"""Python 3.12 service entrypoint and explicit production migrations."""
import asyncio
import logging
import sys

import aiohttp
import asyncpg
from aiohttp import web

from . import db
from .config import Settings
from .server import create_app


async def migration(settings):
    if not settings.valid:
        raise RuntimeError("CONFIG_MISSING")
    pool = await db.create_pool(settings)
    try:
        await db.migrate(pool)
    finally:
        await pool.close()


async def migration_outcome(settings):
    (outcome,) = await asyncio.gather(migration(settings), return_exceptions=True)
    return outcome


def fatal_error(_exception_type, _exception, _traceback):
    # Unhandled defects still terminate with Python's nonzero exit status,
    # but the CLI must not print private exception values or tracebacks.
    print("API fatal error", file=sys.stderr)


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    if sys.argv[1:] == ["migrate"]:
        outcome = asyncio.run(migration_outcome(settings))
        if isinstance(outcome, BaseException):
            raise SystemExit("API migration unavailable")
        return 0
    if sys.argv[1:]:
        print("Usage: python -m hine_api [migrate]", file=sys.stderr)
        return 2
    # No access logger: URL paths can contain private identifiers.
    try:
        web.run_app(create_app(settings), host=settings.host, port=settings.port, access_log=None, print=None)
    except (asyncpg.PostgresError, aiohttp.ClientError, OSError, RuntimeError, ValueError):
        raise SystemExit("API startup unavailable") from None
    return 0


if __name__ == "__main__":
    sys.excepthook = fatal_error
    raise SystemExit(main())
