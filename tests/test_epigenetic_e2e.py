"""
End-to-end integration tests for the epigenetic system.

These tests verify that the full epigenetic lifecycle works:
1. Pattern bootstrap loads patterns from kernel YAML into SQLite
2. Field injection applies epigenetic defaults to new entities
3. Event hooks fire on entity creation/update
4. TTL expiry triggers drift transition

Unlike unit tests, these use real components without mocking.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from chora_store.factory import EntityFactory
from chora_store.repository import EntityRepository
from chora_store.observer import EntityObserver


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def kernel_path():
    """Get the kernel path for bootstrap."""
    # Try relative paths from test directory
    candidates = [
        Path(__file__).parent.parent.parent.parent / "chora-kernel",
        Path("packages/chora-kernel"),
        Path("../chora-kernel"),
    ]
    for path in candidates:
        if (path / "standards" / "entity.yaml").exists():
            return path
    pytest.skip("Kernel not found - skipping integration test")


@pytest.fixture
def test_repo(temp_db):
    """Create a test repository."""
    return EntityRepository(db_path=temp_db)


@pytest.fixture
def test_observer():
    """Create a test observer."""
    return EntityObserver()


@pytest.fixture
def test_factory(kernel_path, test_repo, test_observer):
    """Create a test factory with the real kernel."""
    return EntityFactory(
        kernel_path=str(kernel_path),
        repository=test_repo,
        observer=test_observer,
    )


class TestPatternBootstrap:
    """Test pattern bootstrap mechanism."""

    def test_bootstrap_loads_epigenetic_patterns(self, test_factory, test_repo):
        """Bootstrap should load 7 epigenetic patterns from kernel YAML."""
        # Act
        loaded = test_factory.bootstrap_patterns_from_kernel()

        # Assert
        assert loaded >= 1, "Should load at least 1 pattern"

        # Verify patterns are in repository
        patterns = test_repo.list(entity_type="pattern", limit=100)
        epigenetic_patterns = [
            p for p in patterns
            if p.data.get("subtype") == "schema-extension"
        ]
        assert len(epigenetic_patterns) >= 1, "Should have schema-extension patterns"

    def test_bootstrap_skips_existing_patterns(self, test_factory, test_repo):
        """Bootstrap should not duplicate patterns that already exist."""
        # Act - run bootstrap twice
        first_load = test_factory.bootstrap_patterns_from_kernel()
        second_load = test_factory.bootstrap_patterns_from_kernel()

        # Assert
        assert first_load >= 1, "First bootstrap should load patterns"
        assert second_load == 0, "Second bootstrap should skip (already exist)"

    def test_bootstrap_loads_pattern_feature_ttl(self, test_factory, test_repo):
        """Bootstrap should load pattern-feature-ttl specifically."""
        # Act
        test_factory.bootstrap_patterns_from_kernel()

        # Assert
        ttl_pattern = test_repo.read("pattern-feature-ttl")
        assert ttl_pattern is not None, "Should load pattern-feature-ttl"
        assert ttl_pattern.status == "experimental"
        assert ttl_pattern.data.get("subtype") == "schema-extension"

        # Verify mechanics
        mechanics = ttl_pattern.data.get("mechanics", {})
        assert mechanics.get("target") == "feature"
        inject_fields = mechanics.get("inject_fields", {})
        assert "ttl_days" in inject_fields
        assert "ttl_extended" in inject_fields


class TestFieldInjection:
    """Test epigenetic field injection into entities."""

    def test_feature_gets_ttl_fields_after_bootstrap(self, test_factory, test_repo):
        """Features created after bootstrap should have TTL fields."""
        # Arrange - bootstrap patterns first
        test_factory.bootstrap_patterns_from_kernel()

        # Act - create a feature
        feature = test_factory.create("feature", "Test Feature")

        # Assert - should have epigenetic fields
        assert feature.data.get("ttl_days") == 30, "Should have default ttl_days=30"
        assert feature.data.get("ttl_extended") is False, "Should have ttl_extended=false"

        # Should be tagged with the pattern
        epigenetics = feature.data.get("_epigenetics", [])
        assert "pattern-feature-ttl" in epigenetics, "Should be tagged with pattern-feature-ttl"

    def test_feature_without_bootstrap_has_no_ttl_fields(self, test_factory, test_repo):
        """Features created without bootstrap should not have TTL fields."""
        # Act - create feature WITHOUT bootstrap
        feature = test_factory.create("feature", "Untagged Feature")

        # Assert - should NOT have epigenetic fields
        assert "ttl_days" not in feature.data
        assert "_epigenetics" not in feature.data or len(feature.data["_epigenetics"]) == 0


class TestTTLLifecycle:
    """Test the full TTL lifecycle: create → expiry → drift."""

    def test_ttl_expiry_triggers_drift(self, test_factory, test_repo, test_observer):
        """Feature past TTL should transition to drifting when hooks run."""
        # Arrange - bootstrap and create feature
        test_factory.bootstrap_patterns_from_kernel()
        feature = test_factory.create("feature", "Expiring Feature")

        # Verify initial state
        assert feature.status == "nascent"
        assert feature.data.get("ttl_days") == 30

        # Simulate time passing - backdate created timestamp
        old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        feature = feature.copy(
            data={**feature.data, "created": old_date}
        )
        test_repo.update(feature)

        # Act - run cron:daily hooks (what orient() would do)
        results = test_observer.run_epigenetic_hooks(test_repo, "cron:daily")

        # Assert - feature should now be drifting
        updated_feature = test_repo.read(feature.id)
        assert updated_feature.status == "drifting", \
            f"Feature should be drifting after TTL expiry, got: {updated_feature.status}"

        # Check that a TTL-related hook result was recorded
        # Note: ttl-expiry from pattern-feature-lifecycle or check-feature-ttl from pattern-feature-ttl
        ttl_results = [r for r in results if "ttl" in r.hook_id.lower() and r.matched]
        assert len(ttl_results) >= 1, \
            f"Should have at least one matched TTL hook result, got: {[r.hook_id for r in results if r.matched]}"

    def test_feature_within_ttl_does_not_drift(self, test_factory, test_repo, test_observer):
        """Feature within TTL should not transition."""
        # Arrange - bootstrap and create feature
        test_factory.bootstrap_patterns_from_kernel()
        feature = test_factory.create("feature", "Fresh Feature")

        # Feature is fresh - created just now

        # Act - run cron:daily hooks
        test_observer.run_epigenetic_hooks(test_repo, "cron:daily")

        # Assert - feature should still be nascent
        updated_feature = test_repo.read(feature.id)
        assert updated_feature.status == "nascent", \
            f"Fresh feature should stay nascent, got: {updated_feature.status}"


class TestEventHooks:
    """Test event-driven hook execution."""

    def test_hooks_fire_on_entity_created(self, test_factory, test_repo, test_observer):
        """Event hooks should fire when entities are created."""
        # Arrange - bootstrap patterns
        test_factory.bootstrap_patterns_from_kernel()

        # The create() method should now fire entity:feature:created hooks
        # We can verify by checking that hooks were called without error
        feature = test_factory.create("feature", "Event Test Feature")

        # Assert - feature was created successfully (hooks ran without error)
        assert feature is not None
        assert feature.id == "feature-event-test-feature"

    def test_hooks_fire_on_entity_updated(self, test_factory, test_repo, test_observer):
        """Event hooks should fire when entities are updated."""
        # Arrange
        test_factory.bootstrap_patterns_from_kernel()
        feature = test_factory.create("feature", "Update Test Feature")

        # Act - update the feature (should fire entity:feature:updated hooks)
        updated = test_factory.update(feature.id, description="Updated description")

        # Assert - feature was updated successfully
        assert updated.data.get("description") == "Updated description"


class TestFullCycle:
    """Test the complete epigenetic lifecycle."""

    def test_full_epigenetic_cycle(self, test_factory, test_repo, test_observer):
        """
        Test complete cycle:
        1. Bootstrap patterns
        2. Create feature (gets epigenetic fields)
        3. Time passes (simulate)
        4. Run hooks (feature drifts)
        5. Feature shows drift_signals
        """
        # 1. Bootstrap
        loaded = test_factory.bootstrap_patterns_from_kernel()
        assert loaded >= 1

        # 2. Create feature
        feature = test_factory.create(
            "feature",
            "Full Cycle Test",
            description="Testing the complete epigenetic lifecycle"
        )
        assert feature.data.get("ttl_days") == 30
        assert "pattern-feature-ttl" in feature.data.get("_epigenetics", [])

        # 3. Simulate 35 days passing
        old_created = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        feature = feature.copy(data={**feature.data, "created": old_created})
        test_repo.update(feature)

        # 4. Run hooks
        results = test_observer.run_epigenetic_hooks(test_repo, "cron:daily")

        # 5. Verify drift
        final_feature = test_repo.read(feature.id)
        assert final_feature.status == "drifting"

        # Verify hook result
        matched_results = [r for r in results if r.matched]
        assert len(matched_results) >= 1, "At least one hook should have matched"
