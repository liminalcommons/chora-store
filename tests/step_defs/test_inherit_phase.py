"""
Step definitions for inherit_phase.feature

Tests for the INHERIT phase of the autoevolutionary loop.
The INHERIT phase executes recommendations from SELECT by transitioning
pattern status and capturing experiment outcomes as learnings.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pytest_bdd import scenarios, given, when, then, parsers
from dataclasses import dataclass
from typing import List, Optional

from chora_store.models import Entity
from chora_store.evaluator import PatternEvaluator, FitnessReport, MetricResult, CanaryMonitor, CanaryAlert

# Load scenarios from feature file
scenarios('../features/inherit_phase.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def make_experimental_pattern(
    pattern_id: str,
    target: str = "feature",
    metrics: list = None,
    observation_period: str = "90 days",
    created_days_ago: int = 100,
    sample_size: int = 5,
    name: str = "Test Pattern",
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

    return Entity(
        id=pattern_id,
        type="pattern",
        status="experimental",
        created_at=created_at,
        data={
            "name": name,
            "description": "Test pattern for autoevolution experiments",
            "subtype": "schema-extension",
            "mechanics": {
                "target": target,
                "fitness": fitness,
            },
        },
    )


def make_fitness_report(
    pattern_id: str,
    recommendation: str,
    days_since: int = 100,
    observation_days: int = 90,
    sample_actual: int = 10,
    sample_required: int = 5,
    metrics: List[MetricResult] = None,
) -> FitnessReport:
    """Helper to create FitnessReport objects."""
    if metrics is None:
        metrics = [
            MetricResult(
                name="test_metric",
                description="Test metric for stability rate",
                baseline=0.0,
                target=0.5,
                direction="higher_is_better",
                current_value=0.6 if recommendation == "promote" else 0.2,
                achieved=recommendation == "promote",
            )
        ]

    return FitnessReport(
        pattern_id=pattern_id,
        pattern_name="Test Pattern",
        observation_period_days=observation_days,
        days_since_experimental=days_since,
        sample_size_required=sample_required,
        sample_size_actual=sample_actual,
        metrics=metrics,
        success_condition_met=recommendation == "promote",
        failure_condition_met=recommendation == "deprecate",
        observation_period_elapsed=days_since >= observation_days,
        recommendation=recommendation,
        actions_to_take=[],
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


@given(parsers.parse('an experimental pattern "{pattern_id}" ready for promotion'))
def pattern_ready_for_promotion(repository, context, pattern_id):
    """Create pattern that meets promotion criteria."""
    pattern = make_experimental_pattern(
        pattern_id,
        created_days_ago=100,  # Past observation period
        name="Success Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id
    # Create features to meet sample size
    for i in range(6):
        feature = make_feature_entity(
            f"feature-stable-{i}",
            status="stable",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('an experimental pattern "{pattern_id}" that failed metrics'))
def pattern_failed_metrics(repository, context, pattern_id):
    """Create pattern that failed metrics."""
    pattern = make_experimental_pattern(
        pattern_id,
        created_days_ago=100,
        name="Failed Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id
    # Create features that fail metrics (< 50% stable)
    for i in range(2):
        feature = make_feature_entity(
            f"feature-stable-{i}",
            status="stable",
            epigenetics=[pattern_id],
        )
        repository.create(feature)
    for i in range(8):
        feature = make_feature_entity(
            f"feature-nascent-{i}",
            status="nascent",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('an experimental pattern "{pattern_id}" within observation period'))
def pattern_within_observation(repository, context, pattern_id):
    """Create pattern still in observation."""
    pattern = make_experimental_pattern(
        pattern_id,
        created_days_ago=30,  # Within 90 day observation
        name="Observing Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('an experimental pattern "{pattern_id}"'))
def experimental_pattern(repository, context, pattern_id):
    """Create basic experimental pattern."""
    pattern = make_experimental_pattern(pattern_id, name="Test Pattern")
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('an experimental pattern "{pattern_id}" with full metrics'))
def pattern_with_full_metrics(repository, context, pattern_id):
    """Create pattern with comprehensive metrics."""
    pattern = make_experimental_pattern(
        pattern_id,
        created_days_ago=100,
        name="Harvest Pattern",
        metrics=[
            {
                "name": "stability_rate",
                "query": "count(features WHERE status='stable') / count(features)",
                "baseline": 0.0,
                "target": 0.5,
                "direction": "higher_is_better",
            },
            {
                "name": "adoption_rate",
                "query": "count(features WHERE _epigenetics IS NOT NULL) / count(features)",
                "baseline": 0.0,
                "target": 0.3,
                "direction": "higher_is_better",
            },
        ],
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('an experimental pattern "{pattern_id}" with failed metrics'))
def pattern_with_failed_metrics(repository, context, pattern_id):
    """Create pattern with failed metrics for deprecation learning test."""
    pattern = make_experimental_pattern(
        pattern_id,
        created_days_ago=100,
        name="Failed Metrics Pattern",
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('the pattern has {count:d} affected entities'))
def pattern_has_affected_entities(repository, context, count):
    """Create affected entities for the pattern."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    for i in range(count):
        feature = make_feature_entity(
            f"feature-affected-{i}",
            status="stable" if i % 2 == 0 else "nascent",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('a fitness report with recommendation "{recommendation}"'))
