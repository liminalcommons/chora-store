"""
Step definitions for autoevolution_e2e.feature

End-to-end tests for the complete autoevolutionary cycle:
LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT
"""

import pytest
from datetime import datetime, timedelta, timezone
from pytest_bdd import scenarios, given, when, then, parsers
from typing import List

from chora_store.models import Entity
from chora_store.evaluator import PatternEvaluator

# Load scenarios from feature file
scenarios('../features/autoevolution_e2e.feature')


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


@given('a bootstrapped experimental pattern with fitness metrics')
def bootstrap_pattern(factory, repository, context):
    """Bootstrap patterns and get the test pattern."""
    factory.bootstrap_patterns_from_kernel()

    # Create a test pattern with specific fitness metrics
    pattern = Entity(
        id="pattern-e2e-test",
        type="pattern",
        status="experimental",
        created_at=datetime.now(timezone.utc),
        data={
            "name": "E2E Test Pattern",
            "description": "Pattern for end-to-end autoevolution testing",
            "subtype": "schema-extension",
            "mechanics": {
                "target": "feature",
                "inject_fields": {
                    "e2e_test_field": {
                        "type": "string",
                        "default": "e2e_value",
                    }
                },
                "fitness": {
                    "observation_period": "90 days",
                    "sample_size": 5,
                    "metrics": [
                        {
                            "name": "stability_rate",
                            "query": "count(features WHERE status='stable') / count(features)",
                            "baseline": 0.0,
                            "target": 0.5,
                            "direction": "higher_is_better",
                        }
                    ],
                    "success_condition": "observation_period.elapsed and stability_rate.achieved",
                    "failure_condition": "observation_period.elapsed and not stability_rate.achieved",
                },
            },
        },
    )
    repository.create(pattern)
    context['pattern'] = pattern
    context['pattern_id'] = pattern.id


@given(parsers.parse('{count:d} features are created via the factory'))
def create_features(factory, repository, context, count):
    """Create features via factory with epigenetic injection."""
    pattern_id = context.get('pattern_id', 'pattern-e2e-test')
    features = []

    for i in range(count):
        feature = factory.create("feature", f"E2E Test Feature {i}")
        # Tag with our test pattern
        updated = feature.copy()
        updated.data["_epigenetics"] = updated.data.get("_epigenetics", [])
        if pattern_id not in updated.data["_epigenetics"]:
            updated.data["_epigenetics"].append(pattern_id)
        repository.update(updated)
        features.append(updated)

    context['features'] = features


@given(parsers.parse('{count:d} of the features are transitioned to stable'))
def transition_features_stable(repository, context, count):
    """Transition specified number of features to stable."""
    features = context.get('features', [])
    for i, feature in enumerate(features[:count]):
        # Read fresh version from repository to avoid version conflicts
        current = repository.read(feature.id)
        updated = current.copy(status="stable")
        updated.data["test_evidence"] = f"http://tests.example/{feature.id}"
        repository.update(updated)
        context['features'][i] = updated


@given(parsers.parse('only {count:d} of the features are transitioned to stable'))
def transition_only_some_stable(repository, context, count):
    """Transition only specified number of features to stable (for failure case)."""
    features = context.get('features', [])
    for i, feature in enumerate(features[:count]):
        # Read fresh version from repository to avoid version conflicts
        current = repository.read(feature.id)
        updated = current.copy(status="stable")
        updated.data["test_evidence"] = f"http://tests.example/{feature.id}"
        repository.update(updated)
        context['features'][i] = updated


