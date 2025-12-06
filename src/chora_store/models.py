from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
import json


@dataclass
class Entity:
    """
    The Canonical Noun.
    Matter suspended in a web of Force.
    """
    id: str
    type: str  # One of the 8 Nouns
    status: str
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        # Enforce Semantic ID: type-slug
        if not self.id.startswith(f"{self.type}-"):
            raise ValueError(f"Entity ID '{self.id}' must start with type '{self.type}-'")

    @property
    def slug(self) -> str:
        return self.id.split("-", 1)[1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "title": self.title,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Entity":
        return cls(
            id=d["id"],
            type=d["type"],
            status=d["status"],
            title=d["title"],
            data=d.get("data", {}),
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            updated_at=datetime.fromisoformat(d["updated_at"]) if isinstance(d["updated_at"], str) else d["updated_at"],
        )
