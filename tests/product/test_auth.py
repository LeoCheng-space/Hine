"""Consumer-visible auth/privacy failures against a real native API and PostgreSQL."""
import asyncio
import secrets

import jwt
from support import PASSWORD, ProductCase


class AuthTests(ProductCase):
    async def test_registration_has_no_session_and_identity_survives_restart(self):
        profile = await self.api.signup()
        self.assertEqual(set(profile), {"id", "email", "display_name", "avatar_attachment_id"})
        self.assertIsNone(self.api.last_cookie)
        access = await self.api.login(profile["email"])
        self.assertEqual(access["user_id"], profile["id"])
        self.assertEqual(set(access), {"access_token", "expires_at", "user_id", "device_id", "session_generation"})
        self.assertNotIn("refresh_token", access)
        cookie = self.api.last_headers["Set-Cookie"]
        for attribute in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/api/v1/auth"):
            self.assertIn(attribute, cookie)
        binding = await self.api.binding(access)
        self.assertNotEqual(binding["subject_id"], profile["id"])
        await self.api.restart()
        status, result = await self.request("GET", "/api/v1/users/me", access)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], profile)

    async def test_refresh_rotates_once_old_cookie_and_jwt_are_rejected(self):
        profile, old = await self.account("Refresh")
        cookie = self.api.last_cookie
        status, result = await self.api.request("POST", "/api/v1/auth/refresh", cookie=cookie)
        self.assertEqual(status, 200, result)
        fresh = result["data"]
        self.assertEqual(fresh["session_generation"], old["session_generation"] + 1)
        self.assertEqual(fresh["user_id"], profile["id"])
        fresh_cookie = self.api.last_cookie
        status, _ = await self.api.request("POST", "/api/v1/auth/refresh", cookie=cookie)
        self.assertEqual(status, 401)
        status, result = await self.api.internal("validateAccess", {"access_token": old["access_token"], "device_id": old["device_id"]})
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["details"]["auth_layer"], "user_session")
        self.api.last_cookie = fresh_cookie
        self.assertEqual((await self.request("GET", "/api/v1/users/me", fresh))[0], 200)

    async def test_same_device_login_replaces_only_that_device(self):
        profile, first = await self.account("Device")
        other = await self.api.login(profile["email"])
        replacement = await self.api.login(profile["email"], device_id=first["device_id"])
        self.assertEqual(replacement["device_id"], first["device_id"])
        self.assertEqual((await self.request("GET", "/api/v1/users/me", first))[0], 401)
        self.assertEqual((await self.request("GET", "/api/v1/users/me", other))[0], 200)
        stranger = await self.api.signup()
        status, _ = await self.request("POST", "/api/v1/auth/login", json={"email": stranger["email"], "password": PASSWORD, "device_id": first["device_id"]})
        self.assertEqual(status, 401)

    async def test_logout_idempotent_after_cookie_clear_and_never_refreshes_revoked(self):
        _, access = await self.account("Logout")
        original_cookie = self.api.last_cookie
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/logout", cookie=original_cookie))[0], 204)
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/logout", cookie=original_cookie))[0], 204)
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/logout", cookie=False))[0], 204)
        self.assertEqual((await self.request("GET", "/api/v1/users/me", access))[0], 401)
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/refresh", cookie=original_cookie))[0], 401)

    async def test_cookie_auth_requires_exact_origin_and_rejects_json_body(self):
        await self.account("CSRF")
        for headers in ({"Origin": "https://evil.test"}, {"Origin": "null"}, {"Origin": ""}):
            self.assertEqual((await self.api.request("POST", "/api/v1/auth/refresh", headers=headers))[0], 403)
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/refresh", json={}))[0], 400)

    async def test_service_identity_precedes_malformed_body_and_session_fault_is_separate(self):
        status, result = await self.api.request("POST", "/internal/v1/validateAccess", headers={"Authorization": "Bearer invalid", "Content-Type": "application/json"}, raw=b"not-json", cookie=False)
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["details"], {"auth_layer": "service_identity"})
        status, result = await self.api.internal("validateAccess", {"access_token": "invalid", "device_id": "opaque"})
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["details"], {"auth_layer": "user_session"})

    async def test_wrong_claims_algorithm_device_and_binding_fail_closed(self):
        _, access = await self.account("JWT")
        claims = jwt.decode(access["access_token"], options={"verify_signature": False})
        cases = [{**claims, "iss": "wrong"}, {**claims, "aud": "wrong"}, {**claims, "sid": "not-issued"}, {**claims, "gen": claims["gen"] + 1}, {**claims, "sub": "not-issued"}]
        for altered in cases:
            token = jwt.encode(altered, self.api.signing_key, algorithm="HS256")
            self.assertEqual((await self.api.internal("validateAccess", {"access_token": token, "device_id": access["device_id"]}))[0], 401)
        token = jwt.encode(claims, self.api.signing_key, algorithm="HS384")
        self.assertEqual((await self.api.internal("validateAccess", {"access_token": token, "device_id": access["device_id"]}))[0], 401)
        self.assertEqual((await self.api.internal("validateAccess", {"access_token": access["access_token"], "device_id": "different-device"}))[0], 401)

    async def test_parallel_refresh_has_one_winner_and_gapless_invalidation(self):
        await self.account("Race")
        cookie = self.api.last_cookie
        responses = await asyncio.gather(*(self.api.request("POST", "/api/v1/auth/refresh", cookie=cookie) for _ in range(4)))
        self.assertEqual(sorted(status for status, _ in responses), [200, 401, 401, 401])
        status, result = await self.api.internal("readSessionInvalidations", {"after_position": 0, "limit": 500})
        self.assertEqual(status, 200)
        self.assertEqual([entry["position"] for entry in result["data"]["entries"]], [1])
        self.assertEqual(result["data"]["head_position"], 1)
        self.assertEqual(result["data"]["entries"][0]["reason"], "refresh")

    async def test_rate_limit_persists_restart_and_invalid_structure_does_not_consume(self):
        profile = await self.api.signup()
        for _ in range(3):
            self.assertEqual((await self.request("POST", "/api/v1/auth/login", json={"email": profile["email"], "password": PASSWORD}))[0], 400)
        for _ in range(10):
            self.assertEqual((await self.request("POST", "/api/v1/auth/login", json={"email": profile["email"], "password": "incorrect password", "device_id": None}))[0], 401)
        await self.api.restart()
        status, result = await self.request("POST", "/api/v1/auth/login", json={"email": profile["email"], "password": PASSWORD, "device_id": None})
        self.assertEqual(status, 429)
        self.assertTrue(result["error"]["retryable"])
        self.assertGreater(result["error"]["details"]["retry_after_ms"], 0)
        self.assertNotIn(profile["email"], str(result))

    async def test_unique_registration_and_duplicate_json_keys(self):
        email = secrets.token_hex(8) + "@product.test"
        replies = await asyncio.gather(*(self.api.request("POST", "/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Race"}) for _ in range(2)))
        self.assertEqual(sorted(status for status, _ in replies), [201, 409])
        status, _ = await self.api.request("POST", "/api/v1/auth/login", raw=b'{"email":"a","email":"b","password":"x","device_id":null}', headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    async def test_rolled_back_invalidation_leaves_no_counter_hole(self):
        from hine_api import db
        _, access = await self.account("Rollback")
        binding = await self.api.binding(access)
        async with self.api.pool.acquire() as conn:
            with self.assertRaisesRegex(RuntimeError, "owned rollback"):
                async with conn.transaction():
                    await db.frontier(conn, True)
                    await db.invalidate(conn, binding["session_id"], "refresh", 2)
                    raise RuntimeError("owned rollback")
        self.assertEqual((await self.api.request("POST", "/api/v1/auth/refresh"))[0], 200)
        page = await self.internal("readSessionInvalidations", {"after_position": 0, "limit": 500})
        self.assertEqual([entry["position"] for entry in page["entries"]], [1])

    async def test_invalid_configuration_never_exposes_values_or_references(self):
        from hine_api.config import Settings
        settings = Settings.from_env(self.api.settings_env)
        self.assertTrue(settings.valid)
        representation = repr(settings)
        from support import assert_secret_free
        assert_secret_free(self, (self.api.signing_key, self.api.service_token, self.api.settings_env["DATABASE_URL_SECRET_REF"]), representation)
        for altered in (
            {"PUBLIC_ORIGIN": "http://product.test"},
            {"PUBLIC_ORIGIN": "https://product.test/path"},
            {"REALTIME_INTERNAL_URL": "http://name:password@private.test"},
            {"SYNC_PAGE_LIMIT": "101"},
            {"SYNC_SCAN_LIMIT": "1001"},
            {"INVALIDATION_RETENTION_SECONDS": "899"},
            {"DATABASE_SCHEMA": "public; DROP SCHEMA public"},
            {"INTERNAL_ALLOWED_CALLERS": '{"realtime":"' + self.api.settings_env["INTERNAL_CALLER_TOKEN_SECRET_REF"] + '"}'},
        ):
            self.assertFalse(Settings.from_env({**self.api.settings_env, **altered}).valid)

    async def test_live_and_ready_health_have_no_private_data(self):
        for path in ("/health/live", "/health/ready"):
            status, result = await self.api.request("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(result["service"], "api")
            self.assertEqual(result["dependencies"]["redis"], "not_checked")
            self.assertNotIn("DATABASE_URL", str(result))
        self.assertEqual((await self.api.request("GET", "/health/live"))[1]["dependencies"]["postgresql"], "not_checked")

    async def test_account_quota_cannot_reset_at_calendar_minute_boundary(self):
        import hashlib
        from datetime import datetime, timedelta, timezone
        profile = await self.api.signup()
        async with self.api.pool.acquire() as conn:
            await conn.execute("INSERT INTO auth_rate_limits(scope,key,window_start,count) VALUES('login:account',$1,$2,10)", hashlib.sha256(profile["email"].encode()).hexdigest(), datetime.now(timezone.utc) - timedelta(seconds=40))
        status, result = await self.request("POST", "/api/v1/auth/login", json={"email": profile["email"], "password": PASSWORD, "device_id": None})
        self.assertEqual(status, 429, result)
        self.assertGreater(result["error"]["details"]["retry_after_ms"], 0)

    async def test_database_dependency_down_is_ready503_but_live200(self):
        from pathlib import Path
        # Only mutate this test's own private connection-reference file and API;
        # the shared PostgreSQL server and all operator credentials are untouched.
        Path(self.api.settings_env["DATABASE_URL_SECRET_REF"]).write_text("postgresql://unavailable@127.0.0.1:1/unavailable")
        await self.api.restart(require_ready=False)
        status, result = await self.api.request("GET", "/health/ready")
        self.assertEqual(status, 503)
        self.assertEqual(result["dependencies"], {"postgresql": "fail", "redis": "not_checked"})
        self.assertEqual((await self.api.request("GET", "/health/live"))[0], 200)
        self.assertNotIn("unavailable@", str(result))

    async def test_migration_metadata_checksum_tampering_is_rejected(self):
        from hine_api import db
        async with self.api.pool.acquire() as conn:
            await conn.execute("UPDATE schema_migrations SET checksum='tampered' WHERE name='001_accounts.sql'")
        with self.assertRaisesRegex(RuntimeError, "Migration integrity failure"):
            await db.migrate(self.api.pool)

    async def test_short_service_secret_and_short_signing_key_fail_closed(self):
        from pathlib import Path

        from hine_api.config import Settings
        for name in ("INTERNAL_CALLER_TOKEN_SECRET_REF", "JWT_SIGNING_KEY_SECRET_REF"):
            path = Path(self.api.temp.name) / ("short_" + name)
            path.write_text("x")
            self.assertFalse(Settings.from_env({**self.api.settings_env, name: str(path)}).valid)

    async def test_valid_mixed_case_database_schema_is_isolated(self):
        schema = self.api.schema.upper()
        async with self.api.pool.acquire() as conn:
            await conn.execute(f'CREATE SCHEMA "{schema}"')
        self.api.settings_env["DATABASE_SCHEMA"] = schema
        await self.api.restart()
        profile = await self.api.signup()
        async with self.api.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval(f'SELECT count(*) FROM "{schema}".users WHERE user_id=$1', profile["id"]), 1)
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM users"), 0)

    async def test_profile_display_name_preserves_valid_unicode_and_zero_code_point(self):
        display_name = "😀e\u0301\u0000tail"
        profile = await self.api.signup(display_name=display_name)
        self.assertEqual(profile["display_name"], display_name)
        access = await self.api.login(profile["email"])
        status, result = await self.request("GET", "/api/v1/users/me", access)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["display_name"], display_name)

    async def test_impossible_nul_device_binding_is_unauthenticated_not_database_failure(self):
        profile, _ = await self.account("Opaque")
        status, result = await self.request("POST", "/api/v1/auth/login", json={"email": profile["email"], "password": PASSWORD, "device_id": "opaque\u0000id"})
        self.assertEqual(status, 401, result)

    async def test_control_character_email_is_rejected_before_credential_work(self):
        status, result = await self.request("POST", "/api/v1/auth/register", json={"email": "nul\u0000@example.test", "password": PASSWORD, "display_name": "Email"})
        self.assertEqual(status, 400, result)

    async def test_invalid_config_keeps_health_static_and_auth_fail_closed(self):
        self.api.settings_env["PUBLIC_ORIGIN"] = "http://private-name:private-value@example.test"
        await self.api.restart(require_ready=False)
        status, result = await self.api.request("GET", "/health/ready")
        self.assertEqual(status, 503)
        self.assertEqual(result["reason"], "CONFIG_MISSING")
        self.assertNotIn("private-name", str(result))
        self.assertNotIn("PUBLIC_ORIGIN", str(result))
        self.assertEqual((await self.api.request("GET", "/health/live"))[0], 200)
        self.assertEqual((await self.request("POST", "/api/v1/auth/login", json={"email": "me@example.test", "password": PASSWORD, "device_id": None}))[0], 503)

    async def seed_login_ip_quota(self, address):
        import hashlib
        from datetime import datetime, timezone
        async with self.api.pool.acquire() as conn:
            await conn.execute("INSERT INTO auth_rate_limits(scope,key,window_start,count) VALUES('login:ip',$1,$2,60)", hashlib.sha256(address.encode()).hexdigest(), datetime.now(timezone.utc))

    async def login_attempt_with_headers(self, headers):
        return await self.request("POST", "/api/v1/auth/login", json={"email": secrets.token_hex(8) + "@product.test", "password": PASSWORD, "device_id": None}, headers=headers)

    async def test_trusted_proxy_client_addresses_have_independent_login_ip_quotas(self):
        self.api.settings_env["TRUSTED_PROXY_NETWORKS"] = "127.0.0.1/32"
        await self.api.restart()
        await self.seed_login_ip_quota("192.0.2.10")
        self.assertEqual((await self.login_attempt_with_headers({"X-Hine-Client-IP": "192.0.2.10"}))[0], 429)
        self.assertEqual((await self.login_attempt_with_headers({"X-Hine-Client-IP": "192.0.2.11"}))[0], 401)
        self.assertEqual((await self.login_attempt_with_headers({"X-Hine-Client-IP": "::ffff:192.0.2.10"}))[0], 429)
        await self.seed_login_ip_quota("2001:db8::10")
        self.assertEqual((await self.login_attempt_with_headers({"X-Hine-Client-IP": "2001:0db8:0000:0000:0000:0000:0000:0010"}))[0], 429)
        self.assertEqual((await self.login_attempt_with_headers({"X-Hine-Client-IP": "2001:db8::11"}))[0], 401)

    async def test_forwarding_headers_from_untrusted_peer_cannot_bypass_quota(self):
        self.api.settings_env["TRUSTED_PROXY_NETWORKS"] = "198.51.100.0/24"
        await self.api.restart()
        await self.seed_login_ip_quota("127.0.0.1")
        status, result = await self.login_attempt_with_headers({"X-Hine-Client-IP": "192.0.2.11", "X-Forwarded-For": "192.0.2.11"})
        self.assertEqual(status, 429, result)

    async def test_missing_malformed_duplicate_or_xff_only_headers_fall_back_to_peer(self):
        from multidict import CIMultiDict
        self.api.settings_env["TRUSTED_PROXY_NETWORKS"] = "127.0.0.1/32"
        await self.api.restart()
        await self.seed_login_ip_quota("127.0.0.1")
        for headers in (
            {},
            {"X-Forwarded-For": "192.0.2.11"},
            {"X-Hine-Client-IP": "192.0.2.11, 192.0.2.12"},
            {"X-Hine-Client-IP": "192.0.2.11:1234"},
            {"X-Hine-Client-IP": "not-an-address"},
            {"X-Hine-Client-IP": "fe80::1%eth0"},
            CIMultiDict([("X-Hine-Client-IP", "192.0.2.11"), ("X-Hine-Client-IP", "192.0.2.12")]),
        ):
            # Preserve duplicate headers for the actual HTTP consumer case.
            if isinstance(headers, CIMultiDict):
                headers["Origin"] = self.api.origin
                async with self.api.session.post(self.api.base_url + "/api/v1/auth/login", json={"email": secrets.token_hex(8) + "@product.test", "password": PASSWORD, "device_id": None}, headers=headers) as reply:
                    self.assertEqual(reply.status, 429)
            else:
                self.assertEqual((await self.login_attempt_with_headers(headers))[0], 429)

    async def test_proxy_network_config_is_explicit_and_invalid_cidrs_fail_closed(self):
        from hine_api.config import Settings
        environment = {key: value for key, value in self.api.settings_env.items() if key != "TRUSTED_PROXY_NETWORKS"}
        self.assertEqual(Settings.from_env(environment).trusted_proxy_networks, ())
        parsed = Settings.from_env({**environment, "TRUSTED_PROXY_NETWORKS": "127.0.0.1/32,::1/128"})
        self.assertTrue(parsed.valid)
        self.assertEqual(tuple(str(network) for network in parsed.trusted_proxy_networks), ("127.0.0.1/32", "::1/128"))
        for value in ("not-a-network", "127.0.0.1", "192.0.2.7/24", "127.0.0.1/32,", "fe80::1%eth0/128"):
            self.assertFalse(Settings.from_env({**environment, "TRUSTED_PROXY_NETWORKS": value}).valid)

    async def test_secret_privacy_assertion_failure_diagnostic_never_echoes_values(self):
        from support import assert_secret_free
        sentinel = "synthetic-secret-that-must-not-be-printed"
        representation = "SyntheticSettings(secret=" + sentinel + ")"
        with self.assertRaises(AssertionError) as failure:
            assert_secret_free(self, (sentinel,), representation)
        self.assertEqual(str(failure.exception), "Private diagnostic value exposed")
        self.assertFalse(sentinel in str(failure.exception), "Privacy assertion leaked its operand")
        self.assertFalse(representation in str(failure.exception), "Privacy assertion leaked its representation")

    async def test_cli_migration_failure_has_nonzero_exit_and_static_private_diagnostic(self):
        import sys
        from pathlib import Path

        from support import ROOT
        private = Path(self.api.temp.name) / "unavailable-cli-database"
        private.write_text("postgresql://synthetic-private-user:synthetic-private-password@127.0.0.1:1/synthetic-private-db")
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "hine_api", "migrate", cwd=ROOT, env={**self.api.settings_env, "DATABASE_URL_SECRET_REF": str(private)}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            output, diagnostic = await asyncio.wait_for(process.communicate(), 10)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        self.assertEqual(process.returncode, 1)
        self.assertTrue(output == b"", "CLI emitted unexpected output")
        self.assertTrue(diagnostic == b"API migration unavailable\n", "CLI emitted a non-static diagnostic")

    async def test_unknown_handler_fault_fails_closed_without_private_traceback(self):
        import json
        from types import SimpleNamespace

        from hine_api.config import Settings
        from hine_api.server import RUNTIME, errors
        sentinel = "synthetic-private-handler-fault"
        runtime = SimpleNamespace(settings=Settings.from_env(self.api.settings_env), pool=self.api.pool, schema_ready=True)
        request = SimpleNamespace(app={RUNTIME: runtime}, path="/api/v1/auth/login", method="POST", can_read_body=False)
        async def failing_handler(_request):
            raise RuntimeError(sentinel)
        with self.assertLogs("hine_api", level="ERROR") as logs:
            reply = await errors(request, failing_handler)
        self.assertEqual(reply.status, 503)
        self.assertEqual(json.loads(reply.text)["error"]["code"], "OUTCOME_UNCONFIRMED")
        self.assertTrue(sentinel not in reply.text, "Private handler exception leaked")
        self.assertTrue(all(sentinel not in message for message in logs.output), "Private handler exception logged")
        self.assertTrue(all(record.exc_info is None for record in logs.records), "Private traceback logged")

    async def test_cli_unexpected_fatal_exception_is_static_and_nonzero(self):
        import sys

        from support import ROOT
        code = "import sys; from hine_api.__main__ import fatal_error; sys.excepthook=fatal_error; raise RuntimeError('synthetic-private-fatal-fault')"
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, cwd=ROOT, env=self.api.settings_env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            output, diagnostic = await asyncio.wait_for(process.communicate(), 10)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        self.assertEqual(process.returncode, 1)
        self.assertTrue(output == b"", "Unexpected fatal CLI output")
        self.assertTrue(diagnostic == b"API fatal error\n", "Fatal CLI diagnostic is not static")
