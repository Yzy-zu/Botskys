BEGIN IMMEDIATE;
CREATE TABLE drive_uploads (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), remote_id TEXT NOT NULL,
 folder_id TEXT NOT NULL, scope_hash TEXT NOT NULL, sha256 TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'reserved', updated_ms INTEGER NOT NULL
);
CREATE TABLE message_drafts (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL CHECK(is_group=0), epoch INTEGER NOT NULL,
 names_json TEXT NOT NULL, recipients_json TEXT NOT NULL, directory_hash TEXT NOT NULL,
 content TEXT NOT NULL, artifact_id TEXT REFERENCES artifacts(id), artifact_sha256 TEXT,
 source_json TEXT NOT NULL, preview_receipt_id TEXT NOT NULL REFERENCES inbox(id),
 send_receipt_id TEXT REFERENCES inbox(id), state TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL
);
CREATE UNIQUE INDEX message_draft_active ON message_drafts(instance,account,actor,chat,is_group,epoch) WHERE state='draft';
CREATE TABLE message_parts (
 draft_id TEXT NOT NULL REFERENCES message_drafts(id), position INTEGER NOT NULL,
 target TEXT NOT NULL, contact_name TEXT NOT NULL, kind TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', provider_message_id TEXT, error_code TEXT,
 revision INTEGER NOT NULL DEFAULT 0, updated_ms INTEGER NOT NULL,
 PRIMARY KEY(draft_id,position)
);
CREATE TABLE message_attempts (
 draft_id TEXT NOT NULL, position INTEGER NOT NULL, revision INTEGER NOT NULL,
 state TEXT NOT NULL, provider_message_id TEXT, error_code TEXT, updated_ms INTEGER NOT NULL,
 PRIMARY KEY(draft_id,position,revision)
);
INSERT INTO schema_version(version) VALUES(6);
PRAGMA user_version=6;
COMMIT;
