BEGIN IMMEDIATE;
CREATE TABLE cooperachas (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL CHECK(is_group=1), epoch INTEGER NOT NULL,
 creator TEXT NOT NULL, category TEXT NOT NULL, target INTEGER NOT NULL,
 total INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'preparing',
 preview_receipt_id TEXT NOT NULL REFERENCES inbox(id), complete_receipt_id TEXT REFERENCES inbox(id),
 published_ms INTEGER, expires_ms INTEGER, photo_json TEXT, refund INTEGER NOT NULL DEFAULT 0,
 provider_message_id TEXT
);
CREATE UNIQUE INDEX coop_active ON cooperachas(instance,account,chat,is_group,epoch) WHERE state IN ('preparing','publishing','open','ready','sending','uncertain');
CREATE TABLE coop_contributions (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), challenge_id TEXT NOT NULL REFERENCES cooperachas(id),
 wallet_id INTEGER NOT NULL REFERENCES wallets(id), amount INTEGER NOT NULL, created_ms INTEGER NOT NULL
);
INSERT INTO schema_version(version) VALUES(10);
PRAGMA user_version=10;
COMMIT;
