"""
CLI commands for chora-store.

These are extracted from justfile heredocs for cross-platform compatibility.
"""

import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from .factory import EntityFactory
from .repository import EntityRepository
from .vitality import VitalitySensor
from .agent import get_current_agent


# --- Contextual Tool Awareness ---

# Maps workspace phases to tool cognition phases
WORKSPACE_TO_TOOL_PHASE = {
    'exploring': ['check', 'focus'],      # Inquiries → crystallize, evaluate
    'building': ['focus', 'constellation'],  # Features → engage, get context
    'executing': ['focus', 'check'],      # Tasks → work tools, finalize
    'idle': ['orient'],                    # Nothing active → orient tools
}


def get_contextual_tools(workspace_phase: str, limit: int = 3) -> list:
    """
    Get tools relevant to current workspace phase by matching cognition.phase.

    This bridges the gap between workspace state and tool awareness - making
    phenomenological cognition active rather than passive.

    Args:
        workspace_phase: Current workspace phase (exploring, building, executing, idle)
        limit: Maximum number of tools to return

    Returns:
        List of dicts with tool info including ready_at_hand descriptions
    """
    repo = EntityRepository()
    tools = repo.list(entity_type='tool', status='active', limit=100)

    # Get relevant tool phases for this workspace phase
    relevant_phases = WORKSPACE_TO_TOOL_PHASE.get(workspace_phase, ['orient'])

    contextual = []
    for tool in tools:
        cognition = tool.data.get('cognition', {})
        tool_phase = cognition.get('phase', tool.data.get('phase'))

        if tool_phase in relevant_phases:
            # Extract the phenomenological ready_at_hand description
            ready_at_hand = cognition.get('ready_at_hand', '')
            if not ready_at_hand:
                ready_at_hand = tool.data.get('description', '')[:60]

            contextual.append({
                'id': tool.id,
                'name': tool.data.get('name', tool.id),
                'ready_at_hand': ready_at_hand[:80] if ready_at_hand else '',
                'phase': tool_phase,
                'command': f"just tool {tool.id.replace('tool-', '')}",
            })

    # Prioritize tools with ready_at_hand descriptions (richer cognition)
    contextual.sort(key=lambda t: (0 if t['ready_at_hand'] else 1, t['name']))

    return contextual[:limit]


# --- MCP Functions Mapping (Dynamic Discovery) ---

def _build_mcp_functions():
    """
    Build mapping from tool names to function names dynamically.

    This replaces the hardcoded dict to ensure ALL MCP tools are
    CLI-invokable with both hyphen and underscore naming conventions.

    Source: learning-dynamic-lookup-beats-hardcoded-mapping
    """
    from .mcp import MCP_INFRASTRUCTURE_TOOLS
    import chora_store.mcp as mcp_module

    mapping = {}

    # 1. Map from MCP_INFRASTRUCTURE_TOOLS (hyphenated names)
    for name in MCP_INFRASTRUCTURE_TOOLS.keys():
        func_name = 'tool_' + name.replace('-', '_')
        mapping[name] = func_name                    # get-entity -> tool_get_entity
        mapping[name.replace('-', '_')] = func_name  # get_entity -> tool_get_entity

    # 2. Discover any tool_* functions not in MCP_INFRASTRUCTURE_TOOLS
    for attr in dir(mcp_module):
        if attr.startswith('tool_') and callable(getattr(mcp_module, attr)):
            base = attr[5:]  # tool_get_entity -> get_entity
            canonical = base.replace('_', '-')  # get_entity -> get-entity
            if canonical not in mapping:
                mapping[canonical] = attr
                mapping[base] = attr

    return mapping

# Lazy initialization - built on first use
_mcp_functions_cache = None

def _get_mcp_functions():
    """Get or build the MCP functions mapping."""
    global _mcp_functions_cache
    if _mcp_functions_cache is None:
        _mcp_functions_cache = _build_mcp_functions()
    return _mcp_functions_cache


# --- Pattern Coverage Helper ---

def _calculate_pattern_coverage(entities):
    """
    Calculate pattern alignment metrics for orient display.

    Returns dict with total behaviors, aligned count, coverage %, and breakdown.
    """
    total = 0
    aligned = 0
    by_pattern = {}

    for entity in entities:
        if entity.type != 'feature':
            continue
        for behavior in entity.data.get('behaviors', []):
            # Handle both dict format (new) and string format (legacy)
            if isinstance(behavior, dict):
                total += 1
                pattern_id = behavior.get('implements_pattern')
                if pattern_id:
                    aligned += 1
                    by_pattern[pattern_id] = by_pattern.get(pattern_id, 0) + 1
            elif isinstance(behavior, str):
                total += 1  # Count string behaviors but they can't have pattern alignment

    return {
        'total': total,
        'aligned': aligned,
        'coverage_pct': (aligned / total * 100) if total > 0 else 0,
        'by_pattern': by_pattern,
        'gap_to_target': max(0, int(total * 0.8) - aligned),
    }


# --- Constellation (Phase 2: Relevance Realization) ---

