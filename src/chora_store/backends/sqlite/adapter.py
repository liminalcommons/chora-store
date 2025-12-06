"""
SQLite backend adapter for chora-store.

This adapter implements the BackendAdapter protocol for SQLite,
providing local-first persistence with FTS5 search.

Requires SQLite 3.45+ for JSONB parity with PostgreSQL.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from ..protocol import BackendAdapter

# Minimum SQLite version for JSONB support
MIN_SQLITE_VERSION = (3, 45, 0)


def _check_sqlite_version():
    """Check that SQLite version is 3.45+ for JSONB support."""
    version_parts = tuple(int(x) for x in sqlite3.sqlite_version.split('.'))
    if version_parts < MIN_SQLITE_VERSION:
        import warnings
        warnings.warn(
            f"SQLite {sqlite3.sqlite_version} is below 3.45.0. "
            "JSONB features may not be available. Consider upgrading.",
            RuntimeWarning
        )


class SQLiteAdapter(BackendAdapter):
    """
    SQLite implementation of BackendAdapter.

    Features:
    - Local-first: single file database
    - JSONB: native JSON storage (SQLite 3.45+)
    - FTS5: full-text search with BM25 ranking
    - VIRTUAL generated columns: for tensegrity indexes
    - Triggers: physics enforcement at DB level
    """

    def __init__(self, db_path: str = "~/.chora/chora.db"):
        """
        Initialize SQLite adapter.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.chora/chora.db
        """
        _check_sqlite_version()
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # PROPERTIES
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def param(self) -> str:
        return "?"

    @property
    def name(self) -> str:
        return "sqlite"

    @property
    def supports_fts(self) -> bool:
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """
        Context manager for database connections.

        Creates a new connection, enables foreign keys, and handles
        commit/rollback on exit.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params: Tuple = (),
    ) -> sqlite3.Cursor:
        """Execute SQL and return cursor."""
        return conn.execute(sql, params)

    def executemany(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params_list: List[Tuple],
    ) -> sqlite3.Cursor:
        """Execute SQL with multiple parameter sets."""
        return conn.executemany(sql, params_list)

    def executescript(self, conn: sqlite3.Connection, sql: str) -> None:
        """Execute multiple SQL statements."""
        conn.executescript(sql)

    def fetchone(self, cursor: sqlite3.Cursor) -> Optional[dict]:
        """Fetch one row as dict."""
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self, cursor: sqlite3.Cursor) -> List[dict]:
        """Fetch all rows as list of dicts."""
        return [dict(row) for row in cursor.fetchall()]

    def rowcount(self, cursor: sqlite3.Cursor) -> int:
        """Get number of affected rows."""
        return cursor.rowcount

    # ═══════════════════════════════════════════════════════════════════════════
    # SQL GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def json_extract(self, column: str, path: str) -> str:
        """Generate JSON field extraction expression."""
        return f"json_extract({column}, '$.{path}')"

    def json_set(self, column: str, path: str, value_expr: str) -> str:
        """Generate JSON field update expression."""
        return f"json_set({column}, '$.{path}', {value_expr})"

    def datetime_now(self) -> str:
        """Generate current timestamp expression."""
        return "datetime('now')"

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMA GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_schema_sql(self) -> str:
        """Generate complete SQLite schema DDL."""
        # v4.0 Tensegrity Universe types and statuses
        valid_types = [
            'inquiry', 'learning', 'principle', 'story',
            'behavior', 'tool', 'focus', 'relationship'
        ]
        valid_statuses = [
            'emerging', 'clear', 'fulfilled', 'abandoned',  # story lifecycle
            'active', 'stressed', 'broken',  # relationship states
            'verified', 'drifting',  # behavior states
            'forming', 'crystallized',  # knowledge states
        ]

        types_check = ', '.join(f"'{t}'" for t in valid_types)
        statuses_check = ', '.join(f"'{s}'" for s in valid_statuses)

        # Main entities table with generated columns
        entities_table = f"""
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ({types_check})),
    status TEXT NOT NULL CHECK (status IN ({statuses_check})),
    title TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{{}}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Generated columns for graph traversal (Tensegrity Physics)
    rel_type TEXT GENERATED ALWAYS AS (json_extract(data, '$.relationship_type')) VIRTUAL,
    rel_from TEXT GENERATED ALWAYS AS (json_extract(data, '$.from_id')) VIRTUAL,
    rel_to TEXT GENERATED ALWAYS AS (json_extract(data, '$.to_id')) VIRTUAL,

    CHECK (id LIKE type || '-%')
);
"""

        # FTS5 virtual table
        fts_table = """
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id,
    type,
    status,
    title,
    description,
    content='entities',
    content_rowid='rowid'
);
"""

        # FTS sync triggers
        fts_triggers = """
CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
    INSERT INTO entities_fts(rowid, id, type, status, title, description)
    VALUES (
        new.rowid,
        new.id,
        new.type,
        new.status,
        new.title,
        json_extract(new.data, '$.description')
    );
END;

CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, id, type, status, title, description)
    VALUES ('delete', old.rowid, old.id, old.type, old.status, old.title,
            json_extract(old.data, '$.description'));
    INSERT INTO entities_fts(rowid, id, type, status, title, description)
    VALUES (
        new.rowid,
        new.id,
        new.type,
        new.status,
        new.title,
        json_extract(new.data, '$.description')
    );
END;

CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, id, type, status, title, description)
    VALUES ('delete', old.rowid, old.id, old.type, old.status, old.title,
            json_extract(old.data, '$.description'));
END;
"""

        # Indexes
        indexes = """
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_type_status ON entities(type, status);
CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);

-- Tensegrity Index (Critical Path for stability queries)
CREATE INDEX IF NOT EXISTS idx_tensegrity ON entities(rel_from, rel_type, status) WHERE type = 'relationship';

-- Constellation Index (Reverse Lookup for impact analysis)
CREATE INDEX IF NOT EXISTS idx_constellation ON entities(rel_to, rel_type) WHERE type = 'relationship';
"""

        # Golden Rule Trigger - Prevent story fulfilled without verified behaviors
        golden_rule_trigger = """
CREATE TRIGGER IF NOT EXISTS enforce_golden_rule
BEFORE UPDATE ON entities
WHEN NEW.type = 'story' AND NEW.status = 'fulfilled' AND OLD.status != 'fulfilled'
BEGIN
    SELECT RAISE(ABORT, 'Golden Rule: story cannot be fulfilled without verified behaviors')
    WHERE NOT EXISTS (
        SELECT 1 FROM entities
        WHERE type = 'relationship'
        AND json_extract(data, '$.relationship_type') = 'verifies'
        AND json_extract(data, '$.to_id') = NEW.id
        AND status = 'active'
    );
END;
"""

        # Physics triggers (Tensegrity Engine)
        # A verifies bond: from_id = verifier (behavior/tool), to_id = verified (story)
        # When the bond is stressed, the verified entity (to_id) is abandoned
        physics_triggers = """
CREATE TRIGGER IF NOT EXISTS trigger_bond_stress
AFTER UPDATE ON entities
WHEN NEW.type = 'relationship'
  AND json_extract(NEW.data, '$.relationship_type') = 'verifies'
  AND NEW.status = 'stressed'
  AND OLD.status != 'stressed'
BEGIN
    UPDATE entities
    SET status = 'abandoned',
        updated_at = datetime('now'),
        data = json_set(data, '$.abandonment_reason', 'Bond stress: ' || NEW.id)
    WHERE id = json_extract(NEW.data, '$.to_id')
      AND type = 'story'
      AND status = 'fulfilled';
END;

CREATE TRIGGER IF NOT EXISTS trigger_bond_heal
AFTER UPDATE ON entities
WHEN NEW.type = 'relationship'
  AND json_extract(NEW.data, '$.relationship_type') = 'verifies'
  AND NEW.status = 'active'
  AND OLD.status = 'stressed'
BEGIN
    UPDATE entities
    SET status = 'fulfilled',
        updated_at = datetime('now')
    WHERE id = json_extract(NEW.data, '$.to_id')
      AND type = 'story'
      AND status = 'abandoned'
      AND NOT EXISTS (
          SELECT 1 FROM entities
          WHERE type = 'relationship'
            AND rel_type = 'verifies'
            AND rel_to = json_extract(NEW.data, '$.to_id')
            AND status != 'active'
      );
END;
"""

        # Version tracking table
        version_table = """
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

        # Traces table (action history)
        traces_table = """
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    inputs TEXT,
    outputs TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_tool ON traces(tool);
CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at);
"""

        return "\n".join([
            entities_table,
            fts_table,
            fts_triggers,
            indexes,
            golden_rule_trigger,
            physics_triggers,
            version_table,
            traces_table,
        ])

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════════════

    def is_integrity_error(self, error: Exception) -> bool:
        """Check if exception is an integrity error."""
        return isinstance(error, sqlite3.IntegrityError)

    def is_unique_violation(self, error: Exception) -> bool:
        """Check if exception is a unique constraint violation."""
        return (
            isinstance(error, sqlite3.IntegrityError)
            and "UNIQUE constraint failed" in str(error)
        )

    def is_check_violation(self, error: Exception) -> bool:
        """Check if exception is a check constraint violation."""
        return (
            isinstance(error, sqlite3.IntegrityError)
            and "CHECK constraint failed" in str(error)
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH (FTS5)
    # ═══════════════════════════════════════════════════════════════════════════

    def fts_search_sql(self, query: str, limit: int) -> Tuple[str, Tuple]:
        """Generate FTS5 search query."""
        escaped = self.escape_fts_query(query)
        sql = """
            SELECT e.* FROM entities e
            JOIN entities_fts fts ON e.rowid = fts.rowid
            WHERE entities_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        return sql, (escaped, limit)

    def escape_fts_query(self, query: str) -> str:
        """
        Escape a query string for safe FTS5 searching.

        Hyphens are interpreted as column operators in FTS5,
        so we quote the entire query to treat it as a phrase.
        """
        return '"' + query.replace('"', '""') + '"'

    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    def close(self) -> None:
        """No-op for SQLite (connections are per-request)."""
        pass
