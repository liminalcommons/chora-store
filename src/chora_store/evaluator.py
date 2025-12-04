"""
PatternEvaluator - Fitness Engine for Experimental Patterns.

This is the SELECT mechanism of the epigenetic bridge. It measures
pattern fitness against defined criteria and triggers promotion or
deprecation based on observed outcomes.

The fitness engine completes the MUTATE → EXPRESS → SELECT loop:
- MUTATE: Factory injects experimental fields
- EXPRESS: Observer runs behavioral hooks
- SELECT: Evaluator measures fitness and promotes/deprecates patterns

The Canary Monitor provides early warning detection for harmful patterns
(bricking) before they cause widespread damage.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import re

from .models import Entity
from .observer import EntityObserver, ChangeType, get_observer

if TYPE_CHECKING:
    from .repository import EntityRepository


# =============================================================================
# CANARY THRESHOLDS - Configurable limits for bricking detection
# =============================================================================

CANARY_THRESHOLDS = {
    "reversion_count": 5,          # Max reversions in window before alert
    "reversion_window_days": 7,     # Window for counting reversions
    "trend_decline_count": 3,       # Consecutive declining metrics to trigger
    "failure_rate": 0.10,           # 10% failure rate triggers alert
    "min_operations": 10,           # Minimum operations before failure rate applies
}


@dataclass
class CanaryAlert:
    """Alert for potential bricking behavior."""
    pattern_id: str
    pattern_name: str
    signal: str  # "excessive_reversions", "negative_trend", "failure_spike"
    severity: str  # "warning", "critical"
    details: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    auto_disabled: bool = False


@dataclass
class MetricResult:
    """Result of evaluating a fitness metric."""
    name: str
    description: str
    baseline: Optional[float]
    target: Optional[float]
    direction: str  # "lower_is_better", "higher_is_better", "informational"
    current_value: Optional[float]
    achieved: bool = False
    error: Optional[str] = None


@dataclass
class FitnessReport:
    """Complete fitness report for a pattern."""
    pattern_id: str
    pattern_name: str
    observation_period_days: int
    days_since_experimental: int
    sample_size_required: int
    sample_size_actual: int
    metrics: List[MetricResult]
    success_condition_met: bool
    failure_condition_met: bool
    observation_period_elapsed: bool
    recommendation: str  # "continue", "promote", "deprecate"
    actions_to_take: List[str] = field(default_factory=list)


class PatternEvaluator:
    """
    Fitness Engine for evaluating experimental patterns.

    This class measures pattern effectiveness against defined criteria
    and determines whether patterns should be promoted to kernel physics
    or deprecated as unsuccessful experiments.

    Usage:
        evaluator = PatternEvaluator(repository)

        # Evaluate all experimental patterns
        reports = evaluator.evaluate_all()

        # Execute recommended actions
        for report in reports:
            if report.recommendation != "continue":
                evaluator.execute_actions(report)
    """

    def __init__(
        self,
        repository: "EntityRepository",
        observer: Optional[EntityObserver] = None,
    ):
        """
        Initialize the evaluator.

        Args:
            repository: EntityRepository for data access
            observer: EntityObserver for emitting events (defaults to global)
        """
        self.repository = repository
        self.observer = observer or get_observer()

    def _load_experimental_patterns(self) -> List[Entity]:
        """Load all experimental schema-extension patterns."""
        patterns = []
        try:
            all_patterns = self.repository.list(entity_type="pattern", limit=100)
            for p in all_patterns:
                if p.status == "experimental":
                    subtype = p.data.get("subtype")
                    if subtype == "schema-extension":
                        patterns.append(p)
        except Exception:
            pass
        return patterns

    def _parse_observation_period(self, period_str: str) -> int:
        """Parse observation period string to days."""
        # Handle formats like "90 days", "60 days", etc.
        match = re.match(r"(\d+)\s*days?", period_str.lower())
        if match:
            return int(match.group(1))
        return 90  # Default to 90 days

    def _get_days_since_experimental(self, pattern: Entity) -> int:
        """Calculate days since pattern became experimental."""
        # Check for explicit experimental_since in data
        experimental_since = pattern.data.get("experimental_since")
        now = datetime.now(timezone.utc)
        if experimental_since:
            try:
                since_date = datetime.fromisoformat(experimental_since.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if since_date.tzinfo is None:
                    since_date = since_date.replace(tzinfo=timezone.utc)
                return (now - since_date).days
            except (ValueError, AttributeError):
                pass

        # Fall back to created_at
        created_at = pattern.created_at
        # Ensure timezone-aware
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return (now - created_at).days

    def _count_entities_with_pattern(
        self,
        pattern_id: str,
        entity_type: str,
        status: Optional[str] = None,
        field_condition: Optional[Dict[str, Any]] = None,
        not_null_fields: Optional[List[str]] = None,
    ) -> int:
        """
        Count entities created with a pattern's epigenetics.

        Args:
            pattern_id: ID of the pattern
            entity_type: Type of entities to count
            status: Optional status filter
            field_condition: Optional dict of field=value conditions
            not_null_fields: Fields that must be non-null and non-empty

        Returns:
            Count of matching entities
        """
        count = 0
        try:
            entities = self.repository.list(entity_type=entity_type, status=status, limit=500)
            for entity in entities:
                # Check if entity has this pattern's epigenetics
                epigenetics = entity.data.get("_epigenetics", [])
                if pattern_id not in epigenetics:
                    continue

                match = True

                # Check additional field conditions
                if field_condition:
                    for field_name, expected_value in field_condition.items():
                        actual_value = entity.data.get(field_name)
                        # IS NULL: treat empty string as null
                        if expected_value is None:
                            if actual_value is not None and actual_value != "":
                                match = False
                                break
                        elif actual_value != expected_value:
                            match = False
                            break

                # Check IS NOT NULL conditions
                if match and not_null_fields:
                    for field_name in not_null_fields:
                        actual_value = entity.data.get(field_name)
                        if actual_value is None or actual_value == "":
                            match = False
                            break

                if not match:
                    continue

                count += 1
        except Exception:
            pass
        return count

    def _calculate_metric(
        self,
        metric_def: Dict[str, Any],
        pattern: Entity,
        target_type: str,
    ) -> MetricResult:
        """
        Calculate a single fitness metric.

        The query language in patterns is pseudo-SQL. We translate it
        to actual repository queries.
        """
        name = metric_def.get("name", "unknown")
        description = metric_def.get("description", "")
        baseline = metric_def.get("baseline")
        target = metric_def.get("target")
        direction = metric_def.get("direction", "lower_is_better")
        query = metric_def.get("query", "")

        result = MetricResult(
            name=name,
            description=description,
            baseline=baseline,
            target=target,
            direction=direction,
            current_value=None,
        )

        try:
            # Parse and execute the query
            value = self._execute_metric_query(query, pattern.id, target_type)
            result.current_value = value

            # Determine if target achieved
            if target is not None and value is not None:
                if direction == "lower_is_better":
                    result.achieved = value <= target
                elif direction == "higher_is_better":
                    result.achieved = value >= target
                else:
                    result.achieved = True  # Informational metrics are always "achieved"
            elif direction == "informational":
                result.achieved = True

        except Exception as e:
            result.error = str(e)

        return result

    def _execute_metric_query(
        self,
        query: str,
        pattern_id: str,
        target_type: str,
    ) -> Optional[float]:
        """
        Execute a metric query against the repository.

        Translates pseudo-SQL to repository operations.
        """
        query = query.strip()

        # Handle ratio queries: count(...) / count(...)
        # Pattern 1: Both sides have WHERE
        ratio_match = re.match(
            r"count\((\w+)\s+WHERE\s+(.+?)\)\s*/\s*count\((\w+)\s+WHERE\s+(.+?)\)",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if ratio_match:
            numerator_type = ratio_match.group(1)
            numerator_conditions = ratio_match.group(2)
            denominator_type = ratio_match.group(3)
            denominator_conditions = ratio_match.group(4)

            numerator = self._count_with_conditions(
                pattern_id, numerator_type, numerator_conditions
            )
            denominator = self._count_with_conditions(
                pattern_id, denominator_type, denominator_conditions
            )

            if denominator == 0:
                return 0.0
            return numerator / denominator

        # Pattern 2: Numerator has WHERE, denominator is simple count
        ratio_simple_match = re.match(
            r"count\((\w+)\s+WHERE\s+(.+?)\)\s*/\s*count\((\w+)\)",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if ratio_simple_match:
            numerator_type = ratio_simple_match.group(1)
            numerator_conditions = ratio_simple_match.group(2)
            denominator_type = ratio_simple_match.group(3)

            numerator = self._count_with_conditions(
                pattern_id, numerator_type, numerator_conditions
            )
            denominator = self._count_all(denominator_type)

            if denominator == 0:
                return 0.0
            return numerator / denominator

        # Handle simple count queries: count(type WHERE ...)
        count_match = re.match(
            r"count\((\w+)\s+WHERE\s+(.+?)\)",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if count_match:
            entity_type = count_match.group(1)
            conditions = count_match.group(2)
            return float(self._count_with_conditions(pattern_id, entity_type, conditions))

        # Handle bare count without WHERE: count(type)
        count_bare_match = re.match(r"count\((\w+)\)$", query.strip(), re.IGNORECASE)
        if count_bare_match:
            entity_type = count_bare_match.group(1)
            return float(self._count_all(entity_type))

        # Handle avg queries (simplified)
        avg_match = re.match(r"avg\((.+?)\)", query, re.IGNORECASE | re.DOTALL)
        if avg_match:
            # For now, return None for avg queries (complex to implement)
            return None

        return None

    def _count_all(self, entity_type_plural: str) -> int:
        """
        Count all entities of a given type.

        Args:
            entity_type_plural: Plural form (e.g., "features")

        Returns:
            Total count of entities of that type
        """
        entity_type = entity_type_plural.rstrip("s")  # features -> feature
        try:
            entities = self.repository.list(entity_type=entity_type, limit=1000)
            return len(entities)
        except Exception:
            return 0

    def _count_with_conditions(
        self,
        pattern_id: str,
        entity_type_plural: str,
        conditions: str,
    ) -> int:
        """
        Count entities matching conditions from pseudo-SQL.

        Args:
            pattern_id: Pattern to filter by
            entity_type_plural: Plural form (e.g., "features")
            conditions: SQL-like conditions string
        """
        # Normalize entity type
        entity_type = entity_type_plural.rstrip("s")  # features -> feature

        # Parse conditions
        status = None
        field_conditions = {}

        # Extract status condition
        status_match = re.search(r"status\s*=\s*'(\w+)'", conditions, re.IGNORECASE)
        if status_match:
            status = status_match.group(1)

        # Extract field IS NOT NULL
        not_null_fields = []
        not_null_matches = re.findall(r"(\w+)\s+IS\s+NOT\s+NULL", conditions, re.IGNORECASE)
        for field_name in not_null_matches:
            not_null_fields.append(field_name)

        # Extract field IS NULL
        null_matches = re.findall(r"(\w+)\s+IS\s+NULL", conditions, re.IGNORECASE)
        for field_name in null_matches:
            field_conditions[field_name] = None

        # Extract field = 'value'
        eq_matches = re.findall(r"(\w+)\s*=\s*'([^']+)'", conditions)
        for field_name, value in eq_matches:
            if field_name.lower() != "status":
                field_conditions[field_name] = value

        # Extract field = true/false
        bool_matches = re.findall(r"(\w+)\s*=\s*(true|false)", conditions, re.IGNORECASE)
        for field_name, value in bool_matches:
            field_conditions[field_name] = value.lower() == "true"

        return self._count_entities_with_pattern(
            pattern_id,
            entity_type,
            status,
            field_conditions if field_conditions else None,
            not_null_fields if not_null_fields else None,
        )

    def evaluate_pattern(self, pattern: Entity) -> FitnessReport:
        """
        Evaluate fitness for a single pattern.

        Args:
            pattern: The experimental pattern to evaluate

        Returns:
            FitnessReport with metrics and recommendation
        """
        mechanics = pattern.data.get("mechanics", {})
        fitness = mechanics.get("fitness", {})
        target_type = mechanics.get("target", "feature")

        # Parse observation period
        period_str = fitness.get("observation_period", "90 days")
        observation_period_days = self._parse_observation_period(period_str)

        # Calculate days since experimental
        days_since_experimental = self._get_days_since_experimental(pattern)
        observation_period_elapsed = days_since_experimental >= observation_period_days

        # Get sample size
        sample_size_required = fitness.get("sample_size", 20)
        sample_size_actual = self._count_entities_with_pattern(
            pattern.id, target_type
        )

        # Calculate metrics
        metrics = []
        metric_results = {}  # For condition evaluation
        for metric_def in fitness.get("metrics", []):
            result = self._calculate_metric(metric_def, pattern, target_type)
            metrics.append(result)
            metric_results[result.name] = result

        # Evaluate success/failure conditions
        success_condition = fitness.get("success_condition", "")
        failure_condition = fitness.get("failure_condition", "")

        success_met = self._evaluate_condition(
            success_condition, metric_results, observation_period_elapsed
        )
        failure_met = self._evaluate_condition(
            failure_condition, metric_results, observation_period_elapsed
        )

        # Determine recommendation
        recommendation = "continue"
        actions_to_take = []

        if sample_size_actual < sample_size_required:
            recommendation = "continue"  # Not enough data
        elif success_met:
            recommendation = "promote"
            for action_def in fitness.get("on_success", []):
                actions_to_take.append(action_def.get("action", ""))
        elif failure_met:
            recommendation = "deprecate"
            for action_def in fitness.get("on_failure", []):
                actions_to_take.append(action_def.get("action", ""))

        return FitnessReport(
            pattern_id=pattern.id,
            pattern_name=pattern.data.get("name", pattern.id),
            observation_period_days=observation_period_days,
            days_since_experimental=days_since_experimental,
            sample_size_required=sample_size_required,
            sample_size_actual=sample_size_actual,
            metrics=metrics,
            success_condition_met=success_met,
            failure_condition_met=failure_met,
            observation_period_elapsed=observation_period_elapsed,
            recommendation=recommendation,
            actions_to_take=actions_to_take,
        )

    def _evaluate_condition(
        self,
        condition: str,
        metric_results: Dict[str, MetricResult],
        observation_period_elapsed: bool,
    ) -> bool:
        """
        Evaluate a success/failure condition.

        Conditions can reference:
        - metric_name.achieved
        - observation_period.elapsed
        """
        if not condition.strip():
            return False

        try:
            # Build context
            ctx = {
                "observation_period": type("obj", (), {"elapsed": observation_period_elapsed})(),
            }

            # Add metric results
            for name, result in metric_results.items():
                ctx[name] = result

            # Normalize condition
            cond = condition.strip().replace("\n", " ")
            cond = cond.replace(" AND ", " and ").replace(" OR ", " or ")
            cond = cond.replace("NOT ", "not ")

            # Evaluate
            return bool(eval(cond, {"__builtins__": {}}, ctx))
        except Exception:
            return False

    def evaluate_all(self) -> List[FitnessReport]:
        """
        Evaluate fitness for all experimental patterns.

        Returns:
            List of FitnessReport for each pattern
        """
        reports = []
        patterns = self._load_experimental_patterns()
        for pattern in patterns:
            report = self.evaluate_pattern(pattern)
            reports.append(report)
        return reports

    def execute_actions(self, report: FitnessReport) -> List[str]:
        """
        Execute the actions recommended in a fitness report.

        Args:
            report: FitnessReport with actions_to_take

        Returns:
            List of descriptions of actions taken
        """
        results = []
        pattern = self.repository.read(report.pattern_id)
        if not pattern:
            return ["Pattern not found"]

        for action in report.actions_to_take:
            result = self._execute_action(action, pattern)
            results.append(result)

        return results

    def _execute_action(self, action: str, pattern: Entity) -> str:
        """
        Execute a single fitness action.

        Supported actions:
        - transition(pattern.status='status')
        - emit('event_name', ...)
        - create(learning, title='...', source=pattern.id)
        - finalize(pattern)
        """
        action = action.strip()

        # Pattern status transition
        transition_match = re.match(
            r"transition\(pattern\.status=['\"](\w+)['\"]\)",
            action,
        )
        if transition_match:
            new_status = transition_match.group(1)
            old_status = pattern.status
            updated = pattern.copy(status=new_status)
            updated.data["updated"] = datetime.utcnow().isoformat()
            self.repository.update(updated)
            self.observer.emit(ChangeType.UPDATED, updated, old_status=old_status)
            return f"Transitioned pattern from '{old_status}' to '{new_status}'"

        # Emit event
        emit_match = re.match(r"emit\('([^']+)'", action)
        if emit_match:
            event_name = emit_match.group(1)
            # For now, just log the event (could integrate with observer)
            return f"Emitted event: {event_name}"

        # Create learning
        create_match = re.match(
            r"create\(learning,\s*title=['\"]([^'\"]+)['\"]",
            action,
        )
        if create_match:
            learning_title = create_match.group(1)
            try:
                from .factory import EntityFactory
                factory = EntityFactory(repository=self.repository)
                learning = factory.create(
                    "learning",
                    learning_title,
                    insight=f"Pattern {pattern.id} fitness evaluation result",
                    domain="epigenetic-bridge",
                    links=[pattern.id],
                )
                return f"Created learning: {learning.id}"
            except Exception as e:
                return f"Failed to create learning: {e}"

        # Finalize pattern
        if action.startswith("finalize(pattern"):
            # Mark as deprecated (actual finalization would be more complex)
            if pattern.status != "deprecated":
                updated = pattern.copy(status="deprecated")
                updated.data["updated"] = datetime.utcnow().isoformat()
                updated.data["finalized_at"] = datetime.utcnow().isoformat()
                self.repository.update(updated)
                self.observer.emit(ChangeType.UPDATED, updated, old_status=pattern.status)
            return f"Finalized pattern: {pattern.id}"

        return f"Unknown action: {action}"

    # =========================================================================
    # INHERIT PHASE - Execute recommendations from SELECT
    # =========================================================================

    def execute_recommendation(self, report: FitnessReport) -> Dict[str, Any]:
        """
        Execute a recommendation from the SELECT phase (INHERIT).

        This is the INHERIT phase - it applies the recommendation by:
        - Transitioning pattern status for promote/deprecate
        - Creating a learning entity capturing experiment outcomes
        - Doing nothing for "continue" recommendations

        Args:
            report: FitnessReport from evaluate_pattern()

        Returns:
            Dict with execution results:
            - action_taken: str ("promoted", "deprecated", "continued")
            - pattern_status: str (new status)
            - learning_id: Optional[str] (if learning created)
            - details: str (human-readable summary)
        """
        pattern = self.repository.read(report.pattern_id)
        if not pattern:
            return {
                "action_taken": "error",
                "pattern_status": None,
                "learning_id": None,
                "details": f"Pattern {report.pattern_id} not found",
            }

        if report.recommendation == "continue":
            return {
                "action_taken": "continued",
                "pattern_status": pattern.status,
                "learning_id": None,
                "details": f"Pattern {pattern.id} continues observation",
            }

        if report.recommendation == "promote":
            return self._execute_promotion(pattern, report)

        if report.recommendation == "deprecate":
            return self._execute_deprecation(pattern, report)

        return {
            "action_taken": "error",
            "pattern_status": pattern.status,
            "learning_id": None,
            "details": f"Unknown recommendation: {report.recommendation}",
        }

    def _execute_promotion(
        self, pattern: Entity, report: FitnessReport
    ) -> Dict[str, Any]:
        """Execute pattern promotion to adopted status."""
        old_status = pattern.status
        now = datetime.now(timezone.utc)

        # Update pattern status and add adoption metadata
        updated = pattern.copy(status="adopted")
        updated.data["adopted_at"] = now.isoformat()
        updated.data["experimental_duration_days"] = report.days_since_experimental
        updated.data["final_metrics"] = self._snapshot_metrics(report)
        self.repository.update(updated)

        # Emit event
        self.observer.emit(ChangeType.UPDATED, updated, old_status=old_status)

        # Create learning with experiment outcomes
        learning_id = self._create_experiment_learning(pattern, report, "promoted")

        return {
            "action_taken": "promoted",
            "pattern_status": "adopted",
            "learning_id": learning_id,
            "details": f"Pattern {pattern.id} promoted to adopted after {report.days_since_experimental} days",
        }

    def _execute_deprecation(
        self, pattern: Entity, report: FitnessReport
    ) -> Dict[str, Any]:
        """Execute pattern deprecation."""
        old_status = pattern.status
        now = datetime.now(timezone.utc)

        # Update pattern status and add deprecation metadata
        updated = pattern.copy(status="deprecated")
        updated.data["deprecated_at"] = now.isoformat()
        updated.data["deprecation_reason"] = "metrics_failed"
        updated.data["experimental_duration_days"] = report.days_since_experimental
        updated.data["final_metrics"] = self._snapshot_metrics(report)
        self.repository.update(updated)

        # Emit event
        self.observer.emit(ChangeType.UPDATED, updated, old_status=old_status)

        # Create learning with failure analysis
        learning_id = self._create_experiment_learning(pattern, report, "deprecated")

        return {
            "action_taken": "deprecated",
            "pattern_status": "deprecated",
            "learning_id": learning_id,
            "details": f"Pattern {pattern.id} deprecated: metrics not achieved",
        }

    def _snapshot_metrics(self, report: FitnessReport) -> Dict[str, Any]:
        """Create a snapshot of metrics for archival."""
        return {
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "observation_days": report.days_since_experimental,
            "sample_size": f"{report.sample_size_actual}/{report.sample_size_required}",
            "metrics": [
                {
                    "name": m.name,
                    "baseline": m.baseline,
                    "target": m.target,
                    "final_value": m.current_value,
                    "achieved": m.achieved,
                }
                for m in report.metrics
            ],
        }

    def _create_experiment_learning(
        self,
        pattern: Entity,
        report: FitnessReport,
        outcome: str,  # "promoted" or "deprecated"
    ) -> Optional[str]:
        """Create a learning entity capturing experiment outcomes."""
        try:
            from .factory import EntityFactory
            factory = EntityFactory(repository=self.repository)

            # Build comprehensive insight
            metrics_summary = "\n".join([
                f"  - {m.name}: {m.current_value} (target: {m.target}, "
                f"{'ACHIEVED' if m.achieved else 'FAILED'})"
                for m in report.metrics
            ])

            # Count affected entities
            target_type = pattern.data.get("mechanics", {}).get("target", "feature")
            affected_count = self._count_entities_with_pattern(pattern.id, target_type)

            conclusion = (
                "all success conditions were met"
                if outcome == "promoted"
                else "failure conditions were triggered - metrics did not meet targets"
            )

            insight = f"""## Experiment Outcome: {outcome.upper()}

