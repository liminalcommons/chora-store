# chora-store: Agent Awareness

**Package**: chora-store
**Type**: SQLite Entity Store + Physics Engine
**Purpose**: Persist and validate entities with Structural Governance

---

## What Is This?

This is the **Physics Engine** - the enforcement point for Structural Governance. Invalid entities cannot exist because this package won't create them.

## Key Classes

| Class | Purpose | Autopoietic Pillar |
|-------|---------|-------------------|
| `EntityFactory` | Create/validate entities | Structural Governance |
| `EntityRepository` | SQLite persistence | - |
| `EntityObserver` | Event emission | Stigmergic Coordination |
| `Entity` | Data model | - |

---

## Creating Entities (Use Factory, Not Repository)

**IMPORTANT**: Always use `EntityFactory` to create entities. Direct `EntityRepository` access bypasses validation.

```python
from chora_store import EntityFactory

# Create factory with kernel path
factory = EntityFactory(kernel_path="packages/chora-kernel")

# Create entity (validated)
entity = factory.create("feature", "Voice Canvas")

# Factory handles:
# 1. Type validation (must be in kernel)
# 2. Semantic ID generation
# 3. Status validation
# 4. Required field validation
# 5. Persistence
# 6. Event emission
```

## Validation Rules

The factory validates against `chora-kernel/standards/entity.yaml`:

| Validation | Description | Error |
|------------|-------------|-------|
| Type exists | Entity type must be in schema | `InvalidEntityType` |
| Status valid | Status must be valid for type | `ValidationError` |
| Required fields | All required fields present | `ValidationError` |
| ID unique | No duplicate IDs | `ValidationError` |
| Slug non-empty | Title must produce valid slug | `ValidationError` |

---

## Common Operations

### Create Entity
```python
entity = factory.create(
    "feature",              # Type
    "Voice Canvas",         # Title (becomes slug)
    status="planned",       # Optional (uses default)
    description="..."       # Additional data
)
```

### Update Entity
```python
factory.update(entity.id, status="in_progress")
factory.update(entity.id, description="Updated description")
```

### Get Entity
```python
entity = factory.get("feature-voice-canvas")
```

### List Entities
```python
# All entities
all_entities = factory.list()

# Filter by type
features = factory.list(entity_type="feature")

# Filter by status
active = factory.list(status="in_progress")
```

### Search
```python
results = factory.search("voice")
```

### Delete
```python
factory.delete("feature-voice-canvas")
```

---

## Observing Changes (Stigmergic Coordination)

Register callbacks to react to entity changes:

```python
from chora_store import get_observer, ChangeType

observer = get_observer()

def handle_change(event):
    if event.change_type == ChangeType.CREATED:
        print(f"New entity: {event.entity_id}")
    elif event.change_type == ChangeType.UPDATED:
        print(f"Updated: {event.entity_id}, {event.old_status} → {event.new_status}")

observer.on_change(handle_change)
```

---

## Database Location

Default: `~/.chora/chora.db`

Can be customized:
```python
from chora_store import EntityRepository, EntityFactory

repo = EntityRepository(db_path="/path/to/custom.db")
factory = EntityFactory(kernel_path="...", repository=repo)
```

---

## Error Handling

```python
from chora_store import ValidationError, InvalidEntityType

try:
    factory.create("invalid_type", "Test")
except InvalidEntityType as e:
    print(f"Unknown type: {e}")

try:
    factory.create("feature", "Test", status="invalid_status")
except ValidationError as e:
    print(f"Validation failed: {e}")
```

---

## The Physics Engine Principle

**Invalid states cannot exist.**

This is enforced at two levels:
1. **Factory validation** - Python code checks against kernel
2. **SQLite CHECK constraints** - Database rejects invalid data

If validation fails at either level, the entity is not created.

---

*The ground is solid. You can build here.*
