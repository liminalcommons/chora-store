import yaml
from pathlib import Path
from ..models import Entity
from ..repository import Repository


class Bond:
    """
    The Loom.
    Creates Tension (Force) between Matter.
    """
    def __init__(self, repo: Repository):
        self.repo = repo
        self.rules = self._load_rules()

    def _load_rules(self):
        current_file = Path(__file__)
        repo_root = current_file.parents[5]
        path = repo_root / "packages" / "chora-kernel" / "standards" / "bonds.yaml"
        if not path.exists():
            path = current_file.parents[3] / "chora-kernel" / "standards" / "bonds.yaml"

        if not path.exists():
            # Fallback
            return {
                'yields': {'source': 'inquiry', 'target': 'learning', 'physics': 'Exploration produces insight'},
                'surfaces': {'source': 'learning', 'target': 'principle', 'physics': 'Insight reveals truth'},
                'clarifies': {'source': 'principle', 'target': 'story', 'physics': 'Truth clarifies desire'},
                'specifies': {'source': 'story', 'target': 'behavior', 'physics': 'Desire becomes expectation'},
                'implements': {'source': 'behavior', 'target': 'tool', 'physics': 'Expectation becomes capability'},
                'verifies': {'source': 'tool', 'target': 'behavior', 'physics': 'Capability proves expectation'},
                'crystallized-from': {'source': 'any', 'target': 'any', 'physics': 'Provenance'}
            }

        with open(path) as f:
            return yaml.safe_load(f)['bonds']

    def run(self, verb: str, from_id: str, to_id: str) -> Entity:
        """
        Operator: BOND
        Creates a Relationship entity representing force.
        """
        # 1. Validate The Force
        rule = self.rules.get(verb)
        if not rule:
            raise ValueError(f"Unknown Force: '{verb}'. Valid forces: {list(self.rules.keys())}")

        # 2. Validate The Matter
        source = self.repo.get(from_id)
        target = self.repo.get(to_id)

        if not source:
            raise ValueError(f"Source entity not found: {from_id}")
        if not target:
            raise ValueError(f"Target entity not found: {to_id}")

        # 3. Validate Physics
        if rule['source'] != 'any' and source.type != rule['source']:
            raise ValueError(f"Physics Violation: '{verb}' bond requires source type '{rule['source']}', got '{source.type}'")

        if rule['target'] != 'any' and target.type != rule['target']:
            raise ValueError(f"Physics Violation: '{verb}' bond requires target type '{rule['target']}', got '{target.type}'")

        # 4. Manifest The Bond
        from_slug = source.slug[:15]
        to_slug = target.slug[:15]
        bond_id = f"relationship-{verb}-{from_slug}-to-{to_slug}"

        entity = Entity(
            id=bond_id,
            type='relationship',
            status='active',
            title=f"{verb} bond",
            data={
                'relationship_type': verb,
                'from_id': from_id,
                'to_id': to_id,
                'physics': rule['physics']
            }
        )

        return self.repo.save(entity)
