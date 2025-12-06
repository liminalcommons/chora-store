import yaml
import re
from pathlib import Path
from typing import Dict, Any
from ..models import Entity
from ..repository import Repository


class Manifest:
    """
    The Factory.
    Enforces Structural Governance by validating against the Kernel.
    """
    def __init__(self, repo: Repository):
        self.repo = repo
        self.schema = self._load_schema()

    def _load_schema(self) -> Dict[str, Any]:
        # Find kernel relative to this package
        current_file = Path(__file__)
        repo_root = current_file.parents[5]
        kernel_path = repo_root / "packages" / "chora-kernel" / "standards" / "entity.yaml"

        if not kernel_path.exists():
            kernel_path = current_file.parents[3] / "chora-kernel" / "standards" / "entity.yaml"

        if not kernel_path.exists():
            # Minimal fallback if kernel package missing (bootstrap mode)
            print(f"WARN: Kernel schema not found at {kernel_path}. Using internal fallback.")
            return {'types': {
                'inquiry': {}, 'story': {}, 'tool': {}, 'behavior': {},
                'principle': {}, 'learning': {}, 'focus': {}, 'relationship': {}
            }}

        with open(kernel_path) as f:
            return yaml.safe_load(f)

    def _slugify(self, text: str) -> str:
        slug = text.lower().strip()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        return slug[:50]  # Max 50 chars for slug

    def run(self, type: str, title: str, **kwargs) -> Entity:
        """
        Operator: MANIFEST
        Creates an entity from Eidos.
        """
        type_def = self.schema['types'].get(type)
        if not type_def:
            raise ValueError(f"Unknown Eidos: '{type}'. Valid types: {list(self.schema['types'].keys())}")

        # 1. Generate Semantic ID
        slug = self._slugify(title)
        entity_id = f"{type}-{slug}"

        # 2. Determine Initial Status
        default_statuses = {
            'inquiry': 'active',
            'story': 'emerging',
            'tool': 'active',
            'learning': 'captured',
            'principle': 'proposed',
            'behavior': 'untested',
            'focus': 'active',
            'relationship': 'active'
        }
        status = kwargs.pop('status', default_statuses.get(type, 'active'))

        # 3. Construct
        entity = Entity(
            id=entity_id,
            type=type,
            status=status,
            title=title,
            data=kwargs
        )

        # 4. Persist
        return self.repo.save(entity)
