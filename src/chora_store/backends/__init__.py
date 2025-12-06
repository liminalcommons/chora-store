"""
Backend adapters for chora-store.

Provides database backend abstraction for SQLite (local-first) and PostgreSQL (cloud).
"""

import os
from typing import Optional

from .protocol import BackendAdapter
from .sqlite import SQLiteAdapter

# PostgreSQL is optional - only import if available
try:
    from .postgres import PostgresAdapter
    _POSTGRES_AVAILABLE = True
except ImportError:
    _POSTGRES_AVAILABLE = False
    PostgresAdapter = None  # type: ignore


def create_adapter(
    backend: Optional[str] = None,
    **kwargs,
) -> BackendAdapter:
    """
    Factory function to create a backend adapter.

    Args:
        backend: Backend type ('sqlite' or 'postgres').
                 Defaults to CHORA_DB_BACKEND env var, or 'sqlite'.
        **kwargs: Backend-specific arguments:
            SQLite: db_path (default: ~/.chora/chora.db)
            PostgreSQL: dsn, pool_min, pool_max

    Returns:
        BackendAdapter instance

    Raises:
        ValueError: If backend is unknown
        ImportError: If postgres is requested but psycopg not installed

    Examples:
        # Default SQLite
        adapter = create_adapter()

        # SQLite with custom path
        adapter = create_adapter('sqlite', db_path='/tmp/test.db')

        # PostgreSQL
        adapter = create_adapter('postgres', dsn='postgresql://localhost/chora')

        # From environment
        os.environ['CHORA_DB_BACKEND'] = 'postgres'
        os.environ['CHORA_DB_DSN'] = 'postgresql://localhost/chora'
        adapter = create_adapter()
    """
    backend = backend or os.environ.get('CHORA_DB_BACKEND', 'sqlite')

    if backend == 'sqlite':
        db_path = kwargs.get('db_path') or os.environ.get(
            'CHORA_DB_PATH', '~/.chora/chora.db'
        )
        return SQLiteAdapter(db_path=db_path)

    elif backend == 'postgres':
        if not _POSTGRES_AVAILABLE:
            raise ImportError(
                "PostgreSQL backend requires psycopg. "
                "Install with: pip install 'chora-store[postgres]'"
            )
        dsn = kwargs.get('dsn') or os.environ.get('CHORA_DB_DSN')
        if not dsn:
            raise ValueError(
                "PostgreSQL backend requires 'dsn' argument or CHORA_DB_DSN env var"
            )
        pool_min = kwargs.get('pool_min', 2)
        pool_max = kwargs.get('pool_max', 10)
        return PostgresAdapter(dsn=dsn, pool_min=pool_min, pool_max=pool_max)

    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'sqlite' or 'postgres'.")


__all__ = [
    "BackendAdapter",
    "SQLiteAdapter",
    "PostgresAdapter",
    "create_adapter",
]
