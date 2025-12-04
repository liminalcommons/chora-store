"""
Metabolism: The Digestive Tract of Chora.

Handles the metabolic cycle:
  Ingest (capture) -> Digest (cluster) -> Synthesize (pattern) -> Excrete (archive)

Two modes of digestion:
  - Algorithmic (System 1): PatternInductor clusters by keyword overlap
  - Agentic (System 2): Agent proposes synthesis based on semantic understanding

Also detects Surprises (outliers that don't cluster) as mutation candidates.

Tiered Resolution:
  Operations flow through tiers: data → workflow → inference → agent
  The tiered_synthesize() method tries cheaper tiers first and escalates when needed.
  All tier operations capture traces for future crystallization.
"""
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from .evaluator import PatternInductor
from .models import Entity
from .repository import EntityRepository
from .schema import VALID_TIERS

# Factory import deferred to avoid circular import
_factory = None

def _get_factory():
    """Lazy factory initialization to avoid circular import."""
    global _factory
    if _factory is None:
        from .factory import EntityFactory
        _factory = EntityFactory()
    return _factory

# Optional: chora-inference for LLM tier
try:
    from chora_inference import InferenceClient, get_registry
    HAS_INFERENCE = True
except ImportError:
    HAS_INFERENCE = False
    InferenceClient = None  # type: ignore
    get_registry = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# TRACE CAPTURE - Operational telemetry for crystallization
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Trace:
    """Operational trace for tiered resolution."""
    id: str
    operation_type: str
    tier: str
    capability_id: Optional[str] = None
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)
    cost_units: float = 0.0
    duration_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "tier": self.tier,
            "capability_id": self.capability_id,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "reasoning": self.reasoning,
            "cost_units": self.cost_units,
            "duration_ms": self.duration_ms,
            "success": 1 if self.success else 0,
            "error_message": self.error_message,
            "created_at": self.created_at,
        }


class TraceCapture:
    """Context manager for capturing operation traces."""

    def __init__(
        self,
        repository: EntityRepository,
        operation_type: str,
        tier: str,
        capability_id: Optional[str] = None,
    ):
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")
        self.repository = repository
        self.trace = Trace(
            id=f"trace-{uuid.uuid4().hex[:12]}",
            operation_type=operation_type,
            tier=tier,
            capability_id=capability_id,
        )
        self._start_time: Optional[float] = None

    def __enter__(self) -> "TraceCapture":
        self._start_time = time.monotonic()
        return self

    def step(self, reasoning: str) -> None:
        """Record a reasoning step."""
        self.trace.reasoning.append(reasoning)

    def set_inputs(self, inputs: List[str]) -> None:
        """Set input entity references."""
        self.trace.inputs = inputs

    def set_outputs(self, outputs: List[str]) -> None:
        """Set output entity references."""
        self.trace.outputs = outputs

    def set_cost(self, cost: float) -> None:
        """Set cost units for this operation."""
        self.trace.cost_units = cost

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._start_time:
            self.trace.duration_ms = int((time.monotonic() - self._start_time) * 1000)
        if exc_type is not None:
            self.trace.success = False
            self.trace.error_message = str(exc_val)
        self._persist_trace()
        return False  # Don't suppress exceptions

    def _persist_trace(self) -> None:
        """Persist trace to SQLite."""
        try:
            with self.repository._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.trace.id,
                        self.trace.operation_type,
                        self.trace.tier,
                        self.trace.capability_id,
                        json.dumps(self.trace.inputs),
                        json.dumps(self.trace.outputs),
                        json.dumps(self.trace.reasoning),
                        self.trace.cost_units,
                        self.trace.duration_ms,
                        1 if self.trace.success else 0,
                        self.trace.error_message,
                        self.trace.created_at,
                    ),
                )
        except Exception:
            pass  # Don't fail the operation if trace persistence fails


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE TABLE - Crystallized tier resolutions (Push Right solidification)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Route:
    """A crystallized route from traces - hot operations that have cooled into data lookups."""
    id: str
    tool_id: str
    input_signature: str
    output_template: str
    confidence: float = 0.9
    hit_count: int = 0
    miss_count: int = 0
    status: str = "canary"  # canary, active, deprecated
    source_traces: List[str] = field(default_factory=list)
    source_learning_ids: List[str] = field(default_factory=list)  # Phase 5: learning lineage
    taught_at_thresholds: List[int] = field(default_factory=list)  # Hit thresholds where learnings were generated
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_hit_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool_id": self.tool_id,
            "input_signature": self.input_signature,
            "output_template": self.output_template,
            "confidence": self.confidence,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "status": self.status,
            "source_traces": self.source_traces,
            "source_learning_ids": self.source_learning_ids,
            "taught_at_thresholds": self.taught_at_thresholds,
            "created_at": self.created_at,
            "last_hit_at": self.last_hit_at,
        }


