"""
SQLite schema with CHECK constraints.

The database layer provides a second line of defense for Structural Governance.
Even if someone bypasses the EntityFactory, the database rejects invalid data.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# STANDARD MODEL - 7 Entity Types (matches chora-kernel/standards/entity.yaml v3.0)
# ═══════════════════════════════════════════════════════════════════════════════
# The 7 Nouns (Statics) of the Development Universe:
#   - Inquiry   (Gas)       Potential energy, holds the question
#   - Feature   (Solid)     Structure, holds the plan
#   - Focus     (Plasma)    Ionized attention, holds the "what now?"
#   - Learning  (Radiation) Feedback, holds the history
#   - Pattern   (Crystal)   Law, holds the wisdom
#   - Release   (Clock)     Time, holds the sync point
#   - Tool      (Field)     Affordance, holds the capability
# ═══════════════════════════════════════════════════════════════════════════════

VALID_TYPES = ["inquiry", "feature", "focus", "learning", "pattern", "release", "tool"]

# Valid tiers (matches chora-kernel/standards/ontology.yaml enums.tier)
# Ordered by cost: data (~1) < workflow (~10) < inference (~100) < agent (~1000)
VALID_TIERS = ["data", "workflow", "inference", "agent"]

# Valid statuses by type (must match kernel standards/entity.yaml v3.0)
# Note: inquiry, feature, learning, pattern support 'subsumed' status for distillation
VALID_STATUSES = {
    "inquiry": ["active", "held", "resolved", "reified", "subsumed"],
    "feature": ["nascent", "converging", "stable", "drifting", "finalizing", "subsumed"],
    "focus": ["open", "unlocked", "finalized"],
    "learning": ["captured", "validated", "applied", "subsumed"],
    "pattern": ["proposed", "experimental", "adopted", "deprecated", "subsumed"],
    "release": ["planned", "released", "deprecated"],
    "tool": ["proposed", "active", "deprecated"],
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

# Traces table for tiered resolution - captures expensive operations for crystallization
# These are ephemeral (operational telemetry) and get synthesized into Learnings
CREATE_TRACES_TABLE = f"""
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ({', '.join(f"'{t}'" for t in VALID_TIERS)})),
    capability_id TEXT,
    inputs TEXT NOT NULL DEFAULT '[]',
    outputs TEXT NOT NULL DEFAULT '[]',
    reasoning TEXT NOT NULL DEFAULT '[]',
    cost_units REAL NOT NULL DEFAULT 0.0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_operation ON traces(operation_type);
CREATE INDEX IF NOT EXISTS idx_traces_tier ON traces(tier);
CREATE INDEX IF NOT EXISTS idx_traces_capability ON traces(capability_id);
CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at);
"""

# Valid route statuses for crystallized patterns
VALID_ROUTE_STATUSES = ["canary", "active", "deprecated"]

# Routes table for crystallized tier resolutions (Push-Right solidification)
# Routes are the solidification of traces into data lookups - hot operations
# that have cooled into deterministic mappings from input signatures to outputs.
CREATE_ROUTES_TABLE = f"""
CREATE TABLE IF NOT EXISTS routes (
    id TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL,
    input_signature TEXT NOT NULL,
    output_template TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.9,
    hit_count INTEGER NOT NULL DEFAULT 0,
    miss_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'canary' CHECK (status IN ({', '.join(f"'{s}'" for s in VALID_ROUTE_STATUSES)})),
    source_traces TEXT NOT NULL DEFAULT '[]',
    source_learning_ids TEXT NOT NULL DEFAULT '[]',
    taught_at_thresholds TEXT NOT NULL DEFAULT '[]',  -- Track hit thresholds where learnings were generated
    created_at TEXT NOT NULL,
    last_hit_at TEXT,

    -- Input signature must be unique per tool
    UNIQUE(tool_id, input_signature)
);

CREATE INDEX IF NOT EXISTS idx_routes_tool ON routes(tool_id);
CREATE INDEX IF NOT EXISTS idx_routes_status ON routes(status);
CREATE INDEX IF NOT EXISTS idx_routes_confidence ON routes(confidence);
CREATE INDEX IF NOT EXISTS idx_routes_hit_count ON routes(hit_count DESC);
"""

# Embeddings table for semantic similarity (distillation/clustering)
# Stores vector embeddings for entities to enable semantic search and clustering.
# Separate table allows model versioning and clean migration between embedding models.
CREATE_EMBEDDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS embeddings (
    entity_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_name);
"""

def get_all_schema_sql() -> str:
    """Get all SQL statements to create the schema."""
    return "\n".join([
        CREATE_ENTITIES_TABLE,
        CREATE_FTS_TABLE,
        CREATE_FTS_TRIGGERS,
        CREATE_INDEXES,
        CREATE_VERSION_TABLE,
        CREATE_TRACES_TABLE,
        CREATE_ROUTES_TABLE,
        CREATE_EMBEDDINGS_TABLE,
    ])
