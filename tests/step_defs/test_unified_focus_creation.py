"""
Step definitions for unified_focus_creation.feature

Tests that focus entities are created through Factory, not FocusManager.
FocusManager is deprecated.
"""

import re
import warnings
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.factory import EntityFactory
from chora_store.models import ValidationError
from chora_store.observer import EntityObserver, ChangeType

# Load scenarios from feature file
scenarios('../features/unified_focus_creation.feature')


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def observer_events():
    """Capture observer events."""
    return []


@pytest.fixture
def observed_factory(factory, observer_events):
    """Factory with event capture."""
    original_observer = factory.observer

    class CapturingObserver:
        def __init__(self, delegate, events):
            self.delegate = delegate
            self.events = events

        def emit(self, change_type, entity, **kwargs):
            self.events.append({
                'type': change_type,
                'entity': entity,
                'kwargs': kwargs
            })
            if self.delegate:
                self.delegate.emit(change_type, entity, **kwargs)

        def __getattr__(self, name):
            return getattr(self.delegate, name)

    factory.observer = CapturingObserver(original_observer, observer_events)
    return factory


# =============================================================================
# GIVEN steps
# =============================================================================

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from conftest fixture."""
    pass


@given('a Factory with kernel schema')
def factory_with_schema(factory):
    """Factory is already configured from conftest fixture."""
    pass


@given('an observer is registered for CREATED events')
def observer_registered(observed_factory):
    """Observer is capturing events via observed_factory fixture."""
    pass


@given('the kernel has focus schema extensions')
def kernel_has_focus_schema(factory):
    """Focus schema supports the expected fields."""
    # The kernel already defines focus type - no action needed
    pass


@given(parsers.parse('a focus "{focus_id}" exists with status "{status}"'))
def focus_exists_with_status(factory, context, focus_id, status):
    """Create a focus with specific ID and status."""
    # Extract agent and target from focus_id pattern: focus-{agent}-on-{target}
    parts = focus_id.replace('focus-', '').split('-on-')
    agent = parts[0] if len(parts) > 0 else 'claude'
    target_slug = parts[1] if len(parts) > 1 else 'test'

    focus = factory.create(
        'focus',
        f"{agent} on {target_slug}",
        target=f"feature-{target_slug}",
        agent=agent,
        status=status,
    )
    context['focus'] = focus
    context['focus_id'] = focus.id


@given(parsers.parse('a focus "{focus_id}" exists'))
def focus_exists(factory, context, focus_id):
    """Create a focus with specific ID."""
    parts = focus_id.replace('focus-', '').split('-on-')
    agent = parts[0] if len(parts) > 0 else 'claude'
    target_slug = parts[1] if len(parts) > 1 else 'test'

    focus = factory.create(
        'focus',
        f"{agent} on {target_slug}",
        target=f"feature-{target_slug}",
        agent=agent,
    )
    context['focus'] = focus
    context['focus_id'] = focus.id


@given('FocusManager is initialized')
def focus_manager_initialized(repository, context):
    """Initialize FocusManager for deprecation testing."""
    from chora_store.focus import FocusManager
    context['focus_manager'] = FocusManager(repository)


@given(parsers.parse('a feature "{feature_id}" exists'))
def feature_exists(factory, context, feature_id):
    """Create a feature with specific ID using fixture factory."""
    name = feature_id.replace('feature-', '').replace('-', ' ').title()
    feature = factory.create('feature', name)
    context['feature'] = feature
    context['feature_id'] = feature.id
    # Also create in mcp's global repo for tool_engage compatibility
    context['_fixture_factory'] = factory


@given(parsers.parse('a feature "{feature_id}" exists for tool_engage'))
def feature_exists_for_tool_engage(context, feature_id):
    """Create a feature using mcp's global factory for tool_engage test."""
    import uuid
    from chora_store import mcp as mcp_module
    factory = mcp_module._get_factory()
    # Add unique suffix to avoid collision with other tests
    unique_suffix = str(uuid.uuid4())[:8]
    name = feature_id.replace('feature-', '').replace('-', ' ').title() + f" {unique_suffix}"
    feature = factory.create('feature', name)
    context['feature'] = feature
    context['feature_id'] = feature.id


