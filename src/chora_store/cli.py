"""
CLI commands for chora-store.

These are extracted from justfile heredocs for cross-platform compatibility.
"""

import sys
from .factory import EntityFactory
from .repository import EntityRepository


def get_workspace_context(repo):
    """Get workspace context for orientation."""
    # Count entities by type
    all_entities = repo.list(limit=1000)
    counts = {}
    active_inquiries = []
    active_features = []
    active_tasks = []
    blocked = []

    for e in all_entities:
        counts[e.type] = counts.get(e.type, 0) + 1

        # Track active work
        if e.type == 'inquiry' and e.status == 'active':
            active_inquiries.append({'id': e.id, 'status': e.status})
        elif e.type == 'feature' and e.status in ('design', 'prototype', 'dogfood'):
            active_features.append({'id': e.id, 'status': e.status})
        elif e.type == 'task' and e.status == 'active':
            active_tasks.append({'id': e.id, 'status': e.status})

        # Track blocked
        if e.status == 'blocked':
            blocked.append({'id': e.id})

    # Determine phase
    if active_inquiries:
        phase = {'name': 'exploring', 'description': 'Active inquiries in progress', 'suggestion': 'Continue dialogue or reify to feature'}
    elif active_features:
        phase = {'name': 'building', 'description': 'Features in development', 'suggestion': 'Decompose to tasks or complete features'}
    elif active_tasks:
        phase = {'name': 'executing', 'description': 'Tasks in progress', 'suggestion': 'Complete tasks'}
    else:
        phase = {'name': 'idle', 'description': 'No active work', 'suggestion': 'Start with: just inquire "Your idea"'}

    # Determine season
    total = len(all_entities)
    season = 'construction' if total < 50 else 'harvest'
    integrity = 1.0 if total > 0 else 0.0

    return {
        'season': season,
        'integrity_score': integrity,
        'phase': phase,
        'active_inquiries': active_inquiries,
        'active_features': active_features,
        'active_tasks': active_tasks,
        'blocked': blocked,
        'counts': counts,
    }


def orient():
    """Show current workspace state."""
    repo = EntityRepository()
    ctx = get_workspace_context(repo)

    print("")
    print("  ╭──────────────────────────────────────────────────────────╮")
    print("  │  ORIENT · Situational Awareness                          │")
    print("  ╰──────────────────────────────────────────────────────────╯")
    print("")

    # Season and integrity
    season = ctx.get('season', 'unknown')
    integrity = ctx.get('integrity_score', 0)
    season_emoji = "🌱" if season == "construction" else "🍂"
    print(f"  Season: {season_emoji} {season.title()} (integrity: {integrity:.0%})")
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
    features = ctx.get('active_features', [])
    tasks = ctx.get('active_tasks', [])
    blocked = ctx.get('blocked', [])

    if inquiries or features or tasks:
        print("  Active Work:")
        for i in inquiries:
            print(f"    💭 {i['id']}")
        for f in features:
            print(f"    📦 {f['id']} ({f['status']})")
        for t in tasks:
            print(f"    ⚡ {t['id']}")
        print("")

    if blocked:
        print("  ⚠ Blocked:")
        for b in blocked:
            print(f"    {b['id']}")
        print("")

    # Counts
    counts = ctx.get('counts', {})
    if counts:
        print("  Entities:")
        for t, c in sorted(counts.items()):
            print(f"    {t}: {c}")
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
