"""
EntityFactory - THE PHYSICS ENGINE.

This is the enforcement point for Structural Governance.
Invalid states cannot exist because the factory won't create them.

The factory:
1. Loads the kernel schema (entity.yaml)
2. Loads experimental patterns (epigenetic mutations)
3. Validates all entity creation requests against effective schema
4. Generates semantic IDs
5. Applies templates
6. Persists via repository
7. Emits stigmergic signals via observer

EPIGENETIC BRIDGE:
The factory now supports "epigenetic" patterns - schema extensions that can be
tested on new entities without modifying the kernel permanently. Patterns with
subtype='schema-extension' and status='experimental' are merged into the
effective schema at runtime.
"""

import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Entity, ValidationError, InvalidEntityType
from .repository import EntityRepository
from .observer import EntityObserver, ChangeType, get_observer


class EntityFactory:
    """
    The Physics Engine: Creates valid entities or rejects invalid ones.

    This is the ONLY sanctioned way to create entities.
    Direct repository access bypasses validation.

    Usage:
        factory = EntityFactory(kernel_path="path/to/chora-kernel")
        entity = factory.create("feature", "Voice Canvas")
    """

    def __init__(
        self,
        kernel_path: str = "packages/chora-kernel",
        repository: Optional[EntityRepository] = None,
        observer: Optional[EntityObserver] = None,
    ):
        """
        Initialize factory with kernel path.

        Args:
            kernel_path: Path to chora-kernel directory
            repository: EntityRepository instance (creates default if None)
            observer: EntityObserver instance (uses global if None)
        """
        self.kernel_path = Path(kernel_path)
        self.schema = self._load_schema()
        self.repository = repository or EntityRepository()
        self.observer = observer or get_observer()

    def _load_schema(self) -> Dict[str, Any]:
        """Load entity schema from kernel."""
        schema_path = self.kernel_path / "standards" / "entity.yaml"
        if not schema_path.exists():
            raise ValidationError(f"Kernel schema not found: {schema_path}")

        with open(schema_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ═══════════════════════════════════════════════════════════════════════════
    # EPIGENETIC BRIDGE - Dynamic Schema Extension
    # ═══════════════════════════════════════════════════════════════════════════

    def _load_experimental_patterns(self, target_type: str) -> List[Entity]:
        """
        Load experimental schema-extension patterns for a given entity type.

        These patterns represent "epigenetic" mutations - proposed schema changes
        that are being tested on new entities without modifying the kernel.

        Args:
            target_type: The entity type to find patterns for

        Returns:
            List of Pattern entities with matching mechanics.target
        """
        patterns = []
        try:
            # Query for experimental schema-extension patterns
            all_patterns = self.repository.list(entity_type="pattern", limit=100)
            for p in all_patterns:
                # Check if it's a schema-extension pattern
                subtype = p.data.get("subtype")
                if subtype != "schema-extension":
                    continue
                # Check if it's experimental
                if p.status != "experimental":
                    continue
                # Check if it targets this entity type
                mechanics = p.data.get("mechanics", {})
                if mechanics.get("target") == target_type:
                    patterns.append(p)
        except Exception:
            # If repository isn't ready yet, return empty list
            pass
        return patterns

    def _get_effective_schema(self, entity_type: str) -> tuple:
        """
        Get the effective schema for an entity type, including epigenetic extensions.

        This merges inject_fields from experimental patterns into the base schema.

        Args:
            entity_type: Type of entity

        Returns:
            Tuple of (type_schema dict, list of applied pattern IDs)
        """
        # Start with base schema from kernel
        type_schema = dict(self.schema["types"][entity_type])

        # Track which patterns are applied
        applied_patterns = []

        # Load and merge experimental patterns
        patterns = self._load_experimental_patterns(entity_type)
        for pattern in patterns:
            mechanics = pattern.data.get("mechanics", {})
            inject_fields = mechanics.get("inject_fields", {})

            # Merge injected fields into additional_optional
            if inject_fields:
                current_optional = type_schema.get("additional_optional", [])
                if isinstance(current_optional, list):
                    # Add field names to optional list
                    for field_name in inject_fields.keys():
                        if field_name not in current_optional:
                            current_optional.append(field_name)
                    type_schema["additional_optional"] = current_optional

                # Store field definitions for validation
                if "_epigenetic_fields" not in type_schema:
                    type_schema["_epigenetic_fields"] = {}
                type_schema["_epigenetic_fields"].update(inject_fields)

                applied_patterns.append(pattern.id)

        return type_schema, applied_patterns

    def _apply_epigenetic_defaults(
        self, entity_type: str, data: Dict[str, Any], type_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply default values from epigenetic fields.

        Args:
            entity_type: Type of entity
            data: Current data dict
            type_schema: Effective schema with _epigenetic_fields

        Returns:
            Updated data dict with defaults applied
        """
        epigenetic_fields = type_schema.get("_epigenetic_fields", {})
        for field_name, field_def in epigenetic_fields.items():
            if field_name not in data:
                default = field_def.get("default")
                if default is not None:
                    data[field_name] = default
        return data

    def create(
        self,
        entity_type: str,
        title: str,
        status: Optional[str] = None,
        **kwargs,
    ) -> Entity:
        """
        Create a valid entity or raise ValidationError.

        This is THE way to create entities. Invalid states cannot exist.

        Args:
            entity_type: Type of entity (feature, pattern, etc.)
            title: Human-readable title
            status: Initial status (uses default if None)
            **kwargs: Additional data fields

        Returns:
            Created entity

        Raises:
            InvalidEntityType: If type not recognized
            ValidationError: If validation fails
        """
        # 1. Validate type exists
        if entity_type not in self.schema.get("types", {}):
            raise InvalidEntityType(
                f"Unknown entity type: '{entity_type}'. "
                f"Valid types: {list(self.schema.get('types', {}).keys())}"
            )

        # 2. Get effective schema (base + epigenetic extensions)
        type_schema, applied_patterns = self._get_effective_schema(entity_type)

        # 3. Generate semantic ID
        slug = self._slugify(title)
        entity_id = f"{entity_type}-{slug}"

        # 4. Validate ID doesn't already exist
        existing = self.repository.read(entity_id)
        if existing:
            raise ValidationError(f"Entity '{entity_id}' already exists")

        # 5. Determine status
        valid_statuses = type_schema.get("statuses", [])
        if status is None:
            status = valid_statuses[0] if valid_statuses else "active"
        elif status not in valid_statuses:
            raise ValidationError(
                f"Invalid status '{status}' for {entity_type}. "
                f"Valid statuses: {valid_statuses}"
            )

        # 6. Build data dict
        now = datetime.utcnow()
        data = {
            "name": title,
            "description": kwargs.pop("description", ""),
            "created": now.isoformat(),
            "updated": now.isoformat(),
            **kwargs,
        }

        # 7. Apply epigenetic defaults (from experimental patterns)
        data = self._apply_epigenetic_defaults(entity_type, data, type_schema)

        # 8. Tag entity with applied epigenetic patterns (for tracking)
        if applied_patterns:
            data["_epigenetics"] = applied_patterns

        # 9. Validate required fields
        required = type_schema.get("additional_required", [])
        for field in required:
            if field not in data or not data[field]:
                raise ValidationError(
                    f"Missing required field '{field}' for {entity_type}"
                )

        # 10. Create entity (valid by construction)
        entity = Entity(
            id=entity_id,
            type=entity_type,
            status=status,
            data=data,
            created_at=now,
            updated_at=now,
        )

        # 11. Persist via repository
        entity = self.repository.create(entity)

        # 12. Emit stigmergic signal
        self.observer.emit(ChangeType.CREATED, entity)

        # 13. Cloud sync (best-effort, silent failure)
        self._sync_push(entity)

        return entity

    def update(
        self,
        entity_id: str,
        status: Optional[str] = None,
        **data_updates,
    ) -> Entity:
        """
        Update an existing entity.

        Args:
            entity_id: ID of entity to update
            status: New status (optional)
            **data_updates: Fields to update in data

        Returns:
            Updated entity

        Raises:
            ValidationError: If entity not found or validation fails
        """
        # 1. Read existing entity
        entity = self.repository.read(entity_id)
        if entity is None:
            raise ValidationError(f"Entity '{entity_id}' not found")

        old_status = entity.status
        type_schema = self.schema["types"][entity.type]

        # 2. Validate new status if provided
        if status is not None:
            valid_statuses = type_schema.get("statuses", [])
            if status not in valid_statuses:
                raise ValidationError(
                    f"Invalid status '{status}' for {entity.type}. "
                    f"Valid statuses: {valid_statuses}"
                )
            # 2b. Validate transition is allowed
            if status != old_status:
                self._validate_transition(entity.type, old_status, status)
            entity = entity.copy(status=status)

        # 3. Update data fields
        if data_updates:
            new_data = dict(entity.data)
            new_data.update(data_updates)
            new_data["updated"] = datetime.utcnow().isoformat()
            entity = entity.copy(data=new_data)

        # 4. Persist
        entity = self.repository.update(entity)

        # 5. Emit stigmergic signal
        self.observer.emit(ChangeType.UPDATED, entity, old_status=old_status)

        # 6. Cloud sync (best-effort, silent failure)
        self._sync_push(entity)

        return entity

    def delete(self, entity_id: str) -> bool:
        """
        Delete an entity.

        Args:
            entity_id: ID of entity to delete

        Returns:
            True if deleted, False if not found
        """
        # 1. Read existing entity (for event)
        entity = self.repository.read(entity_id)
        if entity is None:
            return False

        # 2. Delete from repository
        result = self.repository.delete(entity_id)

        # 3. Emit stigmergic signal
        if result:
            self.observer.emit(ChangeType.DELETED, entity)

        return result

    def get(self, entity_id: str) -> Optional[Entity]:
        """
        Get an entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Entity if found, None otherwise
        """
        return self.repository.read(entity_id)

    def list(
        self,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """
        List entities with optional filters.

        Args:
            entity_type: Filter by type
            status: Filter by status
            limit: Maximum results

        Returns:
            List of entities
        """
        return self.repository.list(entity_type=entity_type, status=status, limit=limit)

    def search(self, query: str, limit: int = 20) -> list:
        """
        Search entities by text.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching entities
        """
        return self.repository.search(query, limit=limit)

    def _slugify(self, title: str) -> str:
        """
        Convert title to URL-safe slug.

        Args:
            title: Human-readable title

        Returns:
            Slug string (lowercase, hyphenated)

        Raises:
            ValidationError: If title produces empty slug
        """
        # Lowercase
        slug = title.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove special characters (keep alphanumeric and hyphens)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Collapse multiple hyphens
        slug = re.sub(r"-+", "-", slug)
        # Strip leading/trailing hyphens
        slug = slug.strip("-")
        # Truncate
        slug = slug[:50]

        if not slug:
            raise ValidationError(
                f"Title '{title}' produces empty slug. "
                "Title must contain alphanumeric characters."
            )

        return slug

    def _validate_transition(
        self, entity_type: str, from_status: str, to_status: str
    ) -> None:
        """
        Validate that a status transition is allowed.

        The kernel defines invalid transitions. Anything not explicitly
        invalid is permitted. This is the physics enforcement point.

        Args:
            entity_type: Type of entity
            from_status: Current status
            to_status: Desired new status

        Raises:
            ValidationError: If transition is invalid
        """
        transitions = self.schema.get("transitions", {})
        type_transitions = transitions.get(entity_type, {})
        invalid_edges = type_transitions.get("invalid", [])

        for edge in invalid_edges:
            edge_from = edge.get("from")
            edge_to = edge.get("to")

            # Check if this transition matches an invalid edge
            if edge_from == from_status:
                # Wildcard: from this status, cannot go anywhere
                if edge_to == "*":
                    raise ValidationError(
                        f"Invalid transition: {entity_type} cannot leave "
                        f"'{from_status}' state. {edge.get('reason', '')}"
                    )
                # Specific: from this status, cannot go to that status
                if edge_to == to_status:
                    raise ValidationError(
                        f"Invalid transition: {entity_type} cannot go from "
                        f"'{from_status}' to '{to_status}'. {edge.get('reason', '')}"
                    )

    def get_valid_types(self) -> list:
        """Get list of valid entity types."""
        return list(self.schema.get("types", {}).keys())

    def get_valid_statuses(self, entity_type: str) -> list:
        """Get valid statuses for an entity type."""
        if entity_type not in self.schema.get("types", {}):
            raise InvalidEntityType(f"Unknown entity type: {entity_type}")
        return self.schema["types"][entity_type].get("statuses", [])

    def _sync_push(self, entity: Entity) -> None:
        """
        Push entity to cloud (best-effort, silent failure).

        This is stigmergic - we leave a mark in the cloud for other agents.
        """
        try:
            from .cloud_cli import push_entity, is_configured
            if is_configured():
                push_entity(entity.to_dict())
        except Exception:
            # Silent failure - sync is best-effort
            pass
