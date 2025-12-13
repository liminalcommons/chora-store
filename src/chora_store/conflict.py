"""
Conflict Resolution for chora-store sync.

Provides pluggable conflict resolution strategies for
handling concurrent modifications during sync.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Entity


class ConflictResolution(Enum):
    """How a conflict was resolved."""
    LOCAL_WINS = "local_wins"       # Keep local version
    REMOTE_WINS = "remote_wins"     # Accept remote version
    MERGED = "merged"               # Combined both versions
    DEFERRED = "deferred"           # Needs manual resolution
    SKIPPED = "skipped"             # Change was skipped


@dataclass
class Conflict:
    """
    Represents a sync conflict.

    A conflict occurs when the same entity has been modified
    on both local and remote since the last sync.
    """
    entity_id: str
    entity_type: str
    local_version: int
    remote_version: int
    local_data: Dict[str, Any]
    remote_data: Dict[str, Any]
    local_timestamp: str
    remote_timestamp: str
    local_site_id: str
    remote_site_id: str

    def __str__(self) -> str:
        return f"Conflict({self.entity_id}: local v{self.local_version} vs remote v{self.remote_version})"


@dataclass
class ConflictResult:
    """Result of conflict resolution."""
    conflict: Conflict
    resolution: ConflictResolution
    resolved_data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class ConflictResolver(ABC):
    """
    Base class for conflict resolution strategies.

    Implement resolve() to create custom conflict resolution.
    """

    @abstractmethod
    def resolve(self, conflict: Conflict) -> ConflictResult:
        """
        Resolve a sync conflict.

        Args:
            conflict: The conflict to resolve

        Returns:
            ConflictResult with resolution and resulting data
        """
        pass


class LastWriteWinsResolver(ConflictResolver):
    """
    Last-write-wins conflict resolution.

    The most recent modification (by timestamp) wins.
    This is the simplest strategy but may lose data.
    """

    def resolve(self, conflict: Conflict) -> ConflictResult:
        local_time = datetime.fromisoformat(conflict.local_timestamp.replace('Z', '+00:00'))
        remote_time = datetime.fromisoformat(conflict.remote_timestamp.replace('Z', '+00:00'))

        if local_time >= remote_time:
            return ConflictResult(
                conflict=conflict,
                resolution=ConflictResolution.LOCAL_WINS,
                resolved_data=conflict.local_data,
                message=f"Local version newer ({conflict.local_timestamp} >= {conflict.remote_timestamp})",
            )
        else:
            return ConflictResult(
                conflict=conflict,
                resolution=ConflictResolution.REMOTE_WINS,
                resolved_data=conflict.remote_data,
                message=f"Remote version newer ({conflict.remote_timestamp} > {conflict.local_timestamp})",
            )


class HigherVersionWinsResolver(ConflictResolver):
    """
    Higher version number wins.

    Simple deterministic resolution based on version numbers.
    """

    def resolve(self, conflict: Conflict) -> ConflictResult:
        if conflict.local_version >= conflict.remote_version:
            return ConflictResult(
                conflict=conflict,
                resolution=ConflictResolution.LOCAL_WINS,
                resolved_data=conflict.local_data,
                message=f"Local version higher ({conflict.local_version} >= {conflict.remote_version})",
            )
        else:
            return ConflictResult(
                conflict=conflict,
                resolution=ConflictResolution.REMOTE_WINS,
                resolved_data=conflict.remote_data,
                message=f"Remote version higher ({conflict.remote_version} > {conflict.local_version})",
            )


class MergeFieldsResolver(ConflictResolver):
    """
    Merge non-conflicting fields.

    For fields with different values:
    - Uses specified priority ('local' or 'remote')
    - Can specify field-level priorities
    """

    def __init__(
        self,
        default_priority: str = "remote",
        field_priorities: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize merge resolver.

        Args:
            default_priority: 'local' or 'remote' for conflicting fields
            field_priorities: Per-field overrides {'field': 'local' or 'remote'}
        """
        self.default_priority = default_priority
        self.field_priorities = field_priorities or {}

    def resolve(self, conflict: Conflict) -> ConflictResult:
        merged = {}
        merge_log = []

        # Get all keys from both versions
        all_keys = set(conflict.local_data.keys()) | set(conflict.remote_data.keys())

        for key in all_keys:
            local_val = conflict.local_data.get(key)
            remote_val = conflict.remote_data.get(key)

            if local_val == remote_val:
                # No conflict
                merged[key] = local_val
            elif local_val is None:
                # Only in remote
                merged[key] = remote_val
                merge_log.append(f"{key}: added from remote")
            elif remote_val is None:
                # Only in local
                merged[key] = local_val
                merge_log.append(f"{key}: kept from local")
            else:
                # Conflict - use priority
                priority = self.field_priorities.get(key, self.default_priority)
                if priority == "local":
                    merged[key] = local_val
                    merge_log.append(f"{key}: local wins")
                else:
                    merged[key] = remote_val
                    merge_log.append(f"{key}: remote wins")

        return ConflictResult(
            conflict=conflict,
            resolution=ConflictResolution.MERGED,
            resolved_data=merged,
            message="; ".join(merge_log) if merge_log else "No conflicts",
        )


