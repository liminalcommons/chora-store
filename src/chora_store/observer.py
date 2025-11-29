"""
EntityObserver - Stigmergic coordination via events.

Agents communicate through the environment, not direct messages.
The observer emits events when entities change, allowing other
agents/processes to react.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional
from enum import Enum

from .models import Entity


class ChangeType(Enum):
    """Types of entity changes."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class EntityEvent:
    """
    An event representing an entity change.

    This is the stigmergic signal - the mark left in the environment
    that other agents can observe and react to.
    """
    entity_id: str
    entity_type: str
    change_type: ChangeType
    timestamp: datetime
    entity: Optional[Entity] = None  # None for deletes
    old_status: Optional[str] = None  # For updates
    new_status: Optional[str] = None  # For updates and creates


# Type for event callbacks
EventCallback = Callable[[EntityEvent], None]


class EntityObserver:
    """
    Stigmergic observation: Watch for environment changes.

    This implements the Environment pillar of the Autopoietic Workspace.
    Agents leave marks (create/update entities). Other agents observe
    these marks and react.

    Usage:
        observer = EntityObserver()

        # Register callback
        observer.on_change(lambda event: print(f"Entity {event.entity_id} {event.change_type}"))

        # Emit events (called by factory/repository)
        observer.emit(ChangeType.CREATED, entity)
    """

    def __init__(self):
        """Initialize observer with empty callback list."""
        self._callbacks: List[EventCallback] = []
        self._event_log: List[EntityEvent] = []
        self._max_log_size = 1000

    def on_change(self, callback: EventCallback) -> None:
        """
        Register callback for entity changes.

        Args:
            callback: Function to call when entity changes
        """
        self._callbacks.append(callback)

    def off_change(self, callback: EventCallback) -> None:
        """
        Unregister callback.

        Args:
            callback: Function to remove
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(
        self,
        change_type: ChangeType,
        entity: Entity,
        old_status: Optional[str] = None,
    ) -> EntityEvent:
        """
        Emit an event for an entity change.

        This is the stigmergic signal - the mark left in the environment.

        Args:
            change_type: Type of change (created, updated, deleted)
            entity: The entity that changed
            old_status: Previous status (for updates)

        Returns:
            The emitted event
        """
        event = EntityEvent(
            entity_id=entity.id,
            entity_type=entity.type,
            change_type=change_type,
            timestamp=datetime.utcnow(),
            entity=entity if change_type != ChangeType.DELETED else None,
            old_status=old_status,
            new_status=entity.status,
        )

        # Log event
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                # Don't let callback errors stop other callbacks
                print(f"Warning: Event callback error: {e}")

        return event

    def get_recent_events(
        self,
        entity_type: Optional[str] = None,
        change_type: Optional[ChangeType] = None,
        limit: int = 50,
    ) -> List[EntityEvent]:
        """
        Get recent events from the log.

        Args:
            entity_type: Filter by entity type
            change_type: Filter by change type
            limit: Maximum events to return

        Returns:
            List of matching events, most recent first
        """
        events = self._event_log

        if entity_type:
            events = [e for e in events if e.entity_type == entity_type]

        if change_type:
            events = [e for e in events if e.change_type == change_type]

        return list(reversed(events))[:limit]

    def clear_log(self) -> None:
        """Clear the event log."""
        self._event_log = []


# Global observer singleton for convenience
_global_observer: Optional[EntityObserver] = None


def get_observer() -> EntityObserver:
    """Get the global observer instance."""
    global _global_observer
    if _global_observer is None:
        _global_observer = EntityObserver()
    return _global_observer
