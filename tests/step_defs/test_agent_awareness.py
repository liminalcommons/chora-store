"""
Step definitions for agent_awareness.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.cli import get_workspace_context, _get_time_since_last_orient, get_constellation

# Load scenarios from feature file
scenarios('../features/agent_awareness.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('an agent arriving at the workspace')
def agent_arriving(context):
    """Agent is ready to orient."""
    pass


@given('active features exist in the repository')
def active_features_exist(factory, context):
    """Create some active features."""
    factory.create('feature', 'Active Feature 1', status='nascent')
    factory.create('feature', 'Active Feature 2', status='converging')


@given('a current focus exists')
def current_focus_exists(factory, context):
    """Create an inquiry as current focus."""
    factory.create('inquiry', 'Current Focus Inquiry',
                   spark='What should we work on?')


@given('an entity with relationships')
def entity_with_relationships(factory, context):
    """Create entities with relationships."""
    # Create inquiry
    inquiry = factory.create('inquiry', 'Origin Inquiry',
                             spark='Test spark')

    # Create feature linked to inquiry
    feature = factory.create('feature', 'Linked Feature')
    entity = factory.repository.read(feature.id)
    entity.data['origin'] = inquiry.id
    factory.repository.update(entity)

    context['feature_id'] = feature.id
    context['inquiry_id'] = inquiry.id


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('orient() is called')
def call_orient(context):
    """Get time since last orientation."""
    context['time_since'] = _get_time_since_last_orient()


@when('get_workspace_context() is called')
def call_workspace_context(factory, context):
    """Get workspace context."""
    context['ctx'] = get_workspace_context(factory.repository)


@when('constellation(entity_id) is called')
def call_constellation(factory, context):
    """Get constellation for entity - calls real get_constellation()."""
    feature_id = context['feature_id']
    # Call the real get_constellation function with injected repository
    result = get_constellation(feature_id, factory.repository)
    context['constellation'] = result


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('output includes time since last orientation')
def output_includes_time(context):
    """Verify temporal grounding is present."""
    time_since = context['time_since']
    assert time_since is not None
    assert isinstance(time_since, str)


@then('the context includes active work items')
def context_includes_work(context):
    """Verify context includes work items."""
    ctx = context['ctx']
    # Context should have some work-related keys
    assert 'season' in ctx or 'recent_work' in ctx or 'current_focus' in ctx


@then('the context includes season and integrity score')
def context_includes_season(context):
    """Verify context includes season and integrity."""
    ctx = context['ctx']
    assert 'season' in ctx
    assert 'integrity_score' in ctx


@then('output shows linked entities')
def output_shows_links(context):
    """Verify constellation shows relationships."""
    constellation = context['constellation']
    inquiry_id = context['inquiry_id']

    # Constellation should be a dict with focus and upstream
    assert isinstance(constellation, dict), f"Expected dict, got {type(constellation)}"
    assert 'error' not in constellation, f"Constellation returned error: {constellation.get('error')}"
    assert 'focus' in constellation, "Constellation should have focus"

    # Upstream should contain the origin inquiry
    upstream = constellation.get('upstream', [])
    upstream_ids = [e['id'] for e in upstream]
    assert inquiry_id in upstream_ids, f"Expected {inquiry_id} in upstream {upstream_ids}"
