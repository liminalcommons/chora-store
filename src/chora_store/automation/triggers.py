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
    # Scheduled events (agent-triggered, not system cron)
    CRON_DAILY = "cron.daily"
    CRON_SESSION_START = "cron.session_start"


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

        # Auto-induction action (Experiment 3: Autoevolutionary Loop)
        self.register_action(Action(
            name="auto_induction",
            description="Cluster learnings and propose patterns automatically",
            handler=self._action_auto_induction,
        ))

        # Feature TTL check action
        self.register_action(Action(
            name="feature_ttl_check",
            description="Check for stale features past their TTL",
            handler=self._action_feature_ttl_check,
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

    def _action_auto_induction(self, context: Dict[str, Any]) -> bool:
        """Run auto-induction to cluster learnings and propose patterns."""
        try:
            from ..metabolism import tool_auto_induction
            result = tool_auto_induction(
                min_learnings=context.get("min_learnings", 3),
                confidence_threshold=context.get("confidence_threshold", 0.6),
                auto_approve=context.get("auto_approve", False),
                max_approvals=context.get("max_approvals", 3),
            )
            print(f"[auto_induction] {result}")
            return True
        except Exception as e:
            print(f"[auto_induction] Error: {e}")
            return False

    def _action_feature_ttl_check(self, context: Dict[str, Any]) -> bool:
        """Check for features that have exceeded their TTL."""
        try:
            from ..repository import EntityRepository
            from datetime import datetime, timezone, timedelta

            repo = EntityRepository()
            features = repo.list(entity_type="feature", limit=100)

            stale_count = 0
            now = datetime.now(timezone.utc)

            for feature in features:
                if feature.status == "nascent":
                    ttl_days = feature.data.get("ttl_days", 30)
                    # Handle timezone-naive datetimes
                    created = feature.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age = (now - created).days
                    if age > ttl_days:
                        # Mark drift signal
                        drift_signals = feature.data.get("drift_signals", [])
                        if "ttl_expired" not in drift_signals:
                            drift_signals.append("ttl_expired")
                            feature.data["drift_signals"] = drift_signals
                            repo.update(feature)
                            print(f"[feature_ttl_check] {feature.id}: TTL expired ({age} days > {ttl_days})")
                            stale_count += 1

            if stale_count > 0:
                print(f"[feature_ttl_check] Flagged {stale_count} stale features")
            return True
        except Exception as e:
            print(f"[feature_ttl_check] Error: {e}")
            return False

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

        # Cron triggers (agent-fired, not system cron)
        self.register_trigger(Trigger(
            event_type=EventType.CRON_DAILY,
            actions=["auto_induction", "feature_ttl_check"],
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


def fire_daily_cron(context: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Fire the daily cron event.

    This is meant to be called by agents periodically (e.g., at session start
    or when requested). It runs all actions registered for CRON_DAILY.

    Args:
        context: Optional context to pass to actions

    Returns:
        List of action names that were executed
    """
    registry = get_registry()
    ctx = context or {}
    executed = registry.fire(EventType.CRON_DAILY, ctx)
    return executed


def fire_session_start(context: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Fire the session start event.

    Called at the beginning of an agent session to run any session-start tasks.

    Args:
        context: Optional context to pass to actions

    Returns:
        List of action names that were executed
    """
    registry = get_registry()
    ctx = context or {}
    executed = registry.fire(EventType.CRON_SESSION_START, ctx)
    return executed