def get_constellation(focus_id: str, repo=None):
    """
    Get the constellation of entities around a focus entity.

    Returns map not territory: IDs, names, statuses, relationship types.
    Traces upstream (what led to this), downstream (what came from this),
    and siblings (related by domain).
    """
    if repo is None:
        repo = EntityRepository()

    focus = repo.read(focus_id)
    if not focus:
        return {'error': f'Entity not found: {focus_id}'}

    def entity_summary(e):
        """Extract map-level summary from entity."""
        name = e.data.get('name', '') or e.data.get('title', '') or e.data.get('insight', '')[:40] or ''
        if isinstance(name, dict):
            name = name.get('statement', str(name))
        return {
            'id': e.id,
            'type': e.type,
            'status': e.status,
            'name': str(name)[:50]
        }

    constellation = {
        'focus': entity_summary(focus),
        'upstream': [],    # What led to this
        'downstream': [],  # What came from this
        'siblings': [],    # Related by domain/proximity
    }

    # --- Trace Upstream ---
    # Origin link (feature -> inquiry, task -> feature)
    origin_id = focus.data.get('origin') or focus.data.get('origin_inquiry')
    if origin_id:
        origin = repo.read(origin_id)
        if origin:
            constellation['upstream'].append(entity_summary(origin))

    # Subsumed_by (this entity was consolidated into another)
    subsumed_by_id = focus.data.get('subsumed_by')
    if subsumed_by_id:
        canonical = repo.read(subsumed_by_id)
        if canonical:
            summary = entity_summary(canonical)
            summary['relation'] = 'canonical'
            constellation['upstream'].append(summary)

    # Links array (learning -> inquiries, features)
    for link_id in focus.data.get('links', []):
        if isinstance(link_id, str):
            linked = repo.read(link_id)
            if linked:
                constellation['upstream'].append(entity_summary(linked))

    # Learnings that informed this (feature.learnings)
    for learning_id in focus.data.get('learnings', []):
        if isinstance(learning_id, str):
            learning = repo.read(learning_id)
            if learning:
                constellation['upstream'].append(entity_summary(learning))

    # --- Trace Downstream ---
    # Entities this focus subsumes (canonical -> subsumed entities)
    subsumes_ids = focus.data.get('subsumes', [])
    for subsumed_id in subsumes_ids:
        if isinstance(subsumed_id, str):
            subsumed = repo.read(subsumed_id)
            if subsumed:
                summary = entity_summary(subsumed)
                summary['relation'] = 'subsumed'
                constellation['downstream'].append(summary)

    all_entities = repo.list(limit=500)
    for e in all_entities:
        if e.id == focus_id:
            continue

        # Entities that have this as origin
        if e.data.get('origin') == focus_id or e.data.get('origin_inquiry') == focus_id:
            constellation['downstream'].append(entity_summary(e))

        # Entities that link to this
        elif focus_id in e.data.get('links', []):
            constellation['downstream'].append(entity_summary(e))

        # Tasks under this feature
        elif e.data.get('feature_id') == focus_id:
            constellation['downstream'].append(entity_summary(e))

        # Features that include this learning
        elif focus_id in e.data.get('learnings', []):
            constellation['downstream'].append(entity_summary(e))

        # Entities that have this as subsumed_by (inverse of subsumes)
        elif e.data.get('subsumed_by') == focus_id:
            if e.id not in subsumes_ids:  # Avoid duplicates
                summary = entity_summary(e)
                summary['relation'] = 'subsumed'
                constellation['downstream'].append(summary)

    # --- Trace Siblings ---
    focus_domain = focus.data.get('domain', '')
    if focus_domain:
        for e in all_entities:
            if e.id != focus_id and e.data.get('domain') == focus_domain:
                if len(constellation['siblings']) < 10:
                    constellation['siblings'].append(entity_summary(e))

    # Cap all lists at 10 (map not territory)
    constellation['upstream'] = constellation['upstream'][:10]
    constellation['downstream'] = constellation['downstream'][:10]
    constellation['siblings'] = constellation['siblings'][:10]

    return constellation


def _get_time_since_last_orient(repo=None) -> str:
    """
    Get human-readable time since last orient invocation.

    Returns:
        Time string like "2 hours ago" or "never" if no prior orient.
    """
    from datetime import timedelta

    if repo is None:
        repo = EntityRepository()

    # Check for last orient timestamp via most recent focus entity as proxy
    try:
        focuses = repo.list(entity_type='focus', limit=1)
        if focuses:
            last_focus = focuses[0]
            updated = last_focus.updated_at
            if updated:
                now = datetime.now()
                delta = now - updated
                if delta < timedelta(minutes=5):
                    return "just now"
                elif delta < timedelta(hours=1):
                    mins = int(delta.total_seconds() / 60)
                    return f"{mins} minutes ago"
                elif delta < timedelta(days=1):
                    hours = int(delta.total_seconds() / 3600)
                    return f"{hours} hours ago"
                else:
                    days = delta.days
                    return f"{days} days ago"
    except Exception:
        pass

    return "unknown"


