CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name JSON NOT NULL,
    avatar_attachment_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES users(subject_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(device_id, subject_id)
);
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES users(subject_id),
    device_id TEXT NOT NULL,
    generation BIGINT NOT NULL CHECK(generation >= 1),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_hash TEXT NOT NULL UNIQUE,
    refresh_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(device_id, subject_id) REFERENCES devices(device_id, subject_id)
);
CREATE UNIQUE INDEX sessions_active_device ON sessions(subject_id,device_id) WHERE NOT revoked;
CREATE TABLE authority_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    position BIGINT NOT NULL CHECK(position >= 0)
);
INSERT INTO authority_state(id, position) VALUES (1, 0);
CREATE TABLE session_invalidations (
    position BIGINT PRIMARY KEY CHECK(position >= 1),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    reason TEXT NOT NULL CHECK(reason IN ('refresh','logout','replaced')),
    min_valid_generation BIGINT,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK((reason = 'refresh' AND min_valid_generation >= 1) OR (reason <> 'refresh' AND min_valid_generation IS NULL))
);
CREATE INDEX session_invalidations_time ON session_invalidations(committed_at);
CREATE TABLE auth_rate_limits (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    count INTEGER NOT NULL CHECK(count >= 1),
    PRIMARY KEY(scope,key,window_start)
);
