"""python -m hine_realtime; TLS terminates at the private-network proxy."""
import logging
import sys

from aiohttp import web

from .config import Settings
from .server import create_app


def main():
    if sys.version_info < (3, 12):
        raise SystemExit("Realtime requires Python 3.12 or newer")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    # No aiohttp access log: public queries/headers must not become credential
    # or message-text diagnostics. Runtime logs only fixed categories/codes.
    web.run_app(create_app(settings), host=settings.host, port=settings.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