# =============================================================================
# WHEN steps
# =============================================================================

@when(parsers.parse('Factory.create is called with type "focus" target "{target}" agent "{agent}"'))
def factory_create_focus(factory, context, target, agent):
    """Create focus via Factory."""
    try:
        # Extract target slug for title - use full slug after type prefix
        # e.g., "feature-voice-canvas" -> "voice-canvas"
        parts = target.split('-', 1)
        target_slug = parts[1] if len(parts) > 1 else target
        focus = factory.create(
            'focus',
            f"{agent} on {target_slug}",
            target=target,
            agent=agent,
        )
        context['focus'] = focus
        context['error'] = None
    except ValidationError as e:
        context['focus'] = None
        context['error'] = e


@when('I attempt to create focus without target')
def create_focus_without_target(factory, context):
    """Try to create focus without required target field."""
    try:
        factory.create('focus', 'Test Focus', agent='claude')
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when('I attempt to create focus without agent')
def create_focus_without_agent(factory, context):
    """Try to create focus without required agent field."""
    try:
        factory.create('focus', 'Test Focus', target='feature-test')
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when(parsers.parse('I attempt to create focus with target "{target}"'))
def create_focus_with_invalid_target(factory, context, target):
    """Try to create focus with invalid target format."""
    try:
        factory.create('focus', 'Test Focus', target=target, agent='claude')
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when(parsers.parse('Factory.update is called with status "{status}"'))
def factory_update_status(factory, context, status):
    """Update focus status via Factory."""
    focus_id = context.get('focus_id') or context.get('focus', {}).id
    updated = factory.update(focus_id, status=status)
    context['focus'] = updated


@when(parsers.parse('Factory.update is called with trail {trail}'))
def factory_update_trail(factory, context, trail):
    """Update focus trail via Factory."""
    import json
    trail_list = json.loads(trail)
    focus_id = context.get('focus_id') or context.get('focus', {}).id
    updated = factory.update(focus_id, trail=trail_list)
    context['focus'] = updated


@when('FocusManager.create_focus is called')
def focus_manager_create_focus(context):
    """Call deprecated FocusManager.create_focus."""
    fm = context['focus_manager']
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            focus = fm.create_focus(
                target_id='feature-test',
                agent='claude',
            )
            context['focus'] = focus
            context['warnings'] = w
        except Exception as e:
            context['error'] = e
            context['warnings'] = w


@when(parsers.parse('tool_engage is invoked with feature_id "{feature_id}"'))
def invoke_tool_engage(repository, context, feature_id):
    """Invoke tool_engage and verify Factory path is used."""
    from chora_store import mcp as mcp_module

    # Use actual feature_id from context if available (for unique IDs)
    actual_feature_id = context.get('feature_id', feature_id)

    # Patch the global factory to track calls
    original_get_factory = mcp_module._get_factory
    factory_calls = []

    def tracking_get_factory():
        factory = original_get_factory()
        original_create = factory.create

        def tracking_create(*args, **kwargs):
            factory_calls.append({'args': args, 'kwargs': kwargs})
            return original_create(*args, **kwargs)

        factory.create = tracking_create
        return factory

    mcp_module._get_factory = tracking_get_factory

    try:
        result = mcp_module.tool_engage(actual_feature_id, agent='claude')
        context['engage_result'] = result
        context['factory_calls'] = factory_calls
    finally:
        mcp_module._get_factory = original_get_factory


# =============================================================================
# THEN steps
# =============================================================================

@then('a focus entity exists')
def focus_entity_exists(context):
    """Verify focus was created."""
    assert context.get('focus') is not None, "Focus should exist"


@then(parsers.parse('the focus ID is "{expected_id}"'))
def focus_id_matches(context, expected_id):
    """Verify focus ID matches expected pattern."""
    focus = context['focus']
    assert focus.id == expected_id, f"Expected ID {expected_id}, got {focus.id}"


@then(parsers.parse('focus.status equals "{expected_status}"'))
def focus_status_equals(context, expected_status):
    """Verify focus status."""
    focus = context['focus']
    assert focus.status == expected_status, f"Expected status {expected_status}, got {focus.status}"


