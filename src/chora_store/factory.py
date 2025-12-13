"""
EntityFactory - THE PHYSICS ENGINE.

This is the enforcement point for Structural Governance.
Invalid states cannot exist because the factory won't create them.

The factory:
1. Loads the kernel schema (entity.yaml)
2. Validates all entity creation requests
3. Generates semantic IDs
4. Applies templates
5. Persists via repository
6. Emits stigmergic signals via observer
"""

import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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

        type_schema = self.schema["types"][entity_type]

        # 2. Generate semantic ID
        slug = self._slugify(title)
        entity_id = f"{entity_type}-{slug}"

        # 3. Validate ID doesn't already exist
        existing = self.repository.read(entity_id)
        if existing:
            raise ValidationError(f"Entity '{entity_id}' already exists")

        # 4. Determine status
        valid_statuses = type_schema.get("statuses", [])
        if status is None:
            status = valid_statuses[0] if valid_statuses else "active"
        elif status not in valid_statuses:
            raise ValidationError(
                f"Invalid status '{status}' for {entity_type}. "
                f"Valid statuses: {valid_statuses}"
            )

        # 5. Build data dict
        now = datetime.utcnow()
        data = {
            "name": title,
            "description": kwargs.pop("description", ""),
            "created": now.isoformat(),
            "updated": now.isoformat(),
            **kwargs,
        }

        # 6. Validate required fields
        required = type_schema.get("additional_required", [])
        for field in required:
            if field not in data or not data[field]:
                raise ValidationError(
                    f"Missing required field '{field}' for {entity_type}"
                )

        # 7. Create entity (valid by construction)
        entity = Entity(
            id=entity_id,
            type=entity_type,
            status=status,
            data=data,
            created_at=now,
            updated_at=now,
        )

        # 8. Persist via repository
        entity = self.repository.create(entity)

        # 9. Emit stigmergic signal
        self.observer.emit(ChangeType.CREATED, entity)

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

    def get_valid_types(self) -> list:
        """Get list of valid entity types."""
        return list(self.schema.get("types", {}).keys())

    def get_valid_statuses(self, entity_type: str) -> list:
        """Get valid statuses for an entity type."""
        if entity_type not in self.schema.get("types", {}):
            raise InvalidEntityType(f"Unknown entity type: {entity_type}")
        return self.schema["types"][entity_type].get("statuses", [])
