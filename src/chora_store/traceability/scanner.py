"""
Gherkin Scanner: Parse .feature files into structured behaviors.

Converts pytest-bdd .feature files into the kernel behavior format:
- id: behavior-{slug}
- given: "Precondition (entity in state)"
- when: "Action taken"
- then: "Observable outcome"
- verifiable_by: automated (for test files)
- status: untested | passing | failing
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


def slugify(text: str) -> str:
    """Convert text to slug format."""
    # Lowercase, replace spaces and special chars with hyphens
    slug = text.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


@dataclass
class Scenario:
    """A single Gherkin scenario."""
    name: str
    given: List[str] = field(default_factory=list)
    when: List[str] = field(default_factory=list)
    then: List[str] = field(default_factory=list)
    and_steps: Dict[str, List[str]] = field(default_factory=dict)  # 'given'/'when'/'then' -> steps

    @property
    def id(self) -> str:
        """Generate behavior ID from scenario name."""
        return f"behavior-{slugify(self.name)}"

    @property
    def given_text(self) -> str:
        """Combined given steps as single string."""
        all_given = self.given + self.and_steps.get('given', [])
        return ' AND '.join(all_given) if all_given else ''

    @property
    def when_text(self) -> str:
        """Combined when steps as single string."""
        all_when = self.when + self.and_steps.get('when', [])
        return ' AND '.join(all_when) if all_when else ''

    @property
    def then_text(self) -> str:
        """Combined then steps as single string."""
        all_then = self.then + self.and_steps.get('then', [])
        return ' AND '.join(all_then) if all_then else ''

    def to_behavior(self, status: str = 'untested') -> Dict[str, Any]:
        """Convert to kernel behavior format."""
        return {
            'id': self.id,
            'given': self.given_text,
            'when': self.when_text,
            'then': self.then_text,
            'verifiable_by': 'automated',
            'status': status,
        }


@dataclass
class Feature:
    """A parsed Gherkin feature file."""
    name: str
    description: str = ''
    file_path: Optional[Path] = None
    background_given: List[str] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Generate feature ID from name."""
        return f"feature-{slugify(self.name)}"

    def to_behaviors(self, status: str = 'untested') -> List[Dict[str, Any]]:
        """Convert all scenarios to kernel behavior format."""
        behaviors = []
        for scenario in self.scenarios:
            behavior = scenario.to_behavior(status)
            # Prepend background given if present
            if self.background_given:
                bg_text = ' AND '.join(self.background_given)
                if behavior['given']:
                    behavior['given'] = f"{bg_text} AND {behavior['given']}"
                else:
                    behavior['given'] = bg_text
            behaviors.append(behavior)
        return behaviors


