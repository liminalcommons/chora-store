"""
Pattern Reifier: Autonomous pattern lifecycle management.

This module implements fully autonomous pattern reification:
1. DETECT - Find emergent candidates (≥3 occurrences)
2. REIFY - Auto-create pattern entities (status: proposed)
3. ALIGN - Update behaviors with implements_pattern field
4. EVALUATE - Fitness system handles promotion/deprecation

Key Principle: No human approval. The fitness function approves patterns.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from .pattern_auditor import PatternAuditor, EmergentPattern


@dataclass
class ReifiedPattern:
    """A pattern that was created from an emergent candidate."""
    pattern_id: str
    candidate_name: str
    source_behaviors: List[str]
    confidence: float
    domain: str


@dataclass
class AlignedBehavior:
    """A behavior that was linked to a pattern."""
    behavior_id: str
    feature_id: str
    pattern_id: str
    alignment_type: str  # 'exact', 'inferred', 'existing'


@dataclass
class ReificationReport:
    """Report of autonomous reification actions."""
    candidates_found: int
    candidates_filtered: int  # Removed because covered by existing patterns
    patterns_created: List[ReifiedPattern]
    behaviors_aligned: List[AlignedBehavior]
    one_offs_remaining: int
    errors: List[str]

    def __str__(self) -> str:
        lines = ['AUTONOMOUS REIFICATION REPORT', '=' * 60]
        lines.append(f"Candidates found: {self.candidates_found}")
        lines.append(f"Filtered (already covered): {self.candidates_filtered}")
        lines.append(f"Patterns created: {len(self.patterns_created)}")
        lines.append(f"Behaviors aligned: {len(self.behaviors_aligned)}")
        lines.append(f"One-offs remaining: {self.one_offs_remaining}")

        if self.patterns_created:
            lines.append('')
            lines.append('NEW PATTERNS:')
            for p in self.patterns_created:
                lines.append(f"  ✓ {p.pattern_id}")
                lines.append(f"      Domain: {p.domain}")
                lines.append(f"      Confidence: {p.confidence:.0%}")
                lines.append(f"      Source behaviors: {len(p.source_behaviors)}")

        if self.behaviors_aligned:
            lines.append('')
            lines.append(f'ALIGNED BEHAVIORS ({len(self.behaviors_aligned)}):')
            # Group by pattern
            by_pattern: Dict[str, List[AlignedBehavior]] = {}
            for ab in self.behaviors_aligned:
                if ab.pattern_id not in by_pattern:
                    by_pattern[ab.pattern_id] = []
                by_pattern[ab.pattern_id].append(ab)

            for pattern_id, aligned in by_pattern.items():
                lines.append(f"  {pattern_id}: {len(aligned)} behaviors")

        if self.errors:
            lines.append('')
            lines.append('ERRORS:')
            for e in self.errors:
                lines.append(f"  ✗ {e}")

        return '\n'.join(lines)


# Mapping of emergent candidates to existing patterns that cover them
EXISTING_PATTERN_COVERAGE = {
    'blocks-invalid-transition': 'pattern-structural-governance',
    'rejects-invalid-type': 'pattern-structural-governance',
    'orient-provides-temporal-grounding': 'pattern-meta-agent-orientation',
    'gate-blocks-stable-without-behaviors': 'pattern-quality-gate',
    'focus-created-on-commit': 'pattern-arch-stigmergic-coordination',
    'inquiry-creation': 'pattern-meta-entity-lifecycle',
}


class PatternReifier:
    """
    Autonomous pattern reification from emergent candidates.

    Lifecycle: detect → reify → align → evaluate → promote/deprecate

    The fitness evaluation and promotion/deprecation is handled by
    the existing PatternEvaluator system - this class just creates
    the patterns and aligns behaviors.
    """

    def __init__(self, repository=None):
        """
        Initialize reifier.

        Args:
            repository: EntityRepository instance
        """
        self.repository = repository
        self.auditor = PatternAuditor(repository=repository)
        self._errors: List[str] = []

    def reify_all(self, min_confidence: float = 0.7) -> ReificationReport:
        """
        Full autonomous pipeline.

        1. Get emergent candidates from pattern auditor
        2. Filter: confidence ≥ min_confidence, not covered by existing patterns
        3. For each candidate: create pattern, link behaviors
        4. Align remaining behaviors to existing patterns
        5. Return report of actions taken
        """
        self._errors = []

        # 1. Get emergent candidates
        candidates = self.auditor.find_emergent_patterns()
        candidates_found = len(candidates)

        # 2. Filter candidates
        filtered_candidates = []
        candidates_filtered = 0

        for candidate in candidates:
            # Check confidence threshold
            if candidate.confidence < min_confidence:
                continue

            # Check if covered by existing pattern
            covering_pattern = self._is_covered_by_existing(candidate)
            if covering_pattern:
                candidates_filtered += 1
                continue

            filtered_candidates.append(candidate)

        # 3. Reify each candidate
        patterns_created: List[ReifiedPattern] = []
        for candidate in filtered_candidates:
            pattern = self._reify_candidate(candidate)
            if pattern:
                patterns_created.append(pattern)

        # 4. Align all behaviors
        aligned = self._align_all_behaviors(patterns_created)

        # 5. Count remaining one-offs
        all_behaviors = self.auditor._get_all_behaviors()
        aligned_ids = {ab.behavior_id for ab in aligned}
        one_offs = len([b for b in all_behaviors if b.get('id') not in aligned_ids])

        return ReificationReport(
            candidates_found=candidates_found,
            candidates_filtered=candidates_filtered,
            patterns_created=patterns_created,
            behaviors_aligned=aligned,
            one_offs_remaining=one_offs,
            errors=self._errors,
        )

    def _is_covered_by_existing(self, candidate: EmergentPattern) -> Optional[str]:
        """
        Check if candidate is already covered by an existing pattern.

        Returns pattern_id if covered, None if novel.
        """
        # Check the known coverage mapping
        candidate_key = candidate.name.replace('pattern-candidate-', '')

        for key, pattern_id in EXISTING_PATTERN_COVERAGE.items():
            if key in candidate_key:
                return pattern_id

        # Also check if pattern with similar name exists
        if self.repository:
            # Exclude common words that would cause false positive matches
            EXCLUDED_WORDS = {'pattern', 'candidate', 'behavior', 'feature', 'entity'}
            patterns = self.repository.list(entity_type='pattern', limit=100)
            for pattern in patterns:
                pattern_name = pattern.data.get('name', '').lower()
                # Filter out excluded common words from candidate name
                candidate_words = [w for w in candidate.name.lower().split('-')
                                   if len(w) > 4 and w not in EXCLUDED_WORDS]
                # Check for meaningful word overlap
                if any(word in pattern_name for word in candidate_words):
                    return pattern.id

        return None

    def _reify_candidate(self, candidate: EmergentPattern) -> Optional[ReifiedPattern]:
        """
        Create a pattern entity from an emergent candidate.
        """
        if not self.repository:
            self._errors.append(f"No repository - cannot create pattern for {candidate.name}")
            return None

        try:
            from ..factory import EntityFactory
            factory = EntityFactory(repository=self.repository)

            # Generate pattern definition from behavior analysis
            definition = self._generate_pattern_definition(candidate)

            # Create pattern name
            pattern_name = candidate.name.replace('pattern-candidate-', 'pattern-')
            if not pattern_name.startswith('pattern-'):
                pattern_name = f"pattern-{pattern_name}"

            # Create the pattern entity
            pattern = factory.create(
                'pattern',
                definition['name'],
                status='proposed',  # Start as proposed, fitness will promote
                subtype='behavioral',  # Emergent patterns are behavioral
                context=definition['context'],
                problem=definition['problem'],
                solution=definition['solution'],
                domain=candidate.suggested_domain,
                extracted_from=candidate.behavior_ids,
                emergence_confidence=candidate.confidence,
                # Phase 6 epigenetic fields
                reification_source='autonomous',
                source_behaviors=candidate.behavior_ids,
                # Fitness criteria for auto-created patterns
                fitness={
                    'observation_period': '30 days',
                    'sample_size': 3,
                    'metrics': [
                        {
                            'name': 'adoption_rate',
                            'description': 'New behaviors that reference this pattern',
                            'target': 3,
                            'direction': 'higher_is_better',
                        },
                        {
                            'name': 'alignment_stability',
                            'description': 'Aligned behaviors that remain passing',
                            'target': 0.8,
                            'direction': 'higher_is_better',
                        },
                    ],
                    'success_condition': 'observation_period.elapsed AND adoption_rate >= 3',
                    'failure_condition': 'observation_period.elapsed AND adoption_rate < 1',
                },
            )

            return ReifiedPattern(
                pattern_id=pattern.id,
                candidate_name=candidate.name,
                source_behaviors=candidate.behavior_ids,
                confidence=candidate.confidence,
                domain=candidate.suggested_domain,
            )

        except Exception as e:
            self._errors.append(f"Failed to create pattern for {candidate.name}: {e}")
            return None

    def _generate_pattern_definition(self, candidate: EmergentPattern) -> Dict[str, str]:
        """
        Auto-generate pattern fields from behavior analysis.

        - context: Inferred from common preconditions (given)
        - problem: Inferred from what triggers the behavior (when)
        - solution: Inferred from outcomes (then)
        """
        # Get source behaviors
        behaviors = []
        if self.repository:
            features = self.repository.list(entity_type='feature', limit=1000)
            for f in features:
                for b in f.data.get('behaviors', []):
                    if b.get('id') in candidate.behavior_ids:
                        behaviors.append(b)

        # Extract common elements
        givens = [b.get('given', '') for b in behaviors if b.get('given')]
        whens = [b.get('when', '') for b in behaviors if b.get('when')]
        thens = [b.get('then', '') for b in behaviors if b.get('then')]

        # Generate human-readable name
        name = candidate.name.replace('pattern-candidate-', '').replace('-', ' ').title()

        # Synthesize context from givens
        context = f"When {candidate.occurrences} similar behaviors share preconditions: "
        if givens:
            context += givens[0][:100]
        else:
            context += f"(inferred from {candidate.suggested_domain} domain)"

        # Synthesize problem from whens
        problem = f"Multiple places require: "
        if whens:
            problem += whens[0][:100]
        else:
            problem += candidate.common_structure[:100]

        # Synthesize solution from thens
        solution = f"Apply consistent pattern: "
        if thens:
            solution += thens[0][:100]
        else:
            solution += f"See source behaviors for implementation examples."

        return {
            'name': name,
            'context': context,
            'problem': problem,
            'solution': solution,
        }

    def _align_all_behaviors(
        self,
        new_patterns: List[ReifiedPattern]
    ) -> List[AlignedBehavior]:
        """
        Update all behaviors with implements_pattern field.

        For each behavior:
        1. If it was source for a new pattern: link to that pattern
        2. If it matches an existing pattern: link to existing
        3. If no match: leave as one-off
        """
        aligned: List[AlignedBehavior] = []

        if not self.repository:
            return aligned

        # Build mapping of behavior_id -> pattern_id from new patterns
        new_pattern_map: Dict[str, str] = {}
        for rp in new_patterns:
            for behavior_id in rp.source_behaviors:
                new_pattern_map[behavior_id] = rp.pattern_id

        # Get all features and update behaviors
        features = self.repository.list(entity_type='feature', limit=1000)

        for feature in features:
            behaviors = feature.data.get('behaviors', [])
            if not behaviors:
                continue

            updated = False
            new_behaviors = []

            for behavior in behaviors:
                behavior_id = behavior.get('id', '')

                # Skip if already has implements_pattern
                if behavior.get('implements_pattern'):
                    aligned.append(AlignedBehavior(
                        behavior_id=behavior_id,
                        feature_id=feature.id,
                        pattern_id=behavior['implements_pattern'],
                        alignment_type='existing',
                    ))
                    new_behaviors.append(behavior)
                    continue

                # Check if this was a source behavior for a new pattern
                if behavior_id in new_pattern_map:
                    behavior = dict(behavior)
                    behavior['implements_pattern'] = new_pattern_map[behavior_id]
                    updated = True
                    aligned.append(AlignedBehavior(
                        behavior_id=behavior_id,
                        feature_id=feature.id,
                        pattern_id=new_pattern_map[behavior_id],
                        alignment_type='exact',
                    ))
                    new_behaviors.append(behavior)
                    continue

                # Check if matches an existing pattern via the coverage map
                existing_pattern = self._find_existing_pattern_for_behavior(behavior)
                if existing_pattern:
                    behavior = dict(behavior)
                    behavior['implements_pattern'] = existing_pattern
                    updated = True
                    aligned.append(AlignedBehavior(
                        behavior_id=behavior_id,
                        feature_id=feature.id,
                        pattern_id=existing_pattern,
                        alignment_type='inferred',
                    ))
                    new_behaviors.append(behavior)
                    continue

                # No match - leave as one-off
                new_behaviors.append(behavior)

            # Update feature if behaviors changed
            if updated:
                try:
                    updated_data = dict(feature.data)
                    updated_data['behaviors'] = new_behaviors
                    updated_feature = feature.copy(data=updated_data)
                    self.repository.update(updated_feature)
                except Exception as e:
                    self._errors.append(f"Failed to update {feature.id}: {e}")

        return aligned

    def _find_existing_pattern_for_behavior(self, behavior: Dict) -> Optional[str]:
        """
        Find if a behavior matches an existing pattern.

        Uses keyword matching against the coverage map.
        """
        when_text = behavior.get('when', '').lower()
        then_text = behavior.get('then', '').lower()
        full_text = when_text + ' ' + then_text

        # Check against known pattern keywords (29 patterns, expanded coverage)
        pattern_keywords = {
            # Governance patterns (4)
            'pattern-structural-governance': ['invalid', 'reject', 'validate', 'block', 'error', 'duplicate',
                                            'cannot skip', 'validationerror'],
            'pattern-quality-gate': ['stable', 'behavior', 'require', 'gate', 'evidence', 'passing',
                                     'suggests', 'untested', 'coverage', 'dimension', 'completeness',
                                     'dimensions', 'functional', 'edge-case'],
            'pattern-meta-agent-orientation': ['orient', 'temporal', 'grounding', 'context', 'compass',
                                               'narrative', 'active work', 'invokes', 'guidance',
                                               'summary', 'scale', 'scope', 'inner', 'far', 'personal',
                                               'shared', 'workspace', 'next action', 'card', 'reference',
                                               'claudemd', 'summarizes', 'accessible', 'quick', 'agent session',
                                               'signals', 'surface', 'hierarchy', 'processes'],
            'pattern-arch-stigmergic-coordination': ['focus', 'commit', 'attention', 'trail', 'stigmergy',
                                                      'mark', 'recover', 'resume', 'persist', 'provenance',
                                                      'reopen', 'agent a', 'agent b', 'coordination',
                                                      'focus_id', 'links to', 'focused work'],

            # Kernel verb patterns (7)
            'pattern-factory': ['create', 'entity', 'instantiate', 'spec', 'genesis', 'factory', 'update'],
            'pattern-observer': ['watch', 'react', 'emit', 'event', 'trigger', 'hook', 'execute',
                                 'signal', 'alert', 'detect', 'handler', 'callback', 'invoke',
                                 'canary', 'spike', 'trend', 'warning', 'at-risk', 'flagged',
                                 'bricking', 'harmful', 'reversion', 'traces', 'recorded',
                                 'observability', 'log', 'audit'],
            'pattern-workflow': ['sequence', 'workflow', 'steps', 'order', 'dag'],
            'pattern-expose': ['expose', 'interface', 'endpoint', 'access', 'surface', 'available',
                              'show', 'list', 'queryable', 'hot-reload', 'immediately', 'surfaced',
                              'output includes', 'constellation', 'linkage', 'registered', 'returned',
                              'details', 'upstream', 'downstream', 'includes', 'list_tools', 'generated',
                              'appears in the list', 'can be invoked'],
            'pattern-persist': ['persist', 'store', 'save', 'durable', 'serialize', 'immutable'],
            'pattern-transform': ['transform', 'convert', 'crystallize', 'synthesize', 'bundle',
                                  'digest', 'aggregate', 'group', 'batch', 'resolution', 'reification',
                                  'bidirectional', 'contains', 'returns', 'surprises'],
            'pattern-finalize': ['finalize', 'autophagy', 'harvest', 'archive', 'end', 'closed',
                                 'deprecat', 'shipping', 'released', 'capturing what went wrong'],

            # Epigenetic patterns (4)
            'pattern-feature-ttl': ['ttl', 'nascent', 'stale', 'abandon', 'drift', 'duration'],
            'pattern-feature-lifecycle': ['lifecycle', 'activate', 'transition', 'govern', 'status',
                                          'application', 'validated', 'applied', 'link', 'blocks'],
            'pattern-governance-deviation-gate': ['deviation', 'pattern', 'discover', 'aware'],
            'pattern-kernel-coherence-gate': ['coherence', 'kernel', 'schema', 'align', 'injects'],

            # Meta patterns (5)
            'pattern-meta-structural-governance': ['governance', 'root', 'spec', 'linter', 'enforced'],
            'pattern-meta-entity-lifecycle': ['lifecycle', 'phase', 'research', 'design', 'prototype'],
            'pattern-meta-doc-autopoiesis': ['autopoiesis', 'docs', 'generate', 'self-healing'],
            'pattern-meta-schema-evolution': ['schema', 'evolution', 'version', 'mutation', 'extension'],
            'pattern-meta-infrastructure-integration': ['infra', 'k8s', 'kubernetes', 'n8n'],

            # Architectural patterns (5)
            'pattern-arch-progressive-reification': ['reify', 'crystallize', 'tool', 'capability'],
            'pattern-arch-semantic-identity': ['semantic', 'identity', 'naming', 'slug'],
            'pattern-arch-package-extraction': ['extract', 'package', 'compose', 'module'],
            'pattern-arch-gateway-routing': ['gateway', 'routing', 'unified', 'entry-point'],
            'pattern-arch-unified-capability': ['capability', 'unified', 'affordance', 'tool_id',
                                                'llm|reference|compose'],

            # Process patterns (4)
            'pattern-proc-discovery-first': ['discovery', 'search', 'exist', 'reuse', 'searches'],
            'pattern-proc-lifecycle-governance': ['phase', 'transition', 'suggest', 'enforce', 'succeeds'],
            'pattern-proc-mutual-affordances': ['mutual', 'human-agent', 'trust', 'ergonomic', 'discern',
                                                'acts without asking', 'signals intent', 'surfaces options',
                                                'clarity', 'stakes', 'without asking', 'choose approach',
                                                'agent needs', 'perform operation', 'asking permission'],
            'pattern-proc-curatorial-evaluation': ['curate', 'evaluate', 'review', 'fitness', 'recommend',
                                                   'confidence', 'scores', 'proposal'],

            # Novel patterns (4) - Phase 7 expansion
            'pattern-tiered-synthesis': ['synthesis', 'tier', 'resolution', 'data tier', 'inference tier',
                                         'overlap', 'escalate', 'keyword overlap'],
            'pattern-induction': ['induction', 'inductor', 'cluster', 'spec', 'metabolic',
                                  'auto-synthesize', 'tool_induction', 'pattern spec'],
            'pattern-cognitive-linkage': ['cognitive', 'linkage', 'backlink', 'section', 'parse',
                                          'sync', 'origin', 'parse_cognitive', 'check_linkage'],
            'pattern-leverage-propagation': ['scanner', 'retrofit', 'leverage', 'propagation',
                                             'opportunity', 'automatic', 'identifies'],
        }

        for pattern_id, keywords in pattern_keywords.items():
            matches = sum(1 for k in keywords if k in full_text)
            if matches >= 2:  # Require at least 2 keyword matches
                return pattern_id

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_reify_patterns(min_confidence: float = 0.7) -> str:
    """
    Run full autonomous pattern reification pipeline.

    1. Detects emergent pattern candidates
    2. Filters candidates already covered by existing patterns
    3. Creates new pattern entities (status: proposed)
    4. Links behaviors to patterns via implements_pattern field
    5. Returns comprehensive report

    Args:
        min_confidence: Minimum confidence threshold (default 0.7)

    Returns:
        Reification report showing patterns created and behaviors aligned
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    reifier = PatternReifier(repository=repo)

    report = reifier.reify_all(min_confidence=min_confidence)
    return str(report)


