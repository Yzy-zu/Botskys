BEGIN IMMEDIATE;
CREATE TABLE happy_events (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL CHECK(is_group=1), epoch INTEGER NOT NULL,
 owner TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'preparing', duration_seconds INTEGER NOT NULL,
 receipt_id TEXT NOT NULL REFERENCES inbox(id), published_ms INTEGER, expires_ms INTEGER,
 last_rain_ms INTEGER, activity INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX happy_active ON happy_events(instance,account,chat,is_group,epoch) WHERE state IN ('preparing','active');
CREATE TABLE happy_drops (
 id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE REFERENCES happy_events(id),
 state TEXT NOT NULL DEFAULT 'publishing', receipt_id TEXT NOT NULL REFERENCES inbox(id),
 published_ms INTEGER, wallet_id INTEGER REFERENCES wallets(id), claim_receipt_id TEXT REFERENCES inbox(id)
);
INSERT INTO schema_version(version) VALUES(8);
PRAGMA user_version=8;
COMMIT;
