"""
Pytest configuration and fixtures for chora-store tests.
"""

import os
import tempfile
import pytest

from chora_store.repository import Repository
from chora_store.backends import create_adapter, SQLiteAdapter

# Check if PostgreSQL tests should run
POSTGRES_DSN = os.environ.get('CHORA_TEST_POSTGRES_DSN')


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "postgres: marks tests that require PostgreSQL"
    )


@pytest.fixture
def temp_db_path():
    """Create a temporary SQLite database file."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        yield f.name
    # Cleanup
    try:
        os.unlink(f.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def sqlite_adapter(temp_db_path):
    """Create a SQLite adapter for testing."""
    adapter = SQLiteAdapter(db_path=temp_db_path)
    yield adapter
    adapter.close()


@pytest.fixture
def sqlite_repo(temp_db_path):
    """Create a SQLite-backed Repository for testing."""
    repo = Repository(db_path=temp_db_path)
    yield repo
    repo.close()


@pytest.fixture
def postgres_adapter():
    """Create a PostgreSQL adapter for testing (if available)."""
    if not POSTGRES_DSN:
        pytest.skip("PostgreSQL DSN not configured")

    try:
        from chora_store.backends import PostgresAdapter
        adapter = PostgresAdapter(dsn=POSTGRES_DSN)
        # Initialize schema
        with adapter.connection() as conn:
            adapter.executescript(conn, adapter.get_schema_sql())
        yield adapter
        # Cleanup - drop tables
        with adapter.connection() as conn:
            adapter.execute(conn, "DROP TABLE IF EXISTS entity_versions CASCADE")
            adapter.execute(conn, "DROP TABLE IF EXISTS traces CASCADE")
            adapter.execute(conn, "DROP TABLE IF EXISTS entities CASCADE")
        adapter.close()
    except ImportError:
        pytest.skip("psycopg not installed")


@pytest.fixture
def postgres_repo():
    """Create a PostgreSQL-backed Repository for testing (if available)."""
    if not POSTGRES_DSN:
        pytest.skip("PostgreSQL DSN not configured")

    try:
        repo = Repository(backend='postgres', dsn=POSTGRES_DSN)
        yield repo
        # Cleanup - drop tables
        with repo._adapter.connection() as conn:
            repo._adapter.execute(conn, "DROP TABLE IF EXISTS entity_versions CASCADE")
            repo._adapter.execute(conn, "DROP TABLE IF EXISTS traces CASCADE")
            repo._adapter.execute(conn, "DROP TABLE IF EXISTS entities CASCADE")
        repo.close()
    except ImportError:
        pytest.skip("psycopg not installed")


@pytest.fixture(params=['sqlite', 'postgres'])
def any_repo(request, temp_db_path):
    """
    Parameterized fixture that runs tests against both backends.

    Use this for parity tests that should pass on both SQLite and PostgreSQL.
    """
    if request.param == 'sqlite':
        repo = Repository(db_path=temp_db_path)
        yield repo
        repo.close()
    elif request.param == 'postgres':
        if not POSTGRES_DSN:
            pytest.skip("PostgreSQL DSN not configured")
        try:
            repo = Repository(backend='postgres', dsn=POSTGRES_DSN)
            yield repo
            # Cleanup
            with repo._adapter.connection() as conn:
                repo._adapter.execute(conn, "DROP TABLE IF EXISTS entity_versions CASCADE")
                repo._adapter.execute(conn, "DROP TABLE IF EXISTS traces CASCADE")
                repo._adapter.execute(conn, "DROP TABLE IF EXISTS entities CASCADE")
            repo.close()
        except ImportError:
            pytest.skip("psycopg not installed")
