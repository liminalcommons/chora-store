"""
Enhanced search capabilities for chora-store.

Provides snippet highlighting, ranking, faceted search, and autocomplete.
"""

import sqlite3
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

from .models import Entity


@dataclass
class SearchResult:
    """A search result with ranking and highlighting."""
    entity: Entity
    rank: float
    snippet: Optional[str] = None
    highlights: Optional[Dict[str, str]] = None


@dataclass
class FacetCount:
    """Count of entities per facet value."""
    value: str
    count: int


@dataclass
class SearchFacets:
    """Faceted search results."""
    types: List[FacetCount]
    statuses: List[FacetCount]


class EntitySearch:
    """
    Enhanced search capabilities using SQLite FTS5.

    Features:
    - Full-text search with BM25 ranking
    - Snippet extraction with highlighting
    - Faceted search (filter + count by type/status)
    - Prefix-based autocomplete suggestions
    """

    def __init__(self, db_path: str = "~/.chora/chora.db"):
        """
        Initialize search with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path).expanduser()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        include_snippets: bool = True,
    ) -> List[SearchResult]:
        """
        Search entities with ranking and optional snippets.

        Args:
            query: Search query (supports FTS5 syntax: AND, OR, NOT, "phrase")
            entity_type: Filter by entity type
            status: Filter by status
            limit: Maximum results
            offset: Skip first N results
            include_snippets: Include text snippets in results

        Returns:
            List of SearchResult with ranking and optional snippets
        """
        conn = self._get_connection()
        try:
            # Build the search query with optional type/status filters
            conditions = ["entities_fts MATCH ?"]
            params: List[Any] = [query]

            if entity_type:
                conditions.append("e.type = ?")
                params.append(entity_type)

            if status:
                conditions.append("e.status = ?")
                params.append(status)

            where_clause = " AND ".join(conditions)

            # FTS5 BM25 ranking (lower is better match)
            # Use snippet() for highlighted excerpts
            if include_snippets:
                sql = f"""
                    SELECT
                        e.*,
                        bm25(entities_fts) as rank,
                        snippet(entities_fts, 3, '<mark>', '</mark>', '...', 30) as name_snippet,
                        snippet(entities_fts, 4, '<mark>', '</mark>', '...', 50) as desc_snippet
                    FROM entities e
                    JOIN entities_fts fts ON e.rowid = fts.rowid
                    WHERE {where_clause}
                    ORDER BY rank
                    LIMIT ? OFFSET ?
                """
            else:
                sql = f"""
                    SELECT
                        e.*,
                        bm25(entities_fts) as rank
                    FROM entities e
                    JOIN entities_fts fts ON e.rowid = fts.rowid
                    WHERE {where_clause}
                    ORDER BY rank
                    LIMIT ? OFFSET ?
                """

            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()

            results = []
            for row in rows:
                entity = self._row_to_entity(row)

                # Build snippet from name or description highlights
                snippet = None
                highlights = None
                if include_snippets:
                    name_snip = row["name_snippet"] if "name_snippet" in row.keys() else None
                    desc_snip = row["desc_snippet"] if "desc_snippet" in row.keys() else None

                    if name_snip and "<mark>" in name_snip:
                        snippet = name_snip
                    elif desc_snip and "<mark>" in desc_snip:
                        snippet = desc_snip

                    highlights = {}
                    if name_snip:
                        highlights["name"] = name_snip
                    if desc_snip:
                        highlights["description"] = desc_snip

                results.append(SearchResult(
                    entity=entity,
                    rank=abs(row["rank"]),  # BM25 returns negative scores
                    snippet=snippet,
                    highlights=highlights if highlights else None,
                ))

            return results
        finally:
            conn.close()

    def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """
        Get autocomplete suggestions based on prefix.

        Searches entity names and IDs for matches.

        Args:
            prefix: Prefix to search for
            limit: Maximum suggestions

        Returns:
            List of suggested completions
        """
        if not prefix or len(prefix) < 2:
            return []

        conn = self._get_connection()
        try:
            # Search for names starting with prefix
            # Use FTS5 prefix search (term*)
            search_term = f"{prefix}*"

            rows = conn.execute(
                """
                SELECT DISTINCT
                    json_extract(e.data, '$.name') as name,
                    e.id
                FROM entities e
                JOIN entities_fts fts ON e.rowid = fts.rowid
                WHERE entities_fts MATCH ?
                ORDER BY length(json_extract(e.data, '$.name'))
                LIMIT ?
                """,
                (search_term, limit),
            ).fetchall()

            suggestions = []
            for row in rows:
                if row["name"]:
                    suggestions.append(row["name"])
                else:
                    # Fallback to ID if no name
                    suggestions.append(row["id"])

            return suggestions
        finally:
            conn.close()

    def highlight(
        self,
        entity_id: str,
        query: str,
        before: str = "<mark>",
        after: str = "</mark>",
    ) -> Dict[str, str]:
        """
        Get highlighted version of an entity's text fields.

        Args:
            entity_id: Entity to highlight
            query: Search terms to highlight
            before: Text to insert before matches
            after: Text to insert after matches

        Returns:
            Dict mapping field names to highlighted text
        """
        conn = self._get_connection()
        try:
            # Get the entity
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ?",
                (entity_id,)
            ).fetchone()

            if row is None:
                return {}

            data = json.loads(row["data"])
            name = data.get("name", "")
            description = data.get("description", "")

            # Simple highlighting - find query terms and wrap them
            result = {}
            query_terms = query.lower().split()

            if name:
                highlighted_name = name
                for term in query_terms:
                    # Case-insensitive replacement
                    import re
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    highlighted_name = pattern.sub(
                        lambda m: f"{before}{m.group()}{after}",
                        highlighted_name
                    )
                result["name"] = highlighted_name

            if description:
                highlighted_desc = description
                for term in query_terms:
                    import re
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    highlighted_desc = pattern.sub(
                        lambda m: f"{before}{m.group()}{after}",
                        highlighted_desc
                    )
                result["description"] = highlighted_desc

            return result
        finally:
            conn.close()

    def get_facets(self, query: Optional[str] = None) -> SearchFacets:
        """
        Get facet counts for search results.

        Args:
            query: Optional search query to filter before counting

        Returns:
            SearchFacets with type and status counts
        """
        conn = self._get_connection()
        try:
            # Get type facets
            if query:
                type_rows = conn.execute(
                    """
                    SELECT e.type, COUNT(*) as count
                    FROM entities e
                    JOIN entities_fts fts ON e.rowid = fts.rowid
                    WHERE entities_fts MATCH ?
                    GROUP BY e.type
                    ORDER BY count DESC
                    """,
                    (query,),
                ).fetchall()
            else:
                type_rows = conn.execute(
                    """
                    SELECT type, COUNT(*) as count
                    FROM entities
                    GROUP BY type
                    ORDER BY count DESC
                    """
                ).fetchall()

            types = [FacetCount(value=row["type"], count=row["count"]) for row in type_rows]

            # Get status facets
            if query:
                status_rows = conn.execute(
                    """
                    SELECT e.status, COUNT(*) as count
                    FROM entities e
                    JOIN entities_fts fts ON e.rowid = fts.rowid
                    WHERE entities_fts MATCH ?
                    GROUP BY e.status
                    ORDER BY count DESC
                    """,
                    (query,),
                ).fetchall()
            else:
                status_rows = conn.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM entities
                    GROUP BY status
                    ORDER BY count DESC
                    """
                ).fetchall()

            statuses = [FacetCount(value=row["status"], count=row["count"]) for row in status_rows]

            return SearchFacets(types=types, statuses=statuses)
        finally:
            conn.close()

    def count(
        self,
        query: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        Count matching entities.

        Args:
            query: Optional search query
            entity_type: Filter by type
            status: Filter by status

        Returns:
            Count of matching entities
        """
        conn = self._get_connection()
        try:
            conditions = []
            params: List[Any] = []

            if query:
                conditions.append("entities_fts MATCH ?")
                params.append(query)

            if entity_type:
                conditions.append("e.type = ?")
                params.append(entity_type)

            if status:
                conditions.append("e.status = ?")
                params.append(status)

            if query:
                sql = """
                    SELECT COUNT(*) as count
                    FROM entities e
                    JOIN entities_fts fts ON e.rowid = fts.rowid
                """
            else:
                sql = "SELECT COUNT(*) as count FROM entities e"

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            row = conn.execute(sql, params).fetchone()
            return row["count"]
        finally:
            conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert database row to Entity."""
        from datetime import datetime
        return Entity(
            id=row["id"],
            type=row["type"],
            status=row["status"],
            data=json.loads(row["data"]),
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
