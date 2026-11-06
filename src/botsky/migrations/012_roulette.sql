BEGIN IMMEDIATE;
CREATE TABLE roulette_rooms (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL CHECK(is_group=1), epoch INTEGER NOT NULL, host TEXT NOT NULL,
 bet INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'lobby', revision INTEGER NOT NULL DEFAULT 1,
 deadline_ms INTEGER NOT NULL, target_actor TEXT, target_id TEXT, phone_id TEXT, action TEXT,
 effect_state TEXT, play_receipt_id TEXT REFERENCES inbox(id), invite_link TEXT,
 result_json TEXT, return_due_ms INTEGER, return_state TEXT, return_receipt_id TEXT REFERENCES inbox(id), return_provider_id TEXT
);
CREATE UNIQUE INDEX roulette_active ON roulette_rooms(instance,account,chat,is_group,epoch) WHERE state IN ('lobby','playing','sending','uncertain');
CREATE TABLE roulette_players (
 room_id TEXT NOT NULL REFERENCES roulette_rooms(id), wallet_id INTEGER NOT NULL REFERENCES wallets(id),
 actor TEXT NOT NULL, bet INTEGER NOT NULL, join_receipt_id TEXT NOT NULL REFERENCES inbox(id),
 PRIMARY KEY(room_id,wallet_id), UNIQUE(room_id,actor)
);
CREATE TABLE roulette_views (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), room_id TEXT NOT NULL REFERENCES roulette_rooms(id),
 revision INTEGER NOT NULL, accepted_ms INTEGER
);
INSERT INTO schema_version(version) VALUES(12);
PRAGMA user_version=12;
COMMIT;