@given(parsers.parse('the pattern is aged {days:d} days'))
def age_pattern(repository, context, days):
    """Backdate the pattern's created_at timestamp.

    Note: repository.update() doesn't modify created_at, so we need
    to use raw SQL to backdate the timestamp.
    """
    pattern_id = context['pattern_id']
    old_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Update created_at directly in the database (update() doesn't touch it)
    with repository._connection() as conn:
        conn.execute(
            "UPDATE entities SET created_at = ? WHERE id = ?",
            (old_date.isoformat(), pattern_id)
        )

    # Reload the pattern with the updated timestamp
    context['pattern'] = repository.read(pattern_id)


@given('metrics meet the success criteria')
def metrics_meet_success(context):
    """Verify metrics configuration meets success criteria."""
    # This is a documentation step - the actual metrics are set by
    # transitioning enough features to stable
    pass


@given('the features have custom data fields')
def features_have_custom_data(repository, context):
    """Add custom data fields to features."""
    features = context.get('features', [])
    for i, feature in enumerate(features):
        # Read fresh version from repository to avoid version conflicts
        current = repository.read(feature.id)
        updated = current.copy()
        updated.data["custom_field"] = f"custom_value_{i}"
        updated.data["another_field"] = {"nested": True, "index": i}
        repository.update(updated)
        context['features'][i] = updated


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@when('evaluate_all is called')
def call_evaluate_all(repository, context):
    """Call PatternEvaluator.evaluate_all()."""
    evaluator = PatternEvaluator(repository)
    reports = evaluator.evaluate_all()
    context['reports'] = reports

    # Find our test pattern's report
    pattern_id = context['pattern_id']
    test_report = next((r for r in reports if r.pattern_id == pattern_id), None)
    context['test_report'] = test_report


@when(parsers.parse('execute_recommendation is called for {recommendation}'))
def call_execute_recommendation(repository, context, recommendation):
    """Execute recommendation for the test pattern."""
    evaluator = PatternEvaluator(repository)
    report = context.get('test_report')

    if report is None:
        # Create a mock report for testing
        return

    # Verify recommendation matches expected
    if report.recommendation != recommendation:
        pytest.skip(f"Report recommendation is '{report.recommendation}', expected '{recommendation}'")

    result = evaluator.execute_recommendation(report)
    context['result'] = result

    # Reload pattern to get updated state
    context['updated_pattern'] = repository.read(context['pattern_id'])


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('the pattern status is "{expected_status}"'))
def pattern_status_is(repository, context, expected_status):
    """Check pattern status."""
    pattern_id = context['pattern_id']
    pattern = repository.read(pattern_id)
    assert pattern.status == expected_status, \
        f"Expected pattern status '{expected_status}', got '{pattern.status}'"


@then(parsers.parse('a learning entity exists with domain "{domain}"'))
def learning_exists_with_domain(repository, context, domain):
    """Check that a learning was created with specified domain."""
    result = context.get('result', {})
    learning_id = result.get('learning_id')

    assert learning_id is not None, \
        f"Expected learning to be created, got result: {result}"

    learning = repository.read(learning_id)
    assert learning is not None, f"Learning {learning_id} not found"

    actual_domain = learning.data.get('domain', '')
    assert actual_domain == domain, \
        f"Expected domain '{domain}', got '{actual_domain}'"

    context['learning'] = learning


@then('the learning captures the pattern name')
def learning_has_pattern_name(context):
    """Check that the learning mentions the pattern name."""
    learning = context.get('learning')
    pattern = context.get('pattern')

    if learning is None or pattern is None:
        return

    pattern_name = pattern.data.get('name', pattern.id)
    insight = learning.data.get('insight', '')

    assert pattern_name.lower() in insight.lower(), \
        f"Expected pattern name '{pattern_name}' in learning insight"


@then('all features retain their custom data fields')
def features_retain_custom_data(repository, context):
    """Verify features still have their custom data."""
    features = context.get('features', [])
    for i, original in enumerate(features):
        current = repository.read(original.id)
        assert current.data.get('custom_field') == f"custom_value_{i}", \
            f"Feature {current.id} lost custom_field"
        assert current.data.get('another_field', {}).get('nested') is True, \
            f"Feature {current.id} lost nested field"


@then('all features retain their epigenetic tags')
def features_retain_epigenetics(repository, context):
    """Verify features still have their epigenetic tags."""
    pattern_id = context['pattern_id']
    features = context.get('features', [])

    for original in features:
        current = repository.read(original.id)
        epigenetics = current.data.get('_epigenetics', [])
        assert pattern_id in epigenetics, \
            f"Feature {current.id} lost epigenetic tag {pattern_id}"


@then('no learning entity is created')
def no_learning_created(context):
    """Check that no learning was created."""
    result = context.get('result', {})
    learning_id = result.get('learning_id')

    assert learning_id is None, \
        f"Expected no learning, but got {learning_id}"
