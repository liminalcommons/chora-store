"""
MCP server for chora-store with dynamic tool discovery.

Tools are entities in SQLite. This server reads them and exposes them via MCP.
When a tool is invoked, it executes the appropriate handler:
  - reference: calls a Python function
  - compose: renders a template with context
  - llm: renders a prompt template and calls chora-llm

Optional dependency: fastmcp (pip install fastmcp)
If fastmcp is not available, the tools module still works but MCP server won't run.
"""

import json
from typing import Any, Optional

from .factory import EntityFactory
from .repository import EntityRepository
from .cli import get_workspace_context

# Try to import FastMCP, make it optional
try:
    from fastmcp import FastMCP
    MCP_AVAILABLE = True
    _mcp = FastMCP("chora-store", instructions="Local-first entity store with dynamic tools")
except ImportError:
    MCP_AVAILABLE = False
    _mcp = None


# Lazy-loaded singletons
_factory: Optional[EntityFactory] = None
_repo: Optional[EntityRepository] = None


def _get_factory() -> EntityFactory:
    global _factory
    if _factory is None:
        _factory = EntityFactory()
    return _factory


def _get_repo() -> EntityRepository:
    global _repo
    if _repo is None:
        _repo = EntityRepository()
    return _repo


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL FUNCTIONS (work with or without MCP)
# ═══════════════════════════════════════════════════════════════════════════════

def tool_orient() -> str:
    """The greeting - system's first act of care toward the arriving agent.

    Shows what's alive, what's stuck, and what this moment asks.
    Use this at session start to get oriented.
    """
    repo = _get_repo()
    ctx = get_workspace_context(repo)

    # Build the greeting
    lines = []

    # Season
    season = ctx.get('season', 'unknown')
    season_emoji = "🌱" if season == "construction" else "🍂"
    lines.append(f"Season: {season_emoji} {season.title()}")

    # What's alive
    inquiries = ctx.get('active_inquiries', [])
    features = ctx.get('active_features', [])
    tasks = ctx.get('active_tasks', [])

    if inquiries or features or tasks:
        lines.append("")
        lines.append("What's alive:")
        for i in inquiries:
            lines.append(f"  💭 {i['id']}")
        for f in features:
            lines.append(f"  📦 {f['id']} ({f['status']})")
        for t in tasks:
            lines.append(f"  ⚡ {t['id']}")

    # What's stuck
    blocked = ctx.get('blocked', [])
    if blocked:
        lines.append("")
        lines.append("What's stuck:")
        for b in blocked:
            lines.append(f"  ⚠ {b['id']}")

    # What this moment asks
    phase = ctx.get('phase', {})
    suggestion = phase.get('suggestion', '')
    if suggestion:
        lines.append("")
        lines.append(f"This moment asks: {suggestion}")

    return "\n".join(lines)


def tool_list_entities(
    entity_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20
) -> str:
    """List entities in the store."""
    repo = _get_repo()
    entities = repo.list(entity_type=entity_type, status=status, limit=limit)

    if not entities:
        return "No entities found."

    lines = [f"Found {len(entities)} entities:"]
    for e in entities:
        name = e.data.get('name', '')
        if name:
            lines.append(f"  {e.id} ({e.status}) - {name}")
        else:
            lines.append(f"  {e.id} ({e.status})")

    return "\n".join(lines)


def tool_get_entity(entity_id: str) -> str:
    """Get a specific entity by ID."""
    repo = _get_repo()
    entity = repo.read(entity_id)

    if not entity:
        return f"Entity not found: {entity_id}"

    lines = [
        f"id: {entity.id}",
        f"type: {entity.type}",
        f"status: {entity.status}",
        f"version: {entity.version}",
        f"created: {entity.created_at.isoformat()}",
        f"updated: {entity.updated_at.isoformat()}",
        "",
        "data:"
    ]

    for key, value in entity.data.items():
        if isinstance(value, (dict, list)):
            lines.append(f"  {key}: {json.dumps(value, indent=4)}")
        else:
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def tool_list_tools() -> str:
    """List all available dynamic tools."""
    repo = _get_repo()
    tools = repo.list(entity_type='tool', status='active')

    if not tools:
        tools = repo.list(entity_type='tool')

    if not tools:
        return "No tools defined yet."

    lines = ["Available tools:"]
    for t in tools:
        name = t.data.get('name', t.id)
        desc = t.data.get('description', '')[:60]
        status_icon = "✓" if t.status == "active" else "○"
        lines.append(f"  {status_icon} {name}")
        if desc:
            lines.append(f"      {desc}...")

        handler = t.data.get('handler', {})
        handler_type = handler.get('type', 'unknown') if isinstance(handler, dict) else 'unknown'
        lines.append(f"      handler: {handler_type}")

    return "\n".join(lines)


