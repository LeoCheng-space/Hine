"""Native PG/API consumer tests and explicitly isolated GCS SDK boundary tests.

Local RSA credentials exercise real V4 signing only. They confer no GCS rights;
none of these tests claims a successful physical cloud upload/download.
"""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import tempfile
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qsl, quote, urlsplit

import asyncpg
from aiohttp.test_utils import TestClient, TestServer
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from google.api_core import exceptions as gcs_errors
from google.cloud.storage import Blob
from google.oauth2.credentials import Credentials as OAuthCredentials
from hine_api.attachments import cleanup_abandoned
from hine_api.config import Settings
from hine_api.domain import can_read_attachment
from hine_api.server import RUNTIME, create_app
from hine_api.storage import GcsStorage, StorageFault, sniff_content_type
from support import ProductCase

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")
PNG_SHA = hashlib.sha256(PNG).hexdigest()


def signing_fixture(directory):
    """An explicit private unit-test key, never installed as production ADC."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = Path(directory) / "unit-signing-key.json"
    path.write_text(json.dumps({
        "type": "service_account", "project_id": "local-signature-test",
        "private_key_id": "unit-only", "private_key": key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode(),
        "client_email": "unit-only@local-signature-test.iam.gserviceaccount.com",
        "client_id": "123456789", "token_uri": "https://oauth2.googleapis.com/token",
    }))
    path.chmod(0o600)
    settings = SimpleNamespace(gcs_bucket="unit-signing-only", gcs_credentials_file=str(path),
                               gcs_project=None, gcs_signing_service_account=None,
                               upload_max_bytes=10485760)
    return key, settings


def verify_v4(public_key, url, method, headers):
    """Independent RSA verifier using the published V4 canonical request format."""
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    signature = bytes.fromhex(query.pop("X-Goog-Signature"))
    normalized = {name.lower(): " ".join(value.strip().split()) for name, value in headers.items()}
    normalized["host"] = parsed.netloc
    names = query["X-Goog-SignedHeaders"]
    canonical_headers = "".join(name + ":" + normalized[name] + "\n" for name in names.split(";"))
    canonical_query = "&".join(sorted(quote(k, safe="~") + "=" + quote(v, safe="~") for k, v in query.items()))
    canonical = f"{method}\n{parsed.path}\n{canonical_query}\n{canonical_headers}\n{names}\nUNSIGNED-PAYLOAD"
    scope = query["X-Goog-Credential"].split("/", 1)[1]
    to_sign = "\n".join(["GOOG4-RSA-SHA256", query["X-Goog-Date"], scope,
                          hashlib.sha256(canonical.encode("ascii")).hexdigest()])
    public_key.verify(signature, to_sign.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())


class GcsSdkBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hine-gcs-unit-")
        self.key, self.settings = signing_fixture(self.temp.name)
        self.storage = GcsStorage(self.settings)

    async def asyncTearDown(self):
        await self.storage.close()
        self.temp.cleanup()

    async def test_put_signs_create_only_content_type_and_no_transform(self):
        grant = await self.storage.signed_upload("unit-signing-only", "attempts/private-test",
                                                "image/png", datetime.now(timezone.utc) + timedelta(minutes=10))
        self.assertEqual(grant["required_headers"], {"Content-Type": "image/png",
                         "x-goog-if-generation-match": "0", "Cache-Control": "no-transform"})
        query = dict(parse_qsl(urlsplit(grant["upload_url"]).query))
        self.assertEqual(query["X-Goog-SignedHeaders"], "cache-control;content-type;host;x-goog-if-generation-match")
        self.assertLessEqual(int(query["X-Goog-Expires"]), 600)
        self.assertGreater(int(query["X-Goog-Expires"]), 580)
        verify_v4(self.key.public_key(), grant["upload_url"], "PUT", grant["required_headers"])
        for name, value in (("Content-Type", "text/html"), ("x-goog-if-generation-match", "1"),
                            ("Cache-Control", "public")):
            changed = {**grant["required_headers"], name: value}
            with self.subTest(name=name), self.assertRaises(InvalidSignature):
                verify_v4(self.key.public_key(), grant["upload_url"], "PUT", changed)

    async def test_download_signs_exact_generation_and_pdf_disposition(self):
        declared = {"generation": "9223372036854775808123", "metageneration": "7",
                    "content_type": "application/pdf", "size_bytes": 10,
                    "filename": '報告";x.pdf', "sha256": "a" * 64}
        def reload(blob, **kwargs):
            self.assertEqual(str(blob.generation), "9223372036854775808123")
            self.assertEqual(kwargs["if_generation_match"], 9223372036854775808123)
            self.assertEqual(kwargs["if_metageneration_match"], 7)
            blob._properties.update(generation=declared["generation"], metageneration="7", size="10",
                                    contentType="application/pdf", cacheControl="no-transform")
        with patch.object(Blob, "reload", reload):
            grant = await self.storage.signed_download("unit-signing-only", "attempts/private-test", declared,
                                                      datetime.now(timezone.utc) + timedelta(minutes=5))
        query = dict(parse_qsl(urlsplit(grant["download_url"]).query))
        self.assertEqual(query["generation"], "9223372036854775808123")
        self.assertEqual(query["response-content-type"], "application/pdf")
        self.assertTrue(query["response-content-disposition"].startswith("attachment; "))
        self.assertIn("filename*=UTF-8''", query["response-content-disposition"])
        self.assertNotIn("\r", query["response-content-disposition"])
        verify_v4(self.key.public_key(), grant["download_url"], "GET", {})
        tampered = grant["download_url"].replace("generation=9223372036854775808123", "generation=123")
        with self.assertRaises(InvalidSignature):
            verify_v4(self.key.public_key(), tampered, "GET", {})

    @staticmethod
    def metadata(blob, **kwargs):
        blob._properties.update(generation="1029", metageneration="4", size=str(len(PNG)),
                                contentType="image/png", cacheControl="no-transform")

    async def test_verification_reads_actual_bytes_with_pinned_preconditions(self):
        def download(blob, **kwargs):
            self.assertEqual(str(blob.generation), "1029")
            self.assertEqual(kwargs["if_generation_match"], 1029)
            self.assertEqual(kwargs["if_metageneration_match"], 4)
            self.assertTrue(kwargs["raw_download"])
            return PNG
        with patch.object(Blob, "reload", self.metadata), patch.object(Blob, "download_as_bytes", download):
            verified = await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                       {"size_bytes": len(PNG), "sha256": PNG_SHA, "content_type": "image/png"})
        self.assertEqual((verified.generation, verified.metageneration, verified.sha256), ("1029", "4", PNG_SHA))

    async def test_declared_hash_does_not_replace_hashing_actual_bytes(self):
        with patch.object(Blob, "reload", self.metadata), patch.object(Blob, "download_as_bytes", return_value=PNG), self.assertRaises(StorageFault) as raised:
            await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                 {"size_bytes": len(PNG), "sha256": "0" * 64, "content_type": "image/png"})
        self.assertEqual(raised.exception.code, "CONFLICT")

    async def test_metadata_change_after_bytes_never_verifies(self):
        calls = 0
        def reload(blob, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise gcs_errors.PreconditionFailed("isolated metadata change")
            self.metadata(blob)
        with patch.object(Blob, "reload", reload), patch.object(Blob, "download_as_bytes", return_value=PNG), self.assertRaises(StorageFault) as raised:
            await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                 {"size_bytes": len(PNG), "sha256": PNG_SHA, "content_type": "image/png"})
        self.assertEqual(raised.exception.code, "CONFLICT")

    async def test_compressed_or_wrong_actual_type_is_rejected(self):
        def compressed(blob, **kwargs):
            self.metadata(blob)
            blob._properties["contentEncoding"] = "gzip"
        with patch.object(Blob, "reload", compressed), self.assertRaises(StorageFault) as raised:
            await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                 {"size_bytes": len(PNG), "sha256": PNG_SHA, "content_type": "image/png"})
        self.assertEqual(raised.exception.code, "CONFLICT")
        self.assertIsNone(sniff_content_type(b"<html>not an image</html>"))
        self.assertEqual(sniff_content_type(PNG), "image/png")
        self.assertEqual(sniff_content_type(b"%PDF-1.7\n%%EOF"), "application/pdf")

    async def test_missing_pinned_generation_is_dependency_not_auth_or_latest(self):
        with patch.object(Blob, "reload", side_effect=gcs_errors.NotFound("isolated gone generation")), self.assertRaises(StorageFault) as raised:
            await self.storage.signed_download("unit-signing-only", "attempts/private-test",
                {"generation": "1029", "metageneration": "4", "content_type": "image/png",
                 "size_bytes": len(PNG), "filename": "tiny.png", "sha256": PNG_SHA},
                datetime.now(timezone.utc) + timedelta(minutes=5))
        self.assertEqual(raised.exception.code, "DEPENDENCY_UNAVAILABLE")

    async def test_provider_permission_failure_is_dependency_not_hine_401(self):
        with patch.object(Blob, "reload", side_effect=gcs_errors.Forbidden("isolated cloud permission")), self.assertRaises(StorageFault) as raised:
            await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                 {"size_bytes": len(PNG), "sha256": PNG_SHA, "content_type": "image/png"})
        self.assertEqual(raised.exception.code, "DEPENDENCY_UNAVAILABLE")

    async def test_cleanup_delete_is_generation_conditional_not_412_repair(self):
        def delete(blob, **kwargs):
            self.assertEqual(str(blob.generation), "1029")
            self.assertEqual(kwargs["if_generation_match"], 1029)
            raise gcs_errors.PreconditionFailed("isolated replacement race")
        with patch.object(Blob, "reload", self.metadata), patch.object(Blob, "delete", delete), self.assertRaises(StorageFault) as raised:
            await self.storage.delete_abandoned("unit-signing-only", "attempts/private-test")
        self.assertEqual(raised.exception.code, "DEPENDENCY_UNAVAILABLE")

    async def test_actual_type_length_and_no_transform_must_match(self):
        fixtures = [
            (PNG[:-1], None),
            (b"<html>" + b"x" * (len(PNG) - 6), None),
            (PNG, "public"),
        ]
        for data, cache_control in fixtures:
            def reload(blob, cache_control=cache_control, **kwargs):
                self.metadata(blob)
                if cache_control is not None:
                    blob._properties["cacheControl"] = cache_control
            with self.subTest(length=len(data), cache_control=cache_control):
                with patch.object(Blob, "reload", reload), patch.object(Blob, "download_as_bytes", return_value=data), self.assertRaises(StorageFault) as raised:
                    await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                        {"size_bytes": len(PNG), "sha256": hashlib.sha256(data).hexdigest(), "content_type": "image/png"})
                self.assertEqual(raised.exception.code, "CONFLICT")

    async def test_adc_uses_real_iam_signer_and_rsa_signature_not_fabricated_key(self):
        settings = SimpleNamespace(gcs_bucket="unit-signing-only", gcs_credentials_file=None,
            gcs_project="local-signature-test",
            gcs_signing_service_account="iam-unit@local-signature-test.iam.gserviceaccount.com")
        adapter = GcsStorage(settings)
        source = OAuthCredentials(token="unit-only-private-oauth-token",
                                  expiry=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1))
        def isolated_iam_transport(url, method, body, headers, timeout):
            self.assertEqual(method, "POST")
            self.assertEqual(url, "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/iam-unit@local-signature-test.iam.gserviceaccount.com:signBlob")
            self.assertEqual(headers["authorization"], "Bearer unit-only-private-oauth-token")
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 8)
            payload = base64.b64decode(json.loads(body)["payload"])
            signature = self.key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
            return SimpleNamespace(status=200, headers={"Content-Type": "application/json"},
                data=json.dumps({"signedBlob": base64.b64encode(signature).decode()}).encode())
        try:
            with patch("hine_api.storage.google.auth.default", return_value=(source, "local-signature-test")), patch.object(adapter._transport, "request", isolated_iam_transport):
                grant = await adapter.signed_upload("unit-signing-only", "attempts/iam-unit", "image/png",
                                                    datetime.now(timezone.utc) + timedelta(minutes=10))
            verify_v4(self.key.public_key(), grant["upload_url"], "PUT", grant["required_headers"])
            changed = {**grant["required_headers"], "x-goog-if-generation-match": "1"}
            with self.assertRaises(InvalidSignature):
                verify_v4(self.key.public_key(), grant["upload_url"], "PUT", changed)
        finally:
            await adapter.close()

    async def test_sdk_environment_override_cannot_route_metadata_to_emulator(self):
        def reload(blob, **kwargs):
            self.assertEqual(blob.bucket.client.api_endpoint, "https://storage.googleapis.com")
            self.metadata(blob)
        with patch.dict(os.environ, {"STORAGE_EMULATOR_HOST": "http://127.0.0.1:1",
                                    "API_ENDPOINT_OVERRIDE": "http://127.0.0.1:1"}), patch.object(Blob, "reload", reload), patch.object(Blob, "download_as_bytes", return_value=PNG):
            verified = await self.storage.verify_upload("unit-signing-only", "attempts/private-test",
                {"size_bytes": len(PNG), "sha256": PNG_SHA, "content_type": "image/png"})
        self.assertEqual(verified.sha256, PNG_SHA)

    async def test_absent_bucket_does_not_issue_fake_grant(self):
        unavailable = GcsStorage(SimpleNamespace(gcs_bucket=None))
        try:
            with self.assertRaises(StorageFault) as raised:
                await unavailable.signed_upload("", "private", "image/png", datetime.now(timezone.utc))
            self.assertEqual(raised.exception.code, "DEPENDENCY_UNAVAILABLE")
        finally:
            await unavailable.close()


class AttachmentIntentProductTests(ProductCase):
    """Actual subprocess HTTP and PG; local RSA signing, no cloud success claims."""
    async def asyncSetUp(self):
        await super().asyncSetUp()
        _, settings = signing_fixture(self.api.temp.name)
        self.api.settings_env.update(GCS_BUCKET=settings.gcs_bucket,
                                     GCS_CREDENTIALS_SECRET_REF=settings.gcs_credentials_file,
                                     UPLOAD_MAX_BYTES="10485760")
        await self.api.restart()
        self.owner, self.owner_access = await self.account("Owner")
        self.owner_cookie = self.api.last_cookie
        self.other, self.other_access = await self.account("Other")

    def payload(self, **changes):
        return {"scope": "avatar", "conversation_id": None, "filename": "tiny.png",
                "content_type": "image/png", "size_bytes": len(PNG), "sha256": PNG_SHA, **changes}

    async def create(self, key=None, payload=None, access=None):
        return await self.request("POST", "/api/v1/uploads", access or self.owner_access,
            json=payload or self.payload(), headers={"Idempotency-Key": key or secrets.token_urlsafe(20)})

    async def test_concurrent_same_key_returns_one_durable_grant(self):
        key = secrets.token_urlsafe(20)
        results = await asyncio.gather(*(self.create(key) for _ in range(4)))
        for status, result in results:
            self.assertEqual(status, 201, result)
            self.assertEqual(result, results[0][1])
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM attachments"), 1)

    async def test_invalid_scope_and_media_are_rejected_before_authentication(self):
        for change, status, code in [
            ({"conversation_id": "not-null"}, 400, "INVALID_ARGUMENT"),
            ({"conversation_id": "x" * 129, "scope": "conversation"}, 400, "INVALID_ARGUMENT"),
            ({"content_type": "image/svg+xml"}, 415, "UNSUPPORTED_MEDIA_TYPE"),
            ({"size_bytes": 10485761}, 413, "PAYLOAD_TOO_LARGE"),
            ({"sha256": "bad"}, 400, "INVALID_ARGUMENT"),
            ({"filename": ""}, 400, "INVALID_ARGUMENT"),
        ]:
            with self.subTest(change=change):
                actual, result = await self.request("POST", "/api/v1/uploads",
                    json=self.payload(**change), headers={"Idempotency-Key": secrets.token_urlsafe(20)})
                self.assertEqual((actual, result["error"]["code"]), (status, code))

    async def test_legal_nul_filename_is_lossless_through_intent_and_ready_view(self):
        filename = "圖\x00片.png"
        key = secrets.token_urlsafe(20)
        status, created = await self.create(key, self.payload(filename=filename))
        self.assertEqual(status, 201, created)
        aid = created["data"]["attachment_id"]
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT filename FROM attachments WHERE attachment_id=$1", aid), filename)
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        status, ready = await self.request("POST", f"/api/v1/uploads/{aid}/complete", self.owner_access,
            json={"upload_attempt_id": created["data"]["upload_attempt_id"], "sha256": PNG_SHA})
        self.assertEqual(status, 200, ready)
        self.assertEqual(ready["data"]["filename"], filename)
        status, same = await self.create(key, self.payload(filename=filename))
        self.assertEqual((status, same), (201, created))

    async def test_legal_but_nonexistent_nul_ids_keep_resource_authorization_result(self):
        status, result = await self.create(payload=self.payload(scope="conversation", conversation_id="x\x00y"))
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))
        status, result = await self.request("GET", "/api/v1/attachments/x%00y/download", self.owner_access)
        self.assertEqual((status, result["error"]["code"]), (404, "NOT_FOUND"))

    async def test_idempotent_intent_survives_restart_without_new_lifetime(self):
        key = secrets.token_urlsafe(20)
        status, first = await self.create(key)
        self.assertEqual(status, 201, first)
        await self.api.restart()
        status, again = await self.create(key)
        self.assertEqual(status, 201, again)
        self.assertEqual(first, again)
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM attachments"), 1)
        self.assertNotIn("object_key", first["data"])

    async def test_collision_and_validation_precedence_are_owner_scoped(self):
        key = secrets.token_urlsafe(20)
        status, first = await self.create(key)
        self.assertEqual(status, 201, first)
        status, result = await self.create(key, self.payload(filename="other.png"))
        self.assertEqual((status, result["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))
        status, result = await self.create(key, self.payload(filename="x" * 256))
        self.assertEqual((status, result["error"]["code"]), (400, "INVALID_ARGUMENT"))
        status, other = await self.create(key, access=self.other_access)
        self.assertEqual(status, 201, other)
        self.assertNotEqual(first["data"]["attachment_id"], other["data"]["attachment_id"])

    async def test_expired_key_returns_original_grant_not_renewal(self):
        key = secrets.token_urlsafe(20)
        status, first = await self.create(key)
        self.assertEqual(status, 201, first)
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET expires_at=now()-interval '1 hour' WHERE attachment_id=$1",
                               first["data"]["attachment_id"])
        status, again = await self.create(key)
        self.assertEqual((status, again), (201, first))
        status, fresh = await self.create()
        self.assertEqual(status, 201, fresh)
        self.assertNotEqual(fresh["data"]["attachment_id"], first["data"]["attachment_id"])

    async def test_owner_attempt_and_sha_checks_before_cloud_access(self):
        status, result = await self.create()
        self.assertEqual(status, 201, result)
        grant = result["data"]
        path = "/api/v1/uploads/" + grant["attachment_id"] + "/complete"
        valid = {"upload_attempt_id": grant["upload_attempt_id"], "sha256": PNG_SHA}
        status, result = await self.request("POST", path, self.other_access, json=valid)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))
        for changes in ({"upload_attempt_id": "wrong-attempt"}, {"sha256": "0" * 64}):
            status, result = await self.request("POST", path, self.owner_access, json={**valid, **changes})
            self.assertEqual((status, result["error"]["code"]), (409, "CONFLICT"))
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT state FROM attachments WHERE attachment_id=$1",
                                                grant["attachment_id"]), "pending")

    async def test_same_ready_attempt_returns_saved_view_and_cannot_rebind(self):
        status, result = await self.create()
        self.assertEqual(status, 201, result)
        grant = result["data"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1",
                               grant["attachment_id"])
        path = "/api/v1/uploads/" + grant["attachment_id"] + "/complete"
        valid = {"upload_attempt_id": grant["upload_attempt_id"], "sha256": PNG_SHA}
        status, first = await self.request("POST", path, self.owner_access, json=valid)
        self.assertEqual(status, 200, first)
        self.assertEqual(first["data"]["state"], "ready")
        self.assertIsNone(first["data"]["conversation_id"])
        self.assertNotIn("generation", first["data"])
        status, again = await self.request("POST", path, self.owner_access, json=valid)
        self.assertEqual((status, again), (200, first))
        async with self.runtime.pool.acquire() as conn:
            with self.assertRaises(asyncpg.PostgresError):
                await conn.execute("UPDATE attachments SET generation='1030' WHERE attachment_id=$1", grant["attachment_id"])

    async def test_unconfigured_storage_fails_closed_without_persisting_intent(self):
        self.api.settings_env.pop("GCS_BUCKET", None)
        await self.api.restart()
        status, result = await self.create()
        self.assertEqual((status, result["error"]["code"]), (503, "DEPENDENCY_UNAVAILABLE"))
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM attachments"), 0)

    async def test_expired_closed_attempt_cannot_complete(self):
        status, result = await self.create()
        self.assertEqual(status, 201, result)
        grant = result["data"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='abandoned',abandoned_at=now() WHERE attachment_id=$1",
                               grant["attachment_id"])
        status, result = await self.request("POST", "/api/v1/uploads/" + grant["attachment_id"] + "/complete",
            self.owner_access, json={"upload_attempt_id": grant["upload_attempt_id"], "sha256": PNG_SHA})
        self.assertEqual((status, result["error"]["code"]), (409, "CONFLICT"))

    async def test_avatar_download_requires_current_privacy_not_knowledge_of_id(self):
        status, result = await self.create()
        self.assertEqual(status, 201, result)
        aid = result["data"]["attachment_id"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        status, result = await self.request("GET", "/api/v1/attachments/" + aid + "/download", self.other_access)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))

    async def test_selected_avatar_privacy_is_revoked_when_profile_removes_it(self):
        status, created = await self.create()
        self.assertEqual(status, 201, created)
        aid = created["data"]["attachment_id"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        status, result = await self.request("PATCH", "/api/v1/users/me", self.owner_access,
            json={"avatar_attachment_id": aid})
        self.assertEqual(status, 200, result)
        status, result = await self.request("POST", "/api/v1/contacts", self.other_access, json={"user_id": self.owner["id"]})
        self.assertEqual(status, 201, result)
        async with self.runtime.pool.acquire() as conn:
            self.assertTrue(await can_read_attachment(conn, self.other["id"], aid))
        status, result = await self.request("PATCH", "/api/v1/users/me", self.owner_access, json={"avatar_attachment_id": None})
        self.assertEqual(status, 200, result)
        status, result = await self.request("GET", f"/api/v1/attachments/{aid}/download", self.other_access)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))

    async def test_storage_outage_does_not_rebind_saved_ready_snapshot_or_revoke_auth(self):
        status, created = await self.create()
        self.assertEqual(status, 201, created)
        aid = created["data"]["attachment_id"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        self.api.settings_env.pop("GCS_BUCKET", None)
        await self.api.restart()
        status, result = await self.request("GET", f"/api/v1/attachments/{aid}/download", self.owner_access)
        self.assertEqual((status, result["error"]["code"]), (503, "DEPENDENCY_UNAVAILABLE"))
        async with self.runtime.pool.acquire() as conn:
            saved = await conn.fetchrow("SELECT state,generation,metageneration FROM attachments WHERE attachment_id=$1", aid)
        self.assertEqual((saved["state"], saved["generation"], saved["metageneration"]), ("ready", "1029", "4"))
        status, result = await self.request("GET", "/api/v1/users/me", self.owner_access)
        self.assertEqual(status, 200, result)

    async def test_provider_signing_outage_preserves_reserved_intent(self):
        key = secrets.token_urlsafe(20)
        key_file = self.api.settings_env["GCS_CREDENTIALS_SECRET_REF"]
        self.api.settings_env["GCS_CREDENTIALS_SECRET_REF"] = str(Path(self.api.temp.name) / "missing-key")
        await self.api.restart()
        status, result = await self.create(key)
        self.assertEqual((status, result["error"]["code"]), (503, "DEPENDENCY_UNAVAILABLE"))
        async with self.runtime.pool.acquire() as conn:
            before = await conn.fetchrow("SELECT attachment_id,upload_attempt_id,expires_at,upload_grant FROM attachments")
        self.assertIsNone(before["upload_grant"])
        self.api.settings_env["GCS_CREDENTIALS_SECRET_REF"] = key_file
        await self.api.restart()
        status, result = await self.create(key)
        self.assertEqual(status, 201, result)
        self.assertEqual((result["data"]["attachment_id"], result["data"]["upload_attempt_id"]),
                         (before["attachment_id"], before["upload_attempt_id"]))
        expiry = datetime.fromisoformat(result["data"]["expires_at"].replace("Z", "+00:00"))
        self.assertEqual(expiry, before["expires_at"])

    async def group(self, access=None):
        status, result = await self.request("POST", "/api/v1/conversations/groups", access or self.owner_access,
            json={"title": "Attachment boundary", "member_ids": [self.owner["id"], self.other["id"]]},
            headers={"Idempotency-Key": secrets.token_urlsafe(20)})
        self.assertEqual(status, 201, result)
        return result["data"]["id"]

    async def test_removed_uploader_cannot_replay_grant_complete_or_download(self):
        cid = await self.group(self.other_access)
        key = secrets.token_urlsafe(20)
        payload = self.payload(scope="conversation", conversation_id=cid)
        status, first = await self.create(key, payload)
        self.assertEqual(status, 201, first)
        aid = first["data"]["attachment_id"]
        status, result = await self.request("DELETE", f"/api/v1/conversations/{cid}/members/{self.owner['id']}", self.other_access)
        self.assertEqual(status, 204)
        status, result = await self.create(key, payload)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))
        status, result = await self.request("POST", f"/api/v1/uploads/{aid}/complete", self.owner_access,
            json={"upload_attempt_id": first["data"]["upload_attempt_id"], "sha256": PNG_SHA})
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))
        status, result = await self.request("GET", f"/api/v1/attachments/{aid}/download", self.owner_access)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))

    async def test_download_cannot_cross_current_group_join_boundary(self):
        cid = await self.group()
        status, created = await self.create(payload=self.payload(scope="conversation", conversation_id=cid))
        self.assertEqual(status, 201, created)
        aid = created["data"]["attachment_id"]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
            self.assertFalse(await can_read_attachment(conn, self.other["id"], aid))
        binding = await self.api.binding(self.owner_access)
        await self.internal("persistIfAbsent", {key: binding[key] for key in
            ("subject_id", "device_id", "session_id", "session_generation")} | {
            "conversation_id": cid, "client_message_id": str(uuid.uuid4()), "request_event_id": str(uuid.uuid4()),
            "type": "image", "payload": {"attachment_id": aid}})
        async with self.runtime.pool.acquire() as conn:
            self.assertTrue(await can_read_attachment(conn, self.other["id"], aid))
        status, result = await self.request("DELETE", f"/api/v1/conversations/{cid}/members/{self.other['id']}", self.owner_access)
        self.assertEqual(status, 204)
        status, result = await self.request("POST", f"/api/v1/conversations/{cid}/members", self.owner_access,
            json={"user_id": self.other["id"]})
        self.assertEqual(status, 201, result)
        status, result = await self.request("GET", f"/api/v1/attachments/{aid}/download", self.other_access)
        self.assertEqual((status, result["error"]["code"]), (403, "FORBIDDEN"))

    async def test_revoked_session_cannot_replay_old_grant(self):
        key = secrets.token_urlsafe(20)
        status, result = await self.create(key)
        self.assertEqual(status, 201, result)
        status, _ = await self.api.request("POST", "/api/v1/auth/logout", session=self.owner_access, cookie=self.owner_cookie)
        self.assertEqual(status, 204)
        status, result = await self.create(key)
        self.assertEqual((status, result["error"]["code"]), (401, "UNAUTHENTICATED"))


class AttachmentCleanupPgIsolationTests(ProductCase):
    """Actual PG state/locking with only the external delete operation isolated."""
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.owner, self.access = await self.account("Cleanup owner")

    async def seed(self, state="pending", expired=True):
        aid, attempt = secrets.token_urlsafe(20), secrets.token_urlsafe(20)
        now = datetime.now(timezone.utc)
        grant_expiry = now - timedelta(days=2) if expired else now + timedelta(minutes=10)
        completion_expiry = grant_expiry + timedelta(days=1)
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("""INSERT INTO attachments(attachment_id,uploader_id,scope,conversation_id,
                kind,filename,content_type,size_bytes,sha256,state,upload_attempt_id,bucket,object_key,
                generation,metageneration,created_at,expires_at,completion_expires_at)
                VALUES($1,$2,'avatar',NULL,'image','"tiny.png"','image/png',$3,$4,$5,$6,'unit-isolation',$7,
                       $8,$9,$10,$11,$12)""",
                aid, self.owner["id"], len(PNG), PNG_SHA, state, attempt, "attempts/" + aid,
                "1029" if state == "ready" else None, "4" if state == "ready" else None,
                grant_expiry - timedelta(minutes=10), grant_expiry, completion_expiry)
        return aid, attempt

    async def test_cleanup_closes_expired_attempt_before_delete_and_keeps_ready_and_fresh(self):
        expired, attempt = await self.seed()
        ready, _ = await self.seed(state="ready")
        fresh, _ = await self.seed(expired=False)
        async def isolated_delete(bucket, key):
            aid = key.split("/", 1)[1]
            async with self.runtime.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT state,abandoned_at FROM attachments WHERE attachment_id=$1", aid)
                self.assertEqual(row["state"], "abandoned")
                self.assertIsNotNone(row["abandoned_at"])
                with self.assertRaises(asyncpg.PostgresError):
                    await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
            return "1029"
        runtime = SimpleNamespace(pool=self.runtime.pool,
            storage=SimpleNamespace(configured=True, delete_abandoned=isolated_delete))
        self.assertEqual(await cleanup_abandoned(runtime), 1)
        async with self.runtime.pool.acquire() as conn:
            states = {row["attachment_id"]: (row["state"], row["cleaned_at"]) for row in
                      await conn.fetch("SELECT attachment_id,state,cleaned_at FROM attachments")}
        self.assertEqual(states[expired][0], "abandoned")
        self.assertIsNotNone(states[expired][1])
        self.assertEqual(states[ready], ("ready", None))
        self.assertEqual(states[fresh], ("pending", None))
        status, result = await self.request("POST", f"/api/v1/uploads/{expired}/complete", self.access,
            json={"upload_attempt_id": attempt, "sha256": PNG_SHA})
        self.assertEqual((status, result["error"]["code"]), (409, "CONFLICT"))

    async def test_locked_completion_and_provider_outage_do_not_delete_or_reopen(self):
        aid, _ = await self.seed()
        async def provider_down(bucket, key):
            raise StorageFault("DEPENDENCY_UNAVAILABLE")
        runtime = SimpleNamespace(pool=self.runtime.pool,
            storage=SimpleNamespace(configured=True, delete_abandoned=provider_down))
        async with self.runtime.pool.acquire() as conn, conn.transaction():
            await conn.fetchrow("SELECT * FROM attachments WHERE attachment_id=$1 FOR UPDATE", aid)
            self.assertEqual(await cleanup_abandoned(runtime), 0)
            self.assertEqual(await conn.fetchval("SELECT state FROM attachments WHERE attachment_id=$1", aid), "pending")
        self.assertEqual(await cleanup_abandoned(runtime), 0)
        async with self.runtime.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state,cleaned_at FROM attachments WHERE attachment_id=$1", aid)
        self.assertEqual((row["state"], row["cleaned_at"]), ("abandoned", None))


class AttachmentAuthorityConcurrencyTests(ProductCase):
    """Real PG and HTTP authority; only external GCS SDK calls are controlled.

    This is revocation/lock isolation, not physical cloud acceptance. A second
    real native API process performs refresh/logout/group mutations against the
    same PostgreSQL authority while the in-process HTTP app awaits cloud I/O.
    """
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.owner, self.owner_access = await self.account("Slow cloud owner")
        self.owner_cookie = self.api.last_cookie
        self.other, self.other_access = await self.account("Unrelated authority")
        self.other_cookie = self.api.last_cookie
        _, signing = signing_fixture(self.api.temp.name)
        settings = replace(Settings.from_env(self.api.settings_env), gcs_bucket=signing.gcs_bucket,
                           gcs_credentials_file=signing.gcs_credentials_file, upload_max_bytes=10485760)
        app = create_app(settings)
        self.inproc = TestClient(TestServer(app))
        await self.inproc.start_server()
        self.local_runtime = app[RUNTIME]

    async def asyncTearDown(self):
        await self.inproc.close()
        await super().asyncTearDown()

    async def local_request(self, method, path, *, json=None, headers=None):
        outgoing = {"Origin": self.api.origin, "Authorization": "Bearer " + self.owner_access["access_token"],
                    **(headers or {})}
        async with self.inproc.request(method, path, json=json, headers=outgoing) as reply:
            return reply.status, await reply.json()

    async def prepare_operation(self, operation, conversation_id=None):
        payload = {"scope": "conversation" if conversation_id else "avatar", "conversation_id": conversation_id,
                   "filename": "tiny.png", "content_type": "image/png", "size_bytes": len(PNG), "sha256": PNG_SHA}
        key = secrets.token_urlsafe(20)
        if operation == "signed_upload":
            return "POST", "/api/v1/uploads", payload, {"Idempotency-Key": key}
        status, result = await self.local_request("POST", "/api/v1/uploads", json=payload,
                                                headers={"Idempotency-Key": key})
        self.assertEqual(status, 201, result)
        grant = result["data"]
        aid = grant["attachment_id"]
        if operation == "verify_upload":
            return "POST", f"/api/v1/uploads/{aid}/complete", {
                "upload_attempt_id": grant["upload_attempt_id"], "sha256": PNG_SHA}, {}
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        return "GET", f"/api/v1/attachments/{aid}/download", None, {}

    async def exercise_slow_cloud(self, operation, *, rejoin):
        conversation_id = None
        if rejoin:
            status, result = await self.request("POST", "/api/v1/conversations/groups", self.other_access,
                json={"title": "In-flight join boundary", "member_ids": [self.owner["id"], self.other["id"]]},
                headers={"Idempotency-Key": secrets.token_urlsafe(20)})
            self.assertEqual(status, 201, result)
            conversation_id = result["data"]["id"]
        method, path, payload, headers = await self.prepare_operation(operation, conversation_id)
        entered, release = asyncio.Event(), asyncio.Event()
        original = getattr(self.local_runtime.storage, operation)
        async def slow(*args):
            entered.set()
            await release.wait()
            return await original(*args)
        with (patch.object(Blob, "reload", GcsSdkBoundaryTests.metadata),
              patch.object(Blob, "download_as_bytes", return_value=PNG),
              patch.object(self.local_runtime.storage, operation, slow)):
            pending = asyncio.create_task(self.local_request(method, path, json=payload, headers=headers))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                # Both operations need the global exclusive frontier. They must
                # complete before release, not merely after cloud I/O finishes.
                status, refreshed = await asyncio.wait_for(self.api.request("POST", "/api/v1/auth/refresh",
                    cookie=self.other_cookie), 2)
                self.assertEqual(status, 200, refreshed)
                refreshed_cookie = self.api.last_cookie
                status, result = await asyncio.wait_for(self.api.request("POST", "/api/v1/auth/logout",
                    cookie=refreshed_cookie), 2)
                self.assertEqual(status, 204, result)
                if rejoin:
                    # Re-login unrelated admin after its logout; current target
                    # membership returns, but its join identity has changed.
                    admin = await self.api.login(self.other["email"])
                    status, result = await asyncio.wait_for(self.request("DELETE",
                        f"/api/v1/conversations/{conversation_id}/members/{self.owner['id']}", admin), 2)
                    self.assertEqual(status, 204, result)
                    status, result = await asyncio.wait_for(self.request("POST",
                        f"/api/v1/conversations/{conversation_id}/members", admin,
                        json={"user_id": self.owner["id"]}), 2)
                    self.assertEqual(status, 201, result)
                else:
                    status, result = await asyncio.wait_for(self.api.request("POST", "/api/v1/auth/logout",
                        cookie=self.owner_cookie), 2)
                    self.assertEqual(status, 204, result)
            finally:
                release.set()
                outcome = await asyncio.wait_for(pending, 10)
        status, result = outcome
        self.assertEqual((status, result["error"]["code"]),
                         (403, "FORBIDDEN") if rejoin else (401, "UNAUTHENTICATED"))
        async with self.runtime.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state,generation,upload_grant FROM attachments WHERE uploader_id=$1", self.owner["id"])
        self.assertEqual(row["state"], "ready" if operation == "signed_download" else "pending")
        if operation == "signed_upload":
            self.assertIsNone(row["upload_grant"])
        elif operation == "verify_upload":
            self.assertIsNone(row["generation"])
        else:
            self.assertEqual(row["generation"], "1029")

    async def test_a20_cloud_signing_does_not_block_authority_and_revoked_owner_gets_no_grant(self):
        await self.exercise_slow_cloud("signed_upload", rejoin=False)

    async def test_a21_cloud_verification_does_not_block_authority_and_revoked_owner_never_ready(self):
        await self.exercise_slow_cloud("verify_upload", rejoin=False)

    async def test_a22_cloud_signing_does_not_block_authority_and_revoked_owner_gets_no_grant(self):
        await self.exercise_slow_cloud("signed_download", rejoin=False)

    async def test_a20_inflight_old_join_gets_no_upload_grant_after_rejoin(self):
        await self.exercise_slow_cloud("signed_upload", rejoin=True)

    async def test_a21_inflight_old_join_never_ready_after_rejoin(self):
        await self.exercise_slow_cloud("verify_upload", rejoin=True)

    async def test_a22_inflight_old_join_gets_no_download_grant_after_rejoin(self):
        await self.exercise_slow_cloud("signed_download", rejoin=True)


if __name__ == "__main__":
    unittest.main()
