BEGIN IMMEDIATE;
CREATE TABLE transport_inbox (
 id TEXT PRIMARY KEY,
 instance TEXT NOT NULL, account TEXT NOT NULL, epoch INTEGER NOT NULL,
 fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','admitted','rejected')),
 error_code TEXT, received_ms INTEGER NOT NULL
);
CREATE INDEX transport_pending ON transport_inbox(instance,account,epoch,state,received_ms);
INSERT INTO schema_version(version) VALUES(18);
PRAGMA user_version=18;
COMMIT;
