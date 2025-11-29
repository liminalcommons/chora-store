"""
Tests for EntityFactory - the Physics Engine.

These tests verify that:
1. Valid entities can be created
2. Invalid entities are rejected
3. Semantic IDs are generated correctly
4. Status validation works
5. Events are emitted
"""

import pytest
import tempfile
import os
from pathlib import Path

from chora_store.factory import EntityFactory
from chora_store.repository import EntityRepository
from chora_store.observer import EntityObserver, ChangeType
from chora_store.models import Entity, ValidationError, InvalidEntityType


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def kernel_path():
    """Path to chora-kernel for testing."""
    # Look for kernel relative to workspace root
    workspace_root = Path(__file__).parent.parent.parent.parent
    kernel = workspace_root / "chora-kernel"
    if kernel.exists():
        return str(kernel)
    # Fallback to sibling package
    return str(Path(__file__).parent.parent.parent / "chora-kernel")


@pytest.fixture
def factory(temp_db, kernel_path):
    """Create factory with temp database."""
    repo = EntityRepository(db_path=temp_db)
    observer = EntityObserver()
    return EntityFactory(kernel_path=kernel_path, repository=repo, observer=observer)


class TestEntityCreation:
    """Test valid entity creation."""

    def test_create_feature(self, factory):
        """Test creating a feature entity."""
        entity = factory.create("feature", "Voice Canvas")

        assert entity.id == "feature-voice-canvas"
        assert entity.type == "feature"
        assert entity.status == "planned"  # Default status
        assert entity.data["name"] == "Voice Canvas"

    def test_create_with_custom_status(self, factory):
        """Test creating entity with custom status."""
        entity = factory.create("feature", "Test Feature", status="in_progress")

        assert entity.status == "in_progress"

    def test_create_pattern(self, factory):
        """Test creating a pattern entity."""
        entity = factory.create(
            "pattern",
            "Semantic Identity",
            context="When naming entities",
            problem="Arbitrary IDs are hard to understand",
            solution="Use semantic, self-documenting IDs",
        )

        assert entity.id == "pattern-semantic-identity"
        assert entity.type == "pattern"
        assert entity.data["context"] == "When naming entities"

    def test_semantic_id_generation(self, factory):
        """Test that semantic IDs are generated correctly."""
        test_cases = [
            ("Voice Canvas", "feature-voice-canvas"),
            ("Hello World", "feature-hello-world"),
            ("API Integration 2.0", "feature-api-integration-20"),
            ("Test--Multiple---Hyphens", "feature-test-multiple-hyphens"),
            ("  Spaces Around  ", "feature-spaces-around"),
        ]

        for title, expected_id in test_cases:
            entity = factory.create("feature", title)
            assert entity.id == expected_id
            # Clean up for next test
            factory.delete(entity.id)


class TestValidationRejection:
    """Test that invalid entities are rejected."""

    def test_reject_invalid_type(self, factory):
        """Test that invalid entity type is rejected."""
        with pytest.raises(InvalidEntityType) as exc:
            factory.create("invalid_type", "Test")

        assert "Unknown entity type" in str(exc.value)

    def test_reject_invalid_status(self, factory):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc:
            factory.create("feature", "Test", status="invalid_status")

        assert "Invalid status" in str(exc.value)

    def test_reject_duplicate_id(self, factory):
        """Test that duplicate entity ID is rejected."""
        factory.create("feature", "Test Feature")

        with pytest.raises(ValidationError) as exc:
            factory.create("feature", "Test Feature")

        assert "already exists" in str(exc.value)

    def test_reject_empty_title(self, factory):
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError) as exc:
            factory.create("feature", "")

        assert "empty slug" in str(exc.value)

    def test_reject_special_chars_only(self, factory):
        """Test that title with only special chars is rejected."""
        with pytest.raises(ValidationError) as exc:
            factory.create("feature", "!@#$%^&*()")

        assert "empty slug" in str(exc.value)


