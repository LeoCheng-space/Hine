"""Actual REST gateway and private service provider; no authority fallbacks."""
import asyncio
import hmac
import logging

import aiohttp
import asyncpg
from aiohttp import web
from hine_realtime import protocol as p

from . import db
from .config import Settings
from .support import Fault, body, error, response

RUNTIME = web.AppKey("api", object)
LOG = logging.getLogger("hine_api")


class Runtime:
    def __init__(self, settings):
        from .auth import AuthService
        from .storage import GcsStorage
        self.settings = settings
        self.pool = None
        self.http = None
        self.auth = AuthService(self)
        self.storage = GcsStorage(settings)
        self.pool_lock = asyncio.Lock()
        self.schema_ready = False

    async def connect(self):
        if self.pool is not None or not self.settings.valid:
            return
        async with self.pool_lock:
            if self.pool is not None:
                return
            pool = await db.create_pool(self.settings)
            try:
                if self.settings.environment in {"test", "dev", "development"}:
                    await db.migrate(pool)
                else:
                    await db.verify_migrations(pool)
            except BaseException:
                await pool.close()
                raise
            self.pool = pool
            self.schema_ready = True

    async def notify(self, notice):
        # Commit is final. Collect ordinary notifier failures without allowing
        # their private exception details to reach REST or aiohttp's logger.
        (outcome,) = await asyncio.gather(self._notify_once(notice), return_exceptions=True)
        if isinstance(outcome, Exception):
            LOG.warning("committed_notice_unavailable")
        elif isinstance(outcome, BaseException):
            raise outcome

    async def _notify_once(self, notice):
        p.notice(notice, external=True)
        async with self.http.post(self.settings.realtime_url + "/internal/v1/publishCommitted", json={"notice": notice}, headers={"Authorization": "Bearer " + self.settings.outbound_token}, allow_redirects=False) as reply:
            # Never read or log an untrusted upstream error body.
            if reply.status != 200:
                LOG.warning("committed_notice_unavailable")

    async def lifecycle(self, app):
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.dependency_timeout), trust_env=False)
        try:
            if self.settings.valid:
                try:
                    await self.connect()
                except (asyncpg.PostgresError, OSError, TimeoutError):
                    LOG.warning("database_unavailable")
            yield
        finally:
            await self.storage.close()
            if self.pool is not None:
                await self.pool.close()
            await self.http.close()


@web.middleware
async def errors(request, handler):
    (outcome,) = await asyncio.gather(known_errors(request, handler), return_exceptions=True)
    if isinstance(outcome, Exception):
        # Unexpected faults never produce a success ACK or a private traceback.
        # A mutation may already have committed, so do not claim known rollback.
        LOG.error("request_failed")
        code = "OUTCOME_UNCONFIRMED" if request.method in {"POST", "PATCH", "DELETE"} else "DEPENDENCY_UNAVAILABLE"
        return error(Fault(code, True))
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


async def known_errors(request, handler):
    try:
        rt = request.app[RUNTIME]
        if request.path.startswith("/api/v1/"):
            if request.method in {"GET", "DELETE"} and request.can_read_body:
                raise Fault("INVALID_ARGUMENT")
            if not rt.settings.valid or rt.pool is None or not rt.schema_ready:
                raise Fault("DEPENDENCY_UNAVAILABLE", True)
        return await handler(request)
    except Fault as failure:
        if not request.path.startswith("/internal/"):
            failure.auth_layer = None
        return error(failure)
    except (p.Invalid, TypeError, KeyError, UnicodeError, RecursionError):
        return error(Fault("INVALID_ARGUMENT"))
    except web.HTTPRequestEntityTooLarge:
        return error(Fault("PAYLOAD_TOO_LARGE"))
    except web.HTTPException as failure:
        return error(Fault("NOT_FOUND" if failure.status == 404 else "INVALID_ARGUMENT"))
    except (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, ConnectionResetError):
        code = "OUTCOME_UNCONFIRMED" if request.method in {"POST", "PATCH", "DELETE"} else "DEPENDENCY_UNAVAILABLE"
        LOG.warning("database_connection_unavailable")
        return error(Fault(code, True))
    except (asyncpg.PostgresError, OSError, TimeoutError):
        LOG.warning("database_dependency_unavailable")
        return error(Fault("DEPENDENCY_UNAVAILABLE", True))


async def provider(request):
    rt = request.app[RUNTIME]
    supplied = request.headers.get("Authorization", "")
    expected = "Bearer " + rt.settings.realtime_token
    if not rt.settings.valid or not rt.settings.realtime_token or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise Fault("UNAUTHENTICATED", auth_layer="service_identity")
    # Service identity MUST precede body/type/canonical user validation.
    if rt.pool is None or not rt.schema_ready:
        raise Fault("DEPENDENCY_UNAVAILABLE", True)
    value = await body(request)
    operation = request.match_info["operation"]
    if operation == "validateAccess":
        result = await rt.auth.validate_access(value)
    elif operation == "readSessionInvalidations":
        result = await rt.auth.read_invalidations(value)
    else:
        from . import domain
        result = await domain.internal(rt, operation, value)
    return response(result)


async def health(request):
    rt = request.app[RUNTIME]
    dependencies = {"postgresql": "not_checked", "redis": "not_checked"}
    ready = True
    reason = None
    if request.path == "/health/ready":
        if not rt.settings.valid:
            ready = False
            reason = "CONFIG_MISSING"
        else:
            try:
                async with asyncio.timeout(rt.settings.dependency_timeout):
                    await rt.connect()
                    async with rt.pool.acquire() as conn:
                        await conn.fetchval("SELECT 1 FROM authority_state WHERE id=1")
                    if not rt.schema_ready:
                        raise RuntimeError("Schema unavailable")
                dependencies["postgresql"] = "ok"
            except (asyncpg.PostgresError, OSError, TimeoutError, RuntimeError, asyncpg.InterfaceError):
                dependencies["postgresql"] = "fail"
                ready = False
    result = {"status": "ok" if ready else "unready", "service": "api", "timestamp": p.now(), "dependencies": dependencies}
    if reason is not None:
        result["reason"] = reason
    return web.json_response(result, status=200 if ready else 503, dumps=p.dumps)


def create_app(settings=None):
    from . import attachments, auth, domain
    settings = Settings.from_env() if settings is None else settings
    app = web.Application(client_max_size=1048576, middlewares=[errors])
    runtime = Runtime(settings)
    app[RUNTIME] = runtime
    app.cleanup_ctx.append(runtime.lifecycle)
    app.router.add_get("/health/live", health)
    app.router.add_get("/health/ready", health)
    app.router.add_post("/internal/v1/{operation}", provider)
    auth.register(app)
    domain.register(app)
    attachments.register(app)
    return app
