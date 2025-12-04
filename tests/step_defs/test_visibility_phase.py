"""
Step definitions for visibility_phase.feature

Tests for the VISIBILITY phase of the autoevolutionary loop.
The VISIBILITY phase makes the loop observable through canary alerts,
entity-by-pattern listing, and autoevolution status dashboards.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pytest_bdd import scenarios, given, when, then, parsers
from typing import List, Dict, Any

from chora_store.models import Entity
from chora_store.evaluator import PatternEvaluator, CanaryMonitor, CanaryAlert

# Load scenarios from feature file
scenarios('../features/visibility_phase.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def make_experimental_pattern(
    pattern_id: str,
    target: str = "feature",
    metrics: list = None,
    observation_period: str = "90 days",
    created_days_ago: int = 1,
    sample_size: int = 5,
    name: str = "Test Pattern",
    extra_data: dict = None,
) -> Entity:
    """Helper to create experimental pattern entities."""
    fitness = {
        "observation_period": observation_period,
        "sample_size": sample_size,
        "success_condition": "observation_period.elapsed and test_metric.achieved",
        "failure_condition": "observation_period.elapsed and not test_metric.achieved",
    }
    if metrics:
        fitness["metrics"] = metrics
    else:
        fitness["metrics"] = [
            {
                "name": "test_metric",
                "query": "count(features WHERE status='stable') / count(features)",
                "baseline": 0.0,
                "target": 0.5,
                "direction": "higher_is_better",
            }
        ]

    created_at = datetime.now(timezone.utc) - timedelta(days=created_days_ago)

    data = {
        "name": name,
        "description": "Test pattern for autoevolution experiments",
        "subtype": "schema-extension",
        "mechanics": {
            "target": target,
            "fitness": fitness,
        },
    }
    if extra_data:
        data.update(extra_data)

    return Entity(
        id=pattern_id,
        type="pattern",
        status="experimental",
        created_at=created_at,
        data=data,
    )


def make_feature_entity(
    feature_id: str,
    status: str = "nascent",
    epigenetics: list = None,
) -> Entity:
    """Helper to create feature entities."""
    return Entity(
        id=feature_id,
        type="feature",
        status=status,
        data={
            "name": f"Test Feature {feature_id}",
            "_epigenetics": epigenetics or [],
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('a factory with epigenetic support')
def factory_with_epigenetics(factory):
    """Factory is already available from fixture."""
    pass


@given(parsers.parse('an experimental pattern "{pattern_id}" with reversion signals'))
def pattern_with_reversions(repository, context, pattern_id):
    """Create pattern with excessive reversions to trigger critical alert."""
    pattern = make_experimental_pattern(
        pattern_id,
        name="Problem Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id

    # Create features with reversion markers to trigger alert
    for i in range(10):  # More than threshold
        feature = make_feature_entity(
            f"feature-reverted-{i}",
            status="converging",
            epigenetics=[pattern_id],
        )
        # Add reversion marker within window
        feature.data["_last_reversion"] = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat()
        feature.data["quality_gate_reversion"] = True
        repository.create(feature)


@given(parsers.parse('an experimental pattern "{pattern_id}" with drift signals'))
def pattern_with_drift(repository, context, pattern_id):
    """Create pattern with declining metrics to trigger warning alert."""
    # Create pattern with metric history showing decline (values going down over time)
    # The canary monitor assumes "lower is better", so values going UP would be "declining"
    # But actually the logic checks if prev > snap, which triggers on values going DOWN
    pattern = make_experimental_pattern(
        pattern_id,
        name="Warning Pattern",
        extra_data={
            "_metric_history": [
                {"metrics": {"test_metric": 0.6}, "timestamp": datetime.now(timezone.utc).isoformat()},
                {"metrics": {"test_metric": 0.5}, "timestamp": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()},
                {"metrics": {"test_metric": 0.4}, "timestamp": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()},
                {"metrics": {"test_metric": 0.3}, "timestamp": (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()},
            ]
        }
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('an experimental pattern "{pattern_id}" with no issues'))
def pattern_healthy(repository, context, pattern_id):
    """Create healthy pattern with no alerts."""
    pattern = make_experimental_pattern(
        pattern_id,
        name="Healthy Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id

    # Create normal features (no reversions, good status)
    for i in range(3):
        feature = make_feature_entity(
            f"feature-healthy-{i}",
            status="stable",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('an experimental pattern "{pattern_id}"'))
def experimental_pattern(repository, context, pattern_id):
    """Create basic experimental pattern."""
    pattern = make_experimental_pattern(pattern_id, name="Test Pattern")
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('{count:d} features with epigenetic tag "{pattern_id}"'))
def features_with_pattern(repository, context, count, pattern_id):
    """Create features tagged with a pattern."""
    context['pattern_id'] = pattern_id
    for i in range(count):
        feature = make_feature_entity(
            f"feature-tagged-{pattern_id}-{i}",
            status="nascent",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('{count:d} stable features with epigenetic tag "{pattern_id}"'))
def stable_features_with_pattern(repository, context, count, pattern_id):
    """Create stable features tagged with a pattern."""
    context['pattern_id'] = pattern_id
    for i in range(count):
        feature = make_feature_entity(
            f"feature-stable-{pattern_id}-{i}",
            status="stable",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('{count:d} experimental patterns with fitness metrics'))
def multiple_patterns(repository, context, count):
    """Create multiple experimental patterns."""
    patterns = []
    for i in range(count):
        pattern = make_experimental_pattern(
            f"pattern-multi-{i}",
            name=f"Multi Pattern {i}",
        )
        repository.create(pattern)
        patterns.append(pattern)
    context['patterns'] = patterns


@given('features for each experimental pattern')
def features_for_patterns(repository, context):
    """Create features for each pattern."""
    patterns = context.get('patterns', [])
    for pattern in patterns:
        for i in range(3):
            feature = make_feature_entity(
                f"feature-{pattern.id}-{i}",
                status="stable" if i == 0 else "nascent",
                epigenetics=[pattern.id],
            )
            repository.create(feature)


@given(parsers.parse('an experimental pattern "{pattern_id}" created {days:d} days ago'))
def pattern_with_age(repository, context, pattern_id, days):
    """Create pattern with specific age."""
    pattern = make_experimental_pattern(
        pattern_id,
        name="Aged Pattern",
        created_days_ago=days,
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@when('canary_alerts is called')
def call_canary_alerts(repository, context):
    """Call canary_alerts to get active alerts."""
    monitor = CanaryMonitor(repository)
    alerts = monitor.check_all()
    context['alerts'] = alerts


@when(parsers.parse('entities_by_pattern is called with "{pattern_id}"'))
def call_entities_by_pattern(repository, context, pattern_id):
    """Call entities_by_pattern with a pattern ID."""
    # Query for entities with this pattern in their epigenetics
    all_entities = repository.list(limit=500)
    entities = [
        e for e in all_entities
        if pattern_id in e.data.get("_epigenetics", [])
    ]
    context['entities'] = entities


@when('autoevolution_status is called')
def call_autoevolution_status(repository, context):
    """Call autoevolution_status to get dashboard."""
    evaluator = PatternEvaluator(repository)
    reports = evaluator.evaluate_all()

    status = {
        "experimental_patterns": len(reports),
        "recommendations": {
            "promote": len([r for r in reports if r.recommendation == "promote"]),
            "deprecate": len([r for r in reports if r.recommendation == "deprecate"]),
            "continue": len([r for r in reports if r.recommendation == "continue"]),
        },
        "patterns": [
            {
                "id": r.pattern_id,
                "name": r.pattern_name,
                "days_active": r.days_since_experimental,
                "observation_period": r.observation_period_days,
                "recommendation": r.recommendation,
                "metrics_achieved": sum(1 for m in r.metrics if m.achieved),
                "metrics_total": len(r.metrics),
            }
            for r in reports
        ],
    }
    context['status'] = status


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('at least {count:d} alert is returned'))
def at_least_alerts_count(context, count):
    """Check at least N alerts returned."""
    alerts = context['alerts']
    assert len(alerts) >= count, \
        f"Expected at least {count} alerts, got {len(alerts)}"


@then(parsers.parse('{count:d} alerts are returned'))
def alerts_count(context, count):
    """Check exact number of alerts."""
    alerts = context['alerts']
    assert len(alerts) == count, \
        f"Expected {count} alerts, got {len(alerts)}"


@then(parsers.parse('an alert has severity "{severity}"'))
def alert_has_severity(context, severity):
    """Check an alert has specific severity."""
    alerts = context['alerts']
    severities = [a.severity for a in alerts]
    assert severity in severities, \
        f"Expected severity '{severity}' in alerts, got {severities}"


@then(parsers.parse('{count:d} entities are returned'))
def entities_count(context, count):
    """Check number of entities returned."""
    entities = context['entities']
    assert len(entities) == count, \
        f"Expected {count} entities, got {len(entities)}"


@then('all entities have the pattern in their epigenetics')
def all_entities_have_pattern(context):
    """Check all returned entities have the pattern."""
    entities = context['entities']
    pattern_id = context['pattern_id']
    for entity in entities:
        epigenetics = entity.data.get("_epigenetics", [])
        assert pattern_id in epigenetics, \
            f"Entity {entity.id} missing pattern {pattern_id} in epigenetics"


@then(parsers.parse('the status shows {count:d} experimental patterns'))
def status_pattern_count(context, count):
    """Check number of experimental patterns in status."""
    status = context['status']
    assert status['experimental_patterns'] == count, \
        f"Expected {count} patterns, got {status['experimental_patterns']}"


@then('the status includes recommendation counts')
def status_has_recommendations(context):
    """Check status has recommendation counts."""
    status = context['status']
    recommendations = status.get('recommendations', {})
    assert 'promote' in recommendations, "Missing 'promote' count"
    assert 'deprecate' in recommendations, "Missing 'deprecate' count"
    assert 'continue' in recommendations, "Missing 'continue' count"


@then(parsers.parse('the status patterns include "{pattern_id}"'))
def status_includes_pattern(context, pattern_id):
    """Check status includes a specific pattern."""
    status = context['status']
    pattern_ids = [p['id'] for p in status.get('patterns', [])]
    assert pattern_id in pattern_ids, \
        f"Expected pattern '{pattern_id}' in status, got {pattern_ids}"


@then('the pattern status shows metrics achieved')
def pattern_has_metrics(context):
    """Check pattern in status shows metrics."""
    status = context['status']
    patterns = status.get('patterns', [])
    assert len(patterns) > 0, "No patterns in status"

    for pattern in patterns:
        assert 'metrics_achieved' in pattern, \
            f"Pattern {pattern['id']} missing metrics_achieved"
        assert 'metrics_total' in pattern, \
            f"Pattern {pattern['id']} missing metrics_total"
