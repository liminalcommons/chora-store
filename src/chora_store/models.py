"""
Entity model - the core data structure.

An Entity is the fundamental unit of the chora workspace.
Every feature, pattern, task, etc. is an Entity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import json


class ValidationError(Exception):
    """Raised when entity validation fails."""
    pass


class InvalidEntityType(ValidationError):
    """Raised when entity type is not recognized."""
    pass


@dataclass
class Entity:
    """
    The universal entity model.

    Every entity in the workspace has:
    - id: Semantic ID (e.g., "feature-voice-canvas")
    - type: Entity type (e.g., "feature", "pattern")
    - status: Lifecycle status (varies by type)
    - data: Type-specific data as dict
    - version: Optimistic concurrency version
    - created_at: Creation timestamp
    - updated_at: Last update timestamp
    """
    id: str
    type: str
    status: str
    data: dict = field(default_factory=dict)
    version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate basic invariants."""
        if not self.id:
            raise ValidationError("Entity ID is required")
        if not self.type:
            raise ValidationError("Entity type is required")
        if not self.status:
            raise ValidationError("Entity status is required")
        # ID must start with type
        if not self.id.startswith(f"{self.type}-"):
            raise ValidationError(
                f"Entity ID '{self.id}' must start with type '{self.type}-'"
            )

    @property
    def name(self) -> str:
        """Human-readable name from data."""
        return self.data.get("name", self.id)

    @property
    def description(self) -> Optional[str]:
        """Description from data."""
        return self.data.get("description")

    def copy(self, **changes) -> "Entity":
        """Create a copy with optional field changes."""
        return Entity(
            id=changes.get("id", self.id),
            type=changes.get("type", self.type),
            status=changes.get("status", self.status),
            data=changes.get("data", dict(self.data)),
            version=changes.get("version", self.version),
            created_at=changes.get("created_at", self.created_at),
            updated_at=changes.get("updated_at", datetime.utcnow()),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "data": self.data,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        """Create from dictionary."""
        return cls(
            id=d["id"],
            type=d["type"],
            status=d["status"],
            data=d.get("data", {}),
            version=d.get("version", 1),
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.utcnow(),
            updated_at=datetime.fromisoformat(d["updated_at"]) if "updated_at" in d else datetime.utcnow(),
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Entity":
        """Create from JSON string."""
        return cls.from_dict(json.loads(s))
