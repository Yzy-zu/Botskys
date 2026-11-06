BEGIN IMMEDIATE;
CREATE TABLE nuclear_drafts (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL CHECK(is_group=1), epoch INTEGER NOT NULL,
 preview_receipt_id TEXT NOT NULL REFERENCES inbox(id), confirm_receipt_id TEXT REFERENCES inbox(id),
 state TEXT NOT NULL DEFAULT 'pending', cost INTEGER NOT NULL DEFAULT 5000,
 wallet_id INTEGER REFERENCES wallets(id), expires_ms INTEGER NOT NULL
);
CREATE TABLE nuclear_targets (
 draft_id TEXT NOT NULL REFERENCES nuclear_drafts(id), position INTEGER NOT NULL,
 target_id TEXT NOT NULL, target_actor TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 PRIMARY KEY(draft_id,position), UNIQUE(draft_id,target_id)
);
INSERT INTO schema_version(version) VALUES(16);
PRAGMA user_version=16;
COMMIT;