class RouteTable:
    """
    Manages crystallized routes for tiered resolution.

    Routes are the solidification of traces into data lookups - the ultimate
    Push-Right outcome where expensive inference operations become cheap data retrievals.
    """

    VALID_STATUSES = ["canary", "active", "deprecated"]

    def __init__(self, repository: EntityRepository):
        self.repository = repository

    def lookup(self, tool_id: str, input_signature: str) -> Optional[Route]:
        """
        Look up a route by tool ID and input signature.

        Returns the route if found and active/canary, None otherwise.
        """
        with self.repository._connection() as conn:
            row = conn.execute(
                """
                SELECT id, tool_id, input_signature, output_template, confidence,
                       hit_count, miss_count, status, source_traces, source_learning_ids,
                       taught_at_thresholds, created_at, last_hit_at
                FROM routes
                WHERE tool_id = ? AND input_signature = ? AND status IN ('canary', 'active')
                """,
                (tool_id, input_signature),
            ).fetchone()

            if row:
                return Route(
                    id=row["id"],
                    tool_id=row["tool_id"],
                    input_signature=row["input_signature"],
                    output_template=row["output_template"],
                    confidence=row["confidence"],
                    hit_count=row["hit_count"],
                    miss_count=row["miss_count"],
                    status=row["status"],
                    source_traces=json.loads(row["source_traces"]),
                    source_learning_ids=json.loads(row["source_learning_ids"]),
                    taught_at_thresholds=json.loads(row["taught_at_thresholds"]) if row["taught_at_thresholds"] else [],
                    created_at=row["created_at"],
                    last_hit_at=row["last_hit_at"],
                )
            return None

    def record_hit(self, route_id: str) -> None:
        """Record a successful route hit."""
        now = datetime.utcnow().isoformat()
        with self.repository._connection() as conn:
            conn.execute(
                "UPDATE routes SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
                (now, route_id),
            )

    def record_miss(self, route_id: str) -> None:
        """
        Record a route miss (output didn't match expected).

        If miss_count exceeds threshold, route may be deprecated.
        """
        with self.repository._connection() as conn:
            conn.execute(
                "UPDATE routes SET miss_count = miss_count + 1 WHERE id = ?",
                (route_id,),
            )
            # Check if route should be deprecated
            row = conn.execute(
                "SELECT hit_count, miss_count, status FROM routes WHERE id = ?",
                (route_id,),
            ).fetchone()
            if row and row["status"] != "deprecated":
                total = row["hit_count"] + row["miss_count"]
                if total >= 10 and row["miss_count"] / total > 0.2:
                    conn.execute(
                        "UPDATE routes SET status = 'deprecated' WHERE id = ?",
                        (route_id,),
                    )

    def promote(self, route_id: str) -> bool:
        """
        Promote a route from canary to active.

        Returns True if promotion succeeded, False otherwise.
        """
        with self.repository._connection() as conn:
            result = conn.execute(
                "UPDATE routes SET status = 'active' WHERE id = ? AND status = 'canary'",
                (route_id,),
            )
            return result.rowcount > 0

    def deprecate(self, route_id: str) -> bool:
        """Deprecate a route."""
        with self.repository._connection() as conn:
            result = conn.execute(
                "UPDATE routes SET status = 'deprecated' WHERE id = ?",
                (route_id,),
            )
            return result.rowcount > 0

    def get(self, route_id: str) -> Optional[Route]:
        """
        Get a route by ID.

        Returns the route if found, None otherwise.
        """
        with self.repository._connection() as conn:
            row = conn.execute(
                """
                SELECT id, tool_id, input_signature, output_template, confidence,
                       hit_count, miss_count, status, source_traces, source_learning_ids,
                       taught_at_thresholds, created_at, last_hit_at
                FROM routes
                WHERE id = ?
                """,
                (route_id,),
            ).fetchone()

            if row:
                return Route(
                    id=row["id"],
                    tool_id=row["tool_id"],
                    input_signature=row["input_signature"],
                    output_template=row["output_template"],
                    confidence=row["confidence"],
                    hit_count=row["hit_count"],
                    miss_count=row["miss_count"],
                    status=row["status"],
                    source_traces=json.loads(row["source_traces"]),
                    source_learning_ids=json.loads(row["source_learning_ids"]),
                    taught_at_thresholds=json.loads(row["taught_at_thresholds"]) if row["taught_at_thresholds"] else [],
                    created_at=row["created_at"],
                    last_hit_at=row["last_hit_at"],
                )
            return None

    def evaluate_for_teaching(
        self,
        route_id: str,
        hit_threshold: int = 10,
        factory=None,
    ) -> Dict[str, Any]:
        """
        Evaluate a route for teaching back.

        When a route reaches certain hit thresholds (10, 20, 50, 100, etc.),
        it generates a learning about what crystallized well. This enables
        the system to develop "taste" for what operations crystallize effectively.

        Args:
            route_id: The route to evaluate
            hit_threshold: Base threshold for teaching (default 10)
            factory: EntityFactory for creating learnings

        Returns:
            Dict with 'generated', 'learning_id', 'flagged_for_review' keys
        """
        route = self.get(route_id)
        if not route:
            return {"generated": False, "learning_id": None, "flagged_for_review": False}

        # Check if route is low-performing (more misses than hits)
        total = route.hit_count + route.miss_count
        if total > 0 and route.miss_count > route.hit_count:
            return {"generated": False, "learning_id": None, "flagged_for_review": True}

        # Determine applicable thresholds: 10, 20, 50, 100, 200, 500, 1000...
        thresholds = [10, 20, 50, 100, 200, 500, 1000]
        applicable_threshold = None
        for t in thresholds:
            if route.hit_count >= t and t not in route.taught_at_thresholds:
                applicable_threshold = t

        if applicable_threshold is None:
            return {"generated": False, "learning_id": None, "flagged_for_review": False}

        # Generate learning about crystallization success
        if factory is None:
            return {"generated": False, "learning_id": None, "flagged_for_review": False}

        # Build insight based on threshold level
        if applicable_threshold == 10:
            insight = (
                f"Route {route_id} for {route.tool_id} has crystallized successfully. "
                f"Input pattern '{route.input_signature[:50]}...' consistently produces stable output. "
                f"This operation benefits from caching at the data tier."
            )
        elif applicable_threshold >= 100:
            insight = (
                f"Route {route_id} shows sustained crystallization success with {route.hit_count} hits. "
                f"The input pattern '{route.input_signature[:50]}...' represents a highly stable operation. "
                f"Consider this pattern as a template for similar crystallization opportunities."
            )
        else:
            insight = (
                f"Route {route_id} continues successful crystallization at {route.hit_count} hits (threshold {applicable_threshold}). "
                f"Input pattern '{route.input_signature[:50]}...' maintains output consistency. "
                f"Growing evidence of reliable crystallizability."
            )

        learning = factory.create(
            'learning',
            f'Route Crystallization Success: {route.tool_id}',
            insight=insight,
            domain='metabolic',
            tags=['crystallization-success', 'route-wisdom'],
            context=f"Source: {route_id}, tool: {route.tool_id}, threshold: {applicable_threshold}",
        )

        # Update route to record teaching threshold
        with self.repository._connection() as conn:
            new_thresholds = route.taught_at_thresholds + [applicable_threshold]
            conn.execute(
                "UPDATE routes SET taught_at_thresholds = ? WHERE id = ?",
                (json.dumps(new_thresholds), route_id),
            )

        return {"generated": True, "learning_id": learning.id, "flagged_for_review": False}

    def create(
        self,
        tool_id: str,
        input_signature: str,
        output_template: str,
        source_traces: List[str],
        source_learning_ids: Optional[List[str]] = None,
        confidence: float = 0.9,
    ) -> Route:
        """
        Crystallize a new route from traces.

        Args:
            tool_id: The tool this route applies to
            input_signature: Canonical form of input pattern
            output_template: The crystallized output
            source_traces: Trace IDs that led to this route
            source_learning_ids: Learning IDs that enabled this route (Phase 5)
            confidence: Initial confidence score

        Returns:
            The created Route
        """
        route = Route(
            id=f"route-{uuid.uuid4().hex[:12]}",
            tool_id=tool_id,
            input_signature=input_signature,
            output_template=output_template,
            confidence=confidence,
            source_traces=source_traces,
            source_learning_ids=source_learning_ids or [],
        )

        with self.repository._connection() as conn:
            conn.execute(
                """
                INSERT INTO routes (id, tool_id, input_signature, output_template, confidence,
                                   hit_count, miss_count, status, source_traces, source_learning_ids,
                                   taught_at_thresholds, created_at, last_hit_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route.id,
                    route.tool_id,
                    route.input_signature,
                    route.output_template,
                    route.confidence,
                    route.hit_count,
                    route.miss_count,
                    route.status,
                    json.dumps(route.source_traces),
                    json.dumps(route.source_learning_ids),
                    json.dumps(route.taught_at_thresholds),
                    route.created_at,
                    route.last_hit_at,
                ),
            )

        return route

    def list_routes(
        self,
        tool_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Route]:
        """
        List routes with optional filters.

        Args:
            tool_id: Filter by tool ID
            status: Filter by status (canary, active, deprecated)
            limit: Maximum routes to return
        """
        query = "SELECT * FROM routes WHERE 1=1"
        params: List[Any] = []

        if tool_id:
            query += " AND tool_id = ?"
            params.append(tool_id)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY hit_count DESC LIMIT ?"
        params.append(limit)

        routes = []
        with self.repository._connection() as conn:
            for row in conn.execute(query, params):
                routes.append(Route(
                    id=row["id"],
                    tool_id=row["tool_id"],
                    input_signature=row["input_signature"],
                    output_template=row["output_template"],
                    confidence=row["confidence"],
                    hit_count=row["hit_count"],
                    miss_count=row["miss_count"],
                    status=row["status"],
                    source_traces=json.loads(row["source_traces"]),
                    source_learning_ids=json.loads(row["source_learning_ids"]) if row["source_learning_ids"] else [],
                    taught_at_thresholds=json.loads(row["taught_at_thresholds"]) if row["taught_at_thresholds"] else [],
                    created_at=row["created_at"],
                    last_hit_at=row["last_hit_at"],
                ))

        return routes

    def find_crystallization_candidates(
        self,
        tool_id: Optional[str] = None,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
        use_embeddings: bool = True,
        similarity_threshold: float = 0.90,
    ) -> List[Dict[str, Any]]:
        """
        Find trace clusters that are candidates for crystallization into routes.

        Two modes:
        - use_embeddings=True: Cluster by semantic similarity (recommended)
        - use_embeddings=False: Cluster by exact input string match (legacy)

        Args:
            tool_id: Filter to specific tool
            min_traces: Minimum similar traces required
            consistency_threshold: Required output consistency (0.0-1.0)
            use_embeddings: Use semantic clustering (default True)
            similarity_threshold: Embedding similarity threshold (default 0.90)

        Returns:
            List of crystallization candidates with their stats
        """
        if use_embeddings:
            return self._find_candidates_with_embeddings(
                tool_id=tool_id,
                min_traces=min_traces,
                consistency_threshold=consistency_threshold,
                similarity_threshold=similarity_threshold,
            )
        else:
            return self._find_candidates_exact_match(
                tool_id=tool_id,
                min_traces=min_traces,
                consistency_threshold=consistency_threshold,
            )

    def _find_candidates_exact_match(
        self,
        tool_id: Optional[str] = None,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """Legacy exact-match clustering (for backwards compatibility)."""
        query = """
            SELECT
                capability_id,
                inputs,
                outputs,
                COUNT(*) as trace_count,
                AVG(success) as success_rate
            FROM traces
            WHERE success = 1
              AND tier IN ('inference', 'agent')
        """
        params: List[Any] = []

        if tool_id:
            query += " AND capability_id = ?"
            params.append(tool_id)

        query += """
            GROUP BY capability_id, inputs
            HAVING COUNT(*) >= ?
        """
        params.append(min_traces)

        candidates = []
        with self.repository._connection() as conn:
            for row in conn.execute(query, params):
                # Check output consistency
                outputs_query = """
                    SELECT outputs, COUNT(*) as cnt
                    FROM traces
                    WHERE capability_id = ? AND inputs = ? AND success = 1
                    GROUP BY outputs
                    ORDER BY cnt DESC
                """
                output_dist = list(conn.execute(
                    outputs_query,
                    (row["capability_id"], row["inputs"])
                ))

                if output_dist:
                    total = sum(r["cnt"] for r in output_dist)
                    most_common_pct = output_dist[0]["cnt"] / total

                    if most_common_pct >= consistency_threshold:
                        candidates.append({
                            "tool_id": row["capability_id"],
                            "input_signature": row["inputs"],
                            "output_template": output_dist[0]["outputs"],
                            "trace_count": row["trace_count"],
                            "consistency": most_common_pct,
                            "success_rate": row["success_rate"],
                        })

        return candidates

    def _find_candidates_with_embeddings(
        self,
        tool_id: Optional[str] = None,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
        similarity_threshold: float = 0.90,
    ) -> List[Dict[str, Any]]:
        """
        Find crystallization candidates using semantic embedding similarity.

        This is the recommended approach: traces with semantically similar
        inputs are clustered together, even if the exact strings differ.
        """
        from .embeddings import EmbeddingService
        import os

        # Initialize embedding service (use OpenAI if available)
        provider = 'openai' if os.environ.get('OPENAI_API_KEY') else 'local'
        embedding_service = EmbeddingService(self.repository.db_path, provider=provider)

        # Load traces for clustering
        query = """
            SELECT id, capability_id, inputs, outputs
            FROM traces
            WHERE success = 1
              AND tier IN ('inference', 'agent')
        """
        params: List[Any] = []

        if tool_id:
            query += " AND capability_id = ?"
            params.append(tool_id)

        traces = []
        with self.repository._connection() as conn:
            for row in conn.execute(query, params):
                traces.append({
                    "id": row["id"],
                    "tool_id": row["capability_id"],
                    "inputs": row["inputs"],
                    "outputs": row["outputs"],
                })

        if len(traces) < min_traces:
            return []

        # Group traces by tool_id first (routes are tool-specific)
        traces_by_tool: Dict[str, List[Dict]] = {}
        for trace in traces:
            tid = trace["tool_id"]
            if tid not in traces_by_tool:
                traces_by_tool[tid] = []
            traces_by_tool[tid].append(trace)

        candidates = []

        for tid, tool_traces in traces_by_tool.items():
            if len(tool_traces) < min_traces:
                continue

            # Get embeddings for inputs
            import numpy as np
            input_texts = [t["inputs"] for t in tool_traces]
            embeddings = [embedding_service.embed_text(text) for text in input_texts]

            # Greedy clustering by similarity
            assigned = set()
            clusters = []

            for i, trace in enumerate(tool_traces):
                if i in assigned:
                    continue

                cluster = [trace]
                cluster_indices = [i]
                assigned.add(i)

                for j, other_trace in enumerate(tool_traces):
                    if j in assigned:
                        continue

                    sim = embedding_service.cosine_similarity(embeddings[i], embeddings[j])
                    if sim >= similarity_threshold:
                        cluster.append(other_trace)
                        cluster_indices.append(j)
                        assigned.add(j)

                if len(cluster) >= min_traces:
                    clusters.append(cluster)

            # Evaluate each cluster for output consistency
            for cluster in clusters:
                output_counts: Dict[str, int] = {}
                for trace in cluster:
                    out = trace["outputs"]
                    output_counts[out] = output_counts.get(out, 0) + 1

                total = sum(output_counts.values())
                most_common_output = max(output_counts.keys(), key=lambda k: output_counts[k])
                most_common_count = output_counts[most_common_output]
                consistency = most_common_count / total

                if consistency >= consistency_threshold:
                    # Use centroid input as signature (first trace in cluster)
                    candidates.append({
                        "tool_id": tid,
                        "input_signature": cluster[0]["inputs"],  # Representative input
                        "output_template": most_common_output,
                        "trace_count": len(cluster),
                        "consistency": consistency,
                        "success_rate": 1.0,  # All traces were successful
                        "source_trace_ids": [t["id"] for t in cluster],
                        "clustering_method": "embedding",
                        "similarity_threshold": similarity_threshold,
                    })

        return candidates

    def auto_crystallize(
        self,
        tool_id: Optional[str] = None,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
    ) -> List[Route]:
        """
        Automatically crystallize routes from trace patterns.

        This is the Push-Right in action: hot inference operations
        that have cooled into stable patterns become data lookups.

        Args:
            tool_id: Filter to specific tool
            min_traces: Minimum similar traces required
            consistency_threshold: Required output consistency

        Returns:
            List of newly created routes
        """
        candidates = self.find_crystallization_candidates(
            tool_id=tool_id,
            min_traces=min_traces,
            consistency_threshold=consistency_threshold,
        )

        new_routes = []
        for candidate in candidates:
            # Check if route already exists
            existing = self.lookup(candidate["tool_id"], candidate["input_signature"])
            if existing:
                continue

            # Get source trace IDs and extract learning IDs from input_signature
            with self.repository._connection() as conn:
                trace_ids = [
                    row["id"]
                    for row in conn.execute(
                        """
                        SELECT id FROM traces
                        WHERE capability_id = ? AND inputs = ? AND success = 1
                        ORDER BY created_at DESC
                        LIMIT 10
                        """,
                        (candidate["tool_id"], candidate["input_signature"]),
                    )
                ]

            # Phase 5: Extract learning IDs from input_signature
            # input_signature is the canonical form: json.dumps(sorted(learning_ids))
            try:
                source_learning_ids = json.loads(candidate["input_signature"])
                if not isinstance(source_learning_ids, list):
                    source_learning_ids = []
            except (json.JSONDecodeError, TypeError):
                source_learning_ids = []

            route = self.create(
                tool_id=candidate["tool_id"],
                input_signature=candidate["input_signature"],
                output_template=candidate["output_template"],
                source_traces=trace_ids,
                source_learning_ids=source_learning_ids,
                confidence=candidate["consistency"],
            )
            new_routes.append(route)

            # Emit learning about crystallization (Push-Right in action)
            try:
                factory = _get_factory()
                factory.create(
                    'learning',
                    f'Route crystallized for {candidate["tool_id"]}',
                    insight=(
                        f"Inference traces crystallized into data-tier route. "
                        f"Input pattern matched {candidate['trace_count']} times "
                        f"with {candidate['consistency']:.0%} consistency. "
                        f"Future calls with this input will resolve at data tier."
                    ),
                    domain='tiered-resolution',
                    implications=(
                        "This is Push-Right in action: hot inference operations "
                        "have cooled into solid data lookups. System wisdom increases."
                    ),
                    related=[route.id, candidate["tool_id"]],
                )
            except Exception:
                # Learning emission is optional - don't fail crystallization
                pass

        return new_routes


class MetabolicEngine(PatternInductor):
    """
    Extends PatternInductor to handle the full metabolic cycle,
    including Surprise detection (Outliers).
    """

    def digest(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the metabolic process.

        Returns:
            - proposals: Candidate patterns (Clusters)
            - surprises: Novel learnings (Outliers)
            - stats: Digestion metrics
        """
        # 1. Load active learnings
        active_learnings = []
        try:
            all_learnings = self.repository.list(entity_type="learning", limit=500)
            active_learnings = [
                l for l in all_learnings
                if l.status in ('captured', 'validated')
            ]
            if domain:
                active_learnings = [
                    l for l in active_learnings
                    if l.data.get('domain') == domain
                ]
        except Exception:
            pass

        # 2. Get proposals via base class clustering
        proposals = self.analyze()

        # Filter proposals by domain if specified
        if domain:
            proposals = [p for p in proposals if p.domain == domain]

        # 3. Identify outliers (learnings not covered by any proposal)
        covered_ids = set()
        for p in proposals:
            for source_id in p.source_learnings:
                covered_ids.add(source_id)

        outliers = []
        for l in active_learnings:
            if l.id not in covered_ids:
                outliers.append(l)

        # Sort outliers by recency (newest = freshest surprise)
        outliers.sort(key=lambda x: str(x.created_at) or '', reverse=True)

        return {
            "proposals": proposals,
            "surprises": outliers[:5],  # Top 5 surprises
            "stats": {
                "total_active": len(active_learnings),
                "digested": len(covered_ids),
                "undigested": len(active_learnings) - len(covered_ids)
            }
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # AGENT-ASSISTED SYNTHESIS (System 2)
    # ═══════════════════════════════════════════════════════════════════════════

    def get_undigested_learnings(self, domain: Optional[str] = None) -> List[Entity]:
        """
        Get learnings that are NOT yet linked to any pattern.

        A learning is considered "digested" if:
        - It appears in a pattern's extracted_from/induced_from list, OR
        - It has a link to a pattern-* entity
        """
        # 1. Get all captured/validated learnings
        try:
            all_learnings = self.repository.list(entity_type="learning", limit=1000)
        except Exception:
            return []

        candidates = [l for l in all_learnings if l.status in ('captured', 'validated')]

        if domain:
            candidates = [l for l in candidates if l.data.get('domain') == domain]

        # 2. Get all patterns to find what's already consumed
        patterns = self.repository.list(entity_type="pattern", limit=1000)
        consumed_ids = set()

        for p in patterns:
            # Check extracted_from field
            extracted = p.data.get('extracted_from', [])
            if isinstance(extracted, list):
                for uid in extracted:
                    consumed_ids.add(uid)
            elif isinstance(extracted, str):
                consumed_ids.add(extracted)

            # Check induced_from field (alternate naming)
            induced = p.data.get('induced_from', [])
            if isinstance(induced, list):
                for uid in induced:
                    consumed_ids.add(uid)

        # 3. Filter out consumed learnings
        undigested = [l for l in candidates if l.id not in consumed_ids]

        # 4. Also exclude learnings that link TO a pattern (bi-directional check)
        final_undigested = []
        for l in undigested:
            links_to_pattern = False
            for link in l.data.get('links', []):
                if isinstance(link, str) and link.startswith('pattern-'):
                    links_to_pattern = True
                    break
            if not links_to_pattern:
                final_undigested.append(l)

        return final_undigested

    def get_batch(
        self,
        size: int = 10,
        domain: Optional[str] = None,
        strategy: str = "oldest"
    ) -> List[Entity]:
        """
        Sample a batch of undigested learnings for the agent to process.

        Args:
            size: Number of learnings to return
            domain: Optional domain filter
            strategy: "oldest" | "newest" | "random"
        """
        candidates = self.get_undigested_learnings(domain)

        if strategy == "random":
            random.shuffle(candidates)
        elif strategy == "newest":
            candidates.sort(key=lambda x: str(x.created_at) or '', reverse=True)
        else:  # oldest (default) - digest oldest first
            candidates.sort(key=lambda x: str(x.created_at) or '')

        return candidates[:size]

    def synthesize(
        self,
        name: str,
        learning_ids: List[str],
        insight: str,
        domain: str,
        confidence: str = "medium"
    ) -> Entity:
        """
        Crystallize a group of learnings into a proposed pattern.

        Creates bi-directional links:
        - Pattern.extracted_from -> [learning_ids]
        - Each learning.links -> [pattern_id]

        Args:
            name: Name for the new pattern
            learning_ids: List of learning IDs being synthesized
            insight: The synthesized insight/solution
            domain: Domain for the pattern
            confidence: "low" | "medium" | "high"

        Returns:
            The created pattern entity
        """
        from .factory import EntityFactory
        factory = EntityFactory(repository=self.repository)

        # Create the pattern with status 'experimental' (per kernel schema)
        pattern = factory.create(
            "pattern",
            name,
            status="experimental",
            context=f"Agent-synthesized from {len(learning_ids)} learnings",
            problem=f"Emergent pattern in domain '{domain}'",
            solution=insight,
            domain=domain,
            extracted_from=learning_ids,
            synthesis_confidence=confidence,
            subtype="behavioral"  # Default subtype
        )

        # Create bi-directional links: learning -> pattern
        for lid in learning_ids:
            learning = self.repository.read(lid)
            if learning:
                links = learning.data.get('links', [])
                if pattern.id not in links:
                    links.append(pattern.id)
                    # Update learning with new link (keep current version, repo increments)
                    updated = learning.copy(data={**learning.data, 'links': links})
                    self.repository.update(updated)

        return pattern

    # ═══════════════════════════════════════════════════════════════════════════
    # TIERED SYNTHESIS (Push Right Pattern)
    # ═══════════════════════════════════════════════════════════════════════════

    def tiered_synthesize(
        self,
        learning_ids: List[str],
        max_tier: str = "inference",
        confidence_threshold: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Synthesize learnings using tiered resolution.

        Tries cheaper tiers first and escalates when needed.
        Captures traces of each tier attempt for future crystallization.

        Flow:
          1. workflow tier: Use PatternInductor's algorithmic clustering
          2. inference tier: Use LLM for semantic synthesis (if workflow insufficient)

        Args:
            learning_ids: List of learning IDs to synthesize
            max_tier: Maximum tier to escalate to ("workflow" | "inference")
            confidence_threshold: Minimum confidence to accept workflow tier result

        Returns:
            {
                "success": bool,
                "tier_used": str,
                "result": PatternProposal | None,
                "escalation_reason": str | None,
                "traces": List[str]  # trace IDs
            }
        """
        traces = []
        result: Dict[str, Any] = {
            "success": False,
            "tier_used": None,
            "result": None,
            "escalation_reason": None,
            "traces": traces,
        }

        # Validate inputs
        if not learning_ids:
            result["escalation_reason"] = "No learning IDs provided"
            return result

        # Load learnings
        learnings = []
        for lid in learning_ids:
            entity = self.repository.read(lid)
            if entity:
                learnings.append(entity)

        if len(learnings) < 2:
            result["escalation_reason"] = f"Need at least 2 learnings, got {len(learnings)}"
            return result

        # --- TIER 0: Data (Route Lookup - Push-Right crystallization) ---
        # Check if we have a crystallized route for this input
        route_table = RouteTable(self.repository)
        input_signature = json.dumps(sorted(learning_ids))  # Canonical signature

        route = route_table.lookup("tool-learning-synthesize", input_signature)
        if route:
            with TraceCapture(
                self.repository,
                operation_type="synthesize",
                tier="data",
                capability_id="tool-learning-synthesize",
            ) as trace:
                trace.set_inputs(learning_ids)
                trace.step(f"Route hit: {route.id}")
                trace.set_cost(1.0)  # Minimal cost for data tier

                # Record the hit
                route_table.record_hit(route.id)

                # Parse the crystallized output
                try:
                    from .evaluator import PatternProposal
                    import uuid
                    output = json.loads(route.output_template)

                    # Map confidence string to float if needed
                    confidence_map = {"low": 0.4, "medium": 0.7, "high": 0.9}
                    confidence = output.get("confidence", 0.9)
                    if isinstance(confidence, str):
                        confidence = confidence_map.get(confidence, 0.7)

                    # Build description from context/solution if available
                    description_parts = []
                    if output.get("context"):
                        description_parts.append(f"Context: {output['context']}")
                    if output.get("solution"):
                        description_parts.append(f"Solution: {output['solution']}")
                    description = " | ".join(description_parts) if description_parts else output.get("description", "Crystallized pattern")

                    proposal = PatternProposal(
                        id=f"pattern-{uuid.uuid4().hex[:12]}",
                        name=output.get("name", "Crystallized Pattern"),
                        description=description,
                        source_learnings=output.get("source_learnings", learning_ids),
                        domain=output.get("domain", "engineering"),
                        confidence=confidence,
                        suggested_target="pattern",
                        suggested_fields={"keywords": output.get("keywords", [])},
                    )

                    trace.step(f"Resolved via crystallized route: {proposal.name}")
                    trace.set_outputs([f"proposal:{proposal.name}", f"route:{route.id}"])

                    result["success"] = True
                    result["tier_used"] = "data"
                    result["result"] = proposal
                    traces.append(trace.trace.id)
                    return result

                except (json.JSONDecodeError, KeyError) as e:
                    # Route output is malformed - record miss and continue to workflow
                    trace.step(f"Route output parse error: {e}, falling through to workflow")
                    route_table.record_miss(route.id)
                    traces.append(trace.trace.id)

        # --- TIER 1: Workflow (PatternInductor) ---
        with TraceCapture(
            self.repository,
            operation_type="synthesize",
            tier="workflow",
            capability_id="tool-learning-synthesize",
        ) as trace:
            trace.set_inputs(learning_ids)
            trace.step("Attempting workflow-tier synthesis via PatternInductor")
            trace.set_cost(10.0)  # Relative cost for workflow tier

            # Run algorithmic clustering on the specific learnings
            proposals = self._generate_proposals_from_learnings(learnings)

            if proposals:
                best = max(proposals, key=lambda p: p.confidence)
                trace.step(f"Found {len(proposals)} proposals, best confidence: {best.confidence:.2f}")

                if best.confidence >= confidence_threshold:
                    trace.step(f"Confidence {best.confidence:.2f} >= threshold {confidence_threshold}")
                    trace.set_outputs([f"proposal:{best.name}"])
                    result["success"] = True
                    result["tier_used"] = "workflow"
                    result["result"] = best
                    traces.append(trace.trace.id)
                    return result
                else:
                    trace.step(f"Confidence {best.confidence:.2f} < threshold {confidence_threshold}, escalating")
                    result["escalation_reason"] = f"Confidence {best.confidence:.2f} below threshold"
            else:
                trace.step("No proposals generated by PatternInductor")
                result["escalation_reason"] = "No clusters found"

            traces.append(trace.trace.id)

        # Check if we can escalate to inference tier
        if max_tier == "workflow":
            result["escalation_reason"] = f"Max tier is workflow, cannot escalate. {result['escalation_reason']}"
            return result

        # --- TIER 2: Inference (LLM) ---
        with TraceCapture(
            self.repository,
            operation_type="synthesize",
            tier="inference",
            capability_id="tool-learning-synthesize",
        ) as trace:
            trace.set_inputs(learning_ids)
            trace.step("Escalating to inference tier for semantic synthesis")
            trace.set_cost(100.0)  # Relative cost for inference tier

            # Prepare learning summaries for LLM prompt
            learning_summaries = []
            for l in learnings:
                insight = l.data.get("insight", "")
                domain = l.data.get("domain", "unknown")
                learning_summaries.append(f"- [{domain}] {insight}")

            # Check if inference tier is available
            if not HAS_INFERENCE:
                trace.step("chora-inference package not available - returning placeholder")
                trace.set_outputs([])
                result["tier_used"] = "inference"
                result["escalation_reason"] = "chora-inference package not installed"
                result["result"] = {
                    "requires_llm": True,
                    "learnings": learning_ids,
                    "learning_summaries": learning_summaries,
                    "suggested_prompt": self._build_synthesis_prompt(learnings),
                }
                traces.append(trace.trace.id)
                return result

            # Use chora-inference for LLM synthesis
            trace.step("Invoking LLM via chora-inference")
            try:
                registry = get_registry()
                client = InferenceClient()

                # Build the learnings text for the prompt
                learnings_text = self._build_synthesis_prompt(learnings)

                # Render the prompt template
                system_prompt, user_prompt = registry.render(
                    "prompt-synthesize-learnings-v1",
                    learnings=learnings_text,
                )

                # Make the inference call
                inference_result = client.infer(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    json_output=True,
                )

                # Update trace with cost
                trace.set_cost(inference_result.cost_units)
                trace.step(f"LLM cost: {inference_result.cost_units:.2f} units")

                if inference_result.success:
                    # Parse the LLM output into a PatternProposal
                    from .evaluator import PatternProposal
                    output = inference_result.output

                    # Map confidence string to float
                    confidence_map = {"low": 0.4, "medium": 0.7, "high": 0.9}
                    confidence_str = output.get("confidence", "medium")
                    confidence = confidence_map.get(confidence_str, 0.7)

                    proposal = PatternProposal(
                        name=output.get("name", "Synthesized Pattern"),
                        context=output.get("context", ""),
                        solution=output.get("solution", ""),
                        domain=output.get("domain", "engineering"),
                        confidence=confidence,
                        learning_ids=output.get("source_learnings", learning_ids),
                        keywords=output.get("keywords", []),
                    )

                    trace.step(f"Created proposal: {proposal.name} (confidence: {confidence})")
                    trace.set_outputs([f"proposal:{proposal.name}"])

                    result["success"] = True
                    result["tier_used"] = "inference"
                    result["result"] = proposal
                    traces.append(trace.trace.id)
                    return result
                else:
                    trace.step(f"LLM inference failed: {inference_result.error}")
                    trace.set_outputs([])
                    result["tier_used"] = "inference"
                    result["escalation_reason"] = f"LLM inference failed: {inference_result.error}"
                    traces.append(trace.trace.id)
                    return result

            except Exception as e:
                trace.step(f"Exception during inference: {e}")
                trace.set_outputs([])
                result["tier_used"] = "inference"
                result["escalation_reason"] = f"Inference error: {e}"
                traces.append(trace.trace.id)

        return result

    def _generate_proposals_from_learnings(self, learnings: List[Entity] = None) -> List[Any]:
        """
        Generate pattern proposals from a specific set of learnings.

        This clusters learnings by keyword overlap and generates proposals.
        Note: This is distinct from parent's _cluster_learnings() which returns clusters.
        """
        from .evaluator import PatternProposal

        # Load learnings if not provided (maintains inheritance contract with parent)
        if learnings is None:
            learnings = self._load_learnings()

        if len(learnings) < 2:
            return []

        # Extract keywords from learnings
        learning_keywords: Dict[str, set] = {}
        for l in learnings:
            keywords = set()
            insight = l.data.get("insight", "")
            domain = l.data.get("domain", "")
            context = l.data.get("context", "")

            # Simple keyword extraction
            text = f"{insight} {domain} {context}".lower()
            words = [w for w in text.split() if len(w) > 4]
            keywords.update(words)
            learning_keywords[l.id] = keywords

        # Find overlapping learnings (simple clustering)
        proposals = []
        seen = set()

        for l1 in learnings:
            if l1.id in seen:
                continue

            cluster = [l1]
            for l2 in learnings:
                if l2.id == l1.id or l2.id in seen:
                    continue
                # Check keyword overlap
                overlap = learning_keywords[l1.id] & learning_keywords[l2.id]
                if len(overlap) >= 2:
                    cluster.append(l2)
                    seen.add(l2.id)

            if len(cluster) >= 2:
                seen.add(l1.id)
                # Build proposal
                domain = cluster[0].data.get("domain", "general")
                keywords = set()
                for c in cluster:
                    keywords.update(learning_keywords[c.id])

                # Calculate confidence based on cluster cohesion
                confidence = min(1.0, len(cluster) / len(learnings) + 0.3)

                # Generate a unique ID for the proposal
                proposal_id = f"pattern-cluster-{uuid.uuid4().hex[:8]}"
                keyword_list = list(keywords)[:5]

                proposals.append(PatternProposal(
                    id=proposal_id,
                    name=f"Emergent pattern from {len(cluster)} learnings",
                    description=f"Pattern induced from learnings: {', '.join(keyword_list)}",
                    domain=domain,
                    source_learnings=[c.id for c in cluster],
                    confidence=confidence,
                    suggested_target="",  # No specific target yet
                    suggested_fields={kw: True for kw in keyword_list},
                ))

        return proposals

    def _build_synthesis_prompt(self, learnings: List[Entity]) -> str:
        """Build a prompt for LLM-based synthesis."""
        lines = ["Given these learnings:"]
        for l in learnings:
            insight = l.data.get("insight", "")
            domain = l.data.get("domain", "unknown")
            lines.append(f"- [{l.id}] ({domain}): {insight}")

        lines.append("")
        lines.append("Extract a reusable pattern with:")
        lines.append("- name: (descriptive)")
        lines.append("- context: (when to apply)")
        lines.append("- solution: (what to do)")
        lines.append("- domain: (which area)")
        lines.append("- confidence: (low|medium|high)")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTO-CRYSTALLIZATION CRON HOOK
    # ═══════════════════════════════════════════════════════════════════════════

    def auto_crystallize_cron(
        self,
        min_traces: int = 5,
        consistency_threshold: float = 0.95,
        factory=None,
    ) -> Dict[str, Any]:
        """
        Cron hook for automatic route crystallization.

        This method is designed to be called periodically (e.g., cron:daily)
        to crystallize high-frequency trace patterns into data-tier routes.

        Args:
            min_traces: Minimum traces required for crystallization (default 5)
            consistency_threshold: Required output consistency (default 0.95)
            factory: Optional EntityFactory for creating learnings (uses global if not provided)

        Returns:
            {
                "routes_created": int,
                "tools_processed": int,
                "learning_id": str | None,
                "details": List[Dict]  # Per-route details
            }
        """
        route_table = RouteTable(self.repository)

        # Find all unique tool IDs with traces
        tool_ids = set()
        with self.repository._connection() as conn:
            for row in conn.execute(
                """SELECT DISTINCT capability_id FROM traces
                   WHERE success = 1 AND tier IN ('inference', 'agent')
                   AND capability_id IS NOT NULL"""
            ):
                tool_ids.add(row["capability_id"])

        result = {
            "routes_created": 0,
            "tools_processed": len(tool_ids),
            "learning_id": None,
            "details": [],
        }

        # Process each tool
        all_new_routes = []
        for tool_id in tool_ids:
            new_routes = route_table.auto_crystallize(
                tool_id=tool_id,
                min_traces=min_traces,
                consistency_threshold=consistency_threshold,
            )
            for route in new_routes:
                all_new_routes.append(route)
                result["details"].append({
                    "route_id": route.id,
                    "tool_id": route.tool_id,
                    "input_signature": route.input_signature[:50] + "..." if len(route.input_signature) > 50 else route.input_signature,
                })

        result["routes_created"] = len(all_new_routes)

        # Emit summary learning if routes were created
        if all_new_routes:
            fact = factory or _get_factory()
            try:
                learning = fact.create(
                    "learning",
                    f"Auto-crystallized {len(all_new_routes)} routes",
                    insight=(
                        f"Cron hook crystallized {len(all_new_routes)} routes from "
                        f"{len(tool_ids)} tools. Hot inference operations have "
                        f"cooled into data-tier lookups."
                    ),
                    domain="tiered-resolution",
                    implications=(
                        "System metabolic efficiency increases as more operations "
                        "resolve at cheaper tiers."
                    ),
                    related=[r.id for r in all_new_routes[:10]],  # Link first 10
                )
                result["learning_id"] = learning.id
            except Exception:
                # Learning creation is optional
                pass

        return result

    def route_teach_back_cron(
        self,
        hit_threshold: int = 10,
        factory=None,
    ) -> Dict[str, Any]:
        """
        Cron hook for routes teaching back.

        This method evaluates successful routes and generates learnings about
        what crystallizes well. These learnings can cluster into meta-patterns
        about crystallizability - the system developing "taste" for what
        operations are good candidates for crystallization.

        Args:
            hit_threshold: Base threshold for teaching (default 10)
            factory: Optional EntityFactory for creating learnings

        Returns:
            {
                "learnings_generated": int,
                "routes_evaluated": int,
                "routes_marked": int,
                "flagged_for_review": int,
                "details": List[Dict]
            }
        """
        route_table = RouteTable(self.repository)
        fact = factory or _get_factory()

        result = {
            "learnings_generated": 0,
            "routes_evaluated": 0,
            "routes_marked": 0,
            "flagged_for_review": 0,
            "details": [],
        }

        # Get all routes that might be ready for teaching
        # (hit_count >= threshold and not already taught at that level)
        routes = route_table.list_routes(status="active", limit=1000)
        routes.extend(route_table.list_routes(status="canary", limit=1000))

        for route in routes:
            if route.hit_count < hit_threshold:
                continue

            result["routes_evaluated"] += 1

            teach_result = route_table.evaluate_for_teaching(
                route_id=route.id,
                hit_threshold=hit_threshold,
                factory=fact,
            )

            if teach_result.get("generated"):
                result["learnings_generated"] += 1
                result["routes_marked"] += 1
                result["details"].append({
                    "route_id": route.id,
                    "learning_id": teach_result.get("learning_id"),
                    "hit_count": route.hit_count,
                })
            elif teach_result.get("flagged_for_review"):
                result["flagged_for_review"] += 1

        return result


def tool_induction(domain: Optional[str] = None) -> str:
    """
    The Stomach - Metabolic processing of learnings.

    Clusters learnings into pattern proposals and identifies outliers
    (surprises) that may indicate new areas of exploration.
    """
    repo = EntityRepository()
    engine = MetabolicEngine(repo)

    result = engine.digest(domain)

    lines = ["METABOLIC REPORT"]
    lines.append("=" * 40)

    stats = result['stats']
    digested_pct = (stats['digested'] / stats['total_active'] * 100) if stats['total_active'] > 0 else 0
    lines.append(f"Status: {stats['digested']}/{stats['total_active']} learnings digested ({digested_pct:.0f}%)")
    lines.append(f"Undigested: {stats['undigested']} learnings awaiting synthesis")

    if result['proposals']:
        lines.append("")
        lines.append("PATTERN PROPOSALS (Crystallization Candidates):")
        for p in result['proposals']:
            conf = int(p.confidence * 100)
            lines.append(f"  [{conf}%] {p.name}")
            lines.append(f"       Domain: {p.domain}")
            lines.append(f"       Sources: {len(p.source_learnings)} learnings")
            if p.suggested_target:
                lines.append(f"       Target: {p.suggested_target}")

    if result['surprises']:
        lines.append("")
        lines.append("SURPRISES (Mutation Candidates):")
        lines.append("  Learnings that don't cluster - potential new directions:")
        for s in result['surprises']:
            insight = s.data.get('insight', '')[:60].replace('\n', ' ')
            domain_str = s.data.get('domain', 'no domain')
            lines.append(f"  ? {s.id}")
            lines.append(f"    \"{insight}...\"")
            lines.append(f"    ({domain_str})")

    if not result['proposals'] and not result['surprises']:
        lines.append("")
        lines.append("(System is metabolically balanced. No clusters or outliers found.)")

    return "\n".join(lines)


def tool_auto_induction(
    min_learnings: int = 2,
    confidence_threshold: float = 0.7,
    auto_approve: bool = True,
    max_approvals: int = 3,
    include_cross_domain: bool = False,
) -> str:
    """
    Continuous Mutation Engine - runs induction and auto-approves.

    This tool is designed to be invoked by a cron:daily hook to maintain
    continuous mutation pressure in the autoevolutionary loop.

    Args:
        min_learnings: Minimum learnings per cluster (default 2)
        confidence_threshold: Minimum confidence to auto-approve (default 0.7)
        auto_approve: Whether to auto-approve high-confidence proposals
        max_approvals: Maximum proposals to approve per run (default 3)
        include_cross_domain: Whether to detect cross-domain bridges (default False)

    Returns:
        Report of proposals found and patterns approved
    """
    from .evaluator import PatternInductor
    from .models import Entity

    repo = EntityRepository()
    inductor = PatternInductor(repo, thresholds={
        "min_learnings": min_learnings,
        "confidence_threshold": 0.6,  # Lower threshold to see more proposals
        "max_proposals": 5,
        "keyword_overlap": 0.05,
        "embedding_similarity": 0.70,
    })

    proposals = inductor.analyze(include_cross_domain=include_cross_domain)
    approved = []
    skipped = []

    if auto_approve and proposals:
        for p in proposals:
            if len(approved) >= max_approvals:
                skipped.append((p, "max_approvals reached"))
                continue

            if p.confidence >= confidence_threshold:
                try:
                    pattern = inductor.approve_proposal(p)
                    if pattern:
                        approved.append((p, pattern))
                except Exception as e:
                    skipped.append((p, f"error: {e}"))
            else:
                skipped.append((p, f"confidence {p.confidence:.2f} < {confidence_threshold}"))

    # Build report
    lines = ["AUTO-INDUCTION REPORT"]
    lines.append("=" * 40)
    lines.append(f"Proposals found: {len(proposals)}")
    lines.append(f"Auto-approved: {len(approved)}")
    lines.append(f"Skipped: {len(skipped)}")

    if approved:
        lines.append("")
        lines.append("APPROVED PATTERNS:")
        for proposal, pattern in approved:
            lines.append(f"  ✓ {pattern.id}")
            if proposal.cross_domain:
                domain_str = " + ".join(proposal.source_domains)
                lines.append(f"    From: {len(proposal.source_learnings)} learnings spanning '{domain_str}' (CROSS-DOMAIN)")
                lines.append(f"    Bridge strength: {proposal.bridge_strength:.2f}")
            else:
                lines.append(f"    From: {len(proposal.source_learnings)} learnings in '{proposal.domain}'")
            lines.append(f"    Confidence: {proposal.confidence:.2f}")
            gen = pattern.data.get("loop_generation", "?")
            lines.append(f"    Loop generation: {gen}")

    if skipped:
        lines.append("")
        lines.append("SKIPPED (requires manual review):")
        for proposal, reason in skipped:
            lines.append(f"  - {proposal.name}")
            lines.append(f"    Reason: {reason}")

    if not proposals:
        lines.append("")
        lines.append("(No proposals ready. System metabolically balanced.)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT-ASSISTED SYNTHESIS TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def tool_digest_batch(
    size: int = 10,
    domain: Optional[str] = None,
    strategy: str = "oldest"
) -> str:
    """
    The Spoonful - sample undigested learnings for agent analysis.

    Returns a batch of learnings formatted for the agent to read,
    analyze, and propose synthesis.

    Args:
        size: Number of learnings to sample (default 10)
        domain: Optional domain filter
        strategy: "oldest" | "newest" | "random"
    """
    repo = EntityRepository()
    engine = MetabolicEngine(repo)

    batch = engine.get_batch(size, domain, strategy)

    if not batch:
        if domain:
            return f"No undigested learnings found in domain '{domain}'."
        return "No undigested learnings found. System is metabolically balanced."

    lines = [f"DIGESTION BATCH ({len(batch)} learnings, strategy: {strategy})"]
    lines.append("=" * 60)

    for i, learning in enumerate(batch, 1):
        domain_str = learning.data.get('domain', 'no-domain')
        insight = learning.data.get('insight', 'No insight text')
        context = learning.data.get('context', '')

        lines.append(f"\n[{i}] {learning.id}")
        lines.append(f"    Domain: {domain_str} | Status: {learning.status}")
        lines.append(f"    Insight: \"{insight}\"")
        if context:
            lines.append(f"    Context: {context[:100]}...")

    lines.append("\n" + "=" * 60)
    lines.append("TASK: Analyze these learnings.")
    lines.append("  1. Which learnings cluster together semantically?")
    lines.append("  2. What pattern emerges from the cluster?")
    lines.append("  3. Which learnings are outliers (potential new inquiries)?")
    lines.append("\nUse propose_synthesis(name, learning_ids, insight, domain) to crystallize.")

    return "\n".join(lines)


def tool_suggest_patterns(entity_type: str, context: str = "") -> str:
    """
    Pattern Discovery - suggest applicable patterns before entity creation.

    Surfaces patterns that may be relevant for the entity being created.
    Helps agents discover existing wisdom before reinventing solutions.

    Args:
        entity_type: The type of entity being created (e.g., 'feature', 'inquiry')
        context: Optional context about what the entity will do

    Returns:
        Formatted list of applicable patterns with relevance
    """
    repo = EntityRepository()

    # Get all patterns (any status - even experimental might be relevant)
    patterns = repo.list(entity_type='pattern', limit=100)

    if not patterns:
        return "No patterns found in the system yet."

    # Categorize patterns by applicability
    direct_match = []      # mechanics.target matches entity_type
    universal = []         # process/architectural patterns (apply broadly)
    keyword_match = []     # context keywords match pattern context/problem

    context_lower = context.lower() if context else ""

    for p in patterns:
        mechanics = p.data.get('mechanics', {})
        target = mechanics.get('target', '') if isinstance(mechanics, dict) else ''
        subtype = p.data.get('subtype', '')

        # Direct match: schema-extension patterns targeting this entity type
        if target == entity_type:
            direct_match.append(p)
            continue

        # Universal: process and architectural patterns apply broadly
        if subtype in ('process', 'architectural', 'meta'):
            universal.append(p)
            continue

        # Keyword match: check if context overlaps with pattern context/problem
        if context_lower:
            pattern_context = p.data.get('context', '').lower()
            pattern_problem = p.data.get('problem', '').lower()
            pattern_name = p.data.get('name', '').lower()

            # Simple keyword overlap check
            context_words = set(context_lower.split())
            pattern_words = set(pattern_context.split() + pattern_problem.split() + pattern_name.split())
            overlap = context_words & pattern_words
            # Require at least 2 significant word overlaps
            significant = [w for w in overlap if len(w) > 4]
            if len(significant) >= 2:
                keyword_match.append((p, significant))

    # Build output
    lines = [f"PATTERN DISCOVERY for {entity_type}"]
    lines.append("=" * 50)

    if not (direct_match or universal or keyword_match):
        lines.append(f"No patterns specifically target '{entity_type}'.")
        lines.append("Consider whether this is a novel area needing patterns.")
        return "\n".join(lines)

    if direct_match:
        lines.append(f"\nDIRECT ({len(direct_match)} patterns target {entity_type}):")
        for p in direct_match:
            status_icon = "✓" if p.status == 'adopted' else "⚗" if p.status == 'experimental' else "○"
            lines.append(f"  {status_icon} {p.id}")
            desc = p.data.get('description', '')[:80] or p.data.get('solution', '')[:80]
            if desc:
                lines.append(f"      {desc}...")
            inject_fields = p.data.get('mechanics', {}).get('inject_fields', {})
            if inject_fields:
                lines.append(f"      Injects: {list(inject_fields.keys())}")

    if universal:
        lines.append(f"\nUNIVERSAL ({len(universal)} broadly applicable patterns):")
        for p in universal[:5]:  # Limit to top 5
            status_icon = "✓" if p.status == 'adopted' else "⚗" if p.status == 'experimental' else "○"
            lines.append(f"  {status_icon} {p.id} ({p.data.get('subtype', '')})")
            desc = p.data.get('description', '')[:60] or p.data.get('solution', '')[:60]
            if desc:
                lines.append(f"      {desc}...")
        if len(universal) > 5:
            lines.append(f"  ... and {len(universal) - 5} more")

    if keyword_match:
        lines.append(f"\nCONTEXT MATCHES ({len(keyword_match)} by keyword overlap):")
        for p, keywords in keyword_match[:3]:
            status_icon = "✓" if p.status == 'adopted' else "⚗" if p.status == 'experimental' else "○"
            lines.append(f"  {status_icon} {p.id}")
            lines.append(f"      Matching keywords: {', '.join(keywords[:5])}")

    lines.append("\n" + "-" * 50)
    lines.append("Legend: ✓ adopted | ⚗ experimental | ○ proposed")
    lines.append("Consider: Do any of these patterns apply to your work?")

    return "\n".join(lines)


def tool_propose_synthesis(
    name: str,
    learning_ids: List[str],
    insight: str,
    domain: str,
    confidence: str = "medium"
) -> str:
    """
    The Crystallization - create a pattern from a group of learnings.

    The agent proposes a synthesis after analyzing a batch.
    Creates bi-directional links between pattern and source learnings.

    Args:
        name: Human-readable name for the pattern
        learning_ids: List of learning IDs being synthesized
        insight: The synthesized insight/solution
        domain: Domain for the pattern
        confidence: "low" | "medium" | "high"
    """
    repo = EntityRepository()
    engine = MetabolicEngine(repo)

    # Validate inputs
    if not name or not name.strip():
        return "Error: Pattern name is required"
    if not learning_ids or len(learning_ids) < 2:
        return "Error: At least 2 learning IDs required for synthesis"
    if not insight or not insight.strip():
        return "Error: Insight text is required"
    if not domain or not domain.strip():
        return "Error: Domain is required"

    # Verify all learnings exist
    missing = []
    for lid in learning_ids:
        if not repo.read(lid):
            missing.append(lid)
    if missing:
        return f"Error: Learning(s) not found: {', '.join(missing)}"

    try:
        pattern = engine.synthesize(name, learning_ids, insight, domain, confidence)
        return (
            f"Pattern synthesized successfully!\n"
            f"  ID: {pattern.id}\n"
            f"  Status: {pattern.status}\n"
            f"  Domain: {domain}\n"
            f"  Confidence: {confidence}\n"
            f"  Source learnings: {len(learning_ids)}\n"
            f"\nLearnings have been linked to this pattern."
        )
    except Exception as e:
        return f"Error during synthesis: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# FOCUS CREATION FROM NATURAL LANGUAGE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_focus_create(
    goal: str,
    target: Optional[str] = None,
    agent: str = "claude",
    ttl_minutes: int = 240,
    repository: Optional[EntityRepository] = None,
) -> str:
    """
    Create focus from natural language goal description.

    Fills the creation gap in the focus lifecycle - enables agents to create
    focus entities without requiring a pre-existing feature to engage.

    Args:
        goal: Natural language description of what to focus on
        target: Optional explicit target entity ID (feature-*, inquiry-*, etc.)
        agent: Agent creating the focus (default: "claude")
        ttl_minutes: Time-to-live in minutes (default: 240 = 4 hours)
        repository: Optional repository (uses global if not provided)

    Returns:
        Status message with focus ID or error
    """
    repo = repository or EntityRepository()
    # Create factory with test repository if provided
    if repository:
        from .factory import EntityFactory
        factory = EntityFactory(repository=repository)
    else:
        factory = _get_factory()

    # If target provided, validate it exists
    resolved_target = None
    candidate_targets = []
    created_inquiry = None

    if target:
        entity = repo.read(target)
        if not entity:
            return f"Error: Target entity '{target}' not found"
        resolved_target = target
    else:
        # Try to resolve target from goal text
        resolved_target, candidate_targets = _resolve_target_from_goal(repo, goal)

    # If no target resolved, create implicit inquiry from goal
    # Focus requires a target - we create an inquiry to hold the goal
    if not resolved_target:
        created_inquiry = factory.create(
            "inquiry",
            goal,
            question=goal,
            domain="focus-created",
        )
        resolved_target = created_inquiry.id

    # Generate focus name from goal
    focus_name = _generate_focus_name(goal, agent)

    # Build focus data
    focus_data = {
        "agent": agent,
        "entry_type": "natural_language",
        "goal_level": True,
        "ttl_minutes": ttl_minutes,
        "trail": [],
        "original_goal": goal,
    }

    if resolved_target:
        focus_data["target"] = resolved_target
        focus_data["links"] = [resolved_target]

    if candidate_targets:
        focus_data["candidate_targets"] = candidate_targets

    # Create focus via factory (applies epigenetic patterns)
    try:
        focus = factory.create(
            "focus",
            focus_name,
            target=resolved_target,
            agent=agent,
            entry_type="natural_language",
            goal_level=True,
            ttl_minutes=ttl_minutes,
            trail=[],
            original_goal=goal,
            candidate_targets=candidate_targets if candidate_targets else None,
        )

        result = f"Focus created: {focus.id}"
        if resolved_target:
            result += f" → {resolved_target}"
        if candidate_targets:
            result += f"\nAmbiguous target - candidates: {candidate_targets}"

        return result

    except Exception as e:
        return f"Error creating focus: {e}"


def _resolve_target_from_goal(repo: EntityRepository, goal: str) -> tuple:
    """
    Attempt to resolve a target entity from goal text.

    Returns:
        (resolved_target, candidate_targets) - resolved if single match,
        candidates if ambiguous, both None if no match
    """
    goal_lower = goal.lower()
    goal_words = set(goal_lower.split())

    # Search features and inquiries for matches
    candidates = []

    def score_match(name: str) -> int:
        """Score how well entity name matches goal. Returns 0 for no match."""
        name_lower = name.lower()
        name_words = set(name_lower.split())
        # Check bidirectional: goal in name OR name in goal OR word overlap
        if name_lower in goal_lower or goal_lower in name_lower:
            return len(name)
        # Check word overlap
        overlap = goal_words & name_words
        if overlap:
            return len(overlap) * 10  # Weight by overlap count
        return 0

    # Check features
    features = repo.list(entity_type="feature", limit=100)
    for f in features:
        name = f.data.get("name", "")
        score = score_match(name)
        if score > 0:
            candidates.append((f.id, score))

    # Check inquiries
    inquiries = repo.list(entity_type="inquiry", limit=100)
    for i in inquiries:
        name = i.data.get("name", "")
        score = score_match(name)
        if score > 0:
            candidates.append((i.id, score))

    if not candidates:
        return None, []

    # Sort by match length (longer = more specific)
    candidates.sort(key=lambda x: -x[1])

    if len(candidates) == 1:
        return candidates[0][0], []

    # Multiple candidates - check if top match is significantly better
    if candidates[0][1] > candidates[1][1] * 1.5:
        return candidates[0][0], []

    # Ambiguous - return candidates
    candidate_ids = [c[0] for c in candidates[:5]]  # Top 5
    return None, candidate_ids


def _generate_focus_name(goal: str, agent: str) -> str:
    """
    Generate a focus name from goal description.

    Examples:
        "Implement cross-domain detection" → "Implementing cross-domain detection"
        "Work on voice canvas" → "Working on voice canvas"
    """
    goal = goal.strip()

    # Convert imperative to gerund if possible
    if goal.lower().startswith("implement"):
        return "Implementing" + goal[9:]
    elif goal.lower().startswith("work on"):
        return "Working on" + goal[7:]
    elif goal.lower().startswith("build"):
        return "Building" + goal[5:]
    elif goal.lower().startswith("fix"):
        return "Fixing" + goal[3:]
    elif goal.lower().startswith("explore"):
        return "Exploring" + goal[7:]
    elif goal.lower().startswith("investigate"):
        return "Investigating" + goal[11:]
    elif goal.lower().startswith("add"):
        return "Adding" + goal[3:]
    elif goal.lower().startswith("create"):
        return "Creating" + goal[6:]
    elif goal.lower().startswith("design"):
        return "Designing" + goal[6:]
    elif goal.lower().startswith("research"):
        return "Researching" + goal[8:]

    # Default: just capitalize
    return goal[0].upper() + goal[1:]
