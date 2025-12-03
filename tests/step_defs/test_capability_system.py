"""
Step definitions for capability_system.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity
from chora_store.mcp import _execute_compose_handler

# Load scenarios from feature file
scenarios('../features/capability_system.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('tool entities exist in the repository')
def tools_exist(factory, context):
    """Create some tool entities."""
    for i in range(3):
        tool = Entity(
            id=f'tool-test-{i}',
            type='tool',
            status='active',
            data={
                'name': f'Test Tool {i}',
                'handler': {'type': 'reference', 'function': f'func_{i}'}
            }
        )
        factory.repository.create(tool)
    context['tool_count'] = 3


@given('a tool entity')
def a_tool_entity(factory, context):
    """Create a single tool entity."""
    tool = Entity(
        id='tool-single',
        type='tool',
        status='active',
        data={
            'name': 'Single Tool',
            'handler': {'type': 'llm', 'prompt_template': 'Test prompt'}
        }
    )
    factory.repository.create(tool)
    context['tool'] = tool


@given('the repository has some tools')
def repository_has_tools(factory, context):
    """Create initial tools and record count."""
    for i in range(2):
        tool = Entity(
            id=f'tool-initial-{i}',
            type='tool',
            status='active',
            data={'name': f'Initial Tool {i}', 'handler': {'type': 'reference'}}
        )
        factory.repository.create(tool)
    context['initial_count'] = len(factory.repository.list(entity_type='tool'))


@given('an active tool with handler')
def active_tool_with_handler(factory, context):
    """Create an active tool with a compose handler that can be invoked."""
    tool = Entity(
        id='tool-invocable',
        type='tool',
        status='active',
        data={
            'name': 'Greeting Tool',
            'handler': {
                'type': 'compose',
                'template': 'Hello, {{ name }}! Welcome to {{ place }}.'
            }
        }
    )
    factory.repository.create(tool)
    context['tool_id'] = tool.id


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('repository.list(entity_type=tool) is called')
def list_tools(factory, context):
    """Query tools from repository."""
    context['tools'] = factory.repository.list(entity_type='tool')


@when('tool data is inspected')
def inspect_tool(factory, context):
    """Read tool data."""
    tool = context['tool']
    context['retrieved'] = factory.repository.read(tool.id)


@when('a new tool entity is created')
def create_new_tool(factory, context):
    """Create a new tool entity."""
    tool = Entity(
        id='tool-hot-reload',
        type='tool',
        status='active',
        data={'name': 'Hot Reload Tool', 'handler': {'type': 'reference'}}
    )
    factory.repository.create(tool)
    context['new_tool_id'] = tool.id


@when('the tool is retrieved')
def retrieve_tool(factory, context):
    """Retrieve the tool by ID and invoke its handler."""
    tool = factory.repository.read(context['tool_id'])
    context['retrieved'] = tool

    # Actually invoke the handler
    handler = tool.data.get('handler', {})
    if handler.get('type') == 'compose':
        result = _execute_compose_handler(handler, {'name': 'Agent', 'place': 'Chora'})
        context['invoke_result'] = result


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('all registered tools are returned')
def all_tools_returned(context):
    """Verify all tools are returned."""
    tools = context['tools']
    assert len(tools) >= context['tool_count']
    tool_ids = [t.id for t in tools]
    for i in range(context['tool_count']):
        assert f'tool-test-{i}' in tool_ids


@then(parsers.parse('handler with type "{type1}" or "{type2}" or "{type3}" is present'))
def handler_present(context, type1, type2, type3):
    """Verify handler is present with valid type."""
    tool = context['retrieved']
    assert 'handler' in tool.data
    handler_type = tool.data['handler'].get('type')
    assert handler_type in [type1, type2, type3]


@then('the tool is immediately available via list')
def tool_immediately_available(factory, context):
    """Verify new tool is immediately queryable."""
    tools = factory.repository.list(entity_type='tool')
    new_count = len(tools)
    assert new_count == context['initial_count'] + 1
    assert any(t.id == context['new_tool_id'] for t in tools)


@then('handler is present and tool can be invoked')
def handler_present_invocable(context):
    """Verify tool has handler and can actually be invoked."""
    tool = context['retrieved']
    assert tool.status == 'active'
    assert 'handler' in tool.data
    handler = tool.data['handler']
    assert 'type' in handler

    # Verify actual invocation result
    invoke_result = context.get('invoke_result')
    assert invoke_result is not None, "Tool was not invoked"
    assert 'Hello, Agent!' in invoke_result, f"Unexpected result: {invoke_result}"
    assert 'Welcome to Chora' in invoke_result, f"Template not rendered: {invoke_result}"
