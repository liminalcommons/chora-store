"""
Visibility Module: Making the Autoevolutionary Loop Observable.

This module provides tools to observe the autoevolutionary loop:
- canary_alerts: Surface active canary alerts from experimental patterns
- entities_by_pattern: List entities affected by a specific pattern
- autoevolution_status: Dashboard view of experimental pattern progress

These tools complete the observability story for:
    LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT -> (observe)
"""

from typing import List, Dict, Any, Optional
from ..evaluator import PatternEvaluator, CanaryMonitor, CanaryAlert


def tool_canary_alerts(repository, severity_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Surface active canary alerts from all experimental patterns.

    Canary alerts indicate patterns that may be causing harm:
    - excessive_reversions: Pattern is reverting entities backward
    - negative_trend: Fitness metrics are declining
    - failure_spike: High operation failure rate

    Args:
        repository: EntityRepository for data access
        severity_filter: Optional filter for "critical" or "warning"

    Returns:
        Dict with alerts list and summary counts
    """
    monitor = CanaryMonitor(repository)
    alerts = monitor.check_all()

    # Filter by severity if requested
    if severity_filter:
        alerts = [a for a in alerts if a.severity == severity_filter]

    # Build response
    alert_list = [
        {
            "pattern_id": alert.pattern_id,
            "pattern_name": alert.pattern_name,
            "severity": alert.severity,
            "signal": alert.signal,
            "details": alert.details,
            "detected_at": alert.detected_at.isoformat() if hasattr(alert.detected_at, 'isoformat') else str(alert.detected_at),
        }
        for alert in alerts
    ]

    # Count by severity
    critical_count = len([a for a in alerts if a.severity == "critical"])
    warning_count = len([a for a in alerts if a.severity == "warning"])

    return {
        "total": len(alerts),
        "critical": critical_count,
        "warning": warning_count,
        "alerts": alert_list,
        "summary": (
            f"🚨 {critical_count} critical, ⚠️ {warning_count} warning alerts"
            if alerts else "✅ No canary alerts"
        ),
    }


def tool_entities_by_pattern(repository, pattern_id: str) -> Dict[str, Any]:
    """
    List all entities affected by a pattern (via _epigenetics).

    This shows which entities have been touched by an experimental pattern,
    helping understand the pattern's scope and impact.

    Args:
        repository: EntityRepository for data access
        pattern_id: The pattern ID to query

    Returns:
        Dict with entity list and summary counts
    """
    all_entities = repository.list(limit=1000)

    # Filter to entities with this pattern in epigenetics
    affected = [
        e for e in all_entities
        if pattern_id in e.data.get("_epigenetics", [])
    ]

    # Group by type and status
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}

    entity_list = []
    for e in affected:
        entity_list.append({
            "id": e.id,
            "type": e.type,
            "status": e.status,
            "name": e.data.get("name", e.id),
        })
        by_type[e.type] = by_type.get(e.type, 0) + 1
        by_status[e.status] = by_status.get(e.status, 0) + 1

    return {
        "pattern_id": pattern_id,
        "total": len(affected),
        "by_type": by_type,
        "by_status": by_status,
        "entities": entity_list,
        "summary": (
            f"Pattern {pattern_id} affects {len(affected)} entities"
            if affected else f"Pattern {pattern_id} has no affected entities"
        ),
    }


def tool_autoevolution_status(repository) -> Dict[str, Any]:
    """
    Dashboard view of autoevolutionary loop status.

    Shows all experimental patterns with their:
    - Observation period progress
    - Fitness metric status
    - Current recommendation (promote/deprecate/continue)

    Args:
        repository: EntityRepository for data access

    Returns:
        Dict with patterns list and summary statistics
    """
    evaluator = PatternEvaluator(repository)
    reports = evaluator.evaluate_all()

    # Count recommendations
    promote_count = len([r for r in reports if r.recommendation == "promote"])
    deprecate_count = len([r for r in reports if r.recommendation == "deprecate"])
    continue_count = len([r for r in reports if r.recommendation == "continue"])

    # Build pattern details
    patterns = []
    for r in reports:
        metrics_achieved = sum(1 for m in r.metrics if m.achieved)
        metrics_total = len(r.metrics)

        patterns.append({
            "id": r.pattern_id,
            "name": r.pattern_name,
            "days_active": r.days_since_experimental,
            "observation_period": r.observation_period_days,
            "observation_complete": r.observation_period_elapsed,
            "recommendation": r.recommendation,
            "metrics_achieved": metrics_achieved,
            "metrics_total": metrics_total,
            "metrics_summary": f"{metrics_achieved}/{metrics_total} metrics achieved",
            "sample_size": f"{r.sample_size_actual}/{r.sample_size_required} samples",
        })

    # Build summary line
    if not reports:
        summary = "No experimental patterns active"
    else:
        parts = []
        if promote_count:
            parts.append(f"✅ {promote_count} ready to promote")
        if deprecate_count:
            parts.append(f"❌ {deprecate_count} to deprecate")
        if continue_count:
            parts.append(f"⏳ {continue_count} continuing")
        summary = ", ".join(parts) if parts else "All patterns evaluating"

    return {
        "experimental_patterns": len(reports),
        "recommendations": {
            "promote": promote_count,
            "deprecate": deprecate_count,
            "continue": continue_count,
        },
        "patterns": patterns,
        "summary": summary,
    }


# Aliases for MCP registration
canary_alerts = tool_canary_alerts
entities_by_pattern = tool_entities_by_pattern
autoevolution_status = tool_autoevolution_status
