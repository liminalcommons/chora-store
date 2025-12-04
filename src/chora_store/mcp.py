"""
MCP server for chora-store with dynamic tool discovery.

Tools are entities in SQLite. This server reads them and exposes them via MCP.
When a tool is invoked, it executes the appropriate handler:
  - reference: calls a Python function
  - compose: renders a template with context
  - llm: renders a prompt template and calls LLM
  - generative: renders prompt, calls LLM, parses output as entity, persists (L5)

The generative handler is Level 5 of the interpretation stack - it creates and
persists new entities from LLM output, enabling self-extending tools.

Optional dependency: fastmcp (pip install fastmcp)
If fastmcp is not available, the tools module still works but MCP server won't run.
"""

import json
from typing import Any, Optional, List

from .factory import EntityFactory
from .repository import EntityRepository
from .cli import get_workspace_context, get_constellation
from .metabolism import tool_induction, tool_auto_induction, tool_digest_batch, tool_propose_synthesis, tool_suggest_patterns, TraceCapture
from .traceability import GherkinScanner, BehaviorBridge, CodeScanner
from .traceability.scanner import tool_scan_features, tool_extract_behaviors
from .traceability.bridge import tool_coverage_report, tool_link_test_to_entity, tool_generate_behaviors, tool_link_all_tests
from .traceability.code_scanner import tool_scan_code, tool_find_dark_behaviors
from .traceability.pattern_auditor import tool_pattern_audit, tool_find_emergent_patterns, tool_audit_behavior
from .traceability.reifier import tool_reify_patterns, tool_align_behaviors, tool_pattern_coverage, tool_run_phase6
from .coherence import (
    tool_wobble_test, tool_dimension_checklist, tool_dimension_prompts,
    tool_pre_release_check, tool_generate_story, tool_story_status,
    tool_coherence_check
)

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


# =============================================================================
# UNIFIED CAPABILITY REGISTRY
# =============================================================================
# Makes ALL tools visible to agent awareness - both tool entities and MCP functions

# MCP functions that exist but aren't tool entities (infrastructure layer)
MCP_INFRASTRUCTURE_TOOLS = {
    'crystallize-routes': 'Auto-crystallize inference traces into routes (Push-Right)',
    'list-routes': 'List crystallized routes for a tool',
    'promote-route': 'Promote a route from canary to active status',
    'list-entities': 'List entities by type and status',
    'get-entity': 'Get a specific entity by ID',
    'create-entity': 'Create entity with discovery gate (Discover Before Create)',
    'update-entity': 'Update entity with lifecycle awareness',
    'list-tools': 'List all available tools',
    'invoke-tool': 'Invoke a dynamic tool by ID',
    'suggest-patterns': 'Suggest patterns for an entity type',
    'coherence-check': 'Check workspace or kernel coherence',
    'scan-features': 'Scan directory for Gherkin feature files',
    'extract-behaviors': 'Extract behaviors from a feature file',
    'coverage-report': 'Generate behavior coverage report',
    'link-test': 'Link a test file to an entity',
    'link-all-tests': 'Auto-link all tests to entities',
    'generate-behaviors-from-tests': 'Generate behaviors from test files',
    'scan-code': 'Scan code for entity references',
    'find-dark-behaviors': 'Find behaviors not linked to patterns',
    'pattern-audit': 'Audit pattern health and coverage',
    'emergent-patterns': 'Find emergent pattern candidates',
    'audit-behavior': 'Audit a specific behavior',
    'reify-patterns': 'Reify emergent patterns into entities',
    'align-behaviors': 'Align behaviors with patterns',
    'pattern-coverage': 'Check pattern coverage percentage',
    'tiered-synthesize': 'Synthesize using tiered resolution',
}


def get_all_capabilities(repo: Optional["EntityRepository"] = None) -> dict:
    """
    Get unified list of ALL capabilities - tool entities + MCP infrastructure.

    Returns dict with:
        - entities: List of tool entity summaries
        - infrastructure: List of MCP infrastructure tool summaries
        - combined: Single list for {{ tools }} context
    """
    if repo is None:
        repo = _get_repo()

    # Get tool entities
    tools = repo.list(entity_type='tool', limit=50)
    entity_summaries = [
        f"- {t.id}: {t.data.get('description', '')[:80]}"
        for t in tools
    ]

    # Get MCP infrastructure tools
    infra_summaries = [
        f"- [mcp] {name}: {desc}"
        for name, desc in sorted(MCP_INFRASTRUCTURE_TOOLS.items())
    ]

    return {
        'entities': entity_summaries,
        'infrastructure': infra_summaries,
        'combined': entity_summaries + ['', '## Infrastructure (MCP functions)'] + infra_summaries,
        'entity_count': len(tools),
        'infra_count': len(MCP_INFRASTRUCTURE_TOOLS),
    }


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


# =============================================================================
# DYNAMIC TOOL REGISTRATION
# =============================================================================
# Auto-registers tool entities as MCP functions for native protocol access

def _create_tool_wrapper(tool_id: str):
    """Create an async wrapper function for a tool entity."""
    async def wrapper(**kwargs) -> str:
        return tool_invoke(tool_id, **kwargs)

    # Set proper function metadata
    wrapper.__name__ = tool_id.replace('-', '_').replace('tool_', '')
    return wrapper


def register_tool_entities_as_mcp():
    """
    Register tool entities as MCP functions based on interfaces field.

    Only tools with 'mcp' in their interfaces field are registered.
    This implements physics-aligned exposure: interfaces governs where tools appear.

    This bridges the gap between tool entities (dynamic, in SQLite) and
    MCP functions (available via native protocol). Call this on module load
    or when tools are created/updated.
    """
    if not MCP_AVAILABLE or _mcp is None:
        return

    try:
        repo = _get_repo()
        tools = repo.list(entity_type='tool', status='active', limit=200)

        registered = 0
        skipped = 0
        for tool in tools:
            try:
                # Physics: interfaces field governs exposure
                interfaces = tool.data.get('interfaces', [])
                if 'mcp' not in interfaces:
                    skipped += 1
                    continue

                tool_id = tool.id
                description = tool.data.get('description', f'Tool entity: {tool_id}')

                # Create wrapper and register
                wrapper = _create_tool_wrapper(tool_id)
                _mcp.add_tool(wrapper, name=tool_id, description=description[:200])
                registered += 1
            except Exception:
                pass  # Skip tools that fail to register

        return registered
    except Exception:
        return 0


def register_single_tool(tool_id: str, description: str = None):
    """
    Register a single tool entity as MCP function.

    Only registers if 'mcp' is in the tool's interfaces field.
    Call this when a new tool entity is created for hot-reload.
    """
    if not MCP_AVAILABLE or _mcp is None:
        return False

    try:
        repo = _get_repo()
        tool = repo.read(tool_id)
        if not tool:
            return False

        # Physics: interfaces field governs exposure
        interfaces = tool.data.get('interfaces', [])
        if 'mcp' not in interfaces:
            return False  # Not exposed via MCP

        if description is None:
            description = tool.data.get('description', f'Tool entity: {tool_id}')

        wrapper = _create_tool_wrapper(tool_id)
        _mcp.add_tool(wrapper, name=tool_id, description=description[:200])
        return True
    except Exception:
        return False


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

    # Contextual tools (phenomenological awareness)
    contextual_tools = phase.get('tools', [])
    if contextual_tools:
        lines.append("")
        lines.append("Tools at hand:")
        for tool in contextual_tools:
            name = tool.get('name', tool.get('id', 'unknown'))
            ready = tool.get('ready_at_hand', '')
            cmd = tool.get('command', '')
            lines.append(f"  🔧 {name}")
            if ready:
                # Clean up multiline ready_at_hand text
                ready_clean = ' '.join(ready.split())[:70]
                lines.append(f"     {ready_clean}...")
            if cmd:
                lines.append(f"     → {cmd}")

    return "\n".join(lines)


