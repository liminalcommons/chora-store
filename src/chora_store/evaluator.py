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
        if experimental_since:
            try:
                since_date = datetime.fromisoformat(experimental_since.replace("Z", "+00:00"))
                return (datetime.utcnow() - since_date.replace(tzinfo=None)).days
            except (ValueError, AttributeError):
                pass

        # Fall back to created_at
        return (datetime.utcnow() - pattern.created_at).days

    def _count_entities_with_pattern(
        self,
        pattern_id: str,
        entity_type: str,
        status: Optional[str] = None,
        field_condition: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Count entities created with a pattern's epigenetics.

        Args:
            pattern_id: ID of the pattern
            entity_type: Type of entities to count
            status: Optional status filter
            field_condition: Optional dict of field=value conditions

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

                # Check additional field conditions
                if field_condition:
                    match = True
                    for field_name, expected_value in field_condition.items():
                        actual_value = entity.data.get(field_name)
                        if actual_value != expected_value:
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

        # Handle avg queries (simplified)
        avg_match = re.match(r"avg\((.+?)\)", query, re.IGNORECASE | re.DOTALL)
        if avg_match:
            # For now, return None for avg queries (complex to implement)
            return None

        return None

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
        not_null_matches = re.findall(r"(\w+)\s+IS\s+NOT\s+NULL", conditions, re.IGNORECASE)
        for field_name in not_null_matches:
            # We'll interpret IS NOT NULL as "field exists and is not empty"
            pass  # Can't easily express this in count function

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
            pattern_id, entity_type, status, field_conditions if field_conditions else None
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
    "keyword_overlap": 0.3,       # Minimum keyword overlap for clustering
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


class PatternInductor:
    """
    Pattern Inductor - Analyzes learnings and proposes new patterns.

    This closes the autoevolution loop by enabling:
    - System analyzes learnings → System proposes mutation → Human approves

    The inductor:
    1. Clusters learnings by domain and keyword similarity
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
        """Calculate Jaccard similarity between keyword sets."""
        if not keywords1 or not keywords2:
            return 0.0

        set1 = set(keywords1)
        set2 = set(keywords2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _cluster_learnings(self) -> Dict[str, List[Entity]]:
        """
        Cluster learnings by domain and keyword similarity.

        Returns:
            Dict mapping cluster key to list of learnings
        """
        learnings = self._load_learnings()
        clusters: Dict[str, List[Entity]] = {}

        for learning in learnings:
            domain = learning.data.get("domain", "general")
            insight = learning.data.get("insight", "")
            name = learning.data.get("name", "")

            # Primary clustering by domain
            if domain not in clusters:
                clusters[domain] = []
            clusters[domain].append(learning)

        # Secondary clustering within domains by keyword similarity
        refined_clusters: Dict[str, List[Entity]] = {}

        for domain, domain_learnings in clusters.items():
            if len(domain_learnings) < self.thresholds["min_learnings"]:
                # Not enough learnings to cluster further
                refined_clusters[domain] = domain_learnings
                continue

            # Extract keywords for each learning
            learning_keywords = {}
            for l in domain_learnings:
                text = f"{l.data.get('name', '')} {l.data.get('insight', '')}"
                learning_keywords[l.id] = self._extract_keywords(text)

            # Simple clustering: group learnings with overlapping keywords
            used = set()
            cluster_idx = 0

            for learning in domain_learnings:
                if learning.id in used:
                    continue

                cluster_key = f"{domain}_{cluster_idx}"
                refined_clusters[cluster_key] = [learning]
                used.add(learning.id)

                # Find similar learnings
                for other in domain_learnings:
                    if other.id in used:
                        continue

                    overlap = self._calculate_keyword_overlap(
                        learning_keywords[learning.id],
                        learning_keywords[other.id]
                    )

                    if overlap >= self.thresholds["keyword_overlap"]:
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
        - Keyword overlap (higher = more coherent)
        - Recency (recent learnings = higher relevance)
        """
        if not learnings:
            return 0.0

        # Base confidence from count
        min_learnings = self.thresholds["min_learnings"]
        count_factor = min(len(learnings) / (min_learnings * 2), 1.0)

        # Keyword coherence factor
        if len(learnings) >= 2:
            total_overlap = 0.0
            comparisons = 0
            for i, l1 in enumerate(learnings):
                for l2 in learnings[i + 1:]:
                    text1 = f"{l1.data.get('name', '')} {l1.data.get('insight', '')}"
                    text2 = f"{l2.data.get('name', '')} {l2.data.get('insight', '')}"
                    keywords1 = self._extract_keywords(text1)
                    keywords2 = self._extract_keywords(text2)
                    total_overlap += self._calculate_keyword_overlap(keywords1, keywords2)
                    comparisons += 1
            coherence_factor = total_overlap / comparisons if comparisons > 0 else 0.0
        else:
            coherence_factor = 0.5

        # Combined confidence
        confidence = (count_factor * 0.6) + (coherence_factor * 0.4)

        return min(confidence, 1.0)

    def analyze(self) -> List[PatternProposal]:
        """
        Analyze learnings and generate pattern proposals.

        Returns:
            List of pattern proposals sorted by confidence
        """
        clusters = self._cluster_learnings()
        proposals = []

        for cluster_key, learnings in clusters.items():
            proposal = self._generate_proposal(cluster_key, learnings)
            if proposal and proposal.confidence >= self.thresholds["confidence_threshold"]:
                proposals.append(proposal)

        # Sort by confidence and limit
        proposals.sort(key=lambda p: p.confidence, reverse=True)
        max_proposals = self.thresholds["max_proposals"]

        return proposals[:max_proposals]

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

        # Create the pattern - don't pass status, let factory use default
        pattern = factory.create(
            "pattern",
            proposal.name,
            description=proposal.description,
            subtype="schema-extension",
            context=f"Induced from {len(proposal.source_learnings)} learnings in domain '{proposal.domain}'",
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