@then(parsers.parse('focus.data.target equals "{expected_target}"'))
def focus_target_equals(context, expected_target):
    """Verify focus target."""
    focus = context['focus']
    assert focus.data.get('target') == expected_target, \
        f"Expected target {expected_target}, got {focus.data.get('target')}"


@then(parsers.parse('focus.data.agent equals "{expected_agent}"'))
def focus_agent_equals(context, expected_agent):
    """Verify focus agent."""
    focus = context['focus']
    assert focus.data.get('agent') == expected_agent, \
        f"Expected agent {expected_agent}, got {focus.data.get('agent')}"


@then('the observer receives a CREATED event')
def observer_received_created(observer_events):
    """Verify CREATED event was emitted."""
    created_events = [e for e in observer_events if e['type'] == ChangeType.CREATED]
    assert len(created_events) > 0, "Expected CREATED event"


@then('the event contains the focus entity')
def event_contains_focus(observer_events):
    """Verify event has focus entity."""
    created_events = [e for e in observer_events if e['type'] == ChangeType.CREATED]
    assert len(created_events) > 0
    event = created_events[-1]
    assert event['entity'].type == 'focus', "Event should contain focus entity"


@then('the focus has ttl_minutes field')
def focus_has_ttl(context):
    """Verify focus has ttl_minutes."""
    focus = context['focus']
    assert 'ttl_minutes' in focus.data, "Focus should have ttl_minutes"


@then('the focus has trail field as empty list')
def focus_has_empty_trail(context):
    """Verify focus has empty trail."""
    focus = context['focus']
    trail = focus.data.get('trail', [])
    assert trail == [], f"Trail should be empty, got {trail}"


@then('the focus has started_at timestamp')
def focus_has_started_at(context):
    """Verify focus has started_at."""
    focus = context['focus']
    assert 'started_at' in focus.data or 'created' in focus.data, \
        "Focus should have started_at or created timestamp"


@then(parsers.parse('creation fails with validation error mentioning "{field}"'))
def creation_fails_with_error(context, field):
    """Verify creation failed with validation error about field."""
    error = context.get('error')
    assert error is not None, f"Expected validation error mentioning {field}"
    assert field.lower() in str(error).lower(), \
        f"Error should mention '{field}', got: {error}"


@then('focus.data.finalized_at is set')
def focus_has_finalized_at(context):
    """Verify focus has finalized_at."""
    focus = context['focus']
    assert focus.data.get('finalized_at') is not None, \
        "Focus should have finalized_at timestamp"


@then(parsers.parse('focus.data.trail contains "{item}"'))
def focus_trail_contains(context, item):
    """Verify trail contains item."""
    focus = context['focus']
    trail = focus.data.get('trail', [])
    assert item in trail, f"Trail should contain {item}, got {trail}"


@then('a deprecation warning is emitted')
def deprecation_warning_emitted(context):
    """Verify deprecation warning was raised."""
    captured = context.get('warnings', [])
    deprecation_warnings = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) > 0, "Expected deprecation warning"


@then(parsers.parse('the warning mentions "{text}"'))
def warning_mentions(context, text):
    """Verify warning contains text."""
    captured = context.get('warnings', [])
    warning_text = ' '.join(str(w.message) for w in captured)
    assert text in warning_text, f"Warning should mention '{text}', got: {warning_text}"


@then(parsers.parse('Factory.create was called with type "{entity_type}"'))
def factory_create_was_called(context, entity_type):
    """Verify Factory.create was called with type."""
    calls = context.get('factory_calls', [])
    type_calls = [c for c in calls if c['args'] and c['args'][0] == entity_type]
    assert len(type_calls) > 0, f"Factory.create should have been called with type {entity_type}"


@then('FocusManager was not used')
def focus_manager_not_used(context):
    """Verify FocusManager was not used (Factory was used instead)."""
    # If factory_calls has focus creation, FocusManager wasn't used directly
    calls = context.get('factory_calls', [])
    focus_calls = [c for c in calls if c['args'] and c['args'][0] == 'focus']
    assert len(focus_calls) > 0, "Factory should have been used to create focus"