def tool_constellation(focus_id: str) -> str:
    """The site survey - Phase 2: Relevance Realization.

    Shows the constellation of entities around a focus entity:
    - Upstream: what led to this (origin, links)
    - Downstream: what came from this (features, learnings)
    - Siblings: related by domain
    - Aliveness: for focus entities, shows felt quality, care, trail, handoff

    Returns map not territory - IDs and summaries, not full content.
    """
    repo = _get_repo()
    c = get_constellation(focus_id, repo)

    if 'error' in c:
        return c['error']

    focus = c['focus']
    lines = [f"Constellation for {focus['id']} ({focus['status']}):"]
    if focus.get('name'):
        lines.append(f"  \"{focus['name']}\"")

    # For focus entities, show aliveness fields (the warmth of the work)
    if focus['type'] == 'focus':
        entity = repo.read(focus_id)
        if entity and entity.data:
            data = entity.data
            has_aliveness = any([
                data.get('felt_quality'),
                data.get('care_at_center'),
                data.get('trail'),
                data.get('handoff_note')
            ])
            if has_aliveness:
                lines.append("")
                lines.append("ALIVENESS:")
                if data.get('felt_quality'):
                    lines.append(f"  ✨ Felt: {data['felt_quality']}")
                if data.get('care_at_center'):
                    lines.append(f"  ♡ Care: {data['care_at_center']}")
                trail = data.get('trail', [])
                if trail:
                    lines.append("")
                    lines.append("TRAIL:")
                    for t in trail[-5:]:  # Last 5 trail entries
                        action = t.get('action', str(t)) if isinstance(t, dict) else str(t)
                        lines.append(f"  • {action[:80]}")
                if data.get('handoff_note'):
                    lines.append("")
                    lines.append("HANDOFF NOTE:")
                    for line in data['handoff_note'].strip().split('\n'):
                        lines.append(f"  {line}")

    if c['upstream']:
        lines.append("")
        lines.append("UPSTREAM (Led to this):")
        for item in c['upstream']:
            relation = item.get('relation', '')
            if relation == 'canonical':
                lines.append(f"  ⬆ {item['type']} | {item['name'][:40] or item['id']} [CANONICAL]")
            else:
                lines.append(f"  ↑ {item['type']} | {item['name'][:40] or item['id']}")
            lines.append(f"    {item['id']}")

    if c['downstream']:
        lines.append("")
        lines.append("DOWNSTREAM (Came from this):")
        for item in c['downstream']:
            relation = item.get('relation', '')
            if relation == 'subsumed':
                lines.append(f"  ⬇ {item['type']} | {item['name'][:40] or item['id']} [SUBSUMED]")
            else:
                lines.append(f"  ↓ {item['type']} | {item['name'][:40] or item['id']}")
            lines.append(f"    {item['id']}")

    if c['siblings']:
        lines.append("")
        lines.append("SIBLINGS (Same domain):")
        for item in c['siblings']:
            lines.append(f"  = {item['type']} | {item['name'][:40] or item['id']}")
            lines.append(f"    {item['id']}")

    # Check if entity has connections
    has_connections = c['upstream'] or c['downstream'] or c['siblings']

    if not has_connections:
        # For focus entities with aliveness, don't say "isolated" - they have warmth
        is_warm_focus = (
            focus['type'] == 'focus' and
            repo.read(focus_id) and
            any([
                repo.read(focus_id).data.get('felt_quality'),
                repo.read(focus_id).data.get('care_at_center'),
                repo.read(focus_id).data.get('handoff_note')
            ])
        )
        if not is_warm_focus:
            lines.append("")
            lines.append("(No connections found. This entity is isolated.)")

    return "\n".join(lines)


def tool_pattern_evaluate(pattern_id: Optional[str] = None) -> str:
    """The fitness engine - evaluate experimental patterns.

    If pattern_id is provided, evaluates that specific pattern.
    Otherwise, evaluates all experimental patterns.
    """
    repo = _get_repo()

    try:
        from .evaluator import PatternEvaluator
        evaluator = PatternEvaluator(repo)

        if pattern_id:
            pattern = repo.read(pattern_id)
            if not pattern:
                return f"Pattern not found: {pattern_id}"
            report = evaluator.evaluate_pattern(pattern)
            lines = [
                f"Evaluation for {pattern_id}:",
                f"  Recommendation: {report.recommendation.upper()}",
                f"  Sample size: {report.sample_size_actual}/{report.sample_size_required}",
                "  Metrics:"
            ]
            for m in report.metrics:
                lines.append(f"    {m.name}: {m.current_value}")
            return "\n".join(lines)
        else:
            summary = evaluator.get_summary()
            lines = [
                "Fitness Engine Summary:",
                f"  Total patterns: {summary['total_patterns']}",
                ""
            ]
            for p in summary.get('patterns', []):
                lines.append(f"  {p['id']}: {p['recommendation']} ({p['sample_size']} samples)")
            return "\n".join(lines) if summary['total_patterns'] > 0 else "No experimental patterns to evaluate."

    except ImportError:
        return "PatternEvaluator not available"
    except Exception as e:
        return f"Error evaluating patterns: {e}"


def tool_pathway_catalog() -> str:
    """The mutation map - see all active epigenetic pathways.

    Shows the autoevolutionary loop's current state:
    - What triggers are active (EXPRESS phase)
    - What patterns are under evaluation (SELECT phase)
    - What has been promoted/deprecated (INHERIT phase)

    This is visibility into the system's self-modification layer.
    """
    repo = _get_repo()
    from .observer import get_observer

    observer = get_observer()
    patterns = repo.list(entity_type='pattern', limit=100)

    # Filter to schema-extension patterns (ones with hooks/mechanics)
    epigenetic_patterns = []
    for p in patterns:
        if p.data.get('subtype') == 'schema-extension':
            epigenetic_patterns.append(p)
        else:
            mechanics = p.data.get('mechanics', {})
            # mechanics can be dict or list - handle both
            if isinstance(mechanics, dict) and mechanics.get('hooks'):
                epigenetic_patterns.append(p)

    if not epigenetic_patterns:
        return "No epigenetic patterns found. The mutation layer is empty."

    lines = [
        "╭──────────────────────────────────────────────────────────╮",
        "│  PATHWAY CATALOG · Autoevolutionary Loop                 │",
        "╰──────────────────────────────────────────────────────────╯",
        ""
    ]

    # Group by phase
    expressing = []  # experimental status with hooks
    selecting = []   # experimental with observation data
    inherited = []   # adopted status

    for p in epigenetic_patterns:
        mechanics = p.data.get('mechanics', {})
        hooks = mechanics.get('hooks', []) if isinstance(mechanics, dict) else []
        if p.status == 'adopted':
            inherited.append((p, hooks))
        elif p.status == 'experimental':
            # Check if it has observation data (in SELECT phase)
            fitness = p.data.get('fitness', {})
            if fitness.get('observations', 0) > 0:
                selecting.append((p, hooks, fitness))
            else:
                expressing.append((p, hooks))
        elif p.status == 'proposed':
            # Proposed patterns are waiting to become experimental
            expressing.append((p, hooks))

    # EXPRESS Phase
    if expressing:
        lines.append("┌─ EXPRESS (Active Mutations) ─────────────────────────────┐")
        for p, hooks in expressing:
            mechanics = p.data.get('mechanics', {})
            target = mechanics.get('target_type', 'any') if isinstance(mechanics, dict) else 'any'
            inject_fields = mechanics.get('inject_fields', []) if isinstance(mechanics, dict) else []
            lines.append(f"│  🧬 {p.id}")
            lines.append(f"│     Target: {target}")
            if inject_fields:
                lines.append(f"│     Injects: {', '.join(inject_fields)}")
            for hook in hooks:
                trigger = hook.get('trigger', '?')
                condition = hook.get('condition', 'true')[:50]
                action = hook.get('action', '?')[:40]
                lines.append(f"│     📌 {trigger} → {action}")
        lines.append("└──────────────────────────────────────────────────────────┘")
        lines.append("")

    # SELECT Phase
    if selecting:
        lines.append("┌─ SELECT (Under Evaluation) ──────────────────────────────┐")
        for p, hooks, fitness in selecting:
            obs_count = fitness.get('observations', 0)
            obs_period = fitness.get('observation_period', 30)
            days_remaining = obs_period - obs_count
            recommendation = fitness.get('last_recommendation', 'continue')
            lines.append(f"│  🔬 {p.id}")
            lines.append(f"│     Observations: {obs_count}/{obs_period} ({days_remaining} days remaining)")
            lines.append(f"│     Recommendation: {recommendation.upper()}")
        lines.append("└──────────────────────────────────────────────────────────┘")
        lines.append("")

    # INHERIT Phase
    if inherited:
        lines.append("┌─ INHERIT (Adopted Mutations) ────────────────────────────┐")
        for p, hooks in inherited:
            mechanics = p.data.get('mechanics', {})
            target = mechanics.get('target_type', 'any') if isinstance(mechanics, dict) else 'any'
            lines.append(f"│  ✓ {p.id}")
            lines.append(f"│     Target: {target}")
        lines.append("└──────────────────────────────────────────────────────────┘")
        lines.append("")

    # Summary
    lines.append("─────────────────────────────────────────────────────────────")
    lines.append(f"Loop Health: {len(expressing)} expressing, {len(selecting)} selecting, {len(inherited)} inherited")
    lines.append("Commands: just pathway_catalog · just pattern_evaluate")

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


