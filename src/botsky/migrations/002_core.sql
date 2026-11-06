BEGIN IMMEDIATE;
CREATE TABLE inbox (
 id TEXT PRIMARY KEY,
 instance TEXT NOT NULL, account TEXT NOT NULL, message_id TEXT NOT NULL,
 actor TEXT NOT NULL, chat TEXT NOT NULL, is_group INTEGER NOT NULL CHECK(is_group IN (0,1)),
 epoch INTEGER NOT NULL, source_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL,
 fingerprint TEXT NOT NULL, command_json TEXT, path_json TEXT, permission TEXT,
 state TEXT NOT NULL CHECK(state IN ('queued','completed','cancelled','ignored','rejected')),
 revision INTEGER NOT NULL DEFAULT 0,
 result_json TEXT,
 UNIQUE(instance,account,message_id)
);
CREATE INDEX inbox_queue ON inbox(instance,account,epoch,state,received_ms);
CREATE TABLE effects (
 id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL UNIQUE REFERENCES inbox(id),
 operation TEXT NOT NULL, arguments_json TEXT NOT NULL, result_json TEXT NOT NULL,
 created_ms INTEGER NOT NULL
);
CREATE TABLE notes (
 id INTEGER PRIMARY KEY,
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 text TEXT NOT NULL, search_text TEXT NOT NULL, created_ms INTEGER NOT NULL,
 effect_id TEXT NOT NULL UNIQUE REFERENCES effects(id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX notes_scope ON notes(instance,account,actor,chat,is_group,epoch,id);
CREATE TABLE outbox (
 receipt_id TEXT NOT NULL REFERENCES inbox(id), position INTEGER NOT NULL,
 payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','sending','accepted','failed','uncertain','cancelled')),
 revision INTEGER NOT NULL DEFAULT 0,
 provider_message_id TEXT, error_code TEXT, updated_ms INTEGER NOT NULL,
 PRIMARY KEY(receipt_id,position)
);
CREATE TABLE note_views (
 id TEXT PRIMARY KEY,
 receipt_id TEXT NOT NULL UNIQUE REFERENCES inbox(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 query TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0,
 expires_ms INTEGER NOT NULL
);
CREATE INDEX note_view_scope ON note_views(instance,account,actor,chat,is_group,epoch,accepted,expires_ms);
INSERT INTO schema_version(version) VALUES(2);
PRAGMA application_id=1112755033;
PRAGMA user_version=2;
COMMIT;
