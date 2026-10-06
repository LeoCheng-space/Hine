"""Real native API processes and isolated PostgreSQL schemas; never skips prerequisites."""
import asyncio
import json
import os
import secrets
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import asyncpg

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "correct horse battery staple"


def assert_secret_free(case, secret_values, representation):
    if any(value in representation for value in secret_values):
        case.fail("Private diagnostic value exposed")


class ApiHarness:
    def __init__(self):
        self.process = None
        self.pool = None
        self.session = None
        self.last_cookie = None
        self.temp = tempfile.TemporaryDirectory(prefix="hine-api-test-")
        self.schema = "product_" + secrets.token_hex(10)
        self.origin = "https://product.test"
        self.base_url = ""
        self.settings_env = {}

    async def __aenter__(self):
        try:
            await self.start()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self):
        reference = os.environ.get("HINE_TEST_API_ENV_REF")
        inherited = json.loads(Path(reference).read_text()) if reference else {}
        dsn = os.environ.get("HINE_TEST_DATABASE_URL") or inherited.get("DATABASE_URL")
        if not dsn and inherited.get("DATABASE_URL_SECRET_REF"):
            dsn = Path(inherited["DATABASE_URL_SECRET_REF"]).read_text().rstrip("\r\n")
        if not dsn:
            raise RuntimeError("Real PostgreSQL required: HINE_TEST_DATABASE_URL or HINE_TEST_API_ENV_REF")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        directory = Path(self.temp.name)
        private = {}
        for name in ("database", "jwt", "outbound", "inbound"):
            path = directory / name
            path.write_text(dsn if name == "database" else secrets.token_urlsafe(48))
            path.chmod(0o600)
            private[name] = str(path)
        self.service_token = Path(private["inbound"]).read_text()
        self.signing_key = Path(private["jwt"]).read_text()
        self.settings_env = dict(os.environ, **inherited)
        self.settings_env.update({
            "HINE_ENV": "test", "PUBLIC_ORIGIN": self.origin,
            "DATABASE_URL_SECRET_REF": private["database"], "DATABASE_SCHEMA": self.schema,
            "JWT_ISSUER": "hine-product-tests", "JWT_AUDIENCE": "hine-product-browser",
            "JWT_SIGNING_KEY_SECRET_REF": private["jwt"],
            "REALTIME_INTERNAL_URL": "http://127.0.0.1:1",
            "INTERNAL_CALLER_TOKEN_SECRET_REF": private["outbound"],
            "INTERNAL_ALLOWED_CALLERS": json.dumps({"realtime": private["inbound"]}),
            "SYNC_PAGE_LIMIT": "100", "SYNC_SCAN_LIMIT": "1000",
            "INVALIDATION_RETENTION_SECONDS": "900", "API_HOST": "127.0.0.1", "API_PORT": str(port),
            "PYTHONPATH": os.pathsep.join([str(ROOT / "backend/api/src"), str(ROOT / "backend/realtime/src"), os.environ.get("PYTHONPATH", "")]),
        })
        # Only create a unique owned schema. Never DROP an operator schema or database.
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'CREATE SCHEMA "{self.schema}"')
        finally:
            await conn.close()
        async def init(conn):
            for typ in ("json", "jsonb"):
                await conn.set_type_codec(typ, schema="pg_catalog", encoder=json.dumps, decoder=json.loads)
        self.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8, init=init, server_settings={"search_path": self.schema})
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(), timeout=aiohttp.ClientTimeout(total=15))
        await self._launch()

    async def _launch(self, require_ready=True):
        self.process = await asyncio.create_subprocess_exec(sys.executable, "-m", "hine_api", cwd=ROOT, env=self.settings_env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        deadline = asyncio.get_running_loop().time() + 20
        while asyncio.get_running_loop().time() < deadline:
            if self.process.returncode is not None:
                raise AssertionError("PRODUCT_API_EXITED_BEFORE_REGISTER_LOGIN")
            try:
                async with self.session.get(self.base_url + ("/health/ready" if require_ready else "/health/live")) as reply:
                    if reply.status == 200:
                        return
            except (aiohttp.ClientError, TimeoutError):
                pass
            await asyncio.sleep(0.05)
        raise AssertionError("PRODUCT_API_NOT_READY")

    async def restart(self, require_ready=True):
        await self.stop_process()
        await self._launch(require_ready=require_ready)

    async def stop_process(self):
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 10)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def close(self):
        await self.stop_process()
        if self.session is not None:
            await self.session.close()
            self.session = None
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
        self.temp.cleanup()

    async def request(self, method, path, session=None, json=None, headers=None, cookie=None, raw=None):
        outgoing = {"Origin": self.origin, **(headers or {})}
        if session is not None:
            outgoing["Authorization"] = "Bearer " + session["access_token"]
        if cookie is not False and (cookie or self.last_cookie):
            outgoing["Cookie"] = cookie or self.last_cookie
        async with self.session.request(method, self.base_url + path, json=json, data=raw, headers=outgoing) as reply:
            self.last_headers = dict(reply.headers)
            if "Set-Cookie" in reply.headers:
                self.last_cookie = reply.headers["Set-Cookie"].split(";", 1)[0]
            decoded = await reply.json() if reply.status != 204 else None
            return reply.status, decoded

    async def signup(self, email=None, password=PASSWORD, display_name="Tester"):
        email = email or secrets.token_hex(12) + "@product.test"
        status, result = await self.request("POST", "/api/v1/auth/register", json={"email": email, "password": password, "display_name": display_name})
        assert status == 201, (status, result)
        return result["data"]

    async def login(self, email, password=PASSWORD, device_id=None):
        status, result = await self.request("POST", "/api/v1/auth/login", json={"email": email, "password": password, "device_id": device_id})
        assert status == 200, (status, result)
        return result["data"]

    async def internal(self, operation, body, token=None):
        return await self.request("POST", "/internal/v1/" + operation, json=body, headers={"Authorization": "Bearer " + (self.service_token if token is None else token)}, cookie=False)

    async def binding(self, access):
        status, result = await self.internal("validateAccess", {"access_token": access["access_token"], "device_id": access["device_id"]})
        assert status == 200, (status, result)
        return {**result["data"], "device_id": access["device_id"]}


class ProductCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = await ApiHarness().__aenter__()
        self.runtime = SimpleNamespace(pool=self.api.pool)
        self.client = self.api.session

    async def asyncTearDown(self):
        await self.api.close()

    async def account(self, name):
        profile = await self.api.signup(secrets.token_hex(8) + "@product.test", display_name=name)
        return profile, await self.api.login(profile["email"])

    async def request(self, method, path, access=None, json=None, headers=None):
        return await self.api.request(method, path, session=access, json=json, headers=headers)

    async def internal(self, operation, payload):
        status, result = await self.api.internal(operation, payload)
        self.assertEqual(status, 200, result)
        return result["data"]
