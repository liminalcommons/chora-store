"""
Vitality Sensing - Multi-level health metrics for the system.

Four levels of sensing:
1. Entity vitality - Is this thing alive/moving?
2. System integrity - Ratio of stable to drifting
3. Graph coherence - Are relationships valid?
4. Metabolic health - Are learnings becoming patterns?

These metrics are observer-detectable. No LLM judgment required.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .repository import EntityRepository


@dataclass
class EntityVitality:
    """Vitality assessment for a single entity."""
    entity_id: str
    entity_type: str
    status: str
    days_in_state: int
    is_stagnant: bool
    stagnation_reason: Optional[str] = None


@dataclass
class SystemIntegrity:
    """System-level integrity metrics."""
    total_features: int
    stable_features: int
    drifting_features: int
    integrity_score: float  # stable / (stable + drifting + active)
    season: str  # 'construction' or 'restoration'


@dataclass
class MetabolicHealth:
    """Metabolic health - learning → pattern conversion."""
    total_learnings: int
    captured_learnings: int  # not yet applied
    applied_learnings: int
    total_patterns: int
    proposed_patterns: int
    adopted_patterns: int
    digestion_rate: float  # applied / total learnings
    crystallization_rate: float  # adopted / total patterns


@dataclass
class VitalityReport:
    """Complete vitality report across all levels."""
    timestamp: datetime
    entity_vitality: List[EntityVitality]
    system_integrity: SystemIntegrity
    metabolic_health: MetabolicHealth
    stagnant_entities: List[EntityVitality]
    attention_needed: List[str]


# Stagnation thresholds (days in state before considered stagnant)
STAGNATION_THRESHOLDS = {
    'feature': {
        'nascent': 14,       # 2 weeks to start converging
        'converging': 21,    # 3 weeks to stabilize
        'stable': None,      # stable is fine forever
        'drifting': 7,       # 1 week to address drift
        'finalizing': 7,     # 1 week to complete finalization
    },
    'inquiry': {
        'active': 30,        # 1 month to resolve or reify
        'held': None,        # held is intentional
        'resolved': None,
        'reified': None,
    },
    'task': {
        'pending': 7,        # 1 week to start
        'active': 3,         # 3 days to complete
        'blocked': 7,        # 1 week to unblock
        'complete': None,
    },
    'learning': {
        'captured': 30,      # 1 month to validate
        'validated': 60,     # 2 months to apply
        'applied': None,
    },
    'pattern': {
        'proposed': 30,      # 1 month to adopt or reject
        'adopted': None,
        'deprecated': None,
    },
    'release': {
        'planned': 30,       # 1 month to release
        'released': None,
        'deprecated': None,
    },
}


class VitalitySensor:
    """
    Senses health at multiple levels.

    Usage:
        sensor = VitalitySensor(repository)
        report = sensor.full_report()
    """

    def __init__(self, repository: Optional[EntityRepository] = None):
        self.repo = repository or EntityRepository()

    def assess_entity(self, entity) -> EntityVitality:
        """Assess vitality of a single entity."""
        now = datetime.utcnow()
        updated = entity.updated_at
        days_in_state = (now - updated).days

        # Check stagnation threshold
        thresholds = STAGNATION_THRESHOLDS.get(entity.type, {})
        threshold = thresholds.get(entity.status)

        is_stagnant = False
        stagnation_reason = None

        if threshold is not None and days_in_state > threshold:
            is_stagnant = True
            stagnation_reason = f"{days_in_state}d in {entity.status} (threshold: {threshold}d)"

        return EntityVitality(
            entity_id=entity.id,
            entity_type=entity.type,
            status=entity.status,
            days_in_state=days_in_state,
            is_stagnant=is_stagnant,
            stagnation_reason=stagnation_reason,
        )

    def assess_system_integrity(self) -> SystemIntegrity:
        """Calculate system-level integrity."""
        features = self.repo.list(entity_type='feature', limit=1000)

        total = len(features)
        stable = sum(1 for f in features if f.status == 'stable')
        drifting = sum(1 for f in features if f.status == 'drifting')
        active = sum(1 for f in features if f.status in ('nascent', 'converging'))

        # Integrity = stable / (stable + drifting + active)
        # High integrity means most features are stable, few are drifting
        denominator = stable + drifting + active
        if denominator == 0:
            integrity_score = 1.0  # No features = perfect integrity (vacuously)
        else:
            integrity_score = stable / denominator

        # Season: restoration if too much drift, construction otherwise
        if total > 0:
            drift_ratio = drifting / total
            season = 'restoration' if drift_ratio > 0.3 or integrity_score < 0.7 else 'construction'
        else:
            season = 'construction'

        return SystemIntegrity(
            total_features=total,
            stable_features=stable,
            drifting_features=drifting,
            integrity_score=integrity_score,
            season=season,
        )

    def assess_metabolic_health(self) -> MetabolicHealth:
        """Calculate metabolic health - learning to pattern conversion."""
        learnings = self.repo.list(entity_type='learning', limit=1000)
        patterns = self.repo.list(entity_type='pattern', limit=1000)

        total_learnings = len(learnings)
        captured = sum(1 for l in learnings if l.status == 'captured')
        validated = sum(1 for l in learnings if l.status == 'validated')
        applied = sum(1 for l in learnings if l.status == 'applied')

        total_patterns = len(patterns)
        proposed = sum(1 for p in patterns if p.status == 'proposed')
        adopted = sum(1 for p in patterns if p.status == 'adopted')

        # Digestion rate: how much of what we learn gets applied?
        digestion_rate = applied / total_learnings if total_learnings > 0 else 1.0

        # Crystallization rate: how many proposed patterns become adopted?
        crystallization_rate = adopted / total_patterns if total_patterns > 0 else 1.0

        return MetabolicHealth(
            total_learnings=total_learnings,
            captured_learnings=captured,
            applied_learnings=applied,
            total_patterns=total_patterns,
            proposed_patterns=proposed,
            adopted_patterns=adopted,
            digestion_rate=digestion_rate,
            crystallization_rate=crystallization_rate,
        )

    def full_report(self) -> VitalityReport:
        """Generate complete vitality report."""
        now = datetime.utcnow()

        # Assess all entities
        all_entities = self.repo.list(limit=1000)
        entity_assessments = [self.assess_entity(e) for e in all_entities]

        # Find stagnant entities
        stagnant = [v for v in entity_assessments if v.is_stagnant]

        # System integrity
        integrity = self.assess_system_integrity()

        # Metabolic health
        metabolism = self.assess_metabolic_health()

        # Build attention list
        attention = []

        # Stagnant entities need attention
        for s in stagnant:
            attention.append(f"{s.entity_id}: {s.stagnation_reason}")

        # Low integrity needs attention
        if integrity.integrity_score < 0.7:
            attention.append(f"System integrity low: {integrity.integrity_score:.0%}")

        # Drifting features need attention
        if integrity.drifting_features > 0:
            attention.append(f"{integrity.drifting_features} feature(s) drifting")

        # Metabolic issues
        if metabolism.digestion_rate < 0.5 and metabolism.total_learnings > 3:
            attention.append(f"Metabolic drift: {metabolism.captured_learnings} undigested learnings")

        return VitalityReport(
            timestamp=now,
            entity_vitality=entity_assessments,
            system_integrity=integrity,
            metabolic_health=metabolism,
            stagnant_entities=stagnant,
            attention_needed=attention,
        )

    def summary(self) -> Dict[str, Any]:
        """Return a simple summary dict for orient."""
        report = self.full_report()

        return {
            'integrity_score': report.system_integrity.integrity_score,
            'season': report.system_integrity.season,
            'features': {
                'total': report.system_integrity.total_features,
                'stable': report.system_integrity.stable_features,
                'drifting': report.system_integrity.drifting_features,
            },
            'metabolism': {
                'learnings': report.metabolic_health.total_learnings,
                'undigested': report.metabolic_health.captured_learnings,
                'patterns': report.metabolic_health.total_patterns,
                'digestion_rate': report.metabolic_health.digestion_rate,
            },
            'stagnant_count': len(report.stagnant_entities),
            'stagnant': [
                {'id': s.entity_id, 'reason': s.stagnation_reason}
                for s in report.stagnant_entities[:5]  # Top 5
            ],
            'attention': report.attention_needed[:5],  # Top 5
        }
