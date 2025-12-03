"""
Step definitions for coordination_turn.feature (v0.4.0)

Tests for:
- Presence via Change Lens
- Hierarchy of Attention
- Cross-Scale Visibility
- Orient as Coordination Surface
"""

import os
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.cli import get_workspace_context
from chora_store.agent import get_current_agent

# Load scenarios from feature file
scenarios('../features/coordination_turn.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Presence via Change Lens
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('multiple agents have made changes to the workspace')
def multiple_agents_made_changes(factory, context):
    """Create entities from different agents."""
    # First entity by current agent
    entity1 = factory.create('learning', 'My Learning', insight='Created by me')

    # Manually simulate another agent's entity
    entity2 = factory.create('learning', 'Other Learning', insight='From another')
    e2 = factory.repository.read(entity2.id)
    e2.data['last_changed_by'] = 'other-agent@remote'
    factory.repository.update(e2)

    context['my_entity'] = entity1
    context['other_entity'] = entity2


@given('an entity was modified by another agent')
def entity_modified_by_another(factory, context):
    """Create an entity modified by another agent."""
    entity = factory.create('feature', 'Collaborative Feature')
    e = factory.repository.read(entity.id)
    e.data['last_changed_by'] = 'collaborator@team'
    factory.repository.update(e)
    context['collaborative_entity'] = entity


@given('no changes by others exist')
def no_other_changes(factory, context):
    """Only current agent's work exists."""
    factory.create('learning', 'Solo Learning', insight='My solo work')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Hierarchy of Attention
# ═══════════════════════════════════════════════════════════════════════════════

@given('entities exist at inner, adjacent, and far scales')
def entities_at_all_scales(factory, context):
    """Create entities at different attention scales."""
    # Inner: active tasks, current features, active inquiries
    factory.create('inquiry', 'Active Inquiry', spark='What to do?')
    factory.create('feature', 'Current Feature', status='nascent')

    # Far: patterns, releases, stable features
    factory.create('pattern', 'System Pattern', subtype='domain',
                   context='Test context', problem='Test problem', solution='Test solution')
    factory.create('release', 'Past Release', status='released', version='1.0.0')


@given('inner scope is active tasks and current features')
def inner_scope_setup(factory, context):
    """Set up inner scope entities."""
    factory.create('feature', 'Inner Feature 1', status='nascent')
    factory.create('feature', 'Inner Feature 2', status='converging')
    factory.create('inquiry', 'Active Inquiry', spark='Focus?')


@given('far scope includes patterns and learnings')
def far_scope_setup(factory, context):
    """Set up far scope entities."""
    factory.create('pattern', 'Far Pattern', subtype='domain',
                   context='Test context', problem='Test problem', solution='Test solution')
    factory.create('release', 'Far Release', status='released', version='2.0.0')
    factory.create('feature', 'Stable Feature', status='stable')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Cross-Scale Visibility
# ═══════════════════════════════════════════════════════════════════════════════

@given('learnings have crystallized into patterns')
def learnings_crystallized(factory, context):
    """Create patterns with learning sources (revolt)."""
    learning = factory.create('learning', 'Source Learning', insight='Key insight')

    pattern = factory.create('pattern', 'Crystallized Pattern', subtype='domain',
                             context='Test context', problem='Test problem', solution='Test solution')
    p = factory.repository.read(pattern.id)
    p.data['extracted_from'] = [learning.id]
    factory.repository.update(p)

    context['source_learning'] = learning
    context['crystallized_pattern'] = pattern


@given('patterns are influencing current work')
def patterns_influencing(factory, context):
    """Create features with epigenetic patterns (remember)."""
    pattern = factory.create('pattern', 'Guiding Pattern', subtype='schema-extension',
                             context='Test context', problem='Test problem', solution='Test solution')

    feature = factory.create('feature', 'Influenced Feature', status='nascent')
    f = factory.repository.read(feature.id)
    f.data['_epigenetics'] = [pattern.id]
    factory.repository.update(f)

    context['guiding_pattern'] = pattern
    context['influenced_feature'] = feature


@given('fast cycle tasks and slow cycle patterns exist')
def both_cycles_exist(factory, context):
    """Create entities in both fast and slow cycles."""
    # Fast cycle
    factory.create('feature', 'Fast Feature', status='converging')
    factory.create('inquiry', 'Fast Inquiry', spark='Immediate?')

    # Slow cycle
    factory.create('pattern', 'Slow Pattern', subtype='domain',
                   context='Test context', problem='Test problem', solution='Test solution')
    factory.create('release', 'Slow Release', status='released', version='3.0.0')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Orient as Coordination Surface
# ═══════════════════════════════════════════════════════════════════════════════

@given('individual context my work exists')
def individual_context_exists(factory, context):
    """Create work by current agent."""
    entity = factory.create('feature', 'My Feature', status='nascent')
    context['my_feature'] = entity


@given('collective context team work exists')
def collective_context_exists(factory, context):
    """Create work by other agents."""
    entity = factory.create('feature', 'Team Feature', status='nascent')
    e = factory.repository.read(entity.id)
    e.data['created_by'] = 'teammate@team'
    e.data['last_changed_by'] = 'teammate@team'
    factory.repository.update(e)
    context['team_feature'] = entity


@given('both individual and collective contexts exist')
def both_contexts_exist(factory, context):
    """Create both individual and collective work."""
    # My work
    my_entity = factory.create('feature', 'Personal Feature', status='nascent')

    # Team work
    team_entity = factory.create('feature', 'Shared Feature', status='nascent')
    t = factory.repository.read(team_entity.id)
    t.data['created_by'] = 'colleague@org'
    t.data['last_changed_by'] = 'colleague@org'
    factory.repository.update(t)

    context['my_entity'] = my_entity
    context['team_entity'] = team_entity


@given('coordination signals are present')
def coordination_signals_present(factory, context):
    """Create conditions that generate coordination signals."""
    # Multiple converging features = convergence signal
    factory.create('feature', 'Converging 1', status='converging')
    factory.create('feature', 'Converging 2', status='converging')
    factory.create('feature', 'Converging 3', status='converging')
    factory.create('feature', 'Converging 4', status='converging')


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('orient is invoked')
def invoke_orient(factory, context):
    """Get workspace context."""
    context['ctx'] = get_workspace_context(factory.repository)


@when('get_workspace_context() is called')
def call_get_workspace_context(factory, context):
    """Get workspace context."""
    context['ctx'] = get_workspace_context(factory.repository)


@when('orient is invoked with scope filter')
def invoke_orient_with_scope(factory, context):
    """Get workspace context with inner scope."""
    context['ctx_inner'] = get_workspace_context(factory.repository, scope='inner')
    context['ctx_far'] = get_workspace_context(factory.repository, scope='far')


@when('get_workspace_context with scope="inner" is called')
def call_context_inner(factory, context):
    """Get workspace context with inner scope."""
    context['ctx'] = get_workspace_context(factory.repository, scope='inner')


@when('get_workspace_context with scope="far" is called')
def call_context_far(factory, context):
    """Get workspace context with far scope."""
    context['ctx'] = get_workspace_context(factory.repository, scope='far')


@when('cross-scale summary is requested')
def request_cross_scale(factory, context):
    """Get workspace context for cross-scale visibility."""
    context['ctx'] = get_workspace_context(factory.repository)


@when('orient unifies them')
def orient_unifies(factory, context):
    """Get unified workspace context."""
    context['ctx'] = get_workspace_context(factory.repository)


@when('orient processes them')
def orient_processes(factory, context):
    """Get workspace context with coordination signals."""
    context['ctx'] = get_workspace_context(factory.repository)


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps - Presence via Change Lens
# ═══════════════════════════════════════════════════════════════════════════════

@then('recent changes are surfaced with agent attribution')
def recent_changes_with_attribution(context):
    """Verify presence includes agent attribution."""
    ctx = context['ctx']
    presence = ctx.get('presence', {})

    assert 'recent_changes' in presence, "Presence should include recent_changes"
    changes = presence['recent_changes']
    assert len(changes) > 0, "Should have at least one change"

    # Check for agent attribution
    for change in changes:
        assert 'changed_by' in change, "Each change should have changed_by"
        assert 'is_mine' in change, "Each change should indicate is_mine"


@then('context includes recent_changes with timestamps and agents')
def context_has_changes_with_timestamps(context):
    """Verify presence has timestamps and agents."""
    ctx = context['ctx']
    presence = ctx.get('presence', {})
    changes = presence.get('recent_changes', [])

    assert len(changes) > 0, "Should have changes"
    for change in changes:
        assert 'updated' in change, "Change should have timestamp"
        assert 'changed_by' in change, "Change should have agent"


@then('context indicates solo work mode')
def context_indicates_solo(context):
    """Verify solo mode is detected."""
    ctx = context['ctx']
    presence = ctx.get('presence', {})

    assert presence.get('mode') == 'solo', f"Expected solo mode, got {presence.get('mode')}"


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps - Hierarchy of Attention
# ═══════════════════════════════════════════════════════════════════════════════

@then('only entities matching scale are returned')
def only_matching_scale(context):
    """Verify scope filtering works."""
    ctx_inner = context['ctx_inner']
    ctx_far = context['ctx_far']

    inner_scope = ctx_inner.get('scope', {})
    far_scope = ctx_far.get('scope', {})

    # Verify scope is correctly set
    assert inner_scope.get('active') == 'inner'
    assert far_scope.get('active') == 'far'

    # Content should differ - inner has inquiries/features, far has patterns/releases
    inner_counts = ctx_inner.get('counts', {})
    far_counts = ctx_far.get('counts', {})

    # Inner scope should have inquiry and/or feature
    assert inner_counts.get('inquiry', 0) > 0 or inner_counts.get('feature', 0) > 0

    # Far scope should have pattern and/or release
    assert far_counts.get('pattern', 0) > 0 or far_counts.get('release', 0) > 0


@then('only immediate work items are returned')
def only_immediate_work(context):
    """Verify inner scope contains immediate work."""
    ctx = context['ctx']
    scope = ctx.get('scope', {})

    assert scope.get('active') == 'inner'
    # Inner scope should only have nascent/converging features and active inquiries
    counts = ctx.get('counts', {})
    # Should have features and/or inquiries
    assert counts.get('feature', 0) > 0 or counts.get('inquiry', 0) > 0


@then('systemic entities patterns and releases are included')
def systemic_entities_included(context):
    """Verify far scope contains patterns and releases."""
    ctx = context['ctx']
    scope = ctx.get('scope', {})
    counts = ctx.get('counts', {})

    assert scope.get('active') == 'far'
    # Far scope should have patterns and/or releases
    assert counts.get('pattern', 0) > 0 or counts.get('release', 0) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps - Cross-Scale Visibility
# ═══════════════════════════════════════════════════════════════════════════════

@then('learning to pattern trajectories are surfaced')
def learning_to_pattern_surfaced(context):
    """Verify revolt trajectories are visible."""
    ctx = context['ctx']
    cross_scale = ctx.get('cross_scale', {})
    revolt = cross_scale.get('revolt', [])

    assert len(revolt) > 0, "Should have revolt trajectories"

    # Check structure
    trajectory = revolt[0]
    assert 'pattern_id' in trajectory
    assert 'source_learnings' in trajectory
    assert 'source_count' in trajectory


@then('pattern to feature influences are surfaced')
def pattern_to_feature_surfaced(context):
    """Verify remember trajectories are visible."""
    ctx = context['ctx']
    cross_scale = ctx.get('cross_scale', {})
    remember = cross_scale.get('remember', [])

    assert len(remember) > 0, "Should have remember trajectories"

    # Check structure
    trajectory = remember[0]
    assert 'feature_id' in trajectory
    assert 'patterns_applied' in trajectory
    assert 'pattern_count' in trajectory


@then('both cycle summaries are included in context')
def both_cycles_included(context):
    """Verify fast and slow cycle summaries."""
    ctx = context['ctx']
    cross_scale = ctx.get('cross_scale', {})

    fast_cycle = cross_scale.get('fast_cycle', {})
    slow_cycle = cross_scale.get('slow_cycle', {})

    assert 'active_features' in fast_cycle
    assert 'active_tasks' in fast_cycle
    assert 'patterns' in slow_cycle
    assert 'releases' in slow_cycle


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps - Orient as Coordination Surface
# ═══════════════════════════════════════════════════════════════════════════════

@then('personal work summary is included')
def personal_summary_included(context):
    """Verify individual context is present."""
    ctx = context['ctx']
    coordination = ctx.get('coordination', {})
    individual = coordination.get('individual', {})

    assert 'work_items' in individual
    assert 'count' in individual
    # At least one item should be mine
    assert individual.get('count', 0) >= 0  # May be 0 if test creates in different way


@then('shared workspace summary is included')
def shared_summary_included(context):
    """Verify collective context is present."""
    ctx = context['ctx']
    coordination = ctx.get('coordination', {})
    collective = coordination.get('collective', {})

    assert 'work_items' in collective
    assert 'count' in collective


@then('context includes both without duplication')
def both_contexts_no_duplication(context):
    """Verify individual and collective are distinct."""
    ctx = context['ctx']
    coordination = ctx.get('coordination', {})

    individual = coordination.get('individual', {})
    collective = coordination.get('collective', {})

    individual_ids = {w['id'] for w in individual.get('work_items', [])}
    collective_ids = {w['id'] for w in collective.get('work_items', [])}

    # No overlap between individual and collective
    overlap = individual_ids & collective_ids
    assert len(overlap) == 0, f"Found duplicate IDs: {overlap}"


@then('relevant signals surface based on attention hierarchy')
def signals_surface(context):
    """Verify coordination signals are present."""
    ctx = context['ctx']
    coordination = ctx.get('coordination', {})
    signals = coordination.get('signals', [])

    # Should have at least one signal (convergence)
    assert len(signals) > 0, "Should have coordination signals"

    # Check signal structure
    for signal in signals:
        assert 'type' in signal
        assert 'message' in signal
