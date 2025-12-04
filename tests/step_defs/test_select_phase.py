"""
Step definitions for select_phase.feature

Tests for the SELECT phase of the autoevolutionary loop.
The SELECT phase evaluates experimental pattern fitness and makes
promotion/deprecation recommendations.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity
from chora_store.evaluator import PatternEvaluator

# Load scenarios from feature file
scenarios('../features/select_phase.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def make_experimental_pattern(
    pattern_id: str,
    target: str = "feature",
    metrics: list = None,
    observation_period: str = "90 days",
    created_days_ago: int = 1,
    sample_size: int = 20,
    success_condition: str = "",
    failure_condition: str = "",
) -> Entity:
    """Helper to create experimental pattern entities with fitness metrics."""
    fitness = {
        "observation_period": observation_period,
        "sample_size": sample_size,
    }
    if metrics:
        fitness["metrics"] = metrics
    if success_condition:
        fitness["success_condition"] = success_condition
    if failure_condition:
        fitness["failure_condition"] = failure_condition

    created_at = datetime.now(timezone.utc) - timedelta(days=created_days_ago)

    return Entity(
        id=pattern_id,
        type="pattern",
        status="experimental",
        created_at=created_at,
        data={
            "name": "Test Pattern",
            "subtype": "schema-extension",
            "mechanics": {
                "target": target,
                "fitness": fitness,
            },
        },
    )


def make_feature_entity(
    feature_id: str,
    status: str = "nascent",
    epigenetics: list = None,
    **extra_fields,
) -> Entity:
    """Helper to create feature entities."""
    data = {
        "name": f"Test Feature {feature_id}",
        "_epigenetics": epigenetics or [],
    }
    data.update(extra_fields)

    return Entity(
        id=feature_id,
        type="feature",
        status=status,
        data=data,
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


@given(parsers.parse('an experimental pattern "{pattern_id}" with metrics'))
def experimental_pattern_with_metrics(repository, context, pattern_id):
    """Create an experimental pattern with default metrics."""
    pattern = make_experimental_pattern(
        pattern_id,
        metrics=[
            {
                "name": "test_metric",
                "query": "count(features WHERE status='stable') / count(features)",
                "baseline": 0.3,
                "target": 0.5,
                "direction": "higher_is_better",
            }
        ],
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern_id


@given(parsers.parse('a feature "{feature_id}" with test_evidence "{evidence}"'))
def feature_with_evidence(repository, context, feature_id, evidence):
    """Create feature with test_evidence field."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    feature = make_feature_entity(
        feature_id,
        epigenetics=[pattern_id],
        test_evidence=evidence,
    )
    repository.create(feature)


@given(parsers.re(r'a feature "(?P<feature_id>[^"]+)" with test_evidence ""'))
def feature_with_empty_evidence(repository, context, feature_id):
    """Create feature with empty test_evidence field."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    feature = make_feature_entity(
        feature_id,
        epigenetics=[pattern_id],
        test_evidence="",
    )
    repository.create(feature)


@given(parsers.parse('a feature "{feature_id}" with test_evidence null'))
def feature_with_null_evidence(repository, context, feature_id):
    """Create feature with null test_evidence."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    feature = make_feature_entity(
        feature_id,
        epigenetics=[pattern_id],
        test_evidence=None,
    )
    repository.create(feature)


@given(parsers.parse('{count:d} features with status "{status}"'))
def multiple_features_with_status(repository, context, count, status):
    """Create multiple features with a specific status."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    for i in range(count):
        feature = make_feature_entity(
            f"feature-{status}-{i}",
            status=status,
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given(parsers.parse('a feature "{feature_id}" with status "{status}" and test_evidence "{evidence}"'))
def feature_with_status_and_evidence(repository, context, feature_id, status, evidence):
    """Create feature with both status and test_evidence."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    feature = make_feature_entity(
        feature_id,
        status=status,
        epigenetics=[pattern_id],
        test_evidence=evidence if evidence else None,
    )
    repository.create(feature)


