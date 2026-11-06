BEGIN IMMEDIATE;
CREATE TABLE coop_seen (
 instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL,
 epoch INTEGER NOT NULL, photo_id TEXT NOT NULL,
 PRIMARY KEY(instance,account,chat,epoch,photo_id)
);
INSERT INTO schema_version(version) VALUES(13);
PRAGMA user_version=13;
COMMIT;
