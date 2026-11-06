BEGIN IMMEDIATE;
CREATE TABLE external_operations (
 receipt_id TEXT PRIMARY KEY REFERENCES inbox(id), domain TEXT NOT NULL,
 resource TEXT NOT NULL, action TEXT NOT NULL, args_json TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'reserved', result_json TEXT
);
CREATE UNIQUE INDEX external_resource_active ON external_operations(domain,resource) WHERE state IN ('reserved','sending','uncertain');
INSERT INTO schema_version(version) VALUES(14);
PRAGMA user_version=14;
COMMIT;