@given(parsers.re(r'a feature "(?P<feature_id>[^"]+)" with status "(?P<status>[^"]+)" and test_evidence ""'))
def feature_with_status_and_empty_evidence(repository, context, feature_id, status):
    """Create feature with status and empty test_evidence."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    feature = make_feature_entity(
        feature_id,
        status=status,
        epigenetics=[pattern_id],
        test_evidence="",
    )
    repository.create(feature)


@given('an experimental pattern with fitness metrics:')
def pattern_with_metrics_table(repository, context, datatable):
    """Create pattern with metrics from a table."""
    # datatable is list of lists, first row is headers
    headers = datatable[0]
    metrics = []
    for row in datatable[1:]:
        row_dict = dict(zip(headers, row))
        metrics.append({
            "name": row_dict['name'],
            "query": row_dict['query'],
            "baseline": 0.0,
            "target": float(row_dict['target']),
            "direction": "higher_is_better",
        })

    pattern = make_experimental_pattern(
        "pattern-table-test",
        metrics=metrics,
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern.id


@given(parsers.parse('an experimental pattern created {days:d} days ago with {period:d} day observation'))
def pattern_with_age(repository, context, days, period):
    """Create pattern with specific age and observation period."""
    pattern = make_experimental_pattern(
        "pattern-aged-test",
        observation_period=f"{period} days",
        created_days_ago=days,
        sample_size=5,  # Small sample size for testing
        success_condition="observation_period.elapsed and test_metric.achieved",
        failure_condition="observation_period.elapsed and not test_metric.achieved",
        metrics=[
            {
                "name": "test_metric",
                "query": "count(features WHERE status='stable') / count(features)",
                "baseline": 0.0,
                "target": 0.5,
                "direction": "higher_is_better",
            }
        ],
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern.id


@given('metrics that meet targets')
def metrics_meeting_targets(repository, context):
    """Create features so metrics will meet targets (>= 50% stable)."""
    pattern_id = context.get('pattern_id', 'pattern-test')
    for i in range(6):
        feature = make_feature_entity(
            f"feature-stable-{i}",
            status="stable",
            epigenetics=[pattern_id],
        )
        repository.create(feature)
    for i in range(4):
        feature = make_feature_entity(
            f"feature-nascent-{i}",
            status="nascent",
            epigenetics=[pattern_id],
        )
        repository.create(feature)


@given('metrics that fail targets')
def metrics_failing_targets(repository, context):
    """Create features so metrics will fail targets (< 50% stable)."""
    pattern_id = context.get('pattern_id', 'pattern-test')
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


@given(parsers.parse('{count:d} experimental schema-extension patterns with metrics'))
def multiple_patterns(repository, context, count):
    """Create multiple experimental patterns."""
    patterns = []
    for i in range(count):
        pattern = make_experimental_pattern(
            f"pattern-multi-{i}",
            metrics=[
                {
                    "name": "test_metric",
                    "query": "count(features WHERE status='stable') / count(features)",
                    "baseline": 0.0,
                    "target": 0.5,
                    "direction": "higher_is_better",
                }
            ],
        )
        repository.create(pattern)
        patterns.append(pattern)
    context['patterns'] = patterns


@given('features for each pattern')
def features_for_patterns(repository, context):
    """Create features tagged with each pattern."""
    patterns = context.get('patterns', [])
    for pattern in patterns:
        for i in range(3):
            feature = make_feature_entity(
                f"feature-{pattern.id}-{i}",
                status="stable" if i == 0 else "nascent",
                epigenetics=[pattern.id],
            )
            repository.create(feature)


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@when(parsers.parse('the evaluator executes "{query}"'))
def evaluator_executes_query(repository, context, query):
    """Execute a metric query."""
    evaluator = PatternEvaluator(repository)
    pattern_id = context.get('pattern_id', 'pattern-test')
    result = evaluator._execute_metric_query(query, pattern_id, 'feature')
    context['result'] = result


@when('PatternEvaluator.evaluate_pattern is called')
def evaluate_pattern(repository, context):
    """Evaluate the pattern."""
    evaluator = PatternEvaluator(repository)
    pattern = context['pattern']
    report = evaluator.evaluate_pattern(pattern)
    context['report'] = report


@when('PatternEvaluator.evaluate_all is called')
def evaluate_all(repository, context):
    """Evaluate all experimental patterns."""
    evaluator = PatternEvaluator(repository)
    reports = evaluator.evaluate_all()
    context['reports'] = reports


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('the result is {expected:g}'))
def result_equals(context, expected):
    """Check that result equals expected value."""
    result = context['result']
    assert result == expected, f"Expected {expected}, got {result}"


@then('all metrics have non-null current_value')
def all_metrics_have_values(context):
    """Check all metrics have non-null values."""
    report = context['report']
    for metric in report.metrics:
        assert metric.current_value is not None, \
            f"Metric {metric.name} has null current_value"


@then(parsers.parse('the {metric_name} metric value is {expected:g}'))
def metric_value_equals(context, metric_name, expected):
    """Check specific metric value."""
    report = context['report']
    metric = next((m for m in report.metrics if m.name == metric_name), None)
    assert metric is not None, f"Metric {metric_name} not found"
    assert metric.current_value == expected, \
        f"Expected {expected}, got {metric.current_value}"


@then(parsers.parse('the {metric_name} metric is achieved'))
def metric_is_achieved(context, metric_name):
    """Check metric is achieved."""
    report = context['report']
    metric = next((m for m in report.metrics if m.name == metric_name), None)
    assert metric is not None, f"Metric {metric_name} not found"
    assert metric.achieved is True, f"Metric {metric_name} not achieved"


@then(parsers.parse('the recommendation is "{expected}"'))
def recommendation_equals(context, expected):
    """Check recommendation."""
    report = context['report']
    assert report.recommendation == expected, \
        f"Expected {expected}, got {report.recommendation}"


@then(parsers.parse('observation_period_elapsed is {expected}'))
def observation_period_status(context, expected):
    """Check observation period elapsed status."""
    report = context['report']
    expected_bool = expected.lower() == 'true'
    assert report.observation_period_elapsed == expected_bool, \
        f"Expected {expected_bool}, got {report.observation_period_elapsed}"


@then(parsers.parse('{count:d} fitness reports are returned'))
def reports_count(context, count):
    """Check number of reports."""
    reports = context['reports']
    assert len(reports) == count, f"Expected {count} reports, got {len(reports)}"


@then('all reports have a recommendation')
def all_reports_have_recommendation(context):
    """Check all reports have recommendations."""
    reports = context['reports']
    for report in reports:
        assert report.recommendation is not None, \
            f"Report for {report.pattern_id} has no recommendation"
        assert report.recommendation in ('continue', 'promote', 'deprecate'), \
            f"Invalid recommendation: {report.recommendation}"
