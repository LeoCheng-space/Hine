CREATE TABLE contacts (
    owner_id TEXT NOT NULL REFERENCES users(user_id),
    contact_id TEXT NOT NULL REFERENCES users(user_id),
    added_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(owner_id, contact_id)
);
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('direct','group')),
    title JSON,
    membership_version BIGINT,
    direct_pair TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK ((type='direct' AND title IS NULL AND membership_version IS NULL AND direct_pair IS NOT NULL)
        OR (type='group' AND title IS NOT NULL AND membership_version>=1 AND direct_pair IS NULL))
);
CREATE SEQUENCE message_order AS BIGINT MINVALUE 1 NO CYCLE;
CREATE TABLE memberships (
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    role TEXT NOT NULL CHECK (role IN ('admin','member')),
    joined_order BIGINT NOT NULL DEFAULT 0 CHECK (joined_order>=0),
    joined_message_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    joined_version BIGINT NOT NULL DEFAULT 0 CHECK (joined_version>=0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY(conversation_id,user_id)
);
CREATE INDEX memberships_user_active ON memberships(user_id,conversation_id) WHERE active;
CREATE TABLE messages (
    message_id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    sender_id TEXT NOT NULL REFERENCES users(user_id),
    subject_id TEXT NOT NULL REFERENCES users(subject_id),
    client_message_id UUID NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('text','image','file')),
    payload JSON NOT NULL,
    attachment_id TEXT,
    order_value BIGINT NOT NULL CHECK (order_value>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    invalidation_position BIGINT NOT NULL CHECK (invalidation_position>=0),
    membership_version BIGINT,
    recipient_ids TEXT[] NOT NULL,
    UNIQUE(subject_id,client_message_id)
);
CREATE INDEX messages_history ON messages(conversation_id,order_value DESC,message_id DESC);
CREATE INDEX messages_attachment ON messages(conversation_id,attachment_id) WHERE attachment_id IS NOT NULL;
CREATE TABLE receipts (
    message_id UUID NOT NULL REFERENCES messages(message_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    status TEXT NOT NULL CHECK (status IN ('delivered','read')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status_event_id UUID,
    PRIMARY KEY(message_id,user_id)
);
CREATE TABLE message_quota (
    subject_id TEXT PRIMARY KEY REFERENCES users(subject_id),
    tokens DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE feed_heads (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    position BIGINT NOT NULL DEFAULT 0 CHECK (position>=0)
);
INSERT INTO feed_heads(user_id) SELECT user_id FROM users;
CREATE TABLE user_feed (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    position BIGINT NOT NULL CHECK (position>0),
    envelope JSON NOT NULL,
    PRIMARY KEY(user_id,position)
);
CREATE TABLE rest_cursors (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    scope TEXT NOT NULL,
    state JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE sync_cursors (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    position BIGINT NOT NULL CHECK (position>=0),
    boundary BIGINT CHECK (boundary>=0),
    kind TEXT NOT NULL DEFAULT 'progress' CHECK (kind IN ('progress','boundary')),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    head_position BIGINT NOT NULL CHECK (head_position>=0),
    content JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE mutation_keys (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    key TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload JSON NOT NULL,
    result JSON NOT NULL,
    PRIMARY KEY(user_id,key)
);
CREATE INDEX rest_cursors_expiry ON rest_cursors(expires_at);
CREATE INDEX sync_cursors_expiry ON sync_cursors(expires_at);
CREATE INDEX snapshots_expiry ON snapshots(expires_at);