class TestEventEmission:
    """Test that stigmergic events are emitted."""

    def test_create_emits_event(self, factory):
        """Test that create emits CREATED event."""
        events = []
        factory.observer.on_change(lambda e: events.append(e))

        entity = factory.create("feature", "Event Test")

        assert len(events) == 1
        assert events[0].entity_id == entity.id
        assert events[0].change_type == ChangeType.CREATED

    def test_update_emits_event(self, factory):
        """Test that update emits UPDATED event."""
        entity = factory.create("feature", "Update Test")

        events = []
        factory.observer.on_change(lambda e: events.append(e))

        factory.update(entity.id, status="in_progress")

        assert len(events) == 1
        assert events[0].change_type == ChangeType.UPDATED
        assert events[0].old_status == "planned"
        assert events[0].new_status == "in_progress"

    def test_delete_emits_event(self, factory):
        """Test that delete emits DELETED event."""
        entity = factory.create("feature", "Delete Test")

        events = []
        factory.observer.on_change(lambda e: events.append(e))

        factory.delete(entity.id)

        assert len(events) == 1
        assert events[0].change_type == ChangeType.DELETED


class TestEntityUpdate:
    """Test entity updates."""

    def test_update_status(self, factory):
        """Test updating entity status."""
        entity = factory.create("feature", "Status Test")
        assert entity.status == "planned"

        updated = factory.update(entity.id, status="in_progress")
        assert updated.status == "in_progress"

    def test_update_data(self, factory):
        """Test updating entity data fields."""
        entity = factory.create("feature", "Data Test")

        updated = factory.update(entity.id, description="New description")
        assert updated.data["description"] == "New description"

    def test_update_increments_version(self, factory):
        """Test that update increments version."""
        entity = factory.create("feature", "Version Test")
        assert entity.version == 1

        updated = factory.update(entity.id, status="in_progress")
        assert updated.version == 2


class TestEntityListing:
    """Test entity listing and search."""

    def test_list_all(self, factory):
        """Test listing all entities."""
        factory.create("feature", "List Test 1")
        factory.create("feature", "List Test 2")

        entities = factory.list()
        assert len(entities) >= 2

    def test_list_by_type(self, factory):
        """Test listing entities by type."""
        factory.create("feature", "Type Test")
        factory.create("pattern", "Pattern Test",
                      context="test", problem="test", solution="test")

        features = factory.list(entity_type="feature")
        patterns = factory.list(entity_type="pattern")

        assert all(e.type == "feature" for e in features)
        assert all(e.type == "pattern" for e in patterns)

    def test_list_by_status(self, factory):
        """Test listing entities by status."""
        factory.create("feature", "Status Test 1", status="planned")
        e2 = factory.create("feature", "Status Test 2", status="planned")
        factory.update(e2.id, status="in_progress")

        planned = factory.list(status="planned")
        in_progress = factory.list(status="in_progress")

        assert all(e.status == "planned" for e in planned)
        assert all(e.status == "in_progress" for e in in_progress)


class TestPhysicsEngine:
    """Test the Physics Engine principle: invalid states cannot exist."""

    def test_invalid_state_cannot_be_created(self, factory):
        """Verify the core principle: invalid states cannot exist."""
        # These should all fail
        invalid_attempts = [
            {"entity_type": "nonexistent", "title": "Test"},
            {"entity_type": "feature", "title": "Test", "status": "invalid"},
            {"entity_type": "feature", "title": ""},
        ]

        for attempt in invalid_attempts:
            with pytest.raises((ValidationError, InvalidEntityType)):
                factory.create(**attempt)

        # No invalid entities should exist
        all_entities = factory.list(limit=1000)
        for entity in all_entities:
            # Every entity should have valid type
            assert entity.type in factory.get_valid_types()
            # Every entity should have valid status for its type
            assert entity.status in factory.get_valid_statuses(entity.type)
            # Every entity ID should match pattern
            assert entity.id.startswith(f"{entity.type}-")
