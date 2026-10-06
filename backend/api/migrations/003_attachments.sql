CREATE TABLE attachments (
    attachment_id TEXT PRIMARY KEY,
    uploader_id TEXT NOT NULL REFERENCES users(user_id),
    scope TEXT NOT NULL CHECK (scope IN ('avatar', 'conversation')),
    conversation_id TEXT REFERENCES conversations(conversation_id),
    kind TEXT NOT NULL CHECK (kind IN ('image', 'file')),
    filename JSON NOT NULL CHECK (json_typeof(filename) = 'string'),
    content_type TEXT NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'application/pdf')),
    size_bytes BIGINT NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
    sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL CHECK (state IN ('pending', 'ready', 'rejected', 'abandoned')),
    upload_attempt_id TEXT NOT NULL UNIQUE,
    bucket TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    generation TEXT CHECK (generation ~ '^[1-9][0-9]*$'),
    metageneration TEXT CHECK (metageneration ~ '^[1-9][0-9]*$'),
    upload_grant JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    completion_expires_at TIMESTAMPTZ NOT NULL,
    abandoned_at TIMESTAMPTZ,
    cleaned_at TIMESTAMPTZ,
    cleanup_checked_at TIMESTAMPTZ,
    CHECK ((scope = 'avatar' AND conversation_id IS NULL AND kind = 'image')
        OR (scope = 'conversation' AND conversation_id IS NOT NULL)),
    CHECK ((kind = 'file' AND content_type = 'application/pdf')
        OR (kind = 'image' AND content_type IN ('image/jpeg', 'image/png'))),
    CHECK (state <> 'ready' OR (generation IS NOT NULL AND metageneration IS NOT NULL)),
    CHECK (completion_expires_at >= expires_at)
);

CREATE INDEX attachments_abandoned_cleanup ON attachments ((COALESCE(cleanup_checked_at, completion_expires_at)), attachment_id)
    WHERE state IN ('pending', 'rejected', 'abandoned') AND cleaned_at IS NULL;
CREATE INDEX attachments_conversation ON attachments (conversation_id) WHERE conversation_id IS NOT NULL;

-- Ready bindings and their verified metadata are permanent, never switched to
-- an object with the same name but another generation. Closed attempts cannot
-- return to the completable state, even if an old signed PUT is replayed.
CREATE FUNCTION protect_attachment_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state = 'ready' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'immutable attachment binding';
        END IF;
        IF row_to_json(NEW)::TEXT IS DISTINCT FROM row_to_json(OLD)::TEXT THEN
            RAISE EXCEPTION 'immutable attachment binding';
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF (NEW.attachment_id, NEW.uploader_id, NEW.scope, NEW.conversation_id,
            NEW.kind, NEW.filename::TEXT, NEW.content_type, NEW.size_bytes, NEW.sha256,
            NEW.upload_attempt_id, NEW.bucket, NEW.object_key,
            NEW.created_at, NEW.completion_expires_at)
           IS DISTINCT FROM
           (OLD.attachment_id, OLD.uploader_id, OLD.scope, OLD.conversation_id,
            OLD.kind, OLD.filename::TEXT, OLD.content_type, OLD.size_bytes, OLD.sha256,
            OLD.upload_attempt_id, OLD.bucket, OLD.object_key,
            OLD.created_at, OLD.completion_expires_at) THEN
            RAISE EXCEPTION 'immutable attachment intent';
        END IF;
        IF OLD.state IN ('rejected', 'abandoned') AND NEW.state NOT IN ('rejected', 'abandoned') THEN
            RAISE EXCEPTION 'closed attachment attempt';
        END IF;
        IF OLD.upload_grant IS NOT NULL AND NEW.upload_grant IS DISTINCT FROM OLD.upload_grant THEN
            RAISE EXCEPTION 'immutable upload grant';
        END IF;
        IF OLD.state = 'abandoned' AND NEW.state <> 'abandoned' THEN
            RAISE EXCEPTION 'closed attachment attempt';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER attachments_immutable_binding BEFORE UPDATE OR DELETE ON attachments
    FOR EACH ROW EXECUTE FUNCTION protect_attachment_binding();