**Pattern**: {pattern.data.get('name', pattern.id)}
**ID**: {pattern.id}

### Original Hypothesis
{pattern.data.get('description', 'No description provided')}

### Observation Period
- Duration: {report.days_since_experimental} days (required: {report.observation_period_days})
- Sample size: {report.sample_size_actual}/{report.sample_size_required} entities
- Entities affected: {affected_count} {target_type}s

### Metrics
{metrics_summary}

### Conclusion
Pattern was {outcome} because {conclusion}.
"""

            learning = factory.create(
                "learning",
                f"Pattern {pattern.id} {outcome}: experiment concluded",
                insight=insight.strip(),
                domain="epigenetic-experiment",
                links=[pattern.id],
                impact="high",
            )

            return learning.id

        except Exception as e:
            # Log but don't fail the promotion/deprecation
            return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all experimental patterns and their fitness status.

        Returns:
            Dict with pattern summaries
        """
        reports = self.evaluate_all()

        return {
            "total_patterns": len(reports),
            "ready_for_promotion": sum(1 for r in reports if r.recommendation == "promote"),
            "ready_for_deprecation": sum(1 for r in reports if r.recommendation == "deprecate"),
            "still_observing": sum(1 for r in reports if r.recommendation == "continue"),
            "patterns": [
                {
                    "id": r.pattern_id,
                    "name": r.pattern_name,
                    "days_observed": r.days_since_experimental,
                    "sample_size": f"{r.sample_size_actual}/{r.sample_size_required}",
                    "recommendation": r.recommendation,
                    "metrics": [
                        {
                            "name": m.name,
                            "current": m.current_value,
                            "target": m.target,
                            "achieved": m.achieved,
                        }
                        for m in r.metrics
                    ],
                }
                for r in reports
            ],
        }


