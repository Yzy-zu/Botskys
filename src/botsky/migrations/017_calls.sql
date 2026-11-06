BEGIN IMMEDIATE;
CREATE TABLE call_bindings (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL, policy_revision TEXT NOT NULL,
 call_id TEXT, schedule_id TEXT, state TEXT NOT NULL DEFAULT 'reserved', updated_ms INTEGER NOT NULL
);
CREATE INDEX call_bindings_scope ON call_bindings(instance,account,chat,epoch,updated_ms);
CREATE TABLE call_cancellations (
 receipt_id TEXT PRIMARY KEY REFERENCES call_bindings(receipt_id),
 state TEXT NOT NULL DEFAULT 'pending', updated_ms INTEGER NOT NULL
);
CREATE TABLE call_notices (
 call_id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL REFERENCES call_bindings(receipt_id),
 delivery_receipt_id TEXT UNIQUE REFERENCES inbox(id), lease TEXT NOT NULL,
 state TEXT NOT NULL, outcome TEXT, updated_ms INTEGER NOT NULL
);
INSERT INTO schema_version(version) VALUES(17);
PRAGMA user_version=17;
COMMIT;