# Tier mapping for trace capture - enables Push-Right crystallization
# LLM/generative handlers produce inference-tier traces that can crystallize into routes
# Reference/compose handlers are already at workflow tier (no crystallization potential)
HANDLER_TYPE_TO_TIER = {
    'llm': 'inference',
    'generative': 'inference',
    'agent': 'agent',
    'reference': 'workflow',
    'compose': 'workflow',
}


def tool_invoke(tool_id: str, **inputs) -> str:
    """Invoke a dynamic tool by ID with trace capture for crystallization."""
    repo = _get_repo()
    tool = repo.read(tool_id)

    if not tool:
        return f"Tool not found: {tool_id}"

    if tool.type != 'tool':
        return f"Entity is not a tool: {tool_id} (type: {tool.type})"

    handler = tool.data.get('handler', {})
    handler_type = handler.get('type', 'unknown') if isinstance(handler, dict) else 'unknown'

    # Generate input signature for trace/route lookup
    import hashlib
    input_signature = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]

    # Wrap invocation with trace capture for route crystallization
    # Tier derived from handler type enables Push-Right crystallization
    tier = HANDLER_TYPE_TO_TIER.get(handler_type, 'workflow')
    with TraceCapture(
        repository=repo,
        operation_type="tool_invoke",
        tier=tier,
        capability_id=tool_id,
    ) as trace:
        trace.set_inputs([f"input:{input_signature}"])

        if handler_type == 'reference':
            result = _execute_reference_handler(handler, inputs)
        elif handler_type == 'compose':
            result = _execute_compose_handler(handler, inputs)
        elif handler_type == 'llm':
            result = _execute_llm_handler(handler, inputs, repo)
        elif handler_type == 'generative':
            result = _execute_generative_handler(handler, inputs, repo)
        else:
            result = f"Unknown handler type: {handler_type}"

        # Capture output signature for crystallization matching
        output_signature = hashlib.sha256(result.encode()).hexdigest()[:16]
        trace.set_outputs([f"output:{output_signature}"])
        trace.step(f"Invoked {tool_id} with handler type {handler_type}")

    return result


# Known namespaces for tool ID normalization
KNOWN_NAMESPACES = {'core', 'learning', 'pattern', 'transform', 'release',
                    'feature', 'focus', 'inquiry', 'meta', 'governance', 'trace'}

# Parameter synonyms for flexibility at interface boundaries
PARAM_SYNONYMS = {
    'entity_id': ['focus_id', 'id'],
    'focus_id': ['entity_id', 'id'],
}


def _normalize_func_ref(func_ref: str) -> str:
    """
    Normalize function reference to canonical action name.

    Handles:
    - tool_orient → orient
    - tool-core-orient → orient
    - tool-learning-distill → distill
    - orient → orient
    """
    # Strip tool_ prefix
    if func_ref.startswith('tool_'):
        func_ref = func_ref[5:]
    # Strip tool- prefix
    if func_ref.startswith('tool-'):
        func_ref = func_ref[5:]

    # Strip namespace prefix if present (e.g., core-orient → orient)
    parts = func_ref.split('-', 1)
    if len(parts) >= 2 and parts[0] in KNOWN_NAMESPACES:
        func_ref = parts[1]

    # Convert hyphens to underscores for Python function names
    return func_ref.replace('-', '_')


def _dispatch_with_inputs(func, inputs: dict) -> str:
    """
    Dispatch to function with automatic parameter mapping.

    Uses function signature introspection to map inputs to parameters.
    Handles parameter synonyms for flexibility.
    """
    import inspect

    sig = inspect.signature(func)
    call_args = {}

    for param_name, param in sig.parameters.items():
        # Try exact match first
        value = inputs.get(param_name)

        # Try synonyms if not found
        if value is None and param_name in PARAM_SYNONYMS:
            for synonym in PARAM_SYNONYMS[param_name]:
                value = inputs.get(synonym)
                if value is not None:
                    break

        # Use default if available, otherwise use None or empty
        if value is not None:
            call_args[param_name] = value
        elif param.default is not inspect.Parameter.empty:
            pass  # Will use function's default
        else:
            # Required param without value - use empty/None based on type hints
            call_args[param_name] = ''

    return func(**call_args)


# Reference handlers are defined lazily because some functions are defined later in file
# This dict maps normalized action names to their Python function names (as strings)
_REFERENCE_HANDLER_NAMES = {
    # Core operations
    'orient': 'tool_orient',
    'constellation': 'tool_constellation',
    'list_entities': 'tool_list_entities',
    'get_entity': 'tool_get_entity',
    'create_entity': 'tool_create_entity',
    'update_entity': 'tool_update_entity',
    'list_tools': 'tool_list_tools',

    # Pattern operations
    'pattern_evaluate': 'tool_pattern_evaluate',
    'suggest_patterns': 'tool_suggest_patterns',

    # Learning operations
    'synthesize_learnings': 'tool_synthesize_learnings',
    'distill_learnings': 'tool_distill_learnings',
    'propose_synthesis': 'tool_propose_synthesis',
    'digest_batch': 'tool_digest_batch',

    # Meta operations
    'pathway_catalog': 'tool_pathway_catalog',
    'induction': 'tool_induction',
    'auto_induction': 'tool_auto_induction',

    # Distillation operations (by type)
    'distill_inquiries': 'tool_distill_inquiries',
    'distill_features': 'tool_distill_features',
    'distill_patterns': 'tool_distill_patterns',

    # Transform operations
    'bulk_distill_by_domain': 'tool_bulk_distill_by_domain',
    'apply_distillation': 'tool_apply_distillation',
    'unsubsume': 'tool_unsubsume',
    'unsubsume_all': 'tool_unsubsume_all',

    # Aliases for namespaced names (action part only)
    'list': 'tool_list_entities',
    'get': 'tool_get_entity',
    'create': 'tool_create_entity',
    'update': 'tool_update_entity',
    'distill': 'tool_distill_learnings',  # Default distill to learnings
    'evaluate': 'tool_pattern_evaluate',
    'suggest': 'tool_suggest_patterns',
    'synthesize': 'tool_synthesize_learnings',
}


def _get_reference_handler(action: str):
    """Get reference handler function by action name (lazy lookup)."""
    func_name = _REFERENCE_HANDLER_NAMES.get(action)
    if func_name:
        # Look up in module globals
        return globals().get(func_name)
    return None