def get_workspace_context(repo, scope=None):
    """
    Get workspace context for orientation using vitality sensing.

    Args:
        repo: EntityRepository instance
        scope: Optional attention scope filter:
            - 'inner': Immediate work (active tasks, current features, active inquiries)
            - 'adjacent': Extended context (validated learnings, adopted patterns)
            - 'far': Systemic view (all patterns, releases, stable features)
            - None: Full context (no filtering)

    Returns:
        Context dict with entities filtered by scope
    """
    # Use vitality sensor for real metrics
    sensor = VitalitySensor(repo)
    vitality = sensor.summary()

    # Count entities by type
    all_entities = repo.list(limit=1000)

    # --- Hierarchy of Attention: Scope Filtering ---
    def in_scope(entity, scope):
        """Determine if entity is in the requested attention scope."""
        if scope is None:
            return True

        e_type = entity.type
        e_status = entity.status

        if scope == 'inner':
            # Inner scope: immediate work items
            # - Active tasks
            # - Current features (nascent, converging)
            # - Active inquiries
            if e_type == 'task' and e_status == 'active':
                return True
            if e_type == 'feature' and e_status in ('nascent', 'converging'):
                return True
            if e_type == 'inquiry' and e_status == 'active':
                return True
            return False

        elif scope == 'adjacent':
            # Adjacent scope: validated/supporting context
            # - Inner scope entities
            # - Validated learnings
            # - Adopted patterns
            # - Blocked tasks (adjacent concern)
            if in_scope(entity, 'inner'):
                return True
            if e_type == 'learning' and e_status == 'validated':
                return True
            if e_type == 'pattern' and e_status == 'adopted':
                return True
            if e_status == 'blocked':
                return True
            return False

        elif scope == 'far':
            # Far scope: systemic entities
            # - All patterns
            # - All releases
            # - Stable features
            # - Applied learnings
            if e_type in ('pattern', 'release'):
                return True
            if e_type == 'feature' and e_status == 'stable':
                return True
            if e_type == 'learning' and e_status == 'applied':
                return True
            return False

        return True  # Unknown scope = no filter

    # Filter entities by scope
    scoped_entities = [e for e in all_entities if in_scope(e, scope)]

    # Track current scope for context output
    scope_info = {
        'active': scope,
        'total_entities': len(all_entities),
        'scoped_entities': len(scoped_entities),
    }

    counts = {}
    active_inquiries = []
    active_features = []
    active_tasks = []
    blocked = []
    sample_learnings = []  # Sample of undigested learnings for semantic surface
    recent_work = []  # Recently touched work items for session continuity

    # Use scoped entities for filtered view
    for e in scoped_entities:
        counts[e.type] = counts.get(e.type, 0) + 1

        # Track active work (using Active State Lifecycle language)
        # Include semantic data for agent cognition, not just IDs
        if e.type == 'inquiry' and e.status == 'active':
            core_concern = e.data.get('core_concern', '')
            # Handle dict format (legacy) - extract statement if present
            if isinstance(core_concern, dict):
                core_concern = core_concern.get('statement', str(core_concern))
            if not isinstance(core_concern, str):
                core_concern = str(core_concern)
            active_inquiries.append({
                'id': e.id,
                'status': e.status,
                'core_concern': core_concern[:60] + '...' if len(core_concern) > 60 else core_concern
            })
        elif e.type == 'feature' and e.status in ('nascent', 'converging'):
            name = e.data.get('name', '')
            active_features.append({
                'id': e.id,
                'status': e.status,
                'name': name
            })
        elif e.type == 'task' and e.status == 'active':
            name = e.data.get('name', '')
            active_tasks.append({
                'id': e.id,
                'status': e.status,
                'name': name
            })

        # Track blocked
        if e.status == 'blocked':
            blocked.append({'id': e.id})

        # Sample undigested learnings (captured = not yet validated/applied)
        if e.type == 'learning' and e.status == 'captured' and len(sample_learnings) < 5:
            insight = e.data.get('insight', '')
            if isinstance(insight, str) and insight:
                # Clean up: single line, truncated
                insight_clean = ' '.join(insight.split())[:80]
                if len(insight) > 80:
                    insight_clean += '...'
                sample_learnings.append({
                    'id': e.id,
                    'insight': insight_clean
                })

    # Recent work for session continuity (last 3 modified work items)
    # Uses scoped entities to respect hierarchy of attention
    work_types = {'inquiry', 'feature', 'task', 'learning'}
    work_items = [e for e in scoped_entities if e.type in work_types]
    work_items.sort(key=lambda x: x.updated_at or '', reverse=True)
    for e in work_items[:3]:
        name = e.data.get('name', '') or e.data.get('core_concern', '') or e.data.get('insight', '')
        if isinstance(name, dict):
            name = name.get('statement', str(name))
        if not isinstance(name, str):
            name = str(name)
        name_clean = ' '.join(name.split())[:50]
        if len(name) > 50:
            name_clean += '...'
        recent_work.append({
            'id': e.id,
            'type': e.type,
            'name': name_clean,
            'updated': e.updated_at
        })

    # Current focus - the most recently touched active inquiry (narrative thread)
    # This bridges the session context gap - shows what the agent was working on
    # Uses scoped entities to respect hierarchy of attention
    current_focus = None
    active_inquiry_entities = [e for e in scoped_entities if e.type == 'inquiry' and e.status == 'active']
    if active_inquiry_entities:
        # Find the most recently updated active inquiry
        active_inquiry_entities.sort(key=lambda x: x.updated_at or '', reverse=True)
        focus_inquiry = active_inquiry_entities[0]

        # Extract rich context for the narrative thread
        core_concern = focus_inquiry.data.get('core_concern', '')
        if isinstance(core_concern, dict):
            core_concern = core_concern.get('statement', str(core_concern))
        if not isinstance(core_concern, str):
            core_concern = str(core_concern)

        terrain = focus_inquiry.data.get('terrain', {})
        adjacent = terrain.get('adjacent_concerns', []) if isinstance(terrain, dict) else []
        unknowns = terrain.get('unknowns', []) if isinstance(terrain, dict) else []

        current_focus = {
            'id': focus_inquiry.id,
            'name': focus_inquiry.data.get('name', ''),
            'core_concern': core_concern,
            'adjacent_concerns': adjacent[:3] if isinstance(adjacent, list) else [],
            'unknowns': unknowns[:3] if isinstance(unknowns, list) else [],
            'updated': focus_inquiry.updated_at
        }

    # Determine phase
    if active_inquiries:
        phase = {'name': 'exploring', 'description': 'Active inquiries in progress', 'suggestion': 'Continue dialogue or reify to feature'}
    elif active_features:
        phase = {'name': 'building', 'description': 'Features in development', 'suggestion': 'Decompose to tasks or complete features'}
    elif active_tasks:
        phase = {'name': 'executing', 'description': 'Tasks in progress', 'suggestion': 'Complete tasks'}
    else:
        phase = {'name': 'idle', 'description': 'No active work', 'suggestion': 'Start with: just inquire "Your idea"'}

    # Add contextual tools based on phase (phenomenological awareness activation)
    phase['tools'] = get_contextual_tools(phase['name'], limit=3)

    # --- Presence via Change Lens ---
    # Surface recent changes with agent attribution
    current_agent = get_current_agent()
    recent_changes = []
    agents_seen = set()

    # Get entities modified recently (sort by updated_at)
    all_entities_sorted = sorted(all_entities, key=lambda x: x.updated_at or '', reverse=True)

    for e in all_entities_sorted[:10]:  # Last 10 changes
        agent = e.data.get('last_changed_by', 'unknown')
        agents_seen.add(agent)

        name = e.data.get('name', '') or e.data.get('core_concern', '') or e.data.get('insight', '')
        if isinstance(name, dict):
            name = name.get('statement', str(name))
        if not isinstance(name, str):
            name = str(name)
        name_clean = ' '.join(name.split())[:40]
        if len(name) > 40:
            name_clean += '...'

        recent_changes.append({
            'id': e.id,
            'type': e.type,
            'name': name_clean,
            'changed_by': agent,
            'is_mine': agent == current_agent,
            'updated': e.updated_at.isoformat() if e.updated_at else None,
        })

    # Determine collaboration mode
    other_agents = agents_seen - {current_agent, 'unknown'}
    if other_agents:
        collaboration_mode = 'collaborative'
        collaboration_description = f"Working with: {', '.join(sorted(other_agents))}"
    else:
        collaboration_mode = 'solo'
        collaboration_description = "Solo work mode"

    presence = {
        'current_agent': current_agent,
        'mode': collaboration_mode,
        'description': collaboration_description,
        'other_agents': list(sorted(other_agents)),
        'recent_changes': recent_changes,
    }

    # --- Cross-Scale Visibility ---
    # Surface revolt (learning → pattern) and remember (pattern → feature) dynamics

    # Revolt: Learnings that have crystallized into patterns
    revolt_trajectories = []
    patterns_with_sources = [
        e for e in all_entities
        if e.type == 'pattern' and (
            e.data.get('extracted_from') or
            e.data.get('induced_from') or
            e.data.get('source_learnings')
        )
    ]
    for p in patterns_with_sources[:5]:  # Top 5 patterns with sources
        sources = (
            p.data.get('extracted_from') or
            p.data.get('induced_from') or
            p.data.get('source_learnings') or
            []
        )
        # Handle both string and list formats
        if isinstance(sources, str):
            sources = [sources]
        revolt_trajectories.append({
            'pattern_id': p.id,
            'pattern_name': p.data.get('name', p.id),
            'source_learnings': sources[:3],  # First 3 sources
            'source_count': len(sources),
        })

    # Remember: Patterns influencing features (via _epigenetics)
    remember_trajectories = []
    features_with_epigenetics = [
        e for e in all_entities
        if e.type == 'feature' and e.data.get('_epigenetics')
    ]
    for f in features_with_epigenetics[:5]:  # Top 5 features with patterns
        patterns_applied = f.data.get('_epigenetics', [])
        remember_trajectories.append({
            'feature_id': f.id,
            'feature_name': f.data.get('name', f.id),
            'patterns_applied': patterns_applied[:3],
            'pattern_count': len(patterns_applied),
        })

    # Cycle summaries
    fast_cycle = {
        'active_tasks': len(active_tasks),
        'active_features': len(active_features),
        'active_inquiries': len(active_inquiries),
        'description': 'Immediate work: tasks, features, inquiries'
    }

    slow_cycle = {
        'patterns': counts.get('pattern', 0),
        'releases': counts.get('release', 0),
        'applied_learnings': len([e for e in all_entities if e.type == 'learning' and e.status == 'applied']),
        'description': 'Systemic structure: patterns, releases, codified wisdom'
    }

    cross_scale = {
        'revolt': revolt_trajectories,
        'remember': remember_trajectories,
        'fast_cycle': fast_cycle,
        'slow_cycle': slow_cycle,
    }

    # --- Orient as Coordination Surface ---
    # Unify individual (my work) and collective (shared work) contexts

    # Individual context: work by current agent
    my_work = []
    work_types = {'inquiry', 'feature', 'task', 'learning'}
    for e in all_entities:
        if e.type not in work_types:
            continue
        # Check if I created or last modified this entity
        created_by = e.data.get('created_by', '')
        last_changed_by = e.data.get('last_changed_by', '')
        if created_by == current_agent or last_changed_by == current_agent:
            name = e.data.get('name', '') or e.data.get('core_concern', '') or e.data.get('insight', '')
            if isinstance(name, dict):
                name = name.get('statement', str(name))
            if not isinstance(name, str):
                name = str(name)
            name_clean = ' '.join(name.split())[:40]
            if len(name) > 40:
                name_clean += '...'
            my_work.append({
                'id': e.id,
                'type': e.type,
                'status': e.status,
                'name': name_clean,
                'is_owner': created_by == current_agent,
            })

    # Sort my work by recency
    my_work_ids = {w['id'] for w in my_work}
    my_work_sorted = sorted(my_work, key=lambda x: (
        all_entities_sorted.index(next((e for e in all_entities_sorted if e.id == x['id']), all_entities_sorted[-1]))
        if any(e.id == x['id'] for e in all_entities_sorted) else 9999
    ))

    # Collective context: entities from others (not in my_work)
    others_work = []
    for e in all_entities_sorted[:20]:  # Recent 20 entities
        if e.id in my_work_ids:
            continue
        if e.type not in work_types:
            continue
        changed_by = e.data.get('last_changed_by', 'unknown')
        if changed_by != current_agent and changed_by != 'unknown':
            name = e.data.get('name', '') or e.data.get('core_concern', '') or e.data.get('insight', '')
            if isinstance(name, dict):
                name = name.get('statement', str(name))
            if not isinstance(name, str):
                name = str(name)
            name_clean = ' '.join(name.split())[:40]
            if len(name) > 40:
                name_clean += '...'
            others_work.append({
                'id': e.id,
                'type': e.type,
                'status': e.status,
                'name': name_clean,
                'changed_by': changed_by,
            })

    # Coordination signals based on attention hierarchy
    coordination_signals = []
    if others_work:
        coordination_signals.append({
            'type': 'collaboration',
            'message': f"{len(set(w['changed_by'] for w in others_work))} other agent(s) active in workspace",
        })
    if len([f for f in active_features if f['status'] == 'converging']) > 3:
        coordination_signals.append({
            'type': 'convergence',
            'message': 'Multiple features converging - consider release planning',
        })
    if blocked:
        coordination_signals.append({
            'type': 'attention',
            'message': f"{len(blocked)} blocked item(s) need attention",
        })

    coordination = {
        'individual': {
            'work_items': my_work_sorted[:10],  # Top 10 my work items
            'count': len(my_work),
            'description': 'Work you created or touched',
        },
        'collective': {
            'work_items': others_work[:10],  # Top 10 others' work
            'count': len(others_work),
            'description': 'Work from other agents',
        },
        'signals': coordination_signals,
    }

    # --- Focus Marks (Stigmergic Coordination) ---
    # Get actual focus marks from FocusManager
    focus_marks = []
    try:
        from .focus import FocusManager
        fm = FocusManager(repo)
        awareness_candidates = fm.get_awareness_candidates(agent=current_agent)
        focus_marks = awareness_candidates
    except Exception:
        pass  # Focus module not available or error

    # --- Pattern Coverage (Behavior-to-Pattern Alignment) ---
    vitality['pattern_coverage'] = _calculate_pattern_coverage(all_entities)

    return {
        'season': vitality['season'],
        'integrity_score': vitality['integrity_score'],
        'phase': phase,
        'active_inquiries': active_inquiries,
        'active_features': active_features,
        'active_tasks': active_tasks,
        'blocked': blocked,
        'counts': counts,
        'vitality': vitality,
        'sample_learnings': sample_learnings,
        'recent_work': recent_work,
        'current_focus': current_focus,
        'focus_marks': focus_marks,  # Stigmergic focus marks
        'presence': presence,
        'scope': scope_info,
        'cross_scale': cross_scale,
        'coordination': coordination,
    }