def fitness_report_with_recommendation(context, recommendation):
    """Create fitness report with specified recommendation."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    days_since = 100 if recommendation in ("promote", "deprecate") else 30

    report = make_fitness_report(
        pattern_id,
        recommendation,
        days_since=days_since,
    )
    context['report'] = report


@given(parsers.parse('a canary alert with severity "{severity}" for the pattern'))
def canary_alert_with_severity(context, severity):
    """Create canary alert."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    pattern = context.get('pattern')
    pattern_name = pattern.data.get('name', 'Test Pattern') if pattern else 'Test Pattern'
    alert = CanaryAlert(
        pattern_id=pattern_id,
        pattern_name=pattern_name,
        signal="excessive_reversions",
        severity=severity,
        details=f"Pattern triggered {severity} alert",
    )
    context['alert'] = alert


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@when('execute_recommendation is called')
def call_execute_recommendation(repository, context):
    """Execute the recommendation from the fitness report."""
    evaluator = PatternEvaluator(repository)
    report = context['report']
    result = evaluator.execute_recommendation(report)
    context['result'] = result
    # Reload pattern to get updated state
    context['updated_pattern'] = repository.read(context['pattern_id'])


@when('auto_disable is called with the alert')
def call_auto_disable(repository, context):
    """Call canary auto_disable."""
    monitor = CanaryMonitor(repository)
    alert = context['alert']
    result = monitor.auto_disable(alert)
    context['result'] = result
    # Reload pattern to get updated state
    context['updated_pattern'] = repository.read(context['pattern_id'])


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('the pattern status is "{expected_status}"'))
def pattern_status_is(context, expected_status):
    """Check pattern status."""
    pattern = context['updated_pattern']
    assert pattern.status == expected_status, \
        f"Expected status '{expected_status}', got '{pattern.status}'"


@then('a learning entity is created')
def learning_created(context):
    """Check that a learning was created."""
    result = context['result']
    assert result.get('learning_id') is not None, \
        "Expected learning_id in result, got None"
    context['learning_id'] = result['learning_id']


@then('no learning entity is created')
def no_learning_created(context):
    """Check that no learning was created."""
    result = context['result']
    assert result.get('learning_id') is None, \
        f"Expected no learning, got {result.get('learning_id')}"


@then(parsers.parse('the learning domain is "{expected_domain}"'))
def learning_domain_is(repository, context, expected_domain):
    """Check learning domain."""
    learning_id = context.get('learning_id')
    if learning_id:
        learning = repository.read(learning_id)
        assert learning is not None, f"Learning {learning_id} not found"
        actual_domain = learning.data.get('domain', '')
        assert actual_domain == expected_domain, \
            f"Expected domain '{expected_domain}', got '{actual_domain}'"


