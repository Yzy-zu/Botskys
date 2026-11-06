BEGIN IMMEDIATE;
ALTER TABLE inbox ADD COLUMN text TEXT NOT NULL DEFAULT '';
ALTER TABLE inbox ADD COLUMN mentions_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN provider_dispatched INTEGER NOT NULL DEFAULT 0;
CREATE TABLE ai_history (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id),
 instance TEXT NOT NULL, account TEXT NOT NULL, actor TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 user_text TEXT NOT NULL, assistant_text TEXT NOT NULL,
 accepted INTEGER NOT NULL DEFAULT 0, created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL
);
CREATE INDEX ai_history_scope ON ai_history(instance,account,actor,chat,is_group,epoch,accepted,expires_ms);
CREATE TABLE chat_modes (
 instance TEXT NOT NULL, account TEXT NOT NULL, chat TEXT NOT NULL,
 is_group INTEGER NOT NULL, epoch INTEGER NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('apagado','discreto','activo')),
 paused_until_ms INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(instance,account,chat,is_group,epoch)
);
INSERT INTO schema_version(version) VALUES(4);
PRAGMA user_version=4;
COMMIT;
