"""
Repository - The Memory.

Persists Entities and Relations in a unified graph store.
Supports both SQLite (local-first) and PostgreSQL (cloud) backends.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any

from .models import Entity
from .backends import create_adapter, BackendAdapter


class Repository:
    """
    The Memory.
    Persists Entities and Relations in a unified graph store.

    Supports both SQLite and PostgreSQL backends via the BackendAdapter protocol.
    Default behavior (SQLite) is unchanged for backwards compatibility.
    """

    def __init__(
        self,
        db_path: str = None,
        adapter: BackendAdapter = None,
        backend: str = None,
        **kwargs,
    ):
        """
        Initialize repository.

        Args:
            db_path: Path to SQLite database (backwards compatibility).
                     Ignored if adapter is provided.
            adapter: Pre-configured BackendAdapter instance.
            backend: Backend type ('sqlite' or 'postgres').
                     Used with create_adapter if adapter not provided.
            **kwargs: Additional arguments for create_adapter.

        Examples:
            # Default SQLite (backwards compatible)
            repo = Repository()

            # SQLite with custom path (backwards compatible)
            repo = Repository(db_path="/tmp/test.db")

            # SQLite with explicit adapter
            repo = Repository(adapter=SQLiteAdapter(db_path="/tmp/test.db"))

            # PostgreSQL
            repo = Repository(backend='postgres', dsn='postgresql://localhost/chora')

            # Pre-configured adapter
            adapter = PostgresAdapter(dsn='...')
            repo = Repository(adapter=adapter)
        """
        if adapter is not None:
            self._adapter = adapter
        elif db_path is not None:
            # Backwards compatibility: db_path implies SQLite
            self._adapter = create_adapter('sqlite', db_path=db_path, **kwargs)
        else:
            # Use factory with optional backend override
            self._adapter = create_adapter(backend=backend, **kwargs)

        self._init_db()

    @property
    def db_path(self) -> Optional[str]:
        """
        Get the database path (SQLite only, for backwards compatibility).

        Returns:
            Path string for SQLite, None for other backends.
        """
        if hasattr(self._adapter, 'db_path'):
            return str(self._adapter.db_path)
        return None

    def _init_db(self):
        """Initialize database schema."""
        with self._adapter.connection() as conn:
            schema_sql = self._adapter.get_schema_sql()
            self._adapter.executescript(conn, schema_sql)

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def save(self, entity: Entity) -> Entity:
        """
        Persist Matter.

        Creates or updates an entity with optimistic locking (version tracking).
        """
        p = self._adapter.param
        with self._adapter.connection() as conn:
            # Check if entity exists for version tracking
            cursor = self._adapter.execute(
                conn,
                f"SELECT version FROM entities WHERE id = {p}",
                (entity.id,)
            )
            existing = self._adapter.fetchone(cursor)

            if existing:
                # Update with version increment
                new_version = existing['version'] + 1
                sql = f"""
                    UPDATE entities
                    SET type = {p}, status = {p}, title = {p}, data = {p},
                        version = {p}, updated_at = {p}
                    WHERE id = {p} AND version = {p}
                """
                cursor = self._adapter.execute(
                    conn, sql,
                    (
                        entity.type, entity.status, entity.title,
                        json.dumps(entity.data), new_version,
                        entity.updated_at.isoformat(), entity.id, existing['version']
                    )
                )
                if self._adapter.rowcount(cursor) == 0:
                    raise ValueError(f"Version conflict: entity {entity.id} was modified concurrently")

                # Log version change
                self._log_version(conn, entity.id, new_version, 'update', entity.data)
            else:
                # Insert new entity
                sql = f"""
                    INSERT INTO entities (id, type, status, title, data, version, created_at, updated_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                """
                self._adapter.execute(
                    conn, sql,
                    (
                        entity.id, entity.type, entity.status, entity.title,
                        json.dumps(entity.data), 1,
                        entity.created_at.isoformat(), entity.updated_at.isoformat()
                    )
                )
                # Log version create
                self._log_version(conn, entity.id, 1, 'create', entity.data)

        return entity

    def get(self, id: str) -> Optional[Entity]:
        """Retrieve an entity by ID."""
        p = self._adapter.param
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(
                conn,
                f"SELECT * FROM entities WHERE id = {p}",
                (id,)
            )
            row = self._adapter.fetchone(cursor)
            if row:
                return self._row_to_entity(row)
        return None

    def delete(self, id: str) -> bool:
        """
        Delete an entity.

        Returns True if entity was deleted, False if not found.
        """
        p = self._adapter.param
        with self._adapter.connection() as conn:
            # Get current state for version tracking
            cursor = self._adapter.execute(
                conn,
                f"SELECT version, data FROM entities WHERE id = {p}",
                (id,)
            )
            existing = self._adapter.fetchone(cursor)

            if not existing:
                return False

            # Delete entity
            cursor = self._adapter.execute(
                conn,
                f"DELETE FROM entities WHERE id = {p}",
                (id,)
            )

            # Log version delete
            data = json.loads(existing['data']) if isinstance(existing['data'], str) else existing['data']
            self._log_version(conn, id, existing['version'], 'delete', data)

            return self._adapter.rowcount(cursor) > 0

    def list(
        self,
        type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Entity]:
        """List entities with optional filters."""
        p = self._adapter.param
        query = "SELECT * FROM entities WHERE 1=1"
        params = []

        if type:
            query += f" AND type = {p}"
            params.append(type)
        if status:
            query += f" AND status = {p}"
            params.append(status)

        query += f" ORDER BY updated_at DESC LIMIT {p}"
        params.append(limit)

        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, query, tuple(params))
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════════
    # GRAPH OPERATIONS (Tensegrity Physics)
    # ═══════════════════════════════════════════════════════════════════════════

    def get_bonds_from(self, id: str) -> List[Entity]:
        """Get downstream bonds (Forces emanating from this Entity)."""
        p = self._adapter.param
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(
                conn,
                f"SELECT * FROM entities WHERE type = 'relationship' AND rel_from = {p}",
                (id,)
            )
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    def get_bonds_to(self, id: str) -> List[Entity]:
        """Get upstream bonds (Forces acting upon this Entity)."""
        p = self._adapter.param
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(
                conn,
                f"SELECT * FROM entities WHERE type = 'relationship' AND rel_to = {p}",
                (id,)
            )
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    def count(self, type: Optional[str] = None) -> int:
        """Count entities, optionally by type."""
        p = self._adapter.param
        query = "SELECT COUNT(*) as cnt FROM entities"
        params = []

        if type:
            query += f" WHERE type = {p}"
            params.append(type)

        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, query, tuple(params))
            row = self._adapter.fetchone(cursor)
            return row['cnt'] if row else 0

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH (FTS)
    # ═══════════════════════════════════════════════════════════════════════════

    def search(self, query: str, limit: int = 20) -> List[Entity]:
        """
        Full-text search across entities.

        Uses FTS5 (SQLite) or tsvector (PostgreSQL) depending on backend.
        """
        if not self._adapter.supports_fts:
            # Fallback to LIKE search
            return self._search_like(query, limit)

        sql, params = self._adapter.fts_search_sql(query, limit)

        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, sql, params)
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    def _search_like(self, query: str, limit: int) -> List[Entity]:
        """Fallback LIKE search when FTS is not available."""
        p = self._adapter.param
        pattern = f"%{query}%"
        sql = f"""
            SELECT * FROM entities
            WHERE title LIKE {p}
               OR {self._adapter.json_extract('data', 'description')} LIKE {p}
            LIMIT {p}
        """
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, sql, (pattern, pattern, limit))
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════════
    # TRAJECTORY OPERATIONS (Narrative Arc)
    # ═══════════════════════════════════════════════════════════════════════════

    def get_focus_chain(self, focus_id: str, limit: int = 10) -> List[Entity]:
        """
        Traverse the narrative arc (Trajectory).
        Follows 'relates-to' bonds upstream to find the history of this focus.
        """
        p = self._adapter.param
        # Recursive CTE works in both SQLite and PostgreSQL
        query = f"""
        WITH RECURSIVE chain AS (
            -- Start with the current focus
            SELECT id, type, status, title, data, created_at, updated_at, 0 as depth
            FROM entities WHERE id = {p}

            UNION ALL

            -- Follow 'relates-to' bonds from current to previous
            SELECT e.id, e.type, e.status, e.title, e.data, e.created_at, e.updated_at, c.depth + 1
            FROM entities e
            JOIN entities r ON r.type = 'relationship'
                AND r.rel_type = 'relates-to'
                AND r.rel_to = e.id
            JOIN chain c ON r.rel_from = c.id
            WHERE e.type = 'focus' AND c.depth < {p}
        )
        SELECT * FROM chain ORDER BY depth ASC;
        """
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, query, (focus_id, limit))
            rows = self._adapter.fetchall(cursor)
            return [self._row_to_entity(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════════
    # VERSION TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    def _log_version(
        self,
        conn: Any,
        entity_id: str,
        version: int,
        change_type: str,
        data: dict,
    ):
        """Log a version change for an entity."""
        p = self._adapter.param
        now = datetime.now(timezone.utc).isoformat()
        sql = f"""
            INSERT INTO entity_versions (id, entity_id, version, change_type, changed_at, data_snapshot)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p})
        """
        self._adapter.execute(
            conn, sql,
            (str(uuid.uuid4()), entity_id, version, change_type, now, json.dumps(data))
        )

    def get_versions(self, entity_id: str, limit: int = 10) -> List[dict]:
        """Get version history for an entity."""
        p = self._adapter.param
        sql = f"""
            SELECT * FROM entity_versions
            WHERE entity_id = {p}
            ORDER BY changed_at DESC
            LIMIT {p}
        """
        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, sql, (entity_id, limit))
            rows = self._adapter.fetchall(cursor)
            return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════════
    # HISTORY OPERATIONS (Memory of Action)
    # ═══════════════════════════════════════════════════════════════════════════

    def log_trace(
        self,
        tool: str,
        inputs: Any,
        outputs: Any = None,
        error: Optional[str] = None,
    ):
        """Record an action in history. The system remembers what it did."""
        p = self._adapter.param
        now = datetime.now(timezone.utc).isoformat()
        with self._adapter.connection() as conn:
            self._adapter.execute(
                conn,
                f"""INSERT INTO traces (id, tool, inputs, outputs, error, created_at)
                    VALUES ({p}, {p}, {p}, {p}, {p}, {p})""",
                (
                    str(uuid.uuid4()),
                    tool,
                    json.dumps(inputs) if inputs else None,
                    json.dumps(outputs) if outputs else None,
                    error,
                    now,
                )
            )

    def get_traces(self, tool: Optional[str] = None, limit: int = 100) -> List[dict]:
        """Retrieve action history."""
        p = self._adapter.param
        query = "SELECT * FROM traces WHERE 1=1"
        params = []

        if tool:
            query += f" AND tool = {p}"
            params.append(tool)

        query += f" ORDER BY created_at DESC LIMIT {p}"
        params.append(limit)

        with self._adapter.connection() as conn:
            cursor = self._adapter.execute(conn, query, tuple(params))
            rows = self._adapter.fetchall(cursor)
            return [dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _row_to_entity(self, row: dict) -> Entity:
        """Convert database row to Entity."""
        data = row['data']
        if isinstance(data, str):
            data = json.loads(data)

        created_at = row['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = row['updated_at']
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return Entity(
            id=row['id'],
            type=row['type'],
            status=row['status'],
            title=row['title'],
            data=data,
            created_at=created_at,
            updated_at=updated_at,
        )

    def close(self):
        """Close adapter connections."""
        self._adapter.close()
