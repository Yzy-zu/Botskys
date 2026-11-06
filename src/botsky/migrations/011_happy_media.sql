BEGIN IMMEDIATE;
CREATE TABLE happy_photo_jobs (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), event_id TEXT NOT NULL REFERENCES happy_events(id),
 kind TEXT NOT NULL, target TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued'
);
CREATE TABLE happy_photo_parts (
 receipt_id TEXT NOT NULL REFERENCES happy_photo_jobs(receipt_id), position INTEGER NOT NULL,
 photo_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', provider_message_id TEXT,
 PRIMARY KEY(receipt_id,position)
);
INSERT INTO schema_version(version) VALUES(11);
PRAGMA user_version=11;
COMMIT;
