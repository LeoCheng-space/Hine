"""A20–A22 PostgreSQL upload intents and immutable verified GCS bindings."""
import asyncio
import re
import secrets
from contextlib import suppress
from datetime import timedelta

import asyncpg

from . import db, domain
from .conversations import idempotency_key, mutation_existing, mutation_save
from .domain import required_keys, transaction, valid_string
from .server import RUNTIME
from .storage import MAX_BYTES, StorageFault
from .support import Fault, body, entity, iso, lookup_entity, response

UPLOAD_TTL = timedelta(minutes=10)
DOWNLOAD_TTL = timedelta(minutes=5)
# Reconciliation can finish a PUT whose response was lost after its URL expires.
# The closed-state transition precedes cleanup by construction, never vice versa.
COMPLETION_GRACE = timedelta(days=1)


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise Fault("INVALID_ARGUMENT")
    return value.lower()


def _upload_payload(value, maximum):
    required_keys(value, ("scope", "conversation_id", "filename", "content_type", "size_bytes", "sha256"))
    if value["scope"] not in ("avatar", "conversation"):
        raise Fault("INVALID_ARGUMENT")
    if value["conversation_id"] is not None:
        entity(value["conversation_id"])
    if (value["scope"] == "avatar") != (value["conversation_id"] is None):
        raise Fault("INVALID_ARGUMENT")
    valid_string(value["filename"], maximum=255)
    if not isinstance(value["content_type"], str):
        raise Fault("INVALID_ARGUMENT")
    if value["content_type"] not in ("image/jpeg", "image/png", "application/pdf"):
        raise Fault("UNSUPPORTED_MEDIA_TYPE")
    if value["scope"] == "avatar" and value["content_type"] == "application/pdf":
        raise Fault("INVALID_ARGUMENT")
    if type(value["size_bytes"]) is not int or value["size_bytes"] <= 0:
        raise Fault("INVALID_ARGUMENT")
    if value["size_bytes"] > min(maximum, MAX_BYTES):
        raise Fault("PAYLOAD_TOO_LARGE")
    _hash(value["sha256"])
    return "file" if value["content_type"] == "application/pdf" else "image"


async def _scope_access(conn, user_id, scope, conversation_id):
    if scope != "conversation":
        return None
    exists = await conn.fetchrow("SELECT conversation_id FROM conversations WHERE conversation_id=$1 FOR SHARE", lookup_entity(conversation_id))
    member = await domain.current_member(conn, user_id, conversation_id)
    if exists is None or member is None:
        raise Fault("FORBIDDEN")
    return (member["joined_order"], member["joined_message_id"], member["joined_version"])


async def _upload_authority(runtime, request, conn, value):
    await db.frontier(conn)
    binding = await runtime.auth.access(request, conn, lock=True)
    scope_context = await _scope_access(conn, binding["user_id"], value["scope"], value["conversation_id"])
    return binding, scope_context


def _same_authority(initial, current, initial_scope, current_scope):
    fields = ("subject_id", "user_id", "session_id", "device_id", "session_generation")
    if any(initial[field] != current[field] for field in fields):
        raise Fault("UNAUTHENTICATED", auth_layer="user_session")
    if initial_scope != current_scope:
        raise Fault("FORBIDDEN")


def _same_intent(initial, current):
    fields = ("attachment_id", "uploader_id", "scope", "conversation_id", "kind", "filename",
              "content_type", "size_bytes", "sha256", "upload_attempt_id", "bucket", "object_key",
              "created_at", "expires_at", "completion_expires_at")
    return all(initial[field] == current[field] for field in fields)


def _view(row):
    return {"id": row["attachment_id"], "scope": row["scope"], "conversation_id": row["conversation_id"],
            "uploader_id": row["uploader_id"], "kind": row["kind"], "filename": row["filename"],
            "content_type": row["content_type"], "size_bytes": row["size_bytes"], "sha256": row["sha256"],
            "state": row["state"], "created_at": iso(row["created_at"])}


def _fault(failure):
    return Fault(failure.code, retryable=failure.code in ("DEPENDENCY_UNAVAILABLE", "UPLOAD_NOT_READY"))


