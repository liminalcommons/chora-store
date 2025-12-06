from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .models import Entity
from .repository import Repository


@dataclass
class TensegrityState:
    entity_id: str
    stability: str  # "stable", "drifting", "floating"
    integrity: float  # 0.0 to 1.0
    stressed_bonds: List[str] = field(default_factory=list)
    supporting_entities: int = 0


@dataclass
class DriftCascade:
    """Represents an entity affected by cascading drift."""
    entity_id: str
    entity_type: str
    drift_distance: int  # 0 = directly drifting, 1+ = affected by cascade


class PhysicsEngine:
    """
    The Laws of Physics.
    Computes structural integrity from the tension network.

    Law 1: Stability is Computed, Not Declared
    Law 2: Tension is Transitive (Stories feel their Behaviors)
    Law 3: Gravity pulls drifting entities down
    """
    def __init__(self, repo: Repository):
        self.repo = repo

    def compute_state(self, entity: Entity, _depth: int = 0) -> TensegrityState:
        """
        Compute the tensegrity state of an entity.

        Direct Tension: Behaviors are stable if their verifies bonds are active.
        Transitive Tension: Stories are stable if their specified Behaviors are stable.
        """
        # Prevent infinite recursion
        if _depth > 3:
            return TensegrityState(entity.id, "floating", 0.0, [])

        # 1. Direct Tension (for Behaviors)
        # Check incoming 'verifies' bonds
        incoming = self.repo.get_bonds_to(entity.id)
        verifies_bonds = [b for b in incoming if b.data.get('relationship_type') == 'verifies']

        if verifies_bonds:
            stressed = [b for b in verifies_bonds if b.status != 'active']
            if stressed:
                integrity = 1.0 - (len(stressed) / len(verifies_bonds))
                return TensegrityState(entity.id, "drifting", integrity, [b.id for b in stressed])
            return TensegrityState(entity.id, "stable", 1.0, [])

        # 2. Transitive Tension (for Stories)
        # Check outgoing 'specifies' bonds -> Behaviors
        outgoing = self.repo.get_bonds_from(entity.id)
        specifies_bonds = [b for b in outgoing if b.data.get('relationship_type') == 'specifies']

        if specifies_bonds:
            # The Story relies on the stability of its Behaviors
            behaviors_count = len(specifies_bonds)
            stable_behaviors = 0
            stressed_paths = []

            for bond in specifies_bonds:
                behavior_id = bond.data.get('to_id')
                if not behavior_id:
                    continue

                behavior = self.repo.get(behavior_id)
                if not behavior:
                    continue

                # Recursive check (with depth limit)
                b_state = self.compute_state(behavior, _depth + 1)
                if b_state.stability == "stable":
                    stable_behaviors += 1
                elif b_state.stability == "drifting":
                    stressed_paths.append(f"{behavior_id}->stressed")
                else:  # floating
                    stressed_paths.append(f"{behavior_id}->unverified")

            if not stressed_paths:
                return TensegrityState(entity.id, "stable", 1.0, [], behaviors_count)

            integrity = stable_behaviors / behaviors_count if behaviors_count > 0 else 0.0
            return TensegrityState(entity.id, "drifting", integrity, stressed_paths, behaviors_count)

        # 3. Default State (Untethered)
        return TensegrityState(entity.id, "floating", 0.0, [])

    def scan_for_drift(self) -> List[TensegrityState]:
        """
        Global Observer.
        Scans the universe for entities defying gravity.
        Now includes Stories (transitive) and Behaviors (direct).
        """
        drifting = []

        # Scan Stories (Higher Order - Transitive Tension)
        stories = self.repo.list(type='story', limit=1000)
        for story in stories:
            state = self.compute_state(story)
            if state.stability == "drifting":
                drifting.append(state)

        # Scan Behaviors (Ground Truth - Direct Tension)
        behaviors = self.repo.list(type='behavior', limit=1000)
        for behavior in behaviors:
            state = self.compute_state(behavior)
            if state.stability == "drifting":
                drifting.append(state)

        return drifting

    def compute_system_integrity(self) -> float:
        """
        System-wide integrity calculation.
        Ratio of active verifies bonds to total verifies bonds.
        """
        relationships = self.repo.list(type='relationship', limit=10000)
        verifies_bonds = [r for r in relationships if r.data.get('relationship_type') == 'verifies']

        if not verifies_bonds:
            return 1.0  # No bonds = pristine (empty universe)

        active = len([b for b in verifies_bonds if b.status == 'active'])
        return active / len(verifies_bonds)

    def compute_cascading_drift(self, max_depth: int = 10) -> List[DriftCascade]:
        """
        Compute cascading drift through the bond network using recursive CTE.

        This uses the database directly for deep dependency checking.
        Returns all entities affected by drift, with their distance from
        the source of drift.

        Law: Drift propagates up the chain
        - A drifting behavior affects its specifying story
        - A stressed verifies bond affects the verified behavior

        Args:
            max_depth: Maximum cascade depth to prevent infinite recursion

        Returns:
            List of DriftCascade objects, sorted by drift_distance
        """
        p = self.repo._adapter.param

        # Recursive CTE to find cascading drift through specifies/verifies bonds
        query = f"""
        WITH RECURSIVE drift_cascade AS (
            -- Base case: directly drifting behaviors
            SELECT id, type, 0 as depth
            FROM entities
            WHERE type = 'behavior' AND status = 'drifting'

            UNION ALL

            -- Recursive case: entities connected via specifies/verifies bonds
            SELECT e.id, e.type, dc.depth + 1
            FROM entities e
            JOIN entities rel ON rel.type = 'relationship'
            JOIN drift_cascade dc ON {self.repo._adapter.json_extract('rel.data', 'to_id')} = dc.id
            WHERE {self.repo._adapter.json_extract('rel.data', 'from_id')} = e.id
              AND {self.repo._adapter.json_extract('rel.data', 'relationship_type')} IN ('specifies', 'verifies')
              AND dc.depth < {p}
        )
        SELECT DISTINCT id, type, MIN(depth) as drift_distance
        FROM drift_cascade
        GROUP BY id, type
        ORDER BY drift_distance ASC;
        """

        with self.repo._adapter.connection() as conn:
            cursor = self.repo._adapter.execute(conn, query, (max_depth,))
            rows = self.repo._adapter.fetchall(cursor)

            return [
                DriftCascade(
                    entity_id=row['id'],
                    entity_type=row['type'],
                    drift_distance=row['drift_distance']
                )
                for row in rows
            ]

    def get_affected_by_drift(self, entity_id: str, max_depth: int = 10) -> List[DriftCascade]:
        """
        Find all entities affected if a specific entity were to drift.

        This is useful for impact analysis: "What would break if this behavior drifted?"

        Args:
            entity_id: The entity to analyze
            max_depth: Maximum cascade depth

        Returns:
            List of entities that would be affected
        """
        p = self.repo._adapter.param

        query = f"""
        WITH RECURSIVE impact_cascade AS (
            -- Base case: the entity we're analyzing
            SELECT id, type, 0 as depth
            FROM entities
            WHERE id = {p}

            UNION ALL

            -- Recursive case: find entities that depend on this one
            SELECT e.id, e.type, ic.depth + 1
            FROM entities e
            JOIN entities rel ON rel.type = 'relationship'
            JOIN impact_cascade ic ON {self.repo._adapter.json_extract('rel.data', 'to_id')} = ic.id
            WHERE {self.repo._adapter.json_extract('rel.data', 'from_id')} = e.id
              AND {self.repo._adapter.json_extract('rel.data', 'relationship_type')} IN ('specifies', 'verifies')
              AND ic.depth < {p}
        )
        SELECT DISTINCT id, type, MIN(depth) as drift_distance
        FROM impact_cascade
        WHERE id != {p}  -- Exclude the starting entity
        GROUP BY id, type
        ORDER BY drift_distance ASC;
        """

        with self.repo._adapter.connection() as conn:
            cursor = self.repo._adapter.execute(conn, query, (entity_id, max_depth, entity_id))
            rows = self.repo._adapter.fetchall(cursor)

            return [
                DriftCascade(
                    entity_id=row['id'],
                    entity_type=row['type'],
                    drift_distance=row['drift_distance']
                )
                for row in rows
            ]
