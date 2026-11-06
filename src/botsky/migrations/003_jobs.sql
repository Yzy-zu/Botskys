BEGIN IMMEDIATE;
ALTER TABLE inbox ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE inbox ADD COLUMN quoted_message_id TEXT;
ALTER TABLE inbox ADD COLUMN notice TEXT NOT NULL DEFAULT '';
ALTER TABLE outbox ADD COLUMN artifacts_json TEXT NOT NULL DEFAULT '[]';
CREATE TABLE artifacts (
 id TEXT PRIMARY KEY,
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 source_message_id TEXT NOT NULL, receipt_id TEXT REFERENCES inbox(id),
 origin TEXT NOT NULL CHECK(origin IN ('incoming','result')),
 format TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
 created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','deleting'))
);
CREATE INDEX artifact_source ON artifacts(instance,account,actor,chat,is_group,epoch,source_message_id);
CREATE TABLE artifact_leases (
 artifact_id TEXT NOT NULL REFERENCES artifacts(id), holder TEXT NOT NULL,
 token TEXT NOT NULL, expires_ms INTEGER NOT NULL,
 PRIMARY KEY(artifact_id,holder)
);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY REFERENCES inbox(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, epoch INTEGER NOT NULL,
 operation TEXT NOT NULL, arguments_json TEXT NOT NULL, inputs_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
 revision INTEGER NOT NULL DEFAULT 0, parent_revision INTEGER NOT NULL,
 lease_token TEXT, lease_until_ms INTEGER,
 resource_key TEXT NOT NULL,
 created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL,
 result_json TEXT
);
CREATE INDEX jobs_queue ON jobs(instance,account,epoch,state,created_ms);
CREATE TABLE interactions (
 id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES inbox(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 kind TEXT NOT NULL, command_json TEXT NOT NULL, path_json TEXT NOT NULL,
 data_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL CHECK(state IN ('pending_delivery','active','consumed','cancelled')),
 revision INTEGER NOT NULL DEFAULT 0,
 expires_ms INTEGER NOT NULL
);
CREATE INDEX interactions_scope ON interactions(instance,account,actor,chat,is_group,epoch,kind,state,expires_ms);
CREATE TABLE pdf_sessions (
 id TEXT PRIMARY KEY,
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 inputs_json TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('open','processing','finished','cancelled')),
 revision INTEGER NOT NULL DEFAULT 0,
 created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL
);
CREATE UNIQUE INDEX pdf_active_scope ON pdf_sessions(instance,account,actor,chat,is_group,epoch) WHERE state IN ('open','processing');
CREATE TABLE delivery_attempts (
 receipt_id TEXT NOT NULL, position INTEGER NOT NULL, revision INTEGER NOT NULL,
 state TEXT NOT NULL, provider_message_id TEXT, error_code TEXT, updated_ms INTEGER NOT NULL,
 PRIMARY KEY(receipt_id,position,revision)
);
INSERT INTO schema_version(version) VALUES(3);
PRAGMA user_version=3;
COMMIT;
