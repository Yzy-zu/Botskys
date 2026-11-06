BEGIN IMMEDIATE;
ALTER TABLE inbox ADD COLUMN origin TEXT NOT NULL DEFAULT 'transport';
ALTER TABLE inbox ADD COLUMN source_receipt_id TEXT REFERENCES inbox(id);
CREATE TABLE memories (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 kind TEXT NOT NULL, text TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 receipt_id TEXT NOT NULL REFERENCES inbox(id), created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL
);
CREATE TABLE reminders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 text TEXT NOT NULL, due_ms INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 receipt_id TEXT NOT NULL REFERENCES inbox(id), delivery_receipt_id TEXT REFERENCES inbox(id),
 revision INTEGER NOT NULL DEFAULT 1, created_ms INTEGER NOT NULL
);
CREATE TABLE school_tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 text TEXT NOT NULL, subject TEXT NOT NULL, due_date TEXT NOT NULL, due_time TEXT,
 artifact_id TEXT REFERENCES artifacts(id), state TEXT NOT NULL DEFAULT 'pending',
 revision INTEGER NOT NULL DEFAULT 1, receipt_id TEXT NOT NULL REFERENCES inbox(id), created_ms INTEGER NOT NULL
);
CREATE TABLE school_lessons (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 subject TEXT NOT NULL, weekday INTEGER NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL
);
CREATE TABLE school_digests (
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 enabled INTEGER NOT NULL, digest_time TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 receipt_id TEXT NOT NULL REFERENCES inbox(id),
 PRIMARY KEY(instance,account,chat,is_group,epoch)
);
CREATE TABLE polls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 question TEXT NOT NULL, options_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
 receipt_id TEXT NOT NULL REFERENCES inbox(id), published_ms INTEGER, revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE poll_votes (
 poll_id INTEGER NOT NULL REFERENCES polls(id), actor TEXT NOT NULL, choice INTEGER NOT NULL,
 source_ms INTEGER NOT NULL, sequence INTEGER NOT NULL, receipt_id TEXT NOT NULL REFERENCES inbox(id), PRIMARY KEY(poll_id,actor)
);
CREATE TABLE school_asset_grants (
 task_id INTEGER PRIMARY KEY REFERENCES school_tasks(id), artifact_id TEXT NOT NULL REFERENCES artifacts(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 expires_ms INTEGER NOT NULL
);
CREATE TABLE organization_events (
 event_key TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
 delivery_receipt_id TEXT REFERENCES inbox(id), state TEXT NOT NULL, created_ms INTEGER NOT NULL,
 expires_ms INTEGER NOT NULL
);
CREATE INDEX reminders_due ON reminders(instance,account,epoch,state,due_ms);
CREATE INDEX memories_scope ON memories(instance,account,actor,chat,is_group,epoch);
CREATE INDEX school_scope ON school_tasks(instance,account,chat,is_group,epoch,state);
INSERT INTO schema_version(version) VALUES(5);
PRAGMA user_version=5;
COMMIT;
