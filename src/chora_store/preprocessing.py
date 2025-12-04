"""
Entity Preprocessing - Ensure entities have well-formed fields for distillation.

This module provides tools to:
1. Audit entity field completeness
2. Enrich entities with missing fields (via LLM or heuristics)
3. Classify entities into domains
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import logging
import re

from .models import Entity

logger = logging.getLogger(__name__)

# Domain classification keywords
DOMAIN_KEYWORDS = {
    'metabolic': ['digest', 'induct', 'metabol', 'learning', 'synthesis', 'pattern'],
    'epigenetic': ['epigenet', 'mutation', 'schema', 'evolution', 'fitness', 'hook'],
    'generative': ['generat', 'llm', 'tool', 'handler', 'inference', 'prompt'],
    'stigmergic': ['stigmer', 'mark', 'signal', 'coordinat', 'focus', 'sync'],
    'governance': ['govern', 'status', 'lifecycle', 'valid', 'quality', 'gate'],
    'architecture': ['architect', 'design', 'structure', 'layer', 'interface'],
    'ontology': ['ontolog', 'entity', 'type', 'what is', 'nature of'],
    'autopoiesis': ['autopoie', 'self-', 'emergen', 'bootstrap', 'crystal'],
}


@dataclass
class FieldIssue:
    """A field quality issue on an entity."""
    entity_id: str
    entity_type: str
    field: str
    issue: str  # 'missing', 'empty', 'too_short'
    current_value: Optional[str] = None
    suggested_value: Optional[str] = None


@dataclass
class AuditResult:
    """Result of auditing entity quality."""
    entity_type: str
    total_count: int
    issues: List[FieldIssue]

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def health_pct(self) -> float:
        if self.total_count == 0:
            return 100.0
        return 100.0 * (1 - len(self.issues) / self.total_count)


def audit_entity(entity: Entity) -> List[FieldIssue]:
    """
    Audit a single entity for field quality issues.

    Returns list of issues found.
    """
    issues = []

    # Type-specific primary field
    primary_fields = {
        'inquiry': 'core_concern',
        'learning': 'insight',
        'feature': 'description',
        'pattern': 'description',
    }

    primary_field = primary_fields.get(entity.type)
    if primary_field:
        value = entity.data.get(primary_field, '')
        if not value:
            issues.append(FieldIssue(
                entity_id=entity.id,
                entity_type=entity.type,
                field=primary_field,
                issue='missing',
            ))
        elif isinstance(value, str) and len(value.strip()) < 20:
            issues.append(FieldIssue(
                entity_id=entity.id,
                entity_type=entity.type,
                field=primary_field,
                issue='too_short',
                current_value=value,
            ))

    # Domain field
    domain = entity.data.get('domain', '')
    if not domain:
        # Try to infer domain from content
        suggested = infer_domain(entity)
        issues.append(FieldIssue(
            entity_id=entity.id,
            entity_type=entity.type,
            field='domain',
            issue='missing',
            suggested_value=suggested,
        ))

    return issues


def audit_entities(
    repository: "EntityRepository",
    entity_type: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, AuditResult]:
    """
    Audit entities for field quality.

    Args:
        repository: EntityRepository instance
        entity_type: Specific type to audit (None = all)
        limit: Max entities per type

    Returns:
        Dict of entity_type -> AuditResult
    """
    types_to_audit = [entity_type] if entity_type else ['inquiry', 'learning', 'feature', 'pattern']
    results = {}

    for etype in types_to_audit:
        entities = repository.list(entity_type=etype, limit=limit)
        active = [e for e in entities if e.status != 'subsumed']

        all_issues = []
        for entity in active:
            all_issues.extend(audit_entity(entity))

        results[etype] = AuditResult(
            entity_type=etype,
            total_count=len(active),
            issues=all_issues,
        )

    return results


def infer_domain(entity: Entity) -> Optional[str]:
    """
    Infer domain from entity content using keyword matching.

    Returns the best-matching domain or None.
    """
    # Gather all text content
    text_parts = [
        entity.data.get('name', ''),
        entity.data.get('description', ''),
        entity.data.get('insight', ''),
        entity.data.get('core_concern', ''),
        entity.id,
    ]
    text = ' '.join(str(p).lower() for p in text_parts if p)

    # Score each domain
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score

    if not scores:
        return 'general'

    # Return highest scoring domain
    return max(scores, key=scores.get)


def extract_core_concern(entity: Entity) -> Optional[str]:
    """
    Extract a core_concern from inquiry description/name.

    Uses heuristics to find the central question.
    """
    if entity.type != 'inquiry':
        return None

    name = entity.data.get('name', '')
    description = entity.data.get('description', '')

    # If description exists, try to extract first question or statement
    if description:
        # Look for question patterns
        lines = description.split('\n')
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line.endswith('?'):
                return line
            if line.lower().startswith(('how ', 'what ', 'when ', 'why ', 'should ', 'can ', 'is ')):
                return line + ('?' if not line.endswith('?') else '')

        # Fall back to first non-empty line
        for line in lines:
            line = line.strip()
            if len(line) > 20:
                return line[:200] + ('...' if len(line) > 200 else '')

    # Fall back to name as question
    if name:
        # Convert name to question form
        if not name.endswith('?'):
            if name.lower().startswith(('how', 'what', 'when', 'why', 'should', 'can', 'is')):
                return name + '?'
            else:
                return f"What about {name.lower()}?"
        return name

    return None


def extract_description(entity: Entity) -> Optional[str]:
    """
    Extract description from entity name/other fields for features/patterns.
    """
    if entity.type not in ('feature', 'pattern'):
        return None

    name = entity.data.get('name', '')

    # For patterns, try to create a description from the name
    if entity.type == 'pattern':
        if name:
            return f"Pattern: {name}"

    # For features, use name as base
    if entity.type == 'feature':
        if name:
            return f"Feature for {name.lower()}"

    return None


def enrich_entity(
    entity: Entity,
    issues: List[FieldIssue],
    apply: bool = False,
) -> Tuple[Entity, List[str]]:
    """
    Enrich entity with missing/inferred fields.

    Args:
        entity: Entity to enrich
        issues: List of issues from audit
        apply: If True, modify entity in place

    Returns:
        Tuple of (enriched entity, list of changes made)
    """
    changes = []
    enriched = entity if apply else entity.copy()

    for issue in issues:
        if issue.entity_id != entity.id:
            continue

        if issue.field == 'domain' and issue.issue == 'missing':
            domain = issue.suggested_value or infer_domain(entity)
            if domain:
                enriched.data['domain'] = domain
                changes.append(f"Set domain to '{domain}'")

        elif issue.field == 'core_concern' and issue.issue in ('missing', 'too_short'):
            core = extract_core_concern(entity)
            if core:
                enriched.data['core_concern'] = core
                changes.append(f"Extracted core_concern: '{core[:50]}...'")

        elif issue.field == 'description' and issue.issue in ('missing', 'too_short'):
            desc = extract_description(entity)
            if desc:
                enriched.data['description'] = desc
                changes.append(f"Generated description: '{desc[:50]}...'")

    return enriched, changes


def preprocess_batch(
    repository: "EntityRepository",
    entity_type: str,
    dry_run: bool = True,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Preprocess a batch of entities to improve field quality.

    Args:
        repository: EntityRepository instance
        entity_type: Type to preprocess
        dry_run: If True, don't save changes
        limit: Max entities to process

    Returns:
        Summary of preprocessing results
    """
    # Audit first
    audit = audit_entities(repository, entity_type, limit)
    result = audit.get(entity_type)

    if not result or not result.issues:
        return {
            'status': 'no_issues',
            'entity_type': entity_type,
            'total': result.total_count if result else 0,
            'message': 'No field quality issues found',
        }

    # Group issues by entity
    issues_by_entity = {}
    for issue in result.issues:
        if issue.entity_id not in issues_by_entity:
            issues_by_entity[issue.entity_id] = []
        issues_by_entity[issue.entity_id].append(issue)

    # Enrich entities
    enriched_count = 0
    changes_log = []

    for entity_id, issues in issues_by_entity.items():
        entity = repository.read(entity_id)
        if not entity:
            continue

        enriched, changes = enrich_entity(entity, issues, apply=not dry_run)

        if changes:
            enriched_count += 1
            changes_log.append({
                'entity_id': entity_id,
                'changes': changes,
            })

            if not dry_run:
                repository.update(enriched)

    return {
        'status': 'dry_run' if dry_run else 'applied',
        'entity_type': entity_type,
        'total': result.total_count,
        'issues_found': result.issue_count,
        'entities_enriched': enriched_count,
        'changes': changes_log[:20],  # Limit output
        'next_step': 'Run with dry_run=False to apply changes' if dry_run else 'Changes applied',
    }


# Tool handler for MCP
def preprocess_entities(
    entity_type: str = 'inquiry',
    dry_run: bool = True,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Preprocess entities to ensure field quality for distillation.

    This tool audits entities for missing/empty fields and enriches them
    using heuristics (domain inference, core_concern extraction).

    Args:
        entity_type: Type to preprocess (inquiry, learning, feature, pattern)
        dry_run: If True, show what would change without saving
        limit: Max entities to process

    Returns:
        Summary of preprocessing results
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    return preprocess_batch(repo, entity_type, dry_run, limit)
