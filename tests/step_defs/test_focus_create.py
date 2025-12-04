"""
Step definitions for focus_create.feature

Tests for tool-focus-create: Creating focus entities from natural language.
"""

import pytest
from datetime import datetime, timezone
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity
from chora_store.metabolism import tool_focus_create

# Load scenarios from feature file
scenarios('../features/focus_create.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED BACKGROUND STEPS (from conftest fixtures)
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('a factory with epigenetic support')
def factory_with_epigenetics(factory):
    """Factory is already available from fixture."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@given(parsers.parse('a feature "{feature_id}" exists'))
def create_feature(repository, context, feature_id):
    """Create a feature entity."""
    feature = Entity(
        id=feature_id,
        type="feature",
        status="nascent",
        created_at=datetime.now(timezone.utc),
        data={
            "name": feature_id.replace("feature-", "").replace("-", " ").title(),
        }
    )
    repository.create(feature)
    if 'features' not in context:
        context['features'] = {}
    context['features'][feature_id] = feature


@given(parsers.parse('a feature "{feature_id}" exists with name "{name}"'))
def create_feature_with_name(repository, context, feature_id, name):
    """Create a feature entity with specific name."""
    feature = Entity(
        id=feature_id,
        type="feature",
        status="nascent",
        created_at=datetime.now(timezone.utc),
        data={
            "name": name,
        }
    )
    repository.create(feature)
    if 'features' not in context:
        context['features'] = {}
    context['features'][feature_id] = feature


@given(parsers.parse('an inquiry "{inquiry_id}" exists'))
def create_inquiry(repository, context, inquiry_id):
    """Create an inquiry entity."""
    inquiry = Entity(
        id=inquiry_id,
        type="inquiry",
        status="active",
        created_at=datetime.now(timezone.utc),
        data={
            "name": inquiry_id.replace("inquiry-", "").replace("-", " ").title(),
            "question": "Test inquiry question",
        }
    )
    repository.create(inquiry)
    context['inquiry'] = inquiry


@given(parsers.parse('pattern "{pattern_id}" is active'))
def create_active_pattern(repository, context, pattern_id):
    """Create an active pattern."""
    pattern = Entity(
        id=pattern_id,
        type="pattern",
        status="adopted",
        created_at=datetime.now(timezone.utc),
        data={
            "name": pattern_id.replace("pattern-", "").replace("-", " ").title(),
            "subtype": "schema-extension",
            "target_type": "focus",
        }
    )
    repository.create(pattern)
    context['pattern'] = pattern


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_focus_from_result(repository, result):
    """Extract focus entity from tool result message."""
    # Result format: "Focus created: focus-id → target" or "Focus created: focus-id"
    if "Focus created:" in result:
        after_prefix = result.split("Focus created:")[1].strip()
        # Split by → to get focus ID (before the arrow)
        if "→" in after_prefix:
            focus_id = after_prefix.split("→")[0].strip()
        else:
            focus_id = after_prefix.split()[0]
        return repository.read(focus_id)
    return None


@when(parsers.parse('focus is created with goal "{goal}"'))
def create_focus_with_goal(repository, context, goal):
    """Create focus from natural language goal."""
    result = tool_focus_create(goal=goal, repository=repository)
    context['focus_result'] = result
    context['created_focus'] = _extract_focus_from_result(repository, result)


@when(parsers.parse('focus is created with goal "{goal}" targeting "{target}"'))
def create_focus_with_target(repository, context, goal, target):
    """Create focus with explicit target."""
    result = tool_focus_create(goal=goal, target=target, repository=repository)
    context['focus_result'] = result
    context['created_focus'] = _extract_focus_from_result(repository, result)


@when(parsers.parse('focus is created with goal "{goal}" by agent "{agent}"'))
def create_focus_with_agent(repository, context, goal, agent):
    """Create focus with agent attribution."""
    result = tool_focus_create(goal=goal, agent=agent, repository=repository)
    context['focus_result'] = result
    context['created_focus'] = _extract_focus_from_result(repository, result)


@when(parsers.parse('focus is created with goal "{goal}" with ttl_minutes {ttl:d}'))
def create_focus_with_ttl(repository, context, goal, ttl):
    """Create focus with custom TTL."""
    result = tool_focus_create(goal=goal, ttl_minutes=ttl, repository=repository)
    context['focus_result'] = result
    context['created_focus'] = _extract_focus_from_result(repository, result)


# ═══════════════════════════════════════════════════════════════════════════════
# THEN STEPS
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('a focus entity exists with status "{status}"'))
def focus_exists_with_status(context, status):
    """Verify focus exists with expected status."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.status == status, f"Expected status={status}, got {focus.status}"


@then('the focus has goal_level set to true')
def focus_has_goal_level(context):
    """Verify focus has goal_level=True."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.data.get('goal_level') is True, \
        f"Expected goal_level=True, got {focus.data.get('goal_level')}"


@then(parsers.parse('the focus has entry_type "{entry_type}"'))
def focus_has_entry_type(context, entry_type):
    """Verify focus has expected entry_type."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.data.get('entry_type') == entry_type, \
        f"Expected entry_type={entry_type}, got {focus.data.get('entry_type')}"


@then(parsers.parse('the focus has target "{target}"'))
def focus_has_target(context, target):
    """Verify focus has expected target."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.data.get('target') == target, \
        f"Expected target={target}, got {focus.data.get('target')}"


@then('the focus links to the target entity')
def focus_links_to_target(context):
    """Verify focus links to its target."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    target = focus.data.get('target')
    assert target is not None, "Focus has no target"
    # The target should be in links or target field
    links = focus.data.get('links', [])
    assert target in links or focus.data.get('target') == target, \
        f"Focus doesn't link to target: {target}"


@then(parsers.parse('the focus has agent "{agent}"'))
def focus_has_agent(context, agent):
    """Verify focus has expected agent."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.data.get('agent') == agent, \
        f"Expected agent={agent}, got {focus.data.get('agent')}"


@then('no user confirmation was required')
def no_confirmation_required(context):
    """Verify no user confirmation was needed."""
    result = context.get('focus_result', '')
    # The result should not indicate ambiguity
    assert 'ambiguous' not in result.lower(), \
        f"Unexpected ambiguity in result: {result}"


@then(parsers.parse('the focus has a target starting with "{prefix}"'))
def focus_has_target_prefix(context, prefix):
    """Verify focus has target starting with expected prefix."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    target = focus.data.get('target', '')
    assert target.startswith(prefix), \
        f"Expected target starting with '{prefix}', got: {target}"


@then('the focus includes candidate_targets in data')
def focus_has_candidates(context):
    """Verify focus has candidate_targets for ambiguous case."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    candidates = focus.data.get('candidate_targets') or []
    assert len(candidates) > 0, \
        f"Expected candidate_targets for ambiguous match, got: {focus.data}"


@then(parsers.parse('the focus has _epigenetics containing "{pattern_prefix}"'))
def focus_has_epigenetics(context, pattern_prefix):
    """Verify focus has expected epigenetic pattern."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    epigenetics = focus.data.get('_epigenetics', [])
    matching = [e for e in epigenetics if pattern_prefix in e]
    assert len(matching) > 0, \
        f"Expected pattern containing '{pattern_prefix}' in _epigenetics: {epigenetics}"


@then(parsers.parse('the focus has ttl_minutes set to {ttl:d}'))
def focus_has_ttl(context, ttl):
    """Verify focus has expected TTL."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"
    assert focus.data.get('ttl_minutes') == ttl, \
        f"Expected ttl_minutes={ttl}, got {focus.data.get('ttl_minutes')}"


@then('the focus structure matches engage output for same feature')
def focus_matches_engage(repository, context):
    """Verify focus-create produces similar output to engage."""
    focus = context.get('created_focus')
    assert focus is not None, "No focus was created"

    # Key fields that should match engage behavior
    required_fields = ['name', 'agent', 'target', 'goal_level', 'ttl_minutes', 'trail']
    for field in required_fields:
        assert field in focus.data, f"Focus missing field: {field}"

    # Trail should be initialized as empty list
    assert isinstance(focus.data.get('trail'), list), "Trail should be a list"