# =============================================================================
# CANARY MONITOR - Early warning system for harmful patterns
# =============================================================================


class CanaryMonitor:
    """
    Canary Monitor - Early warning system for harmful (bricking) patterns.

    Detects three types of harmful behavior:
    1. Excessive Reversions - Pattern keeps reverting entities backward
    2. Negative Fitness Trend - Metrics getting worse over time
    3. Operation Failures - Create/update operations failing

    When bricking is detected, the monitor can auto-disable patterns
    and create learnings capturing what went wrong.

    Usage:
        monitor = CanaryMonitor(repository)
        alerts = monitor.check_all()

        for alert in alerts:
            if alert.severity == "critical":
                monitor.disable_pattern(alert.pattern_id)
    """

    def __init__(
        self,
        repository: "EntityRepository",
        observer: Optional[EntityObserver] = None,
        thresholds: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the canary monitor.

        Args:
            repository: EntityRepository for data access
            observer: EntityObserver for emitting events
            thresholds: Optional custom thresholds (defaults to CANARY_THRESHOLDS)
        """
        self.repository = repository
        self.observer = observer or get_observer()
        self.thresholds = thresholds or CANARY_THRESHOLDS.copy()
        self._evaluator = PatternEvaluator(repository, observer)

    def _load_experimental_patterns(self) -> List[Entity]:
        """Load all experimental schema-extension patterns."""
        return self._evaluator._load_experimental_patterns()

    def _get_reversion_count(self, pattern: Entity, window_days: int) -> int:
        """
        Count reversions (backward status transitions) for entities with this pattern.

        A reversion is when an entity moves backward in its lifecycle:
        - stable -> converging (quality gate reversion)
        - converging -> nascent (abandoned progress)

        Args:
            pattern: The pattern to check
            window_days: Number of days to look back

        Returns:
            Count of reversions in the window
        """
        target_type = pattern.data.get("mechanics", {}).get("target", "feature")
        reversion_count = 0

        # Look for entities with reversion markers
        try:
            entities = self.repository.list(entity_type=target_type, limit=500)
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

            for entity in entities:
                # Check if entity has this pattern
                epigenetics = entity.data.get("_epigenetics", [])
                if pattern.id not in epigenetics:
                    continue

                # Check for reversion marker
                last_reversion = entity.data.get("_last_reversion")
                if last_reversion:
                    try:
                        reversion_time = datetime.fromisoformat(
                            last_reversion.replace("Z", "+00:00")
                        )
                        if reversion_time.tzinfo is None:
                            reversion_time = reversion_time.replace(tzinfo=timezone.utc)
                        if reversion_time >= cutoff:
                            reversion_count += 1
                    except (ValueError, AttributeError):
                        pass

                # Also check for quality_gate_reversion flag (from quality-gate pattern)
                if entity.data.get("quality_gate_reversion"):
                    reversion_count += 1

        except Exception:
            pass

        return reversion_count

    def _check_reversions(self, pattern: Entity) -> Optional[CanaryAlert]:
        """
        Check if pattern is causing excessive reversions.

        Args:
            pattern: Pattern to check

        Returns:
            CanaryAlert if threshold exceeded, None otherwise
        """
        window_days = self.thresholds["reversion_window_days"]
        max_reversions = self.thresholds["reversion_count"]

        count = self._get_reversion_count(pattern, window_days)

        if count > max_reversions:
            severity = "critical" if count > max_reversions * 2 else "warning"
            return CanaryAlert(
                pattern_id=pattern.id,
                pattern_name=pattern.data.get("name", pattern.id),
                signal="excessive_reversions",
                severity=severity,
                details=f"{count} reversions in {window_days} days (threshold: {max_reversions})",
            )

        return None

    def _get_metric_history(self, pattern: Entity) -> List[Dict[str, Any]]:
        """
        Get historical metric values for a pattern.

        Metrics are stored in pattern.data._metric_history as snapshots.

        Args:
            pattern: Pattern to get history for

        Returns:
            List of metric snapshots, newest first
        """
        return pattern.data.get("_metric_history", [])

    def _check_fitness_trend(self, pattern: Entity) -> Optional[CanaryAlert]:
        """
        Check if pattern's fitness metrics are declining.

        Args:
            pattern: Pattern to check

        Returns:
            CanaryAlert if metrics declining, None otherwise
        """
        decline_count = self.thresholds["trend_decline_count"]
        history = self._get_metric_history(pattern)

        if len(history) < decline_count:
            return None  # Not enough data

        # Check each metric for declining trend
        declining_metrics = []

        # Get metric names from most recent snapshot
        if not history:
            return None

        recent = history[0]
        for metric_name, current_value in recent.get("metrics", {}).items():
            if current_value is None:
                continue

            # Look for declining trend
            consecutive_declines = 0
            prev_value = current_value

            for snapshot in history[1:decline_count + 1]:
                snap_value = snapshot.get("metrics", {}).get(metric_name)
                if snap_value is None:
                    break

                # Check if value is worse (depends on metric direction)
                # For now, assume lower is better (most common)
                if prev_value > snap_value:
                    consecutive_declines += 1
                else:
                    break
                prev_value = snap_value

            if consecutive_declines >= decline_count:
                declining_metrics.append(metric_name)

        if declining_metrics:
            severity = "critical" if len(declining_metrics) > 1 else "warning"
            return CanaryAlert(
                pattern_id=pattern.id,
                pattern_name=pattern.data.get("name", pattern.id),
                signal="negative_trend",
                severity=severity,
                details=f"Declining metrics: {', '.join(declining_metrics)}",
            )

        return None

    def _get_operation_stats(self, pattern: Entity) -> Dict[str, int]:
        """
        Get operation statistics for entities with this pattern.

        Stats are stored in pattern.data._operation_stats.

        Args:
            pattern: Pattern to get stats for

        Returns:
            Dict with total_operations and failed_operations
        """
        return pattern.data.get("_operation_stats", {
            "total_operations": 0,
            "failed_operations": 0,
        })

    def _check_failure_rate(self, pattern: Entity) -> Optional[CanaryAlert]:
        """
        Check if pattern is causing high operation failure rates.

        Args:
            pattern: Pattern to check

        Returns:
            CanaryAlert if failure rate too high, None otherwise
        """
        min_ops = self.thresholds["min_operations"]
        max_rate = self.thresholds["failure_rate"]

        stats = self._get_operation_stats(pattern)
        total = stats.get("total_operations", 0)
        failed = stats.get("failed_operations", 0)

        if total < min_ops:
            return None  # Not enough data

        failure_rate = failed / total if total > 0 else 0

        if failure_rate > max_rate:
            severity = "critical" if failure_rate > max_rate * 2 else "warning"
            return CanaryAlert(
                pattern_id=pattern.id,
                pattern_name=pattern.data.get("name", pattern.id),
                signal="failure_spike",
                severity=severity,
                details=f"{failure_rate:.1%} failure rate ({failed}/{total} operations)",
            )

        return None

    def check_pattern(self, pattern: Entity) -> List[CanaryAlert]:
        """
        Check a single pattern for bricking signals.

        Args:
            pattern: Pattern to check

        Returns:
            List of alerts (empty if pattern is healthy)
        """
        alerts = []

        # Check all signal types
        reversion_alert = self._check_reversions(pattern)
        if reversion_alert:
            alerts.append(reversion_alert)

        trend_alert = self._check_fitness_trend(pattern)
        if trend_alert:
            alerts.append(trend_alert)

        failure_alert = self._check_failure_rate(pattern)
        if failure_alert:
            alerts.append(failure_alert)

        return alerts

    def check_all(self) -> List[CanaryAlert]:
        """
        Check all experimental patterns for bricking signals.

        Returns:
            List of all alerts across all patterns
        """
        alerts = []
        patterns = self._load_experimental_patterns()

        for pattern in patterns:
            pattern_alerts = self.check_pattern(pattern)
            alerts.extend(pattern_alerts)

        return alerts

    def disable_pattern(
        self,
        pattern_id: str,
        reason: str = "Bricking detected by canary",
        create_learning: bool = True,
    ) -> Optional[str]:
        """
        Disable a pattern that is causing harm.

        Args:
            pattern_id: ID of pattern to disable
            reason: Reason for disabling
            create_learning: Whether to create a learning from the incident

        Returns:
            Learning ID if created, None otherwise
        """
        pattern = self.repository.read(pattern_id)
        if not pattern:
            return None

        # Transition to deprecated
        old_status = pattern.status
        updated = pattern.copy(status="deprecated")
        updated.data["disabled_by_canary"] = True
        updated.data["disabled_at"] = datetime.now(timezone.utc).isoformat()
        updated.data["disabled_reason"] = reason
        self.repository.update(updated)

        # Emit event
        self.observer.emit(
            ChangeType.UPDATED,
            updated,
            old_status=old_status,
        )

        learning_id = None

        # Create learning if requested
        if create_learning:
            try:
                from .factory import EntityFactory
                factory = EntityFactory(repository=self.repository)
                learning = factory.create(
                    "learning",
                    f"Pattern {pattern_id} disabled by canary",
                    insight=f"""
Pattern was automatically disabled due to harmful behavior.

Reason: {reason}
Pattern: {pattern_id}
Previous status: {old_status}

This is a safety mechanism to prevent experimental patterns from causing
widespread damage. Review the pattern definition and consider whether:
1. The pattern's hooks are too aggressive
2. The fitness criteria are misconfigured
3. The pattern should be deprecated permanently
""".strip(),
                    domain="epigenetic-canary",
                    links=[pattern_id],
                )
                learning_id = learning.id
            except Exception:
                pass

        return learning_id

    def auto_disable(self, alert: CanaryAlert) -> Dict[str, Any]:
        """
        Automatically disable a pattern based on a critical canary alert.

        This is the emergency deprecation path - no observation period,
        immediate status transition to protect the system.

        Args:
            alert: CanaryAlert with severity information

        Returns:
            Dict with execution results:
            - action_taken: str ("disabled", "skipped")
            - pattern_status: str (new status if changed)
            - learning_id: Optional[str] (if learning created)
            - details: str (human-readable summary)
        """
        # Only auto-disable on critical alerts
        if alert.severity != "critical":
            return {
                "action_taken": "skipped",
                "pattern_status": None,
                "learning_id": None,
                "details": f"Alert severity '{alert.severity}' does not require auto-disable",
            }

        pattern = self.repository.read(alert.pattern_id)
        if not pattern:
            return {
                "action_taken": "error",
                "pattern_status": None,
                "learning_id": None,
                "details": f"Pattern {alert.pattern_id} not found",
            }

        # Already deprecated, nothing to do
        if pattern.status == "deprecated":
            return {
                "action_taken": "skipped",
                "pattern_status": "deprecated",
                "learning_id": None,
                "details": "Pattern already deprecated",
            }

        old_status = pattern.status
        now = datetime.now(timezone.utc)

        # Update pattern status with full alert context
        updated = pattern.copy(status="deprecated")
        updated.data["disabled_by_canary"] = True
        updated.data["disabled_at"] = now.isoformat()
        updated.data["disabled_reason"] = alert.details
        updated.data["canary_signal"] = alert.signal
        updated.data["canary_severity"] = alert.severity
        self.repository.update(updated)

        # Emit event
        self.observer.emit(ChangeType.UPDATED, updated, old_status=old_status)

        # Mark alert as handled
        alert.auto_disabled = True

        # Create learning with alert details
        learning_id = self._create_canary_learning(pattern, alert)

        return {
            "action_taken": "disabled",
            "pattern_status": "deprecated",
            "learning_id": learning_id,
            "alert_signal": alert.signal,
            "details": f"Pattern {pattern.id} emergency-disabled: {alert.details}",
        }

    def _create_canary_learning(
        self, pattern: Entity, alert: CanaryAlert
    ) -> Optional[str]:
        """Create a learning entity capturing canary alert details."""
        try:
            from .factory import EntityFactory
            factory = EntityFactory(repository=self.repository)

            insight = f"""## Canary Alert: Pattern Emergency Disabled

**Pattern**: {pattern.data.get('name', pattern.id)}
**ID**: {pattern.id}

### Alert Details
- Signal: {alert.signal}
- Severity: {alert.severity}
- Detected at: {alert.detected_at.isoformat()}

### Reason
{alert.details}

### Action Taken
Pattern was automatically disabled to prevent further harm.
This is a safety mechanism - review the pattern definition and consider:
1. Whether the pattern's hooks are too aggressive
2. If the fitness criteria are misconfigured
3. Whether the pattern should be deprecated permanently
"""

            learning = factory.create(
                "learning",
                f"Canary disabled pattern {pattern.id}: {alert.signal}",
                insight=insight.strip(),
                domain="epigenetic-canary",
                links=[pattern.id],
                impact="high",
            )

            return learning.id

        except Exception:
            return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of canary status for all patterns.

        Returns:
            Dict with alerts and overall health status
        """
        alerts = self.check_all()
        patterns = self._load_experimental_patterns()

        critical_count = sum(1 for a in alerts if a.severity == "critical")
        warning_count = sum(1 for a in alerts if a.severity == "warning")

        # Determine overall health
        if critical_count > 0:
            health = "critical"
        elif warning_count > 0:
            health = "warning"
        else:
            health = "healthy"

        return {
            "health": health,
            "total_patterns": len(patterns),
            "critical_alerts": critical_count,
            "warning_alerts": warning_count,
            "alerts": [
                {
                    "pattern_id": a.pattern_id,
                    "pattern_name": a.pattern_name,
                    "signal": a.signal,
                    "severity": a.severity,
                    "details": a.details,
                }
                for a in alerts
            ],
        }


# =============================================================================
# PATTERN INDUCTOR - Learning analysis and pattern proposal system
# =============================================================================

# Induction thresholds
INDUCTION_THRESHOLDS = {
    "min_learnings": 3,          # Minimum learnings to propose pattern
    "confidence_threshold": 0.6,  # Minimum confidence to show proposal
    "max_proposals": 3,           # Maximum proposals per check
    "keyword_overlap": 0.05,      # Legacy Jaccard threshold (fallback)
    "embedding_similarity": 0.70, # Cosine similarity threshold for embeddings
}

# Cross-domain thresholds (Experiment 4: Cross-Domain Pollination)
CROSS_DOMAIN_THRESHOLDS = {
    "min_domains": 2,              # Minimum domains to bridge
    "embedding_similarity": 0.85,  # Higher bar than within-domain (0.70)
    "min_learnings_per_domain": 1, # At least 1 learning per domain
    "min_total_learnings": 3,      # Minimum learnings total
    "confidence_boost": 0.1,       # Bonus confidence for cross-domain
}


@dataclass
class PatternProposal:
    """A proposed pattern synthesized from learnings."""
    id: str  # Proposed pattern ID
    name: str
    description: str
    source_learnings: List[str]  # IDs of learnings that informed this
    domain: str
    confidence: float  # 0.0 to 1.0
    suggested_target: str  # Entity type this pattern would target
    suggested_fields: Dict[str, Any]  # Fields to inject
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Cross-domain support (Experiment 4)
    cross_domain: bool = False  # Is this a bridge pattern?
    source_domains: List[str] = field(default_factory=list)  # Domains this bridges
    bridge_strength: float = 0.0  # Semantic similarity across domains


class PatternInductor:
    """
    Pattern Inductor - Analyzes learnings and proposes new patterns.

    This closes the autoevolution loop by enabling:
    - System analyzes learnings → System proposes mutation → Human approves

    The inductor:
    1. Clusters learnings by domain and semantic similarity (embeddings)
    2. Identifies clusters with recurring themes (>= 3 learnings)
    3. Synthesizes pattern proposals from clusters
    4. Presents proposals with confidence scores

    Usage:
        inductor = PatternInductor(repository)
        proposals = inductor.analyze()

        for proposal in proposals:
            if proposal.confidence >= 0.7:
                inductor.approve_proposal(proposal)
    """

    def __init__(
        self,
        repository: "EntityRepository",
        thresholds: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the pattern inductor.

        Args:
            repository: EntityRepository for data access
            thresholds: Optional custom thresholds
        """
        self.repository = repository
        self.thresholds = thresholds or INDUCTION_THRESHOLDS.copy()
        self._embedding_service = None  # Lazy-loaded
        self._embeddings_available = None  # Cached availability check

    @property
    def embedding_service(self):
        """Lazy-load the embedding service if available."""
        if self._embedding_service is None and self._embeddings_available is not False:
            try:
                from .embeddings import EmbeddingService
                self._embedding_service = EmbeddingService(self.repository.db_path)
                self._embeddings_available = True
            except ImportError:
                self._embeddings_available = False
        return self._embedding_service

    @property
    def embeddings_available(self) -> bool:
        """Check if embeddings are available."""
        if self._embeddings_available is None:
            # Trigger lazy load attempt
            _ = self.embedding_service
        return self._embeddings_available or False

    def _load_learnings(self, status: Optional[str] = None) -> List[Entity]:
        """Load learnings from repository."""
        try:
            learnings = self.repository.list(
                entity_type="learning",
                status=status,
                limit=200
            )
            return learnings
        except Exception:
            return []

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text for clustering."""
        if not text:
            return []

        # Simple keyword extraction - lowercase, remove common words
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "dare", "ought", "used", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between", "under",
            "again", "further", "then", "once", "here", "there", "when",
            "where", "why", "how", "all", "each", "few", "more", "most",
            "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "just", "and", "but",
            "if", "or", "because", "until", "while", "this", "that", "these",
            "those", "it", "its", "they", "them", "their", "we", "our", "you",
        }

        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in stopwords]

        # Return unique keywords
        return list(set(keywords))

    def _calculate_keyword_overlap(
        self, keywords1: List[str], keywords2: List[str]
    ) -> float:
        """Calculate Jaccard similarity between keyword sets (fallback method)."""
        if not keywords1 or not keywords2:
            return 0.0

        set1 = set(keywords1)
        set2 = set(keywords2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _calculate_semantic_similarity(
        self, entity1: Entity, entity2: Entity
    ) -> float:
        """
        Calculate semantic similarity between entities using embeddings.

        Falls back to Jaccard keyword overlap if embeddings unavailable.

        Args:
            entity1: First entity
            entity2: Second entity

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if self.embeddings_available:
            try:
                emb1 = self.embedding_service.get_or_create_embedding(entity1)
                emb2 = self.embedding_service.get_or_create_embedding(entity2)
                return self.embedding_service.cosine_similarity(emb1, emb2)
            except Exception:
                pass  # Fall back to Jaccard

        # Fallback: Jaccard keyword overlap
        text1 = f"{entity1.data.get('name', '')} {entity1.data.get('insight', '')}"
        text2 = f"{entity2.data.get('name', '')} {entity2.data.get('insight', '')}"
        keywords1 = self._extract_keywords(text1)
        keywords2 = self._extract_keywords(text2)
        return self._calculate_keyword_overlap(keywords1, keywords2)

    def _get_similarity_threshold(self) -> float:
        """Get the appropriate similarity threshold based on available method."""
        if self.embeddings_available:
            return self.thresholds.get("embedding_similarity", 0.70)
        return self.thresholds.get("keyword_overlap", 0.05)

    def _cluster_learnings(self) -> Dict[str, List[Entity]]:
        """
        Cluster learnings by domain and semantic similarity.

        Uses vector embeddings when available for more accurate semantic
        clustering. Falls back to Jaccard keyword overlap otherwise.

        Returns:
            Dict mapping cluster key to list of learnings
        """
        learnings = self._load_learnings()
        clusters: Dict[str, List[Entity]] = {}

        for learning in learnings:
            domain = learning.data.get("domain", "general")

            # Primary clustering by domain
            if domain not in clusters:
                clusters[domain] = []
            clusters[domain].append(learning)

        # Secondary clustering within domains by semantic similarity
        refined_clusters: Dict[str, List[Entity]] = {}
        similarity_threshold = self._get_similarity_threshold()

        for domain, domain_learnings in clusters.items():
            if len(domain_learnings) < self.thresholds["min_learnings"]:
                # Not enough learnings to cluster further
                refined_clusters[domain] = domain_learnings
                continue

            # Use embeddings for batch efficiency if available
            if self.embeddings_available:
                try:
                    # Batch compute embeddings for efficiency
                    self.embedding_service.batch_embed_entities(domain_learnings)
                except Exception:
                    pass  # Will fall back to per-pair calculation

            # Simple greedy clustering: group learnings with semantic similarity
            used = set()
            cluster_idx = 0

            for learning in domain_learnings:
                if learning.id in used:
                    continue

                cluster_key = f"{domain}_{cluster_idx}"
                refined_clusters[cluster_key] = [learning]
                used.add(learning.id)

                # Find semantically similar learnings
                for other in domain_learnings:
                    if other.id in used:
                        continue

                    similarity = self._calculate_semantic_similarity(learning, other)

                    if similarity >= similarity_threshold:
                        refined_clusters[cluster_key].append(other)
                        used.add(other.id)

                cluster_idx += 1

        return refined_clusters

    def _generate_proposal(
        self, cluster_key: str, learnings: List[Entity]
    ) -> Optional[PatternProposal]:
        """
        Generate a pattern proposal from a cluster of learnings.

        Args:
            cluster_key: Identifier for the cluster
            learnings: List of learnings in the cluster

        Returns:
            PatternProposal if viable, None otherwise
        """
        min_learnings = self.thresholds["min_learnings"]

        if len(learnings) < min_learnings:
            return None

        # Extract domain from cluster key
        domain = cluster_key.split("_")[0] if "_" in cluster_key else cluster_key

        # Synthesize name from learning names
        learning_names = [l.data.get("name", "") for l in learnings]
        common_words = self._find_common_theme(learning_names)
        proposed_name = f"Pattern from {domain}: {common_words}" if common_words else f"Pattern from {domain}"

        # Synthesize description from insights
        insights = [l.data.get("insight", "") for l in learnings]
        combined_insight = self._synthesize_insights(insights)

        # Calculate confidence based on cluster coherence
        confidence = self._calculate_confidence(learnings)

        # Generate proposed pattern ID
        slug = re.sub(r'[^a-z0-9]+', '-', proposed_name.lower()).strip('-')[:40]
        pattern_id = f"pattern-proposed-{slug}"

        return PatternProposal(
            id=pattern_id,
            name=proposed_name,
            description=combined_insight,
            source_learnings=[l.id for l in learnings],
            domain=domain,
            confidence=confidence,
            suggested_target="feature",  # Default to feature
            suggested_fields={},  # To be refined by human
        )

    def _find_common_theme(self, names: List[str]) -> str:
        """Find common theme from a list of names."""
        if not names:
            return ""

        # Extract keywords from all names
        all_keywords = []
        for name in names:
            all_keywords.extend(self._extract_keywords(name))

        if not all_keywords:
            return ""

        # Find most common keywords
        from collections import Counter
        counts = Counter(all_keywords)
        common = counts.most_common(3)

        return " ".join(word for word, _ in common)

    def _synthesize_insights(self, insights: List[str]) -> str:
        """Combine multiple insights into a synthesized description."""
        if not insights:
            return ""

        # Filter empty insights
        valid_insights = [i.strip() for i in insights if i and i.strip()]

        if not valid_insights:
            return ""

        if len(valid_insights) == 1:
            return valid_insights[0]

        # Combine insights with attribution
        synthesized = "Combined wisdom from multiple learnings:\n\n"
        for i, insight in enumerate(valid_insights[:5], 1):  # Limit to 5
            # Truncate long insights
            truncated = insight[:200] + "..." if len(insight) > 200 else insight
            synthesized += f"{i}. {truncated}\n\n"

        return synthesized.strip()

    def _calculate_confidence(self, learnings: List[Entity]) -> float:
        """
        Calculate confidence score for a pattern proposal.

        Factors:
        - Number of learnings (more = higher confidence)
        - Semantic coherence (higher = more related)
        """
        if not learnings:
            return 0.0

        # Base confidence from count
        min_learnings = self.thresholds["min_learnings"]
        count_factor = min(len(learnings) / (min_learnings * 2), 1.0)

        # Semantic coherence factor
        if len(learnings) >= 2:
            total_similarity = 0.0
            comparisons = 0
            for i, l1 in enumerate(learnings):
                for l2 in learnings[i + 1:]:
                    total_similarity += self._calculate_semantic_similarity(l1, l2)
                    comparisons += 1
            coherence_factor = total_similarity / comparisons if comparisons > 0 else 0.0
        else:
            coherence_factor = 0.5

        # Combined confidence
        confidence = (count_factor * 0.6) + (coherence_factor * 0.4)

        return min(confidence, 1.0)

    def analyze(self, include_cross_domain: bool = False) -> List[PatternProposal]:
        """
        Analyze learnings and generate pattern proposals.

        Args:
            include_cross_domain: If True, also detect cross-domain bridges
                                  (Experiment 4: Cross-Domain Pollination)

        Returns:
            List of pattern proposals sorted by confidence
        """
        clusters = self._cluster_learnings()
        proposals = []

        for cluster_key, learnings in clusters.items():
            proposal = self._generate_proposal(cluster_key, learnings)
            if proposal and proposal.confidence >= self.thresholds["confidence_threshold"]:
                proposals.append(proposal)

        # Cross-domain proposals (opt-in)
        if include_cross_domain:
            cross_domain_proposals = self._detect_cross_domain_bridges(clusters)
            proposals.extend(cross_domain_proposals)

        # Sort by confidence and limit
        proposals.sort(key=lambda p: p.confidence, reverse=True)
        max_proposals = self.thresholds["max_proposals"]

        return proposals[:max_proposals]

    def _detect_cross_domain_bridges(
        self, domain_clusters: Dict[str, List[Entity]]
    ) -> List[PatternProposal]:
        """
        Detect bridge opportunities across domain boundaries.

        Algorithm:
        1. Group clusters by their primary domain
        2. Compare representative learnings across domains using embeddings
        3. When similarity exceeds threshold, generate cross-domain proposal
        4. Mark proposals with cross_domain=True

        Args:
            domain_clusters: Dict of cluster_key -> learnings (from _cluster_learnings)

        Returns:
            List of cross-domain PatternProposals
        """
        # Check for configurable cross_domain_similarity in thresholds
        if "cross_domain_similarity" in self.thresholds:
            cross_threshold = self.thresholds["cross_domain_similarity"]
        elif self.embeddings_available:
            cross_threshold = CROSS_DOMAIN_THRESHOLDS["embedding_similarity"]
        else:
            cross_threshold = 0.3  # Lower threshold for keyword-based fallback

        min_learnings = CROSS_DOMAIN_THRESHOLDS["min_total_learnings"]

        # Group clusters by primary domain (domain_0 -> domain)
        domain_groups: Dict[str, List[Entity]] = {}
        for cluster_key, learnings in domain_clusters.items():
            # Extract primary domain from cluster key (e.g., "testing_0" -> "testing")
            primary_domain = cluster_key.split("_")[0] if "_" in cluster_key else cluster_key
            if primary_domain not in domain_groups:
                domain_groups[primary_domain] = []
            domain_groups[primary_domain].extend(learnings)

        # Need at least 2 domains for cross-domain
        domains = list(domain_groups.keys())
        if len(domains) < 2:
            return []

        # Collect domain representatives (first learning from each domain)
        domain_reps: Dict[str, Entity] = {}
        for domain, learnings in domain_groups.items():
            if learnings:
                domain_reps[domain] = learnings[0]

        # Find bridge candidates by comparing domain representatives
        bridges: List[PatternProposal] = []
        checked_pairs: set = set()

        for i, domain_a in enumerate(domains):
            for domain_b in domains[i + 1:]:
                pair_key = tuple(sorted([domain_a, domain_b]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                rep_a = domain_reps.get(domain_a)
                rep_b = domain_reps.get(domain_b)
                if not rep_a or not rep_b:
                    continue

                # Calculate cross-domain similarity
                similarity = self._calculate_semantic_similarity(rep_a, rep_b)

                if similarity >= cross_threshold:
                    # Combine learnings from both domains
                    bridge_learnings = (
                        domain_groups[domain_a][:5] +
                        domain_groups[domain_b][:5]
                    )

                    if len(bridge_learnings) >= min_learnings:
                        proposal = self._generate_cross_domain_proposal(
                            domains=[domain_a, domain_b],
                            learnings=bridge_learnings,
                            bridge_strength=similarity,
                        )
                        if proposal:
                            bridges.append(proposal)

        return bridges

    def _generate_cross_domain_proposal(
        self,
        domains: List[str],
        learnings: List[Entity],
        bridge_strength: float,
    ) -> Optional[PatternProposal]:
        """Generate a cross-domain pattern proposal."""
        if len(learnings) < CROSS_DOMAIN_THRESHOLDS["min_total_learnings"]:
            return None

        domain_str = " + ".join(sorted(domains)[:3])

        # Extract insights from learnings
        insights = [l.data.get("insight", "") for l in learnings if l.data.get("insight")]
        combined_insight = " ".join(insights[:3])[:500]

        # Find common theme from learning names
        names = [l.data.get("name", "") for l in learnings]
        common_words = self._find_common_words(names)
        common_theme = " ".join(common_words[:3]) if common_words else "shared pattern"

        proposed_name = f"Bridge pattern ({domain_str}): {common_theme}"

        # Calculate confidence with boost for cross-domain
        base_confidence = self._calculate_confidence(learnings)
        confidence_boost = CROSS_DOMAIN_THRESHOLDS.get("confidence_boost", 0.1)
        confidence = min(base_confidence + confidence_boost, 1.0)

        # Generate slug and ID
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', proposed_name.lower()).strip('-')[:40]
        pattern_id = f"pattern-bridge-{slug}"

        return PatternProposal(
            id=pattern_id,
            name=proposed_name,
            description=combined_insight,
            source_learnings=[l.id for l in learnings],
            domain=domains[0],  # Primary domain
            confidence=confidence,
            suggested_target="feature",
            suggested_fields={},
            cross_domain=True,
            source_domains=sorted(domains),
            bridge_strength=bridge_strength,
        )

    def _find_common_words(self, texts: List[str]) -> List[str]:
        """Find common words across multiple texts."""
        if not texts:
            return []

        # Simple common word extraction
        word_counts: Dict[str, int] = {}
        stopwords = {"the", "a", "an", "is", "are", "in", "on", "for", "to", "of", "and", "about"}

        for text in texts:
            words = set(text.lower().split())
            for word in words:
                if word not in stopwords and len(word) > 2:
                    word_counts[word] = word_counts.get(word, 0) + 1

        # Return words that appear in at least half the texts
        threshold = len(texts) / 2
        common = [word for word, count in word_counts.items() if count >= threshold]
        return sorted(common, key=lambda w: word_counts[w], reverse=True)

    def _get_current_loop_generation(self) -> int:
        """
        Determine the current loop generation.

        Generation 1: Manually created or first-wave induced patterns
        Generation N+1: Patterns induced from learnings about generation N patterns
        """
        max_gen = 0
        try:
            patterns = self.repository.list(entity_type="pattern", limit=100)
            for p in patterns:
                gen = p.data.get("loop_generation", 0)
                if isinstance(gen, int) and gen > max_gen:
                    max_gen = gen
        except Exception:
            pass
        return max(max_gen, 1)  # At least generation 1

    def approve_proposal(self, proposal: PatternProposal) -> Optional[Entity]:
        """
        Approve a proposal and create an experimental pattern.

        Args:
            proposal: The proposal to approve

        Returns:
            Created pattern entity, or None if failed
        """
        from .factory import EntityFactory
        factory = EntityFactory(repository=self.repository)

        # Determine loop generation for meta-tracking
        current_generation = self._get_current_loop_generation()
        induced_from_count = len(proposal.source_learnings)

        # Build context description
        if proposal.cross_domain:
            domain_str = " + ".join(proposal.source_domains)
            context_desc = f"Cross-domain bridge from {induced_from_count} learnings spanning '{domain_str}'"
        else:
            context_desc = f"Induced from {induced_from_count} learnings in domain '{proposal.domain}'"

        # Create the pattern - don't pass status, let factory use default
        pattern = factory.create(
            "pattern",
            proposal.name,
            description=proposal.description,
            subtype="schema-extension",
            context=context_desc,
            problem=f"Multiple learnings suggest a pattern opportunity",
            solution=proposal.description,
            mechanics={
                "target": proposal.suggested_target,
                "inject_fields": proposal.suggested_fields,
                "hooks": [],
                "fitness": {
                    "observation_period": "90 days",
                    "sample_size": 10,
                    "metrics": [],
                },
            },
            induced_from=proposal.source_learnings,
            induction_confidence=proposal.confidence,
            # Meta-loop tracking fields (Experiment 2)
            loop_generation=current_generation,
            induced_from_count=induced_from_count,
            # Cross-domain tracking fields (Experiment 4)
            cross_domain=proposal.cross_domain,
            source_domains=proposal.source_domains if proposal.cross_domain else [],
            bridge_strength=proposal.bridge_strength if proposal.cross_domain else 0.0,
        )

        # Mark source learnings as applied
        for learning_id in proposal.source_learnings:
            try:
                learning = self.repository.read(learning_id)
                if learning and learning.status != "applied":
                    updated = learning.copy(status="applied")
                    updated.data["applied_to"] = pattern.id
                    self.repository.update(updated)
            except Exception:
                pass  # Skip if learning can't be updated

        return pattern

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of induction status.

        Returns:
            Dict with proposals and stats
        """
        proposals = self.analyze()
        learnings = self._load_learnings()

        # Count learnings by status
        captured = sum(1 for l in learnings if l.status == "captured")
        validated = sum(1 for l in learnings if l.status == "validated")
        applied = sum(1 for l in learnings if l.status == "applied")

        return {
            "total_learnings": len(learnings),
            "captured": captured,
            "validated": validated,
            "applied": applied,
            "proposals_count": len(proposals),
            "proposals": [
                {
                    "id": p.id,
                    "name": p.name,
                    "domain": p.domain,
                    "confidence": p.confidence,
                    "source_count": len(p.source_learnings),
                }
                for p in proposals
            ],
        }
