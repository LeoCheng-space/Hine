"""Private GCS objects: real credentials, create-only V4 grants, pinned bytes.

Only provider I/O runs in worker threads. Nothing here stores bytes locally or
turns a missing cloud dependency into a successful grant.
"""
import asyncio
import hashlib
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote

import google.auth
import requests
from google.api_core import exceptions as gcs_errors
from google.auth import credentials as auth_credentials
from google.auth import exceptions as auth_errors
from google.auth import iam
from google.auth.transport.requests import AuthorizedSession, Request
from google.cloud import storage
from google.cloud.storage.exceptions import DataCorruption
from google.oauth2 import service_account

MAX_BYTES = 10485760
HTTP_TIMEOUT = 8.0
OPERATION_TIMEOUT = 30.0
CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class StorageFault(Exception):
    """Public canonical code only; provider errors never escape into responses."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifiedObject:
    generation: str
    metageneration: str
    content_type: str
    size_bytes: int
    sha256: str


def sniff_content_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if re.match(rb"%PDF-(?:1\.[0-9]|2\.0)(?:\r|\n|\s)", data[:16]):
        return "application/pdf"
    return None


def _disposition(filename, content_type):
    # Preserve the UTF-8 name in RFC 5987; ASCII fallback cannot inject headers.
    fallback = "".join(c if 32 <= ord(c) < 127 and c not in '\\";' else "_" for c in filename)
    mode = "attachment" if content_type == "application/pdf" else "inline"
    return f'{mode}; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'


def _decimal(value):
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", text):
        raise StorageFault("CONFLICT")
    return text


class _BoundedRequest:
    """Bound ADC refresh/IAM transport, including retries performed by auth SDK."""
    def __init__(self):
        session = requests.Session()
        session.trust_env = False
        self.request = Request(session)
        self.deadline = 0.0

    def __call__(self, *args, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise auth_errors.TransportError("cloud operation deadline")
        timeout = kwargs.get("timeout")
        kwargs["timeout"] = min(HTTP_TIMEOUT, remaining, timeout if isinstance(timeout, (int, float)) else HTTP_TIMEOUT)
        return self.request(*args, **kwargs)

    def close(self):
        self.request.session.close()


class _IamCredentials(auth_credentials.Credentials, auth_credentials.Signing):
    """Signing facade backed by the official IAM Signer, not a generated key."""
    def __init__(self, credentials, request, email):
        super().__init__()
        self._source = credentials
        self._email = email
        self._signer = iam.Signer(request, credentials, email)

    @property
    def signer(self):
        return self._signer

    @property
    def signer_email(self):
        return self._email

    def sign_bytes(self, message):
        return self._signer.sign(message)

    def refresh(self, request):
        self._source.refresh(request)
        self.token, self.expiry = self._source.token, self._source.expiry


class GcsStorage:
    def __init__(self, settings):
        self.settings = settings
        self.bucket = getattr(settings, "gcs_bucket", None)
        self._client = None
        self._credentials = None
        self._signing = None
        self._transport = _BoundedRequest()
        self._thread_lock = threading.Lock()
        self._slots = asyncio.Semaphore(2)
        self._jobs = set()
        self._closed = False

    @property
    def configured(self):
        return bool(self.bucket)

    def _initialize(self):
        if not self.configured:
            raise StorageFault("DEPENDENCY_UNAVAILABLE")
        if self._client is not None:
            return
        key_ref = getattr(self.settings, "gcs_credentials_file", None)
        project = getattr(self.settings, "gcs_project", None)
        if key_ref:
            credentials = service_account.Credentials.from_service_account_file(key_ref, scopes=[CLOUD_SCOPE])
            project = project or credentials.project_id
        else:
            credentials, adc_project = google.auth.default(scopes=[CLOUD_SCOPE], request=self._transport)
            project = project or adc_project
        email = getattr(self.settings, "gcs_signing_service_account", None)
        if email:
            signing = _IamCredentials(credentials, self._transport, email)
        elif isinstance(credentials, service_account.Credentials):
            signing = credentials
        else:
            # GCE ADC may reveal its actual account only after a real refresh.
            email = getattr(credentials, "signer_email", None) or getattr(credentials, "service_account_email", None)
            if not email or email == "default":
                credentials.refresh(self._transport)
                email = getattr(credentials, "signer_email", None) or getattr(credentials, "service_account_email", None)
            if not email or email == "default":
                raise StorageFault("DEPENDENCY_UNAVAILABLE")
            signing = _IamCredentials(credentials, self._transport, email)
        session = AuthorizedSession(credentials, auth_request=self._transport,
                                    refresh_timeout=HTTP_TIMEOUT, max_refresh_attempts=1)
        session.trust_env = False
        self._client = storage.Client(project=project, credentials=credentials, _http=session,
                                      client_options={"api_endpoint": "https://storage.googleapis.com"})
        self._credentials, self._signing = credentials, signing

    def _invoke(self, function, args):
        deadline = time.monotonic() + OPERATION_TIMEOUT
        with self._thread_lock:
            if self._closed or time.monotonic() >= deadline:
                raise StorageFault("DEPENDENCY_UNAVAILABLE")
            self._transport.deadline = deadline
            try:
                self._initialize()
                return function(*args)
            except StorageFault:
                raise
            except (gcs_errors.GoogleAPICallError, auth_errors.GoogleAuthError,
                    requests.RequestException, DataCorruption, OSError, ValueError, TypeError, AttributeError):
                raise StorageFault("DEPENDENCY_UNAVAILABLE") from None

    async def _run(self, function, *args):
        if self._closed:
            raise StorageFault("DEPENDENCY_UNAVAILABLE")
        started = time.monotonic()
        try:
            await asyncio.wait_for(self._slots.acquire(), OPERATION_TIMEOUT)
        except TimeoutError:
            raise StorageFault("DEPENDENCY_UNAVAILABLE") from None
        job = asyncio.create_task(asyncio.to_thread(self._invoke, function, args))
        self._jobs.add(job)
        def finished(task):
            self._jobs.discard(task)
            self._slots.release()
            if not task.cancelled():
                task.exception()  # Retrieve faults even if the awaiting request timed out.
        job.add_done_callback(finished)
        try:
            return await asyncio.wait_for(asyncio.shield(job), max(0.001, OPERATION_TIMEOUT - (time.monotonic() - started)))
        except TimeoutError:
            raise StorageFault("DEPENDENCY_UNAVAILABLE") from None

    def _blob(self, bucket, key, generation=None):
        if bucket != self.bucket:
            raise StorageFault("DEPENDENCY_UNAVAILABLE")
        return self._client.bucket(bucket).blob(key, generation=int(generation) if generation else None)

    def _timeout(self):
        remaining = self._transport.deadline - time.monotonic()
        if remaining <= 0:
            raise StorageFault("DEPENDENCY_UNAVAILABLE")
        return min(HTTP_TIMEOUT, remaining)

    async def signed_upload(self, bucket, key, content_type, expires_at):
        return await self._run(self._signed_upload, bucket, key, content_type, expires_at)

    def _signed_upload(self, bucket, key, content_type, expires_at):
        headers = {"Content-Type": content_type, "x-goog-if-generation-match": "0", "Cache-Control": "no-transform"}
        url = self._blob(bucket, key).generate_signed_url(
            version="v4", method="PUT", expiration=expires_at, content_type=content_type,
            headers=dict(headers), credentials=self._signing,
            api_access_endpoint="https://storage.googleapis.com")
        return {"upload_url": url, "required_headers": headers}

    def _metadata(self, blob, declared):
        generation = _decimal(blob.generation)
        metageneration = _decimal(blob.metageneration)
        if blob.size != declared["size_bytes"] or not 0 < blob.size <= MAX_BYTES:
            raise StorageFault("CONFLICT")
        if blob.content_type != declared["content_type"] or blob.content_encoding:
            raise StorageFault("CONFLICT")
        if "no-transform" not in {part.strip().lower() for part in (blob.cache_control or "").split(",")}:
            raise StorageFault("CONFLICT")
        return generation, metageneration

    async def verify_upload(self, bucket, key, declared):
        return await self._run(self._verify_upload, bucket, key, declared)

    def _verify_upload(self, bucket, key, declared):
        latest = self._blob(bucket, key)
        try:
            latest.reload(timeout=self._timeout(), retry=None)
        except gcs_errors.NotFound:
            raise StorageFault("UPLOAD_NOT_READY") from None
        generation, metageneration = self._metadata(latest, declared)
        pinned = self._blob(bucket, key, generation)
        try:
            data = pinned.download_as_bytes(raw_download=True, start=0, end=declared["size_bytes"],
                if_generation_match=int(generation), if_metageneration_match=int(metageneration),
                timeout=self._timeout(), retry=None, checksum="auto")
            if len(data) != declared["size_bytes"] or sniff_content_type(data) != declared["content_type"]:
                raise StorageFault("CONFLICT")
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != declared["sha256"]:
                raise StorageFault("CONFLICT")
            # The final precondition check occurs after the complete pinned bytes.
            pinned.reload(if_generation_match=int(generation), if_metageneration_match=int(metageneration),
                          timeout=self._timeout(), retry=None)
            if self._metadata(pinned, declared) != (generation, metageneration):
                raise StorageFault("CONFLICT")
        except (gcs_errors.NotFound, gcs_errors.PreconditionFailed, DataCorruption):
            raise StorageFault("CONFLICT") from None
        return VerifiedObject(generation, metageneration, declared["content_type"], len(data), actual_sha)

    async def signed_download(self, bucket, key, saved, expires_at):
        return await self._run(self._signed_download, bucket, key, saved, expires_at)

    def _signed_download(self, bucket, key, saved, expires_at):
        blob = self._blob(bucket, key, saved["generation"])
        try:
            blob.reload(if_generation_match=int(saved["generation"]),
                        if_metageneration_match=int(saved["metageneration"]), timeout=self._timeout(), retry=None)
            if self._metadata(blob, saved) != (saved["generation"], saved["metageneration"]):
                raise StorageFault("DEPENDENCY_UNAVAILABLE")
            url = blob.generate_signed_url(version="v4", method="GET", expiration=expires_at,
                generation=saved["generation"], response_type=saved["content_type"],
                response_disposition=_disposition(saved["filename"], saved["content_type"]),
                credentials=self._signing, api_access_endpoint="https://storage.googleapis.com")
        except (gcs_errors.NotFound, gcs_errors.PreconditionFailed, StorageFault):
            raise StorageFault("DEPENDENCY_UNAVAILABLE") from None
        return {"download_url": url}

    async def delete_abandoned(self, bucket, key):
        """Resolve only an already-closed private attempt, then conditionally delete."""
        return await self._run(self._delete_abandoned, bucket, key)

    def _delete_abandoned(self, bucket, key):
        latest = self._blob(bucket, key)
        try:
            latest.reload(timeout=self._timeout(), retry=None)
        except gcs_errors.NotFound:
            return None
        generation = _decimal(latest.generation)
        pinned = self._blob(bucket, key, generation)
        try:
            pinned.delete(if_generation_match=int(generation), timeout=self._timeout(), retry=None)
        except gcs_errors.NotFound:
            pass  # That exact generation is already absent; never target a replacement.
        except gcs_errors.PreconditionFailed:
            raise StorageFault("DEPENDENCY_UNAVAILABLE") from None
        return generation

    async def close(self):
        self._closed = True
        if self._jobs:
            await asyncio.gather(*tuple(self._jobs), return_exceptions=True)
        def close_transport():
            with self._thread_lock:
                if self._client is not None:
                    self._client.close()
                self._transport.close()
        await asyncio.to_thread(close_transport)
