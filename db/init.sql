CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id TEXT,
    actor      TEXT,
    role       TEXT,
    event      TEXT NOT NULL,
    allowed    BOOLEAN,
    detail     JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log (session_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