class DeferResolver(ConflictResolver):
    """
    Defer conflict resolution.

    Marks conflicts for manual resolution later.
    Useful when automatic resolution isn't appropriate.
    """

    def resolve(self, conflict: Conflict) -> ConflictResult:
        return ConflictResult(
            conflict=conflict,
            resolution=ConflictResolution.DEFERRED,
            resolved_data=None,
            message="Conflict deferred for manual resolution",
        )


class CallbackResolver(ConflictResolver):
    """
    Custom callback-based resolution.

    Allows arbitrary conflict resolution logic via a callback function.
    """

    def __init__(self, callback: Callable[[Conflict], ConflictResult]):
        """
        Initialize with callback.

        Args:
            callback: Function that takes Conflict and returns ConflictResult
        """
        self.callback = callback

    def resolve(self, conflict: Conflict) -> ConflictResult:
        return self.callback(conflict)


class ConflictQueue:
    """
    Queue for tracking and managing deferred conflicts.

    Use this to collect conflicts that need manual resolution.
    """

    def __init__(self):
        self._conflicts: List[Conflict] = []
        self._resolved: List[ConflictResult] = []

    def add(self, conflict: Conflict) -> None:
        """Add a conflict to the queue."""
        self._conflicts.append(conflict)

    def pending(self) -> List[Conflict]:
        """Get pending conflicts."""
        return list(self._conflicts)

    def resolve(self, conflict: Conflict, resolution: ConflictResolution, data: Dict[str, Any]) -> ConflictResult:
        """
        Mark a conflict as resolved.

        Args:
            conflict: The conflict to resolve
            resolution: How it was resolved
            data: The resolved data

        Returns:
            ConflictResult
        """
        result = ConflictResult(
            conflict=conflict,
            resolution=resolution,
            resolved_data=data,
        )
        self._conflicts.remove(conflict)
        self._resolved.append(result)
        return result

    def resolved(self) -> List[ConflictResult]:
        """Get resolved conflicts."""
        return list(self._resolved)

    def clear(self) -> None:
        """Clear all conflicts."""
        self._conflicts.clear()
        self._resolved.clear()

    def __len__(self) -> int:
        return len(self._conflicts)


def detect_conflict(
    entity_id: str,
    local_entity: "Entity",
    remote_data: Dict[str, Any],
    local_site_id: str,
    remote_site_id: str,
    remote_timestamp: str,
) -> Optional[Conflict]:
    """
    Detect if there's a conflict between local and remote versions.

    Args:
        entity_id: Entity ID
        local_entity: Local entity
        remote_data: Remote entity data
        local_site_id: Local site identifier
        remote_site_id: Remote site identifier
        remote_timestamp: Remote modification timestamp

    Returns:
        Conflict if detected, None otherwise
    """
    local_data = local_entity.to_dict()
    remote_version = remote_data.get("version", 0)

    # No conflict if same version or remote is older
    if remote_version <= local_entity.version:
        return None

    # No conflict if data is identical
    if local_data == remote_data:
        return None

    return Conflict(
        entity_id=entity_id,
        entity_type=local_entity.type,
        local_version=local_entity.version,
        remote_version=remote_version,
        local_data=local_data,
        remote_data=remote_data,
        local_timestamp=local_entity.updated_at or local_entity.created_at,
        remote_timestamp=remote_timestamp,
        local_site_id=local_site_id,
        remote_site_id=remote_site_id,
    )
