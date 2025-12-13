"""
Tests for SyncableRepository.
"""

import pytest
import tempfile
import os
import sys

# Add chora-sync to path for testing
sync_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "chora-sync", "src"
)
if os.path.exists(sync_path):
    sys.path.insert(0, sync_path)

from chora_store.repository import EntityRepository
from chora_store.models import Entity

# Try to import sync components
try:
    from chora_store.syncable_repository import (
        SyncableRepository,
        SyncNotAvailable,
        SYNC_AVAILABLE,
    )
    from chora_sync import ChangeType
except ImportError:
    SYNC_AVAILABLE = False


# Skip all tests if sync not available
pytestmark = pytest.mark.skipif(
    not SYNC_AVAILABLE,
    reason="chora-sync not available"
)


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def temp_db_pair():
    """Create two temporary databases for sync testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f1:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f2:
            yield f1.name, f2.name
    os.unlink(f1.name)
    os.unlink(f2.name)


@pytest.fixture
def repo(temp_db):
    """Create base repository."""
    return EntityRepository(db_path=temp_db)


@pytest.fixture
def sync_repo(repo):
    """Create syncable repository."""
    return SyncableRepository(repo, site_id="test-site-001")


def make_entity(id: str = "feature-test", **kwargs) -> Entity:
    """Helper to create test entities."""
    defaults = {
        "type": "feature",
        "status": "planned",
        "data": {"name": "Test Feature", "description": "A test"},
    }
    defaults.update(kwargs)
    return Entity(id=id, **defaults)


class TestSyncableCRUD:
    """Test CRUD operations with sync tracking."""

    def test_create_records_change(self, sync_repo):
        """Create records a change for sync."""
        entity = make_entity()
        created = sync_repo.create(entity)

        assert created.version == 1

        # Should have recorded a change
        changes = sync_repo.get_pending_changes()
        assert len(changes) == 1
        assert changes[0].entity_id == entity.id
        assert changes[0].change_type == ChangeType.INSERT

    def test_read_no_change(self, sync_repo):
        """Read does not record changes."""
        entity = make_entity()
        sync_repo.create(entity)
        version_before = sync_repo.get_current_version()

        sync_repo.read(entity.id)

        version_after = sync_repo.get_current_version()
        assert version_after == version_before

    def test_update_records_change(self, sync_repo):
        """Update records a change for sync."""
        entity = make_entity()
        created = sync_repo.create(entity)

        updated = sync_repo.update(
            created.copy(data={"name": "Updated"})
        )

        changes = sync_repo.get_pending_changes()
        assert len(changes) == 2  # create + update
        assert changes[1].change_type == ChangeType.UPDATE

    def test_delete_records_change(self, sync_repo):
        """Delete records a change for sync."""
        entity = make_entity()
        sync_repo.create(entity)

        result = sync_repo.delete(entity.id)
        assert result is True

        changes = sync_repo.get_pending_changes()
        assert len(changes) == 2  # create + delete
        assert changes[1].change_type == ChangeType.DELETE

    def test_list_works(self, sync_repo):
        """List operations work through wrapper."""
        sync_repo.create(make_entity("feature-one"))
        sync_repo.create(make_entity("feature-two"))

        entities = sync_repo.list()
        assert len(entities) == 2

    def test_search_works(self, sync_repo):
        """Search operations work through wrapper."""
        sync_repo.create(make_entity("feature-test", data={"name": "Unique Name"}))

        results = sync_repo.search("Unique")
        assert len(results) == 1


class TestBidirectionalSync:
    """Test bidirectional sync between repositories."""

    def test_sync_sends_local_changes(self, temp_db_pair):
        """Local changes are sent to remote."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        # Create entity on site 1
        entity = make_entity()
        repo1.create(entity)

        # Sync
        result = repo1.sync_with(repo2)

        assert result.success
        assert result.changes_sent == 1
        assert result.changes_received == 0

    def test_sync_receives_remote_changes(self, temp_db_pair):
        """Remote changes are received locally."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        # Create entity on site 2
        entity = make_entity()
        repo2.create(entity)

        # Sync from site 1's perspective
        result = repo1.sync_with(repo2)

        assert result.success
        assert result.changes_sent == 0
        assert result.changes_received == 1

    def test_sync_bidirectional(self, temp_db_pair):
        """Both sides exchange changes."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        # Create on both sites
        repo1.create(make_entity("feature-one"))
        repo2.create(make_entity("feature-two"))

        # Sync
        result = repo1.sync_with(repo2)

        assert result.success
        assert result.changes_sent == 1
        assert result.changes_received == 1

    def test_sync_idempotent(self, temp_db_pair):
        """Syncing twice doesn't duplicate changes."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        repo1.create(make_entity())

        # Sync twice
        result1 = repo1.sync_with(repo2)
        result2 = repo1.sync_with(repo2)

        assert result1.changes_sent == 1
        assert result2.changes_sent == 0  # Already synced


class TestChangeTracking:
    """Test change tracking details."""

    def test_version_increments(self, sync_repo):
        """Version increments with each change."""
        v0 = sync_repo.get_current_version()
        sync_repo.create(make_entity("feature-one"))
        v1 = sync_repo.get_current_version()
        sync_repo.create(make_entity("feature-two"))
        v2 = sync_repo.get_current_version()

        assert v1 > v0
        assert v2 > v1

    def test_changes_since_version(self, sync_repo):
        """Can get changes since a specific version."""
        sync_repo.create(make_entity("feature-one"))
        v1 = sync_repo.get_current_version()

        sync_repo.create(make_entity("feature-two"))
        sync_repo.create(make_entity("feature-three"))

        # Get only changes after v1
        changes = sync_repo.get_pending_changes(since_version=v1)
        assert len(changes) == 2

    def test_change_has_site_id(self, sync_repo):
        """Changes record the site ID."""
        sync_repo.create(make_entity())

        changes = sync_repo.get_pending_changes()
        assert changes[0].site_id == "test-site-001"

    def test_change_has_entity_data(self, sync_repo):
        """Changes include full entity data."""
        import json

        entity = make_entity(data={"secret": "value"})
        sync_repo.create(entity)

        changes = sync_repo.get_pending_changes()
        change_data = json.loads(changes[0].value)

        assert change_data["data"]["secret"] == "value"


class TestApplyRemoteChanges:
    """Test applying remote changes."""

    def test_apply_insert(self, temp_db_pair):
        """Can apply remote insert."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        # Create on site 1
        repo1.create(make_entity("feature-test"))

        # Get changes and apply to site 2
        changes = repo1.get_pending_changes()
        repo2.apply_remote_changes(changes, "site-001", repo1.get_current_version())

        # Entity should exist on site 2
        entity = repo2.read("feature-test")
        assert entity is not None

    def test_apply_delete(self, temp_db_pair):
        """Can apply remote delete."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        # Create on both sites (simulate already synced)
        entity = make_entity()
        repo1.create(entity)
        repo2.create(entity)

        # Record baseline version before delete
        baseline_version = repo1.get_current_version()

        # Delete on site 1
        repo1.delete(entity.id)

        # Get changes since baseline (should include the delete)
        changes = repo1.get_pending_changes(since_version=baseline_version)
        delete_changes = [c for c in changes if c.change_type == ChangeType.DELETE]

        assert len(delete_changes) == 1, f"Expected 1 delete change, got {len(delete_changes)}"

        repo2.apply_remote_changes(delete_changes, "site-001", repo1.get_current_version())

        # Entity should be gone from site 2
        assert repo2.read(entity.id) is None


class TestEdgeCases:
    """Edge case tests."""

    def test_sync_empty_repos(self, temp_db_pair):
        """Can sync empty repositories."""
        db1, db2 = temp_db_pair

        repo1 = SyncableRepository(EntityRepository(db_path=db1), "site-001")
        repo2 = SyncableRepository(EntityRepository(db_path=db2), "site-002")

        result = repo1.sync_with(repo2)

        assert result.success
        assert result.changes_sent == 0
        assert result.changes_received == 0

    def test_delete_nonexistent_no_change(self, sync_repo):
        """Deleting nonexistent entity doesn't record change."""
        version_before = sync_repo.get_current_version()

        result = sync_repo.delete("nonexistent-id")

        assert result is False
        assert sync_repo.get_current_version() == version_before
