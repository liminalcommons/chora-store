"""
Step definitions for learning_system.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.evaluator import PatternInductor

# Load scenarios from feature file
scenarios('../features/learning_system.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given(parsers.parse('an insight "{insight}"'))
def an_insight(context, insight):
    """Store insight for later use."""
    context['insight'] = insight


@given('a captured learning')
def captured_learning(factory, context):
    """Create a captured learning."""
    learning = factory.create('learning', 'Test Learning',
                              insight='Test insight for validation')
    context['learning'] = learning
    assert learning.status == 'captured'


@given('a validated learning')
def validated_learning(factory, context):
    """Create and validate a learning."""
    learning = factory.create('learning', 'Validated Learning',
                              insight='Test insight for application')
    factory.update(learning.id, status='validated')
    context['learning'] = factory.repository.read(learning.id)
    assert context['learning'].status == 'validated'


@given('multiple validated learnings with common themes')
def multiple_learnings(factory, context):
    """Create multiple learnings for pattern induction."""
    for i in range(3):
        learning = factory.create('learning', f'Theme Learning {i}',
                                  insight=f'Testing patterns are important {i}')
        factory.update(learning.id, status='validated')
    context['learning_count'] = 3


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('Factory.create(learning, title, insight) is called')
def create_learning(factory, context):
    """Create a learning with stored insight."""
    insight = context.get('insight', 'Default insight')
    learning = factory.create('learning', 'Test Learning', insight=insight)
    context['learning'] = learning


@when('the learning is reviewed and confirmed useful')
def review_learning(factory, context):
    """Transition learning to validated."""
    learning = context['learning']
    context['learning'] = factory.update(learning.id, status='validated')


@when('the learning is incorporated into practice')
def apply_learning(factory, context):
    """Transition learning to applied."""
    learning = context['learning']
    context['learning'] = factory.update(learning.id, status='applied')


@when('PatternInductor.analyze() is called')
def analyze_patterns(factory, context):
    """Run pattern induction analysis."""
    inductor = PatternInductor(factory.repository)
    context['proposals'] = inductor.analyze()


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('a learning entity exists with status "{status}"'))
def learning_exists_with_status(context, status):
    """Verify learning exists with expected status."""
    learning = context['learning']
    assert learning is not None
    assert learning.type == 'learning'
    assert learning.status == status


@then(parsers.parse('the learning can transition to "{status}" status'))
def learning_can_transition(context, status):
    """Verify learning transitioned to expected status."""
    learning = context['learning']
    assert learning.status == status


@then(parsers.parse('the learning transitions to "{status}" status'))
def learning_transitions_to(context, status):
    """Verify learning has transitioned."""
    learning = context['learning']
    assert learning.status == status


@then('pattern proposals can be generated')
def proposals_generated(context):
    """Verify pattern induction can run."""
    proposals = context['proposals']
    # Should return a list (possibly empty if not enough data)
    assert isinstance(proposals, list)