async def create_upload(request):
    runtime = request.app[RUNTIME]
    value = await body(request)
    kind = _upload_payload(value, runtime.settings.upload_max_bytes)
    key = idempotency_key(request, required=True)
    if request.query:
        raise Fault("INVALID_ARGUMENT")
    # Capture/reserve authority in a short transaction. Cloud signing must not
    # hold frontier/session/group/attachment locks while another user logs out.
    async with transaction(runtime) as conn:
        initial_binding, initial_scope = await _upload_authority(runtime, request, conn, value)
        user_id = initial_binding["user_id"]
        intent = await mutation_existing(conn, user_id, key, "A20", value)
        if intent is None:
            if not runtime.storage.configured:
                raise Fault("DEPENDENCY_UNAVAILABLE", retryable=True)
            created_at = (await conn.fetchval("SELECT clock_timestamp()")).replace(microsecond=0)
            expires_at = created_at + UPLOAD_TTL
            intent = {"attachment_id": secrets.token_urlsafe(24), "upload_attempt_id": secrets.token_urlsafe(24)}
            object_key = "attempts/" + secrets.token_hex(32)
            await conn.execute("""INSERT INTO attachments
                (attachment_id,uploader_id,scope,conversation_id,kind,filename,content_type,size_bytes,sha256,
                 state,upload_attempt_id,bucket,object_key,created_at,expires_at,completion_expires_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'pending',$10,$11,$12,$13,$14,$15)""",
                intent["attachment_id"], user_id, value["scope"], value["conversation_id"], kind,
                value["filename"], value["content_type"], value["size_bytes"], _hash(value["sha256"]),
                intent["upload_attempt_id"], runtime.settings.gcs_bucket, object_key, created_at,
                expires_at, expires_at + COMPLETION_GRACE)
            await mutation_save(conn, user_id, key, "A20", value, intent)
        row = await conn.fetchrow("SELECT * FROM attachments WHERE attachment_id=$1 FOR UPDATE", intent["attachment_id"])
        if row is None or row["uploader_id"] != user_id or row["upload_attempt_id"] != intent["upload_attempt_id"]:
            raise Fault("CONFLICT")
        grant = row["upload_grant"]
        if grant is not None:
            return response(grant, status=201)
        if row["state"] != "pending" or row["expires_at"] <= await conn.fetchval("SELECT clock_timestamp()"):
            raise Fault("UPLOAD_NOT_READY")
        snapshot = dict(row)
    try:
        signed = await runtime.storage.signed_upload(snapshot["bucket"], snapshot["object_key"],
                                                     snapshot["content_type"], snapshot["expires_at"])
    except StorageFault as failure:
        raise _fault(failure) from None
    candidate = {**intent, **signed, "expires_at": iso(snapshot["expires_at"])}
    async with transaction(runtime) as conn:
        current_binding, current_scope = await _upload_authority(runtime, request, conn, value)
        _same_authority(initial_binding, current_binding, initial_scope, current_scope)
        recovered = await mutation_existing(conn, current_binding["user_id"], key, "A20", value)
        if recovered != intent:
            raise Fault("IDEMPOTENCY_CONFLICT")
        row = await conn.fetchrow("SELECT * FROM attachments WHERE attachment_id=$1 FOR UPDATE", intent["attachment_id"])
        if row is None or not _same_intent(snapshot, row):
            raise Fault("CONFLICT")
        # Concurrent signers may create candidates with the same absolute
        # expiry, but only the first saved URL is ever returned to any caller.
        grant = row["upload_grant"]
        if grant is None:
            if row["state"] != "pending" or row["expires_at"] <= await conn.fetchval("SELECT clock_timestamp()"):
                raise Fault("UPLOAD_NOT_READY")
            grant = candidate
            await conn.execute("UPDATE attachments SET upload_grant=$2 WHERE attachment_id=$1", row["attachment_id"], grant)
    return response(grant, status=201)


