"""
PostgreSQL backend adapter for chora-store.

This adapter implements the BackendAdapter protocol for PostgreSQL,
providing cloud-ready persistence with tsvector search.

Requires: pip install psycopg[binary,pool]
"""

from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Tuple

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    _PSYCOPG_AVAILABLE = True
except ImportError:
    _PSYCOPG_AVAILABLE = False
    psycopg = None  # type: ignore
    ConnectionPool = None  # type: ignore

from ..protocol import BackendAdapter


class PostgresAdapter(BackendAdapter):
    """
    PostgreSQL implementation of BackendAdapter.

    Features:
    - Connection pooling: efficient connection reuse
    - JSONB: native JSON with indexing
    - tsvector: full-text search with GIN indexes
    - STORED generated columns: for tensegrity indexes
    - PL/pgSQL triggers: physics enforcement at DB level
    """

    def __init__(
        self,
        dsn: str = None,
        pool_min: int = 2,
        pool_max: int = 10,
        **kwargs,
    ):
        """
        Initialize PostgreSQL adapter.

        Args:
            dsn: Connection string (e.g., postgresql://user:pass@host/db)
            pool_min: Minimum pool size
            pool_max: Maximum pool size
            **kwargs: Additional args passed to ConnectionPool
        """
        if not _PSYCOPG_AVAILABLE:
            raise ImportError(
                "PostgreSQL backend requires psycopg. "
                "Install with: pip install psycopg[binary,pool]"
            )

        if not dsn:
            raise ValueError("PostgreSQL adapter requires 'dsn' connection string")

        self._dsn = dsn
        self._pool = ConnectionPool(
            dsn,
            min_size=pool_min,
            max_size=pool_max,
            kwargs={"row_factory": dict_row},
            **kwargs,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # PROPERTIES
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def param(self) -> str:
        return "%s"

    @property
    def name(self) -> str:
        return "postgres"

    @property
    def supports_fts(self) -> bool:
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """
        Context manager for database connections.

        Gets a connection from the pool, handles commit/rollback on exit.
        """
        with self._pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute(
        self,
        conn: Any,
        sql: str,
        params: Tuple = (),
    ) -> Any:
        """Execute SQL and return cursor."""
        return conn.execute(sql, params)

    def executemany(
        self,
        conn: Any,
        sql: str,
        params_list: List[Tuple],
    ) -> Any:
        """Execute SQL with multiple parameter sets."""
        return conn.executemany(sql, params_list)

    def executescript(self, conn: Any, sql: str) -> None:
        """
        Execute multiple SQL statements.

        PostgreSQL doesn't have executescript, so we split and execute.
        """
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for stmt in statements:
            conn.execute(stmt)

    def fetchone(self, cursor: Any) -> Optional[dict]:
        """Fetch one row as dict."""
        return cursor.fetchone()

    def fetchall(self, cursor: Any) -> List[dict]:
        """Fetch all rows as list of dicts."""
        return cursor.fetchall()

    def rowcount(self, cursor: Any) -> int:
        """Get number of affected rows."""
        return cursor.rowcount

    # ═══════════════════════════════════════════════════════════════════════════
    # SQL GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def json_extract(self, column: str, path: str) -> str:
        """
        Generate JSON field extraction expression.

        Uses ->> for text extraction from JSONB.
        """
        return f"{column}->>'{path}'"

    def json_set(self, column: str, path: str, value_expr: str) -> str:
        """
        Generate JSON field update expression.

        Uses jsonb_set for JSONB modification.
        """
        return f"jsonb_set({column}, '{{{path}}}', {value_expr})"

    def datetime_now(self) -> str:
        """Generate current timestamp expression."""
        return "NOW()"

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMA GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def get_schema_sql(self) -> str:
        """Generate complete PostgreSQL schema DDL."""
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

        # Main entities table with STORED generated columns and tsvector
        entities_table = f"""
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ({types_check})),
    status TEXT NOT NULL CHECK (status IN ({statuses_check})),
    title TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{{}}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,

    -- STORED generated columns for graph traversal (Tensegrity Physics)
    rel_type TEXT GENERATED ALWAYS AS (data->>'relationship_type') STORED,
    rel_from TEXT GENERATED ALWAYS AS (data->>'from_id') STORED,
    rel_to TEXT GENERATED ALWAYS AS (data->>'to_id') STORED,

    -- tsvector for full-text search
    search_vector TSVECTOR,

    CHECK (id LIKE type || '-%')
)
"""

        # Indexes (including GIN for FTS)
        indexes = """
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_entities_type_status ON entities(type, status);
CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);

-- Tensegrity Index (Critical Path for stability queries)
CREATE INDEX IF NOT EXISTS idx_tensegrity ON entities(rel_from, rel_type, status) WHERE type = 'relationship';

-- Constellation Index (Reverse Lookup for impact analysis)
CREATE INDEX IF NOT EXISTS idx_constellation ON entities(rel_to, rel_type) WHERE type = 'relationship';

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_entities_fts ON entities USING GIN (search_vector)
"""

        # tsvector update trigger function
        fts_trigger_function = """
CREATE OR REPLACE FUNCTION entities_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.id, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.data->>'description', '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.type, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(NEW.status, '')), 'D');
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""

        # tsvector update trigger
        fts_trigger = """
DROP TRIGGER IF EXISTS entities_search_update ON entities;
CREATE TRIGGER entities_search_update
    BEFORE INSERT OR UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION entities_search_vector_update()
"""

        # Golden Rule Function - Prevent story fulfilled without verified behaviors
        golden_rule_function = """
CREATE OR REPLACE FUNCTION enforce_golden_rule() RETURNS trigger AS $$
BEGIN
    IF NEW.type = 'story'
       AND NEW.status = 'fulfilled'
       AND (OLD.status IS NULL OR OLD.status != 'fulfilled') THEN
        IF NOT EXISTS (
            SELECT 1 FROM entities
            WHERE type = 'relationship'
            AND data->>'relationship_type' = 'verifies'
            AND data->>'to_id' = NEW.id
            AND status = 'active'
        ) THEN
            RAISE EXCEPTION 'Golden Rule: story cannot be fulfilled without verified behaviors';
        END IF;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""

        golden_rule_trigger = """
DROP TRIGGER IF EXISTS enforce_golden_rule ON entities;
CREATE TRIGGER enforce_golden_rule
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION enforce_golden_rule()
"""

        # Physics trigger: Bond Stress -> Parent Abandonment
        # A verifies bond: from_id = verifier (behavior/tool), to_id = verified (story)
        bond_stress_function = """
CREATE OR REPLACE FUNCTION trigger_bond_stress() RETURNS trigger AS $$
BEGIN
    IF NEW.type = 'relationship'
       AND (NEW.data->>'relationship_type') = 'verifies'
       AND NEW.status = 'stressed'
       AND OLD.status != 'stressed' THEN
        UPDATE entities
        SET status = 'abandoned',
            updated_at = NOW(),
            data = data || jsonb_build_object('abandonment_reason', 'Bond stress: ' || NEW.id)
        WHERE id = (NEW.data->>'to_id')
          AND type = 'story'
          AND status = 'fulfilled';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""

        bond_stress_trigger = """
DROP TRIGGER IF EXISTS entities_bond_stress ON entities;
CREATE TRIGGER entities_bond_stress
    AFTER UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION trigger_bond_stress()
"""

        # Physics trigger: Bond Heal -> Restabilization
        bond_heal_function = """
CREATE OR REPLACE FUNCTION trigger_bond_heal() RETURNS trigger AS $$
BEGIN
    IF NEW.type = 'relationship'
       AND (NEW.data->>'relationship_type') = 'verifies'
       AND NEW.status = 'active'
       AND OLD.status = 'stressed' THEN
        -- Only restore fulfillment if ALL verifies bonds are now active
        UPDATE entities
        SET status = 'fulfilled',
            updated_at = NOW()
        WHERE id = (NEW.data->>'to_id')
          AND type = 'story'
          AND status = 'abandoned'
          AND NOT EXISTS (
              SELECT 1 FROM entities
              WHERE type = 'relationship'
                AND rel_type = 'verifies'
                AND rel_to = (NEW.data->>'to_id')
                AND status != 'active'
          );
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""

        bond_heal_trigger = """
DROP TRIGGER IF EXISTS entities_bond_heal ON entities;
CREATE TRIGGER entities_bond_heal
    AFTER UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION trigger_bond_heal()
"""

        # Version tracking table
        version_table = """
CREATE TABLE IF NOT EXISTS entity_versions (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('create', 'update', 'delete')),
    changed_at TIMESTAMPTZ NOT NULL,
    data_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS idx_versions_entity ON entity_versions(entity_id);
CREATE INDEX IF NOT EXISTS idx_versions_changed ON entity_versions(changed_at)
"""

        # Traces table (action history)
        traces_table = """
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    inputs JSONB,
    outputs JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_tool ON traces(tool);
CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at)
"""

        return ";\n".join([
            entities_table,
            indexes,
            fts_trigger_function,
            fts_trigger,
            golden_rule_function,
            golden_rule_trigger,
            bond_stress_function,
            bond_stress_trigger,
            bond_heal_function,
            bond_heal_trigger,
            version_table,
            traces_table,
        ])

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════════════

    def is_integrity_error(self, error: Exception) -> bool:
        """Check if exception is an integrity error."""
        if not _PSYCOPG_AVAILABLE:
            return False
        return isinstance(error, psycopg.errors.IntegrityError)

    def is_unique_violation(self, error: Exception) -> bool:
        """Check if exception is a unique constraint violation."""
        if not _PSYCOPG_AVAILABLE:
            return False
        return isinstance(error, psycopg.errors.UniqueViolation)

    def is_check_violation(self, error: Exception) -> bool:
        """Check if exception is a check constraint violation."""
        if not _PSYCOPG_AVAILABLE:
            return False
        return isinstance(error, psycopg.errors.CheckViolation)

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH (tsvector)
    # ═══════════════════════════════════════════════════════════════════════════

    def fts_search_sql(self, query: str, limit: int) -> Tuple[str, Tuple]:
        """Generate tsvector search query with ranking."""
        escaped = self.escape_fts_query(query)
        sql = """
            SELECT * FROM entities
            WHERE search_vector @@ plainto_tsquery('english', %s)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC
            LIMIT %s
        """
        return sql, (escaped, escaped, limit)

    def escape_fts_query(self, query: str) -> str:
        """
        Escape a query string for safe tsvector searching.

        plainto_tsquery handles most escaping, but we still sanitize.
        """
        return query.replace("'", "''")

    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
