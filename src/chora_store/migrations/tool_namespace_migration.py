"""
Tool Namespace Migration - Migrate tool IDs to namespaced format.

Pattern: tool-{namespace}-{action}

Run with:
    PYTHONPATH=packages/chora-store/src python3 -m chora_store.migrations.tool_namespace_migration

Options:
    --dry-run    Show what would change without modifying
    --apply      Actually perform the migration
"""

import sys
from datetime import datetime
from typing import Dict, Optional

# Known namespaces for detection
KNOWN_NAMESPACES = {'core', 'learning', 'pattern', 'transform', 'release',
                    'feature', 'focus', 'inquiry', 'meta', 'governance', 'trace'}

# Complete mapping from old ID to new namespaced ID
NAMESPACE_MAP: Dict[str, str] = {
    # ═══════════════════════════════════════════════════════════════════════════
    # CORE - Essential cognitive cycle operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-orient": "tool-core-orient",
    "tool-list-entities": "tool-core-list",
    "tool-get-entity": "tool-core-get",
    "tool-create-entity": "tool-core-create",
    "tool-update-entity": "tool-core-update",
    "tool-list-tools": "tool-core-list-tools",

    # ═══════════════════════════════════════════════════════════════════════════
    # FOCUS - Attention and constellation operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-constellation": "tool-focus-constellation",
    "tool-finalize": "tool-focus-finalize",

    # ═══════════════════════════════════════════════════════════════════════════
    # LEARNING - Learning metabolism operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-distill-learnings": "tool-learning-distill",
    "tool-synthesize-learnings": "tool-learning-synthesize",
    "tool-learning-generator": "tool-learning-generate",
    "tool-propose-synthesis": "tool-learning-propose-synthesis",
    "tool-digest-batch": "tool-learning-digest-batch",
    "tool-reclaim": "tool-learning-reclaim",

    # ═══════════════════════════════════════════════════════════════════════════
    # INQUIRY - Inquiry-specific operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-distill-inquiries": "tool-inquiry-distill",
    "tool-inquiry-cluster-analyzer": "tool-inquiry-cluster-analyzer",

    # ═══════════════════════════════════════════════════════════════════════════
    # PATTERN - Pattern lifecycle operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-pattern-evaluate": "tool-pattern-evaluate",
    "tool-suggest-patterns": "tool-pattern-suggest",
    "tool-pattern-audit": "tool-pattern-audit",
    "tool-pattern-auto-synthesizer": "tool-pattern-auto-synthesize",
    "tool-propose-pattern-from-cluster": "tool-pattern-propose-from-cluster",

    # ═══════════════════════════════════════════════════════════════════════════
    # TRANSFORM - Entity transformation operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-crystallize": "tool-transform-crystallize",
    "tool-engage": "tool-transform-engage",
    "tool-bulk-distill-by-domain": "tool-transform-distill-bulk",
    "tool-unsubsume": "tool-transform-unsubsume",
    "tool-unsubsume-all": "tool-transform-unsubsume-all",
    "tool-apply-distillation": "tool-transform-apply-distillation",

    # ═══════════════════════════════════════════════════════════════════════════
    # RELEASE - Release coherence operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-wobble-test": "tool-release-wobble-test",
    "tool-pre-release-check": "tool-release-pre-check",
    "tool-dimension-checklist": "tool-release-dimension",
    "tool-dimension-prompts": "tool-release-dimension-prompts",
    "tool-generate-story": "tool-release-generate-story",
    "tool-story-status": "tool-release-story-status",
    "tool-coherence-check": "tool-release-coherence-check",

    # ═══════════════════════════════════════════════════════════════════════════
    # FEATURE - Feature and behavior operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-scan-features": "tool-feature-scan",
    "tool-scan-code": "tool-feature-scan-code",
    "tool-behavior-definer": "tool-feature-define-behavior",
    "tool-extract-behaviors": "tool-feature-extract-behaviors",
    "tool-generate-behaviors-from-tests": "tool-feature-generate-behaviors",
    "tool-find-dark-behaviors": "tool-feature-find-dark-behaviors",
    "tool-missing-behavior-generator": "tool-feature-missing-behavior-generator",
    "tool-coverage-report": "tool-feature-coverage-report",
    "tool-link-test": "tool-feature-link-test",
    "tool-link-all-tests": "tool-feature-link-all-tests",

    # ═══════════════════════════════════════════════════════════════════════════
    # META - Autopoietic loop and tool meta-operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-induction": "tool-meta-induction",
    "tool-pathway-catalog": "tool-meta-pathway-catalog",
    "tool-notice-emerging-tools": "tool-meta-notice-emerging",
    "tool-discover": "tool-meta-discover",
    "tool-invoke-tool": "tool-meta-invoke",
    "tool-tool-factory": "tool-meta-tool-factory",
    "tool-capability-gap-filler": "tool-meta-capability-gap-filler",
    "tool-summarize": "tool-meta-summarize",
    "tool-suggest-next-action": "tool-meta-suggest-next-action",
    "tool-circle-boundary-analyzer": "tool-meta-circle-boundary-analyzer",
    "tool-leverage-propagation-scanner": "tool-meta-leverage-propagation-scanner",

    # ═══════════════════════════════════════════════════════════════════════════
    # GOVERNANCE - Quality and validation operations
    # ═══════════════════════════════════════════════════════════════════════════
    "tool-validate": "tool-governance-validate",
}

