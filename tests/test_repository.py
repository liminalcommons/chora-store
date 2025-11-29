"""
Tests for EntityRepository - SQLite persistence layer.
"""

import pytest
import tempfile
import os
from datetime import datetime

from chora_store.repository import EntityRepository
from chora_store.models import Entity, ValidationError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def repo(temp_db):
    """Create repository with temp database."""
    return EntityRepository(db_path=temp_db)


def make_entity(id: str = "feature-test", **kwargs) -> Entity:
    """Helper to create test entities."""
    defaults = {
        "type": "feature",
        "status": "planned",
        "data": {"name": "Test", "description": "Test entity"},
    }
    defaults.update(kwargs)
    return Entity(id=id, **defaults)


class TestCRUD:
    """Test basic CRUD operations."""

    def test_create(self, repo):
        """Test creating an entity."""
        entity = make_entity()
        created = repo.create(entity)

        assert created.id == entity.id
        assert created.version == 1

    def test_read(self, repo):
        """Test reading an entity."""
        entity = make_entity()
        repo.create(entity)

        read_entity = repo.read(entity.id)

        assert read_entity is not None
        assert read_entity.id == entity.id
        assert read_entity.type == entity.type

    def test_read_not_found(self, repo):
        """Test reading non-existent entity."""
        result = repo.read("nonexistent-id")
        assert result is None

    def test_update(self, repo):
        """Test updating an entity."""
        entity = make_entity()
        created = repo.create(entity)

        updated = created.copy(status="in_progress")
        result = repo.update(updated)

        assert result.status == "in_progress"
        assert result.version == 2

    def test_update_version_conflict(self, repo):
        """Test that version conflicts are detected."""
        entity = make_entity()
        created = repo.create(entity)

        # Simulate concurrent update
        repo.update(created.copy(status="in_progress"))

        # Try to update with old version
        with pytest.raises(ValidationError) as exc:
            repo.update(created.copy(status="blocked"))

        assert "Version conflict" in str(exc.value)

    def test_delete(self, repo):
        """Test deleting an entity."""
        entity = make_entity()
        repo.create(entity)

        result = repo.delete(entity.id)
        assert result is True

        # Verify deleted
        assert repo.read(entity.id) is None

    def test_delete_not_found(self, repo):
        """Test deleting non-existent entity."""
        result = repo.delete("nonexistent-id")
        assert result is False


class TestListing:
    """Test listing entities."""

    def test_list_all(self, repo):
        """Test listing all entities."""
        repo.create(make_entity("feature-test1"))
        repo.create(make_entity("feature-test2"))

        entities = repo.list()
        assert len(entities) == 2

    def test_list_by_type(self, repo):
        """Test filtering by type."""
        repo.create(make_entity("feature-test", type="feature"))
        repo.create(make_entity("pattern-test", type="pattern"))

        features = repo.list(entity_type="feature")
        assert len(features) == 1
        assert features[0].type == "feature"

    def test_list_by_status(self, repo):
        """Test filtering by status."""
        repo.create(make_entity("feature-test1", status="planned"))
        repo.create(make_entity("feature-test2", status="in_progress"))

        planned = repo.list(status="planned")
        assert len(planned) == 1
        assert planned[0].status == "planned"

    def test_list_pagination(self, repo):
        """Test pagination."""
        for i in range(5):
            repo.create(make_entity(f"feature-test{i}"))

        page1 = repo.list(limit=2, offset=0)
        page2 = repo.list(limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id


class TestSearch:
    """Test full-text search."""

    def test_search_by_name(self, repo):
        """Test searching by name."""
        repo.create(make_entity("feature-voice-canvas", data={
            "name": "Voice Canvas",
            "description": "Voice interface"
        }))
        repo.create(make_entity("feature-text-editor", data={
            "name": "Text Editor",
            "description": "Text editing"
        }))

        results = repo.search("Voice")
        assert len(results) == 1
        assert results[0].id == "feature-voice-canvas"

    def test_search_by_description(self, repo):
        """Test searching by description."""
        repo.create(make_entity("feature-test", data={
            "name": "Test",
            "description": "Unique description here"
        }))

        results = repo.search("Unique")
        assert len(results) == 1


class TestSchemaConstraints:
    """Test SQLite CHECK constraints."""

    def test_reject_invalid_type_at_db_level(self, repo):
        """Test that invalid type is rejected by DB CHECK constraint."""
        import sqlite3

        # Bypass model validation by using raw SQL
        with pytest.raises(sqlite3.IntegrityError) as exc:
            with repo._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO entities (id, type, status, data, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "invalid_type-test",
                        "invalid_type",  # Not in VALID_TYPES
                        "active",
                        "{}",
                        1,
                        "2025-01-01T00:00:00",
                        "2025-01-01T00:00:00",
                    ),
                )

        assert "CHECK constraint" in str(exc.value)

    def test_id_must_start_with_type(self, repo):
        """Test that ID must start with type (DB CHECK constraint)."""
        import sqlite3

        # Bypass model validation by using raw SQL
        with pytest.raises(sqlite3.IntegrityError) as exc:
            with repo._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO entities (id, type, status, data, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "wrong-prefix",  # Should be feature-prefix
                        "feature",
                        "planned",
                        "{}",
                        1,
                        "2025-01-01T00:00:00",
                        "2025-01-01T00:00:00",
                    ),
                )

        assert "CHECK constraint" in str(exc.value)

    def test_model_rejects_id_type_mismatch(self):
        """Test that Entity model rejects ID not starting with type."""
        with pytest.raises(ValidationError) as exc:
            Entity(
                id="wrong-prefix",
                type="feature",
                status="planned",
                data={},
            )

        assert "must start with type" in str(exc.value)


class TestVersionTracking:
    """Test version tracking for sync."""

    def test_changes_tracked(self, repo):
        """Test that changes are tracked."""
        entity = make_entity()
        repo.create(entity)
        repo.update(entity.copy(status="in_progress"))

        changes = repo.get_changes_since(0)
        assert len(changes) >= 2

    def test_delete_tracked(self, repo):
        """Test that deletes are tracked."""
        entity = make_entity()
        repo.create(entity)
        repo.delete(entity.id)

        changes = repo.get_changes_since(0)
        delete_changes = [c for c in changes if c[1] == "delete"]
        assert len(delete_changes) == 1
