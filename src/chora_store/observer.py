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
from contextlib import contextmanager
import re
import threading

from .models import Entity

if TYPE_CHECKING:
    from .repository import EntityRepository


class ProcessingContext:
    """
    Thread-local context to prevent circular hook execution.

    When a hook triggers an entity update, which triggers more hooks,
    this guard prevents infinite loops by tracking which hook+entity
    combinations are currently being processed.
    """
    _local = threading.local()

    @classmethod
    def is_processing(cls, hook_id: str, entity_id: str) -> bool:
        """Check if we're already processing this hook+entity combination."""
        key = f"{hook_id}:{entity_id}"
        processing = getattr(cls._local, 'processing', set())
        return key in processing

    @classmethod
    @contextmanager
    def guard(cls, hook_id: str, entity_id: str):
        """Context manager to guard against reentrant processing."""
        key = f"{hook_id}:{entity_id}"
        if not hasattr(cls._local, 'processing'):
            cls._local.processing = set()

        if key in cls._local.processing:
            # Already processing this combination, skip
            yield False
            return

        cls._local.processing.add(key)
        try:
            yield True
        finally:
            cls._local.processing.discard(key)


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

        # Check for behavior-based drift signals (features only)
        if (
            change_type == ChangeType.UPDATED
            and entity.type == "feature"
            and entity.status == "stable"
        ):
            self._check_behavior_drift_signal(event)

        return event

    def _check_behavior_drift_signal(self, event: EntityEvent) -> None:
        """
        Check if a stable feature has failing behaviors and emit drift signal.

        When a behavior.status changes to 'failing' on a stable feature,
        this is a drift signal indicating functional regression.

        Args:
            event: The entity update event
        """
        entity = event.entity
        if entity is None:
            return

        behaviors = entity.data.get("behaviors", [])
        if not behaviors:
            return

        # Check for any failing behaviors
        failing_behaviors = [
            b.get("id", "unnamed")
            for b in behaviors
            if b.get("status") == "failing"
        ]

        if failing_behaviors:
            # Emit drift signal event
            drift_event = EntityEvent(
                entity_id=entity.id,
                entity_type=entity.type,
                change_type=ChangeType.UPDATED,
                timestamp=datetime.utcnow(),
                entity=entity,
                old_status="stable",
                new_status="drift_signal",  # Special signal status
            )
            self._event_log.append(drift_event)

            # Log the drift signal
            print(
                f"DRIFT SIGNAL: {entity.id} has failing behaviors: {failing_behaviors}. "
                f"Consider transitioning to 'drifting' status."
            )

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

    def _compute_staleness_variables(
        self,
        entity: Entity,
        repository: "EntityRepository",
    ) -> Dict[str, Any]:
        """
        Compute staleness-related variables for drift detection.

        - days_since_referenced: days since entity was referenced by another entity
        - linked_tests_failing: placeholder for test integration (always False for now)
        - dependencies_changed: placeholder for dependency tracking (always False for now)

        Args:
            entity: The entity to check
            repository: Repository for querying references

        Returns:
            Dict of computed variable names to values
        """
        computed: Dict[str, Any] = {
            "days_since_referenced": 0,
            "linked_tests_failing": False,
            "dependencies_changed": False,
        }

        # For now, use updated timestamp as proxy for "referenced"
        # A more sophisticated implementation would track actual references
        now = datetime.utcnow()
        updated_str = entity.data.get("updated") or entity.data.get("created")
        if updated_str:
            try:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                computed["days_since_referenced"] = (now - updated.replace(tzinfo=None)).days
            except (ValueError, AttributeError):
                pass

        return computed

    def _compute_focus_variables(
        self,
        entity: Entity,
        repository: "EntityRepository",
    ) -> Dict[str, Any]:
        """
        Compute focus-related variables for feature lifecycle hooks.

        Focus (Plasma) provides natural signals for lifecycle transitions:
        - focus_exists: Any focus targets this entity
        - focus_open: An open focus targets this entity (work in progress)
        - focus_finalized_count: Number of completed focus cycles
        - focus_trail_length: Total items in trails (work accumulation)
        - latest_focus_status: Status of most recent focus

        Args:
            entity: The entity to check (typically a feature)
            repository: Repository for querying foci

        Returns:
            Dict of computed variable names to values
        """
        computed: Dict[str, Any] = {
            "focus_exists": False,
            "focus_open": False,
            "focus_finalized_count": 0,
            "focus_trail_length": 0,
            "latest_focus_status": "",
        }

        try:
            # Import here to avoid circular dependency
            from .focus import FocusManager, FOCUS_STATUS_OPEN, FOCUS_STATUS_FINALIZED

            fm = FocusManager(repository)
            all_foci = fm._list_foci()

            # Filter to foci targeting this entity
            targeting_foci = [
                f for f in all_foci
                if f.data.get("target") == entity.id
            ]

            if targeting_foci:
                computed["focus_exists"] = True

                # Check for open focus
                open_foci = [f for f in targeting_foci if f.status == FOCUS_STATUS_OPEN]
                computed["focus_open"] = len(open_foci) > 0

                # Count finalized
                finalized = [f for f in targeting_foci if f.status == FOCUS_STATUS_FINALIZED]
                computed["focus_finalized_count"] = len(finalized)

                # Total trail length
                total_trail = sum(len(f.data.get("trail", [])) for f in targeting_foci)
                computed["focus_trail_length"] = total_trail

                # Latest focus status (by created timestamp)
                sorted_foci = sorted(
                    targeting_foci,
                    key=lambda f: f.data.get("created", ""),
                    reverse=True
                )
                if sorted_foci:
                    computed["latest_focus_status"] = sorted_foci[0].status

        except Exception:
            # If focus system not available, leave defaults
            pass

        return computed

    def _evaluate_condition(
        self,
        condition: str,
        entity: Entity,
        repository: Optional["EntityRepository"] = None,
        old_status: Optional[str] = None,
    ) -> bool:
        """
        Evaluate a hook condition against an entity.

        The condition is a simple expression language:
        - entity.type, entity.status, entity.id
        - entity.{field} for data fields
        - old_status, new_status - for status_changed triggers
        - days_since(entity.created) for time calculations
        - Computed focus variables: focus_exists, focus_open, focus_finalized_count, etc.
        - Computed staleness variables: days_since_referenced, etc.
        - ==, !=, <, >, AND, OR operators

        Args:
            condition: Condition expression string
            entity: Entity to evaluate against
            repository: Optional repository for computing derived variables
            old_status: Previous status (for status_changed triggers)

        Returns:
            True if condition matches, False otherwise
        """
        try:
            # Build evaluation context
            ctx: Dict[str, Any] = {
                "entity_type": entity.type,
                "entity_status": entity.status,
                "entity_id": entity.id,
                "new_status": entity.status,  # Alias for status_changed triggers
                "old_status": old_status,     # Previous status for status_changed
                "true": True,
                "false": False,
                "True": True,
                "False": False,
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

            # Add computed variables if repository available
            if repository:
                ctx.update(self._compute_staleness_variables(entity, repository))
                ctx.update(self._compute_focus_variables(entity, repository))

            # Normalize condition string
            cond = condition.strip()
            # Replace entity.field with entity_field
            cond = re.sub(r"entity\.(\w+)", r"entity_\1", cond)
            # Replace days_since(entity.created) with days_since_created
            cond = re.sub(r"days_since\(entity\.created\)", "days_since_created", cond)
            cond = re.sub(r"days_since\(entity_created\)", "days_since_created", cond)

            # Simple expression evaluation
            # First replace newlines with spaces (conditions can span multiple lines)
            cond = cond.replace("\n", " ")
            # Replace AND/OR with Python equivalents
            cond = cond.replace(" AND ", " and ").replace(" OR ", " or ")
            # Replace SQL-style NULL checks with Python equivalents
            cond = cond.replace(" IS NOT NULL", " is not None")
            cond = cond.replace(" IS NULL", " is None")

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
        - transition(status='new_status') - change entity status
        - emit('event.name', key=value, ...) - emit a custom event
        - append(field, 'value') - append to an array field
        - set_field(field=value) - set a data field value
        - generate('tool_id', input=entity.field) - invoke generative tool
        - invoke_tool('tool_id', key=value) - invoke any tool by ID (Wave 8)
        - invoke_pipeline('pipeline_name', key=value) - invoke a Phase 6 pipeline
        - crystallize_routes(min_traces=5, consistency_threshold=0.95) - auto-crystallize routes

        The generate action enables Observer → Factory wiring for L5 operations.
        The invoke_tool action enables epigenetic hooks to trigger any tool (Wave 8 automation).
        The crystallize_routes action enables Push-Right solidification of inference traces.

        Args:
            action: Action expression string
            entity: Entity to act on
            repository: Repository for persistence

        Returns:
            Description of action taken
        """
        results = []

        # Handle multi-line actions (each line is an action)
        action_lines = [line.strip() for line in action.strip().split('\n') if line.strip()]

        for action_line in action_lines:
            result = self._execute_single_action(action_line, entity, repository)
            if result:
                results.append(result)
                # Re-fetch entity to get updated state for subsequent actions
                try:
                    entity = repository.read(entity.id) or entity
                except Exception:
                    pass

        return "; ".join(results) if results else "No actions taken"

    def _execute_single_action(
        self,
        action: str,
        entity: Entity,
        repository: "EntityRepository",
    ) -> str:
        """Execute a single action line."""

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

        # Parse emit action: emit('event.name', key=value, ...)
        emit_match = re.match(r"emit\(['\"]([^'\"]+)['\"]", action)
        if emit_match:
            event_name = emit_match.group(1)
            # Log the event (could be expanded to actual event bus)
            self._event_log.append(EntityEvent(
                entity_id=entity.id,
                entity_type=entity.type,
                change_type=ChangeType.UPDATED,
                timestamp=datetime.utcnow(),
                entity=entity,
                old_status=None,
                new_status=entity.status,
            ))
            return f"Emitted '{event_name}'"

        # Parse append action: append(field, 'value')
        append_match = re.match(r"append\((\w+),\s*['\"]([^'\"]+)['\"]\)", action)
        if append_match:
            field_name = append_match.group(1)
            value = append_match.group(2)

            updated_data = dict(entity.data)
            current_list = updated_data.get(field_name, [])
            if not isinstance(current_list, list):
                current_list = []
            current_list.append(value)
            updated_data[field_name] = current_list
            updated_data["updated"] = datetime.utcnow().isoformat()

            updated_entity = entity.copy(data=updated_data)
            repository.update(updated_entity)

            return f"Appended '{value}' to {field_name}"

        # Parse set_field action: set_field(field=value)
        set_field_match = re.match(r"set_field\((\w+)=(.*)\)", action)
        if set_field_match:
            field_name = set_field_match.group(1)
            value_str = set_field_match.group(2).strip()

            # Parse value (handle booleans and strings)
            if value_str.lower() == "true":
                value = True
            elif value_str.lower() == "false":
                value = False
            elif value_str.startswith("'") or value_str.startswith('"'):
                value = value_str.strip("'\"")
            else:
                try:
                    value = int(value_str)
                except ValueError:
                    value = value_str

            updated_data = dict(entity.data)
            updated_data[field_name] = value
            updated_data["updated"] = datetime.utcnow().isoformat()

            updated_entity = entity.copy(data=updated_data)
            repository.update(updated_entity)

            return f"Set {field_name}={value}"

        # Parse generate action: generate(tool_id, input1=entity.field1, input2='literal')
        generate_match = re.match(r"generate\(['\"]([^'\"]+)['\"](?:,\s*(.+))?\)", action)
        if generate_match:
            tool_id = generate_match.group(1)
            args_str = generate_match.group(2) or ""

            # Parse input arguments
            inputs = {}
            if args_str:
                # Split by comma but respect nested structures
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if '=' in arg:
                        key, value = arg.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip("'\"")

                        # Check if value references entity field (entity.field)
                        if value.startswith('entity.'):
                            field_path = value[7:]  # Remove 'entity.'
                            # Navigate nested fields
                            obj = entity.data
                            for part in field_path.split('.'):
                                if isinstance(obj, dict):
                                    obj = obj.get(part, '')
                                else:
                                    obj = getattr(obj, part, '')
                            inputs[key] = str(obj)
                        else:
                            inputs[key] = value

            # Import and call tool_invoke
            try:
                from .mcp import tool_invoke
                result = tool_invoke(tool_id, **inputs)

                # Check if generation succeeded
                if result.startswith("✓ Generated"):
                    return f"Generated via {tool_id}: {result.split(chr(10))[0]}"
                elif "[APPROVAL REQUIRED]" in result:
                    return f"Generation pending approval via {tool_id}"
                else:
                    return f"Generate action: {result[:100]}"
            except Exception as e:
                return f"Generate error: {e}"

        # Parse invoke_pipeline action: invoke_pipeline('phase6.full', key=value)
        pipeline_match = re.match(r"invoke_pipeline\(['\"]([^'\"]+)['\"](?:,\s*(.+))?\)", action)
        if pipeline_match:
            pipeline_name = pipeline_match.group(1)
            args_str = pipeline_match.group(2) or ""

            # Parse keyword arguments
            kwargs = {}
            if args_str:
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if '=' in arg:
                        key, value = arg.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Handle entity_id reference
                        if value == 'entity_id':
                            kwargs[key] = entity.id
                        elif value.startswith("'") or value.startswith('"'):
                            kwargs[key] = value.strip("'\"")
                        else:
                            kwargs[key] = value

            return self._invoke_phase6_pipeline(pipeline_name, entity, repository, kwargs)

        # Parse invoke_tool action: invoke_tool('tool_id', key=value, ...)
        invoke_tool_match = re.match(r"invoke_tool\(['\"]([^'\"]+)['\"](?:,\s*(.+))?\)", action)
        if invoke_tool_match:
            tool_id = invoke_tool_match.group(1)
            args_str = invoke_tool_match.group(2) or ""

            # Parse keyword arguments
            inputs = {}
            if args_str:
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if '=' in arg:
                        key, value = arg.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        inputs[key] = value

            try:
                from .mcp import tool_invoke
                result = tool_invoke(tool_id, **inputs)
                return f"Invoked {tool_id}: {result[:100]}"
            except Exception as e:
                return f"invoke_tool error: {e}"

        # Parse crystallize_routes action: crystallize_routes(min_traces=5, consistency_threshold=0.95)
        crystallize_match = re.match(
            r"crystallize_routes\((?:min_traces=(\d+))?(?:,\s*)?(?:consistency_threshold=([\d.]+))?\)",
            action
        )
        if crystallize_match:
            min_traces = int(crystallize_match.group(1) or 5)
            consistency_threshold = float(crystallize_match.group(2) or 0.95)

            try:
                from .mcp import tool_crystallize_routes
                result = tool_crystallize_routes(
                    tool_id=None,
                    min_traces=min_traces,
                    consistency_threshold=consistency_threshold,
                )
                return f"Crystallization: {result}"
            except Exception as e:
                return f"Crystallization error: {e}"

        return f"Unknown action: {action}"

    def _invoke_phase6_pipeline(
        self,
        pipeline_name: str,
        entity: Optional[Entity],
        repository: "EntityRepository",
        kwargs: Dict[str, Any],
    ) -> str:
        """
        Invoke a Phase 6 autonomous reification pipeline stage.

        Pipeline stages:
        - phase6.full: Run complete pipeline (DETECT -> REIFY -> ALIGN -> EVALUATE)
        - phase6.align: Align behaviors for a specific feature
        - phase6.evaluate: Evaluate fitness for a specific pattern
        """
        try:
            if pipeline_name == 'phase6.full':
                # DETECT + REIFY + ALIGN
                from .traceability.reifier import PatternReifier
                from .evaluator import PatternEvaluator

                reifier = PatternReifier(repository=repository)
                report = reifier.reify_all(min_confidence=0.7)

                # EVALUATE experimental patterns
                evaluator = PatternEvaluator(repository)
                eval_reports = evaluator.evaluate_all()
                promoted = sum(1 for r in eval_reports if r.recommendation == 'promote')
                deprecated = sum(1 for r in eval_reports if r.recommendation == 'deprecate')

                # Execute promotion/deprecation actions
                for r in eval_reports:
                    if r.recommendation in ('promote', 'deprecate'):
                        try:
                            evaluator.execute_actions(r)
                        except Exception:
                            pass

                return (f"Phase 6 pipeline: {report.candidates_found} candidates, "
                        f"{len(report.patterns_created)} patterns created, "
                        f"{len(report.behaviors_aligned)} aligned, "
                        f"{promoted} promoted, {deprecated} deprecated")

            elif pipeline_name == 'phase6.align':
                from .traceability.reifier import PatternReifier

                reifier = PatternReifier(repository=repository)
                feature_id = kwargs.get('feature_id')

                if feature_id:
                    # Align behaviors for specific feature
                    aligned = reifier._align_all_behaviors([])
                    feature_aligned = [a for a in aligned if a.feature_id == feature_id]
                    return f"Aligned {len(feature_aligned)} behaviors for {feature_id}"
                else:
                    aligned = reifier._align_all_behaviors([])
                    return f"Aligned {len(aligned)} behaviors"

            elif pipeline_name == 'phase6.evaluate':
                from .evaluator import PatternEvaluator

                pattern_id = kwargs.get('pattern_id')
                if not pattern_id:
                    return "No pattern_id specified for evaluation"

                pattern = repository.read(pattern_id)
                if not pattern:
                    return f"Pattern not found: {pattern_id}"

                evaluator = PatternEvaluator(repository)
                report = evaluator.evaluate_pattern(pattern)

                if report.recommendation in ('promote', 'deprecate'):
                    evaluator.execute_actions(report)
                    return f"Evaluated {pattern_id}: {report.recommendation} (executed)"
                else:
                    return f"Evaluated {pattern_id}: {report.recommendation}"

            else:
                return f"Unknown pipeline: {pipeline_name}"

        except Exception as e:
            return f"Pipeline error ({pipeline_name}): {e}"

    def run_epigenetic_hooks(
        self,
        repository: "EntityRepository",
        trigger_type: str = "cron:daily",
        entity: Optional["Entity"] = None,
        old_status: Optional[str] = None,
    ) -> List[HookResult]:
        """
        Run all epigenetic hooks for a given trigger type.

        This is the main entry point for the epigenetic bridge runtime.
        Call this during orient() or on a schedule to evaluate and
        execute hooks from experimental patterns.

        For event-driven triggers (entity:created, entity:updated), pass
        the specific entity to avoid scanning all entities.

        For status_changed triggers, pass old_status to enable conditions
        that check transition direction (e.g., old_status == 'nascent').

        Args:
            repository: EntityRepository for queries and updates
            trigger_type: Trigger type to run (e.g., "cron:daily", "entity:feature:created")
            entity: Optional specific entity for event-driven triggers
            old_status: Optional previous status for status_changed triggers

        Returns:
            List of HookResult showing what happened
        """
        results: List[HookResult] = []

        # Load all hooks for this trigger
        hooks = self.load_epigenetic_hooks(repository, trigger_type)

        for hook in hooks:
            # Get entities to process
            if entity is not None:
                # Event-driven: use the provided entity
                if entity.type != hook.target_type:
                    continue
                entities = [entity]
            else:
                # Scheduled: query all entities of target type
                try:
                    entities = repository.list(entity_type=hook.target_type, limit=500)
                except Exception:
                    continue

            # For cron triggers, check if this is a pattern-level hook (runs once)
            # Pattern-level hooks have conditions like "true" or SQL-like queries
            is_cron = trigger_type.startswith("cron:")
            is_pattern_level = is_cron and hook.condition in ("true", "True", "")

            if is_pattern_level:
                # Pattern-level hook: run once, not per-entity
                # Use first entity as context (or None)
                ctx_entity = entities[0] if entities else None
                matched = self._evaluate_condition(
                    hook.condition, ctx_entity, repository, old_status=old_status
                )
                result = HookResult(
                    hook_id=hook.hook_id,
                    pattern_id=hook.pattern_id,
                    entity_id=ctx_entity.id if ctx_entity else "global",
                    matched=matched,
                )
                if matched:
                    try:
                        action_taken = self._execute_action(
                            hook.action, ctx_entity, repository
                        )
                        result.action_taken = action_taken
                    except Exception as e:
                        result.error = str(e)
                results.append(result)
                continue  # Skip per-entity loop

            for ent in entities:
                # Check if entity was created with this pattern's epigenetics
                # For cron triggers, skip _epigenetics check (pattern-level)
                if not is_cron:
                    epigenetics = ent.data.get("_epigenetics", [])
                    if hook.pattern_id not in epigenetics:
                        # Entity wasn't created with this pattern - skip
                        continue

                # Evaluate condition (pass repository for computed variables)
                # Also pass old_status for status_changed triggers
                matched = self._evaluate_condition(
                    hook.condition, ent, repository, old_status=old_status
                )

                result = HookResult(
                    hook_id=hook.hook_id,
                    pattern_id=hook.pattern_id,
                    entity_id=ent.id,
                    matched=matched,
                )

                if matched:
                    try:
                        action_taken = self._execute_action(
                            hook.action, ent, repository
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
