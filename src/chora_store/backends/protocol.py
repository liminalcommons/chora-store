"""
BackendAdapter Protocol - Minimal interface for database backend differences.

This protocol abstracts only what differs between SQLite and PostgreSQL,
keeping the abstraction surface as small as possible.

The protocol covers:
1. Connection management
2. SQL syntax differences (params, JSON paths)
3. Schema generation
4. Error handling
5. Full-text search

The Repository uses this protocol to remain backend-agnostic.
"""

from abc import abstractmethod
from contextlib import contextmanager
from typing import Protocol, Any, Iterator, List, Tuple, Optional, runtime_checkable


@runtime_checkable
class BackendAdapter(Protocol):
    """
    Minimal protocol for database backend differences.

    This protocol abstracts the small set of operations that differ
    between SQLite and PostgreSQL. The Repository delegates
    these operations to the adapter.

    Implementations:
        - SQLiteAdapter: sqlite3-based, local-first
        - PostgresAdapter: psycopg-based, cloud-ready
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # PROPERTIES
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    @abstractmethod
    def param(self) -> str:
        """
        SQL parameter placeholder style.

        Returns:
            '?' for SQLite, '%s' for PostgreSQL
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Backend name for logging and debugging.

        Returns:
            'sqlite' or 'postgres'
        """
        ...

    @property
    @abstractmethod
    def supports_fts(self) -> bool:
        """
        Whether this backend supports full-text search.

        Returns:
            True if FTS is available
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    @contextmanager
    def connection(self) -> Iterator[Any]:
        """
        Context manager for database connections.

        For SQLite: Creates new connection, enables foreign keys, handles commit/rollback.
        For PostgreSQL: Gets connection from pool, handles commit/rollback.

        Yields:
            Database connection object

        Example:
            with adapter.connection() as conn:
                conn.execute("SELECT * FROM entities")
        """
        ...

    @abstractmethod
    def execute(
        self,
        conn: Any,
        sql: str,
        params: Tuple = (),
    ) -> Any:
        """
        Execute SQL and return cursor/result.

        Args:
            conn: Connection from connection() context manager
            sql: SQL statement (uses self.param for placeholders)
            params: Parameter values

        Returns:
            Cursor or result object
        """
        ...

    @abstractmethod
    def executemany(
        self,
        conn: Any,
        sql: str,
        params_list: List[Tuple],
    ) -> Any:
        """
        Execute SQL with multiple parameter sets.

        Args:
            conn: Connection from connection() context manager
            sql: SQL statement
            params_list: List of parameter tuples

        Returns:
            Cursor or result object
        """
        ...

    @abstractmethod
    def executescript(self, conn: Any, sql: str) -> None:
        """
        Execute multiple SQL statements (for schema init).

        For SQLite: Uses executescript()
        For PostgreSQL: Splits and executes statements

        Args:
            conn: Connection from connection() context manager
            sql: Multiple SQL statements separated by semicolons
        """
        ...

    @abstractmethod
    def fetchone(self, cursor: Any) -> Optional[dict]:
        """
        Fetch one row as dict.

        Args:
            cursor: Cursor from execute()

        Returns:
            Row as dict, or None if no rows
        """
        ...

    @abstractmethod
    def fetchall(self, cursor: Any) -> List[dict]:
        """
        Fetch all rows as list of dicts.

        Args:
            cursor: Cursor from execute()

        Returns:
            List of rows as dicts
        """
        ...

    @abstractmethod
    def rowcount(self, cursor: Any) -> int:
        """
        Get number of affected rows.

        Args:
            cursor: Cursor from execute()

        Returns:
            Number of rows affected by last operation
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # SQL GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def json_extract(self, column: str, path: str) -> str:
        """
        Generate JSON field extraction expression.

        Args:
            column: Column name (e.g., 'data')
            path: JSON path (e.g., 'relationship_type')

        Returns:
            SQLite: "json_extract(data, '$.relationship_type')"
            PostgreSQL: "data->>'relationship_type'"
        """
        ...

    @abstractmethod
    def json_set(self, column: str, path: str, value_expr: str) -> str:
        """
        Generate JSON field update expression.

        Args:
            column: Column name
            path: JSON path to update
            value_expr: SQL expression for the new value

        Returns:
            SQLite: "json_set(data, '$.path', value_expr)"
            PostgreSQL: "jsonb_set(data, '{path}', value_expr)"
        """
        ...

    @abstractmethod
    def datetime_now(self) -> str:
        """
        Generate current timestamp expression.

        Returns:
            SQLite: "datetime('now')"
            PostgreSQL: "NOW()"
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEMA GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def get_schema_sql(self) -> str:
        """
        Generate complete schema DDL for this backend.

        Returns:
            Complete SQL to create all tables, indexes, triggers
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def is_integrity_error(self, error: Exception) -> bool:
        """
        Check if exception is an integrity error (unique/check constraint).

        Args:
            error: Exception to check

        Returns:
            True if this is an integrity constraint error
        """
        ...

    @abstractmethod
    def is_unique_violation(self, error: Exception) -> bool:
        """
        Check if exception is a unique constraint violation.

        Args:
            error: Exception to check

        Returns:
            True if this is a unique constraint violation
        """
        ...

    @abstractmethod
    def is_check_violation(self, error: Exception) -> bool:
        """
        Check if exception is a check constraint violation.

        Args:
            error: Exception to check

        Returns:
            True if this is a check constraint violation
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # SEARCH (FTS)
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def fts_search_sql(self, query: str, limit: int) -> Tuple[str, Tuple]:
        """
        Generate FTS search query.

        Args:
            query: Search query string
            limit: Maximum results

        Returns:
            Tuple of (SQL string, parameters tuple)
        """
        ...

    @abstractmethod
    def escape_fts_query(self, query: str) -> str:
        """
        Escape a query string for safe FTS searching.

        Args:
            query: Raw search query

        Returns:
            Escaped query string
        """
        ...

    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    @abstractmethod
    def close(self) -> None:
        """
        Close connections and release resources.

        For SQLite: No-op (connections are per-request)
        For PostgreSQL: Close connection pool
        """
        ...