class GherkinScanner:
    """
    Scanner for Gherkin .feature files.

    Parses .feature files and extracts scenarios in a format
    compatible with the kernel behavior schema.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize scanner.

        Args:
            base_path: Base directory for relative path resolution
        """
        self.base_path = base_path or Path.cwd()

    def scan_file(self, file_path: Path) -> Optional[Feature]:
        """
        Parse a single .feature file.

        Args:
            file_path: Path to .feature file

        Returns:
            Feature object or None if parsing fails
        """
        try:
            content = file_path.read_text()
            return self._parse_content(content, file_path)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None

    def scan_directory(self, directory: Path) -> List[Feature]:
        """
        Scan a directory for .feature files.

        Args:
            directory: Directory to scan

        Returns:
            List of parsed Feature objects
        """
        features = []
        feature_files = list(directory.glob('**/*.feature'))

        for file_path in feature_files:
            feature = self.scan_file(file_path)
            if feature:
                features.append(feature)

        return features

    def _parse_content(self, content: str, file_path: Optional[Path] = None) -> Optional[Feature]:
        """Parse Gherkin content into a Feature object."""
        lines = content.split('\n')

        feature_name = ''
        feature_desc = []
        background_given: List[str] = []
        scenarios: List[Scenario] = []

        current_scenario: Optional[Scenario] = None
        current_section = None  # 'feature', 'background', 'scenario'
        last_step_type = None  # 'given', 'when', 'then' for And/But
        in_description = False

        for line in lines:
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Feature line
            if stripped.startswith('Feature:'):
                feature_name = stripped[8:].strip()
                current_section = 'feature'
                in_description = True
                continue

            # Background
            if stripped.startswith('Background:'):
                current_section = 'background'
                in_description = False
                continue

            # Scenario or Scenario Outline
            if stripped.startswith('Scenario:') or stripped.startswith('Scenario Outline:'):
                in_description = False
                # Save previous scenario
                if current_scenario:
                    scenarios.append(current_scenario)

                if stripped.startswith('Scenario Outline:'):
                    name = stripped[17:].strip()
                else:
                    name = stripped[9:].strip()
                current_scenario = Scenario(name=name)
                current_section = 'scenario'
                last_step_type = None
                continue

            # Given step
            if stripped.startswith('Given '):
                step_text = stripped[6:].strip()
                last_step_type = 'given'
                if current_section == 'background':
                    background_given.append(step_text)
                elif current_scenario:
                    current_scenario.given.append(step_text)
                continue

            # When step
            if stripped.startswith('When '):
                step_text = stripped[5:].strip()
                last_step_type = 'when'
                if current_scenario:
                    current_scenario.when.append(step_text)
                continue

            # Then step
            if stripped.startswith('Then '):
                step_text = stripped[5:].strip()
                last_step_type = 'then'
                if current_scenario:
                    current_scenario.then.append(step_text)
                continue

            # And step (continues previous step type)
            if stripped.startswith('And '):
                step_text = stripped[4:].strip()
                if current_section == 'background' and last_step_type == 'given':
                    background_given.append(step_text)
                elif current_scenario and last_step_type:
                    if last_step_type not in current_scenario.and_steps:
                        current_scenario.and_steps[last_step_type] = []
                    current_scenario.and_steps[last_step_type].append(step_text)
                continue

            # But step (same as And, continues previous)
            if stripped.startswith('But '):
                step_text = stripped[4:].strip()
                if current_scenario and last_step_type:
                    if last_step_type not in current_scenario.and_steps:
                        current_scenario.and_steps[last_step_type] = []
                    current_scenario.and_steps[last_step_type].append(step_text)
                continue

            # Feature description (lines after Feature: before first section)
            if in_description and current_section == 'feature':
                feature_desc.append(stripped)

        # Don't forget the last scenario
        if current_scenario:
            scenarios.append(current_scenario)

        if not feature_name:
            return None

        return Feature(
            name=feature_name,
            description='\n'.join(feature_desc),
            file_path=file_path,
            background_given=background_given,
            scenarios=scenarios,
        )

    def generate_report(self, features: List[Feature]) -> str:
        """Generate a summary report of scanned features."""
        lines = ['GHERKIN SCAN REPORT', '=' * 50]

        total_scenarios = sum(len(f.scenarios) for f in features)
        lines.append(f'Files scanned: {len(features)}')
        lines.append(f'Total scenarios: {total_scenarios}')
        lines.append('')

        for feature in features:
            lines.append(f'Feature: {feature.name}')
            if feature.file_path:
                lines.append(f'  File: {feature.file_path.name}')
            lines.append(f'  Scenarios: {len(feature.scenarios)}')

            for scenario in feature.scenarios:
                lines.append(f'    - {scenario.name}')
                lines.append(f'      ID: {scenario.id}')
            lines.append('')

        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_scan_features(directory: str = 'tests/features') -> str:
    """
    Scan .feature files and report on test scenarios.

    Args:
        directory: Directory containing .feature files (relative to chora-store)

    Returns:
        Report of all scenarios found
    """
    from pathlib import Path

    # Resolve relative to chora-store package
    base = Path(__file__).parent.parent.parent.parent  # chora-store root
    target_dir = base / directory

    if not target_dir.exists():
        return f"Directory not found: {target_dir}"

    scanner = GherkinScanner(base)
    features = scanner.scan_directory(target_dir)

    if not features:
        return f"No .feature files found in {directory}"

    return scanner.generate_report(features)


def tool_extract_behaviors(feature_file: str) -> str:
    """
    Extract behaviors from a specific .feature file in kernel format.

    Args:
        feature_file: Path to .feature file (relative to chora-store)

    Returns:
        YAML-formatted behaviors ready for entity injection
    """
    from pathlib import Path
    import yaml

    base = Path(__file__).parent.parent.parent.parent
    file_path = base / feature_file

    if not file_path.exists():
        return f"File not found: {file_path}"

    scanner = GherkinScanner(base)
    feature = scanner.scan_file(file_path)

    if not feature:
        return f"Failed to parse: {feature_file}"

    behaviors = feature.to_behaviors()

    lines = [f'# Behaviors extracted from {feature_file}',
             f'# Feature: {feature.name}',
             f'# Suggested entity: {feature.id}',
             '',
             'behaviors:']

    for b in behaviors:
        lines.append(yaml.dump([b], default_flow_style=False, indent=2))

    return '\n'.join(lines)
