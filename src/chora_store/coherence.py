"""
Release Coherence: Sensing imbalance in releases.

A release is coherent when it tells a complete story - when all the pieces
fit together and nothing essential is missing. This module defines the
signals that indicate coherence or its absence.

The Six Types of Imbalance (from pattern-release-as-relational-coherence):
1. Narrative Gap - No coherent story connecting changes
2. Asymmetric Depth - Some areas polished, others rough
3. Orphaned Capability - Features without documentation/onboarding
4. Promise-Reality Gap - Claims exceed actual delivery
5. Audience Blind Spot - Missing consideration for user segments
6. Support Vacuum - No path for users who get stuck

Each imbalance type has:
- description: What this imbalance means
- signals: Detectable conditions that indicate this imbalance
- weight: Relative importance (1-3, where 3 is critical)
- remediation: How to address the imbalance
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ImbalanceType(Enum):
    """The six types of release imbalance."""
    NARRATIVE_GAP = "narrative_gap"
    ASYMMETRIC_DEPTH = "asymmetric_depth"
    ORPHANED_CAPABILITY = "orphaned_capability"
    PROMISE_REALITY_GAP = "promise_reality_gap"
    AUDIENCE_BLIND_SPOT = "audience_blind_spot"
    SUPPORT_VACUUM = "support_vacuum"


@dataclass
class Signal:
    """A detectable condition that indicates imbalance."""
    id: str
    description: str
    check: str  # Name of check function or condition to evaluate
    severity: str  # "warning" | "error" | "info"


@dataclass
class ImbalanceDefinition:
    """Definition of an imbalance type with its detection signals."""
    type: ImbalanceType
    description: str
    weight: int  # 1-3, where 3 is critical
    signals: List[Signal]
    remediation: str


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

IMBALANCE_DEFINITIONS: Dict[ImbalanceType, ImbalanceDefinition] = {

    ImbalanceType.NARRATIVE_GAP: ImbalanceDefinition(
        type=ImbalanceType.NARRATIVE_GAP,
        description="No coherent story connects the changes. The release is a list of items, not a narrative.",
        weight=2,
        signals=[
            Signal(
                id="no_release_name",
                description="Release has no thematic name (just version number)",
                check="release.data.get('name') is None or release.data.get('name') == release.data.get('version')",
                severity="warning"
            ),
            Signal(
                id="no_release_description",
                description="Release has no description or story",
                check="not release.data.get('description')",
                severity="error"
            ),
            Signal(
                id="features_lack_narrative_thread",
                description="Included features span unrelated domains with no connecting theme",
                check="len(set(f.data.get('domain') for f in features)) > 3 and not release.data.get('theme')",
                severity="warning"
            ),
            Signal(
                id="no_changelog",
                description="No changelog or release notes content",
                check="not release.data.get('changelog') and not release.data.get('notes')",
                severity="error"
            ),
        ],
        remediation="Write a release story: What changed? Why does it matter? How does it connect?"
    ),

    ImbalanceType.ASYMMETRIC_DEPTH: ImbalanceDefinition(
        type=ImbalanceType.ASYMMETRIC_DEPTH,
        description="Some areas are polished while others are rough. Uneven quality across the release.",
        weight=2,
        signals=[
            Signal(
                id="incomplete_tasks",
                description="Some features have incomplete tasks while others are done",
                check="any(t.status != 'complete' for t in feature_tasks)",
                severity="error"
            ),
            Signal(
                id="mixed_feature_status",
                description="Features in release have mixed statuses (stable vs converging)",
                check="len(set(f.status for f in features)) > 1",
                severity="warning"
            ),
            Signal(
                id="documentation_gaps",
                description="Some features have docs, others don't",
                check="some_have_docs and some_lack_docs",
                severity="warning"
            ),
            Signal(
                id="test_coverage_uneven",
                description="Test coverage varies significantly across features",
                check="max_coverage - min_coverage > 0.3",
                severity="warning"
            ),
        ],
        remediation="Either complete the rough areas or explicitly scope them out of the release."
    ),

    ImbalanceType.ORPHANED_CAPABILITY: ImbalanceDefinition(
        type=ImbalanceType.ORPHANED_CAPABILITY,
        description="Features exist but users don't know they're there or how to use them.",
        weight=3,  # Critical - users can't benefit from what they can't find
        signals=[
            Signal(
                id="no_user_documentation",
                description="Feature has no user-facing documentation",
                check="not feature.data.get('docs') and not feature.data.get('documentation')",
                severity="error"
            ),
            Signal(
                id="no_examples",
                description="No examples or tutorials for the feature",
                check="not feature.data.get('examples')",
                severity="warning"
            ),
            Signal(
                id="no_discoverability",
                description="Feature not mentioned in README, help, or navigation",
                check="not in_readme and not in_help",
                severity="error"
            ),
            Signal(
                id="implementation_only_description",
                description="Description is technical jargon, not user benefit",
                check="is_implementation_language(feature.data.get('description'))",
                severity="warning"
            ),
        ],
        remediation="For each capability: Who uses it? How do they find it? What do they do first?"
    ),

    ImbalanceType.PROMISE_REALITY_GAP: ImbalanceDefinition(
        type=ImbalanceType.PROMISE_REALITY_GAP,
        description="Marketing claims or feature names promise more than the implementation delivers.",
        weight=3,  # Critical - erodes trust
        signals=[
            Signal(
                id="ambitious_name_minimal_tasks",
                description="Feature has grand name but few/incomplete tasks",
                check="len(feature_name.split()) > 3 and len(completed_tasks) < 3",
                severity="warning"
            ),
            Signal(
                id="alpha_claimed_as_stable",
                description="Feature status is experimental but release implies stability",
                check="feature.status == 'experimental' and release.data.get('stability') == 'stable'",
                severity="error"
            ),
            Signal(
                id="known_limitations_hidden",
                description="Known limitations not documented in release notes",
                check="feature.data.get('limitations') and not in_release_notes",
                severity="error"
            ),
            Signal(
                id="incomplete_api",
                description="API surface is incomplete compared to documentation",
                check="documented_endpoints > implemented_endpoints",
                severity="error"
            ),
        ],
        remediation="Audit claims vs reality. Either deliver or clearly scope expectations."
    ),

    ImbalanceType.AUDIENCE_BLIND_SPOT: ImbalanceDefinition(
        type=ImbalanceType.AUDIENCE_BLIND_SPOT,
        description="Release doesn't consider all user segments who will be affected.",
        weight=2,
        signals=[
            Signal(
                id="no_audience_defined",
                description="Release has no explicit audience/persona defined",
                check="not release.data.get('audience') and not release.data.get('personas')",
                severity="warning"
            ),
            Signal(
                id="no_migration_path",
                description="Breaking changes without migration guide for existing users",
                check="has_breaking_changes and not has_migration_guide",
                severity="error"
            ),
            Signal(
                id="assumes_expertise",
                description="Documentation assumes expertise that new users lack",
                check="no_getting_started and no_prerequisites",
                severity="warning"
            ),
            Signal(
                id="accessibility_unconsidered",
                description="No accessibility considerations documented",
                check="not release.data.get('accessibility')",
                severity="info"
            ),
        ],
        remediation="List all user segments. For each: How does this release affect them?"
    ),

    ImbalanceType.SUPPORT_VACUUM: ImbalanceDefinition(
        type=ImbalanceType.SUPPORT_VACUUM,
        description="No path forward for users who encounter problems.",
        weight=2,
        signals=[
            Signal(
                id="no_troubleshooting",
                description="No troubleshooting guide or FAQ",
                check="not has_troubleshooting",
                severity="warning"
            ),
            Signal(
                id="no_support_channel",
                description="No link to support channel (issues, discord, email)",
                check="not release.data.get('support') and not has_support_link",
                severity="error"
            ),
            Signal(
                id="no_error_documentation",
                description="Error messages not documented with solutions",
                check="has_custom_errors and not has_error_docs",
                severity="warning"
            ),
            Signal(
                id="no_rollback_path",
                description="No instructions for reverting if things go wrong",
                check="not has_rollback_guide and has_breaking_changes",
                severity="error"
            ),
        ],
        remediation="For each way things can go wrong: What does the user see? What should they do?"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# COHERENCE SCORE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CoherenceReport:
    """Result of coherence analysis."""
    release_id: str
    overall_score: float  # 0.0 to 1.0
    imbalances: List[Dict[str, Any]]  # Detected imbalances with details
    warnings: List[str]
    errors: List[str]
    recommendations: List[str]


def get_signal_count() -> Dict[str, int]:
    """Get count of signals by imbalance type."""
    return {
        itype.value: len(defn.signals)
        for itype, defn in IMBALANCE_DEFINITIONS.items()
    }


def get_total_weight() -> int:
    """Get total weight across all imbalance types."""
    return sum(defn.weight for defn in IMBALANCE_DEFINITIONS.values())


# ═══════════════════════════════════════════════════════════════════════════════
# FIVE DIMENSIONS (for orchestration)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Dimension:
    """A dimension of release communication."""
    id: str
    name: str
    description: str
    prompts: List[str]  # Questions to answer for this dimension
    artifacts: List[str]  # What this dimension produces


FIVE_DIMENSIONS: Dict[str, Dimension] = {
    "narrative": Dimension(
        id="narrative",
        name="Narrative",
        description="The story that connects all changes into a coherent whole.",
        prompts=[
            "What is the theme of this release?",
            "Why now? What made this the right time?",
            "What journey does the user go on with these changes?",
            "How does this connect to where we've been and where we're going?",
        ],
        artifacts=["release_name", "release_story", "changelog_intro"]
    ),

    "value": Dimension(
        id="value",
        name="Value",
        description="The benefits users receive from this release.",
        prompts=[
            "What can users do now that they couldn't before?",
            "What pain points does this address?",
            "What's the headline benefit?",
            "How would a user describe this to a colleague?",
        ],
        artifacts=["value_proposition", "feature_benefits", "user_quotes"]
    ),

    "audience": Dimension(
        id="audience",
        name="Audience",
        description="Who this release is for and how it affects them.",
        prompts=[
            "Who are the primary audiences for this release?",
            "How does each audience's experience change?",
            "Who might be surprised or disrupted by these changes?",
            "What do existing users need to know vs new users?",
        ],
        artifacts=["audience_map", "migration_guide", "getting_started"]
    ),

    "invitation": Dimension(
        id="invitation",
        name="Invitation",
        description="How users are invited to engage with the release.",
        prompts=[
            "What's the first thing a user should try?",
            "How do they know if it's working?",
            "What's the path from announcement to adoption?",
            "How do we make the first step easy?",
        ],
        artifacts=["quick_start", "call_to_action", "demo_link"]
    ),

    "support": Dimension(
        id="support",
        name="Support",
        description="How users get help when things don't go as expected.",
        prompts=[
            "What are the most likely problems users will encounter?",
            "Where should users go for help?",
            "What should users do if something breaks?",
            "How do we know if users are struggling?",
        ],
        artifacts=["troubleshooting", "faq", "support_links", "rollback_guide"]
    ),
}


def get_dimension_prompts() -> Dict[str, List[str]]:
    """Get all prompts organized by dimension."""
    return {
        dim_id: dim.prompts
        for dim_id, dim in FIVE_DIMENSIONS.items()
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WOBBLE DETECTOR - The Sensor
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Finding:
    """A detected imbalance signal."""
    signal_id: str
    imbalance_type: str
    severity: str  # "error" | "warning" | "info"
    description: str
    context: Optional[str] = None  # Additional context (e.g., which feature)


class WobbleDetector:
    """
    Detects coherence imbalances in releases.

    The "wobble test" - like sitting on a chair to see if it's stable.
    Runs signal checks against a release and its features to detect
    the six types of imbalance.
    """

    def __init__(self, repository):
        """
        Initialize detector with repository access.

        Args:
            repository: EntityRepository instance
        """
        self.repository = repository

    def analyze(self, release_id: str) -> CoherenceReport:
        """
        Analyze a release for coherence imbalances.

        Args:
            release_id: ID of the release entity to analyze

        Returns:
            CoherenceReport with findings and score
        """
        release = self.repository.read(release_id)
        if not release:
            return CoherenceReport(
                release_id=release_id,
                overall_score=0.0,
                imbalances=[],
                warnings=[],
                errors=[f"Release not found: {release_id}"],
                recommendations=[]
            )

        # Load associated features
        feature_ids = release.data.get('features', [])
        features = []
        for fid in feature_ids:
            f = self.repository.read(fid)
            if f:
                features.append(f)

        # Load tasks for features
        all_tasks = self.repository.list(entity_type='task', limit=500)
        feature_tasks = {}
        for f in features:
            feature_tasks[f.id] = [
                t for t in all_tasks
                if t.data.get('feature_id') == f.id
            ]

        # Run checks
        findings: List[Finding] = []

        # Narrative Gap checks
        findings.extend(self._check_narrative_gap(release, features))

        # Asymmetric Depth checks
        findings.extend(self._check_asymmetric_depth(release, features, feature_tasks))

        # Orphaned Capability checks
        findings.extend(self._check_orphaned_capability(release, features))

        # Promise-Reality Gap checks
        findings.extend(self._check_promise_reality_gap(release, features, feature_tasks))

        # Audience Blind Spot checks
        findings.extend(self._check_audience_blind_spot(release, features))

        # Support Vacuum checks
        findings.extend(self._check_support_vacuum(release, features))

        # Calculate score
        errors = [f for f in findings if f.severity == 'error']
        warnings = [f for f in findings if f.severity == 'warning']

        # Score: start at 1.0, subtract for findings
        # Errors subtract 0.15, warnings subtract 0.05
        score = 1.0 - (len(errors) * 0.15) - (len(warnings) * 0.05)
        score = max(0.0, min(1.0, score))  # Clamp to [0, 1]

        # Build recommendations from imbalance types with findings
        recommendations = []
        seen_types = set()
        for f in findings:
            if f.imbalance_type not in seen_types:
                defn = IMBALANCE_DEFINITIONS.get(ImbalanceType(f.imbalance_type))
                if defn:
                    recommendations.append(defn.remediation)
                seen_types.add(f.imbalance_type)

        return CoherenceReport(
            release_id=release_id,
            overall_score=score,
            imbalances=[{
                'signal': f.signal_id,
                'type': f.imbalance_type,
                'severity': f.severity,
                'description': f.description,
                'context': f.context
            } for f in findings],
            warnings=[f.description for f in warnings],
            errors=[f.description for f in errors],
            recommendations=recommendations
        )

    def _check_narrative_gap(self, release, features) -> List[Finding]:
        """Check for narrative gap signals."""
        findings = []

        # no_release_name
        name = release.data.get('name', '')
        version = release.data.get('version', '')
        if not name or name == version:
            findings.append(Finding(
                signal_id='no_release_name',
                imbalance_type='narrative_gap',
                severity='warning',
                description='Release has no thematic name (just version number)'
            ))

        # no_release_description
        if not release.data.get('description'):
            findings.append(Finding(
                signal_id='no_release_description',
                imbalance_type='narrative_gap',
                severity='error',
                description='Release has no description or story'
            ))

        # features_lack_narrative_thread
        if features:
            domains = set(f.data.get('domain', 'unknown') for f in features)
            if len(domains) > 3 and not release.data.get('theme'):
                findings.append(Finding(
                    signal_id='features_lack_narrative_thread',
                    imbalance_type='narrative_gap',
                    severity='warning',
                    description=f'Features span {len(domains)} domains with no connecting theme',
                    context=f"Domains: {', '.join(domains)}"
                ))

        # no_changelog
        if not release.data.get('changelog') and not release.data.get('notes'):
            findings.append(Finding(
                signal_id='no_changelog',
                imbalance_type='narrative_gap',
                severity='error',
                description='No changelog or release notes content'
            ))

        return findings

    def _check_asymmetric_depth(self, release, features, feature_tasks) -> List[Finding]:
        """Check for asymmetric depth signals."""
        findings = []

        # incomplete_tasks
        for f in features:
            tasks = feature_tasks.get(f.id, [])
            incomplete = [t for t in tasks if t.status != 'complete']
            if incomplete:
                findings.append(Finding(
                    signal_id='incomplete_tasks',
                    imbalance_type='asymmetric_depth',
                    severity='error',
                    description=f'{len(incomplete)} incomplete tasks',
                    context=f"Feature: {f.id}"
                ))

        # mixed_feature_status
        if features:
            statuses = set(f.status for f in features)
            if len(statuses) > 1:
                findings.append(Finding(
                    signal_id='mixed_feature_status',
                    imbalance_type='asymmetric_depth',
                    severity='warning',
                    description=f'Features have mixed statuses: {", ".join(statuses)}'
                ))

        # documentation_gaps
        has_docs = [f for f in features if f.data.get('docs') or f.data.get('documentation')]
        lacks_docs = [f for f in features if not f.data.get('docs') and not f.data.get('documentation')]
        if has_docs and lacks_docs:
            findings.append(Finding(
                signal_id='documentation_gaps',
                imbalance_type='asymmetric_depth',
                severity='warning',
                description=f'{len(lacks_docs)} features lack documentation',
                context=f"Missing docs: {', '.join(f.id for f in lacks_docs[:3])}"
            ))

        return findings

    def _check_orphaned_capability(self, release, features) -> List[Finding]:
        """Check for orphaned capability signals."""
        findings = []

        for f in features:
            # no_user_documentation
            if not f.data.get('docs') and not f.data.get('documentation'):
                findings.append(Finding(
                    signal_id='no_user_documentation',
                    imbalance_type='orphaned_capability',
                    severity='error',
                    description='Feature has no user-facing documentation',
                    context=f"Feature: {f.id}"
                ))

            # no_examples
            if not f.data.get('examples'):
                findings.append(Finding(
                    signal_id='no_examples',
                    imbalance_type='orphaned_capability',
                    severity='warning',
                    description='No examples or tutorials for the feature',
                    context=f"Feature: {f.id}"
                ))

        return findings

    def _check_promise_reality_gap(self, release, features, feature_tasks) -> List[Finding]:
        """Check for promise-reality gap signals."""
        findings = []

        for f in features:
            tasks = feature_tasks.get(f.id, [])
            completed = [t for t in tasks if t.status == 'complete']

            # ambitious_name_minimal_tasks
            name = f.data.get('name', '')
            if len(name.split()) > 4 and len(completed) < 3:
                findings.append(Finding(
                    signal_id='ambitious_name_minimal_tasks',
                    imbalance_type='promise_reality_gap',
                    severity='warning',
                    description=f'Feature "{name}" has only {len(completed)} completed tasks',
                    context=f"Feature: {f.id}"
                ))

            # alpha_claimed_as_stable
            if f.status in ('nascent', 'converging') and release.data.get('stability') == 'stable':
                findings.append(Finding(
                    signal_id='alpha_claimed_as_stable',
                    imbalance_type='promise_reality_gap',
                    severity='error',
                    description=f'Feature is {f.status} but release claims stability',
                    context=f"Feature: {f.id}"
                ))

            # known_limitations_hidden
            limitations = f.data.get('limitations')
            if limitations and not release.data.get('notes'):
                findings.append(Finding(
                    signal_id='known_limitations_hidden',
                    imbalance_type='promise_reality_gap',
                    severity='error',
                    description='Known limitations not documented in release notes',
                    context=f"Feature: {f.id}"
                ))

        return findings

    def _check_audience_blind_spot(self, release, features) -> List[Finding]:
        """Check for audience blind spot signals."""
        findings = []

        # no_audience_defined
        if not release.data.get('audience') and not release.data.get('personas'):
            findings.append(Finding(
                signal_id='no_audience_defined',
                imbalance_type='audience_blind_spot',
                severity='warning',
                description='Release has no explicit audience defined'
            ))

        # no_migration_path
        breaking = release.data.get('breaking_changes') or release.data.get('breaking')
        migration = release.data.get('migration') or release.data.get('migration_guide')
        if breaking and not migration:
            findings.append(Finding(
                signal_id='no_migration_path',
                imbalance_type='audience_blind_spot',
                severity='error',
                description='Breaking changes without migration guide'
            ))

        # assumes_expertise
        if not release.data.get('getting_started') and not release.data.get('prerequisites'):
            findings.append(Finding(
                signal_id='assumes_expertise',
                imbalance_type='audience_blind_spot',
                severity='warning',
                description='No getting started guide or prerequisites documented'
            ))

        return findings

    def _check_support_vacuum(self, release, features) -> List[Finding]:
        """Check for support vacuum signals."""
        findings = []

        # no_troubleshooting
        if not release.data.get('troubleshooting') and not release.data.get('faq'):
            findings.append(Finding(
                signal_id='no_troubleshooting',
                imbalance_type='support_vacuum',
                severity='warning',
                description='No troubleshooting guide or FAQ'
            ))

        # no_support_channel
        if not release.data.get('support') and not release.data.get('support_url'):
            findings.append(Finding(
                signal_id='no_support_channel',
                imbalance_type='support_vacuum',
                severity='error',
                description='No link to support channel'
            ))

        # no_rollback_path
        breaking = release.data.get('breaking_changes') or release.data.get('breaking')
        rollback = release.data.get('rollback') or release.data.get('rollback_guide')
        if breaking and not rollback:
            findings.append(Finding(
                signal_id='no_rollback_path',
                imbalance_type='support_vacuum',
                severity='error',
                description='Breaking changes without rollback instructions'
            ))

        return findings


# ═══════════════════════════════════════════════════════════════════════════════
# CLI TOOL
# ═══════════════════════════════════════════════════════════════════════════════

def tool_wobble_test(release_id: str) -> str:
    """
    The Wobble Test - check a release for coherence imbalances.

    Like sitting on a chair to see if it wobbles. Runs all signal
    checks and reports findings with a coherence score.

    Args:
        release_id: ID of the release to analyze
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    detector = WobbleDetector(repo)
    report = detector.analyze(release_id)

    lines = [f"WOBBLE TEST: {release_id}"]
    lines.append("=" * 60)

    # Score with visual indicator
    score_pct = int(report.overall_score * 100)
    if score_pct >= 80:
        indicator = "STABLE"
    elif score_pct >= 60:
        indicator = "WOBBLY"
    else:
        indicator = "UNSTABLE"

    lines.append(f"Coherence Score: {score_pct}% ({indicator})")
    lines.append(f"Errors: {len(report.errors)} | Warnings: {len(report.warnings)}")

    if report.errors:
        lines.append("")
        lines.append("ERRORS (must fix):")
        for err in report.errors:
            lines.append(f"  ! {err}")

    if report.warnings:
        lines.append("")
        lines.append("WARNINGS (should address):")
        for warn in report.warnings:
            lines.append(f"  ? {warn}")

    if report.recommendations:
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for rec in report.recommendations:
            lines.append(f"  → {rec}")

    if not report.errors and not report.warnings:
        lines.append("")
        lines.append("No imbalances detected. Release appears coherent.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FIVE DIMENSIONS CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DimensionStatus:
    """Status of a single dimension in the checklist."""
    dimension_id: str
    name: str
    complete: bool
    prompts_answered: int
    prompts_total: int
    artifacts_present: List[str]
    artifacts_missing: List[str]


@dataclass
class ChecklistReport:
    """Status of the five dimensions checklist for a release."""
    release_id: str
    overall_complete: bool
    dimensions_complete: int
    dimensions_total: int
    dimensions: List[DimensionStatus]
    next_action: Optional[str]


class DimensionChecklist:
    """
    Tracks completion of the five dimensions for a release.

    Each dimension has:
    - Prompts to answer (stored in release.data.dimensions.{dim}.responses)
    - Artifacts to produce (stored in release.data.{artifact_name})
    """

    def __init__(self, repository):
        self.repository = repository

    def get_status(self, release_id: str) -> ChecklistReport:
        """
        Get the current status of the five dimensions for a release.

        Args:
            release_id: ID of the release to check

        Returns:
            ChecklistReport with dimension-by-dimension status
        """
        release = self.repository.read(release_id)
        if not release:
            return ChecklistReport(
                release_id=release_id,
                overall_complete=False,
                dimensions_complete=0,
                dimensions_total=5,
                dimensions=[],
                next_action=f"Release not found: {release_id}"
            )

        dimensions_data = release.data.get('dimensions', {})
        dimension_statuses = []

        for dim_id, dim in FIVE_DIMENSIONS.items():
            dim_data = dimensions_data.get(dim_id, {})
            responses = dim_data.get('responses', {})

            # Count prompts answered
            prompts_answered = sum(1 for p in dim.prompts if responses.get(p))
            prompts_total = len(dim.prompts)

            # Check artifacts
            artifacts_present = []
            artifacts_missing = []
            for artifact in dim.artifacts:
                if release.data.get(artifact):
                    artifacts_present.append(artifact)
                else:
                    artifacts_missing.append(artifact)

            # Dimension is complete if all prompts answered and key artifacts present
            complete = (prompts_answered == prompts_total and len(artifacts_missing) == 0)

            dimension_statuses.append(DimensionStatus(
                dimension_id=dim_id,
                name=dim.name,
                complete=complete,
                prompts_answered=prompts_answered,
                prompts_total=prompts_total,
                artifacts_present=artifacts_present,
                artifacts_missing=artifacts_missing
            ))

        dimensions_complete = sum(1 for d in dimension_statuses if d.complete)
        overall_complete = dimensions_complete == 5

        # Determine next action
        next_action = None
        if not overall_complete:
            for ds in dimension_statuses:
                if not ds.complete:
                    if ds.prompts_answered < ds.prompts_total:
                        next_action = f"Answer prompts for {ds.name} dimension ({ds.prompts_answered}/{ds.prompts_total})"
                    else:
                        next_action = f"Create artifacts for {ds.name}: {', '.join(ds.artifacts_missing)}"
                    break

        return ChecklistReport(
            release_id=release_id,
            overall_complete=overall_complete,
            dimensions_complete=dimensions_complete,
            dimensions_total=5,
            dimensions=dimension_statuses,
            next_action=next_action
        )

    def answer_prompt(self, release_id: str, dimension_id: str, prompt: str, response: str) -> bool:
        """
        Record a response to a dimension prompt.

        Args:
            release_id: ID of the release
            dimension_id: ID of the dimension (narrative, value, audience, invitation, support)
            prompt: The prompt text being answered
            response: The response text

        Returns:
            True if successful
        """
        release = self.repository.read(release_id)
        if not release:
            return False

        if dimension_id not in FIVE_DIMENSIONS:
            return False

        # Update dimensions data
        dimensions = release.data.get('dimensions', {})
        dim_data = dimensions.get(dimension_id, {'responses': {}})
        dim_data['responses'][prompt] = response
        dimensions[dimension_id] = dim_data

        # Update release
        updated = release.copy(data={**release.data, 'dimensions': dimensions})
        self.repository.update(updated)
        return True

    def get_prompts(self, dimension_id: str) -> List[str]:
        """Get prompts for a dimension."""
        dim = FIVE_DIMENSIONS.get(dimension_id)
        return dim.prompts if dim else []


def tool_dimension_checklist(release_id: str) -> str:
    """
    The Five Dimensions Checklist - track release orchestration progress.

    Shows completion status for each dimension:
    - Narrative: The story connecting changes
    - Value: Benefits users receive
    - Audience: Who it's for and how it affects them
    - Invitation: How users engage
    - Support: How users get help

    Args:
        release_id: ID of the release to check
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    checklist = DimensionChecklist(repo)
    report = checklist.get_status(release_id)

    lines = [f"FIVE DIMENSIONS CHECKLIST: {release_id}"]
    lines.append("=" * 60)

    # Overall status
    status = "COMPLETE" if report.overall_complete else "IN PROGRESS"
    lines.append(f"Status: {status} ({report.dimensions_complete}/{report.dimensions_total} dimensions)")

    # Each dimension
    for ds in report.dimensions:
        icon = "[x]" if ds.complete else "[ ]"
        lines.append(f"\n{icon} {ds.name.upper()}")
        lines.append(f"    Prompts: {ds.prompts_answered}/{ds.prompts_total}")

        if ds.artifacts_present:
            lines.append(f"    Artifacts: {', '.join(ds.artifacts_present)}")
        if ds.artifacts_missing:
            lines.append(f"    Missing: {', '.join(ds.artifacts_missing)}")

    # Next action
    if report.next_action:
        lines.append("")
        lines.append(f"NEXT: {report.next_action}")

    return "\n".join(lines)


def tool_dimension_prompts(dimension_id: str) -> str:
    """
    Show prompts for a specific dimension.

    Use this to see what questions need to be answered for a dimension.

    Args:
        dimension_id: One of: narrative, value, audience, invitation, support
    """
    dim = FIVE_DIMENSIONS.get(dimension_id)
    if not dim:
        return f"Unknown dimension: {dimension_id}. Valid: narrative, value, audience, invitation, support"

    lines = [f"DIMENSION: {dim.name.upper()}"]
    lines.append("=" * 60)
    lines.append(f"{dim.description}")
    lines.append("")
    lines.append("PROMPTS (answer each for this dimension):")

    for i, prompt in enumerate(dim.prompts, 1):
        lines.append(f"  {i}. {prompt}")

    lines.append("")
    lines.append("ARTIFACTS (create these):")
    for artifact in dim.artifacts:
        lines.append(f"  - {artifact}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PRE-RELEASE ORCHESTRATION WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ReleaseReadiness:
    """Overall readiness assessment for a release."""
    release_id: str
    ready: bool
    coherence_score: float
    dimensions_complete: int
    blockers: List[str]  # Must fix before release
    warnings: List[str]  # Should address
    recommendation: str  # GO, WAIT, or STOP


class ReleaseOrchestrator:
    """
    Orchestrates the pre-release process.

    Combines:
    - Wobble test (coherence sensing)
    - Dimension checklist (orchestration tracking)
    - Readiness assessment (go/no-go)
    """

    def __init__(self, repository):
        self.repository = repository
        self.detector = WobbleDetector(repository)
        self.checklist = DimensionChecklist(repository)

    def assess_readiness(self, release_id: str) -> ReleaseReadiness:
        """
        Assess overall release readiness.

        Args:
            release_id: ID of the release to assess

        Returns:
            ReleaseReadiness with go/no-go recommendation
        """
        # Run wobble test
        coherence = self.detector.analyze(release_id)

        # Get dimension status
        dimensions = self.checklist.get_status(release_id)

        # Collect blockers (errors) and warnings
        blockers = coherence.errors.copy()
        warnings = coherence.warnings.copy()

        # Add dimension blockers
        if dimensions.dimensions_complete < 3:
            blockers.append(f"Only {dimensions.dimensions_complete}/5 dimensions complete")

        # Narrative dimension is critical
        narrative_status = next((d for d in dimensions.dimensions if d.dimension_id == 'narrative'), None)
        if narrative_status and not narrative_status.complete:
            blockers.append("Narrative dimension incomplete - release needs a story")

        # Support dimension is critical
        support_status = next((d for d in dimensions.dimensions if d.dimension_id == 'support'), None)
        if support_status and support_status.prompts_answered == 0:
            blockers.append("Support dimension not started - users need help paths")

        # Determine recommendation
        if len(blockers) > 3:
            recommendation = "STOP - Multiple critical issues must be addressed"
            ready = False
        elif len(blockers) > 0:
            recommendation = "WAIT - Address blockers before releasing"
            ready = False
        elif len(warnings) > 5:
            recommendation = "CAUTION - Consider addressing warnings first"
            ready = True  # Technically ready but not recommended
        elif coherence.overall_score >= 0.8 and dimensions.dimensions_complete >= 4:
            recommendation = "GO - Release appears ready"
            ready = True
        else:
            recommendation = "REVIEW - Manual review recommended"
            ready = False

        return ReleaseReadiness(
            release_id=release_id,
            ready=ready,
            coherence_score=coherence.overall_score,
            dimensions_complete=dimensions.dimensions_complete,
            blockers=blockers,
            warnings=warnings,
            recommendation=recommendation
        )

    def get_next_steps(self, release_id: str) -> List[str]:
        """
        Get prioritized list of next steps for release preparation.

        Args:
            release_id: ID of the release

        Returns:
            Ordered list of recommended actions
        """
        readiness = self.assess_readiness(release_id)
        dimensions = self.checklist.get_status(release_id)
        steps = []

        # Priority 1: Critical blockers
        for blocker in readiness.blockers[:3]:
            steps.append(f"[BLOCKER] {blocker}")

        # Priority 2: Incomplete dimensions (in order)
        dimension_order = ['narrative', 'value', 'audience', 'invitation', 'support']
        for dim_id in dimension_order:
            ds = next((d for d in dimensions.dimensions if d.dimension_id == dim_id), None)
            if ds and not ds.complete:
                if ds.prompts_answered < ds.prompts_total:
                    steps.append(f"[DIMENSION] Answer {ds.name} prompts ({ds.prompts_answered}/{ds.prompts_total})")
                if ds.artifacts_missing:
                    steps.append(f"[ARTIFACT] Create {ds.name} artifacts: {', '.join(ds.artifacts_missing[:2])}")

        # Priority 3: Warnings (limited)
        for warning in readiness.warnings[:3]:
            steps.append(f"[WARNING] {warning}")

        return steps[:10]  # Cap at 10 steps


def tool_pre_release_check(release_id: str) -> str:
    """
    Pre-Release Check - comprehensive release readiness assessment.

    Runs the full orchestration workflow:
    1. Wobble test (coherence sensing)
    2. Dimension checklist status
    3. Readiness assessment
    4. Prioritized next steps

    Args:
        release_id: ID of the release to check
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    orchestrator = ReleaseOrchestrator(repo)

    readiness = orchestrator.assess_readiness(release_id)
    next_steps = orchestrator.get_next_steps(release_id)

    lines = ["PRE-RELEASE CHECK"]
    lines.append("=" * 60)
    lines.append(f"Release: {release_id}")
    lines.append("")

    # Readiness summary
    lines.append("READINESS ASSESSMENT")
    lines.append("-" * 40)
    score_pct = int(readiness.coherence_score * 100)
    lines.append(f"  Coherence Score: {score_pct}%")
    lines.append(f"  Dimensions Complete: {readiness.dimensions_complete}/5")
    lines.append(f"  Blockers: {len(readiness.blockers)}")
    lines.append(f"  Warnings: {len(readiness.warnings)}")
    lines.append("")
    lines.append(f"  >>> {readiness.recommendation} <<<")

    # Blockers
    if readiness.blockers:
        lines.append("")
        lines.append("BLOCKERS (must fix)")
        lines.append("-" * 40)
        for blocker in readiness.blockers[:5]:
            lines.append(f"  ! {blocker}")
        if len(readiness.blockers) > 5:
            lines.append(f"  ... and {len(readiness.blockers) - 5} more")

    # Next steps
    if next_steps:
        lines.append("")
        lines.append("NEXT STEPS (prioritized)")
        lines.append("-" * 40)
        for i, step in enumerate(next_steps, 1):
            lines.append(f"  {i}. {step}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# RELEASE STORY TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════

STORY_TEMPLATE = """# {release_name}

> {tagline}

## The Story

{narrative_intro}

## What's New

{feature_summaries}

## Who This Is For

{audience_section}

## Getting Started

{invitation_section}

## If You Need Help

{support_section}

---

**Version:** {version}
**Released:** {release_date}
"""


def tool_generate_story(release_id: str) -> str:
    """
    Generate a release story from dimension responses and features.

    Creates a narrative release announcement that goes beyond a changelog
    to tell the story of what changed and why it matters.

    Args:
        release_id: ID of the release
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    release = repo.read(release_id)

    if not release:
        return f"Release not found: {release_id}"

    # Get dimension responses
    dimensions = release.data.get('dimensions', {})

    def get_response(dim_id: str, prompt_idx: int) -> str:
        """Get response to a dimension prompt by index."""
        dim_data = dimensions.get(dim_id, {})
        responses = dim_data.get('responses', {})
        dim = FIVE_DIMENSIONS.get(dim_id)
        if dim and prompt_idx < len(dim.prompts):
            return responses.get(dim.prompts[prompt_idx], '')
        return ''

    # Build narrative intro from narrative dimension
    narrative_responses = [
        get_response('narrative', 0),  # theme
        get_response('narrative', 1),  # why now
        get_response('narrative', 2),  # user journey
        get_response('narrative', 3),  # continuity
    ]
    narrative_intro = ' '.join(r for r in narrative_responses if r) or \
        "[Answer narrative dimension prompts to generate this section]"

    # Build feature summaries
    feature_ids = release.data.get('features', [])
    feature_lines = []
    for fid in feature_ids:
        f = repo.read(fid)
        if f:
            name = f.data.get('name', fid)
            desc = f.data.get('description', '')[:200]
            if desc:
                feature_lines.append(f"### {name}\n\n{desc}")
            else:
                feature_lines.append(f"### {name}\n\n[Add description]")

    feature_summaries = '\n\n'.join(feature_lines) if feature_lines else \
        "[No features linked to this release]"

    # Build audience section
    audience_responses = [
        get_response('audience', 0),  # primary audiences
        get_response('audience', 1),  # experience changes
        get_response('audience', 2),  # surprises
        get_response('audience', 3),  # existing vs new
    ]
    audience_section = '\n\n'.join(r for r in audience_responses if r) or \
        "[Answer audience dimension prompts to generate this section]"

    # Build invitation section
    invitation_responses = [
        get_response('invitation', 0),  # first thing to try
        get_response('invitation', 1),  # how to know it's working
        get_response('invitation', 2),  # path to adoption
        get_response('invitation', 3),  # easy first step
    ]
    invitation_section = '\n\n'.join(r for r in invitation_responses if r) or \
        "[Answer invitation dimension prompts to generate this section]"

    # Build support section
    support_responses = [
        get_response('support', 0),  # likely problems
        get_response('support', 1),  # where to get help
        get_response('support', 2),  # if something breaks
        get_response('support', 3),  # knowing if struggling
    ]
    support_section = '\n\n'.join(r for r in support_responses if r) or \
        "[Answer support dimension prompts to generate this section]"

    # Get tagline from value dimension
    tagline = get_response('value', 2) or \
        release.data.get('tagline', '') or \
        "[What's the headline benefit?]"

    # Fill template
    from datetime import datetime
    story = STORY_TEMPLATE.format(
        release_name=release.data.get('name', release_id),
        tagline=tagline,
        narrative_intro=narrative_intro,
        feature_summaries=feature_summaries,
        audience_section=audience_section,
        invitation_section=invitation_section,
        support_section=support_section,
        version=release.data.get('version', 'X.Y.Z'),
        release_date=datetime.now().strftime('%Y-%m-%d'),
    )

    return story


# ═══════════════════════════════════════════════════════════════════════════════
# KERNEL COHERENCE - CLAUDE.md ↔ entity.yaml Alignment
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class KernelCoherenceFinding:
    """A detected drift between CLAUDE.md and kernel schema."""
    file: str
    line: int
    issue_type: str  # 'invalid_type', 'invalid_status', 'stale_metaphor', 'invalid_field'
    reference: str   # What was referenced
    expected: str    # What was expected (or valid options)
    severity: str    # 'error', 'warning'


@dataclass
class KernelCoherenceReport:
    """Result of kernel coherence analysis."""
    score: float  # 0.0 to 1.0
    findings: List[KernelCoherenceFinding]
    errors: List[str]
    warnings: List[str]


class KernelCoherenceDetector:
    """
    Detects drift between CLAUDE.md and kernel schema (entity.yaml).

    The kernel defines the physics (types, statuses, metaphors).
    CLAUDE.md documents these for agents. This detector ensures alignment.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Initialize detector.

        Args:
            workspace_root: Root of workspace (defaults to cwd)
        """
        import os
        self.workspace_root = workspace_root or os.getcwd()
        self.schema = self._load_kernel()

    def _load_kernel(self) -> Dict[str, Any]:
        """Load entity.yaml schema."""
        import os
        import yaml

        # Try common locations for kernel
        kernel_paths = [
            os.path.join(self.workspace_root, 'packages/chora-kernel/standards/entity.yaml'),
            os.path.join(self.workspace_root, '../chora-kernel/standards/entity.yaml'),
        ]

        for path in kernel_paths:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return yaml.safe_load(f)

        # Return empty schema if not found
        return {'types': {}}

    def _get_valid_types(self) -> List[str]:
        """Get list of valid entity types from kernel."""
        return list(self.schema.get('types', {}).keys())

    def _get_valid_statuses(self, entity_type: str) -> List[str]:
        """Get valid statuses for an entity type."""
        type_def = self.schema.get('types', {}).get(entity_type, {})
        return type_def.get('statuses', [])

    def _get_physics_metaphor(self, entity_type: str) -> str:
        """Get the physics metaphor for an entity type."""
        type_def = self.schema.get('types', {}).get(entity_type, {})
        return type_def.get('physics', '')

    def analyze_file(self, file_path: str) -> List[KernelCoherenceFinding]:
        """
        Analyze a file for kernel coherence issues.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of findings
        """
        import os
        import re

        if not os.path.exists(file_path):
            return []

        with open(file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')

        findings = []
        valid_types = self._get_valid_types()

        # Build status lookup
        all_statuses: Dict[str, List[str]] = {}
        for t in valid_types:
            all_statuses[t] = self._get_valid_statuses(t)

        # Build physics lookup
        physics_metaphors: Dict[str, str] = {}
        for t in valid_types:
            physics_metaphors[t] = self._get_physics_metaphor(t)

        for line_num, line in enumerate(lines, 1):
            # Check for type references like "task" or "(Liquid)" which are stale
            # after Task→Focus evolution

            # Pattern: references to old "task" type in code/schema contexts
            if re.search(r'\btask\b', line.lower()) and 'focus' not in line.lower():
                # Check if this looks like a kernel/entity context
                if any(ctx in line.lower() for ctx in ['type', 'status', 'entity', 'statuses:', 'physics']):
                    findings.append(KernelCoherenceFinding(
                        file=file_path,
                        line=line_num,
                        issue_type='invalid_type',
                        reference='task',
                        expected=f"Valid types: {', '.join(valid_types)}",
                        severity='error'
                    ))

            # Pattern: old physics metaphor "(Liquid)" which was Task's metaphor
            if '(liquid)' in line.lower() and 'focus' not in line.lower():
                findings.append(KernelCoherenceFinding(
                    file=file_path,
                    line=line_num,
                    issue_type='stale_metaphor',
                    reference='Liquid',
                    expected='Focus uses Plasma; Task no longer exists in v3.0',
                    severity='warning'
                ))

            # Check for explicit status declarations in tables/lists
            # Pattern: "| type | statuses: X, Y, Z" or "type statuses: [X, Y]"
            for entity_type, statuses in all_statuses.items():
                # Only match explicit declarations, not mentions in entity IDs
                # Look for "| type |" table cells or "type:" definitions
                type_pattern = rf'^\s*\|?\s*{entity_type}\s*\|.*status'
                if re.search(type_pattern, line.lower()):
                    # Extract all status-like words after the type
                    status_words = re.findall(r'\b([a-z]+)\b', line.lower().split('status')[-1])
                    for word in status_words:
                        # Skip common non-status words
                        if word in ['the', 'and', 'or', 'is', 'are', 'a', 'an', 'for', 'to', 'in', 'of']:
                            continue
                        # Check if it looks like a status (matches any valid status somewhere)
                        all_valid = [s.lower() for ss in all_statuses.values() for s in ss]
                        if word not in all_valid and word in [s.lower() for s in statuses]:
                            continue  # It's valid for this type
                        if word not in all_valid:
                            continue  # Not a status word at all
                        # It's a status word - check if valid for THIS type
                        if word not in [s.lower() for s in statuses]:
                            findings.append(KernelCoherenceFinding(
                                file=file_path,
                                line=line_num,
                                issue_type='invalid_status',
                                reference=f'{entity_type}.{word}',
                                expected=f"Valid {entity_type} statuses: {', '.join(statuses)}",
                                severity='error'
                            ))

        return findings

    def analyze(self, scope: str = "workspace") -> KernelCoherenceReport:
        """
        Analyze CLAUDE.md for kernel coherence.

        Args:
            scope: "workspace" for CLAUDE.md only, "all" for all markdown files

        Returns:
            KernelCoherenceReport with findings and score
        """
        import os

        findings: List[KernelCoherenceFinding] = []

        # Always check CLAUDE.md
        claude_md = os.path.join(self.workspace_root, 'CLAUDE.md')
        if os.path.exists(claude_md):
            findings.extend(self.analyze_file(claude_md))

        if scope == "all":
            # Check other markdown files too
            for root, dirs, files in os.walk(self.workspace_root):
                # Skip common non-relevant directories
                dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', '.venv']]

                for file in files:
                    if file.endswith('.md') and file != 'CLAUDE.md':
                        file_path = os.path.join(root, file)
                        findings.extend(self.analyze_file(file_path))

        # Calculate score
        errors = [f for f in findings if f.severity == 'error']
        warnings = [f for f in findings if f.severity == 'warning']

        # Score: start at 1.0, subtract for findings
        score = 1.0 - (len(errors) * 0.2) - (len(warnings) * 0.05)
        score = max(0.0, min(1.0, score))

        return KernelCoherenceReport(
            score=score,
            findings=findings,
            errors=[f"{f.reference} at line {f.line}: {f.expected}" for f in errors],
            warnings=[f"{f.reference} at line {f.line}: {f.expected}" for f in warnings]
        )


def tool_coherence_check(scope: str = "workspace") -> str:
    """
    Check CLAUDE.md coherence with kernel schema.

    Detects drift between agent instructions (CLAUDE.md) and the kernel
    physics (entity.yaml). Catches:
    - Invalid type references (e.g., "task" when kernel v3.0 uses "focus")
    - Invalid status references
    - Stale physics metaphors

    Args:
        scope: "workspace" for CLAUDE.md only, "all" for all markdown files
    """
    detector = KernelCoherenceDetector()
    report = detector.analyze(scope)

    lines = ["KERNEL COHERENCE CHECK"]
    lines.append("=" * 60)

    # Score with visual indicator
    score_pct = int(report.score * 100)
    if score_pct >= 90:
        indicator = "ALIGNED"
    elif score_pct >= 70:
        indicator = "DRIFTING"
    else:
        indicator = "MISALIGNED"

    lines.append(f"Coherence Score: {score_pct}% ({indicator})")
    lines.append(f"Errors: {len(report.errors)} | Warnings: {len(report.warnings)}")

    if report.errors:
        lines.append("")
        lines.append("ERRORS (kernel violation):")
        for err in report.errors:
            lines.append(f"  ! {err}")

    if report.warnings:
        lines.append("")
        lines.append("WARNINGS (potential drift):")
        for warn in report.warnings:
            lines.append(f"  ? {warn}")

    if not report.errors and not report.warnings:
        lines.append("")
        lines.append("CLAUDE.md is aligned with kernel schema.")

    # Show kernel version
    if detector.schema.get('version'):
        lines.append("")
        lines.append(f"Kernel version: {detector.schema['version']}")

    return "\n".join(lines)


def tool_story_status(release_id: str) -> str:
    """
    Check how complete the release story is.

    Shows which sections are filled vs need content.

    Args:
        release_id: ID of the release
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    release = repo.read(release_id)

    if not release:
        return f"Release not found: {release_id}"

    dimensions = release.data.get('dimensions', {})

    lines = [f"STORY STATUS: {release_id}"]
    lines.append("=" * 50)

    sections = [
        ('Narrative', 'narrative', 'The story intro'),
        ('Value', 'value', 'Tagline and benefits'),
        ('Audience', 'audience', 'Who it\'s for'),
        ('Invitation', 'invitation', 'Getting started'),
        ('Support', 'support', 'Help section'),
    ]

    total_prompts = 0
    answered_prompts = 0

    for name, dim_id, desc in sections:
        dim = FIVE_DIMENSIONS.get(dim_id)
        dim_data = dimensions.get(dim_id, {})
        responses = dim_data.get('responses', {})

        prompts_total = len(dim.prompts) if dim else 0
        prompts_answered = sum(1 for p in (dim.prompts if dim else []) if responses.get(p))

        total_prompts += prompts_total
        answered_prompts += prompts_answered

        icon = "[x]" if prompts_answered == prompts_total else "[ ]"
        lines.append(f"{icon} {name}: {prompts_answered}/{prompts_total} ({desc})")

    lines.append("")
    pct = int(answered_prompts / total_prompts * 100) if total_prompts > 0 else 0
    lines.append(f"Overall: {answered_prompts}/{total_prompts} prompts answered ({pct}%)")

    if pct < 50:
        lines.append("\nTip: Use tool_dimension_prompts(dim_id) to see prompts for each section")
    elif pct < 100:
        lines.append("\nAlmost there! Fill remaining prompts to complete the story.")
    else:
        lines.append("\nStory is ready! Use tool_generate_story(release_id) to generate.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# COGNITIVE LINKAGE - CLAUDE.md ↔ Entity Bidirectional Links
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CognitiveSectionMeta:
    """Metadata for a cognitive section in CLAUDE.md."""
    section_name: str
    status: str  # core | adopted | experimental
    origin: str  # entity ID that governs this section
    source: Optional[str] = None  # optional learning/inquiry that informed it
    created: Optional[str] = None
    line_number: int = 0


@dataclass
class CognitiveLinkageReport:
    """Result of cognitive linkage analysis."""
    total_sections: int
    linked_sections: int
    missing_origins: List[str]
    missing_backlinks: List[str]
    sections: List[CognitiveSectionMeta]


def parse_cognitive_sections(filepath: str) -> List[CognitiveSectionMeta]:
    """
    Parse CLAUDE.md and extract cognitive section metadata.

    Args:
        filepath: Path to CLAUDE.md

    Returns:
        List of CognitiveSectionMeta objects
    """
    import re
    import os

    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r') as f:
        content = f.read()

    # Pattern to match section header followed by cognitive metadata
    pattern = r'## ([^\n]+)\n<!-- @chora:cognitive\n(.*?)-->'

    sections = []
    for match in re.finditer(pattern, content, re.DOTALL):
        section_name = match.group(1).strip()
        metadata_block = match.group(2)

        # Find line number
        start_pos = match.start()
        line_number = content[:start_pos].count('\n') + 1

        # Parse YAML-like metadata
        metadata = {}
        for line in metadata_block.strip().split('\n'):
            if ':' in line and not line.startswith(' '):
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()

        sections.append(CognitiveSectionMeta(
            section_name=section_name,
            status=metadata.get('status', 'unknown'),
            origin=metadata.get('origin', 'unknown'),
            source=metadata.get('source'),
            created=metadata.get('created'),
            line_number=line_number
        ))

    return sections


def analyze_cognitive_linkage(workspace_root: Optional[str] = None) -> CognitiveLinkageReport:
    """
    Analyze bidirectional linkage between CLAUDE.md sections and entities.

    Args:
        workspace_root: Root of workspace (defaults to cwd)

    Returns:
        CognitiveLinkageReport with linkage status
    """
    import os
    from .repository import EntityRepository

    workspace_root = workspace_root or os.getcwd()
    claude_md = os.path.join(workspace_root, 'CLAUDE.md')

    sections = parse_cognitive_sections(claude_md)
    repo = EntityRepository()

    missing_origins = []
    missing_backlinks = []
    linked = 0

    for section in sections:
        origin_id = section.origin
        if origin_id == 'unknown':
            missing_origins.append(f"{section.section_name} (no origin specified)")
            continue

        entity = repo.read(origin_id)
        if not entity:
            missing_origins.append(f"{section.section_name} → {origin_id}")
        else:
            linked += 1
            # Check for backlink
            cognitive_sections = entity.data.get('cognitive_sections', [])
            if section.section_name not in cognitive_sections:
                missing_backlinks.append(f"{origin_id} → {section.section_name}")

    return CognitiveLinkageReport(
        total_sections=len(sections),
        linked_sections=linked,
        missing_origins=missing_origins,
        missing_backlinks=missing_backlinks,
        sections=sections
    )


def sync_cognitive_backlinks(workspace_root: Optional[str] = None, dry_run: bool = True) -> str:
    """
    Sync backlinks from CLAUDE.md sections to their origin entities.

    Args:
        workspace_root: Root of workspace
        dry_run: If True, report what would be done without making changes

    Returns:
        Report of actions taken or planned
    """
    import os
    from .repository import EntityRepository

    workspace_root = workspace_root or os.getcwd()
    claude_md = os.path.join(workspace_root, 'CLAUDE.md')

    sections = parse_cognitive_sections(claude_md)
    repo = EntityRepository()

    actions = []

    # Group sections by origin
    by_origin: Dict[str, List[str]] = {}
    for section in sections:
        origin_id = section.origin
        if origin_id != 'unknown':
            if origin_id not in by_origin:
                by_origin[origin_id] = []
            by_origin[origin_id].append(section.section_name)

    for origin_id, section_names in by_origin.items():
        entity = repo.read(origin_id)
        if not entity:
            actions.append(f"SKIP: {origin_id} not found")
            continue

        existing = set(entity.data.get('cognitive_sections', []))
        new_sections = set(section_names)

        if new_sections != existing:
            if dry_run:
                added = new_sections - existing
                removed = existing - new_sections
                if added:
                    actions.append(f"WOULD ADD to {origin_id}: {', '.join(added)}")
                if removed:
                    actions.append(f"WOULD REMOVE from {origin_id}: {', '.join(removed)}")
            else:
                entity.data['cognitive_sections'] = list(new_sections)
                repo.update(entity)
                actions.append(f"UPDATED: {origin_id} → {section_names}")
        else:
            actions.append(f"OK: {origin_id} already linked")

    return "\n".join(actions) if actions else "No actions needed"


def tool_cognitive_linkage(action: str = "check") -> str:
    """
    Check or sync cognitive linkage between CLAUDE.md and entities.

    CLAUDE.md sections have @chora:cognitive metadata with 'origin' fields
    that point to governing entities. This tool validates those links exist
    and optionally adds backlinks from entities to their sections.

    Args:
        action: "check" to validate, "sync" to add missing backlinks
    """
    if action == "sync":
        # First do dry run
        dry_report = sync_cognitive_backlinks(dry_run=True)
        # Then actually sync
        sync_report = sync_cognitive_backlinks(dry_run=False)

        lines = ["COGNITIVE LINKAGE SYNC"]
        lines.append("=" * 60)
        lines.append("")
        lines.append("Actions taken:")
        lines.append(sync_report)
        return "\n".join(lines)

    # Default: check
    report = analyze_cognitive_linkage()

    lines = ["COGNITIVE LINKAGE CHECK"]
    lines.append("=" * 60)
    lines.append(f"Total sections: {report.total_sections}")
    lines.append(f"Linked to entities: {report.linked_sections}")

    if report.missing_origins:
        lines.append("")
        lines.append(f"MISSING ORIGINS ({len(report.missing_origins)}):")
        for m in report.missing_origins:
            lines.append(f"  ✗ {m}")

    if report.missing_backlinks:
        lines.append("")
        lines.append(f"MISSING BACKLINKS ({len(report.missing_backlinks)}):")
        for m in report.missing_backlinks:
            lines.append(f"  → {m}")
        lines.append("")
        lines.append("Run tool_cognitive_linkage('sync') to add backlinks")

    if not report.missing_origins and not report.missing_backlinks:
        lines.append("")
        lines.append("✓ All sections properly linked!")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL COGNITION CLAUDE.MD GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ToolCognitionSummary:
    """Summary of a tool's cognition for generation."""
    tool_id: str
    name: str
    description: str
    phase: Optional[str]
    core: bool
    cognitive_status: str


def get_core_tools_with_cognition() -> List[ToolCognitionSummary]:
    """
    Get all tools that have cognition.core = True.

    Returns:
        List of ToolCognitionSummary for core tools
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    tools = repo.list('tool')

    core_tools = []
    for tool in tools:
        cognition = tool.data.get('cognition', {})
        if cognition.get('core', False):
            core_tools.append(ToolCognitionSummary(
                tool_id=tool.id,
                name=tool.data.get('name', tool.id),
                description=tool.data.get('description', ''),
                phase=cognition.get('phase'),
                core=True,
                cognitive_status=cognition.get('cognitive_status', 'experimental')
            ))

    return core_tools


def get_tools_by_phase() -> Dict[str, List[ToolCognitionSummary]]:
    """
    Get all tools with cognition grouped by phase.

    Returns:
        Dict mapping phase name to list of tools
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    tools = repo.list('tool')

    by_phase: Dict[str, List[ToolCognitionSummary]] = {
        'orient': [],
        'constellation': [],
        'focus': [],
        'check': [],
        'unassigned': []
    }

    for tool in tools:
        cognition = tool.data.get('cognition', {})
        if not cognition:
            continue

        phase = cognition.get('phase', 'unassigned') or 'unassigned'
        if phase not in by_phase:
            by_phase[phase] = []

        by_phase[phase].append(ToolCognitionSummary(
            tool_id=tool.id,
            name=tool.data.get('name', tool.id),
            description=tool.data.get('description', ''),
            phase=phase,
            core=cognition.get('core', False),
            cognitive_status=cognition.get('cognitive_status', 'experimental')
        ))

    return by_phase


def generate_quick_ref_tools_section() -> str:
    """
    Generate the Quick Reference Card tool commands section.

    Returns:
        Markdown content for quick_ref_tools section
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    tools = repo.list('tool')
    total_tools = len(tools)

    # Justfile has these shortcuts (friendly names)
    JUSTFILE_SHORTCUTS = {
        'tool-core-orient': ('orient', 'See current state'),
        'tool-focus-constellation': ('constellation <id>', 'See entity context'),
        'tool-meta-induction': ('induction', 'Cluster learnings for synthesis'),
        'tool-meta-notice-emerging': ('emerging', 'Notice what tools want to exist'),
    }

    lines = [
        f"```bash",
        f"just capabilities    # See ALL tools ({total_tools} total)",
        f"just tool <id>       # Invoke any tool by ID"
    ]

    # Add justfile shortcuts
    for tool_id, (cmd, desc) in JUSTFILE_SHORTCUTS.items():
        lines.append(f"just {cmd:<20} # {desc}")

    lines.append("```")

    return "\n".join(lines)


def generate_core_mcp_tools_section() -> str:
    """
    Generate the Core MCP Tools table section.

    Returns:
        Markdown table content for core_mcp_tools section
    """
    core_tools = get_core_tools_with_cognition()
    by_phase = get_tools_by_phase()

    # Build table with phase information
    lines = [
        "| Tool | Phase | Purpose |",
        "|------|-------|---------|"
    ]

    # Order by phase: orient -> constellation -> focus -> check
    phase_order = ['orient', 'constellation', 'focus', 'check']

    seen = set()
    for phase in phase_order:
        tools_in_phase = by_phase.get(phase, [])
        # Only include core tools, sorted by name
        for tool in sorted(tools_in_phase, key=lambda t: t.name):
            if tool.core and tool.tool_id not in seen:
                short_name = tool.tool_id.replace('tool-', '')
                desc = tool.description[:50] if tool.description else tool.name
                lines.append(f"| `{short_name}` | {phase} | {desc} |")
                seen.add(tool.tool_id)

    return "\n".join(lines)


def generate_mcp_tools_summary_section() -> str:
    """
    Generate the MCP Tools summary section.

    Returns:
        Markdown content for mcp_tools_summary section
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    tools = repo.list('tool')
    total_tools = len(tools)

    # Count tools with cognition
    with_cognition = sum(1 for t in tools if t.data.get('cognition'))

    lines = [
        f"The system exposes {total_tools} tools via two layers:",
        f"- **Tool Entities** ({total_tools}): Dynamic, hot-reloadable tools in SQLite with phenomenological cognition",
        f"- **MCP Functions**: Infrastructure tools in Python code"
    ]

    if with_cognition > 0:
        lines.append(f"\n{with_cognition} tools have phenomenological cognition for agent awareness.")

    return "\n".join(lines)


@dataclass
class ClaudemDriftReport:
    """Report of drift between CLAUDE.md markers and actual tool state."""
    section: str
    expected_content: str
    has_drift: bool
    message: str


def check_claudemd_drift(workspace_root: Optional[str] = None) -> List[ClaudemDriftReport]:
    """
    Check if CLAUDE.md generated sections are out of sync with tool state.

    Args:
        workspace_root: Root of workspace

    Returns:
        List of drift reports
    """
    import os
    import re

    workspace_root = workspace_root or os.getcwd()
    claude_md = os.path.join(workspace_root, 'CLAUDE.md')

    if not os.path.exists(claude_md):
        return [ClaudemDriftReport(
            section='CLAUDE.md',
            expected_content='',
            has_drift=True,
            message='CLAUDE.md not found'
        )]

    with open(claude_md, 'r') as f:
        content = f.read()

    reports = []

    # Check each generated section
    sections = {
        'quick_ref_tools': generate_quick_ref_tools_section,
        'core_mcp_tools': generate_core_mcp_tools_section,
        'mcp_tools_summary': generate_mcp_tools_summary_section
    }

    for section_name, generator in sections.items():
        # Find marker in content
        pattern = rf'<!-- @chora:generated section={section_name} -->\n(.*?)<!-- @chora:generated:end -->'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            reports.append(ClaudemDriftReport(
                section=section_name,
                expected_content='',
                has_drift=True,
                message=f'Marker not found for section={section_name}'
            ))
            continue

        current_content = match.group(1).strip()
        expected_content = generator().strip()

        # Simple diff check
        has_drift = current_content != expected_content

        if has_drift:
            # Check if it's just tool count
            if 'total' in section_name.lower() or 'summary' in section_name.lower():
                message = 'Tool count may have changed'
            else:
                message = 'Content differs from generated'
        else:
            message = 'Up to date'

        reports.append(ClaudemDriftReport(
            section=section_name,
            expected_content=expected_content,
            has_drift=has_drift,
            message=message
        ))

    return reports


def regenerate_claudemd_sections(workspace_root: Optional[str] = None, dry_run: bool = True) -> str:
    """
    Regenerate CLAUDE.md sections from tool cognition.

    Args:
        workspace_root: Root of workspace
        dry_run: If True, show what would be changed without writing

    Returns:
        Report of what was/would be changed
    """
    import os
    import re

    workspace_root = workspace_root or os.getcwd()
    claude_md = os.path.join(workspace_root, 'CLAUDE.md')

    if not os.path.exists(claude_md):
        return "CLAUDE.md not found"

    with open(claude_md, 'r') as f:
        content = f.read()

    changes = []
    new_content = content

    # Sections to regenerate
    sections = {
        'quick_ref_tools': generate_quick_ref_tools_section,
        'core_mcp_tools': generate_core_mcp_tools_section,
        'mcp_tools_summary': generate_mcp_tools_summary_section
    }

    for section_name, generator in sections.items():
        pattern = rf'(<!-- @chora:generated section={section_name} -->\n)(.*?)(<!-- @chora:generated:end -->)'
        match = re.search(pattern, new_content, re.DOTALL)

        if not match:
            changes.append(f"SKIP: {section_name} - marker not found")
            continue

        current = match.group(2).strip()
        generated = generator()

        if current != generated.strip():
            changes.append(f"UPDATE: {section_name}")
            replacement = match.group(1) + generated + '\n' + match.group(3)
            new_content = new_content[:match.start()] + replacement + new_content[match.end():]
        else:
            changes.append(f"OK: {section_name} - no changes needed")

    if not dry_run and new_content != content:
        with open(claude_md, 'w') as f:
            f.write(new_content)
        changes.append("\n✓ CLAUDE.md updated")
    elif dry_run:
        changes.append("\n(dry run - no changes written)")

    return "\n".join(changes)


def tool_claudemd_regen(action: str = "check") -> str:
    """
    Check or regenerate CLAUDE.md sections from tool cognition.

    Tools with cognition.core = True appear in Quick Reference Card.
    Tools with cognition.phase set appear in phase mappings.

    This tool keeps CLAUDE.md in sync with the actual tool state.

    Args:
        action: "check" to see drift, "regen" to regenerate sections
    """
    if action == "regen":
        result = regenerate_claudemd_sections(dry_run=False)
        lines = ["CLAUDE.MD REGENERATION"]
        lines.append("=" * 60)
        lines.append(result)
        return "\n".join(lines)

    # Default: check
    reports = check_claudemd_drift()

    lines = ["CLAUDE.MD DRIFT CHECK"]
    lines.append("=" * 60)

    has_any_drift = False
    for report in reports:
        icon = "✗" if report.has_drift else "✓"
        lines.append(f"{icon} {report.section}: {report.message}")
        if report.has_drift:
            has_any_drift = True

    if has_any_drift:
        lines.append("")
        lines.append("Run tool_claudemd_regen('regen') to update CLAUDE.md")
    else:
        lines.append("")
        lines.append("✓ CLAUDE.md is in sync with tool cognition")

    return "\n".join(lines)
