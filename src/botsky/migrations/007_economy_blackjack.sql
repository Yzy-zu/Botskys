BEGIN IMMEDIATE;
CREATE TABLE wallets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL,
 actor TEXT NOT NULL, epoch INTEGER NOT NULL, balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0),
 reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0), last_daily_ms INTEGER, streak INTEGER NOT NULL DEFAULT 0,
 UNIQUE(instance,account,actor,epoch), CHECK(balance+reserved<=9007199254740991)
);
CREATE TABLE xp_entries (
 event_key TEXT NOT NULL, wallet_id INTEGER NOT NULL REFERENCES wallets(id),
 kind TEXT NOT NULL, amount INTEGER NOT NULL, balance_after INTEGER NOT NULL,
 receipt_id TEXT, created_ms INTEGER NOT NULL, PRIMARY KEY(event_key,wallet_id)
);
CREATE TABLE xp_holds (
 resource TEXT NOT NULL, wallet_id INTEGER NOT NULL REFERENCES wallets(id),
 amount INTEGER NOT NULL CHECK(amount>=0), PRIMARY KEY(resource,wallet_id)
);
CREATE TABLE blackjack_games (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL, host TEXT NOT NULL, mode TEXT NOT NULL,
 state TEXT NOT NULL, bet INTEGER NOT NULL, deck_json TEXT NOT NULL DEFAULT '[]',
 dealer_json TEXT NOT NULL DEFAULT '[]', turn INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 1, deadline_ms INTEGER NOT NULL, board_receipt_id TEXT REFERENCES inbox(id),
 result_json TEXT, created_ms INTEGER NOT NULL
);
CREATE UNIQUE INDEX bj_table_active ON blackjack_games(instance,account,chat,is_group,epoch) WHERE mode='table' AND state IN ('lobby','playing');
CREATE TABLE blackjack_players (
 game_id TEXT NOT NULL REFERENCES blackjack_games(id), wallet_id INTEGER NOT NULL REFERENCES wallets(id),
 actor TEXT NOT NULL, seat INTEGER NOT NULL, bet INTEGER NOT NULL,
 hand_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'waiting',
 PRIMARY KEY(game_id,wallet_id), UNIQUE(game_id,seat)
);
CREATE TABLE game_views (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), game_id TEXT NOT NULL REFERENCES blackjack_games(id),
 revision INTEGER NOT NULL, accepted_ms INTEGER
);
INSERT INTO schema_version(version) VALUES(7);
PRAGMA user_version=7;
COMMIT;