def tool_align_behaviors() -> str:
    """
    Update all behaviors with implements_pattern field.

    Links behaviors to their canonical patterns without creating new patterns.
    Use this after manually creating patterns to align existing behaviors.

    Returns:
        Report of behaviors aligned to patterns
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    reifier = PatternReifier(repository=repo)

    # Just run alignment without creating new patterns
    aligned = reifier._align_all_behaviors([])

    lines = ['BEHAVIOR ALIGNMENT REPORT', '=' * 50]
    lines.append(f"Behaviors aligned: {len(aligned)}")

    if aligned:
        # Group by pattern
        by_pattern: Dict[str, List[AlignedBehavior]] = {}
        for ab in aligned:
            if ab.pattern_id not in by_pattern:
                by_pattern[ab.pattern_id] = []
            by_pattern[ab.pattern_id].append(ab)

        lines.append('')
        for pattern_id, behaviors in by_pattern.items():
            lines.append(f"{pattern_id}: {len(behaviors)} behaviors")
            for ab in behaviors[:3]:
                lines.append(f"  - {ab.behavior_id} ({ab.alignment_type})")
            if len(behaviors) > 3:
                lines.append(f"  ... and {len(behaviors) - 3} more")

    return '\n'.join(lines)


def tool_pattern_coverage() -> str:
    """
    Report on pattern alignment coverage.

    Shows:
    - Total behaviors
    - Behaviors with implements_pattern
    - Coverage percentage
    - Breakdown by pattern

    Returns:
        Pattern coverage report
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    features = repo.list(entity_type='feature', limit=1000)

    total_behaviors = 0
    aligned_behaviors = 0
    by_pattern: Dict[str, int] = {}
    one_offs: List[str] = []

    for feature in features:
        for behavior in feature.data.get('behaviors', []):
            total_behaviors += 1
            behavior_id = behavior.get('id', '')

            pattern_id = behavior.get('implements_pattern')
            if pattern_id:
                aligned_behaviors += 1
                by_pattern[pattern_id] = by_pattern.get(pattern_id, 0) + 1
            else:
                one_offs.append(behavior_id)

    coverage = (aligned_behaviors / total_behaviors * 100) if total_behaviors > 0 else 0

    lines = ['PATTERN COVERAGE REPORT', '=' * 50]
    lines.append(f"Total behaviors: {total_behaviors}")
    lines.append(f"Aligned to patterns: {aligned_behaviors}")
    lines.append(f"Coverage: {coverage:.1f}%")

    if by_pattern:
        lines.append('')
        lines.append('ALIGNMENT BY PATTERN:')
        for pattern_id, count in sorted(by_pattern.items(), key=lambda x: -x[1]):
            lines.append(f"  {pattern_id}: {count}")

    if one_offs:
        lines.append('')
        lines.append(f'ONE-OFFS ({len(one_offs)}):')
        for behavior_id in one_offs[:10]:
            lines.append(f"  ○ {behavior_id}")
        if len(one_offs) > 10:
            lines.append(f"  ... and {len(one_offs) - 10} more")

    # Target check
    lines.append('')
    if coverage >= 80:
        lines.append(f"✓ Target achieved: {coverage:.1f}% >= 80%")
    else:
        needed = int(total_behaviors * 0.8) - aligned_behaviors
        lines.append(f"○ Target: 80% ({needed} more behaviors need alignment)")

    return '\n'.join(lines)


def tool_run_phase6() -> str:
    """
    Run the Phase 6 autonomous reification pipeline manually.

    Executes the full pipeline:
    1. DETECT - Find emergent pattern candidates
    2. REIFY - Create pattern entities from candidates
    3. ALIGN - Link behaviors to patterns
    4. EVALUATE - Run fitness evaluation on experimental patterns

    Returns:
        Summary of pipeline execution
    """
    from ..repository import EntityRepository
    from ..observer import get_observer

    repo = EntityRepository()
    observer = get_observer()

    result = observer._invoke_phase6_pipeline('phase6.full', None, repo, {})
    return f"Phase 6 Pipeline\n{'=' * 50}\n{result}"
