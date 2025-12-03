"""
Step definitions for inquiry_and_discovery.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity

# Load scenarios from feature file
scenarios('../features/inquiry_and_discovery.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given(parsers.parse('a spark "{spark}"'))
def a_spark(context, spark):
    """Store the spark for later use."""
    context['spark'] = spark


@given('an active inquiry')
def an_active_inquiry(factory, context):
    """Create an active inquiry."""
    inquiry = factory.create('inquiry', 'Test Inquiry', spark='Test spark')
    context['inquiry'] = inquiry
    assert inquiry.status == 'active'


@given('an active inquiry with clear intent')
def an_active_inquiry_with_intent(factory, context):
    """Create an active inquiry with clear intent."""
    inquiry = factory.create('inquiry', 'Clear Intent Inquiry',
                             spark='We should build a testing framework')
    context['inquiry'] = inquiry


@given('an agent considering creating a new entity')
def agent_considering_creation(factory, context):
    """Agent is ready to search before create."""
    # Create discover tool if not exists
    discover = Entity(
        id='tool-discover',
        type='tool',
        status='active',
        data={
            'name': 'Discover',
            'description': 'Search before create',
            'handler': {'type': 'llm'}
        }
    )
    try:
        factory.repository.create(discover)
    except:
        pass  # Already exists


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('Factory.create(inquiry, title) is called')
def create_inquiry(factory, context):
    """Create an inquiry with the stored spark."""
    spark = context.get('spark', 'Default spark')
    inquiry = factory.create('inquiry', 'Test Inquiry', spark=spark)
    context['inquiry'] = inquiry


@when('the exploration reaches conclusion')
def exploration_concludes(factory, context):
    """Transition inquiry to resolved."""
    inquiry = context['inquiry']
    context['updated'] = factory.update(inquiry.id, status='resolved')


@when('the inquiry is reified')
def reify_inquiry(factory, context):
    """Transition inquiry to reified."""
    inquiry = context['inquiry']
    context['updated'] = factory.update(inquiry.id, status='reified')


@when('tools are queried')
def query_tools(factory, context):
    """Query all tools from repository."""
    context['tools'] = factory.repository.list(entity_type='tool')


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('an inquiry entity exists with status "{status}"'))
def inquiry_exists_with_status(context, status):
    """Verify inquiry exists with expected status."""
    inquiry = context['inquiry']
    assert inquiry is not None
    assert inquiry.type == 'inquiry'
    assert inquiry.status == status


@then(parsers.parse('the inquiry can transition to "{status}" status'))
def inquiry_can_transition(context, status):
    """Verify inquiry transitioned to expected status."""
    updated = context['updated']
    assert updated.status == status


@then(parsers.parse('the inquiry status is "{status}"'))
def inquiry_status_is(context, status):
    """Verify inquiry has expected status."""
    updated = context['updated']
    assert updated.status == status


@then('a feature can be created with origin link to the inquiry')
def feature_with_origin_link(factory, context):
    """Create feature and link to inquiry."""
    inquiry = context['inquiry']
    feature = factory.create('feature', 'Feature from Inquiry')

    # Update with origin link
    entity = factory.repository.read(feature.id)
    entity.data['origin'] = inquiry.id
    factory.repository.update(entity)

    # Verify link
    updated = factory.repository.read(feature.id)
    assert updated.data.get('origin') == inquiry.id


@then('a discover tool exists and is active')
def discover_tool_exists(context):
    """Verify discover tool exists and is active."""
    tools = context['tools']
    discover = next((t for t in tools if t.id == 'tool-discover'), None)
    assert discover is not None
    assert discover.status == 'active'
