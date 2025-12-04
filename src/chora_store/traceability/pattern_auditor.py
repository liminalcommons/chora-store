"""
Pattern Auditor: Categorize behaviors by pattern alignment.

This module analyzes behaviors and categorizes them as:
1. Pattern-aligned: Follows an established pattern
2. One-off: Custom implementation not following patterns
3. Emergent candidate: Appears multiple times, may become a pattern

Emergent Pattern Criteria:
- Appears 3+ times in different contexts
- Solves a recurring problem
- Has consistent structure

The goal is to surface which implementations are pattern-aligned,
which are conscious deviations, and which suggest new patterns.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter


@dataclass
class PatternAlignment:
    """Analysis of how well a behavior aligns with patterns."""
    behavior_id: str
    category: str  # 'pattern-aligned', 'one-off', 'emergent-candidate'
    pattern_id: Optional[str] = None  # If aligned, which pattern
    similar_behaviors: List[str] = field(default_factory=list)  # For emergent candidates
    confidence: float = 0.5
    reasoning: str = ""


@dataclass
class EmergentPattern:
    """A candidate for a new pattern."""
    name: str
    occurrences: int
    behavior_ids: List[str]
    common_structure: str
    suggested_domain: str
    confidence: float


class PatternAuditor:
    """
    Audits behaviors for pattern alignment.

    Categories:
    - Pattern-aligned: Matches an existing pattern's mechanics
    - One-off: No pattern match, appears once
    - Emergent candidate: No pattern match, appears 3+ times
    """

    def __init__(self, repository=None):
        """
        Initialize auditor.

        Args:
            repository: EntityRepository for pattern lookups
        """
        self.repository = repository
        self._pattern_cache: Optional[List[Any]] = None
        self._behavior_cache: Optional[List[Dict]] = None

    def _get_patterns(self) -> List[Any]:
        """Get all patterns from repository."""
        if self._pattern_cache is None:
            if self.repository:
                self._pattern_cache = self.repository.list(entity_type='pattern', limit=1000)
            else:
                self._pattern_cache = []
        return self._pattern_cache

    def _get_all_behaviors(self) -> List[Dict]:
        """Get all documented behaviors from features."""
        if self._behavior_cache is None:
            self._behavior_cache = []
            if self.repository:
                features = self.repository.list(entity_type='feature', limit=1000)
                for f in features:
                    behaviors = f.data.get('behaviors', [])
                    for b in behaviors:
                        b_copy = dict(b)
                        b_copy['_feature_id'] = f.id
                        self._behavior_cache.append(b_copy)
        return self._behavior_cache

    def audit_behavior(self, behavior: Dict) -> PatternAlignment:
        """
        Audit a single behavior for pattern alignment.

        Args:
            behavior: Behavior dict with id, given, when, then

        Returns:
            PatternAlignment with category and details
        """
        behavior_id = behavior.get('id', 'unknown')
        when_text = behavior.get('when', '').lower()
        then_text = behavior.get('then', '').lower()

        # Check against patterns
        patterns = self._get_patterns()
        for pattern in patterns:
            if self._behavior_matches_pattern(behavior, pattern):
                return PatternAlignment(
                    behavior_id=behavior_id,
                    category='pattern-aligned',
                    pattern_id=pattern.id,
                    confidence=0.8,
                    reasoning=f"Matches pattern mechanics: {pattern.id}",
                )

        # Check for similar behaviors (emergent candidate check)
        all_behaviors = self._get_all_behaviors()
        similar = self._find_similar_behaviors(behavior, all_behaviors)

        if len(similar) >= 2:  # 3+ occurrences including this one
            return PatternAlignment(
                behavior_id=behavior_id,
                category='emergent-candidate',
                similar_behaviors=[b.get('id', '') for b in similar],
                confidence=0.6,
                reasoning=f"Found {len(similar) + 1} similar behaviors - candidate for pattern extraction",
            )

        # One-off
        return PatternAlignment(
            behavior_id=behavior_id,
            category='one-off',
            confidence=0.7,
            reasoning="No pattern match, no similar behaviors found",
        )

    def _behavior_matches_pattern(self, behavior: Dict, pattern: Any) -> bool:
        """Check if behavior matches a pattern's mechanics."""
        mechanics = pattern.data.get('mechanics', {})
        if not mechanics:
            return False

        # Check target entity type match
        target = mechanics.get('target', '')
        behavior_feature = behavior.get('_feature_id', '')

        # Check if behavior action matches pattern hooks
        hooks = mechanics.get('hooks', [])
        behavior_when = behavior.get('when', '').lower()

        for hook in hooks:
            trigger = hook.get('trigger', '').lower()
            action = hook.get('action', '').lower()

            # Match if behavior when/then mentions the hook's trigger/action
            if trigger in behavior_when or action in behavior.get('then', '').lower():
                return True

        # Check pattern context/solution for keyword overlap
        pattern_context = pattern.data.get('context', '').lower()
        pattern_solution = pattern.data.get('solution', '').lower()
        pattern_keywords = set(pattern_context.split() + pattern_solution.split())

        behavior_words = set(behavior_when.split() + behavior.get('then', '').lower().split())

        # Significant overlap (5+ shared meaningful words)
        overlap = pattern_keywords & behavior_words
        significant = [w for w in overlap if len(w) > 4]
        if len(significant) >= 5:
            return True

        return False

    def _find_similar_behaviors(
        self,
        behavior: Dict,
        all_behaviors: List[Dict]
    ) -> List[Dict]:
        """Find behaviors similar to the given one."""
        similar = []
        behavior_id = behavior.get('id', '')
        behavior_when = behavior.get('when', '').lower()
        behavior_then = behavior.get('then', '').lower()

        when_words = set(behavior_when.split())
        then_words = set(behavior_then.split())

        for other in all_behaviors:
            if other.get('id') == behavior_id:
                continue

            other_when = other.get('when', '').lower()
            other_then = other.get('then', '').lower()

            other_when_words = set(other_when.split())
            other_then_words = set(other_then.split())

            # Calculate similarity
            when_overlap = len(when_words & other_when_words)
            then_overlap = len(then_words & other_then_words)

            # Require significant overlap in both when and then
            if when_overlap >= 2 and then_overlap >= 2:
                similar.append(other)

        return similar

    def audit_all_behaviors(self) -> Dict[str, List[PatternAlignment]]:
        """
        Audit all documented behaviors.

        Returns:
            Dict with keys: pattern-aligned, one-off, emergent-candidate
        """
        all_behaviors = self._get_all_behaviors()
        results: Dict[str, List[PatternAlignment]] = {
            'pattern-aligned': [],
            'one-off': [],
            'emergent-candidate': [],
        }

        for behavior in all_behaviors:
            alignment = self.audit_behavior(behavior)
            results[alignment.category].append(alignment)

        return results

    def find_emergent_patterns(self) -> List[EmergentPattern]:
        """
        Identify candidates for new patterns.

        Looks for behaviors that appear 3+ times with similar structure.
        """
        all_behaviors = self._get_all_behaviors()
        emergent: List[EmergentPattern] = []

        # Group behaviors by structural similarity
        processed = set()
        for behavior in all_behaviors:
            behavior_id = behavior.get('id', '')
            if behavior_id in processed:
                continue

            similar = self._find_similar_behaviors(behavior, all_behaviors)
            if len(similar) >= 2:  # 3+ total
                all_ids = [behavior_id] + [b.get('id', '') for b in similar]
                processed.update(all_ids)

                # Extract common structure
                when_text = behavior.get('when', '')
                then_text = behavior.get('then', '')

                emergent.append(EmergentPattern(
                    name=f"pattern-candidate-{behavior_id.replace('behavior-', '')}",
                    occurrences=len(all_ids),
                    behavior_ids=all_ids,
                    common_structure=f"When: {when_text[:50]}... Then: {then_text[:50]}...",
                    suggested_domain=self._infer_domain(behavior),
                    confidence=min(0.9, 0.4 + (len(all_ids) * 0.1)),
                ))

        return emergent

    def _infer_domain(self, behavior: Dict) -> str:
        """Infer domain from behavior content."""
        when_text = behavior.get('when', '').lower()
        then_text = behavior.get('then', '').lower()
        full_text = when_text + ' ' + then_text

        # Domain keywords
        domains = {
            'governance': ['validate', 'reject', 'require', 'enforce', 'block'],
            'lifecycle': ['transition', 'status', 'state', 'create', 'finalize'],
            'coordination': ['focus', 'orient', 'signal', 'trail', 'attention'],
            'synthesis': ['pattern', 'learning', 'extract', 'synthesize', 'induc'],
            'coherence': ['behavior', 'test', 'coverage', 'stable', 'drift'],
        }

        for domain, keywords in domains.items():
            matches = sum(1 for k in keywords if k in full_text)
            if matches >= 2:
                return domain

        return 'general'

    def generate_report(self) -> str:
        """Generate comprehensive audit report."""
        results = self.audit_all_behaviors()
        emergent = self.find_emergent_patterns()

        lines = ['PATTERN ALIGNMENT AUDIT', '=' * 60]

        total = sum(len(v) for v in results.values())
        lines.append(f"Total behaviors audited: {total}")
        lines.append('')

        # Summary
        for category, alignments in results.items():
            pct = (len(alignments) / total * 100) if total > 0 else 0
            icon = '✓' if category == 'pattern-aligned' else '?' if category == 'emergent-candidate' else '○'
            lines.append(f"{icon} {category}: {len(alignments)} ({pct:.0f}%)")

        # Pattern-aligned details
        if results['pattern-aligned']:
            lines.append('')
            lines.append('PATTERN-ALIGNED:')
            patterns_used = Counter(a.pattern_id for a in results['pattern-aligned'])
            for pattern_id, count in patterns_used.most_common(10):
                lines.append(f"  {pattern_id}: {count} behaviors")

        # Emergent candidates
        if emergent:
            lines.append('')
            lines.append(f'EMERGENT PATTERN CANDIDATES ({len(emergent)}):')
            for ep in emergent:
                lines.append(f"  {ep.name}")
                lines.append(f"    Occurrences: {ep.occurrences}")
                lines.append(f"    Domain: {ep.suggested_domain}")
                lines.append(f"    Structure: {ep.common_structure[:60]}...")
                lines.append(f"    Confidence: {ep.confidence:.0%}")

        # One-offs (sample)
        if results['one-off']:
            lines.append('')
            lines.append(f'ONE-OFFS ({len(results["one-off"])} total):')
            for a in results['one-off'][:5]:
                lines.append(f"  {a.behavior_id}")
            if len(results['one-off']) > 5:
                lines.append(f"  ... and {len(results['one-off']) - 5} more")

        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_pattern_audit() -> str:
    """
    Audit all behaviors for pattern alignment.

    Categorizes behaviors as:
    - Pattern-aligned: Follows established patterns
    - One-off: Custom implementation
    - Emergent-candidate: May become a new pattern

    Returns:
        Comprehensive audit report
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    auditor = PatternAuditor(repository=repo)

    return auditor.generate_report()


def tool_find_emergent_patterns() -> str:
    """
    Find candidates for new patterns.

    Identifies behaviors that appear 3+ times with similar structure,
    suggesting they should be documented as patterns.

    Returns:
        List of emergent pattern candidates
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    auditor = PatternAuditor(repository=repo)

    emergent = auditor.find_emergent_patterns()

    if not emergent:
        return "No emergent pattern candidates found. Behaviors are unique or already pattern-aligned."

    lines = ['EMERGENT PATTERN CANDIDATES', '=' * 50]
    lines.append(f"Found {len(emergent)} candidates for new patterns:")
    lines.append('')

    for i, ep in enumerate(emergent, 1):
        lines.append(f"{i}. {ep.name}")
        lines.append(f"   Domain: {ep.suggested_domain}")
        lines.append(f"   Occurrences: {ep.occurrences}")
        lines.append(f"   Confidence: {ep.confidence:.0%}")
        lines.append(f"   Behaviors: {', '.join(ep.behavior_ids[:3])}")
        if len(ep.behavior_ids) > 3:
            lines.append(f"              ... and {len(ep.behavior_ids) - 3} more")
        lines.append(f"   Structure: {ep.common_structure}")
        lines.append('')

    lines.append("Next steps:")
    lines.append("  1. Review candidates for actual pattern potential")
    lines.append("  2. Use propose_synthesis() to create pattern from related learnings")
    lines.append("  3. Document pattern with context, problem, solution")

    return '\n'.join(lines)