def orient():
    """Show current workspace state."""
    repo = EntityRepository()

    # Pull remote changes first (best-effort, silent failure)
    sync_status = None
    pulled_count = 0
    try:
        from .cloud_cli import is_configured, pull_entities
        if is_configured():
            sync_status = "connected"
            remote_entities = pull_entities()
            for entity_dict in remote_entities:
                try:
                    from .models import Entity
                    entity = Entity.from_dict(entity_dict)
                    existing = repo.read(entity.id)
                    if existing:
                        if entity.version > existing.version:
                            repo.update(entity)
                            pulled_count += 1
                    else:
                        repo.create(entity)
                        pulled_count += 1
                except Exception:
                    pass  # Skip problematic entities
    except Exception:
        sync_status = "error"

    ctx = get_workspace_context(repo)
    ctx['sync_status'] = sync_status
    ctx['pulled_count'] = pulled_count

    # Run Phase 6 epigenetic hooks (cron:daily trigger)
    # These are the autonomous pattern reification hooks
    phase6_results = None
    try:
        from .observer import get_observer
        observer = get_observer()
        phase6_results = observer.run_epigenetic_hooks(repo, "cron:daily")
    except Exception:
        pass  # Silent failure for hooks

    # Run daily crystallization (Push-Right solidification)
    # This turns repeated inference traces into cheap data lookups
    crystallization_result = None
    try:
        from .mcp import tool_crystallize_routes
        crystallization_result = tool_crystallize_routes(
            tool_id=None,
            min_traces=5,
            consistency_threshold=0.95,
        )
    except Exception:
        pass  # Silent failure for crystallization

    print("")
    print("  ╭──────────────────────────────────────────────────────────╮")
    print("  │  ORIENT · Vitality Sensing                               │")
    print("  ╰──────────────────────────────────────────────────────────╯")
    print("")

    # Season and integrity (now real metrics)
    season = ctx.get('season', 'unknown')
    integrity = ctx.get('integrity_score', 0)
    season_emoji = "🌱" if season == "construction" else "🔧"
    print(f"  Season: {season_emoji} {season.title()}")
    print(f"  Integrity: {integrity:.0%}")

    # Current Focus - the narrative thread for session continuity
    # This shows the agent what it was working on, with full context
    current_focus = ctx.get('current_focus')
    if current_focus:
        print("")
        print("  ┌─ Current Focus ─────────────────────────────────────────┐")
        name = current_focus.get('name', '')
        if name:
            print(f"  │ 💭 {name}")
        core = current_focus.get('core_concern', '')
        if core:
            # Word wrap long core concerns
            core_clean = ' '.join(core.split())
            if len(core_clean) > 55:
                print(f"  │    \"{core_clean[:55]}\"")
                print(f"  │    \"{core_clean[55:110]}...\"" if len(core_clean) > 110 else f"  │    \"{core_clean[55:]}\"")
            else:
                print(f"  │    \"{core_clean}\"")
        adjacent = current_focus.get('adjacent_concerns', [])
        if adjacent:
            print(f"  │")
            print(f"  │  Adjacent concerns:")
            for a in adjacent[:2]:
                a_clean = ' '.join(str(a).split())[:50]
                print(f"  │    · {a_clean}")
        unknowns = current_focus.get('unknowns', [])
        if unknowns:
            print(f"  │")
            print(f"  │  Open questions:")
            for u in unknowns[:2]:
                u_clean = ' '.join(str(u).split())[:50]
                print(f"  │    ? {u_clean}")
        print(f"  │")
        print(f"  │  {current_focus.get('id', '')}")
        print("  └────────────────────────────────────────────────────────┘")

    # Focus Marks (Stigmergic Coordination)
    focus_marks = ctx.get('focus_marks', [])
    if focus_marks:
        print("")
        print("  ┌─ Focus Marks (Stigmergic) ───────────────────────────────┐")
        for fm in focus_marks[:5]:  # Show top 5
            # Use warmer icon if focus has aliveness fields
            has_aliveness = fm.get('felt_quality') or fm.get('handoff_note')
            if fm.get('status') == 'stale':
                status_icon = "🔴"
            elif has_aliveness:
                status_icon = "🔥"  # Warm - this focus left something alive
            else:
                status_icon = "🟢"
            is_own = "·" if fm.get('is_own') else fm.get('agent', '?')[:12]
            target = fm.get('target', '')[:80]  # Comfortable identifier length
            print(f"  │  {status_icon} [{is_own}] → {target}")
            # Show felt quality if present (no truncation - usually short)
            if fm.get('felt_quality'):
                print(f"  │     ✨ {fm['felt_quality']}")
            # Show care at center if present (half-tweet, enough for a thought)
            if fm.get('care_at_center'):
                care = fm['care_at_center'][:140]
                print(f"  │     ♡ {care}")
        if len(focus_marks) > 5:
            print(f"  │  ... and {len(focus_marks) - 5} more")
        print("  └────────────────────────────────────────────────────────┘")

    # Recent work for session continuity
    recent_work = ctx.get('recent_work', [])
    if recent_work:
        print("")
        print("  Recently Touched:")
        type_emoji = {'inquiry': '💭', 'feature': '📦', 'task': '⚡', 'learning': '💡'}
        for r in recent_work:
            emoji = type_emoji.get(r['type'], '·')
            print(f"    {emoji} {r['name']}")
    print("")

    # Vitality metrics
    vitality = ctx.get('vitality', {})
    features = vitality.get('features', {})
    metabolism = vitality.get('metabolism', {})

    if features.get('total', 0) > 0:
        print(f"  Features: {features.get('stable', 0)} stable, {features.get('drifting', 0)} drifting")

    if metabolism.get('learnings', 0) > 0:
        undigested = metabolism.get('undigested', 0)
        if undigested > 0:
            print(f"  Metabolism: {undigested} undigested learning(s)")
            # Show sample learnings for semantic access
            sample_learnings = ctx.get('sample_learnings', [])
            if sample_learnings:
                for l in sample_learnings[:3]:
                    print(f"    • {l['insight']}")
        else:
            print(f"  Metabolism: healthy")

    # Experimental patterns fitness (Epigenetic Bridge)
    try:
        from .evaluator import PatternEvaluator
        evaluator = PatternEvaluator(repo)
        fitness_summary = evaluator.get_summary()
        if fitness_summary['total_patterns'] > 0:
            print(f"  Epigenetics: {fitness_summary['total_patterns']} experimental pattern(s)")
            for p in fitness_summary['patterns'][:3]:
                status_icon = "🧬" if p['recommendation'] == 'continue' else "✓" if p['recommendation'] == 'promote' else "✗"
                print(f"    {status_icon} {p['id'].replace('pattern-', '')}: {p['recommendation']} ({p['sample_size']})")
    except Exception:
        pass  # Evaluator not available

    # Canary monitoring (bricking detection)
    try:
        from .evaluator import CanaryMonitor
        canary = CanaryMonitor(repo)
        canary_summary = canary.get_summary()
        if canary_summary['critical_alerts'] > 0 or canary_summary['warning_alerts'] > 0:
            health = canary_summary['health']
            health_icon = "🚨" if health == "critical" else "⚠️"
            print(f"  Canary: {health_icon} {health.upper()}")
            for alert in canary_summary['alerts'][:3]:
                alert_icon = "🚨" if alert['severity'] == "critical" else "⚠️"
                print(f"    {alert_icon} {alert['pattern_name']}: {alert['signal']}")
                print(f"       {alert['details']}")
    except Exception:
        pass  # Canary not available

    # Kernel coherence (CLAUDE.md ↔ entity.yaml alignment)
    try:
        from .coherence import KernelCoherenceDetector
        detector = KernelCoherenceDetector()
        report = detector.analyze()
        if report.errors or report.warnings:
            score_pct = int(report.score * 100)
            indicator = "⚠️ DRIFT" if score_pct < 90 else "👀"
            print(f"  Kernel Coherence: {indicator} ({score_pct}%)")
            for err in report.errors[:2]:
                print(f"    ! {err[:55]}...")
            for warn in report.warnings[:2]:
                print(f"    ? {warn[:55]}...")
    except Exception:
        pass  # Coherence detector not available

    # Pattern induction (learning synthesis)
    try:
        from .evaluator import PatternInductor
        inductor = PatternInductor(repo)
        induction_summary = inductor.get_summary()
        if induction_summary['proposals_count'] > 0:
            print(f"  Induction: {induction_summary['proposals_count']} pattern proposal(s)")
            for p in induction_summary['proposals'][:3]:
                conf_pct = int(p['confidence'] * 100)
                print(f"    💡 {p['name'][:40]} ({conf_pct}% confidence)")
                print(f"       from {p['source_count']} learnings in {p['domain']}")
    except Exception:
        pass  # Inductor not available

    # Pattern coverage (behavior-to-pattern alignment)
    pc = vitality.get('pattern_coverage', {})
    if pc.get('total', 0) > 0:
        coverage = pc['coverage_pct']
        icon = '✓' if coverage >= 80 else '○'
        print(f"  {icon} Pattern Coverage: {pc['aligned']}/{pc['total']} ({coverage:.0f}%)")

        if pc.get('by_pattern'):
            top_patterns = sorted(pc['by_pattern'].items(), key=lambda x: -x[1])[:3]
            pattern_str = ', '.join(f"{p.split('-')[-1]}({c})" for p, c in top_patterns)
            print(f"      Top: {pattern_str}")

        if pc.get('gap_to_target', 0) > 0:
            print(f"      → {pc['gap_to_target']} more needed for 80% target")

    # Crystallization results (Push-Right)
    if crystallization_result and "crystallized" in crystallization_result.lower():
        print(f"  ❄️  Crystallization: {crystallization_result}")

    # Release coherence sensing
    try:
        from .coherence import WobbleDetector, DimensionChecklist
        releases = repo.list(entity_type='release', limit=10)
        planned_releases = [r for r in releases if r.status == 'planned']
        if planned_releases:
            print(f"  Release Coherence:")
            detector = WobbleDetector(repo)
            checklist = DimensionChecklist(repo)
            for r in planned_releases[:3]:
                report = detector.analyze(r.id)
                dims = checklist.get_status(r.id)
                score_pct = int(report.overall_score * 100)

                # Determine indicator
                if len(report.errors) > 3:
                    indicator = "🛑 STOP"
                elif len(report.errors) > 0:
                    indicator = "⏸️  WAIT"
                elif score_pct >= 80 and dims.dimensions_complete >= 4:
                    indicator = "✅ GO"
                else:
                    indicator = "👀 REVIEW"

                name = r.data.get('name', r.id)
                print(f"    📦 {name[:35]}")
                print(f"       {indicator} · {score_pct}% coherent · {dims.dimensions_complete}/5 dimensions")
                if report.errors:
                    print(f"       ! {report.errors[0][:50]}...")
    except Exception:
        pass  # Coherence not available
    print("")

    # Phase
    phase = ctx.get('phase', {})
    phase_name = phase.get('name', 'idle')
    phase_desc = phase.get('description', '')
    suggestion = phase.get('suggestion', '')
    print(f"  Phase: {phase_name}")
    if phase_desc:
        print(f"         {phase_desc}")
    if suggestion:
        print(f"  → {suggestion}")

    # Tools at hand (contextual awareness based on phase)
    contextual_tools = phase.get('tools', [])
    if contextual_tools:
        print("")
        print("  Tools at hand:")
        for tool in contextual_tools[:3]:
            name = tool.get('name', tool.get('id', 'unknown'))
            ready = tool.get('ready_at_hand', '')
            cmd = tool.get('command', '')
            print(f"    🔧 {name}")
            if ready:
                # Clean and truncate the ready_at_hand description
                ready_clean = ' '.join(ready.split())[:65]
                print(f"       {ready_clean}...")
            if cmd:
                print(f"       → {cmd}")
    print("")

    # Active work
    inquiries = ctx.get('active_inquiries', [])
    active_features = ctx.get('active_features', [])
    tasks = ctx.get('active_tasks', [])
    blocked = ctx.get('blocked', [])

    if inquiries or active_features or tasks:
        print("  Active Work:")
        for i in inquiries:
            # Show core concern for semantic understanding, not just ID
            concern = i.get('core_concern', '')
            if concern:
                print(f"    💭 {concern}")
                print(f"       └─ {i['id']}")
            else:
                print(f"    💭 {i['id']}")
        for f in active_features:
            name = f.get('name', '')
            if name:
                print(f"    📦 {name} ({f['status']})")
                print(f"       └─ {f['id']}")
            else:
                print(f"    📦 {f['id']} ({f['status']})")
        for t in tasks:
            name = t.get('name', '')
            if name:
                print(f"    ⚡ {name}")
                print(f"       └─ {t['id']}")
            else:
                print(f"    ⚡ {t['id']}")
        print("")

    if blocked:
        print("  ⚠ Blocked:")
        for b in blocked:
            print(f"    {b['id']}")
        print("")

    # Attention needed (from vitality sensing)
    attention = vitality.get('attention', [])
    stagnant = vitality.get('stagnant', [])

    if attention or stagnant:
        print("  ⚠ Attention Needed:")
        for item in attention[:3]:
            print(f"    • {item}")
        for s in stagnant[:3]:
            print(f"    • {s['id']}: {s['reason']}")
        print("")

    # Counts
    counts = ctx.get('counts', {})
    if counts:
        print("  Entities:")
        for t, c in sorted(counts.items()):
            print(f"    {t}: {c}")
        print("")

    # --- v0.4.0: The Coordination Turn ---

    # Presence via Change Lens
    presence = ctx.get('presence', {})
    if presence.get('mode'):
        mode = presence.get('mode', 'solo')
        agent = presence.get('current_agent', 'unknown')
        mode_icon = "👥" if mode == "collaborative" else "👤"
        print(f"  {mode_icon} Presence: {mode.title()}")
        if mode == "collaborative":
            others = presence.get('other_agents', [])
            if others:
                print(f"     Working with: {', '.join(others[:3])}")
        print("")

    # Cross-Scale Visibility
    cross_scale = ctx.get('cross_scale', {})
    revolt = cross_scale.get('revolt', [])
    remember = cross_scale.get('remember', [])
    if revolt or remember:
        fast = cross_scale.get('fast_cycle', {})
        slow = cross_scale.get('slow_cycle', {})
        print("  Cross-Scale:")
        print(f"    Fast: {fast.get('active_features', 0)} features, {fast.get('active_tasks', 0)} tasks")
        print(f"    Slow: {slow.get('patterns', 0)} patterns, {slow.get('releases', 0)} releases")
        if revolt:
            r = revolt[0]
            print(f"    ↑ Revolt: {r.get('pattern_name', '')[:30]} ← {r.get('source_count', 0)} learnings")
        if remember:
            r = remember[0]
            print(f"    ↓ Remember: {r.get('feature_name', '')[:30]} ← {r.get('pattern_count', 0)} patterns")
        print("")

    # Coordination Signals
    coordination = ctx.get('coordination', {})
    signals = coordination.get('signals', [])
    if signals:
        print("  Coordination Signals:")
        for s in signals[:3]:
            signal_icon = "📡" if s.get('type') == 'collaboration' else "🎯" if s.get('type') == 'convergence' else "⚠️"
            print(f"    {signal_icon} {s.get('message', '')}")
        print("")

    # Sync status
    sync_status = ctx.get('sync_status')
    pulled = ctx.get('pulled_count', 0)
    if sync_status == "connected":
        sync_icon = "☁️"
        if pulled > 0:
            print(f"  {sync_icon} Cloud: synced ({pulled} pulled)")
        else:
            print(f"  {sync_icon} Cloud: connected")
        print("")
    elif sync_status == "error":
        print("  ⚠ Cloud: sync error")
        print("")

    print("  ─────────────────────────────────────────────────────────")
    print("  Commands: just inquire · just create · just search")
    print("")


