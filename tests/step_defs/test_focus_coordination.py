"""
Step definitions for focus_coordination.feature

Focus as Stigmergic Coordination - enabling agents to coordinate through
focus marks that communicate what attention has settled on.
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from datetime import datetime, timedelta

# Load scenarios from feature file
scenarios('../features/focus_coordination.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Focus Creation
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('an agent in constellation phase with awareness candidates')
def agent_in_constellation(factory, context):
    """Create awareness candidates (entities to focus on)."""
    # Create some entities as candidates
    inquiry = factory.create('inquiry', 'Test Inquiry', spark='What to explore?')
    feature = factory.create('feature', 'Test Feature')
    context['candidates'] = [inquiry.id, feature.id]
    context['inquiry_id'] = inquiry.id


@given('an agent committing focus from an inquiry')
def agent_from_inquiry(factory, context):
    """Create an inquiry that will be the provenance."""
    inquiry = factory.create('inquiry', 'Origin Inquiry', spark='Starting point')
    context['origin_inquiry_id'] = inquiry.id


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Focus Surfacing
# ═══════════════════════════════════════════════════════════════════════════════

@given('multiple foci exist with different statuses')
def multiple_foci(factory, context):
    """Create foci in different lifecycle states."""
    from chora_store.focus import FocusManager

    fm = FocusManager(factory.repository)

    # Create target entities
    inq1 = factory.create('inquiry', 'Inquiry 1', spark='Q1')
    inq2 = factory.create('inquiry', 'Inquiry 2', spark='Q2')
    inq3 = factory.create('inquiry', 'Inquiry 3', spark='Q3')

    # Create foci in different states (new lifecycle: open → unlocked → finalized)
    f_open = fm.create_focus(inq1.id, agent='test-agent')
    f_unlocked = fm.create_focus(inq2.id, agent='test-agent')
    fm.mark_unlocked(f_unlocked.id)
    f_finalized = fm.create_focus(inq3.id, agent='test-agent')
    fm.finalize_focus(f_finalized.id)

    context['foci'] = {
        'open': f_open.id,
        'unlocked': f_unlocked.id,
        'finalized': f_finalized.id
    }


@given('agent A has open focus on entity X')
def agent_a_has_focus(factory, context):
    """Create a focus for agent A."""
    from chora_store.focus import FocusManager

    entity_x = factory.create('inquiry', 'Entity X', spark='Target')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(entity_x.id, agent='agent-A')

    context['entity_x_id'] = entity_x.id
    context['agent_a_focus_id'] = focus.id


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Focus Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

@given('an open focus with TTL configured')
def open_focus_with_ttl(factory, context):
    """Create a focus with TTL that will expire."""
    from chora_store.focus import FocusManager
    from datetime import datetime, timedelta

    entity = factory.create('inquiry', 'TTL Test', spark='Will become stale')
    fm = FocusManager(factory.repository)
    # Create with short TTL for testing
    focus = fm.create_focus(entity.id, agent='test-agent', ttl_minutes=1)

    # Manually set last_cycled to be in the past (beyond TTL)
    focus_entity = factory.repository.read(focus.id)
    past_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    focus_entity.data['last_cycled'] = past_time
    focus_entity.data['started_at'] = past_time
    factory.repository.update(focus_entity)

    context['focus_id'] = focus.id
    context['focus_manager'] = fm


@given('an open focus on entity X')
def open_focus_on_x(factory, context):
    """Create an open focus on entity X."""
    from chora_store.focus import FocusManager

    entity_x = factory.create('inquiry', 'Focus Target X', spark='X')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(entity_x.id, agent='test-agent')

    context['entity_x_id'] = entity_x.id
    context['focus_x_id'] = focus.id
    context['focus_manager'] = fm


@given('a focus with accumulated trail')
def focus_with_trail(factory, context):
    """Create a focus that has accumulated trail."""
    from chora_store.focus import FocusManager

    target = factory.create('inquiry', 'Trail Test', spark='Accumulating')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(target.id, agent='test-agent')

    # Simulate trail accumulation
    learning = factory.create('learning', 'Trail Learning', insight='Emerged')
    fm.add_to_trail(focus.id, learning.id)

    touched = factory.create('feature', 'Touched Feature')
    fm.add_to_trail(focus.id, touched.id)

    context['focus_id'] = focus.id
    context['focus_manager'] = fm
    context['trail_items'] = [learning.id, touched.id]


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Focus as Container
# ═══════════════════════════════════════════════════════════════════════════════

@given('an open focus on inquiry X')
def open_focus_on_inquiry_x(factory, context):
    """Create an open focus on an inquiry."""
    from chora_store.focus import FocusManager

    inquiry_x = factory.create('inquiry', 'Inquiry X', spark='Container test')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(inquiry_x.id, agent='test-agent')

    context['inquiry_x_id'] = inquiry_x.id
    context['focus_id'] = focus.id
    context['focus_manager'] = fm


@given('an open focus')
def open_focus(factory, context):
    """Create a simple open focus."""
    from chora_store.focus import FocusManager

    target = factory.create('inquiry', 'Open Focus', spark='Active')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(target.id, agent='test-agent')

    context['focus_id'] = focus.id
    context['focus_manager'] = fm


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Stigmergic Coordination
# ═══════════════════════════════════════════════════════════════════════════════

@given('a focus with trail and provenance')
def focus_with_trail_and_provenance(factory, context):
    """Create a focus with full context for persistence test."""
    from chora_store.focus import FocusManager

    origin = factory.create('inquiry', 'Origin', spark='Where it started')
    target = factory.create('feature', 'Target Feature')

    fm = FocusManager(factory.repository)
    focus = fm.create_focus(target.id, agent='test-agent', provenance=origin.id)

    learning = factory.create('learning', 'Session Learning', insight='Discovered')
    fm.add_to_trail(focus.id, learning.id)

    context['focus_id'] = focus.id
    context['focus_manager'] = fm


@given("a previous session's focus mark exists")
def previous_session_focus(factory, context):
    """Create a focus mark from a 'previous session'."""
    from chora_store.focus import FocusManager

    target = factory.create('inquiry', 'Previous Work', spark='To be continued')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(target.id, agent='previous-agent')

    # Add some trail
    learning = factory.create('learning', 'Previous Learning', insight='Found this')
    fm.add_to_trail(focus.id, learning.id)

    # Unlock it (simulating session pause - available for pickup)
    fm.mark_unlocked(focus.id)

    context['previous_focus_id'] = focus.id
    context['target_id'] = target.id
    context['focus_manager'] = fm


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps - Closure by Target Type
# ═══════════════════════════════════════════════════════════════════════════════

@given('a closed focus on an inquiry')
def closed_focus_on_inquiry(factory, context):
    """Create a finalized focus on an inquiry (exploratory work completed)."""
    from chora_store.focus import FocusManager

    inquiry = factory.create('inquiry', 'Closed Inquiry', spark='Was exploring')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(inquiry.id, agent='test-agent', target_type='inquiry')
    fm.finalize_focus(focus.id)

    context['inquiry_id'] = inquiry.id
    context['closed_focus_id'] = focus.id
    context['focus_manager'] = fm


@given('a closed focus on a goal that was closed by condition')
def closed_focus_on_goal(factory, context):
    """Create a finalized focus on a goal/feature (condition met)."""
    from chora_store.focus import FocusManager

    feature = factory.create('feature', 'Completed Goal')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(feature.id, agent='test-agent', target_type='goal')
    # Finalize and store the completion reason in focus data
    focus_entity = factory.repository.read(focus.id)
    focus_entity.data['close_reason'] = 'condition_met'
    factory.repository.update(focus_entity)
    fm.finalize_focus(focus.id)

    context['goal_id'] = feature.id
    context['closed_focus_id'] = focus.id
    context['focus_manager'] = fm


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('agent commits attention to an entity')
def commit_attention(factory, context):
    """Agent commits focus to an entity."""
    from chora_store.focus import FocusManager

    fm = FocusManager(factory.repository)
    target_id = context['candidates'][0]  # Pick first candidate
    focus = fm.create_focus(target_id, agent='test-agent')
    context['focus'] = focus
    context['focus_manager'] = fm


@when('focus is created')
def focus_created(factory, context):
    """Create focus with provenance."""
    from chora_store.focus import FocusManager

    target = factory.create('feature', 'Focus Target')
    fm = FocusManager(factory.repository)
    focus = fm.create_focus(
        target.id,
        agent='test-agent',
        provenance=context['origin_inquiry_id']
    )
    context['focus'] = focus


@when('agent runs orient')
def agent_runs_orient(factory, context):
    """Agent runs orient to see awareness candidates."""
    from chora_store.focus import FocusManager

    fm = context.get('focus_manager') or FocusManager(factory.repository)
    candidates = fm.get_awareness_candidates(agent='agent-B')
    context['awareness_candidates'] = candidates


@when('agent B runs orient')
def agent_b_runs_orient(factory, context):
    """Agent B runs orient."""
    from chora_store.focus import FocusManager

    fm = context.get('focus_manager') or FocusManager(factory.repository)
    candidates = fm.get_awareness_candidates(agent='agent-B')
    context['awareness_candidates'] = candidates


@when('TTL duration passes without cycling')
def ttl_passes(context):
    """Simulate TTL expiration."""
    fm = context['focus_manager']
    # Force check for stale foci
    fm.check_and_mark_stale()


@when('agent commits focus to different entity Y')
def commit_to_entity_y(factory, context):
    """Shift focus from X to Y."""
    entity_y = factory.create('inquiry', 'Entity Y', spark='New focus')
    fm = context['focus_manager']
    new_focus = fm.shift_focus(context['focus_x_id'], entity_y.id, agent='test-agent')
    context['entity_y_id'] = entity_y.id
    context['focus_y'] = new_focus


@when('focus is finalized')
def finalize_focus(context):
    """Finalize the focus."""
    fm = context['focus_manager']
    result = fm.finalize_focus(context['focus_id'])
    context['finalization_result'] = result


@when('learning is created during focused work')
def create_learning_during_focus(factory, context):
    """Create a learning while focus is active."""
    fm = context['focus_manager']
    learning = factory.create('learning', 'New Learning', insight='Discovered during focus')
    fm.add_to_trail(context['focus_id'], learning.id, entity_type='learning')
    context['learning_id'] = learning.id


@when('agent touches entities during work')
def touch_entities(factory, context):
    """Simulate touching entities during focused work."""
    fm = context['focus_manager']

    # Touch various entities
    e1 = factory.create('feature', 'Touched 1')
    e2 = factory.create('inquiry', 'Touched 2', spark='Q')

    fm.add_to_trail(context['focus_id'], e1.id)
    fm.add_to_trail(context['focus_id'], e2.id)

    context['touched_entities'] = [e1.id, e2.id]


@when('session ends')
def session_ends(context):
    """Session ends - focus should persist."""
    # Focus is already persisted in repository
    # This step verifies persistence
    pass


@when('new agent orients and requests recovery')
def new_agent_recovery(factory, context):
    """New agent tries to recover previous focus."""
    from chora_store.focus import FocusManager

    fm = context['focus_manager']
    # Find recoverable focus for the target
    recovered = fm.recover_focus(context['target_id'], agent='new-agent')
    context['recovered_focus'] = recovered


@when('agent reopens focus on same inquiry')
def reopen_inquiry_focus(context):
    """Reopen focus on the same inquiry."""
    fm = context['focus_manager']
    new_focus = fm.reopen_focus(context['inquiry_id'], agent='test-agent')
    context['new_focus'] = new_focus


@when('focus is reopened on same goal')
def reopen_goal_focus(context):
    """Reopen focus on the same goal."""
    fm = context['focus_manager']
    result = fm.reopen_focus(context['goal_id'], agent='test-agent')
    context['reopen_result'] = result


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('a focus is created with target and started_at timestamp')
def focus_has_target_and_timestamp(context):
    """Verify focus has required fields."""
    focus = context['focus']
    assert focus is not None
    assert focus.data.get('target') is not None
    assert focus.data.get('started_at') is not None


@then('focus provenance links to the source inquiry')
def focus_has_provenance(context):
    """Verify focus has provenance."""
    focus = context['focus']
    assert focus.data.get('provenance') == context['origin_inquiry_id']


@then('only unfinalized foci are surfaced as awareness candidates')
def only_unfinalized_surfaced(context):
    """Verify only open and unlocked foci are surfaced."""
    candidates = context['awareness_candidates']
    candidate_ids = [c['id'] for c in candidates]
    foci = context['foci']

    # Open and unlocked should be surfaced
    assert foci['open'] in candidate_ids or any(foci['open'] in str(c) for c in candidates)
    assert foci['unlocked'] in candidate_ids or any(foci['unlocked'] in str(c) for c in candidates)

    # Finalized should NOT be surfaced
    assert foci['finalized'] not in candidate_ids


@then("agent B sees agent A's focus on X")
def agent_b_sees_agent_a(context):
    """Verify stigmergic visibility."""
    candidates = context['awareness_candidates']
    # Should see the focus from agent A
    found = any(
        c.get('agent') == 'agent-A' or
        context['entity_x_id'] in str(c)
        for c in candidates
    )
    assert found, f"Agent B should see Agent A's focus. Candidates: {candidates}"


@then('focus transitions to stale status')
def focus_is_stale(context):
    """Verify focus became unlocked (was called stale in old model)."""
    fm = context['focus_manager']
    focus = fm.get_focus(context['focus_id'])
    # Accept either 'unlocked' (new) or 'stale' (legacy alias)
    assert focus.status in ('unlocked', 'stale') or focus.data.get('status') in ('unlocked', 'stale')


@then('focus on X is closed and focus on Y is opened')
def x_closed_y_opened(factory, context):
    """Verify focus shift (X unlocked, Y opened)."""
    fm = context['focus_manager']

    # X should be unlocked (was 'closed' in old model)
    focus_x = fm.get_focus(context['focus_x_id'])
    assert focus_x.status == 'unlocked' or focus_x.data.get('status') == 'unlocked'

    # Y should be open
    focus_y = context['focus_y']
    assert focus_y.status == 'open' or focus_y.data.get('status') == 'open'


@then('trail is harvested and focus is archived')
def trail_harvested(context):
    """Verify finalization harvested trail."""
    result = context['finalization_result']
    assert result is not None
    assert 'trail' in result or 'harvested' in str(result)

    fm = context['focus_manager']
    focus = fm.get_focus(context['focus_id'])
    assert focus.status == 'finalized' or focus.data.get('status') == 'finalized'


@then('learning links to the active focus')
def learning_linked_to_focus(factory, context):
    """Verify learning is linked to focus."""
    fm = context['focus_manager']
    focus = fm.get_focus(context['focus_id'])
    trail = focus.data.get('trail', [])
    assert context['learning_id'] in trail


@then('touched entities are recorded in focus trail')
def entities_in_trail(context):
    """Verify touched entities are in trail."""
    fm = context['focus_manager']
    focus = fm.get_focus(context['focus_id'])
    trail = focus.data.get('trail', [])
    for entity_id in context['touched_entities']:
        assert entity_id in trail


@then('focus mark persists in shared substrate')
def focus_persists(factory, context):
    """Verify focus mark is persisted."""
    fm = context['focus_manager']
    focus = fm.get_focus(context['focus_id'])
    assert focus is not None
    # Verify it has trail and provenance
    assert focus.data.get('trail') or focus.data.get('provenance')


@then('agent can resume with target trail and provenance')
def can_resume_focus(context):
    """Verify focus is recoverable."""
    recovered = context['recovered_focus']
    assert recovered is not None
    assert recovered.data.get('target') == context['target_id']
    # Should have trail from previous session
    assert recovered.data.get('trail') is not None


@then('new focus is created linked to prior focus')
def new_focus_linked_to_prior(context):
    """Verify new focus links to prior (natural continuation)."""
    new_focus = context['new_focus']
    assert new_focus is not None
    # Should link to prior focus in provenance
    assert new_focus.data.get('prior_focus') == context['closed_focus_id']


@then('system signals potential inquiry in disguise')
def signals_inquiry_in_disguise(context):
    """Verify system signals the pattern."""
    result = context['reopen_result']
    # Should have a signal/warning about reopening a goal
    assert result is not None
    assert result.data.get('signal') == 'inquiry_in_disguise' or \
           'inquiry_in_disguise' in str(result.data)