def tool_audit_behavior(behavior_id: str) -> str:
    """
    Audit a specific behavior for pattern alignment.

    Args:
        behavior_id: ID of behavior to audit

    Returns:
        Alignment analysis for the behavior
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    auditor = PatternAuditor(repository=repo)

    # Find the behavior
    features = repo.list(entity_type='feature', limit=1000)
    target_behavior = None
    feature_id = None

    for f in features:
        for b in f.data.get('behaviors', []):
            if b.get('id') == behavior_id:
                target_behavior = dict(b)
                target_behavior['_feature_id'] = f.id
                feature_id = f.id
                break
        if target_behavior:
            break

    if not target_behavior:
        return f"Behavior not found: {behavior_id}"

    alignment = auditor.audit_behavior(target_behavior)

    lines = [f'BEHAVIOR AUDIT: {behavior_id}', '=' * 50]
    lines.append(f"Feature: {feature_id}")
    lines.append(f"Category: {alignment.category}")
    lines.append(f"Confidence: {alignment.confidence:.0%}")

    if alignment.pattern_id:
        lines.append(f"Pattern: {alignment.pattern_id}")

    if alignment.similar_behaviors:
        lines.append(f"Similar behaviors: {len(alignment.similar_behaviors)}")
        for sb in alignment.similar_behaviors[:5]:
            lines.append(f"  - {sb}")

    lines.append(f"Reasoning: {alignment.reasoning}")

    return '\n'.join(lines)