def handoffs():
    """
    Show recent handoff notes from finalized foci.

    These are gifts left behind by previous agents - cairns on the trail.
    When someone finishes work, they may leave a note for whoever comes next.
    """
    from chora_store.focus import FocusManager

    repo = EntityRepository()
    fm = FocusManager(repo)
    recent = fm.get_recent_handoffs(limit=5, days=7)

    print("")
    print("  ╭──────────────────────────────────────────────────────────╮")
    print("  │   🔥 Handoffs · Gifts from those who came before         │")
    print("  ╰──────────────────────────────────────────────────────────╯")
    print("")

    if not recent:
        print("  No handoff notes in the last 7 days.")
        print("")
        print("  When you finalize a focus with a handoff_note,")
        print("  it will appear here for the next dweller.")
        print("")
        return

    for handoff in recent:
        agent = handoff.get('agent', 'unknown')[:15]
        target = handoff.get('target', '')[:60]
        name = handoff.get('name', '')
        felt = handoff.get('felt_quality', '')
        care = handoff.get('care_at_center', '')
        note = handoff.get('handoff_note', '')
        when = handoff.get('finalized_at', '')[:10] if handoff.get('finalized_at') else ''

        # Header: who, when, what target
        print(f"  ┌─ [{agent}] → {target}")
        if when:
            print(f"  │  {when}")

        # Name if present
        if name:
            print(f"  │  \"{name}\"")

        # Aliveness fields
        if felt:
            print(f"  │  ✨ {felt}")
        if care:
            print(f"  │  ♡ {care}")

        # The handoff note itself - the gift
        if note:
            print(f"  │")
            print(f"  │  To whoever comes next:")
            # Wrap long notes nicely
            lines = note.split('\n')
            for line in lines:
                # Wrap at ~60 chars
                while len(line) > 60:
                    print(f"  │    {line[:60]}")
                    line = line[60:]
                print(f"  │    {line}")

        print(f"  └─────────────────────────────────────────────────────────")
        print("")

    print(f"  Showing {len(recent)} handoff(s) from the last 7 days.")
    print("")