@then(parsers.parse('the pattern data includes "{field}"'))
def pattern_data_includes_field(context, field):
    """Check pattern data has field."""
    pattern = context['updated_pattern']
    assert field in pattern.data, \
        f"Expected '{field}' in pattern data, got keys: {list(pattern.data.keys())}"


@then(parsers.parse('the pattern data includes "{field}" as true'))
def pattern_data_includes_field_true(context, field):
    """Check pattern data has field set to true."""
    pattern = context['updated_pattern']
    assert field in pattern.data, \
        f"Expected '{field}' in pattern data"
    assert pattern.data[field] is True, \
        f"Expected '{field}' to be True, got {pattern.data[field]}"


@then(parsers.parse('the pattern data does not include "{field}"'))
def pattern_data_excludes_field(context, field):
    """Check pattern data does not have field."""
    pattern = context['updated_pattern']
    assert field not in pattern.data, \
        f"Expected '{field}' not in pattern data, but it exists"


@then(parsers.parse('the learning insight contains "{text}"'))
def learning_insight_contains(repository, context, text):
    """Check learning insight contains text."""
    # Try to get learning_id from context directly or from result
    learning_id = context.get('learning_id')
    if learning_id is None:
        result = context.get('result', {})
        learning_id = result.get('learning_id')
    assert learning_id is not None, "No learning was created"
    context['learning_id'] = learning_id  # Store for subsequent steps
    learning = repository.read(learning_id)
    assert learning is not None, f"Learning {learning_id} not found"
    insight = learning.data.get('insight', '')
    assert text.lower() in insight.lower(), \
        f"Expected '{text}' in insight, got:\n{insight[:200]}..."


def _get_learning_id(context):
    """Helper to get learning_id from context or result."""
    learning_id = context.get('learning_id')
    if learning_id is None:
        result = context.get('result', {})
        learning_id = result.get('learning_id')
    if learning_id is not None:
        context['learning_id'] = learning_id
    return learning_id


@then('the learning insight contains the pattern name')
def learning_insight_contains_pattern_name(repository, context):
    """Check learning insight contains pattern name."""
    learning_id = _get_learning_id(context)
    assert learning_id is not None, "No learning was created"
    pattern = context['pattern']
    pattern_name = pattern.data.get('name', pattern.id)

    learning = repository.read(learning_id)
    insight = learning.data.get('insight', '')
    assert pattern_name.lower() in insight.lower(), \
        f"Expected pattern name '{pattern_name}' in insight"


@then('the learning insight contains metrics results')
def learning_insight_contains_metrics(repository, context):
    """Check learning insight contains metrics."""
    learning_id = _get_learning_id(context)
    assert learning_id is not None, "No learning was created"
    learning = repository.read(learning_id)
    insight = learning.data.get('insight', '')
    # Should contain either metric names or terms like 'target', 'achieved'
    assert any(term in insight.lower() for term in ['metric', 'target', 'achieved', 'failed']), \
        f"Expected metrics information in insight"


@then('the learning links include the pattern id')
def learning_links_include_pattern(repository, context):
    """Check learning links to pattern."""
    learning_id = _get_learning_id(context)
    assert learning_id is not None, "No learning was created"
    pattern_id = context['pattern_id']

    learning = repository.read(learning_id)
    links = learning.data.get('links', [])
    assert pattern_id in links, \
        f"Expected pattern '{pattern_id}' in links, got {links}"


@then(parsers.parse('the learning impact is "{expected_impact}"'))
def learning_impact_is(repository, context, expected_impact):
    """Check learning impact level."""
    learning_id = _get_learning_id(context)
    assert learning_id is not None, "No learning was created"
    learning = repository.read(learning_id)
    actual_impact = learning.data.get('impact', '')
    assert actual_impact == expected_impact, \
        f"Expected impact '{expected_impact}', got '{actual_impact}'"
