"""
EntityRepository - SQLite persistence layer.

This is the storage layer. It handles CRUD operations against SQLite.
The EntityFactory should be used for creating entities (with validation).
Direct repository access bypasses the Physics Engine.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from contextlib import contextmanager

from .models import Entity, ValidationError
from .schema import get_all_schema_sql


class EntityRepository:
    """
    SQLite-based entity repository.

    Provides CRUD operations and search capabilities.
    """

    def __init__(self, db_path: str = "~/.chora/chora.db"):
        """
        Initialize repository with database path.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.chora/chora.db
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._connection() as conn:
            conn.executescript(get_all_schema_sql())

    @contextmanager
    def _connection(self):
        """Context manager for database connections."""
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

    def create(self, entity: Entity) -> Entity:
        """
        Create a new entity.

        Args:
            entity: Entity to create

        Returns:
            Created entity with version 1

        Raises:
            ValidationError: If entity with same ID already exists
        """
        with self._connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO entities (id, type, status, data, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity.id,
                        entity.type,
                        entity.status,
                        json.dumps(entity.data),
                        1,
                        entity.created_at.isoformat(),
                        entity.updated_at.isoformat(),
                    ),
                )
                # Record version for sync
                conn.execute(
                    """
                    INSERT INTO entity_versions (id, entity_id, version, change_type, changed_at, data_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{entity.id}:1",
                        entity.id,
                        1,
                        "create",
                        datetime.utcnow().isoformat(),
                        json.dumps(entity.to_dict()),
                    ),
                )
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    raise ValidationError(f"Entity '{entity.id}' already exists")
                elif "CHECK constraint failed" in str(e):
                    raise ValidationError(f"Entity violates schema constraints: {e}")
                raise

        return entity.copy(version=1)

    def read(self, entity_id: str) -> Optional[Entity]:
        """
        Read an entity by ID.

        Args:
            entity_id: Entity ID to read

        Returns:
            Entity if found, None otherwise
        """
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,)
            ).fetchone()

            if row is None:
                return None

            return self._row_to_entity(row)

    def update(self, entity: Entity) -> Entity:
        """
        Update an existing entity.

        Uses optimistic concurrency - fails if version doesn't match.

        Args:
            entity: Entity with changes to save

        Returns:
            Updated entity with incremented version

        Raises:
            ValidationError: If entity not found or version conflict
        """
        new_version = entity.version + 1
        now = datetime.utcnow()

        with self._connection() as conn:
            result = conn.execute(
                """
                UPDATE entities
                SET status = ?, data = ?, version = ?, updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    entity.status,
                    json.dumps(entity.data),
                    new_version,
                    now.isoformat(),
                    entity.id,
                    entity.version,
                ),
            )

            if result.rowcount == 0:
                existing = self.read(entity.id)
                if existing is None:
                    raise ValidationError(f"Entity '{entity.id}' not found")
                else:
                    raise ValidationError(
                        f"Version conflict: expected {entity.version}, got {existing.version}"
                    )

            # Record version for sync
            updated_entity = entity.copy(version=new_version, updated_at=now)
            conn.execute(
                """
                INSERT INTO entity_versions (id, entity_id, version, change_type, changed_at, data_snapshot)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{entity.id}:{new_version}",
                    entity.id,
                    new_version,
                    "update",
                    now.isoformat(),
                    json.dumps(updated_entity.to_dict()),
                ),
            )

        return updated_entity

    def delete(self, entity_id: str) -> bool:
        """
        Delete an entity by ID.

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        with self._connection() as conn:
            # Get full entity before delete (for version tracking snapshot)
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,)
            ).fetchone()

            if row is None:
                return False

            version = row["version"]

            # Create snapshot for sync/audit purposes
            entity_snapshot = {
                "id": row["id"],
                "type": row["type"],
                "status": row["status"],
                "data": json.loads(row["data"]),
                "version": version,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

            # Record deletion for sync BEFORE delete
            conn.execute(
                """
                INSERT INTO entity_versions (id, entity_id, version, change_type, changed_at, data_snapshot)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{entity_id}:{version + 1}",
                    entity_id,
                    version + 1,
                    "delete",
                    datetime.utcnow().isoformat(),
                    json.dumps(entity_snapshot),
                ),
            )

            # Now delete the entity
            result = conn.execute(
                "DELETE FROM entities WHERE id = ?",
                (entity_id,)
            )

            return result.rowcount > 0

    def list(
        self,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """
        List entities with optional filters.

        Args:
            entity_type: Filter by type (e.g., "feature")
            status: Filter by status (e.g., "in_progress")
            limit: Maximum entities to return
            offset: Number of entities to skip

        Returns:
            List of matching entities
        """
        query = "SELECT * FROM entities WHERE 1=1"
        params = []

        if entity_type:
            query += " AND type = ?"
            params.append(entity_type)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def search(self, query: str, limit: int = 20) -> List[Entity]:
        """
        Full-text search across entities.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching entities
        """
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT e.* FROM entities e
                JOIN entities_fts fts ON e.rowid = fts.rowid
                WHERE entities_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_changes_since(self, since_version: int) -> List[Tuple[Entity, str]]:
        """
        Get entity changes since a version (for sync).

        Args:
            since_version: Get changes after this version

        Returns:
            List of (entity, change_type) tuples
        """
        with self._connection() as conn:
            # Query version records directly - all changes have data_snapshot
            rows = conn.execute(
                """
                SELECT * FROM entity_versions
                WHERE CAST(SUBSTR(id, INSTR(id, ':') + 1) AS INTEGER) > ?
                ORDER BY changed_at
                """,
                (since_version,),
            ).fetchall()

            results = []
            for row in rows:
                change_type = row["change_type"]
                data_snapshot = row["data_snapshot"]

                if not data_snapshot:
                    # Skip records without snapshots (shouldn't happen)
                    continue

                entity = Entity.from_dict(json.loads(data_snapshot))
                results.append((entity, change_type))

            return results

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert database row to Entity."""
        return Entity(
            id=row["id"],
            type=row["type"],
            status=row["status"],
            data=json.loads(row["data"]),
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
