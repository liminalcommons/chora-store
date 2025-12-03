"""
Step definitions for tiered_resolution.feature
"""

import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.metabolism import MetabolicEngine

# Load scenarios from feature file
scenarios('../features/tiered_resolution.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('multiple learnings with high keyword overlap')
def learnings_high_overlap(factory, context):
    """Create learnings that will cluster together (high keyword overlap)."""
    learnings = []
    # These share keywords: "testing", "patterns", "important"
    l1 = factory.create('learning', 'Testing Patterns 1',
                        insight='Testing patterns are important for quality',
                        domain='engineering')
    l2 = factory.create('learning', 'Testing Patterns 2',
                        insight='Quality testing patterns prevent bugs',
                        domain='engineering')
    l3 = factory.create('learning', 'Testing Importance',
                        insight='Important testing ensures patterns work',
                        domain='engineering')
    learnings.extend([l1, l2, l3])
    context['learnings'] = learnings
    context['learning_ids'] = [l.id for l in learnings]


@given('multiple learnings with low keyword overlap')
def learnings_low_overlap(factory, context):
    """Create learnings that won't cluster well (low keyword overlap)."""
    learnings = []
    # These have minimal keyword overlap
    l1 = factory.create('learning', 'Database Design',
                        insight='Indexes speed up queries',
                        domain='databases')
    l2 = factory.create('learning', 'UI Patterns',
                        insight='Components should be reusable',
                        domain='frontend')
    l3 = factory.create('learning', 'Security Practices',
                        insight='Always validate user input',
                        domain='security')
    learnings.extend([l1, l2, l3])
    context['learnings'] = learnings
    context['learning_ids'] = [l.id for l in learnings]


@given('only one learning')
def single_learning(factory, context):
    """Create only one learning (insufficient for synthesis)."""
    l = factory.create('learning', 'Single Learning',
                       insight='This is a solo insight',
                       domain='general')
    context['learnings'] = [l]
    context['learning_ids'] = [l.id]


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('tiered_synthesize is called with the learning IDs')
def call_tiered_synthesize(repository, context):
    """Call tiered_synthesize with default parameters."""
    engine = MetabolicEngine(repository)
    result = engine.tiered_synthesize(context['learning_ids'])
    context['result'] = result


@when(parsers.parse('tiered_synthesize is called with max_tier "{max_tier}"'))
def call_tiered_synthesize_with_max_tier(repository, context, max_tier):
    """Call tiered_synthesize with a max tier constraint."""
    engine = MetabolicEngine(repository)
    result = engine.tiered_synthesize(context['learning_ids'], max_tier=max_tier)
    context['result'] = result


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('synthesis succeeds at the workflow tier')
def synthesis_succeeds_workflow(context):
    """Verify synthesis succeeded at workflow tier."""
    result = context['result']
    assert result['success'] is True
    assert result['tier_used'] == 'workflow'
    assert result['result'] is not None


@then('a trace is captured for the workflow tier')
def trace_captured_workflow(context):
    """Verify a workflow tier trace was captured."""
    result = context['result']
    assert len(result['traces']) >= 1
    # The trace ID should be in the list
    assert any('trace-' in t for t in result['traces'])


@then('synthesis escalates to inference tier')
def synthesis_escalates_inference(context):
    """Verify synthesis escalated to inference tier."""
    result = context['result']
    # Since LLM is not implemented, success will be False
    # but tier_used should be 'inference'
    assert result['tier_used'] == 'inference'


@then('traces are captured for both workflow and inference tiers')
def traces_both_tiers(repository, context):
    """Verify traces were captured for both tier attempts."""
    result = context['result']
    # Should have 2 traces (one for each tier)
    assert len(result['traces']) == 2

    # Verify traces exist in database
    with repository._connection() as conn:
        for trace_id in result['traces']:
            row = conn.execute(
                "SELECT tier FROM traces WHERE id = ?",
                (trace_id,)
            ).fetchone()
            assert row is not None


@then('synthesis does not escalate beyond workflow')
def no_escalation_beyond_workflow(context):
    """Verify synthesis stayed at workflow tier."""
    result = context['result']
    assert result['tier_used'] is None or result['tier_used'] == 'workflow'
    assert result['success'] is False  # Can't succeed without escalation


@then('an escalation reason is provided')
def escalation_reason_provided(context):
    """Verify an escalation reason was given."""
    result = context['result']
    assert result['escalation_reason'] is not None
    assert len(result['escalation_reason']) > 0


@then('synthesis fails with an error about insufficient learnings')
def synthesis_fails_insufficient(context):
    """Verify synthesis fails due to insufficient learnings."""
    result = context['result']
    assert result['success'] is False
    assert 'learning' in result['escalation_reason'].lower()
    assert '2' in result['escalation_reason'] or 'insufficient' in result['escalation_reason'].lower()


@then('no traces are captured')
def no_traces(context):
    """Verify no traces were captured."""
    result = context['result']
    assert len(result['traces']) == 0


@then(parsers.parse('the trace includes operation_type "{operation_type}"'))
def trace_has_operation_type(repository, context, operation_type):
    """Verify trace has the expected operation type."""
    result = context['result']
    assert len(result['traces']) > 0

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT operation_type FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        assert row['operation_type'] == operation_type


@then('the trace includes the input learning IDs')
def trace_has_inputs(repository, context):
    """Verify trace includes input learning IDs."""
    result = context['result']
    learning_ids = context['learning_ids']

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT inputs FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        inputs = json.loads(row['inputs'])
        for lid in learning_ids:
            assert lid in inputs


@then('the trace includes reasoning steps')
def trace_has_reasoning(repository, context):
    """Verify trace includes reasoning steps."""
    result = context['result']

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT reasoning FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        reasoning = json.loads(row['reasoning'])
        assert len(reasoning) > 0