def tool_invoke(tool_id: str, **inputs) -> str:
    """Invoke a dynamic tool by ID."""
    repo = _get_repo()
    tool = repo.read(tool_id)

    if not tool:
        return f"Tool not found: {tool_id}"

    if tool.type != 'tool':
        return f"Entity is not a tool: {tool_id} (type: {tool.type})"

    handler = tool.data.get('handler', {})
    handler_type = handler.get('type', 'unknown') if isinstance(handler, dict) else 'unknown'

    if handler_type == 'reference':
        return _execute_reference_handler(handler, inputs)

    elif handler_type == 'compose':
        return _execute_compose_handler(handler, inputs)

    elif handler_type == 'llm':
        return _execute_llm_handler(handler, inputs, repo)

    else:
        return f"Unknown handler type: {handler_type}"


def _execute_reference_handler(handler: dict, inputs: dict) -> str:
    """Execute a reference handler (calls Python function)."""
    func_ref = handler.get('function')
    if not func_ref:
        return "Error: reference handler missing 'function' field"

    if func_ref == 'orient':
        return tool_orient()

    return f"Unknown function reference: {func_ref}"


def _execute_compose_handler(handler: dict, inputs: dict) -> str:
    """Execute a compose handler (renders template)."""
    template = handler.get('template')
    if not template:
        return "Error: compose handler missing 'template' field"

    result = template
    for key, value in inputs.items():
        result = result.replace(f"{{{{ {key} }}}}", str(value))

    return result


def _execute_llm_handler(handler: dict, inputs: dict, repo: EntityRepository) -> str:
    """Execute an LLM handler (renders prompt and calls LLM)."""
    prompt_template = handler.get('prompt_template')
    if not prompt_template:
        return "Error: llm handler missing 'prompt_template' field"

    ctx = get_workspace_context(repo)

    # Gather entity context for prompts that need it
    tools = repo.list(entity_type='tool', limit=20)
    tools_summary = [f"- {t.id}: {t.data.get('description', '')[:80]}" for t in tools]

    learnings = repo.list(entity_type='learning', limit=30)
    learnings_summary = [f"- {l.id}: {l.data.get('insight', '')[:80]}" for l in learnings]

    patterns = repo.list(entity_type='pattern', limit=20)
    patterns_summary = [f"- {p.id}: {p.data.get('context', '')[:80]}" for p in patterns]

    template_context = {
        'features': [f['id'] for f in ctx.get('active_features', [])],
        'inquiries': [i['id'] for i in ctx.get('active_inquiries', [])],
        'tasks': [t['id'] for t in ctx.get('active_tasks', [])],
        'season': ctx.get('season', 'unknown'),
        'tools': '\n'.join(tools_summary) if tools_summary else 'No tools defined yet',
        'learnings': '\n'.join(learnings_summary) if learnings_summary else 'No learnings captured yet',
        'patterns': '\n'.join(patterns_summary) if patterns_summary else 'No patterns defined yet',
        **inputs
    }

    prompt = prompt_template
    for key, value in template_context.items():
        prompt = prompt.replace(f"{{{{ {key} }}}}", str(value))

    # Call LLM
    return _call_llm(prompt, handler.get('model'), handler.get('system_prompt'))


def _call_llm(prompt: str, model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
    """Call the LLM with a prompt. Uses Anthropic API if available."""
    import os

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return f"[No ANTHROPIC_API_KEY set. Prompt:]\n\n{prompt}"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        messages = [{"role": "user", "content": prompt}]

        response = client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt or "You are a helpful assistant in the chora development system. Be concise and warm.",
            messages=messages
        )

        # Extract text from response
        if response.content and len(response.content) > 0:
            return response.content[0].text

        return "[Empty response from LLM]"

    except ImportError:
        return f"[anthropic not installed. Prompt:]\n\n{prompt}"
    except Exception as e:
        return f"[LLM error: {e}]\n\nPrompt was:\n{prompt}"


# ═══════════════════════════════════════════════════════════════════════════════
# MCP WRAPPERS (only registered if fastmcp is available)
# ═══════════════════════════════════════════════════════════════════════════════

if MCP_AVAILABLE and _mcp:
    @_mcp.tool()
    async def orient() -> str:
        """The greeting - system's first act of care toward the arriving agent."""
        return tool_orient()

    @_mcp.tool()
    async def list_entities(entity_type: Optional[str] = None, status: Optional[str] = None, limit: int = 20) -> str:
        """List entities in the store."""
        return tool_list_entities(entity_type, status, limit)

    @_mcp.tool()
    async def get_entity(entity_id: str) -> str:
        """Get a specific entity by ID."""
        return tool_get_entity(entity_id)

    @_mcp.tool()
    async def list_tools() -> str:
        """List all available dynamic tools."""
        return tool_list_tools()

    @_mcp.tool()
    async def invoke_tool(tool_id: str) -> str:
        """Invoke a dynamic tool by ID."""
        return tool_invoke(tool_id)


def main():
    """Run the MCP server."""
    if not MCP_AVAILABLE:
        print("fastmcp not installed. Install with: pip install fastmcp")
        print("Tools can still be used via tool_* functions.")
        return

    _mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
