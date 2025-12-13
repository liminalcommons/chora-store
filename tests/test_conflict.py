"""
Tests for conflict resolution module.
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chora_store.conflict import (
    Conflict,
    ConflictResult,
    ConflictResolution,
    ConflictResolver,
    LastWriteWinsResolver,
    HigherVersionWinsResolver,
    MergeFieldsResolver,
    DeferResolver,
    CallbackResolver,
    ConflictQueue,
    detect_conflict,
)
from chora_store.models import Entity


class TestConflict:
    """Tests for Conflict dataclass."""

    def test_conflict_creation(self):
        """Test creating a conflict."""
        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T11:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        assert conflict.entity_id == "entity-123"
        assert conflict.local_version == 1
        assert conflict.remote_version == 2

    def test_conflict_str(self):
        """Test conflict string representation."""
        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=5,
            remote_version=7,
            local_data={},
            remote_data={},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T11:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        assert "entity-123" in str(conflict)
        assert "v5" in str(conflict)
        assert "v7" in str(conflict)


class TestConflictResult:
    """Tests for ConflictResult."""

    def test_result_creation(self):
        """Test creating a conflict result."""
        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T11:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = ConflictResult(
            conflict=conflict,
            resolution=ConflictResolution.LOCAL_WINS,
            resolved_data={"name": "Local"},
            message="Local version kept",
        )

        assert result.resolution == ConflictResolution.LOCAL_WINS
        assert result.resolved_data["name"] == "Local"


class TestLastWriteWinsResolver:
    """Tests for LastWriteWinsResolver."""

    def test_local_wins_when_newer(self):
        """Test local wins when timestamp is newer."""
        resolver = LastWriteWinsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T12:00:00Z",  # Newer
            remote_timestamp="2024-01-01T10:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.LOCAL_WINS
        assert result.resolved_data == {"name": "Local"}

    def test_remote_wins_when_newer(self):
        """Test remote wins when timestamp is newer."""
        resolver = LastWriteWinsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=2,
            remote_version=1,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",  # Newer
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.REMOTE_WINS
        assert result.resolved_data == {"name": "Remote"}

    def test_local_wins_on_tie(self):
        """Test local wins when timestamps are equal."""
        resolver = LastWriteWinsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=1,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T10:00:00Z",  # Same
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.LOCAL_WINS


class TestHigherVersionWinsResolver:
    """Tests for HigherVersionWinsResolver."""

    def test_local_wins_with_higher_version(self):
        """Test local wins with higher version."""
        resolver = HigherVersionWinsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=5,  # Higher
            remote_version=3,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.LOCAL_WINS
        assert result.resolved_data == {"name": "Local"}

    def test_remote_wins_with_higher_version(self):
        """Test remote wins with higher version."""
        resolver = HigherVersionWinsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=3,
            remote_version=5,  # Higher
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T12:00:00Z",
            remote_timestamp="2024-01-01T10:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.REMOTE_WINS
        assert result.resolved_data == {"name": "Remote"}


class TestMergeFieldsResolver:
    """Tests for MergeFieldsResolver."""

    def test_merge_non_conflicting_fields(self):
        """Test merging when fields don't conflict."""
        resolver = MergeFieldsResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Test", "status": "local-status"},
            remote_data={"name": "Test", "priority": "high"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.MERGED
        assert result.resolved_data["name"] == "Test"
        assert result.resolved_data["status"] == "local-status"
        assert result.resolved_data["priority"] == "high"

    def test_merge_with_remote_priority(self):
        """Test merge with remote priority for conflicts."""
        resolver = MergeFieldsResolver(default_priority="remote")

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.MERGED
        assert result.resolved_data["name"] == "Remote Name"

    def test_merge_with_local_priority(self):
        """Test merge with local priority for conflicts."""
        resolver = MergeFieldsResolver(default_priority="local")

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.MERGED
        assert result.resolved_data["name"] == "Local Name"

    def test_merge_with_field_priorities(self):
        """Test merge with per-field priorities."""
        resolver = MergeFieldsResolver(
            default_priority="remote",
            field_priorities={"status": "local"},  # Status always local
        )

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local Name", "status": "local-status"},
            remote_data={"name": "Remote Name", "status": "remote-status"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.MERGED
        assert result.resolved_data["name"] == "Remote Name"  # Remote priority
        assert result.resolved_data["status"] == "local-status"  # Local override


class TestDeferResolver:
    """Tests for DeferResolver."""

    def test_defer_resolution(self):
        """Test deferring conflict resolution."""
        resolver = DeferResolver()

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.DEFERRED
        assert result.resolved_data is None


class TestCallbackResolver:
    """Tests for CallbackResolver."""

    def test_callback_resolution(self):
        """Test custom callback resolution."""

        def custom_resolve(conflict: Conflict) -> ConflictResult:
            # Custom logic: always prefer the one with longer name
            local_name = conflict.local_data.get("name", "")
            remote_name = conflict.remote_data.get("name", "")

            if len(local_name) >= len(remote_name):
                return ConflictResult(
                    conflict=conflict,
                    resolution=ConflictResolution.LOCAL_WINS,
                    resolved_data=conflict.local_data,
                )
            else:
                return ConflictResult(
                    conflict=conflict,
                    resolution=ConflictResolution.REMOTE_WINS,
                    resolved_data=conflict.remote_data,
                )

        resolver = CallbackResolver(custom_resolve)

        conflict = Conflict(
            entity_id="entity-123",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Short"},
            remote_data={"name": "Much Longer Name"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        result = resolver.resolve(conflict)

        assert result.resolution == ConflictResolution.REMOTE_WINS
        assert result.resolved_data["name"] == "Much Longer Name"


class TestConflictQueue:
    """Tests for ConflictQueue."""

    def test_add_and_pending(self):
        """Test adding conflicts and getting pending."""
        queue = ConflictQueue()

        conflict1 = Conflict(
            entity_id="entity-1",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={},
            remote_data={},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        conflict2 = Conflict(
            entity_id="entity-2",
            entity_type="task",
            local_version=3,
            remote_version=4,
            local_data={},
            remote_data={},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        queue.add(conflict1)
        queue.add(conflict2)

        assert len(queue) == 2
        assert len(queue.pending()) == 2

    def test_resolve_conflict(self):
        """Test resolving a conflict from the queue."""
        queue = ConflictQueue()

        conflict = Conflict(
            entity_id="entity-1",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        queue.add(conflict)
        assert len(queue) == 1

        result = queue.resolve(
            conflict,
            ConflictResolution.LOCAL_WINS,
            {"name": "Local"},
        )

        assert len(queue) == 0
        assert len(queue.resolved()) == 1
        assert result.resolution == ConflictResolution.LOCAL_WINS

    def test_clear_queue(self):
        """Test clearing the queue."""
        queue = ConflictQueue()

        conflict = Conflict(
            entity_id="entity-1",
            entity_type="feature",
            local_version=1,
            remote_version=2,
            local_data={},
            remote_data={},
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T12:00:00Z",
            local_site_id="site-001",
            remote_site_id="site-002",
        )

        queue.add(conflict)
        queue.clear()

        assert len(queue) == 0
        assert len(queue.resolved()) == 0


class TestDetectConflict:
    """Tests for detect_conflict function."""

    def test_no_conflict_same_data(self):
        """Test no conflict when data is identical."""
        entity = Entity(
            id="feature-123",
            type="feature",
            status="active",
            data={"name": "Test"},
            version=1,
        )

        result = detect_conflict(
            entity_id="feature-123",
            local_entity=entity,
            remote_data=entity.to_dict(),
            local_site_id="site-001",
            remote_site_id="site-002",
            remote_timestamp="2024-01-01T12:00:00Z",
        )

        assert result is None

    def test_no_conflict_older_remote(self):
        """Test no conflict when remote is older."""
        entity = Entity(
            id="feature-123",
            type="feature",
            status="active",
            data={"name": "Test"},
            version=5,
        )

        remote_data = entity.to_dict()
        remote_data["version"] = 3  # Older
        remote_data["name"] = "Different"

        result = detect_conflict(
            entity_id="feature-123",
            local_entity=entity,
            remote_data=remote_data,
            local_site_id="site-001",
            remote_site_id="site-002",
            remote_timestamp="2024-01-01T12:00:00Z",
        )

        assert result is None

    def test_conflict_detected(self):
        """Test conflict detection with different data."""
        entity = Entity(
            id="feature-123",
            type="feature",
            status="active",
            data={"name": "Local"},
            version=1,
        )

        remote_data = entity.to_dict()
        remote_data["version"] = 2  # Newer
        remote_data["data"] = {"name": "Remote"}  # Different

        result = detect_conflict(
            entity_id="feature-123",
            local_entity=entity,
            remote_data=remote_data,
            local_site_id="site-001",
            remote_site_id="site-002",
            remote_timestamp="2024-01-01T12:00:00Z",
        )

        assert result is not None
        assert result.entity_id == "feature-123"
        assert result.local_version == 1
        assert result.remote_version == 2
