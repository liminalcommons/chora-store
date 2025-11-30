"""
Tests for the Epigenetic Bridge - Schema extension and hook execution.

The Epigenetic Bridge allows experimental patterns to:
1. Inject fields into entity schemas at runtime
2. Define hooks that modulate system behavior
3. All without modifying the kernel physics
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import tempfile
import os

from chora_store.factory import EntityFactory
from chora_store.observer import (
    EntityObserver,
    EpigeneticHook,
    HookResult,
    ChangeType,
)
from chora_store.repository import EntityRepository
from chora_store.models import Entity


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
def observer():
    """Create a fresh observer."""
    return EntityObserver()


def make_pattern_entity(
    pattern_id: str = "pattern-feature-ttl",
    target: str = "feature",
    status: str = "experimental",
    inject_fields: dict = None,
    hooks: list = None,
) -> Entity:
    """Helper to create schema-extension pattern entities."""
    if inject_fields is None:
        inject_fields = {
            "ttl_days": {
                "type": "integer",
                "default": 30,
                "description": "Days before TTL expires",
            }
        }
    if hooks is None:
        hooks = [
            {
                "id": "check-ttl",
                "trigger": "cron:daily",
                "condition": "entity_type == 'feature' and entity_status == 'nascent' and days_since_created > entity_ttl_days",
                "action": "transition(status='drifting')",
            }
        ]

    return Entity(
        id=pattern_id,
        type="pattern",
        status=status,
        data={
            "name": "Feature TTL Pattern",
            "subtype": "schema-extension",
            "mechanics": {
                "target": target,
                "inject_fields": inject_fields,
                "hooks": hooks,
            },
        },
    )


def make_feature_entity(
    feature_id: str = "feature-test",
    status: str = "nascent",
    created_days_ago: int = 0,
    ttl_days: int = None,
    epigenetics: list = None,
) -> Entity:
    """Helper to create feature entities for testing."""
    created = datetime.utcnow() - timedelta(days=created_days_ago)
    data = {
        "name": "Test Feature",
        "created": created.isoformat(),
        "updated": datetime.utcnow().isoformat(),
    }
    if ttl_days is not None:
        data["ttl_days"] = ttl_days
    if epigenetics is not None:
        data["_epigenetics"] = epigenetics

    return Entity(
        id=feature_id,
        type="feature",
        status=status,
        data=data,
        created_at=created,
        updated_at=datetime.utcnow(),
    )


class TestEpigeneticHookLoading:
    """Test loading hooks from experimental patterns."""

    def test_load_hooks_from_experimental_pattern(self, repository, observer):
        """Test that hooks are loaded from experimental patterns."""
        # Create an experimental schema-extension pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Load hooks
        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")

        assert len(hooks) == 1
        assert hooks[0].hook_id == "check-ttl"
        assert hooks[0].pattern_id == "pattern-feature-ttl"
        assert hooks[0].target_type == "feature"

    def test_ignore_non_experimental_patterns(self, repository, observer):
        """Test that non-experimental patterns are ignored."""
        pattern = make_pattern_entity(status="adopted")
        repository.create(pattern)

        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(hooks) == 0

    def test_ignore_non_schema_extension_patterns(self, repository, observer):
        """Test that non-schema-extension patterns are ignored."""
        pattern = Entity(
            id="pattern-other",
            type="pattern",
            status="experimental",
            data={
                "name": "Other Pattern",
                "subtype": "process",  # Not schema-extension
            },
        )
        repository.create(pattern)

        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(hooks) == 0

    def test_filter_hooks_by_trigger_type(self, repository, observer):
        """Test that hooks are filtered by trigger type."""
        pattern = make_pattern_entity(
            hooks=[
                {"id": "hook-daily", "trigger": "cron:daily", "condition": "true", "action": "noop"},
                {"id": "hook-hourly", "trigger": "cron:hourly", "condition": "true", "action": "noop"},
            ]
        )
        repository.create(pattern)

        daily_hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(daily_hooks) == 1
        assert daily_hooks[0].hook_id == "hook-daily"

        hourly_hooks = observer.load_epigenetic_hooks(repository, "cron:hourly")
        assert len(hourly_hooks) == 1
        assert hourly_hooks[0].hook_id == "hook-hourly"


class TestConditionEvaluation:
    """Test hook condition evaluation."""

    def test_simple_type_condition(self, observer):
        """Test evaluating simple entity type condition."""
        entity = make_feature_entity()
        result = observer._evaluate_condition("entity_type == 'feature'", entity)
        assert result is True

    def test_simple_status_condition(self, observer):
        """Test evaluating simple status condition."""
        entity = make_feature_entity(status="nascent")
        result = observer._evaluate_condition("entity_status == 'nascent'", entity)
        assert result is True

        entity = make_feature_entity(status="stable")
        result = observer._evaluate_condition("entity_status == 'nascent'", entity)
        assert result is False

    def test_entity_field_condition(self, observer):
        """Test evaluating condition with entity data fields."""
        entity = make_feature_entity(ttl_days=30)
        result = observer._evaluate_condition("entity_ttl_days == 30", entity)
        assert result is True

    def test_days_since_condition(self, observer):
        """Test evaluating days_since condition."""
        # Entity created 45 days ago
        entity = make_feature_entity(created_days_ago=45, ttl_days=30)
        result = observer._evaluate_condition(
            "days_since_created > entity_ttl_days",
            entity
        )
        assert result is True

        # Entity created 15 days ago
        entity = make_feature_entity(created_days_ago=15, ttl_days=30)
        result = observer._evaluate_condition(
            "days_since_created > entity_ttl_days",
            entity
        )
        assert result is False

    def test_compound_condition(self, observer):
        """Test evaluating compound AND condition."""
        entity = make_feature_entity(
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
        )
        result = observer._evaluate_condition(
            "entity_type == 'feature' and entity_status == 'nascent' and days_since_created > entity_ttl_days",
            entity
        )
        assert result is True

    def test_invalid_condition_returns_false(self, observer):
        """Test that invalid conditions return False."""
        entity = make_feature_entity()
        result = observer._evaluate_condition("invalid syntax {{{{", entity)
        assert result is False


class TestActionExecution:
    """Test hook action execution."""

    def test_transition_action(self, repository, observer):
        """Test executing transition action."""
        # Create a feature
        feature = make_feature_entity(status="nascent")
        repository.create(feature)

        # Execute transition action
        result = observer._execute_action(
            "transition(status='drifting')",
            feature,
            repository,
        )

        assert "drifting" in result

        # Verify entity was updated
        updated = repository.read(feature.id)
        assert updated.status == "drifting"

    def test_unknown_action(self, repository, observer):
        """Test unknown action returns message."""
        feature = make_feature_entity()
        result = observer._execute_action("unknown_action()", feature, repository)
        assert "Unknown action" in result


class TestRunEpigeneticHooks:
    """Test end-to-end hook execution."""

    def test_run_hooks_transitions_expired_features(self, repository, observer):
        """Test that running hooks transitions features past TTL."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a feature that should trigger (45 days old, 30 day TTL)
        feature = make_feature_entity(
            feature_id="feature-old",
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
            epigenetics=["pattern-feature-ttl"],
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Verify hook matched and acted
        assert len(results) == 1
        assert results[0].matched is True
        assert results[0].action_taken is not None
        assert "drifting" in results[0].action_taken

        # Verify entity was transitioned
        updated = repository.read("feature-old")
        assert updated.status == "drifting"

    def test_run_hooks_skips_fresh_features(self, repository, observer):
        """Test that hooks skip features within TTL."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a fresh feature (5 days old, 30 day TTL)
        feature = make_feature_entity(
            feature_id="feature-fresh",
            status="nascent",
            created_days_ago=5,
            ttl_days=30,
            epigenetics=["pattern-feature-ttl"],
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Verify hook did not match
        assert len(results) == 1
        assert results[0].matched is False
        assert results[0].action_taken is None

        # Verify entity was NOT transitioned
        unchanged = repository.read("feature-fresh")
        assert unchanged.status == "nascent"

    def test_run_hooks_skips_non_epigenetic_entities(self, repository, observer):
        """Test that hooks skip entities without epigenetic tagging."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a feature WITHOUT epigenetic tagging
        feature = make_feature_entity(
            feature_id="feature-plain",
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
            epigenetics=None,  # No epigenetic tagging
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Should have no results (entity skipped)
        assert len(results) == 0

        # Verify entity was NOT transitioned
        unchanged = repository.read("feature-plain")
        assert unchanged.status == "nascent"


@pytest.fixture
def kernel_path():
    """Get the path to chora-kernel."""
    # When running tests from packages/chora-store, kernel is at ../../packages/chora-kernel
    # or from workspace root at packages/chora-kernel
    import os

    # Try various paths
    candidates = [
        "packages/chora-kernel",  # From workspace root
        "../chora-kernel",  # From packages/chora-store
        "../../packages/chora-kernel",  # From packages/chora-store/tests
    ]

    for path in candidates:
        schema_path = os.path.join(path, "standards", "entity.yaml")
        if os.path.exists(schema_path):
            return path

    # Fallback: construct absolute path
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(test_dir, "..", "..", "chora-kernel")


class TestFactoryEpigeneticSchema:
    """Test factory's epigenetic schema extension."""

    def test_factory_loads_experimental_patterns(self, repository, kernel_path):
        """Test that factory loads experimental patterns."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern in repository
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Load patterns
        patterns = factory._load_experimental_patterns("feature")
        assert len(patterns) == 1
        assert patterns[0].id == "pattern-feature-ttl"

    def test_get_effective_schema_merges_fields(self, repository, kernel_path):
        """Test that effective schema includes epigenetic fields."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Get effective schema
        type_schema, applied_patterns = factory._get_effective_schema("feature")

        # Verify pattern was applied
        assert "pattern-feature-ttl" in applied_patterns

        # Verify field was merged into additional_optional
        optional_fields = type_schema.get("additional_optional", [])
        assert "ttl_days" in optional_fields

        # Verify epigenetic field definition was stored
        epigenetic_fields = type_schema.get("_epigenetic_fields", {})
        assert "ttl_days" in epigenetic_fields

    def test_apply_epigenetic_defaults(self, repository, kernel_path):
        """Test that epigenetic defaults are applied."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Get effective schema
        type_schema, _ = factory._get_effective_schema("feature")

        # Apply defaults to empty data
        data = {}
        data = factory._apply_epigenetic_defaults("feature", data, type_schema)

        # Verify default was applied
        assert data.get("ttl_days") == 30
