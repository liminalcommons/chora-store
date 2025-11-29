"""
Trigger system for event → action mapping.

Defines what actions to take when events occur.
"""

import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from enum import Enum


class EventType(Enum):
    """Types of events that can trigger actions."""
    ENTITY_CREATED = "entity.created"
    ENTITY_UPDATED = "entity.updated"
    ENTITY_DELETED = "entity.deleted"
    FILE_CHANGED = "file.changed"
    GIT_PRE_COMMIT = "git.pre-commit"
    GIT_POST_COMMIT = "git.post-commit"
    GIT_PRE_PUSH = "git.pre-push"


@dataclass
class Action:
    """
    An action to execute when triggered.

    Can be either a Python callable or a shell command.
    """
    name: str
    description: str
    handler: Optional[Callable[[Dict[str, Any]], bool]] = None
    command: Optional[str] = None
    enabled: bool = True

    def execute(self, context: Dict[str, Any]) -> bool:
        """
        Execute the action.

        Args:
            context: Event context with details about what triggered

        Returns:
            True if action succeeded
        """
        if not self.enabled:
            return True

        if self.handler:
            return self.handler(context)
        elif self.command:
            # Execute shell command
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                env={**dict(__import__('os').environ), **context.get('env', {})}
            )
            return result.returncode == 0
        return True


@dataclass
class Trigger:
    """
    Maps an event type to actions.
    """
    event_type: EventType
    actions: List[str] = field(default_factory=list)
    conditions: Optional[Callable[[Dict[str, Any]], bool]] = None

    def should_fire(self, context: Dict[str, Any]) -> bool:
        """Check if trigger conditions are met."""
        if self.conditions:
            return self.conditions(context)
        return True


class TriggerRegistry:
    """
    Registry of triggers and actions.

    Manages the mapping between events and the actions they trigger.
    """

    def __init__(self):
        self._actions: Dict[str, Action] = {}
        self._triggers: Dict[EventType, List[Trigger]] = {}
        self._register_default_actions()

    def _register_default_actions(self):
        """Register built-in actions."""
        # Validation action
        self.register_action(Action(
            name="validate",
            description="Validate entity against kernel schema",
            handler=self._action_validate,
        ))

        # Log action
        self.register_action(Action(
            name="log",
            description="Log event to console",
            handler=self._action_log,
        ))

        # Lint action
        self.register_action(Action(
            name="lint",
            description="Run linters on changed files",
            command="just lint 2>/dev/null || echo 'Lint check failed'",
        ))

        # Backup check action
        self.register_action(Action(
            name="backup_check",
            description="Check backup status",
            handler=self._action_backup_check,
        ))

    def _action_validate(self, context: Dict[str, Any]) -> bool:
        """Validate an entity."""
        entity_id = context.get("entity_id")
        if not entity_id:
            return True
        print(f"[validate] Validating {entity_id}")
        # In practice, would call EntityFactory validation
        return True

    def _action_log(self, context: Dict[str, Any]) -> bool:
        """Log an event."""
        event_type = context.get("event_type", "unknown")
        entity_id = context.get("entity_id", "")
        print(f"[log] Event: {event_type} | Entity: {entity_id}")
        return True

    def _action_backup_check(self, context: Dict[str, Any]) -> bool:
        """Check if backup is running."""
        from ..backup import get_status
        status = get_status()
        if status.configured and not status.running:
            print(f"[backup_check] Warning: Backup configured but not running")
        return True

    def register_action(self, action: Action) -> None:
        """Register an action."""
        self._actions[action.name] = action

    def register_trigger(self, trigger: Trigger) -> None:
        """Register a trigger."""
        if trigger.event_type not in self._triggers:
            self._triggers[trigger.event_type] = []
        self._triggers[trigger.event_type].append(trigger)

    def fire(self, event_type: EventType, context: Dict[str, Any]) -> List[str]:
        """
        Fire all triggers for an event.

        Args:
            event_type: Type of event that occurred
            context: Event context

        Returns:
            List of action names that were executed
        """
        context["event_type"] = event_type.value
        executed = []

        triggers = self._triggers.get(event_type, [])
        for trigger in triggers:
            if not trigger.should_fire(context):
                continue

            for action_name in trigger.actions:
                action = self._actions.get(action_name)
                if action:
                    try:
                        action.execute(context)
                        executed.append(action_name)
                    except Exception as e:
                        print(f"[trigger] Action '{action_name}' failed: {e}")

        return executed

    def get_actions(self) -> Dict[str, Action]:
        """Get all registered actions."""
        return dict(self._actions)

    def get_triggers(self) -> Dict[EventType, List[Trigger]]:
        """Get all registered triggers."""
        return dict(self._triggers)

    def load_default_triggers(self) -> None:
        """Load default trigger configuration."""
        # Entity lifecycle triggers
        self.register_trigger(Trigger(
            event_type=EventType.ENTITY_CREATED,
            actions=["validate", "log"],
        ))

        self.register_trigger(Trigger(
            event_type=EventType.ENTITY_UPDATED,
            actions=["validate", "backup_check"],
        ))

        self.register_trigger(Trigger(
            event_type=EventType.ENTITY_DELETED,
            actions=["log"],
        ))

        # Git hook triggers
        self.register_trigger(Trigger(
            event_type=EventType.GIT_PRE_COMMIT,
            actions=["lint"],
        ))


# Global registry instance
_registry: Optional[TriggerRegistry] = None


def get_registry() -> TriggerRegistry:
    """Get the global trigger registry."""
    global _registry
    if _registry is None:
        _registry = TriggerRegistry()
        _registry.load_default_triggers()
    return _registry
