"""
Shared fixtures for BDD step definitions.
"""

import pytest
import tempfile
import os

from chora_store.factory import EntityFactory
from chora_store.repository import EntityRepository
from chora_store.models import Entity


def get_kernel_path():
    """Get the path to chora-kernel."""
    candidates = [
        "packages/chora-kernel",
        "../chora-kernel",
        "../../packages/chora-kernel",
    ]

    for path in candidates:
        schema_path = os.path.join(path, "standards", "entity.yaml")
        if os.path.exists(schema_path):
            return path

    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(test_dir, "..", "..", "..", "chora-kernel")


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def repository(temp_db):
    """Create a repository with temp database."""
    return EntityRepository(db_path=temp_db)


@pytest.fixture
def factory(repository):
    """Create a factory with temp database."""
    kernel_path = get_kernel_path()
    return EntityFactory(kernel_path=kernel_path, repository=repository)


@pytest.fixture
def context():
    """Shared context for passing data between steps."""
    return {}
