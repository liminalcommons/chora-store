"""
SQLite schema with CHECK constraints.

The database layer provides a second line of defense for Structural Governance.
Even if someone bypasses the EntityFactory, the database rejects invalid data.
"""

# Valid entity types (must match kernel standards/entity.yaml)
VALID_TYPES = ["feature", "pattern", "context", "capability", "learning", "task", "release"]

# Valid statuses by type (must match kernel standards/entity.yaml)
VALID_STATUSES = {
    "feature": ["planned", "in_progress", "complete", "blocked", "deprecated"],
    "pattern": ["proposed", "adopted", "deprecated"],
    "context": ["active", "paused", "completed", "abandoned"],
    "capability": ["active", "deprecated"],
    "learning": ["documented", "mitigated", "propagated"],
    "task": ["open", "in_progress", "complete", "blocked"],
    "release": ["draft", "published", "deprecated"],
}

# Flatten all valid statuses for CHECK constraint
ALL_VALID_STATUSES = list(set(
    status for statuses in VALID_STATUSES.values() for status in statuses
))

# SQL to create the entities table with CHECK constraints
CREATE_ENTITIES_TABLE = f"""
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ({', '.join(f"'{t}'" for t in VALID_TYPES)})),
    status TEXT NOT NULL CHECK (status IN ({', '.join(f"'{s}'" for s in ALL_VALID_STATUSES)})),
    data TEXT NOT NULL DEFAULT '{{}}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Semantic ID must start with type
    CHECK (id LIKE type || '-%')
);
"""

# FTS5 virtual table for full-text search
CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id,
    type,
    status,
    name,
    description,
    content='entities',
    content_rowid='rowid'
);
"""

# Triggers to keep FTS in sync
CREATE_FTS_TRIGGERS = """
-- Insert trigger
CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
    INSERT INTO entities_fts(rowid, id, type, status, name, description)
    VALUES (
        new.rowid,
        new.id,
        new.type,
        new.status,
        json_extract(new.data, '$.name'),
        json_extract(new.data, '$.description')
    );
END;

-- Update trigger
CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, id, type, status, name, description)
    VALUES ('delete', old.rowid, old.id, old.type, old.status,
            json_extract(old.data, '$.name'), json_extract(old.data, '$.description'));
    INSERT INTO entities_fts(rowid, id, type, status, name, description)
    VALUES (
        new.rowid,
        new.id,
        new.type,
        new.status,
        json_extract(new.data, '$.name'),
        json_extract(new.data, '$.description')
    );
END;

-- Delete trigger
CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, id, type, status, name, description)
    VALUES ('delete', old.rowid, old.id, old.type, old.status,
            json_extract(old.data, '$.name'), json_extract(old.data, '$.description'));
END;
"""

# Index for common queries
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_type_status ON entities(type, status);
CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);
"""

# Version tracking table for sync
# Note: No FK constraint on entity_id because version records must survive
# entity deletion (for sync/audit purposes). Delete records need to persist.
CREATE_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS entity_versions (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('create', 'update', 'delete')),
    changed_at TEXT NOT NULL,
    data_snapshot TEXT
);

CREATE INDEX IF NOT EXISTS idx_versions_entity ON entity_versions(entity_id);
CREATE INDEX IF NOT EXISTS idx_versions_changed ON entity_versions(changed_at);
"""

def get_all_schema_sql() -> str:
    """Get all SQL statements to create the schema."""
    return "\n".join([
        CREATE_ENTITIES_TABLE,
        CREATE_FTS_TABLE,
        CREATE_FTS_TRIGGERS,
        CREATE_INDEXES,
        CREATE_VERSION_TABLE,
    ])
