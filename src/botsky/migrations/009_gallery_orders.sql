BEGIN IMMEDIATE;
CREATE TABLE gallery_orders (
 id TEXT PRIMARY KEY, instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL,
 chat TEXT NOT NULL, is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 wallet_id INTEGER NOT NULL REFERENCES wallets(id), category TEXT, price INTEGER NOT NULL,
 happy_event_id TEXT REFERENCES happy_events(id), state TEXT NOT NULL DEFAULT 'offered',
 preview_receipt_id TEXT NOT NULL REFERENCES inbox(id), send_receipt_id TEXT REFERENCES inbox(id),
 expires_ms INTEGER NOT NULL, refund INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE gallery_parts (
 order_id TEXT NOT NULL REFERENCES gallery_orders(id), position INTEGER NOT NULL,
 photo_id TEXT NOT NULL, sha256 TEXT NOT NULL, cost INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', provider_message_id TEXT, error_code TEXT,
 PRIMARY KEY(order_id,position)
);
CREATE TABLE gallery_seen (
 wallet_id INTEGER NOT NULL REFERENCES wallets(id), photo_id TEXT NOT NULL,
 PRIMARY KEY(wallet_id,photo_id)
);
INSERT INTO schema_version(version) VALUES(9);
PRAGMA user_version=9;
COMMIT;
