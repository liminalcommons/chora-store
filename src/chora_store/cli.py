"""
CLI commands for chora-store.

These are extracted from justfile heredocs for cross-platform compatibility.
"""

import sys
from .factory import EntityFactory
from .repository import EntityRepository
from .vitality import VitalitySensor


def get_workspace_context(repo):
    """Get workspace context for orientation using vitality sensing."""
    # Use vitality sensor for real metrics
    sensor = VitalitySensor(repo)
    vitality = sensor.summary()

    # Count entities by type
    all_entities = repo.list(limit=1000)
    counts = {}
    active_inquiries = []
    active_features = []
    active_tasks = []
    blocked = []
    sample_learnings = []  # Sample of undigested learnings for semantic surface
    recent_work = []  # Recently touched work items for session continuity

    for e in all_entities:
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
    work_types = {'inquiry', 'feature', 'task', 'learning'}
    work_items = [e for e in all_entities if e.type in work_types]
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
    current_focus = None
    active_inquiry_entities = [e for e in all_entities if e.type == 'inquiry' and e.status == 'active']
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


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m chora_store.cli <command> [args...]")
        print("Commands: orient, hello, inquire, create, search, list")
        sys.exit(1)

    command = sys.argv[1]

    if command == "orient":
        orient()
    elif command == "hello":
        hello()
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
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