async def _attachment_authority(runtime, request, conn, attachment_id, *, write):
    await db.frontier(conn)
    binding = await runtime.auth.access(request, conn, lock=True)
    initial = await conn.fetchrow("SELECT * FROM attachments WHERE attachment_id=$1", lookup_entity(attachment_id))
    if initial is None:
        raise Fault("NOT_FOUND")
    if write and initial["uploader_id"] != binding["user_id"]:
        raise Fault("FORBIDDEN")
    scope_context = None
    if initial["scope"] == "conversation":
        scope_context = await _scope_access(conn, binding["user_id"], initial["scope"], initial["conversation_id"])
    elif not write:
        # Pin current avatar/privacy edges only for this short DB transaction.
        if initial["uploader_id"] != binding["user_id"]:
            await conn.fetch("""SELECT c.conversation_id FROM conversations c
                WHERE EXISTS(SELECT 1 FROM memberships a JOIN memberships b USING(conversation_id)
                    WHERE a.conversation_id=c.conversation_id AND a.user_id=$1 AND b.user_id=$2
                    AND a.active AND b.active) ORDER BY c.conversation_id COLLATE "C" FOR SHARE""",
                binding["user_id"], initial["uploader_id"])
            await conn.fetchrow("SELECT * FROM contacts WHERE owner_id=$1 AND contact_id=$2 FOR SHARE",
                                binding["user_id"], initial["uploader_id"])
        await conn.fetchrow("SELECT avatar_attachment_id FROM users WHERE user_id=$1 FOR SHARE", initial["uploader_id"])
    row = await conn.fetchrow("SELECT * FROM attachments WHERE attachment_id=$1 FOR " + ("UPDATE" if write else "SHARE"), lookup_entity(attachment_id))
    if row is None:
        raise Fault("NOT_FOUND")
    if write:
        if row["uploader_id"] != binding["user_id"]:
            raise Fault("FORBIDDEN")
    elif not await domain.can_read_attachment(conn, binding["user_id"], attachment_id):
        raise Fault("FORBIDDEN")
    return binding, row, scope_context


async def complete_upload(request):
    attachment_id = entity(request.match_info["attachment_id"])
    value = await body(request)
    required_keys(value, ("upload_attempt_id", "sha256"))
    attempt = entity(value["upload_attempt_id"])
    sha256 = _hash(value["sha256"])
    if request.query:
        raise Fault("INVALID_ARGUMENT")
    runtime = request.app[RUNTIME]
    failure = None
    async with transaction(runtime) as conn:
        initial_binding, row, initial_scope = await _attachment_authority(runtime, request, conn, attachment_id, write=True)
        if row["upload_attempt_id"] != attempt or row["sha256"] != sha256:
            raise Fault("CONFLICT")
        if row["state"] == "ready":
            return response(_view(row))
        if row["state"] != "pending":
            raise Fault("CONFLICT")
        if row["completion_expires_at"] <= await conn.fetchval("SELECT clock_timestamp()"):
            await conn.execute("UPDATE attachments SET state='abandoned',abandoned_at=clock_timestamp() WHERE attachment_id=$1", attachment_id)
            failure = Fault("CONFLICT")
        elif row["upload_grant"] is None:
            raise Fault("UPLOAD_NOT_READY")
        snapshot = dict(row)
    if failure is not None:
        raise failure
    verified = None
    verification_failure = None
    try:
        # All byte/metadata requests, including the final pinned recheck, are
        # outside every PostgreSQL transaction and global authority lock.
        verified = await runtime.storage.verify_upload(snapshot["bucket"], snapshot["object_key"], snapshot)
    except StorageFault as error:
        verification_failure = error
    async with transaction(runtime) as conn:
        current_binding, row, current_scope = await _attachment_authority(runtime, request, conn, attachment_id, write=True)
        _same_authority(initial_binding, current_binding, initial_scope, current_scope)
        if not _same_intent(snapshot, row) or row["upload_attempt_id"] != attempt or row["sha256"] != sha256:
            raise Fault("CONFLICT")
        if row["state"] == "ready":
            # Another same-attempt verifier may have committed while I/O ran.
            # Never overwrite its immutable binding with this candidate.
            result = _view(row)
        elif row["state"] != "pending":
            raise Fault("CONFLICT")
        elif row["completion_expires_at"] <= await conn.fetchval("SELECT clock_timestamp()"):
            await conn.execute("UPDATE attachments SET state='abandoned',abandoned_at=clock_timestamp() WHERE attachment_id=$1", attachment_id)
            failure = Fault("CONFLICT")
        elif verification_failure is not None:
            if verification_failure.code == "CONFLICT":
                await conn.execute("UPDATE attachments SET state='rejected' WHERE attachment_id=$1", attachment_id)
            failure = _fault(verification_failure)
        else:
            ready = await conn.fetchrow("""UPDATE attachments SET state='ready',generation=$2,metageneration=$3
                WHERE attachment_id=$1 AND state='pending' AND upload_attempt_id=$4 RETURNING *""",
                attachment_id, verified.generation, verified.metageneration, attempt)
            if ready is None:
                raise Fault("CONFLICT")
            result = _view(ready)
    if failure is not None:
        raise failure
    return response(result)


