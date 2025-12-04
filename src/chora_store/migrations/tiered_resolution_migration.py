"""
Tiered Resolution Migration - Add epigenetics tracking to existing tools.

This migration:
1. Adds _epigenetics: ["pattern-tiered-resolution"] to existing tools
2. Adds tier_policy field if missing
3. Enables hooks to fire for these tools

Run with:
    PYTHONPATH=packages/chora-store/src python3 -m chora_store.migrations.tiered_resolution_migration

Options:
    --dry-run    Show what would change without modifying
    --apply      Actually perform the migration
"""

import sys
from datetime import datetime
from typing import Dict, List

# The pattern we're applying to tools
PATTERN_ID = "pattern-tiered-resolution"

# Default tier policy for tools
DEFAULT_TIER_POLICY = {
    "default_tier": "workflow",
    "confidence_threshold": 0.7,
}


def migrate_tool(repo, tool, dry_run: bool = True) -> bool:
    """Add epigenetics tracking to a single tool."""
    tool_id = tool.id
    data = dict(tool.data)
    changes = []

    # Add pattern to _epigenetics if not present
    epigenetics = data.get("_epigenetics", [])
    if PATTERN_ID not in epigenetics:
        changes.append("_epigenetics")

    # Add tier_policy if not present
    if "tier_policy" not in data:
        changes.append("tier_policy")

    if not changes:
        print(f"  SKIP (already migrated): {tool_id}")
        return False

    if dry_run:
        print(f"  WOULD ADD: {tool_id} [{', '.join(changes)}]")
        return True

    # Re-read to get current version and data
    current = repo.read(tool_id)
    if not current:
        print(f"  ERROR: {tool_id} disappeared during migration")
        return False

    # Build updated data from current
    data = dict(current.data)

    # Add pattern to _epigenetics
    epigenetics = data.get("_epigenetics", [])
    if PATTERN_ID not in epigenetics:
        epigenetics = list(epigenetics)
        epigenetics.append(PATTERN_ID)
        data["_epigenetics"] = epigenetics

    # Add tier_policy
    if "tier_policy" not in data:
        data["tier_policy"] = DEFAULT_TIER_POLICY

    data["_migration_tiered_resolution"] = datetime.now().isoformat()

    from chora_store.models import Entity

    # repo.update() auto-increments version, so pass current version
    updated_tool = Entity(
        id=tool_id,
        type='tool',
        status=current.status,
        data=data,
        created_at=current.created_at,
        version=current.version,
    )

    repo.update(updated_tool)
    print(f"  DONE: {tool_id} [{', '.join(changes)}]")
    return True


def run_migration(dry_run: bool = True):
    """Run the full migration."""
    from chora_store.repository import EntityRepository
    from chora_store.factory import EntityFactory

    print("=" * 60)
    print("Tiered Resolution Migration")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLYING CHANGES'}")
    print()

    repo = EntityRepository()

    # Ensure pattern exists in SQLite
    pattern = repo.read(PATTERN_ID)
    if not pattern:
        print(f"Bootstrapping {PATTERN_ID} into SQLite...")
        factory = EntityFactory(repository=repo)
        factory.bootstrap_patterns_from_kernel("epigenetic")
        pattern = repo.read(PATTERN_ID)
        if pattern:
            print(f"  Pattern loaded: {pattern.id}")
        else:
            print(f"  WARNING: Could not load pattern {PATTERN_ID}")

    print()
    print("Migrating tools...")

    tools = repo.list(entity_type='tool', limit=200)
    migrated = 0
    skipped = 0

    for tool in sorted(tools, key=lambda x: x.id):
        if migrate_tool(repo, tool, dry_run):
            migrated += 1
        else:
            skipped += 1

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")

    if dry_run and migrated > 0:
        print()
        print("To apply changes, run with --apply")


if __name__ == '__main__':
    if '--apply' in sys.argv:
        run_migration(dry_run=False)
    else:
        run_migration(dry_run=True)
        if '--dry-run' not in sys.argv:
            print()
            print("(This was a dry run. Use --apply to actually migrate.)")