# Tools to skip (test/generated tools that should be reviewed separately)
SKIP_TOOLS = {
    "tool-focus-session-2025-12-01-victor",
    "tool-focus-test-agent-variables-053246227651",
    "tool-simple-greeter-generator",
    "tool-timestamped-greeter-1764731789",
}


def is_already_namespaced(tool_id: str) -> bool:
    """Check if tool ID already uses namespace format."""
    if not tool_id.startswith('tool-'):
        return False
    parts = tool_id[5:].split('-', 1)
    return len(parts) >= 2 and parts[0] in KNOWN_NAMESPACES


def migrate_tool(repo, old_id: str, new_id: str, dry_run: bool = True) -> bool:
    """Migrate a single tool from old ID to new ID."""
    from chora_store.models import Entity

    tool = repo.read(old_id)
    if not tool:
        print(f"  SKIP: {old_id} not found")
        return False

    if repo.read(new_id):
        print(f"  SKIP: {new_id} already exists")
        return False

    if dry_run:
        print(f"  WOULD: {old_id} → {new_id}")
        return True

    # Create new tool with namespaced ID
    new_data = dict(tool.data)
    new_data['_migrated_from'] = old_id
    new_data['_migrated_at'] = datetime.now().isoformat()

    new_tool = Entity(
        id=new_id,
        type='tool',
        status=tool.status,
        data=new_data,
        created_at=tool.created_at,
        version=tool.version,
    )

    # Delete old, create new (ID is primary key)
    repo.delete(old_id)
    repo.create(new_tool)

    print(f"  DONE: {old_id} → {new_id}")
    return True


def run_migration(dry_run: bool = True):
    """Run the full migration."""
    from chora_store.repository import EntityRepository

    print("=" * 60)
    print("Tool Namespace Migration")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLYING CHANGES'}")
    print()

    repo = EntityRepository()
    tools = repo.list(entity_type='tool', limit=200)

    migrated = 0
    skipped = 0
    already_namespaced = 0
    unmapped = []

    for tool in sorted(tools, key=lambda x: x.id):
        old_id = tool.id

        # Skip test/generated tools
        if old_id in SKIP_TOOLS:
            print(f"  SKIP (test): {old_id}")
            skipped += 1
            continue

        # Skip already namespaced
        if is_already_namespaced(old_id):
            print(f"  SKIP (namespaced): {old_id}")
            already_namespaced += 1
            continue

        # Look up mapping
        new_id = NAMESPACE_MAP.get(old_id)
        if not new_id:
            unmapped.append(old_id)
            continue

        if migrate_tool(repo, old_id, new_id, dry_run):
            migrated += 1

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Migrated: {migrated}")
    print(f"  Already namespaced: {already_namespaced}")
    print(f"  Skipped (test): {skipped}")
    print(f"  Unmapped: {len(unmapped)}")

    if unmapped:
        print()
        print("Unmapped tools (need to add to NAMESPACE_MAP):")
        for tool_id in unmapped:
            print(f"    - {tool_id}")

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
