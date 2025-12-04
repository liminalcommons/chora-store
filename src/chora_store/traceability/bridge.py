"""
Behavior Bridge: Connect test scenarios to feature entities.

This module creates bidirectional links between:
- .feature files (test scenarios)
- Feature entities (with behaviors field)
- Pattern implementations

Traceability fields added to entities:
- test_coverage: {scenario_id: {file, status}}
- behavior_source: 'documented' | 'discovered' | 'generated'
- pattern_alignment: {pattern_id: alignment_type}
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from .scanner import GherkinScanner, Feature, Scenario, slugify


@dataclass
class CoverageMapping:
    """Maps a feature entity to its test coverage."""
    entity_id: str
    entity_name: str
    test_file: Optional[Path] = None
    scenarios: List[Scenario] = field(default_factory=list)
    behaviors_documented: int = 0
    behaviors_tested: int = 0

    @property
    def coverage_ratio(self) -> float:
        """Percentage of documented behaviors that have tests."""
        if self.behaviors_documented == 0:
            return 0.0
        return self.behaviors_tested / self.behaviors_documented

    @property
    def has_test_file(self) -> bool:
        return self.test_file is not None


@dataclass
class BehaviorMatch:
    """A match between a documented behavior and a test scenario."""
    behavior_id: str
    scenario_id: str
    match_type: str  # 'exact', 'fuzzy', 'manual'
    confidence: float  # 0.0 - 1.0
    scenario: Optional[Scenario] = None


class BehaviorBridge:
    """
    Bridge between test files and feature entities.

    Creates and maintains traceability links between:
    - Feature behaviors (documented in entity data)
    - Test scenarios (in .feature files)
    - Code implementations (Phase 2)
    """

    def __init__(self, repository=None, tests_dir: Optional[Path] = None):
        """
        Initialize bridge.

        Args:
            repository: EntityRepository instance
            tests_dir: Directory containing .feature files
        """
        self.repository = repository
        self.tests_dir = tests_dir or self._default_tests_dir()
        self.scanner = GherkinScanner()

    def _default_tests_dir(self) -> Path:
        """Get default tests directory (chora-store/tests/features)."""
        return Path(__file__).parent.parent.parent.parent / 'tests' / 'features'

    def scan_all_tests(self) -> List[Feature]:
        """Scan all .feature files in tests directory."""
        if not self.tests_dir.exists():
            return []
        return self.scanner.scan_directory(self.tests_dir)

    def get_all_features(self) -> List[Any]:
        """Get all feature entities from repository."""
        if not self.repository:
            return []
        return self.repository.list(entity_type='feature', limit=1000)

    def build_mapping_name(self, feature_name: str) -> str:
        """
        Convert a .feature file name to expected entity ID.

        Examples:
            'Factory Governance' -> 'feature-factory-governance'
            'Behavioral Stability Gate' -> 'feature-behavioral-stability-gate'
        """
        return f"feature-{slugify(feature_name)}"

    def find_entity_for_test(self, test_feature: Feature) -> Optional[Any]:
        """
        Find the entity that a test file corresponds to.

        Strategy:
        1. Exact ID match (test name -> entity ID)
        2. Fuzzy name match
        3. Return None if no match
        """
        if not self.repository:
            return None

        expected_id = self.build_mapping_name(test_feature.name)

        # Try exact match first
        entity = self.repository.read(expected_id)
        if entity:
            return entity

        # Try fuzzy match on feature names
        features = self.get_all_features()
        test_name_lower = test_feature.name.lower()

        for feature in features:
            entity_name = feature.data.get('name', '').lower()
            # Check if names are substantially similar
            if self._names_match(test_name_lower, entity_name):
                return feature

        return None

    def _names_match(self, name1: str, name2: str) -> bool:
        """Check if two names are similar enough to be a match."""
        # Remove common suffixes/prefixes
        name1 = name1.replace('feature', '').strip()
        name2 = name2.replace('feature', '').strip()

        # Word overlap check
        words1 = set(name1.split())
        words2 = set(name2.split())

        if not words1 or not words2:
            return False

        # Jaccard similarity > 0.5
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) > 0.5

    def match_behaviors(
        self,
        entity_behaviors: List[Dict],
        test_scenarios: List[Scenario]
    ) -> List[BehaviorMatch]:
        """
        Match documented behaviors to test scenarios.

        Returns list of matches with confidence scores.
        """
        matches = []

        for behavior in entity_behaviors:
            behavior_id = behavior.get('id', '')
            behavior_when = behavior.get('when', '').lower()
            behavior_then = behavior.get('then', '').lower()

            best_match = None
            best_confidence = 0.0

            for scenario in test_scenarios:
                # Calculate similarity
                scenario_when = scenario.when_text.lower()
                scenario_then = scenario.then_text.lower()

                # Word overlap scoring
                when_score = self._text_similarity(behavior_when, scenario_when)
                then_score = self._text_similarity(behavior_then, scenario_then)

                # Average of when and then similarity
                confidence = (when_score + then_score) / 2

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = scenario

            if best_match and best_confidence > 0.3:
                match_type = 'exact' if best_confidence > 0.8 else 'fuzzy'
                matches.append(BehaviorMatch(
                    behavior_id=behavior_id,
                    scenario_id=best_match.id,
                    match_type=match_type,
                    confidence=best_confidence,
                    scenario=best_match,
                ))

        return matches

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate word overlap similarity between two texts."""
        if not text1 or not text2:
            return 0.0

        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def analyze_coverage(self) -> Dict[str, Any]:
        """
        Analyze test coverage across all features.

        Returns comprehensive coverage report.
        """
        test_features = self.scan_all_tests()
        entity_features = self.get_all_features()

        report = {
            'test_files': len(test_features),
            'total_scenarios': sum(len(f.scenarios) for f in test_features),
            'entity_features': len(entity_features),
            'mapped': [],      # Test files with matching entities
            'unmapped': [],    # Test files without matching entities
            'uncovered': [],   # Entity features without test files
            'coverage_details': [],
        }

        # Track which entities have test files
        covered_entity_ids = set()

        for test_feature in test_features:
            entity = self.find_entity_for_test(test_feature)

            if entity:
                covered_entity_ids.add(entity.id)

                # Get entity behaviors
                entity_behaviors = entity.data.get('behaviors', [])

                # Match behaviors to scenarios
                matches = self.match_behaviors(entity_behaviors, test_feature.scenarios)

                mapping = CoverageMapping(
                    entity_id=entity.id,
                    entity_name=entity.data.get('name', entity.id),
                    test_file=test_feature.file_path,
                    scenarios=test_feature.scenarios,
                    behaviors_documented=len(entity_behaviors),
                    behaviors_tested=len(matches),
                )
                report['mapped'].append({
                    'test_file': str(test_feature.file_path.name) if test_feature.file_path else test_feature.name,
                    'entity_id': entity.id,
                    'scenarios': len(test_feature.scenarios),
                    'behaviors_documented': len(entity_behaviors),
                    'behaviors_matched': len(matches),
                    'coverage_ratio': mapping.coverage_ratio,
                    'matches': [
                        {
                            'behavior': m.behavior_id,
                            'scenario': m.scenario_id,
                            'confidence': m.confidence,
                            'type': m.match_type,
                        }
                        for m in matches
                    ]
                })
            else:
                report['unmapped'].append({
                    'test_file': str(test_feature.file_path.name) if test_feature.file_path else test_feature.name,
                    'feature_name': test_feature.name,
                    'suggested_id': self.build_mapping_name(test_feature.name),
                    'scenarios': len(test_feature.scenarios),
                })

        # Find uncovered entities
        for entity in entity_features:
            if entity.id not in covered_entity_ids:
                report['uncovered'].append({
                    'entity_id': entity.id,
                    'entity_name': entity.data.get('name', entity.id),
                    'behaviors': len(entity.data.get('behaviors', [])),
                    'status': entity.status,
                })

        return report

    def inject_test_coverage(self, entity_id: str, test_file: Path) -> Optional[Any]:
        """
        Inject test coverage metadata into an entity.

        Adds traceability fields:
        - test_coverage: mapping of scenario IDs to test info
        - behavior_source: 'documented' or 'discovered'
        """
        if not self.repository:
            return None

        entity = self.repository.read(entity_id)
        if not entity:
            return None

        feature = self.scanner.scan_file(test_file)
        if not feature:
            return None

        # Build test coverage mapping
        test_coverage = {}
        for scenario in feature.scenarios:
            test_coverage[scenario.id] = {
                'file': str(test_file.name),
                'name': scenario.name,
                'status': 'untested',  # Will be updated by test runner
            }

        # Update entity data
        updated_data = dict(entity.data)
        updated_data['test_coverage'] = test_coverage
        updated_data['test_file'] = str(test_file)

        updated = entity.copy(data=updated_data)
        return self.repository.update(updated)

    def generate_behaviors_from_tests(self, entity_id: str) -> List[Dict]:
        """
        Generate behaviors for an entity from its test file.

        Useful when entity has no documented behaviors but has tests.
        """
        if not self.repository:
            return []

        entity = self.repository.read(entity_id)
        if not entity:
            return []

        # Find test file for this entity
        test_features = self.scan_all_tests()
        for test_feature in test_features:
            if self.find_entity_for_test(test_feature) == entity:
                return test_feature.to_behaviors(status='untested')

        return []


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_coverage_report() -> str:
    """
    Generate test coverage report for all features.

    Shows:
    - Which test files map to which entities
    - Coverage gaps (entities without tests)
    - Unmapped tests (tests without entities)
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    bridge = BehaviorBridge(repository=repo)
    report = bridge.analyze_coverage()

    lines = ['BEHAVIOR COVERAGE REPORT', '=' * 60]
    lines.append(f"Test files: {report['test_files']}")
    lines.append(f"Total scenarios: {report['total_scenarios']}")
    lines.append(f"Feature entities: {report['entity_features']}")
    lines.append('')

    # Mapped (good)
    if report['mapped']:
        lines.append('LINKED (test file <-> entity):')
        for m in report['mapped']:
            ratio = m['coverage_ratio']
            icon = '✓' if ratio >= 0.8 else '◐' if ratio >= 0.5 else '○'
            lines.append(f"  {icon} {m['test_file']} -> {m['entity_id']}")
            lines.append(f"      Scenarios: {m['scenarios']}, Behaviors matched: {m['behaviors_matched']}/{m['behaviors_documented']}")
        lines.append('')

    # Unmapped tests (need entities)
    if report['unmapped']:
        lines.append('UNMAPPED TESTS (need entities):')
        for u in report['unmapped']:
            lines.append(f"  ? {u['test_file']}")
            lines.append(f"      Suggested entity: {u['suggested_id']}")
            lines.append(f"      Scenarios: {u['scenarios']}")
        lines.append('')

    # Uncovered entities (need tests)
    if report['uncovered']:
        lines.append('UNCOVERED ENTITIES (need tests):')
        for u in report['uncovered']:
            icon = '!' if u['behaviors'] > 0 else '○'
            lines.append(f"  {icon} {u['entity_id']} ({u['status']})")
            if u['behaviors'] > 0:
                lines.append(f"      Has {u['behaviors']} documented behaviors but no test file")
        lines.append('')

    if not report['unmapped'] and not report['uncovered']:
        lines.append('Full coverage achieved!')

    return '\n'.join(lines)


def tool_link_test_to_entity(test_file: str, entity_id: str) -> str:
    """
    Manually link a test file to an entity.

    Args:
        test_file: Path to .feature file (relative to chora-store)
        entity_id: ID of the feature entity

    Returns:
        Confirmation or error message
    """
    from pathlib import Path
    from ..repository import EntityRepository

    base = Path(__file__).parent.parent.parent.parent
    file_path = base / test_file

    if not file_path.exists():
        return f"Test file not found: {test_file}"

    repo = EntityRepository()
    bridge = BehaviorBridge(repository=repo)

    result = bridge.inject_test_coverage(entity_id, file_path)
    if result:
        return f"Linked {test_file} to {entity_id}. Test coverage metadata injected."
    else:
        return f"Failed to link. Entity {entity_id} may not exist."


def tool_generate_behaviors(entity_id: str) -> str:
    """
    Generate behavior documentation from tests.

    For entities that have tests but no documented behaviors,
    this extracts behaviors from the test scenarios.

    Args:
        entity_id: ID of the feature entity

    Returns:
        YAML-formatted behaviors for the entity
    """
    import yaml
    from ..repository import EntityRepository

    repo = EntityRepository()
    bridge = BehaviorBridge(repository=repo)

    behaviors = bridge.generate_behaviors_from_tests(entity_id)

    if not behaviors:
        return f"No test file found for {entity_id}, or entity doesn't exist."

    lines = [f'# Generated behaviors for {entity_id}',
             '# Copy these to the entity behaviors field',
             '',
             'behaviors:']

    for b in behaviors:
        lines.append(yaml.dump([b], default_flow_style=False, indent=2))

    return '\n'.join(lines)


def tool_link_all_tests() -> str:
    """
    Batch link all test files to their matching entities.

    Automatically injects test_coverage and test_file metadata
    into all entities that have matching .feature files.

    Returns:
        Report of entities linked and any failures
    """
    from ..repository import EntityRepository

    repo = EntityRepository()
    bridge = BehaviorBridge(repository=repo)

    test_features = bridge.scan_all_tests()
    results = {
        'linked': [],
        'already_linked': [],
        'no_match': [],
        'failed': [],
    }

    for test_feature in test_features:
        entity = bridge.find_entity_for_test(test_feature)

        if not entity:
            results['no_match'].append({
                'test_file': str(test_feature.file_path.name) if test_feature.file_path else test_feature.name,
                'suggested_id': bridge.build_mapping_name(test_feature.name),
            })
            continue

        # Check if already linked
        if entity.data.get('test_file'):
            results['already_linked'].append({
                'entity_id': entity.id,
                'test_file': entity.data.get('test_file'),
            })
            continue

        # Link the test file
        try:
            result = bridge.inject_test_coverage(entity.id, test_feature.file_path)
            if result:
                results['linked'].append({
                    'entity_id': entity.id,
                    'test_file': str(test_feature.file_path.name),
                    'scenarios': len(test_feature.scenarios),
                })
            else:
                results['failed'].append({
                    'entity_id': entity.id,
                    'reason': 'inject_test_coverage returned None',
                })
        except Exception as e:
            results['failed'].append({
                'entity_id': entity.id,
                'reason': str(e),
            })

    # Build report
    lines = ['BATCH LINKING REPORT', '=' * 50]

    if results['linked']:
        lines.append(f"\n✓ LINKED ({len(results['linked'])}):")
        for r in results['linked']:
            lines.append(f"  {r['entity_id']} <- {r['test_file']} ({r['scenarios']} scenarios)")

    if results['already_linked']:
        lines.append(f"\n○ ALREADY LINKED ({len(results['already_linked'])}):")
        for r in results['already_linked']:
            lines.append(f"  {r['entity_id']} <- {r['test_file']}")

    if results['no_match']:
        lines.append(f"\n? NO MATCH ({len(results['no_match'])}):")
        for r in results['no_match']:
            lines.append(f"  {r['test_file']} (create entity: {r['suggested_id']})")

    if results['failed']:
        lines.append(f"\n✗ FAILED ({len(results['failed'])}):")
        for r in results['failed']:
            lines.append(f"  {r['entity_id']}: {r['reason']}")

    summary_linked = len(results['linked'])
    summary_total = len(test_features)
    lines.append(f"\nSummary: {summary_linked}/{summary_total} newly linked")

    return '\n'.join(lines)
