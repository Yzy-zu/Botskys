BEGIN IMMEDIATE;
ALTER TABLE outbox ADD COLUMN kind TEXT NOT NULL DEFAULT 'text' CHECK(kind IN ('text','table','media'));
ALTER TABLE outbox ADD COLUMN rich_payload_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE outbox ADD COLUMN visual_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE outbox ADD COLUMN content_sha256 TEXT;
CREATE INDEX outbox_provider_part ON outbox(provider_message_id) WHERE provider_message_id IS NOT NULL;
INSERT INTO schema_version(version) VALUES(19);
PRAGMA user_version=19;
COMMIT;
