"""
Step definitions for quality_gate.feature

Tests for the Quality Gate pattern - active reversion of features
that claim stability without evidence (homeostatic resistance).
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity
from chora_store.observer import EntityObserver

# Load scenarios from feature file
scenarios('../features/quality_gate.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def observer():
    """Create an EntityObserver."""
    return EntityObserver()


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


@given('the quality-gate pattern is bootstrapped')
def bootstrap_quality_gate(factory, repository, context):
    """Bootstrap patterns from kernel to load quality-gate."""
    loaded = factory.bootstrap_patterns_from_kernel()
    context['patterns_loaded'] = loaded

    # Verify quality-gate pattern exists
    pattern = repository.read("pattern-quality-gate")
    assert pattern is not None, "pattern-quality-gate should be loaded"
    context['quality_gate_pattern'] = pattern


@given(parsers.parse('a feature "{feature_id}" with status "{status}" and no test_evidence'))
def feature_without_evidence(factory, repository, context, feature_id, status):
    """Create feature without test evidence."""
    # Create feature via factory (gets epigenetic fields injected)
    feature = factory.create("feature", feature_id.replace("feature-", "").replace("-", " ").title())

    # Force status to specified value
    updated = feature.copy(status=status)
    updated.data["test_evidence"] = ""  # Explicitly empty
    updated.data["quality_gate_passed"] = False
    updated.data["_epigenetics"] = ["pattern-quality-gate"]
    repository.update(updated)

    context[feature_id] = updated


@given(parsers.parse('a feature "{feature_id}" with status "{status}" and test_evidence "{evidence}"'))
def feature_with_evidence(factory, repository, context, feature_id, status, evidence):
    """Create feature with test evidence."""
    feature = factory.create("feature", feature_id.replace("feature-", "").replace("-", " ").title())

    updated = feature.copy(status=status)
    updated.data["test_evidence"] = evidence
    updated.data["_epigenetics"] = ["pattern-quality-gate"]
    repository.update(updated)

    context[feature_id] = updated


@given(parsers.parse('the feature has quality_gate_passed as {value}'))
def set_quality_gate_passed(repository, context, value):
    """Set quality_gate_passed field."""
    # Get the most recently created feature from context
    feature_ids = [k for k in context.keys() if k.startswith("feature-")]
    if not feature_ids:
        return

    feature_id = feature_ids[-1]
    feature = repository.read(feature_id)

    bool_value = value.lower() == "true"
    updated = feature.copy()
    updated.data["quality_gate_passed"] = bool_value
    repository.update(updated)

    context[feature_id] = updated


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@when('cron:daily hooks are executed')
def execute_cron_daily(repository, observer, context):
    """Execute cron:daily hooks via observer."""
    results = observer.run_epigenetic_hooks(repository, "cron:daily")
    context['hook_results'] = results


@when(parsers.parse('the feature is manually set back to "{status}" without evidence'))
def set_feature_status_without_evidence(repository, context, status):
    """Manually set a feature back to a status without adding evidence."""
    feature_ids = [k for k in context.keys() if k.startswith("feature-")]
    if not feature_ids:
        return

    feature_id = feature_ids[-1]
    feature = repository.read(feature_id)

    updated = feature.copy(status=status)
    updated.data["test_evidence"] = ""  # Ensure no evidence
    repository.update(updated)

    context[feature_id] = updated


@when('cron:daily hooks are executed again')
def execute_cron_daily_again(repository, observer, context):
    """Execute cron:daily hooks again."""
    results = observer.run_epigenetic_hooks(repository, "cron:daily")
    context.setdefault('all_hook_results', [])
    context['all_hook_results'].append(context.get('hook_results', []))
    context['all_hook_results'].append(results)
    context['hook_results'] = results


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('the feature "{feature_id}" status is "{expected_status}"'))
def feature_status_is(repository, feature_id, expected_status):
    """Check feature status."""
    feature = repository.read(feature_id)
    assert feature is not None, f"Feature {feature_id} not found"
    assert feature.status == expected_status, \
        f"Expected status '{expected_status}', got '{feature.status}'"


@then(parsers.parse('the feature "{feature_id}" has drift_signal "{signal}"'))
def feature_has_drift_signal(repository, feature_id, signal):
    """Check feature has specific drift signal."""
    feature = repository.read(feature_id)
    drift_signals = feature.data.get("drift_signals", [])
    assert signal in drift_signals, \
        f"Expected drift_signal '{signal}' in {drift_signals}"


@then(parsers.parse('the feature "{feature_id}" has at least {count:d} drift_signals'))
def feature_has_multiple_signals(repository, feature_id, count):
    """Check feature has at least N drift signals."""
    feature = repository.read(feature_id)
    drift_signals = feature.data.get("drift_signals", [])
    assert len(drift_signals) >= count, \
        f"Expected at least {count} drift_signals, got {len(drift_signals)}: {drift_signals}"


@then(parsers.parse('the feature "{feature_id}" has quality_gate_passed as {value}'))
def feature_quality_gate_passed(repository, feature_id, value):
    """Check quality_gate_passed field."""
    feature = repository.read(feature_id)
    expected = value.lower() == "true"
    actual = feature.data.get("quality_gate_passed", False)
    assert actual == expected, \
        f"Expected quality_gate_passed={expected}, got {actual}"


@then(parsers.parse('the feature "{feature_id}" has no drift_signals'))
def feature_has_no_drift_signals(repository, feature_id):
    """Check feature has no drift signals."""
    feature = repository.read(feature_id)
    drift_signals = feature.data.get("drift_signals", [])
    assert len(drift_signals) == 0, \
        f"Expected no drift_signals, got {drift_signals}"
