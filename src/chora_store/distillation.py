"""
Distillation Service - Same-type consolidation of entities.

This module implements the Distillation interface from the kernel:
  Entities[] of type T → Fewer Entities of type T

Distillation is type-preserving semantic consolidation:
- Multiple learnings become one canonical learning
- Multiple inquiries become one canonical inquiry
- Source entities are marked 'subsumed' with provenance

The service uses vector embeddings for semantic clustering and
an LLM for synthesis. Human approval is always required.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging

from .models import Entity

logger = logging.getLogger(__name__)


@dataclass
class DistillationCandidate:
    """A cluster of entities proposed for distillation."""
    cluster_id: str
    entity_type: str
    source_entities: List[Entity]
    similarity_scores: Dict[str, float]  # entity_id -> avg similarity
    domain: str
    proposed_name: str
    proposed_insight: str
    confidence: float  # 0.0 to 1.0


@dataclass
class DistillationProposal:
    """A proposal to distill entities into a canonical form."""
    cluster_id: str
    canonical_name: str
    canonical_insight: str
    source_ids: List[str]
    domain: str
    confidence: float
    preserves: List[str]  # Unique aspects to preserve
    reasoning: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DistillationService:
    """
    Service for finding and executing distillation opportunities.

    Usage:
        service = DistillationService(repository)
        candidates = service.find_distillation_candidates('learning')

        for candidate in candidates:
            if candidate.confidence >= 0.7:
                proposal = service.synthesize_proposal(candidate)
                # Human reviews proposal...
                service.apply_distillation(proposal)
    """

    def __init__(
        self,
        repository: "EntityRepository",
        similarity_threshold: float = 0.60,
        min_cluster_size: int = 2,
    ):
        """
        Initialize the distillation service.

        Args:
            repository: EntityRepository for data access
            similarity_threshold: Minimum cosine similarity to cluster (default 0.60)
            min_cluster_size: Minimum entities to form a cluster (default 2)
        """
        self.repository = repository
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Lazy-load the embedding service."""
        if self._embedding_service is None:
            from .embeddings import EmbeddingService
            self._embedding_service = EmbeddingService(self.repository.db_path)
        return self._embedding_service

    def find_distillation_candidates(
        self,
        entity_type: str,
        domain: Optional[str] = None,
        limit: int = 100,
    ) -> List[DistillationCandidate]:
        """
        Find clusters of semantically similar entities for distillation.

        Args:
            entity_type: Type of entity to cluster (learning, inquiry, pattern, feature)
            domain: Optional domain filter
            limit: Maximum entities to analyze

        Returns:
            List of DistillationCandidate clusters
        """
        # Load entities (exclude already-subsumed)
        entities = self._load_distillable_entities(entity_type, domain, limit)

        if len(entities) < self.min_cluster_size:
            logger.info(f"Not enough {entity_type}s to distill ({len(entities)})")
            return []

        # Batch compute embeddings for efficiency
        self.embedding_service.batch_embed_entities(entities)

        # Cluster by semantic similarity
        clusters = self.embedding_service.cluster_by_similarity(
            entities,
            threshold=self.similarity_threshold
        )

        # Convert to candidates, filtering by size
        candidates = []
        for i, cluster in enumerate(clusters):
            if len(cluster) >= self.min_cluster_size:
                candidate = self._create_candidate(
                    cluster_id=f"distill-{entity_type}-{i}",
                    entities=cluster,
                    entity_type=entity_type,
                )
                candidates.append(candidate)

        # Sort by confidence (higher = better distillation opportunity)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        return candidates

    def _load_distillable_entities(
        self,
        entity_type: str,
        domain: Optional[str],
        limit: int,
    ) -> List[Entity]:
        """Load entities that can be distilled (not already subsumed)."""
        entities = self.repository.list(
            entity_type=entity_type,
            limit=limit * 2  # Get extra to filter subsumed
        )

        # Filter out subsumed entities
        distillable = [
            e for e in entities
            if e.status != 'subsumed'
            and not e.data.get('subsumed_by')
        ]

        # Filter by domain if specified
        if domain:
            distillable = [
                e for e in distillable
                if e.data.get('domain') == domain
            ]

        return distillable[:limit]

    def _create_candidate(
        self,
        cluster_id: str,
        entities: List[Entity],
        entity_type: str,
    ) -> DistillationCandidate:
        """Create a distillation candidate from a cluster."""
        # Calculate pairwise similarities
        similarity_scores = {}
        for entity in entities:
            total_sim = 0.0
            for other in entities:
                if entity.id != other.id:
                    emb1 = self.embedding_service.get_or_create_embedding(entity)
                    emb2 = self.embedding_service.get_or_create_embedding(other)
                    total_sim += self.embedding_service.cosine_similarity(emb1, emb2)
            avg_sim = total_sim / (len(entities) - 1) if len(entities) > 1 else 1.0
            similarity_scores[entity.id] = avg_sim

        # Extract common domain
        domains = [e.data.get('domain', 'general') for e in entities]
        common_domain = max(set(domains), key=domains.count)

        # Extract names for proposed synthesis
        names = [e.data.get('name', e.id) for e in entities]
        insights = [e.data.get('insight', e.data.get('description', '')) for e in entities]

        # Simple synthesis: find common theme
        proposed_name = self._find_common_theme(names)
        proposed_insight = self._combine_insights(insights)

        # Calculate confidence based on average similarity
        avg_similarity = sum(similarity_scores.values()) / len(similarity_scores)
        confidence = min(avg_similarity, 1.0)

        return DistillationCandidate(
            cluster_id=cluster_id,
            entity_type=entity_type,
            source_entities=entities,
            similarity_scores=similarity_scores,
            domain=common_domain,
            proposed_name=proposed_name,
            proposed_insight=proposed_insight,
            confidence=confidence,
        )

    def _find_common_theme(self, names: List[str]) -> str:
        """Find common theme from entity names."""
        if not names:
            return "Unnamed cluster"

        # Simple approach: use the shortest name as base
        names = [n for n in names if n]
        if not names:
            return "Unnamed cluster"

        # Find common words
        from collections import Counter
        words = []
        for name in names:
            words.extend(name.lower().split())

        common = Counter(words).most_common(3)
        if common:
            return " ".join(word.title() for word, _ in common)

        return names[0][:50]

    def _combine_insights(self, insights: List[str]) -> str:
        """Combine multiple insights into a summary."""
        valid = [i.strip() for i in insights if i and i.strip()]
        if not valid:
            return ""
        if len(valid) == 1:
            return valid[0]

        # Return first insight as base (LLM will synthesize properly)
        return valid[0]

    def format_for_llm(self, candidate: DistillationCandidate) -> str:
        """Format a candidate for LLM synthesis (type-aware)."""
        lines = []
        entity_type = candidate.entity_type.title()

        for i, entity in enumerate(candidate.source_entities, 1):
            name = entity.data.get('name', entity.id)
            sim = candidate.similarity_scores.get(entity.id, 0)
            lines.append(f"### {entity_type} {i}: {name}")
            lines.append(f"- **ID**: {entity.id}")
            lines.append(f"- **Similarity**: {sim:.2f}")

            # Type-specific primary content
            if entity.type == 'learning':
                insight = entity.data.get('insight', entity.data.get('description', ''))
                insight_str = str(insight)[:300] if insight else ''
                lines.append(f"- **Insight**: {insight_str}...")
            elif entity.type == 'inquiry':
                core_concern = entity.data.get('core_concern', '')
                terrain = entity.data.get('terrain', '')
                # Handle terrain as list or string
                if isinstance(terrain, list):
                    terrain = ', '.join(str(t) for t in terrain)
                if core_concern:
                    core_str = str(core_concern)[:300] if core_concern else ''
                    lines.append(f"- **Core Concern**: {core_str}...")
                if terrain:
                    terrain_str = str(terrain)[:200]
                    lines.append(f"- **Terrain**: {terrain_str}...")
            elif entity.type == 'feature':
                # Features: description + problem + status
                lines.append(f"- **Status**: {entity.status}")
                description = entity.data.get('description', '')
                if description:
                    lines.append(f"- **Description**: {str(description)[:300]}...")
                problem = entity.data.get('problem', '')
                if problem:
                    lines.append(f"- **Problem**: {str(problem)[:200]}...")
                solution = entity.data.get('solution', '')
                if solution:
                    lines.append(f"- **Solution**: {str(solution)[:200]}...")
            elif entity.type == 'pattern':
                # Patterns: subtype + problem + solution + context
                subtype = entity.data.get('subtype', 'unknown')
                lines.append(f"- **Subtype**: {subtype}")
                problem = entity.data.get('problem', '')
                if problem:
                    lines.append(f"- **Problem**: {str(problem)[:300]}...")
                solution = entity.data.get('solution', '')
                if solution:
                    lines.append(f"- **Solution**: {str(solution)[:300]}...")
                context = entity.data.get('context', '')
                if context:
                    lines.append(f"- **Context**: {str(context)[:200]}...")
            else:
                # Fallback for other types
                description = entity.data.get('description', '')
                desc_str = str(description)[:300] if description else ''
                lines.append(f"- **Description**: {desc_str}...")

            lines.append("")

        return "\n".join(lines)

    def apply_distillation(
        self,
        proposal: DistillationProposal,
    ) -> Entity:
        """
        Apply a distillation proposal, creating canonical entity and marking sources as subsumed.

        Type-specific field mapping:
        - learning: canonical_insight → insight
        - inquiry: canonical_insight → core_concern, terrain merged from sources
        - feature/pattern: canonical_insight → description

        Args:
            proposal: The approved distillation proposal

        Returns:
            The newly created canonical entity
        """
        from .factory import EntityFactory
        factory = EntityFactory(repository=self.repository)

        # Determine entity type from source
        source = self.repository.read(proposal.source_ids[0])
        if not source:
            raise ValueError(f"Source entity not found: {proposal.source_ids[0]}")

        entity_type = source.type

        # Build type-specific kwargs
        kwargs = {
            'domain': proposal.domain,
            'subsumes': proposal.source_ids,
            'distillation_confidence': proposal.confidence,
            'distillation_preserves': proposal.preserves,
            'distillation_reasoning': proposal.reasoning,
        }

        if entity_type == 'learning':
            kwargs['insight'] = proposal.canonical_insight
        elif entity_type == 'inquiry':
            kwargs['core_concern'] = proposal.canonical_insight
            # Merge terrain from top 3 sources (by similarity)
            terrains = []
            for source_id in proposal.source_ids[:3]:
                src = self.repository.read(source_id)
                if src and src.data.get('terrain'):
                    terrains.append(src.data['terrain'])
            if terrains:
                kwargs['terrain'] = ' | '.join(terrains)
        elif entity_type == 'feature':
            kwargs['description'] = proposal.canonical_insight
            # Merge problem from top 3 sources
            problems = []
            for source_id in proposal.source_ids[:3]:
                src = self.repository.read(source_id)
                if src and src.data.get('problem'):
                    problems.append(str(src.data['problem']).strip())
            if problems:
                kwargs['problem'] = ' | '.join(problems)
            # Merge requirements (deduplicate by id)
            all_requirements = []
            seen_req_ids = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    for req in src.data.get('requirements', []):
                        # Handle both string and dict requirements
                        if isinstance(req, str):
                            req_id = req  # Use string itself as ID
                        else:
                            req_id = req.get('id', str(len(all_requirements)))
                        if req_id not in seen_req_ids:
                            seen_req_ids.add(req_id)
                            all_requirements.append(req)
            if all_requirements:
                kwargs['requirements'] = all_requirements
            # Merge behaviors (deduplicate by id)
            all_behaviors = []
            seen_beh_ids = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    for beh in src.data.get('behaviors', []):
                        # Handle both string and dict behaviors
                        if isinstance(beh, str):
                            beh_id = beh  # Use string itself as ID
                        else:
                            beh_id = beh.get('id', str(len(all_behaviors)))
                        if beh_id not in seen_beh_ids:
                            seen_beh_ids.add(beh_id)
                            all_behaviors.append(beh)
            if all_behaviors:
                kwargs['behaviors'] = all_behaviors
            # Merge dependencies, blockers, learnings (union)
            all_deps = set()
            all_blockers = set()
            all_learnings = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    all_deps.update(src.data.get('dependencies', []))
                    all_blockers.update(src.data.get('blockers', []))
                    all_learnings.update(src.data.get('learnings', []))
            if all_deps:
                kwargs['dependencies'] = list(all_deps)
            if all_blockers:
                kwargs['blockers'] = list(all_blockers)
            if all_learnings:
                kwargs['learnings'] = list(all_learnings)
        elif entity_type == 'pattern':
            kwargs['problem'] = proposal.canonical_insight
            # Merge solution from top 3 sources
            solutions = []
            for source_id in proposal.source_ids[:3]:
                src = self.repository.read(source_id)
                if src and src.data.get('solution'):
                    solutions.append(str(src.data['solution']).strip())
            if solutions:
                kwargs['solution'] = ' | '.join(solutions)
            # Merge context from top 3 sources
            contexts = []
            for source_id in proposal.source_ids[:3]:
                src = self.repository.read(source_id)
                if src and src.data.get('context'):
                    contexts.append(str(src.data['context']).strip())
            if contexts:
                kwargs['context'] = ' | '.join(contexts)
            # Preserve subtype from primary source only
            if proposal.source_ids:
                primary_src = self.repository.read(proposal.source_ids[0])
                if primary_src and primary_src.data.get('subtype'):
                    kwargs['subtype'] = primary_src.data['subtype']
            # CRITICAL: Preserve mechanics from primary source ONLY (never merge)
            if proposal.source_ids:
                primary_src = self.repository.read(proposal.source_ids[0])
                if primary_src and primary_src.data.get('mechanics'):
                    kwargs['mechanics'] = primary_src.data['mechanics']
            # Merge consequences (deduplicate)
            all_consequences = []
            seen = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    for cons in src.data.get('consequences', []):
                        cons_str = str(cons).strip()
                        if cons_str not in seen:
                            seen.add(cons_str)
                            all_consequences.append(cons)
            if all_consequences:
                kwargs['consequences'] = all_consequences
            # Merge related (union)
            all_related = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    all_related.update(src.data.get('related', []))
            if all_related:
                kwargs['related'] = list(all_related)
            # Merge when_to_use and when_not_to_use (deduplicate)
            when_to_use = []
            when_not_to_use = []
            seen_use = set()
            seen_not_use = set()
            for source_id in proposal.source_ids:
                src = self.repository.read(source_id)
                if src:
                    for use in src.data.get('when_to_use', []):
                        use_str = str(use).strip()
                        if use_str not in seen_use:
                            seen_use.add(use_str)
                            when_to_use.append(use)
                    for not_use in src.data.get('when_not_to_use', []):
                        not_use_str = str(not_use).strip()
                        if not_use_str not in seen_not_use:
                            seen_not_use.add(not_use_str)
                            when_not_to_use.append(not_use)
            if when_to_use:
                kwargs['when_to_use'] = when_to_use
            if when_not_to_use:
                kwargs['when_not_to_use'] = when_not_to_use
        else:
            # Fallback for other types
            kwargs['description'] = proposal.canonical_insight

        # Create canonical entity
        canonical = factory.create(
            entity_type,
            proposal.canonical_name,
            **kwargs,
        )

        # Mark sources as subsumed (with prior_status for reversibility)
        now = datetime.now(timezone.utc).isoformat()
        for source_id in proposal.source_ids:
            source_entity = self.repository.read(source_id)
            if source_entity:
                updated = source_entity.copy(status='subsumed')
                updated.data['prior_status'] = source_entity.status  # For un-subsumption
                updated.data['subsumed_by'] = canonical.id
                updated.data['subsumed_at'] = now
                self.repository.update(updated)

        logger.info(
            f"Distilled {len(proposal.source_ids)} {entity_type}s "
            f"into {canonical.id}"
        )

        return canonical

    def unsubsume(
        self,
        entity_id: str,
        window_days: int = 30,
    ) -> Tuple[bool, str]:
        """
        Un-subsume an entity, restoring its prior status.

        Args:
            entity_id: ID of the subsumed entity to restore
            window_days: Maximum days since subsumption to allow reversal

        Returns:
            Tuple of (success, message)
        """
        # Get the entity
        entity = self.repository.read(entity_id)
        if not entity:
            return False, f"Entity not found: {entity_id}"

        # Verify it's subsumed
        if entity.status != 'subsumed':
            return False, f"Entity is not subsumed (status: {entity.status})"

        # Check window
        subsumed_at = entity.data.get('subsumed_at')
        if subsumed_at:
            subsumed_dt = datetime.fromisoformat(subsumed_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            days_elapsed = (now - subsumed_dt).days
            if days_elapsed > window_days:
                return False, f"Subsumption is permanent (elapsed: {days_elapsed} days, window: {window_days} days)"

        # Get canonical
        canonical_id = entity.data.get('subsumed_by')
        if not canonical_id:
            return False, "Entity has no subsumed_by reference"

        canonical = self.repository.read(canonical_id)

        # Get prior status (default to type's initial status)
        prior_status = entity.data.get('prior_status')
        if not prior_status:
            # Default to initial status for type
            type_defaults = {
                'learning': 'captured',
                'inquiry': 'active',
                'feature': 'nascent',
                'pattern': 'proposed',
            }
            prior_status = type_defaults.get(entity.type, 'active')

        # Restore entity
        restored = entity.copy(status=prior_status)
        del restored.data['subsumed_by']
        del restored.data['subsumed_at']
        if 'prior_status' in restored.data:
            del restored.data['prior_status']
        self.repository.update(restored)

        # Update canonical's subsumes array
        if canonical and canonical.data.get('subsumes'):
            subsumes = canonical.data['subsumes']
            if entity_id in subsumes:
                subsumes.remove(entity_id)
                canonical.data['subsumes'] = subsumes
                # If no more subsumes, mark canonical as drifting
                if not subsumes:
                    canonical = canonical.copy(status='drifting')
                    canonical.data['drift_signals'] = canonical.data.get('drift_signals', [])
                    canonical.data['drift_signals'].append('all_sources_unsubsumed')
                self.repository.update(canonical)

        logger.info(f"Un-subsumed {entity_id}, restored to status '{prior_status}'")
        return True, f"Restored {entity_id} to status '{prior_status}'"

    def unsubsume_all(
        self,
        canonical_id: str,
        window_days: int = 30,
    ) -> Tuple[int, int, List[str]]:
        """
        Un-subsume all entities from a canonical.

        Args:
            canonical_id: ID of the canonical entity
            window_days: Maximum days since subsumption to allow reversal

        Returns:
            Tuple of (success_count, failure_count, messages)
        """
        canonical = self.repository.read(canonical_id)
        if not canonical:
            return 0, 0, [f"Canonical entity not found: {canonical_id}"]

        subsumes = canonical.data.get('subsumes', [])
        if not subsumes:
            return 0, 0, ["No subsumed entities to restore"]

        # Check if canonical itself is subsumed (block meta-distillation unwinding)
        if canonical.status == 'subsumed':
            return 0, 0, ["Cannot unsubsume: canonical is itself subsumed. Unwind parent first."]

        success_count = 0
        failure_count = 0
        messages = []

        for entity_id in list(subsumes):  # Copy list since we're modifying
            success, msg = self.unsubsume(entity_id, window_days)
            if success:
                success_count += 1
            else:
                failure_count += 1
            messages.append(msg)

        # After all un-subsumptions, check canonical state
        canonical = self.repository.read(canonical_id)  # Re-read
        if canonical and not canonical.data.get('subsumes'):
            # All sources removed, canonical is now orphaned
            messages.append(f"Canonical {canonical_id} now has no subsumes, marked as drifting")

        return success_count, failure_count, messages


# Tool handler function for MCP integration
def distill_learnings(
    domain: Optional[str] = None,
    threshold: float = 0.60,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Find clusters of semantically similar learnings for distillation.

    This is the tool handler function called by the MCP server.

    Args:
        domain: Optional domain to filter learnings
        threshold: Similarity threshold for clustering (default 0.60)
        limit: Maximum learnings to analyze

    Returns:
        Dict with distillation candidates and summary
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(
        repository=repo,
        similarity_threshold=threshold,
    )

    candidates = service.find_distillation_candidates(
        entity_type='learning',
        domain=domain,
        limit=limit,
    )

    if not candidates:
        return {
            "status": "no_candidates",
            "message": "No distillation candidates found. Learnings may be too dissimilar or already subsumed.",
            "candidates": [],
        }

    # Format candidates for display
    formatted = []
    for candidate in candidates:
        formatted.append({
            "cluster_id": candidate.cluster_id,
            "confidence": round(candidate.confidence, 2),
            "domain": candidate.domain,
            "source_count": len(candidate.source_entities),
            "sources": [
                {
                    "id": e.id,
                    "name": e.data.get('name', ''),
                    "similarity": round(candidate.similarity_scores.get(e.id, 0), 2),
                }
                for e in candidate.source_entities
            ],
            "proposed_name": candidate.proposed_name,
            "llm_context": service.format_for_llm(candidate),
        })

    return {
        "status": "candidates_found",
        "message": f"Found {len(candidates)} distillation candidates",
        "candidates": formatted,
        "next_steps": [
            "Review the candidates and their similarity scores",
            "For promising candidates, use the LLM to synthesize a canonical form",
            "Apply the distillation with human approval",
        ],
    }


def distill_inquiries(
    domain: Optional[str] = None,
    threshold: float = 0.60,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Find clusters of semantically similar inquiries for distillation.

    This is the tool handler function for inquiry distillation.
    Uses core_concern as the primary embedding field.

    Args:
        domain: Optional domain to filter inquiries
        threshold: Similarity threshold for clustering (default 0.60)
        limit: Maximum inquiries to analyze

    Returns:
        Dict with distillation candidates and summary
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(
        repository=repo,
        similarity_threshold=threshold,
    )

    candidates = service.find_distillation_candidates(
        entity_type='inquiry',
        domain=domain,
        limit=limit,
    )

    if not candidates:
        return {
            "status": "no_candidates",
            "message": "No distillation candidates found. Inquiries may be too dissimilar or already subsumed.",
            "candidates": [],
        }

    # Format candidates for display (inquiry-specific)
    formatted = []
    for candidate in candidates:
        formatted.append({
            "cluster_id": candidate.cluster_id,
            "confidence": round(candidate.confidence, 2),
            "domain": candidate.domain,
            "source_count": len(candidate.source_entities),
            "sources": [
                {
                    "id": e.id,
                    "name": e.data.get('name', ''),
                    "core_concern": (str(e.data.get('core_concern', ''))[:100] + '...'
                                    if e.data.get('core_concern') else ''),
                    "terrain": (', '.join(e.data['terrain']) if isinstance(e.data.get('terrain'), list)
                               else e.data.get('terrain', '')),
                    "similarity": round(candidate.similarity_scores.get(e.id, 0), 2),
                }
                for e in candidate.source_entities
            ],
            "proposed_name": candidate.proposed_name,
            "llm_context": service.format_for_llm(candidate),
        })

    return {
        "status": "candidates_found",
        "message": f"Found {len(candidates)} inquiry distillation candidates",
        "candidates": formatted,
        "next_steps": [
            "Review the candidates and their similarity scores",
            "Ensure core_concern overlap is genuine (not just keyword similarity)",
            "Consider whether terrain should be preserved or merged",
            "Apply the distillation with human approval",
        ],
    }


def distill_features(
    domain: Optional[str] = None,
    threshold: float = 0.70,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Find clusters of semantically similar features for distillation.

    Uses description + problem as the primary embedding fields.
    Higher threshold (0.70) due to structural complexity.

    Args:
        domain: Optional domain to filter features
        threshold: Similarity threshold for clustering (default 0.70)
        limit: Maximum features to analyze

    Returns:
        Dict with distillation candidates and summary
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(
        repository=repo,
        similarity_threshold=threshold,
    )

    candidates = service.find_distillation_candidates(
        entity_type='feature',
        domain=domain,
        limit=limit,
    )

    if not candidates:
        return {
            "status": "no_candidates",
            "message": "No distillation candidates found. Features may be too dissimilar or already subsumed.",
            "candidates": [],
        }

    # Format candidates for display (feature-specific)
    formatted = []
    for candidate in candidates:
        formatted.append({
            "cluster_id": candidate.cluster_id,
            "confidence": round(candidate.confidence, 2),
            "domain": candidate.domain,
            "source_count": len(candidate.source_entities),
            "sources": [
                {
                    "id": e.id,
                    "name": e.data.get('name', ''),
                    "status": e.status,
                    "description": (str(e.data.get('description', ''))[:100] + '...'
                                   if e.data.get('description') else ''),
                    "problem": (str(e.data.get('problem', ''))[:80] + '...'
                               if e.data.get('problem') else ''),
                    "similarity": round(candidate.similarity_scores.get(e.id, 0), 2),
                }
                for e in candidate.source_entities
            ],
            "proposed_name": candidate.proposed_name,
            "llm_context": service.format_for_llm(candidate),
        })

    return {
        "status": "candidates_found",
        "message": f"Found {len(candidates)} feature distillation candidates",
        "candidates": formatted,
        "next_steps": [
            "Review the candidates and their similarity scores",
            "Verify that features address the same problem domain",
            "Check that requirements and behaviors can be meaningfully merged",
            "Apply the distillation with human approval",
        ],
    }


def distill_patterns(
    domain: Optional[str] = None,
    subtype: Optional[str] = None,
    threshold: float = 0.75,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Find clusters of semantically similar patterns for distillation.

    Uses problem + solution + context as the primary embedding fields.
    Highest threshold (0.75) - patterns encode nuanced wisdom.
    Only clusters patterns of the same subtype.

    Args:
        domain: Optional domain to filter patterns
        subtype: Optional subtype to filter (meta, architectural, process, etc.)
        threshold: Similarity threshold for clustering (default 0.75)
        limit: Maximum patterns to analyze

    Returns:
        Dict with distillation candidates and summary
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(
        repository=repo,
        similarity_threshold=threshold,
    )

    candidates = service.find_distillation_candidates(
        entity_type='pattern',
        domain=domain,
        limit=limit,
    )

    # Filter by subtype if specified
    if subtype:
        candidates = [
            c for c in candidates
            if all(e.data.get('subtype') == subtype for e in c.source_entities)
        ]

    # Additional filtering: only cluster same-subtype patterns
    filtered_candidates = []
    for candidate in candidates:
        subtypes = {e.data.get('subtype', 'unknown') for e in candidate.source_entities}
        if len(subtypes) == 1:  # All same subtype
            filtered_candidates.append(candidate)
    candidates = filtered_candidates

    if not candidates:
        return {
            "status": "no_candidates",
            "message": "No distillation candidates found. Patterns may be too dissimilar, different subtypes, or already subsumed.",
            "candidates": [],
        }

    # Format candidates for display (pattern-specific)
    formatted = []
    for candidate in candidates:
        formatted.append({
            "cluster_id": candidate.cluster_id,
            "confidence": round(candidate.confidence, 2),
            "domain": candidate.domain,
            "source_count": len(candidate.source_entities),
            "sources": [
                {
                    "id": e.id,
                    "name": e.data.get('name', ''),
                    "subtype": e.data.get('subtype', 'unknown'),
                    "problem": (str(e.data.get('problem', ''))[:100] + '...'
                               if e.data.get('problem') else ''),
                    "solution": (str(e.data.get('solution', ''))[:100] + '...'
                                if e.data.get('solution') else ''),
                    "similarity": round(candidate.similarity_scores.get(e.id, 0), 2),
                }
                for e in candidate.source_entities
            ],
            "proposed_name": candidate.proposed_name,
            "llm_context": service.format_for_llm(candidate),
        })

    return {
        "status": "candidates_found",
        "message": f"Found {len(candidates)} pattern distillation candidates",
        "candidates": formatted,
        "next_steps": [
            "Review the candidates - patterns require careful judgment",
            "Verify all sources are the same subtype",
            "Check that mechanics from primary source is appropriate for canonical",
            "Consider if nuanced distinctions would be lost",
            "Apply the distillation with human approval",
        ],
    }


def bulk_distill_by_domain(
    entity_type: str,
    group_by: str = 'domain',
    threshold: float = 0.65,
    limit_per_group: int = 50,
) -> Dict[str, Any]:
    """
    Bulk distillation grouped by domain or meta-behavior.

    Returns proposals for each domain with candidates above threshold.

    Args:
        entity_type: Type to distill (inquiry, learning, feature, pattern)
        group_by: Field to group by (domain, meta_behavior)
        threshold: Similarity threshold (default 0.65 for bulk)
        limit_per_group: Max entities per group to analyze

    Returns:
        Dict with per-domain proposals
    """
    from .repository import EntityRepository

    # Validate entity type is distillable
    distillable_types = ['inquiry', 'learning', 'feature', 'pattern']
    if entity_type not in distillable_types:
        return {
            "status": "error",
            "message": f"Entity type '{entity_type}' is not distillable. Valid types: {distillable_types}",
        }

    repo = EntityRepository()
    service = DistillationService(
        repository=repo,
        similarity_threshold=threshold,
    )

    # Get all entities of this type (excluding subsumed)
    all_entities = repo.list(entity_type=entity_type, limit=1000)
    active_entities = [e for e in all_entities if e.status != 'subsumed']

    # Group by the specified field
    groups: Dict[str, List] = {}
    for entity in active_entities:
        group_value = entity.data.get(group_by, 'unclassified')
        if group_value not in groups:
            groups[group_value] = []
        groups[group_value].append(entity)

    # Find candidates per group
    results = {}
    total_candidates = 0

    for group_name, entities in groups.items():
        if len(entities) < 2:
            continue  # Need at least 2 to cluster

        candidates = service.find_distillation_candidates(
            entity_type=entity_type,
            domain=group_name if group_by == 'domain' else None,
            limit=limit_per_group,
        )

        # Filter candidates to only include entities in this group
        if group_by != 'domain':
            group_ids = {e.id for e in entities}
            candidates = [
                c for c in candidates
                if all(e.id in group_ids for e in c.source_entities)
            ]

        if candidates:
            results[group_name] = {
                'entity_count': len(entities),
                'candidate_count': len(candidates),
                'proposals': [
                    {
                        "cluster_id": c.cluster_id,
                        "confidence": round(c.confidence, 2),
                        "source_count": len(c.source_entities),
                        "sources": [e.id for e in c.source_entities],
                        "proposed_name": c.proposed_name,
                    }
                    for c in candidates
                ],
            }
            total_candidates += len(candidates)

    return {
        "status": "proposals_ready" if results else "no_candidates",
        "entity_type": entity_type,
        "group_by": group_by,
        "threshold": threshold,
        "groups_analyzed": len(groups),
        "groups_with_candidates": len(results),
        "total_candidates": total_candidates,
        "results": results,
        "next_steps": [
            "Review proposals per group",
            "For each approved proposal, call apply_distillation()",
            "Consider cross-group patterns after within-group distillation",
        ] if results else [
            "No clusters found above threshold",
            "Try lowering threshold or checking entity content",
        ],
    }


def unsubsume(
    entity_id: str,
    window_days: int = 30,
) -> Dict[str, Any]:
    """
    Un-subsume an entity, restoring its prior status.

    Reversibility is only allowed within the window period (default 30 days).
    After the window, subsumption is permanent.

    Args:
        entity_id: ID of the subsumed entity to restore
        window_days: Maximum days since subsumption to allow reversal

    Returns:
        Dict with success status and message
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(repository=repo)

    success, message = service.unsubsume(entity_id, window_days)

    return {
        "status": "success" if success else "error",
        "entity_id": entity_id,
        "message": message,
    }


def unsubsume_all(
    canonical_id: str,
    window_days: int = 30,
) -> Dict[str, Any]:
    """
    Un-subsume all entities from a canonical.

    This reverses a distillation operation, restoring all source entities
    to their prior status. The canonical is marked as 'drifting' if all
    sources are restored.

    Args:
        canonical_id: ID of the canonical entity
        window_days: Maximum days since subsumption to allow reversal

    Returns:
        Dict with counts and messages
    """
    from .repository import EntityRepository

    repo = EntityRepository()
    service = DistillationService(repository=repo)

    success_count, failure_count, messages = service.unsubsume_all(
        canonical_id, window_days
    )

    return {
        "status": "success" if success_count > 0 else "error",
        "canonical_id": canonical_id,
        "success_count": success_count,
        "failure_count": failure_count,
        "messages": messages,
    }
