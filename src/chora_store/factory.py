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
from .agent import get_current_agent
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
        kernel_path: Optional[str] = None,
        repository: Optional[EntityRepository] = None,
        observer: Optional[EntityObserver] = None,
    ):
        """
        Initialize factory with kernel path.

        Args:
            kernel_path: Path to chora-kernel directory (auto-detected if None)
            repository: EntityRepository instance (creates default if None)
            observer: EntityObserver instance (uses global if None)
        """
        self.kernel_path = Path(kernel_path) if kernel_path else self._find_kernel_path()
        self.schema = self._load_schema()
        self.repository = repository or EntityRepository()
        self.observer = observer or get_observer()

        # Bootstrap epigenetic patterns from kernel YAML into SQLite
        # This ensures patterns like tiered-resolution are available for field injection
        self._bootstrap_epigenetic_patterns()

    def _bootstrap_epigenetic_patterns(self) -> None:
        """Bootstrap patterns from kernel YAML if not already in SQLite."""
        try:
            self.bootstrap_patterns_from_kernel("epigenetic")
        except Exception:
            # Silent failure - patterns may not be needed for all operations
            pass

    def _find_kernel_path(self) -> Path:
        """
        Find the chora-kernel directory by searching common locations.

        Returns:
            Path to kernel directory

        Raises:
            ValidationError: If kernel cannot be found
        """
        import os

        # Candidate paths to search (in order of preference)
        candidates = [
            "packages/chora-kernel",           # From workspace root
            "../chora-kernel",                 # From packages/chora-store
            "../../packages/chora-kernel",     # From packages/chora-store/src
            "../../../packages/chora-kernel",  # From deeper nesting
        ]

        # Also try relative to this file's location
        this_file = Path(__file__).resolve()
        file_based = this_file.parent.parent.parent.parent / "chora-kernel"

        for candidate in candidates:
            path = Path(candidate)
            if (path / "standards" / "entity.yaml").exists():
                return path

        # Try file-based path
        if (file_based / "standards" / "entity.yaml").exists():
            return file_based

        # Try environment variable
        env_path = os.environ.get("CHORA_KERNEL_PATH")
        if env_path:
            path = Path(env_path)
            if (path / "standards" / "entity.yaml").exists():
                return path

        # Default fallback (will likely fail in _load_schema)
        return Path("packages/chora-kernel")

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

    def _apply_focus_defaults(
        self, data: Dict[str, Any], now: datetime
    ) -> Dict[str, Any]:
        """
        Apply focus-specific validation and defaults.

        Focus entities require:
        - target: The entity being focused on (must be valid entity ID format)
        - agent: The agent holding focus

        Focus entities receive defaults:
        - ttl_minutes: Time before focus becomes unlocked (default: 240)
        - trail: List of entities touched during focus (default: [])
        - started_at: When focus began (default: now)
        - entry_type: How focus was created (default: 'declared')

        Args:
            data: Current data dict
            now: Current timestamp

        Returns:
            Updated data dict with focus defaults

        Raises:
            ValidationError: If required focus fields missing or invalid
        """
        # Validate required focus fields
        if "target" not in data or not data["target"]:
            raise ValidationError(
                "Focus requires 'target' field: the entity being focused on"
            )

        if "agent" not in data or not data["agent"]:
            raise ValidationError(
                "Focus requires 'agent' field: the agent holding focus"
            )

        # Validate target follows entity ID format (type-slug)
        target = data["target"]
        if not re.match(r"^[a-z]+-[a-z0-9-]+$", target):
            raise ValidationError(
                f"Focus target must be valid entity ID format (type-slug), got: '{target}'"
            )

        # Apply defaults
        if "ttl_minutes" not in data:
            data["ttl_minutes"] = 240  # 4 hours default

        if "trail" not in data:
            data["trail"] = []

        if "started_at" not in data:
            data["started_at"] = now.isoformat()

        if "entry_type" not in data:
            data["entry_type"] = "declared"

        if "last_cycled" not in data:
            data["last_cycled"] = now.isoformat()

        return data

    def bootstrap_patterns_from_kernel(self, pattern_dir: Optional[str] = None) -> int:
        """
        Load experimental patterns from kernel YAML files into repository.

        This is the pattern bootstrap mechanism that closes the gap between
        patterns defined in kernel YAML and patterns available in SQLite.

        Unlike normal entity creation, bootstrap preserves the exact ID from
        the YAML file rather than generating one from the name.

        Args:
            pattern_dir: Optional subdirectory within kernel patterns/
                        (default: 'epigenetic')

        Returns:
            Number of patterns loaded
        """
        subdir = pattern_dir or "epigenetic"
        patterns_path = self.kernel_path / "patterns" / subdir

        if not patterns_path.exists():
            return 0

        loaded = 0
        for yaml_file in patterns_path.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    pattern_data = yaml.safe_load(f)

                pattern_id = pattern_data.get("id")
                if not pattern_id:
                    continue

                # Skip if already exists in repository
                existing = self.repository.read(pattern_id)
                if existing:
                    continue

                # Extract standard pattern fields
                name = pattern_data.get("name", pattern_id)
                status = pattern_data.get("status", "experimental")
                subtype = pattern_data.get("subtype", "behavioral")

                # Validate status is valid for patterns
                type_schema = self.schema["types"]["pattern"]
                valid_statuses = type_schema.get("statuses", [])
                if status not in valid_statuses:
                    status = valid_statuses[0] if valid_statuses else "proposed"

                # Build data dict, converting dates to strings
                now = datetime.utcnow()
                data = {
                    "name": name,
                    "subtype": subtype,
                    "description": pattern_data.get("description", ""),
                    "created": now.isoformat(),
                    "updated": now.isoformat(),
                    "created_by": "kernel-bootstrap",
                    "last_changed_by": "kernel-bootstrap",
                }

                # Add all other fields from YAML (convert dates)
                skip_fields = {"id", "type", "status", "name", "subtype", "description"}
                for k, v in pattern_data.items():
                    if k not in skip_fields:
                        if hasattr(v, 'isoformat'):
                            data[k] = v.isoformat()
                        else:
                            data[k] = v

                # Create entity with exact ID from YAML (bypass factory ID generation)
                entity = Entity(
                    id=pattern_id,
                    type="pattern",
                    status=status,
                    data=data,
                    created_at=now,
                    updated_at=now,
                )

                # Persist directly to repository
                entity = self.repository.create(entity)

                # Emit signal
                self.observer.emit(ChangeType.CREATED, entity)

                loaded += 1

            except Exception as e:
                # Log error but continue with other patterns
                import sys
                print(f"Warning: Failed to load {yaml_file}: {e}", file=sys.stderr)
                continue

        return loaded

    def create(
        self,
        entity_type: str,
        title: str,
        status: Optional[str] = None,
        namespace: Optional[str] = None,
        **kwargs,
    ) -> Entity:
        """
        Create a valid entity or raise ValidationError.

        This is THE way to create entities. Invalid states cannot exist.

        Args:
            entity_type: Type of entity (feature, pattern, etc.)
            title: Human-readable title
            status: Initial status (uses default if None)
            namespace: For tools, the semantic namespace (core, learning, etc.)
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
        # Avoid doubled prefix (e.g., "pattern-pattern-foo" when title is "pattern-foo")
        if slug.startswith(f"{entity_type}-"):
            slug = slug[len(f"{entity_type}-"):]

        # For tools, include namespace in ID: tool-{namespace}-{action}
        if entity_type == 'tool' and namespace:
            # Avoid doubled namespace (e.g., "core-core-orient")
            if slug.startswith(f"{namespace}-"):
                slug = slug[len(f"{namespace}-"):]
            entity_id = f"tool-{namespace}-{slug}"
        else:
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
        agent = get_current_agent()
        data = {
            "name": title,
            "description": kwargs.pop("description", ""),
            "created": now.isoformat(),
            "updated": now.isoformat(),
            "created_by": agent,
            "last_changed_by": agent,
            **kwargs,
        }

        # 7. Apply epigenetic defaults (from experimental patterns)
        data = self._apply_epigenetic_defaults(entity_type, data, type_schema)

        # 7.5. Focus-specific validation and defaults
        if entity_type == "focus":
            data = self._apply_focus_defaults(data, now)

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

        # 11.5. Register tool entities as MCP functions (hot reload)
        if entity_type == 'tool':
            try:
                from .mcp import register_single_tool
                register_single_tool(entity_id, data.get('description', ''))
            except Exception:
                pass  # Silent failure - MCP registration is best-effort

        # 12. Emit stigmergic signal
        self.observer.emit(ChangeType.CREATED, entity)

        # 13. Fire event-driven epigenetic hooks (best-effort)
        try:
            self.observer.run_epigenetic_hooks(
                self.repository,
                f"entity:{entity_type}:created",
                entity
            )
        except Exception:
            pass  # Silent failure - event hooks are best-effort

        # 14. Cloud sync (best-effort, silent failure)
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
                # 2c. Validate transition preconditions (e.g., behaviors for stable)
                self._validate_transition_requires(entity, old_status, status)
                # 2d. Apply focus-specific status transition side effects
                if entity.type == "focus" and status == "finalized":
                    data_updates["finalized_at"] = datetime.utcnow().isoformat()
                elif entity.type == "focus" and status == "unlocked":
                    data_updates["unlocked_at"] = datetime.utcnow().isoformat()
            entity = entity.copy(status=status)

        # 3. Update data fields
        if data_updates:
            new_data = dict(entity.data)
            new_data.update(data_updates)
            new_data["updated"] = datetime.utcnow().isoformat()
            new_data["last_changed_by"] = get_current_agent()
            entity = entity.copy(data=new_data)
        else:
            # Even if no data updates, record the agent for status-only changes
            new_data = dict(entity.data)
            new_data["updated"] = datetime.utcnow().isoformat()
            new_data["last_changed_by"] = get_current_agent()
            entity = entity.copy(data=new_data)

        # 4. Persist
        entity = self.repository.update(entity)

        # 5. Emit stigmergic signal
        self.observer.emit(ChangeType.UPDATED, entity, old_status=old_status)

        # 6. Fire event-driven epigenetic hooks (best-effort)
        try:
            self.observer.run_epigenetic_hooks(
                self.repository,
                f"entity:{entity.type}:updated",
                entity
            )
        except Exception:
            pass  # Silent failure - event hooks are best-effort

        # 6b. Fire status_changed hooks if status transitioned
        if old_status != entity.status:
            try:
                self.observer.run_epigenetic_hooks(
                    self.repository,
                    f"entity:{entity.type}:status_changed",
                    entity,
                    old_status=old_status
                )
            except Exception:
                pass  # Silent failure - event hooks are best-effort

        # 7. Cloud sync (best-effort, silent failure)
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

    def expose(
        self,
        subject: str,
        name: str,
        interfaces: List[str] = None,
        handler_type: str = "reference",
        description: str = "",
        namespace: Optional[str] = None,
        **kwargs,
    ) -> Entity:
        """
        Expose a capability as a Tool entity.

        This is the Expose verb from the kernel - it creates an interface boundary
        that makes internal capabilities accessible externally.

        Physics: subject → Expose(protocol) → Tool (endpoint)

        Args:
            subject: What to expose (pattern ID, function reference, or prompt template)
            name: Human-readable name for the tool
            interfaces: List of protocols to expose via (default: ['mcp', 'cli'])
            handler_type: Type of handler ('reference', 'compose', 'llm', 'generative')
            description: Description of what the tool does
            namespace: Semantic namespace for tool ID (core, learning, pattern, etc.)
            **kwargs: Additional handler configuration

        Returns:
            Created Tool entity

        Raises:
            ValidationError: If exposure fails

        Example:
            # Expose a Python function with namespace
            factory.expose(
                subject="tool_orient",
                name="Orient",
                interfaces=['mcp', 'cli'],
                handler_type='reference',
                description="System greeting",
                namespace='core'  # Creates tool-core-orient
            )

            # Expose an LLM capability
            factory.expose(
                subject="Given {{ input }}, analyze...",
                name="Analyzer",
                interfaces=['mcp'],
                handler_type='llm',
                description="Analyzes input",
                namespace='meta'  # Creates tool-meta-analyzer
            )
        """
        if interfaces is None:
            interfaces = ['mcp', 'cli']

        # Build handler based on type
        handler = {'type': handler_type}

        if handler_type == 'reference':
            handler['function'] = subject
        elif handler_type == 'compose':
            handler['template'] = subject
        elif handler_type == 'llm':
            handler['prompt_template'] = subject
            if 'system_prompt' in kwargs:
                handler['system_prompt'] = kwargs.pop('system_prompt')
        elif handler_type == 'generative':
            handler['output_type'] = kwargs.pop('output_type', 'entity')
            handler['prompt_template'] = subject

        # Create the Tool entity with namespace
        tool = self.create(
            'tool',
            name,
            description=description,
            handler=handler,
            interfaces=interfaces,
            namespace=namespace,
            **kwargs
        )

        return tool

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

    def _validate_transition_requires(
        self, entity: "Entity", from_status: str, to_status: str
    ) -> None:
        """
        Validate transition preconditions from the 'requires' section.

        The kernel defines preconditions for certain transitions (e.g., behaviors
        required for feature converging → stable). This enforces those.

        Args:
            entity: The entity being transitioned
            from_status: Current status
            to_status: Desired new status

        Raises:
            ValidationError: If preconditions not met
        """
        transitions = self.schema.get("transitions", {})
        type_transitions = transitions.get(entity.type, {})
        requires = type_transitions.get("requires", [])

        for req in requires:
            req_from = req.get("from")
            req_to = req.get("to")

            # Check if this transition matches a requires rule
            if req_from == from_status and req_to == to_status:
                # Feature converging → stable: behaviors required
                if entity.type == "feature" and to_status == "stable":
                    behaviors = entity.data.get("behaviors", [])

                    if not behaviors:
                        raise ValidationError(
                            f"Cannot transition to stable: no behaviors defined. "
                            f"{req.get('reason', 'Stability claims require verified behaviors.')}"
                        )

                    # Check all behaviors are passing
                    failing = [
                        b.get("id", "unnamed")
                        for b in behaviors
                        if b.get("status") != "passing"
                    ]
                    if failing:
                        raise ValidationError(
                            f"Cannot transition to stable: behaviors not passing: {failing}. "
                            f"{req.get('reason', 'All behaviors must be passing.')}"
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
