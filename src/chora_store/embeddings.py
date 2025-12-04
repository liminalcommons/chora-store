"""
Embedding service for semantic similarity in distillation and clustering.

This module provides vector embeddings for entity text to enable semantic search,
clustering, and distillation operations.

Providers:
- local (default): sentence-transformers, free, works offline
- openai: OpenAI API, better semantic understanding, requires API key

The service:
1. Generates embeddings from entity text (name + insight/description)
2. Caches embeddings in SQLite for reuse
3. Provides cosine similarity for clustering
4. Supports model versioning (different models can coexist)

Usage:
    # Local (default)
    service = EmbeddingService(db_path)

    # OpenAI
    service = EmbeddingService(db_path, provider='openai')

    emb1 = service.get_or_create_embedding(entity1)
    emb2 = service.get_or_create_embedding(entity2)
    similarity = service.cosine_similarity(emb1, emb2)
"""

import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Tuple
import logging

import numpy as np

from .models import Entity

logger = logging.getLogger(__name__)

# Default models per provider
DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"  # Good balance of quality/cost

# Provider-aware default thresholds
# Local embeddings (sentence-transformers) produce lower similarity scores
# OpenAI embeddings produce higher similarity scores for equivalent semantic distance
DEFAULT_THRESHOLDS = {
    'local': {
        'similarity': 0.65,   # For find_similar operations
        'clustering': 0.70,   # For cluster_by_similarity operations
    },
    'openai': {
        'similarity': 0.80,   # Higher because OpenAI scores are more spread
        'clustering': 0.85,   # Higher for tighter clusters
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Embedding Providers (Strategy Pattern)
# ═══════════════════════════════════════════════════════════════════════════════

class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier for caching."""
        pass

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts efficiently."""
        pass


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.

    Pros: Free, works offline, fast for small batches
    Cons: Lower semantic quality than OpenAI
    """

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL):
        self._model_name = model_name
        self._model = None
        self._dim = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading local embedding model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
                self._dim = self._model.get_sentence_embedding_dimension()
                logger.info(f"Model loaded. Embedding dimension: {self._dim}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    @property
    def embedding_dim(self) -> int:
        if self._dim is None:
            _ = self.model  # Trigger lazy load
        return self._dim

    def embed_text(self, text: str) -> np.ndarray:
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 10
        )
        return list(embeddings)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embedding provider using the API.

    Pros: Better semantic understanding, handles nuance
    Cons: Requires API key, costs money, needs network

    Models:
    - text-embedding-3-small: 1536 dims, $0.02/1M tokens (recommended)
    - text-embedding-3-large: 3072 dims, $0.13/1M tokens (highest quality)
    - text-embedding-ada-002: 1536 dims, $0.10/1M tokens (legacy)
    """

    # Dimensions per model
    MODEL_DIMS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, model_name: str = DEFAULT_OPENAI_MODEL, api_key: Optional[str] = None):
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None

        if model_name not in self.MODEL_DIMS:
            raise ValueError(f"Unknown OpenAI model: {model_name}. Use one of: {list(self.MODEL_DIMS.keys())}")

    @property
    def model_name(self) -> str:
        return f"openai:{self._model_name}"

    @property
    def embedding_dim(self) -> int:
        return self.MODEL_DIMS[self._model_name]

    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                    "or pass api_key to OpenAIEmbeddingProvider."
                )
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
                logger.info(f"OpenAI client initialized with model: {self._model_name}")
            except ImportError:
                raise ImportError(
                    "openai package is required for OpenAI embeddings. "
                    "Install with: pip install openai"
                )
        return self._client

    def embed_text(self, text: str) -> np.ndarray:
        response = self.client.embeddings.create(
            model=self._model_name,
            input=text,
        )
        embedding = np.array(response.data[0].embedding, dtype=np.float32)
        # Normalize for cosine similarity
        embedding = embedding / np.linalg.norm(embedding)
        return embedding

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        if not texts:
            return []

        # OpenAI supports batching up to 2048 texts
        response = self.client.embeddings.create(
            model=self._model_name,
            input=texts,
        )

        embeddings = []
        for item in response.data:
            emb = np.array(item.embedding, dtype=np.float32)
            # Normalize for cosine similarity
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)

        return embeddings


# ═══════════════════════════════════════════════════════════════════════════════
# Embedding Service (Main Interface)
# ═══════════════════════════════════════════════════════════════════════════════

