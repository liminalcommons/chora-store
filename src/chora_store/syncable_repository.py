"""
SyncableRepository - Entity repository with CRDT sync support.

Wraps EntityRepository to record changes for sync between databases.
Uses chora-sync's ChangeTracker for vector clock-based CRDT sync.
"""

import json
from typing import List, Optional, TYPE_CHECKING

from .repository import EntityRepository
from .models import Entity

# Try to import sync components
try:
    from chora_sync import (
        ChangeTracker,
        ChangeType,
        Change,
        DatabaseMerger,
        MergeResult,
    )
    SYNC_AVAILABLE = True
except ImportError:
    SYNC_AVAILABLE = False
    ChangeTracker = None
    ChangeType = None
    Change = None
    DatabaseMerger = None
    MergeResult = None


class SyncNotAvailable(Exception):
    """Raised when chora-sync is not installed."""
    pass


class SyncableRepository:
    """
    Entity repository with sync support.

    Wraps an EntityRepository and records all changes for CRDT sync.
    Changes are tracked using vector clocks for conflict-free merging.

    Example:
        repo = EntityRepository(db_path="local.db")
        sync_repo = SyncableRepository(repo, site_id="laptop-001")

        # Use like normal repository
        entity = sync_repo.create(Entity(...))

        # Later, sync with another database
        remote_repo = SyncableRepository(...)
        result = sync_repo.sync_with(remote_repo)
    """

    def __init__(self, repo: EntityRepository, site_id: str):
        """
        Initialize syncable repository.

        Args:
            repo: Underlying EntityRepository
            site_id: Unique identifier for this site (e.g., "laptop-001")

        Raises:
            SyncNotAvailable: If chora-sync is not installed
        """
        if not SYNC_AVAILABLE:
            raise SyncNotAvailable(
                "chora-sync is not installed. Install it with: pip install chora-sync"
            )

        self.repo = repo
        self.site_id = site_id
        self.tracker = ChangeTracker(str(repo.db_path), site_id)
        self._merger = DatabaseMerger(self.tracker)

    def create(self, entity: Entity) -> Entity:
        """
        Create an entity and record for sync.

        Args:
            entity: Entity to create

        Returns:
            Created entity with version
        """
        created = self.repo.create(entity)

        # Record change for sync
        self.tracker.record_change(
            entity_id=created.id,
            change_type=ChangeType.INSERT,
            table_name="entities",
            value=json.dumps(created.to_dict()),
        )

        return created

    def read(self, entity_id: str) -> Optional[Entity]:
        """
        Read an entity by ID.

        Args:
            entity_id: Entity ID to read

        Returns:
            Entity if found, None otherwise
        """
        return self.repo.read(entity_id)

    def update(self, entity: Entity) -> Entity:
        """
        Update an entity and record for sync.

        Args:
            entity: Entity with changes

        Returns:
            Updated entity with incremented version
        """
        updated = self.repo.update(entity)

        # Record change for sync
        self.tracker.record_change(
            entity_id=updated.id,
            change_type=ChangeType.UPDATE,
            table_name="entities",
            value=json.dumps(updated.to_dict()),
        )

        return updated

    def delete(self, entity_id: str) -> bool:
        """
        Delete an entity and record for sync.

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Get entity before delete for sync record
        entity = self.repo.read(entity_id)
        if entity is None:
            return False

        result = self.repo.delete(entity_id)

        if result:
            # Record deletion for sync
            self.tracker.record_change(
                entity_id=entity_id,
                change_type=ChangeType.DELETE,
                table_name="entities",
                value=json.dumps(entity.to_dict()),
            )

        return result

    def list(
        self,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """
        List entities with optional filters.

        Args:
            entity_type: Filter by type
            status: Filter by status
            limit: Maximum entities to return
            offset: Number to skip

        Returns:
            List of matching entities
        """
        return self.repo.list(
            entity_type=entity_type,
            status=status,
            limit=limit,
            offset=offset,
        )

    def search(self, query: str, limit: int = 20) -> List[Entity]:
        """
        Full-text search across entities.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching entities
        """
        return self.repo.search(query, limit=limit)

    # Sync operations

    def get_pending_changes(self, since_version: int = 0) -> List[Change]:
        """
        Get changes since a version for sync.

        Args:
            since_version: Get changes after this version

        Returns:
            List of changes
        """
        return self.tracker.get_changes_since(since_version)

    def get_current_version(self) -> int:
        """Get the current sync version."""
        return self.tracker.get_current_version()

    def sync_with(self, remote: "SyncableRepository") -> MergeResult:
        """
        Bidirectional sync with another repository.

        Exchanges changes between both repos and applies entity changes.

        Args:
            remote: Remote SyncableRepository to sync with

        Returns:
            MergeResult with statistics
        """
        remote_site_id = remote.site_id
        local_site_id = self.site_id

        # Get changes to send to remote
        last_remote_version = self.tracker.get_site_version(remote_site_id)
        changes_to_send = self.tracker.get_changes_since(last_remote_version)
        changes_to_send = [c for c in changes_to_send if c.site_id != remote_site_id]
        local_version = self.tracker.get_current_version()

        # Get changes from remote
        last_local_version_at_remote = remote.tracker.get_site_version(local_site_id)
        remote_changes = remote.tracker.get_changes_since(last_local_version_at_remote)
        remote_changes = [c for c in remote_changes if c.site_id != local_site_id]
        remote_version = remote.tracker.get_current_version()

        # Apply remote changes locally (both to tracker and entity repo)
        local_applied = 0
        local_errors = []
        for change in remote_changes:
            try:
                if self.tracker.apply_remote_change(change):
                    self._apply_entity_change(change)
                    local_applied += 1
            except Exception as e:
                local_errors.append(f"Error applying remote change {change.entity_id}: {e}")

        # Apply local changes to remote (both to tracker and entity repo)
        remote_applied = 0
        remote_errors = []
        for change in changes_to_send:
            try:
                if remote.tracker.apply_remote_change(change):
                    remote._apply_entity_change(change)
                    remote_applied += 1
            except Exception as e:
                remote_errors.append(f"Error applying local change {change.entity_id}: {e}")

        # Update version bookkeeping
        # Track what version each site has seen from us
        self.tracker.update_site_version(remote_site_id, local_version)
        remote.tracker.update_site_version(local_site_id, remote_version)

        return MergeResult(
            changes_sent=len(changes_to_send),
            changes_received=local_applied,
            conflicts_resolved=0,
            errors=local_errors + [f"Remote: {e}" for e in remote_errors],
        )

    def apply_remote_changes(
        self,
        changes: List[Change],
        remote_site_id: str,
        remote_version: int,
    ) -> MergeResult:
        """
        Apply changes received from a remote site.

        For one-way sync or custom sync protocols.

        Args:
            changes: Changes from remote
            remote_site_id: ID of remote site
            remote_version: Current version at remote

        Returns:
            MergeResult with statistics
        """
        result = self._merger.apply_remote_changes(
            changes, remote_site_id, remote_version
        )

        # Apply entity changes to local repository
        for change in changes:
            self._apply_entity_change(change)

        return result

    def _apply_entity_change(self, change: Change) -> None:
        """
        Apply a sync change to the entity repository.

        Args:
            change: Change to apply
        """
        if change.table_name != "entities":
            return  # Only handle entity changes

        if change.value is None:
            return

        data = json.loads(change.value)

        if change.change_type == ChangeType.INSERT:
            entity = Entity.from_dict(data)
            # Check if already exists (from previous sync)
            existing = self.repo.read(entity.id)
            if existing is None:
                try:
                    self.repo.create(entity)
                except Exception:
                    pass  # Entity may already exist

        elif change.change_type == ChangeType.UPDATE:
            entity = Entity.from_dict(data)
            existing = self.repo.read(entity.id)
            if existing:
                # Only update if remote version is newer
                if entity.version > existing.version:
                    try:
                        # Update with correct version for optimistic lock
                        updated = entity.copy(version=existing.version)
                        self.repo.update(updated)
                    except Exception:
                        pass  # Version conflict handled by CRDT

        elif change.change_type == ChangeType.DELETE:
            self.repo.delete(data.get("id", ""))