async def download_attachment(request):
    attachment_id = entity(request.match_info["attachment_id"])
    if request.query or request.can_read_body:
        raise Fault("INVALID_ARGUMENT")
    runtime = request.app[RUNTIME]
    async with transaction(runtime, write=False) as conn:
        initial_binding, row, initial_scope = await _attachment_authority(runtime, request, conn, attachment_id, write=False)
        if row["state"] != "ready":
            raise Fault("UPLOAD_NOT_READY")
        expires_at = (await conn.fetchval("SELECT clock_timestamp()")).replace(microsecond=0) + DOWNLOAD_TTL
        snapshot = dict(row)
    try:
        signed = await runtime.storage.signed_download(snapshot["bucket"], snapshot["object_key"], snapshot, expires_at)
    except StorageFault as failure:
        raise _fault(failure) from None
    async with transaction(runtime, write=False) as conn:
        current_binding, row, current_scope = await _attachment_authority(runtime, request, conn, attachment_id, write=False)
        _same_authority(initial_binding, current_binding, initial_scope, current_scope)
        if row["state"] != "ready" or not _same_intent(snapshot, row) or (
            row["generation"], row["metageneration"]) != (snapshot["generation"], snapshot["metageneration"]):
            raise Fault("DEPENDENCY_UNAVAILABLE", retryable=True)
        if expires_at <= await conn.fetchval("SELECT clock_timestamp()"):
            raise Fault("DEPENDENCY_UNAVAILABLE", retryable=True)
        result = {**signed, "expires_at": iso(expires_at), "content_type": row["content_type"],
                  "filename": row["filename"], "size_bytes": row["size_bytes"]}
    return response(result)


async def cleanup_abandoned(runtime, limit=100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid cleanup batch size")
    if not runtime.storage.configured:
        return 0
    # Commit closed states before any provider delete. A21 shares these row
    # locks and the DB trigger forbids reopening an abandoned/rejected row.
    async with transaction(runtime) as conn:
        rows = await conn.fetch("""SELECT * FROM attachments
            WHERE state IN ('pending','rejected','abandoned') AND cleaned_at IS NULL
              AND completion_expires_at <= clock_timestamp() AND expires_at < clock_timestamp()
            ORDER BY COALESCE(cleanup_checked_at,completion_expires_at),attachment_id
            LIMIT $1 FOR UPDATE SKIP LOCKED""", limit)
        for row in rows:
            await conn.execute("""UPDATE attachments SET state='abandoned',
                abandoned_at=COALESCE(abandoned_at,clock_timestamp()),cleanup_checked_at=clock_timestamp()
                WHERE attachment_id=$1""", row["attachment_id"])
    deleted = 0
    for row in rows:
        try:
            generation = await runtime.storage.delete_abandoned(row["bucket"], row["object_key"])
        except StorageFault:
            continue  # State stays closed; the next bounded sweep can retry.
        if generation is not None:
            async with transaction(runtime) as conn:
                await conn.execute("""UPDATE attachments SET cleaned_at=clock_timestamp()
                    WHERE attachment_id=$1 AND state='abandoned' AND cleaned_at IS NULL""", row["attachment_id"])
            deleted += 1
    return deleted


async def _cleanup_context(app):
    async def sweep():
        while True:
            await asyncio.sleep(60)
            runtime = app[RUNTIME]
            try:
                await cleanup_abandoned(runtime)
            except (Fault, asyncpg.PostgresError, OSError, TimeoutError):
                # No identifiers, object keys, grants or provider secrets logged.
                continue
    task = asyncio.create_task(sweep(), name="attachment-abandoned-cleanup")
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def register(app):
    app.router.add_post("/api/v1/uploads", create_upload)
    app.router.add_post("/api/v1/uploads/{attachment_id}/complete", complete_upload)
    app.router.add_get("/api/v1/attachments/{attachment_id}/download", download_attachment)
    app.cleanup_ctx.append(_cleanup_context)