def hello():
    """Create welcome inquiry if not exists."""
    factory = EntityFactory()
    repo = EntityRepository()

    existing = repo.read('inquiry-welcome-to-chora')
    if existing:
        print("")
        print("  You've already been welcomed!")
        print("  Your welcome inquiry: inquiry-welcome-to-chora")
        print("")
        print("  Try: just orient")
        print("")
    else:
        inquiry = factory.create('inquiry', 'Welcome to Chora',
            description='Your first inquiry in this chora.',
            core_concern='What would I like to explore or build here?',
            terrain={
                'adjacent_concerns': [
                    'Getting oriented in the system',
                    'Understanding the physics (6 nouns, 6 verbs)',
                    'Finding my first spark'
                ],
                'unknowns': [
                    'What matters to me right now?',
                    'What would be delightful to create?'
                ]
            },
            dialogue_log=[]
        )
        print("")
        print("  ╭──────────────────────────────────────────────────────────╮")
        print("  │                                                          │")
        print("  │   🌱 Welcome to your chora!                              │")
        print("  │                                                          │")
        print("  │   Your first inquiry has been created:                   │")
        print(f"  │     {inquiry.id}")
        print("  │                                                          │")
        print("  │   This is a space for exploration.                       │")
        print("  │   When you're ready, this inquiry can become             │")
        print("  │   a feature, then tasks, then reality.                   │")
        print("  │                                                          │")
        print("  │   The ground is solid. You can build here.               │")
        print("  │                                                          │")
        print("  ╰──────────────────────────────────────────────────────────╯")
        print("")


