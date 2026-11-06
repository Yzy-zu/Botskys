BEGIN IMMEDIATE;
CREATE TABLE admin_warnings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL,
 chat TEXT NOT NULL, epoch INTEGER NOT NULL, target TEXT NOT NULL,
 receipt_id TEXT NOT NULL UNIQUE REFERENCES inbox(id), state TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE admin_bans (
 instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL, epoch INTEGER NOT NULL,
 target TEXT NOT NULL, receipt_id TEXT NOT NULL REFERENCES inbox(id), state TEXT NOT NULL, aliases_json TEXT NOT NULL,
 PRIMARY KEY(instance,account,chat,epoch,target)
);
INSERT INTO schema_version(version) VALUES(15);
PRAGMA user_version=15;
COMMIT;
