from ..models import Entity
from ..repository import Repository
from .manifest import Manifest
from .bond import Bond


class Transmute:
    """
    The Metabolism.
    Handles state changes and phase transitions via Manifest+Bond sequences.
    """
    def __init__(self, repo: Repository):
        self.repo = repo
        self.manifest = Manifest(repo)
        self.bond = Bond(repo)

    def run(self, source_id: str, operation: str, **kwargs) -> Entity:
        """
        Operator: TRANSMUTE
        Execute a phase transition.
        """
        source = self.repo.get(source_id)
        if not source:
            raise ValueError(f"Entity not found: {source_id}")

        method = getattr(self, f"_op_{operation}", None)
        if not method:
            raise ValueError(f"Unknown transmutation: {operation}")

        return method(source, **kwargs)

    def _op_crystallize(self, source: Entity) -> Entity:
        """Inquiry (Gas) -> Story (Clarity)"""
        if source.type != 'inquiry':
            raise ValueError("Only Inquiries can crystallize.")

        story = self.manifest.run(
            type='story',
            title=source.title,
            description=f"Crystallized from {source.id}. {source.data.get('description', '')}"
        )
        self.bond.run('crystallized-from', story.id, source.id)
        return story

    def _op_extract(self, source: Entity) -> Entity:
        """Learning (Radiation) -> Principle (Crystal)"""
        if source.type != 'learning':
            raise ValueError("Only Learnings can have principles extracted.")

        principle = self.manifest.run(
            type='principle',
            title=f"Principle from {source.slug}",
            statement=source.data.get('insight', 'Extracted truth'),
            context=f"Extracted from {source.id}"
        )
        self.bond.run('surfaces', source.id, principle.id)
        return principle

    def _op_specialize(self, source: Entity, title: str = None) -> Entity:
        """Story (Clarity) -> Behavior (Solid)"""
        if source.type != 'story':
            raise ValueError("Only Stories can specify Behaviors.")

        behavior = self.manifest.run(
            type='behavior',
            title=title or f"Behavior for {source.slug}",
            given="Context",
            when="Action",
            then="Result"
        )
        self.bond.run('specifies', source.id, behavior.id)
        return behavior

    def _op_update_status(self, source: Entity, new_status: str = None) -> Entity:
        """Update entity status."""
        if not new_status:
            raise ValueError("new_status is required for update_status operation")

        source.status = new_status
        return self.repo.save(source)