def inquire(title: str):
    """Create a new inquiry."""
    factory = EntityFactory()
    inquiry = factory.create('inquiry', title,
        core_concern='What is the essential question here?',
        terrain={'adjacent_concerns': [], 'unknowns': []},
        dialogue_log=[]
    )
    print(f"Created: {inquiry.id}")
    print(f"Status: {inquiry.status}")


def create(entity_type: str, title: str):
    """Create an entity of any type."""
    factory = EntityFactory()
    entity = factory.create(entity_type, title)
    print(f"Created: {entity.id}")
    print(f"Type: {entity.type}")
    print(f"Status: {entity.status}")


def search(query: str):
    """Search for entities."""
    repo = EntityRepository()
    results = repo.search(query)
    if results:
        print(f"Found {len(results)} results:")
        for e in results:
            name = e.data.get('name', e.id)
            print(f"  {e.id} ({e.status}) - {name}")
    else:
        print("No results found.")


def list_entities(entity_type: str = None):
    """List entities by type."""
    repo = EntityRepository()
    entities = repo.list(entity_type=entity_type if entity_type else None, limit=50)
    if entities:
        for e in entities:
            print(f"{e.id} ({e.status})")
    else:
        print("No entities found.")


def invoke(tool_id: str, **kwargs):
    """
    Invoke a dynamic tool by ID with optional arguments.

    Bridges CLI to MCP tool infrastructure for ergonomic tool access.
    Physics: interfaces field governs exposure - only tools with 'cli' in interfaces
    can be invoked via CLI.
    """
    from .repository import EntityRepository
    from .mcp import tool_invoke

    # Check if tool exists and is CLI-exposed
    repo = EntityRepository()
    tool = repo.read(tool_id)
    if tool:
        interfaces = tool.data.get('interfaces', [])
        if 'cli' not in interfaces:
            print(f"Tool '{tool_id}' is not exposed via CLI (interfaces: {interfaces})")
            return

    result = tool_invoke(tool_id, **kwargs)

    # If tool entity not found, try MCP functions directly
    if result.startswith("Tool not found:"):
        # Use dynamic mapping (built from MCP_INFRASTRUCTURE_TOOLS + introspection)
        mcp_functions = _get_mcp_functions()
        func_name = mcp_functions.get(tool_id)
        if func_name:
            try:
                from . import mcp
                func = getattr(mcp, func_name, None)
                if func:
                    result = func(**kwargs)
            except Exception as e:
                result = f"Error invoking {tool_id}: {e}"

    print(result)


