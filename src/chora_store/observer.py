"""
EntityObserver - Stigmergic coordination via events.

Agents communicate through the environment, not direct messages.
The observer emits events when entities change, allowing other
agents/processes to react.

EPIGENETIC BRIDGE:
The observer now supports running "epigenetic hooks" - conditional
actions defined in experimental schema-extension patterns. These
hooks modulate system behavior without changing the kernel physics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any, TYPE_CHECKING
from enum import Enum
import re

from .models import Entity

if TYPE_CHECKING:
    from .repository import EntityRepository


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


@dataclass
class EpigeneticHook:
    """
    A hook from an experimental schema-extension pattern.

    Hooks define conditional actions that modulate system behavior.
    They are the "gene expression" mechanism of the epigenetic bridge.
    """
    hook_id: str
    pattern_id: str
    trigger: str  # e.g., "cron:daily", "event:entity.created"
    condition: str  # Expression to evaluate
    action: str  # Action to execute
    target_type: str  # Entity type this hook targets


@dataclass
class HookResult:
    """Result of running an epigenetic hook."""
    hook_id: str
    pattern_id: str
    entity_id: str
    matched: bool
    action_taken: Optional[str] = None
    error: Optional[str] = None


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

    # ═══════════════════════════════════════════════════════════════════════════
    # EPIGENETIC BRIDGE - Hook Evaluation and Execution
    # ═══════════════════════════════════════════════════════════════════════════

    def load_epigenetic_hooks(
        self,
        repository: "EntityRepository",
        trigger_type: str = "cron:daily",
    ) -> List[EpigeneticHook]:
        """
        Load hooks from experimental schema-extension patterns.

        Args:
            repository: EntityRepository to query patterns from
            trigger_type: Only load hooks with this trigger type

        Returns:
            List of EpigeneticHook objects
        """
        hooks = []
        try:
            patterns = repository.list(entity_type="pattern", limit=100)
            for pattern in patterns:
                # Only experimental schema-extension patterns
                if pattern.status != "experimental":
                    continue
                subtype = pattern.data.get("subtype")
                if subtype != "schema-extension":
                    continue

                # Extract mechanics
                mechanics = pattern.data.get("mechanics", {})
                target_type = mechanics.get("target")
                if not target_type:
                    continue

                # Extract hooks
                pattern_hooks = mechanics.get("hooks", [])
                for hook_def in pattern_hooks:
                    hook_trigger = hook_def.get("trigger", "")
                    if trigger_type and hook_trigger != trigger_type:
                        continue

                    hooks.append(EpigeneticHook(
                        hook_id=hook_def.get("id", "unknown"),
                        pattern_id=pattern.id,
                        trigger=hook_trigger,
                        condition=hook_def.get("condition", ""),
                        action=hook_def.get("action", ""),
                        target_type=target_type,
                    ))
        except Exception:
            # Repository not ready or other error
            pass

        return hooks

    def _evaluate_condition(
        self,
        condition: str,
        entity: Entity,
    ) -> bool:
        """
        Evaluate a hook condition against an entity.

        The condition is a simple expression language:
        - entity.type, entity.status, entity.id
        - entity.{field} for data fields
        - days_since(entity.created) for time calculations
        - ==, !=, <, >, AND, OR operators

        Args:
            condition: Condition expression string
            entity: Entity to evaluate against

        Returns:
            True if condition matches, False otherwise
        """
        try:
            # Build evaluation context
            ctx: Dict[str, Any] = {
                "entity_type": entity.type,
                "entity_status": entity.status,
                "entity_id": entity.id,
            }

            # Add data fields
            for key, value in entity.data.items():
                ctx[f"entity_{key}"] = value

            # Calculate days_since for time fields
            now = datetime.utcnow()
            created_str = entity.data.get("created")
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    ctx["days_since_created"] = (now - created.replace(tzinfo=None)).days
                except (ValueError, AttributeError):
                    ctx["days_since_created"] = 0

            # Normalize condition string
            cond = condition.strip()
            # Replace entity.field with entity_field
            cond = re.sub(r"entity\.(\w+)", r"entity_\1", cond)
            # Replace days_since(entity.created) with days_since_created
            cond = re.sub(r"days_since\(entity\.created\)", "days_since_created", cond)
            cond = re.sub(r"days_since\(entity_created\)", "days_since_created", cond)

            # Simple expression evaluation
            # Replace AND/OR with Python equivalents
            cond = cond.replace(" AND ", " and ").replace(" OR ", " or ")
            cond = cond.replace("\n", " ")

            # Evaluate (restricted eval with only our context)
            return bool(eval(cond, {"__builtins__": {}}, ctx))

        except Exception as e:
            # Condition evaluation failed - treat as not matching
            return False

    def _execute_action(
        self,
        action: str,
        entity: Entity,
        repository: "EntityRepository",
    ) -> str:
        """
        Execute a hook action on an entity.

        Supported actions:
        - transition(status='new_status')

        Args:
            action: Action expression string
            entity: Entity to act on
            repository: Repository for persistence

        Returns:
            Description of action taken
        """
        action = action.strip()

        # Parse transition action
        transition_match = re.match(r"transition\(status=['\"](\w+)['\"]\)", action)
        if transition_match:
            new_status = transition_match.group(1)
            old_status = entity.status

            # Update entity via repository
            updated_data = dict(entity.data)
            updated_data["updated"] = datetime.utcnow().isoformat()
            updated_entity = entity.copy(status=new_status, data=updated_data)
            repository.update(updated_entity)

            # Emit transition event
            self.emit(ChangeType.UPDATED, updated_entity, old_status=old_status)

            return f"Transitioned from '{old_status}' to '{new_status}'"

        return f"Unknown action: {action}"

    def run_epigenetic_hooks(
        self,
        repository: "EntityRepository",
        trigger_type: str = "cron:daily",
    ) -> List[HookResult]:
        """
        Run all epigenetic hooks for a given trigger type.

        This is the main entry point for the epigenetic bridge runtime.
        Call this during orient() or on a schedule to evaluate and
        execute hooks from experimental patterns.

        Args:
            repository: EntityRepository for queries and updates
            trigger_type: Trigger type to run (e.g., "cron:daily")

        Returns:
            List of HookResult showing what happened
        """
        results: List[HookResult] = []

        # Load all hooks for this trigger
        hooks = self.load_epigenetic_hooks(repository, trigger_type)

        for hook in hooks:
            # Get all entities of the target type
            try:
                entities = repository.list(entity_type=hook.target_type, limit=500)
            except Exception:
                continue

            for entity in entities:
                # Check if entity was created with this pattern's epigenetics
                # (only apply to entities that have the epigenetic fields)
                epigenetics = entity.data.get("_epigenetics", [])
                if hook.pattern_id not in epigenetics:
                    # Entity wasn't created with this pattern - skip
                    continue

                # Evaluate condition
                matched = self._evaluate_condition(hook.condition, entity)

                result = HookResult(
                    hook_id=hook.hook_id,
                    pattern_id=hook.pattern_id,
                    entity_id=entity.id,
                    matched=matched,
                )

                if matched:
                    try:
                        action_taken = self._execute_action(
                            hook.action, entity, repository
                        )
                        result.action_taken = action_taken
                    except Exception as e:
                        result.error = str(e)

                results.append(result)

        return results


# Global observer singleton for convenience
_global_observer: Optional[EntityObserver] = None


def get_observer() -> EntityObserver:
    """Get the global observer instance."""
    global _global_observer
    if _global_observer is None:
        _global_observer = EntityObserver()
    return _global_observer