def _execute_reference_handler(handler: dict, inputs: dict) -> str:
    """
    Execute a reference handler (calls Python function).

    Table-driven dispatch with automatic parameter mapping.
    Supports namespaced tool IDs (e.g., tool-core-orient → orient).
    """
    func_ref = handler.get('function')
    if not func_ref:
        return "Error: reference handler missing 'function' field"

    # Normalize: tool-core-orient → orient, tool_orient → orient
    normalized_ref = _normalize_func_ref(func_ref)

    # Look up handler in dispatch table (lazy lookup)
    handler_func = _get_reference_handler(normalized_ref)
    if not handler_func:
        return f"Unknown function reference: {func_ref} (normalized: {normalized_ref})"

    # Special case for update_entity - needs to pass remaining inputs as kwargs
    if normalized_ref == 'update_entity':
        entity_id = inputs.get('entity_id', '')
        status = inputs.get('status')
        field_updates = {k: v for k, v in inputs.items()
                        if k not in ('entity_id', 'status')}
        return handler_func(entity_id, status, **field_updates)

    # Use automatic dispatch for all other handlers
    return _dispatch_with_inputs(handler_func, inputs)


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
    # Use unified capability registry for {{ tools }} - includes both entities AND MCP functions
    capabilities = get_all_capabilities(repo)

    learnings = repo.list(entity_type='learning', limit=30)
    learnings_summary = [f"- {l.id}: {l.data.get('insight', '')[:80]}" for l in learnings]

    patterns = repo.list(entity_type='pattern', limit=20)
    patterns_summary = [f"- {p.id}: {p.data.get('context', '')[:80]}" for p in patterns]

    template_context = {
        'features': [f['id'] for f in ctx.get('active_features', [])],
        'inquiries': [i['id'] for i in ctx.get('active_inquiries', [])],
        'tasks': [t['id'] for t in ctx.get('active_tasks', [])],
        'season': ctx.get('season', 'unknown'),
        'tools': '\n'.join(capabilities['combined']) if capabilities['combined'] else 'No tools defined yet',
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


def _execute_generative_handler(handler: dict, inputs: dict, repo: EntityRepository) -> str:
    """
    Execute a generative handler (L5: creates and persists new entities).

    Like LLM handler, but parses output as entity YAML and persists it.
    If approval_required=true, returns the spec for review instead of persisting.
    """
    import yaml

    prompt_template = handler.get('prompt_template')
    if not prompt_template:
        return "Error: generative handler missing 'prompt_template' field"

    # Build context (same as llm handler)
    ctx = get_workspace_context(repo)

    # Use unified capability registry for {{ tools }}
    capabilities = get_all_capabilities(repo)

    learnings = repo.list(entity_type='learning', limit=30)
    learnings_summary = [f"- {l.id}: {l.data.get('insight', '')[:80]}" for l in learnings]

    patterns = repo.list(entity_type='pattern', limit=20)
    patterns_summary = [f"- {p.id}: {p.data.get('context', '')[:80]}" for p in patterns]

    template_context = {
        'features': [f['id'] for f in ctx.get('active_features', [])],
        'inquiries': [i['id'] for i in ctx.get('active_inquiries', [])],
        'tasks': [t['id'] for t in ctx.get('active_tasks', [])],
        'season': ctx.get('season', 'unknown'),
        'tools': '\n'.join(capabilities['combined']) if capabilities['combined'] else 'No tools defined yet',
        'learnings': '\n'.join(learnings_summary) if learnings_summary else 'No learnings captured yet',
        'patterns': '\n'.join(patterns_summary) if patterns_summary else 'No patterns defined yet',
        **inputs
    }

    prompt = prompt_template
    for key, value in template_context.items():
        prompt = prompt.replace(f"{{{{ {key} }}}}", str(value))

    # Call LLM to generate entity spec
    llm_output = _call_llm(prompt, handler.get('model'), handler.get('system_prompt'))

    # Check for LLM errors
    if llm_output.startswith('[') and ('error' in llm_output.lower() or 'not installed' in llm_output.lower()):
        return llm_output

    # Extract YAML from output (may be wrapped in ```yaml ... ```)
    yaml_content = llm_output
    if '```yaml' in yaml_content:
        start = yaml_content.find('```yaml') + 7
        end = yaml_content.find('```', start)
        if end > start:
            yaml_content = yaml_content[start:end].strip()
    elif '```' in yaml_content:
        start = yaml_content.find('```') + 3
        end = yaml_content.find('```', start)
        if end > start:
            yaml_content = yaml_content[start:end].strip()

    # Parse YAML
    try:
        entity_spec = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return f"Error parsing generated YAML: {e}\n\nGenerated content:\n{yaml_content}"

    if not isinstance(entity_spec, dict):
        return f"Error: Generated content is not a valid entity spec (got {type(entity_spec).__name__})"

    # Check if approval required
    approval_required = handler.get('approval_required', False)
    if approval_required:
        return f"[APPROVAL REQUIRED]\n\nGenerated entity spec:\n```yaml\n{yaml_content}\n```\n\nTo persist, invoke with approval_required=false or use Factory directly."

    # Extract entity type and create via Factory
    entity_type = entity_spec.get('type')
    if not entity_type:
        return f"Error: Generated spec missing 'type' field\n\nSpec:\n{yaml_content}"

    entity_name = entity_spec.get('name', entity_spec.get('id', 'unnamed'))

    # Remove fields that Factory will generate
    create_kwargs = {k: v for k, v in entity_spec.items()
                     if k not in ['id', 'type', 'created', 'updated']}

    try:
        factory = EntityFactory()
        new_entity = factory.create(entity_type, entity_name, **create_kwargs)
        repo.create(new_entity)

        return f"✓ Generated and persisted: {new_entity.id}\n  Type: {new_entity.type}\n  Status: {new_entity.status}"

    except Exception as e:
        return f"Error creating entity: {e}\n\nSpec was:\n{yaml_content}"


# ═══════════════════════════════════════════════════════════════════════════════
# TIERED RESOLUTION TOOLS
# ═══════════════════════════════════════════════════════════════════════════════


def tool_tiered_synthesize(
    learning_ids: List[str],
    max_tier: str = "inference",
    confidence_threshold: float = 0.7,
) -> str:
    """
    Run tiered synthesis on a list of learnings.

    Tries cheaper tiers first and escalates when needed.
    """
    repo = _get_repo()
    from .metabolism import MetabolicEngine

    engine = MetabolicEngine(repo)
    result = engine.tiered_synthesize(
        learning_ids=learning_ids,
        max_tier=max_tier,
        confidence_threshold=confidence_threshold,
    )

    lines = ["TIERED SYNTHESIS RESULT"]
    lines.append("=" * 50)
    lines.append(f"Success: {result['success']}")
    lines.append(f"Tier used: {result['tier_used'] or 'none'}")

    if result.get("escalation_reason"):
        lines.append(f"Escalation reason: {result['escalation_reason']}")

    if result["success"] and result.get("result"):
        proposal = result["result"]
        lines.append("")
        lines.append("PATTERN PROPOSAL")
        lines.append(f"  Name: {proposal.name}")
        lines.append(f"  Domain: {proposal.domain}")
        lines.append(f"  Confidence: {proposal.confidence:.2f}")
        lines.append(f"  Source learnings: {len(proposal.learning_ids)}")

    if result.get("traces"):
        lines.append("")
        lines.append(f"Traces captured: {len(result['traces'])}")

    return "\n".join(lines)


def tool_list_routes(
    tool_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List crystallized routes for tiered resolution."""
    repo = _get_repo()
    from .metabolism import RouteTable

    route_table = RouteTable(repo)
    routes = route_table.list_routes(tool_id=tool_id, status=status, limit=limit)

    if not routes:
        return "No routes found."

    lines = [f"ROUTES ({len(routes)} found)"]
    lines.append("=" * 50)

    for r in routes:
        hit_rate = r.hit_count / (r.hit_count + r.miss_count) * 100 if (r.hit_count + r.miss_count) > 0 else 0
        lines.append(f"\n{r.id} [{r.status}]")
        lines.append(f"  Tool: {r.tool_id}")
        lines.append(f"  Hits: {r.hit_count}, Misses: {r.miss_count} ({hit_rate:.1f}% hit rate)")
        lines.append(f"  Confidence: {r.confidence:.2f}")
        lines.append(f"  Created: {r.created_at}")
        if r.last_hit_at:
            lines.append(f"  Last hit: {r.last_hit_at}")

    return "\n".join(lines)


def tool_crystallize_routes(
    tool_id: Optional[str] = None,
    min_traces: int = 5,
    consistency_threshold: float = 0.95,
) -> str:
    """
    Auto-crystallize routes from trace patterns (Push-Right).

    Finds repeated input patterns with consistent outputs and creates routes.
    """
    repo = _get_repo()
    from .metabolism import RouteTable

    route_table = RouteTable(repo)
    new_routes = route_table.auto_crystallize(
        tool_id=tool_id,
        min_traces=min_traces,
        consistency_threshold=consistency_threshold,
    )

    if not new_routes:
        # Check for candidates
        candidates = route_table.find_crystallization_candidates(
            tool_id=tool_id,
            min_traces=min_traces,
            consistency_threshold=consistency_threshold,
        )
        if candidates:
            return f"No new routes created. {len(candidates)} candidates found but may already be crystallized."
        return "No crystallization candidates found. Need more traces with consistent outputs."

    lines = [f"CRYSTALLIZED {len(new_routes)} NEW ROUTES"]
    lines.append("=" * 50)

    for r in new_routes:
        lines.append(f"\n{r.id} [canary]")
        lines.append(f"  Tool: {r.tool_id}")
        lines.append(f"  Confidence: {r.confidence:.2f}")
        lines.append(f"  Source traces: {len(r.source_traces)}")

    return "\n".join(lines)


def tool_promote_route(route_id: str) -> str:
    """Promote a route from canary to active status."""
    repo = _get_repo()
    from .metabolism import RouteTable

    route_table = RouteTable(repo)

    # Check current status
    route = None
    for r in route_table.list_routes(status="canary"):
        if r.id == route_id:
            route = r
            break

    if not route:
        # Check if already active
        for r in route_table.list_routes(status="active"):
            if r.id == route_id:
                return f"Route {route_id} is already active."
        return f"Route {route_id} not found in canary status."

    if route_table.promote(route_id):
        return f"Promoted route {route_id} from canary to active. Hit count: {route.hit_count}"
    return f"Failed to promote route {route_id}."


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFORMATION VERBS (The 7 Verbs as Invokable Tools)
# ═══════════════════════════════════════════════════════════════════════════════


def tool_crystallize(inquiry_id: str) -> str:
    """
    Transform an inquiry into a feature (crystallization).

    This is the Inquiry → Feature transformation:
    - Creates feature entity with origin = inquiry_id
    - Sets inquiry status to 'reified'
    - Carries forward any learnings linked to the inquiry
    """
    repo = _get_repo()
    factory = _get_factory()

    # Validate inquiry exists
    inquiry = repo.read(inquiry_id)
    if not inquiry:
        return f"Error: {inquiry_id} not found"
    if inquiry.type != "inquiry":
        return f"Error: {inquiry_id} is not an inquiry (type: {inquiry.type})"
    if inquiry.status == "reified":
        return f"Error: {inquiry_id} is already reified"

    # Generate feature slug from inquiry
    feature_slug = inquiry_id.replace("inquiry-", "")
    feature_id = f"feature-{feature_slug}"

    # Check if feature already exists
    existing = repo.read(feature_id)
    if existing:
        return f"Error: {feature_id} already exists"

    # Create feature
    inquiry_name = inquiry.data.get("name", feature_slug)
    feature = factory.create(
        "feature",
        inquiry_name,
        origin=inquiry_id,
        learnings=inquiry.data.get("learnings", []),
    )

    # Update inquiry status to reified
    updated_inquiry = inquiry.copy(status="reified")
    repo.update(updated_inquiry)

    return f"Crystallized: {inquiry_id} → {feature.id}"


def tool_engage(feature_id: str, agent: str = "claude") -> str:
    """
    Create a focus on a feature (engagement).

    This is the Feature → Focus transformation:
    - Creates focus entity targeting the feature
    - Sets focus.agent and focus.entry_type
    - Signals the agent is actively working on this feature
    """
    repo = _get_repo()
    factory = _get_factory()

    # Validate feature exists
    feature = repo.read(feature_id)
    if not feature:
        return f"Error: {feature_id} not found"
    if feature.type != "feature":
        return f"Error: {feature_id} is not a feature (type: {feature.type})"

    # Check for existing open focus on this feature
    all_foci = repo.list(entity_type="focus", status="open")
    for f in all_foci:
        if f.data.get("target") == feature_id:
            return f"Already engaged: {f.id} is open on {feature_id}"

    # Create focus
    feature_name = feature.data.get("name", feature_id)
    focus = factory.create(
        "focus",
        f"{agent} on {feature_name}",
        target=feature_id,
        agent=agent,
        entry_type="declared",
    )

    return f"Engaged: {focus.id} → {feature_id}"


def tool_finalize(
    entity_id: str,
    reason: str = "",
    felt_quality: str = "",
    care_at_center: str = "",
    handoff_note: str = ""
) -> str:
    """
    Finalize an entity (lifecycle termination with learning extraction).

    This is the Finalize verb - biological digestion, not surgical deletion:
    - Extracts learnings from the entity
    - Archives the entity blueprint
    - Sets status to 'finalizing'

    For focus entities, you can also provide aliveness fields:
    - felt_quality: How the work felt (e.g., "flowing", "stuck", "curious")
    - care_at_center: What was being cared for
    - handoff_note: A gift for whoever comes next
    """
    repo = _get_repo()
    factory = _get_factory()

    # Validate entity exists
    entity = repo.read(entity_id)
    if not entity:
        return f"Error: {entity_id} not found"

    # Check if already finalizing/finalized
    if entity.status in ("finalizing", "finalized"):
        return f"Error: {entity_id} is already {entity.status}"

    learning_id = None

    # For focus entities, use FocusManager with aliveness fields
    if entity.type == "focus":
        from chora_store.focus import FocusManager
        fm = FocusManager(repo)

        # Update aliveness fields before finalizing
        if felt_quality or care_at_center or handoff_note:
            if felt_quality:
                entity.data['felt_quality'] = felt_quality
            if care_at_center:
                entity.data['care_at_center'] = care_at_center
            if handoff_note:
                entity.data['handoff_note'] = handoff_note
            repo.update(entity)

        # Finalize via FocusManager
        result_data = fm.finalize_focus(entity_id)
        result = f"Finalized: {entity_id}"
        if result_data.get('trail_count'):
            result += f" (trail: {result_data['trail_count']} entries)"
        if handoff_note:
            result += " with handoff note"
        return result

    # Extract learning about why this was finalized (if reason provided)
    if reason:
        try:
            learning = factory.create(
                "learning",
                f"Finalization of {entity_id}",
                insight=reason,
                domain="lifecycle",
                links=[entity_id],
            )
            learning_id = learning.id
        except Exception as e:
            # Non-fatal: continue with finalization even if learning fails
            pass

    # Update status to finalizing
    updated = entity.copy(status="finalizing")
    repo.update(updated)

    result = f"Finalized: {entity_id}"
    if learning_id:
        result += f" with learning {learning_id}"

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY CRUD TOOLS (Discovery-Gated)
# ═══════════════════════════════════════════════════════════════════════════════


def tool_create_entity(
    entity_type: str,
    title: str,
    context: str = "",
    skip_discovery: bool = False,
    **kwargs
) -> str:
    """
    Create an entity with discovery gate cognition.

    Implements "Discover Before Create" principle:
    1. DISCOVER: Search for existing entities/patterns that might serve the need
    2. CONFIRM: Surface discoveries so agent can decide to proceed or reuse
    3. CREATE: Instantiate via factory if proceeding
    4. REPORT: Return created entity with suggestions for next steps

    Args:
        entity_type: One of the 7 Nouns (inquiry, feature, focus, learning, pattern, release, tool)
        title: Human-readable title (will be slugified for ID)
        context: Optional context about what you're trying to accomplish
        skip_discovery: Set true to bypass discovery (use sparingly)
        **kwargs: Type-specific fields passed to factory

    Returns:
        Discovery results if similar entities exist (agent should confirm)
        Created entity ID if no conflicts or skip_discovery=True
    """
    repo = _get_repo()
    factory = _get_factory()

    # === 1. DISCOVER ===
    discoveries = []

    if not skip_discovery:
        # Generate potential ID from title
        slug = title.lower().replace(' ', '-').replace('_', '-')
        # Remove special chars
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')
        potential_id = f"{entity_type}-{slug}"

        # Check for exact ID collision
        existing = repo.read(potential_id)
        if existing:
            return f"DISCOVERY: Entity {potential_id} already exists (status: {existing.status}). Use skip_discovery=True to create anyway, or reuse existing."

        # Search for similar entities
        try:
            search_results = repo.search(title, limit=10)
            similar = [e for e in search_results if e.type == entity_type]
            if similar:
                discoveries.append({
                    'type': 'similar_entities',
                    'items': [{'id': e.id, 'status': e.status} for e in similar[:3]]
                })
        except Exception:
            # Search might fail if FTS not set up - continue without
            pass

        # Suggest applicable patterns (only for types that benefit from patterns)
        if entity_type in ['feature', 'pattern', 'tool']:
            try:
                patterns_result = tool_suggest_patterns(entity_type, context or title)
                if patterns_result and 'No patterns' not in patterns_result:
                    discoveries.append({
                        'type': 'applicable_patterns',
                        'raw': patterns_result
                    })
            except Exception:
                # Pattern suggestion might fail - continue without
                pass

    # === 2. CONFIRM (if discoveries) ===
    if discoveries and not skip_discovery:
        result = f"DISCOVERY GATE for {entity_type} '{title}':\n\n"
        for d in discoveries:
            if d['type'] == 'similar_entities':
                result += "Similar entities exist:\n"
                for item in d['items']:
                    result += f"  - {item['id']} ({item['status']})\n"
                result += "\n"
            elif d['type'] == 'applicable_patterns':
                result += "Applicable patterns:\n"
                result += d['raw'] + "\n\n"

        result += "To proceed with creation, call again with skip_discovery=True.\n"
        result += "To reuse existing, use tool-core-get or tool-core-update."
        return result

    # === 3. CREATE ===
    try:
        entity = factory.create(entity_type, title, **kwargs)
    except Exception as e:
        return f"Error creating {entity_type}: {e}"

    # === 4. REPORT ===
    report = f"Created: {entity.id} (status: {entity.status})"

    # Suggest next steps based on type
    next_steps = {
        'inquiry': "Next: Explore the inquiry, capture learnings, then crystallize when ready.",
        'feature': "Next: Define behaviors, then engage to start focused work.",
        'learning': "Next: Link to source entity, consider if ready for pattern synthesis.",
        'pattern': "Next: Define mechanics, link to governing feature.",
        'focus': "Next: Work on the target, capture trail entries, finalize when done.",
        'tool': "Next: Test the handler, add cognition for phenomenological transparency.",
        'release': "Next: Link features, run wobble_test, prepare dimension checklist."
    }

    if entity_type in next_steps:
        report += f"\n{next_steps[entity_type]}"

    return report


def tool_update_entity(
    entity_id: str,
    status: Optional[str] = None,
    **updates
) -> str:
    """
    Update an entity with lifecycle-aware cognition.

    Handles:
    - Field updates (data fields)
    - Status transitions (with lifecycle validation)
    - Link management (origin, links, etc.)

    Args:
        entity_id: The entity to update
        status: New status for transition (optional)
        **updates: Fields to update in entity.data

    Returns:
        Updated entity summary with any warnings/suggestions
    """
    repo = _get_repo()
    factory = _get_factory()

    # Get current entity
    entity = repo.read(entity_id)
    if not entity:
        return f"Error: {entity_id} not found"

    # Track what changed for reporting
    changes = []
    warnings = []

    # Handle status transitions specially
    if status is not None:
        old_status = entity.status
        if status != old_status:
            # Validate transition (factory has the logic)
            try:
                updated_entity = factory.update(entity_id, status=status)
                changes.append(f"status: {old_status} → {status}")
                entity = updated_entity  # Use updated entity for further changes
            except Exception as e:
                warnings.append(f"Status transition blocked: {e}")

    # Handle remaining data field updates
    if updates:
        try:
            # Merge updates into existing data
            new_data = {**entity.data, **updates}
            updated_entity = entity.copy(data=new_data)
            repo.update(updated_entity)

            for key, value in updates.items():
                old_value = entity.data.get(key, '<unset>')
                changes.append(f"{key}: {old_value} → {value}")
        except Exception as e:
            warnings.append(f"Field update failed: {e}")

    # Build report
    if changes:
        report = f"Updated {entity_id}:\n"
        for change in changes:
            report += f"  - {change}\n"
    else:
        report = f"No changes made to {entity_id}\n"

    if warnings:
        report += "\nWarnings:\n"
        for w in warnings:
            report += f"  - {w}\n"

    # Suggest next steps based on entity type and new state
    refreshed = repo.read(entity_id)
    if refreshed:
        if refreshed.type == 'feature' and refreshed.status == 'converging':
            report += "\nSuggested: Define behaviors if not already done."
        elif refreshed.type == 'inquiry' and refreshed.status == 'resolved':
            report += "\nSuggested: Consider crystallizing into a feature."
        elif refreshed.type == 'feature' and refreshed.status == 'drifting':
            report += "\nSuggested: Either recommit to work on this, or finalize with learnings."

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# DISTILLATION TOOLS - Same-type consolidation
# ═══════════════════════════════════════════════════════════════════════════════

def tool_distill_learnings(
    domain: Optional[str] = None,
    threshold: float = 0.60,
    limit: int = 50,
) -> str:
    """
    Find clusters of semantically similar learnings for distillation.

    Uses vector embeddings to identify learnings that could be
    consolidated into canonical forms.

    Args:
        domain: Optional domain to filter learnings
        threshold: Similarity threshold for clustering (default 0.60)
        limit: Maximum learnings to analyze

    Returns:
        Formatted distillation candidates
    """
    from .distillation import distill_learnings as _distill

    result = _distill(domain=domain, threshold=threshold, limit=limit)

    if result["status"] == "no_candidates":
        return result["message"]

    # Format output
    lines = [
        "# Distillation Candidates",
        f"\nFound {len(result['candidates'])} clusters of similar learnings:\n",
    ]

    for i, candidate in enumerate(result["candidates"], 1):
        lines.append(f"## Cluster {i}: {candidate['proposed_name']}")
        lines.append(f"- **Cluster ID**: {candidate['cluster_id']}")
        lines.append(f"- **Confidence**: {candidate['confidence']}")
        lines.append(f"- **Domain**: {candidate['domain']}")
        lines.append(f"- **Sources**: {candidate['source_count']} learnings")
        lines.append("")

        for source in candidate["sources"]:
            lines.append(f"  - {source['name'][:60]} (sim: {source['similarity']})")
            lines.append(f"    ID: {source['id']}")

        lines.append("")

    lines.append("\n## Next Steps")
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")

    lines.append("\nUse `apply_distillation` with a cluster_id to execute.")

    return "\n".join(lines)


# Cache for distillation candidates (for apply flow)
_distillation_cache: dict = {}


def tool_apply_distillation(
    cluster_id: str,
    canonical_name: str = "",
    canonical_insight: str = "",
) -> str:
    """
    Apply a distillation, creating canonical entity and marking sources as subsumed.

    Args:
        cluster_id: The cluster ID from distill_learnings output
        canonical_name: Name for the canonical entity (optional, uses proposed if empty)
        canonical_insight: Insight for the canonical entity (optional)

    Returns:
        Summary of distillation result
    """
    from .distillation import DistillationService, DistillationProposal
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(repository=repo)

    # Find the candidate - re-run distillation to get fresh data
    candidates = service.find_distillation_candidates('learning', limit=100)

    target = None
    for c in candidates:
        if c.cluster_id == cluster_id:
            target = c
            break

    if not target:
        return f"Error: Cluster '{cluster_id}' not found. Run distill_learnings first."

    # Create proposal
    proposal = DistillationProposal(
        cluster_id=cluster_id,
        canonical_name=canonical_name or target.proposed_name,
        canonical_insight=canonical_insight or target.proposed_insight,
        source_ids=[e.id for e in target.source_entities],
        domain=target.domain,
        confidence=target.confidence,
        preserves=[],  # LLM would fill this in full flow
        reasoning=f"Distilled from {len(target.source_entities)} semantically similar learnings",
    )

    # Apply the distillation
    try:
        canonical = service.apply_distillation(proposal)

        lines = [
            "# Distillation Applied",
            f"\n✓ Created canonical: **{canonical.id}**",
            f"  - Name: {canonical.data.get('name')}",
            f"  - Domain: {canonical.data.get('domain')}",
            f"  - Subsumes: {len(proposal.source_ids)} learnings",
            "",
            "## Subsumed Learnings",
        ]

        for source_id in proposal.source_ids:
            lines.append(f"  - {source_id} → status: subsumed")

        lines.append(f"\nThe original learnings are preserved with status 'subsumed'.")
        lines.append(f"They reference the canonical via 'subsumed_by' field.")

        return "\n".join(lines)

    except Exception as e:
        return f"Error applying distillation: {e}"


def tool_distill_inquiries(
    domain: Optional[str] = None,
    threshold: float = 0.60,
    limit: int = 50,
) -> str:
    """
    Find clusters of semantically similar inquiries for distillation.

    Uses vector embeddings to identify inquiries that could be
    consolidated into canonical forms.

    Args:
        domain: Optional domain to filter inquiries
        threshold: Similarity threshold for clustering (default 0.60)
        limit: Maximum inquiries to analyze

    Returns:
        Formatted distillation candidates
    """
    from .distillation import distill_inquiries as _distill

    result = _distill(domain=domain, threshold=threshold, limit=limit)

    if result["status"] == "no_candidates":
        return result["message"]

    # Format output
    lines = [
        "# Inquiry Distillation Candidates",
        f"\nFound {len(result['candidates'])} clusters of similar inquiries:\n",
    ]

    for i, candidate in enumerate(result["candidates"], 1):
        lines.append(f"## Cluster {i}: {candidate['proposed_name']}")
        lines.append(f"- **Cluster ID**: {candidate['cluster_id']}")
        lines.append(f"- **Confidence**: {candidate['confidence']}")
        lines.append(f"- **Domain**: {candidate['domain']}")
        lines.append(f"- **Sources**: {candidate['source_count']} inquiries")
        lines.append("")

        for source in candidate["sources"]:
            lines.append(f"  - {source['name'][:60]} (sim: {source['similarity']})")
            lines.append(f"    ID: {source['id']}")
            if source.get('terrain'):
                lines.append(f"    Terrain: {source['terrain'][:50]}...")
            if source.get('core_concern'):
                lines.append(f"    Core: {source['core_concern'][:50]}...")

        lines.append("")

    lines.append("\n## Next Steps")
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")

    lines.append("\nUse `apply_distillation` with a cluster_id to execute.")

    return "\n".join(lines)


def tool_distill_features(
    domain: Optional[str] = None,
    threshold: float = 0.70,
    limit: int = 50,
) -> str:
    """
    Find clusters of semantically similar features for distillation.

    Uses vector embeddings on description + problem to identify features
    that could be consolidated into canonical forms.

    Higher threshold (0.70) due to structural complexity of features.

    Args:
        domain: Optional domain to filter features
        threshold: Similarity threshold for clustering (default 0.70)
        limit: Maximum features to analyze

    Returns:
        Formatted distillation candidates
    """
    from .distillation import distill_features as _distill

    result = _distill(domain=domain, threshold=threshold, limit=limit)

    if result["status"] == "no_candidates":
        return result["message"]

    # Format output
    lines = [
        "# Feature Distillation Candidates",
        f"\nFound {len(result['candidates'])} clusters of similar features:\n",
    ]

    for i, candidate in enumerate(result["candidates"], 1):
        lines.append(f"## Cluster {i}: {candidate['proposed_name']}")
        lines.append(f"- **Cluster ID**: {candidate['cluster_id']}")
        lines.append(f"- **Confidence**: {candidate['confidence']}")
        lines.append(f"- **Domain**: {candidate['domain']}")
        lines.append(f"- **Sources**: {candidate['source_count']} features")
        lines.append("")

        for source in candidate["sources"]:
            lines.append(f"  - {source['name'][:60]} [{source['status']}] (sim: {source['similarity']})")
            lines.append(f"    ID: {source['id']}")
            if source.get('description'):
                lines.append(f"    Desc: {source['description'][:50]}...")
            if source.get('problem'):
                lines.append(f"    Problem: {source['problem'][:50]}...")

        lines.append("")

    lines.append("\n## Next Steps")
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")

    lines.append("\nUse `apply_distillation` with a cluster_id to execute.")

    return "\n".join(lines)


def tool_distill_patterns(
    domain: Optional[str] = None,
    subtype: Optional[str] = None,
    threshold: float = 0.75,
    limit: int = 50,
) -> str:
    """
    Find clusters of semantically similar patterns for distillation.

    Uses vector embeddings on problem + solution + context to identify patterns
    that could be consolidated. Only clusters same-subtype patterns.

    Highest threshold (0.75) - patterns encode nuanced wisdom.

    Args:
        domain: Optional domain to filter patterns
        subtype: Optional subtype filter (meta, architectural, process, etc.)
        threshold: Similarity threshold for clustering (default 0.75)
        limit: Maximum patterns to analyze

    Returns:
        Formatted distillation candidates
    """
    from .distillation import distill_patterns as _distill

    result = _distill(domain=domain, subtype=subtype, threshold=threshold, limit=limit)

    if result["status"] == "no_candidates":
        return result["message"]

    # Format output
    lines = [
        "# Pattern Distillation Candidates",
        f"\nFound {len(result['candidates'])} clusters of similar patterns:\n",
    ]

    for i, candidate in enumerate(result["candidates"], 1):
        lines.append(f"## Cluster {i}: {candidate['proposed_name']}")
        lines.append(f"- **Cluster ID**: {candidate['cluster_id']}")
        lines.append(f"- **Confidence**: {candidate['confidence']}")
        lines.append(f"- **Domain**: {candidate['domain']}")
        lines.append(f"- **Sources**: {candidate['source_count']} patterns")
        lines.append("")

        for source in candidate["sources"]:
            lines.append(f"  - {source['name'][:60]} [{source['subtype']}] (sim: {source['similarity']})")
            lines.append(f"    ID: {source['id']}")
            if source.get('problem'):
                lines.append(f"    Problem: {source['problem'][:50]}...")
            if source.get('solution'):
                lines.append(f"    Solution: {source['solution'][:50]}...")

        lines.append("")

    lines.append("\n## Next Steps")
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")

    lines.append("\n**Warning**: Pattern distillation requires careful judgment.")
    lines.append("Mechanics are preserved from primary source only - verify appropriateness.")
    lines.append("\nUse `apply_distillation` with a cluster_id to execute.")

    return "\n".join(lines)


def tool_bulk_distill_by_domain(
    entity_type: str,
    group_by: str = 'domain',
    threshold: float = 0.65,
    limit_per_group: int = 50,
) -> str:
    """
    Bulk distillation of entities grouped by domain or meta-behavior.

    Analyzes all entities of the specified type, groups them by the given field,
    and returns distillation proposals for each group.

    Args:
        entity_type: Type to distill (inquiry, learning, feature, pattern)
        group_by: Field to group by (domain, meta_behavior)
        threshold: Similarity threshold (default 0.65 for bulk)
        limit_per_group: Max entities per group to analyze

    Returns:
        Summary of per-group distillation proposals
    """
    from .distillation import bulk_distill_by_domain as _bulk_distill

    result = _bulk_distill(
        entity_type=entity_type,
        group_by=group_by,
        threshold=threshold,
        limit_per_group=limit_per_group,
    )

    if result["status"] == "error":
        return f"Error: {result['message']}"

    if result["status"] == "no_candidates":
        lines = [
            f"# Bulk Distillation: {entity_type}",
            f"\nNo distillation candidates found.",
            f"- Groups analyzed: {result.get('groups_analyzed', 0)}",
            f"- Threshold: {result.get('threshold', threshold)}",
        ]
        return "\n".join(lines)

    # Format output
    lines = [
        f"# Bulk Distillation: {entity_type}",
        f"\n**Grouped by**: {group_by}",
        f"**Threshold**: {threshold}",
        f"**Groups analyzed**: {result['groups_analyzed']}",
        f"**Groups with candidates**: {result['groups_with_candidates']}",
        f"**Total candidates**: {result['total_candidates']}",
        "",
    ]

    for group_name, group_data in result.get("results", {}).items():
        lines.append(f"## {group_name}")
        lines.append(f"- Entities: {group_data['entity_count']}")
        lines.append(f"- Candidates: {group_data['candidate_count']}")
        lines.append("")

        for proposal in group_data.get("proposals", []):
            lines.append(f"  ### {proposal['proposed_name']}")
            lines.append(f"  - Cluster ID: {proposal['cluster_id']}")
            lines.append(f"  - Confidence: {proposal['confidence']}")
            lines.append(f"  - Sources ({proposal['source_count']}): {', '.join(proposal['sources'][:3])}...")
            lines.append("")

    lines.append("\n## Next Steps")
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")

    return "\n".join(lines)


def tool_unsubsume(
    entity_id: str,
    window_days: int = 30,
) -> str:
    """
    Un-subsume an entity, restoring its prior status.

    Reversibility is only allowed within the window period (default 30 days).
    After the window, subsumption is permanent.

    Args:
        entity_id: ID of the subsumed entity to restore
        window_days: Maximum days since subsumption to allow reversal

    Returns:
        Status message
    """
    from .distillation import unsubsume as _unsubsume

    result = _unsubsume(entity_id=entity_id, window_days=window_days)

    if result["status"] == "success":
        return f"✓ Un-subsumed: {result['message']}"
    else:
        return f"✗ Error: {result['message']}"


def tool_unsubsume_all(
    canonical_id: str,
    window_days: int = 30,
) -> str:
    """
    Un-subsume all entities from a canonical.

    This reverses a distillation operation, restoring all source entities
    to their prior status. The canonical is marked as 'drifting' if all
    sources are restored.

    Args:
        canonical_id: ID of the canonical entity
        window_days: Maximum days since subsumption to allow reversal

    Returns:
        Summary of un-subsumption results
    """
    from .distillation import unsubsume_all as _unsubsume_all

    result = _unsubsume_all(canonical_id=canonical_id, window_days=window_days)

    lines = [
        f"# Un-subsumption Results: {canonical_id}",
        "",
        f"- **Restored**: {result['success_count']}",
        f"- **Failed**: {result['failure_count']}",
        "",
        "## Details",
    ]

    for msg in result.get("messages", []):
        lines.append(f"- {msg}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP WRAPPERS (only registered if fastmcp is available)
# ═══════════════════════════════════════════════════════════════════════════════

if MCP_AVAILABLE and _mcp:
    @_mcp.tool()
    async def orient() -> str:
        """The greeting - system's first act of care toward the arriving agent."""
        return tool_orient()

    @_mcp.tool()
    async def constellation(focus_id: str) -> str:
        """The site survey - show entities related to a focus entity."""
        return tool_constellation(focus_id)

    @_mcp.tool()
    async def pattern_evaluate(pattern_id: Optional[str] = None) -> str:
        """The fitness engine - evaluate experimental patterns."""
        return tool_pattern_evaluate(pattern_id)

    @_mcp.tool()
    async def pathway_catalog() -> str:
        """The mutation map - see all active epigenetic pathways in the autoevolutionary loop."""
        return tool_pathway_catalog()

    @_mcp.tool()
    async def induction(domain: Optional[str] = None) -> str:
        """The stomach - cluster learnings into patterns, identify surprises."""
        return tool_induction(domain)

    @_mcp.tool()
    async def digest_batch(size: int = 10, domain: Optional[str] = None, strategy: str = "oldest") -> str:
        """The spoonful - sample undigested learnings for agent analysis."""
        return tool_digest_batch(size, domain, strategy)

    @_mcp.tool()
    async def propose_synthesis(name: str, learning_ids: List[str], insight: str, domain: str, confidence: str = "medium") -> str:
        """The crystallization - create a pattern from a group of learnings."""
        return tool_propose_synthesis(name, learning_ids, insight, domain, confidence)

    @_mcp.tool()
    async def suggest_patterns(entity_type: str, context: str = "") -> str:
        """Pattern Discovery - suggest applicable patterns before entity creation."""
        return tool_suggest_patterns(entity_type, context)

    @_mcp.tool()
    async def list_entities(entity_type: Optional[str] = None, status: Optional[str] = None, limit: int = 20) -> str:
        """List entities in the store."""
        return tool_list_entities(entity_type, status, limit)

    @_mcp.tool()
    async def get_entity(entity_id: str) -> str:
        """Get a specific entity by ID."""
        return tool_get_entity(entity_id)

    @_mcp.tool()
    async def create_entity(
        entity_type: str,
        title: str,
        context: str = "",
        skip_discovery: bool = False,
        **kwargs
    ) -> str:
        """Create entity with discovery gate. Pass type-specific fields as kwargs."""
        return tool_create_entity(entity_type, title, context, skip_discovery, **kwargs)

    @_mcp.tool()
    async def update_entity(
        entity_id: str,
        status: Optional[str] = None,
        **updates
    ) -> str:
        """Update entity with lifecycle awareness. Pass field updates as kwargs."""
        return tool_update_entity(entity_id, status, **updates)

    @_mcp.tool()
    async def list_tools() -> str:
        """List all available dynamic tools."""
        return tool_list_tools()

    @_mcp.tool()
    async def invoke_tool(tool_id: str, **inputs) -> str:
        """Invoke a dynamic tool by ID with optional inputs."""
        return tool_invoke(tool_id, **inputs)

    # ═══════════════════════════════════════════════════════════════════════════
    # TRANSFORMATION VERBS (The 7 Verbs)
    # ═══════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def crystallize(inquiry_id: str) -> str:
        """Transform inquiry into feature - crystallize potential into structure."""
        return tool_crystallize(inquiry_id)

    @_mcp.tool()
    async def engage(feature_id: str, agent: str = "claude") -> str:
        """Create focus on feature - direct energy at structure."""
        return tool_engage(feature_id, agent)

    @_mcp.tool()
    async def finalize(
        entity_id: str,
        reason: str = "",
        felt_quality: str = "",
        care_at_center: str = "",
        handoff_note: str = ""
    ) -> str:
        """End lifecycle with learning extraction - biological digestion, not deletion.

        For focus entities, you can also provide aliveness fields:
        - felt_quality: How the work felt (e.g., "flowing", "stuck", "curious")
        - care_at_center: What was being cared for
        - handoff_note: A gift for whoever comes next
        """
        return tool_finalize(entity_id, reason, felt_quality, care_at_center, handoff_note)

    # ═══════════════════════════════════════════════════════════════════════════
    # RELEASE COHERENCE TOOLS
    # ═══════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def wobble_test(release_id: str) -> str:
        """The wobble test - check a release for coherence imbalances."""
        return tool_wobble_test(release_id)

    @_mcp.tool()
    async def dimension_checklist(release_id: str) -> str:
        """Five dimensions checklist - track release orchestration progress."""
        return tool_dimension_checklist(release_id)

    @_mcp.tool()
    async def dimension_prompts(dimension_id: str) -> str:
        """Show prompts for a specific dimension (narrative, value, audience, invitation, support)."""
        return tool_dimension_prompts(dimension_id)

    @_mcp.tool()
    async def pre_release_check(release_id: str) -> str:
        """Pre-release check - comprehensive release readiness assessment."""
        return tool_pre_release_check(release_id)

    @_mcp.tool()
    async def generate_story(release_id: str) -> str:
        """Generate a release story from dimension responses and features."""
        return tool_generate_story(release_id)

    @_mcp.tool()
    async def story_status(release_id: str) -> str:
        """Check how complete the release story is."""
        return tool_story_status(release_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # KERNEL COHERENCE TOOLS
    # ═══════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def coherence_check(scope: str = "workspace") -> str:
        """Check CLAUDE.md coherence with kernel schema (entity.yaml)."""
        return tool_coherence_check(scope)

    # ═══════════════════════════════════════════════════════════════════════════
    # TRACEABILITY TOOLS (Feature-Behavior-Test Coherence)
    # ═══════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def scan_features(directory: str = "tests/features") -> str:
        """Scan .feature files and report on test scenarios."""
        return tool_scan_features(directory)

    @_mcp.tool()
    async def extract_behaviors(feature_file: str) -> str:
        """Extract behaviors from a .feature file in kernel format."""
        return tool_extract_behaviors(feature_file)

    @_mcp.tool()
    async def coverage_report() -> str:
        """Generate test coverage report for all features."""
        return tool_coverage_report()

    @_mcp.tool()
    async def link_test(test_file: str, entity_id: str) -> str:
        """Link a test file to an entity (injects traceability metadata)."""
        return tool_link_test_to_entity(test_file, entity_id)

    @_mcp.tool()
    async def generate_behaviors_from_tests(entity_id: str) -> str:
        """Generate behavior documentation from tests for an entity."""
        return tool_generate_behaviors(entity_id)

    @_mcp.tool()
    async def link_all_tests() -> str:
        """Batch link all test files to their matching entities."""
        return tool_link_all_tests()

    @_mcp.tool()
    async def scan_code(directory: str = "src/chora_store") -> str:
        """Scan Python code for pattern usage (Factory, Repository, Observer)."""
        return tool_scan_code(directory)

    @_mcp.tool()
    async def find_dark_behaviors() -> str:
        """Find implemented but undocumented behaviors in code."""
        return tool_find_dark_behaviors()

    @_mcp.tool()
    async def pattern_audit() -> str:
        """Audit all behaviors for pattern alignment."""
        return tool_pattern_audit()

    @_mcp.tool()
    async def emergent_patterns() -> str:
        """Find candidates for new patterns from recurring behaviors."""
        return tool_find_emergent_patterns()

    @_mcp.tool()
    async def audit_behavior(behavior_id: str) -> str:
        """Audit a specific behavior for pattern alignment."""
        return tool_audit_behavior(behavior_id)

    # ═══════════════════════════════════════════════════════════════════════════════
    # PATTERN REIFICATION TOOLS
    # ═══════════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def reify_patterns(min_confidence: float = 0.7) -> str:
        """
        Run full autonomous pattern reification pipeline.

        Detects emergent patterns, creates pattern entities, and links behaviors.
        No human approval needed - fitness function handles promotion/deprecation.
        """
        return tool_reify_patterns(min_confidence)

    @_mcp.tool()
    async def align_behaviors() -> str:
        """Update all behaviors with implements_pattern field linking to canonical patterns."""
        return tool_align_behaviors()

    @_mcp.tool()
    async def pattern_coverage() -> str:
        """Report on pattern alignment coverage across all behaviors."""
        return tool_pattern_coverage()

    # ═══════════════════════════════════════════════════════════════════════════
    # TIERED RESOLUTION TOOLS
    # ═══════════════════════════════════════════════════════════════════════════

    @_mcp.tool()
    async def tiered_synthesize(
        learning_ids: List[str],
        max_tier: str = "inference",
        confidence_threshold: float = 0.7,
    ) -> str:
        """
        Run tiered synthesis - tries cheap tiers first, escalates when needed.

        Push-Right principle: workflow tier → data tier (route lookup) → inference tier.
        """
        return tool_tiered_synthesize(learning_ids, max_tier, confidence_threshold)

    @_mcp.tool()
    async def list_routes(
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> str:
        """List crystallized routes for tiered resolution."""
        return tool_list_routes(tool_id, status, limit)

    @_mcp.tool()
    async def crystallize_routes(
        tool_id: Optional[str] = None,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
    ) -> str:
        """
        Auto-crystallize routes from trace patterns (Push-Right).

        Finds repeated input patterns with consistent outputs and creates canary routes.
        """
        return tool_crystallize_routes(tool_id, min_traces, consistency_threshold)

    @_mcp.tool()
    async def promote_route(route_id: str) -> str:
        """Promote a route from canary to active status."""
        return tool_promote_route(route_id)


def main():
    """Run the MCP server."""
    if not MCP_AVAILABLE:
        print("fastmcp not installed. Install with: pip install fastmcp")
        print("Tools can still be used via tool_* functions.")
        return

    # Register all tool entities as MCP functions before starting server
    registered = register_tool_entities_as_mcp()
    if registered:
        print(f"Registered {registered} tool entities as MCP functions")

    _mcp.run(show_banner=False)


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================
# Lazy registration happens when MCP functions are actually used

_tools_registered = False


def _ensure_tools_registered():
    """Lazy registration of tool entities as MCP functions."""
    global _tools_registered
    if not _tools_registered and MCP_AVAILABLE and _mcp is not None:
        register_tool_entities_as_mcp()
        _tools_registered = True


if __name__ == "__main__":
    main()