def kernel_command(subcommand: str, args: list):
    """
    Kernel versioning commands.

    Subcommands:
        status  - Show current kernel version info (default)
        verify  - Verify hash matches content
        bump    - Bump version (requires change_type: major|minor|patch)
    """
    import hashlib
    import subprocess
    import yaml

    # Find kernel path
    kernel_paths = [
        Path("packages/chora-kernel"),
        Path("../chora-kernel"),
        Path.home() / ".chora" / "kernel",
    ]
    kernel_path = None
    for p in kernel_paths:
        if (p / "kernel.yaml").exists():
            kernel_path = p
            break

    if not kernel_path:
        print("Error: kernel.yaml not found")
        sys.exit(1)

    manifest_path = kernel_path / "kernel.yaml"

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    kernel = manifest.get("kernel", {})

    if subcommand == "status":
        print("")
        print("  ╭──────────────────────────────────────────────────────────╮")
        print("  │  KERNEL · Version Status                                 │")
        print("  ╰──────────────────────────────────────────────────────────╯")
        print("")
        print(f"  Name: {kernel.get('name', 'unknown')}")
        print(f"  Version: {kernel.get('version', 'unknown')}")
        print(f"  Hash: {kernel.get('hash', 'unknown')}")
        print(f"  Generation: {kernel.get('generation', 0)}")
        print("")

        # Show lineage
        lineage = manifest.get("lineage", [])
        if lineage:
            print("  ┌─ Lineage ─────────────────────────────────────────────────┐")
            for entry in lineage[-5:]:  # Last 5 entries
                gen = entry.get("generation", "?")
                date = entry.get("date", "?")
                change = entry.get("version_change", "?")
                desc = entry.get("description", "")[:40]
                print(f"  │ Gen {gen}: {date} ({change}) {desc}")
            print("  └──────────────────────────────────────────────────────────┘")
        print("")

    elif subcommand == "verify":
        # Calculate current hash (excluding kernel.yaml itself to avoid self-reference)
        result = subprocess.run(
            f'find {kernel_path} -name "*.yaml" -type f ! -name "kernel.yaml" | sort | xargs cat | shasum -a 256',
            shell=True,
            capture_output=True,
            text=True
        )
        current_hash = f"sha256:{result.stdout.strip()[:16]}"
        stored_hash = kernel.get("hash", "")

        print("")
        print(f"  Stored hash:  {stored_hash}")
        print(f"  Current hash: {current_hash}")
        print("")

        if stored_hash == current_hash:
            print("  ✓ Hash verified - kernel is coherent")
        else:
            print("  ✗ Hash mismatch - kernel has drifted")
            print("    Run 'kernel bump' to update version")
        print("")

    elif subcommand == "bump":
        if not args:
            print("Usage: kernel bump <major|minor|patch> <description>")
            sys.exit(1)

        change_type = args[0]
        description = " ".join(args[1:]) if len(args) > 1 else "Version bump"

        if change_type not in ("major", "minor", "patch"):
            print(f"Invalid change type: {change_type}")
            print("Must be: major, minor, or patch")
            sys.exit(1)

        # Parse current version
        current = kernel.get("version", "0.0.0")
        parts = current.split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        old_version = current
        if change_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif change_type == "minor":
            minor += 1
            patch = 0
        else:
            patch += 1

        new_version = f"{major}.{minor}.{patch}"

        # Calculate new hash (excluding kernel.yaml itself to avoid self-reference)
        result = subprocess.run(
            f'find {kernel_path} -name "*.yaml" -type f ! -name "kernel.yaml" | sort | xargs cat | shasum -a 256',
            shell=True,
            capture_output=True,
            text=True
        )
        new_hash = f"sha256:{result.stdout.strip()[:16]}"

        # Update generation
        new_generation = kernel.get("generation", 0) + 1

        # Update manifest
        manifest["kernel"]["version"] = new_version
        manifest["kernel"]["hash"] = new_hash
        manifest["kernel"]["generation"] = new_generation

        # Add lineage entry
        if "lineage" not in manifest:
            manifest["lineage"] = []

        manifest["lineage"].append({
            "generation": new_generation,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "version_change": f"{old_version} → {new_version}",
            "change_type": change_type,
            "description": description,
        })

        # Write back
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print("")
        print(f"  ✓ Kernel version bumped: {old_version} → {new_version}")
        print(f"  ✓ Hash updated: {new_hash}")
        print(f"  ✓ Generation: {new_generation}")
        print("")

    else:
        print(f"Unknown kernel subcommand: {subcommand}")
        print("Available: status, verify, bump")
        sys.exit(1)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m chora_store.cli <command> [args...]")
        print("Commands: orient, hello, inquire, create, search, list, invoke")
        sys.exit(1)

    command = sys.argv[1]

    if command == "orient":
        orient()
    elif command == "hello":
        hello()
    elif command == "handoffs":
        handoffs()
    elif command == "inquire":
        if len(sys.argv) < 3:
            print("Usage: python -m chora_store.cli inquire <title>")
            sys.exit(1)
        inquire(sys.argv[2])
    elif command == "create":
        if len(sys.argv) < 4:
            print("Usage: python -m chora_store.cli create <type> <title>")
            sys.exit(1)
        create(sys.argv[2], sys.argv[3])
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m chora_store.cli search <query>")
            sys.exit(1)
        search(sys.argv[2])
    elif command == "list":
        entity_type = sys.argv[2] if len(sys.argv) > 2 else None
        list_entities(entity_type)
    elif command == "invoke":
        if len(sys.argv) < 3:
            print("Usage: python -m chora_store.cli invoke <tool_id> [key=value ...]")
            sys.exit(1)
        tool_id = sys.argv[2]
        # Parse key=value arguments (filter out empty values)
        kwargs = {}
        for arg in sys.argv[3:]:
            if '=' in arg:
                k, v = arg.split('=', 1)
                if v:  # Only include non-empty values
                    kwargs[k] = v
        invoke(tool_id, **kwargs)
    elif command == "capabilities":
        capabilities()
    elif command == "kernel":
        subcommand = sys.argv[2] if len(sys.argv) > 2 else "status"
        kernel_command(subcommand, sys.argv[3:])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


def capabilities():
    """
    List all capabilities - tool entities + MCP infrastructure functions.

    Unified view of everything the system can do.
    """
    from .mcp import get_all_capabilities

    caps = get_all_capabilities()

    print("")
    print("  ╭──────────────────────────────────────────────────────────╮")
    print("  │  CAPABILITIES · Unified Tool Registry                    │")
    print("  ╰──────────────────────────────────────────────────────────╯")
    print("")
    print(f"  Tool Entities: {caps['entity_count']}")
    print(f"  MCP Functions: {caps['infra_count']}")
    print(f"  Total: {caps['entity_count'] + caps['infra_count']}")
    print("")
    print("  ┌─ Tool Entities (dynamic, hot-reloadable) ─────────────────┐")
    for line in caps['entities'][:15]:
        # Truncate long lines
        display = line[:60] + "..." if len(line) > 60 else line
        print(f"  │ {display}")
    if len(caps['entities']) > 15:
        print(f"  │ ... and {len(caps['entities']) - 15} more")
    print("  └──────────────────────────────────────────────────────────┘")
    print("")
    print("  ┌─ MCP Functions (infrastructure) ─────────────────────────┐")
    for line in caps['infrastructure']:
        display = line[:60] + "..." if len(line) > 60 else line
        print(f"  │ {display}")
    print("  └──────────────────────────────────────────────────────────┘")
    print("")
    print("  Invoke: just tool <id>  |  just capabilities  |  just emerging")
    print("")


if __name__ == "__main__":
    main()
