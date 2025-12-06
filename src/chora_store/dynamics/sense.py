from typing import Dict, Any, List
from ..repository import Repository
from ..physics import PhysicsEngine


class Sense:
    """
    The Observer.
    Reads the tension network to report Vitality.
    """
    def __init__(self, repo: Repository):
        self.repo = repo
        self.physics = PhysicsEngine(repo)

    def orient(self) -> Dict[str, Any]:
        """
        Global System Sense.
        Returns the vitality report.
        """
        drifting_states = self.physics.scan_for_drift()
        active_focus = self.repo.list(type='focus', status='active', limit=5)
        recent_inquiries = self.repo.list(type='inquiry', status='active', limit=5)
        system_integrity = self.physics.compute_system_integrity()

        # Count entities by type
        entity_counts = {}
        for t in ['inquiry', 'learning', 'principle', 'story', 'behavior', 'tool', 'focus', 'relationship']:
            entity_counts[t] = self.repo.count(type=t)

        return {
            "vitality": "construction" if len(drifting_states) == 0 else "restoration",
            "integrity": system_integrity,
            "drift_count": len(drifting_states),
            "drifting_entities": [s.entity_id for s in drifting_states],
            "active_focus": [f.title for f in active_focus],
            "open_inquiries": [i.title for i in recent_inquiries],
            "entity_counts": entity_counts
        }

    def constellation(self, center_id: str) -> Dict[str, Any]:
        """
        Local Physics Sense.
        Maps the immediate tension network around an entity.
        """
        entity = self.repo.get(center_id)
        if not entity:
            raise ValueError(f"Entity not found: {center_id}")

        upstream = self.repo.get_bonds_to(center_id)
        downstream = self.repo.get_bonds_from(center_id)
        state = self.physics.compute_state(entity)

        result = {
            "entity": entity.to_dict(),
            "physics": {
                "stability": state.stability,
                "integrity": state.integrity,
            },
            "network": {
                "upstream": [self._fmt_bond(b, "from") for b in upstream],
                "downstream": [self._fmt_bond(b, "to") for b in downstream]
            }
        }

        # If this is a Focus, attach its narrative chain (Trajectory)
        if entity.type == "focus":
            chain = self.repo.get_focus_chain(entity.id)
            # Index 0 is self, skip it
            if len(chain) > 1:
                result["trajectory"] = [e.to_dict() for e in chain[1:]]

        return result

    def scan_voids(self) -> List[str]:
        """
        Detect Generative Voids (Negative Space).
        Finds entities that break the Generative Chain (stuck potential).
        """
        voids = []

        # 1. Inquiries that yielded nothing (Stuck Gas)
        inquiries = self.repo.list(type='inquiry', status='active')
        for i in inquiries:
            bonds = self.repo.get_bonds_from(i.id)
            if not any(b.data.get('relationship_type') == 'yields' for b in bonds):
                voids.append(f"💭 {i.title} (Has not yielded Learning)")

        # 2. Stories that specify nothing (Vague Desire)
        stories = self.repo.list(type='story', status='emerging')
        for s in stories:
            bonds = self.repo.get_bonds_from(s.id)
            if not any(b.data.get('relationship_type') == 'specifies' for b in bonds):
                voids.append(f"📖 {s.title} (Does not specify Behavior)")

        # 3. Behaviors not implemented (Dream Logic)
        behaviors = self.repo.list(type='behavior', status='untested')
        for b in behaviors:
            bonds = self.repo.get_bonds_from(b.id)
            if not any(bd.data.get('relationship_type') == 'implements' for bd in bonds):
                voids.append(f"🧪 {b.title} (Not implemented by Tool)")

        return voids

    def _fmt_bond(self, bond, direction):
        target_id = bond.data.get(f'{direction}_id')
        target = self.repo.get(target_id)
        return {
            "bond": bond.data.get('relationship_type'),
            "target": target.title if target else "Unknown",
            "target_id": target_id,
            "status": bond.status
        }