class EmbeddingService:
    """
    Generates and caches embeddings for entity text.

    Supports multiple embedding providers:
    - 'local': sentence-transformers (default, free, offline)
    - 'openai': OpenAI API (better quality, requires API key)
    """

    def __init__(
        self,
        db_path: str,
        provider: str = 'local',
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the embedding service.

        Args:
            db_path: Path to the SQLite database
            provider: 'local' or 'openai'
            model_name: Model name (uses default for provider if not specified)
            api_key: API key for OpenAI (can also use OPENAI_API_KEY env var)
        """
        self.db_path = db_path
        self._provider_name = provider

        # Initialize provider
        if provider == 'local':
            self._provider = LocalEmbeddingProvider(
                model_name=model_name or DEFAULT_LOCAL_MODEL
            )
        elif provider == 'openai':
            self._provider = OpenAIEmbeddingProvider(
                model_name=model_name or DEFAULT_OPENAI_MODEL,
                api_key=api_key,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'local' or 'openai'.")

    @property
    def model_name(self) -> str:
        """Return the model identifier for caching."""
        return self._provider.model_name

    @property
    def embedding_dim(self) -> int:
        """Get the embedding dimension for the current model."""
        return self._provider.embedding_dim

    @property
    def provider_name(self) -> str:
        """Return the provider name ('local' or 'openai')."""
        return self._provider_name

    @staticmethod
    def get_default_thresholds() -> dict:
        """
        Get provider-specific default thresholds.

        Returns:
            Dict with thresholds per provider:
            {
                'local': {'similarity': 0.65, 'clustering': 0.70},
                'openai': {'similarity': 0.80, 'clustering': 0.85},
            }
        """
        return DEFAULT_THRESHOLDS.copy()

    def get_default_similarity_threshold(self) -> float:
        """Get default similarity threshold for the current provider."""
        return DEFAULT_THRESHOLDS[self._provider_name]['similarity']

    def get_default_clustering_threshold(self) -> float:
        """Get default clustering threshold for the current provider."""
        return DEFAULT_THRESHOLDS[self._provider_name]['clustering']

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Normalized embedding vector as numpy array
        """
        return self._provider.embed_text(text)

    def _extract_entity_text(self, entity: Entity) -> str:
        """
        Extract text from entity for embedding with type-aware field selection.

        Type-specific primary fields:
        - learning: insight
        - inquiry: core_concern
        - feature: description + problem
        - pattern: problem + solution + context
        """
        name = entity.data.get('name', '')

        # Type-specific primary text field
        if entity.type == 'learning':
            primary_text = entity.data.get('insight', '')
        elif entity.type == 'inquiry':
            primary_text = entity.data.get('core_concern', '')
        elif entity.type == 'feature':
            # Features: description (WHAT) + problem (WHY)
            description = entity.data.get('description', '')
            problem = entity.data.get('problem', '')
            primary_text = f"{description} {problem}".strip()
        elif entity.type == 'pattern':
            # Patterns: problem + solution + context (full semantic identity)
            problem = entity.data.get('problem', '')
            solution = entity.data.get('solution', '')
            context = entity.data.get('context', '')
            primary_text = f"{problem} {solution} {context}".strip()
        else:
            primary_text = entity.data.get('description', '')

        # Fallback to description if primary is empty
        if not primary_text:
            primary_text = entity.data.get('description', '')

        text = f"{name} {primary_text}".strip()

        if not text:
            # Fallback to entity ID if no text
            text = entity.id

        return text

    def embed_entity(self, entity: Entity) -> np.ndarray:
        """
        Generate embedding for entity with type-aware text extraction.

        Args:
            entity: Entity to embed

        Returns:
            Normalized embedding vector
        """
        text = self._extract_entity_text(entity)
        return self.embed_text(text)

    def get_cached_embedding(self, entity_id: str) -> Optional[np.ndarray]:
        """
        Get cached embedding from database.

        Args:
            entity_id: ID of entity to look up

        Returns:
            Cached embedding or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT embedding, embedding_dim FROM embeddings
                WHERE entity_id = ? AND model_name = ?
                """,
                (entity_id, self.model_name)
            )
            row = cursor.fetchone()
            if row:
                embedding_bytes, dim = row
                return np.frombuffer(embedding_bytes, dtype=np.float32)
            return None
        finally:
            conn.close()

    def cache_embedding(self, entity_id: str, embedding: np.ndarray) -> None:
        """
        Cache embedding in database.

        Args:
            entity_id: ID of entity
            embedding: Embedding vector to cache
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings
                (entity_id, model_name, embedding, embedding_dim, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    self.model_name,
                    embedding.astype(np.float32).tobytes(),
                    len(embedding),
                    datetime.now().isoformat()
                )
            )
            conn.commit()
        finally:
            conn.close()

    def get_or_create_embedding(self, entity: Entity) -> np.ndarray:
        """
        Get embedding from cache or generate and cache it.

        Args:
            entity: Entity to get embedding for

        Returns:
            Embedding vector
        """
        # Check cache first
        cached = self.get_cached_embedding(entity.id)
        if cached is not None:
            return cached

        # Generate and cache
        embedding = self.embed_entity(entity)
        self.cache_embedding(entity.id, embedding)
        return embedding

    def invalidate_cache(self, entity_id: str) -> None:
        """
        Remove cached embedding for entity (call when entity is updated).

        Args:
            entity_id: ID of entity to invalidate
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "DELETE FROM embeddings WHERE entity_id = ?",
                (entity_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Calculate cosine similarity between embeddings.

        Since embeddings are normalized, this is just the dot product.

        Args:
            emb1: First embedding
            emb2: Second embedding

        Returns:
            Cosine similarity in range [-1, 1], typically [0, 1] for text
        """
        return float(np.dot(emb1, emb2))

    def batch_embed_entities(self, entities: List[Entity]) -> List[np.ndarray]:
        """
        Efficiently embed multiple entities at once.

        Uses batch encoding which is much faster than individual calls.

        Args:
            entities: List of entities to embed

        Returns:
            List of embeddings in same order as entities
        """
        # Separate cached and uncached
        embeddings = []
        uncached_indices = []
        uncached_texts = []

        for i, entity in enumerate(entities):
            cached = self.get_cached_embedding(entity.id)
            if cached is not None:
                embeddings.append(cached)
            else:
                embeddings.append(None)
                uncached_indices.append(i)
                uncached_texts.append(self._extract_entity_text(entity))

        # Batch encode uncached
        if uncached_texts:
            new_embeddings = self._provider.embed_batch(uncached_texts)

            # Cache and fill in results
            for idx, (orig_idx, embedding) in enumerate(zip(uncached_indices, new_embeddings)):
                entity = entities[orig_idx]
                self.cache_embedding(entity.id, embedding)
                embeddings[orig_idx] = embedding

        return embeddings

    def find_similar(
        self,
        entity: Entity,
        candidates: List[Entity],
        threshold: float = 0.7,
        top_k: Optional[int] = None
    ) -> List[Tuple[Entity, float]]:
        """
        Find entities similar to the given entity.

        Args:
            entity: Entity to find similar entities for
            candidates: List of candidate entities to compare against
            threshold: Minimum similarity to include (default 0.7)
            top_k: Return only top K results (None for all above threshold)

        Returns:
            List of (entity, similarity) tuples, sorted by similarity descending
        """
        # Get embedding for target entity
        target_emb = self.get_or_create_embedding(entity)

        # Batch embed candidates
        candidate_embs = self.batch_embed_entities(candidates)

        # Calculate similarities
        similarities = []
        for i, (candidate, emb) in enumerate(zip(candidates, candidate_embs)):
            if candidate.id != entity.id:  # Don't match self
                sim = self.cosine_similarity(target_emb, emb)
                if sim >= threshold:
                    similarities.append((candidate, sim))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)

        if top_k is not None:
            similarities = similarities[:top_k]

        return similarities

    def cluster_by_similarity(
        self,
        entities: List[Entity],
        threshold: float = 0.7
    ) -> List[List[Entity]]:
        """
        Cluster entities by semantic similarity using greedy agglomerative approach.

        Args:
            entities: Entities to cluster
            threshold: Minimum similarity to be in same cluster

        Returns:
            List of clusters (each cluster is a list of entities)
        """
        if not entities:
            return []

        # Get all embeddings
        embeddings = self.batch_embed_entities(entities)

        # Track which entities are assigned
        assigned = set()
        clusters = []

        # Greedy clustering: start with unassigned, find all similar
        for i, entity in enumerate(entities):
            if entity.id in assigned:
                continue

            # Start new cluster with this entity
            cluster = [entity]
            assigned.add(entity.id)

            # Find all similar unassigned entities
            for j, other in enumerate(entities):
                if other.id in assigned or i == j:
                    continue

                sim = self.cosine_similarity(embeddings[i], embeddings[j])
                if sim >= threshold:
                    cluster.append(other)
                    assigned.add(other.id)

            clusters.append(cluster)

        return clusters


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════

def compare_providers(
    db_path: str,
    entity1: Entity,
    entity2: Entity,
) -> dict:
    """
    Compare similarity scores between local and OpenAI providers.

    Useful for evaluating whether OpenAI provides better semantic matching
    for specific entity pairs.

    Args:
        db_path: Path to SQLite database
        entity1: First entity
        entity2: Second entity

    Returns:
        Dict with similarity scores from each provider
    """
    results = {}

    # Local embeddings
    local_service = EmbeddingService(db_path, provider='local')
    local_emb1 = local_service.embed_entity(entity1)
    local_emb2 = local_service.embed_entity(entity2)
    results['local'] = {
        'model': local_service.model_name,
        'similarity': local_service.cosine_similarity(local_emb1, local_emb2),
    }

    # OpenAI embeddings (only if API key available)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            openai_service = EmbeddingService(db_path, provider='openai')
            openai_emb1 = openai_service.embed_entity(entity1)
            openai_emb2 = openai_service.embed_entity(entity2)
            results['openai'] = {
                'model': openai_service.model_name,
                'similarity': openai_service.cosine_similarity(openai_emb1, openai_emb2),
            }
        except Exception as e:
            results['openai'] = {'error': str(e)}
    else:
        results['openai'] = {'error': 'OPENAI_API_KEY not set'}

    return results
