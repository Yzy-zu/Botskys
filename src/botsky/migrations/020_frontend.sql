BEGIN IMMEDIATE;
ALTER TABLE inbox ADD COLUMN input_mode TEXT NOT NULL DEFAULT 'command';
CREATE TABLE frontend_tasks (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id),
 state TEXT NOT NULL CHECK(state IN ('pending','running','adopted','completed','failed','cancelled')),
 token TEXT, deadline_ms INTEGER, decision_json TEXT, error_code TEXT,
 created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL
);
CREATE INDEX frontend_pending ON frontend_tasks(state,created_ms);
INSERT INTO schema_version VALUES(20);
PRAGMA user_version=20;
COMMIT;
