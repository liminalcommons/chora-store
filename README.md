# chora-store

**SQLite entity storage for Python with built-in validation, versioning, and sync.**

[![PyPI version](https://badge.fury.io/py/chora-store.svg)](https://badge.fury.io/py/chora-store)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Quick Start

```bash
pip install chora-store
```

```python
from chora_store import Entity, EntityRepository

# Initialize (creates ~/.chora/chora.db)
repo = EntityRepository()

# Create an entity
feature = Entity(
    id="feature-my-first-feature",
    type="feature",
    status="planned",
    data={"name": "My First Feature", "description": "Testing chora"}
)
repo.create(feature)

print(f"Created: {feature.id}")
```

**That's it.** You now have a SQLite database with your first entity.

---

## Features

- **Zero configuration** - Works out of the box with sensible defaults
- **Version tracking** - Every entity has a version number for optimistic concurrency
- **Full-text search** - Built-in FTS5 search across entity data
- **Status validation** - Schema constraints prevent invalid states
- **Event system** - React to entity changes with observers
- **Sync support** - Optional CRDT-style sync between databases

---

## Installation Options

```bash
# Core package (local storage only)
pip install chora-store

# With sync support (multi-database merge)
pip install chora-store[sync]

# With cloud sync (E2E encrypted)
pip install chora-store[cloud]

# All features
pip install chora-store[all]
```

---

## API Overview

### CRUD Operations

```python
from chora_store import Entity, EntityRepository

repo = EntityRepository()  # Default: ~/.chora/chora.db
repo = EntityRepository("./my-project.db")  # Custom path

# Create
entity = Entity(
    id="task-write-docs",
    type="task",
    status="planned",
    data={"name": "Write documentation"}
)
created = repo.create(entity)  # Returns entity with version=1

# Read
entity = repo.read("task-write-docs")  # Returns Entity or None

# Update (creates new version)
updated = entity.copy(status="in_progress")
saved = repo.update(updated)  # Returns entity with version=2

# Delete
repo.delete("task-write-docs")  # Returns True if existed
```

### Querying

```python
# List all entities
all_entities = repo.list()

# Filter by type
features = repo.list(entity_type="feature")

# Filter by status
active = repo.list(status="in_progress")

# Combine filters
planned_features = repo.list(entity_type="feature", status="planned")

# Pagination
page1 = repo.list(limit=10, offset=0)
page2 = repo.list(limit=10, offset=10)

# Full-text search
results = repo.search("documentation")
```

### Entity Model

```python
from chora_store import Entity

entity = Entity(
    id="feature-user-auth",      # Required: type-slug format
    type="feature",              # Required: entity type
    status="planned",            # Required: see valid statuses below
    data={"name": "User Auth"}   # Optional: your custom data
)

# Auto-populated fields
entity.version      # 0 (incremented on save)
entity.created_at   # datetime
entity.updated_at   # datetime

# Entities are immutable - use copy() to modify
updated = entity.copy(
    status="in_progress",
    data={**entity.data, "started": "2025-01-15"}
)
```

### Valid Statuses

```
planned, proposed, published, complete, completed, paused,
in_progress, draft, abandoned, propagated, open, mitigated,
blocked, adopted, active, deprecated, documented
```

### Semantic IDs

Entity IDs must start with their type:

```python
# Valid
Entity(id="feature-voice-input", type="feature", ...)
Entity(id="task-fix-login-bug", type="task", ...)
Entity(id="pattern-factory-linter", type="pattern", ...)

# Invalid (raises ValidationError)
Entity(id="my-feature", type="feature", ...)  # Missing type prefix
```

---

## Observer Pattern

React to entity changes:

```python
from chora_store import EntityObserver

observer = EntityObserver()

@observer.on_create
def handle_create(entity):
    print(f"Created: {entity.id}")

@observer.on_update
def handle_update(old, new):
    print(f"Updated: {new.id} (v{old.version} -> v{new.version})")

@observer.on_delete
def handle_delete(entity):
    print(f"Deleted: {entity.id}")

# Connect to repository
repo.add_observer(observer)
```

---

## Sync (Optional)

Sync between SQLite databases using CRDT-style merge:

```python
from chora_store import SyncableRepository

# Requires: pip install chora-store[sync]
repo = SyncableRepository(
    EntityRepository("./local.db"),
    site_id="my-laptop"
)

# Sync with another database
repo.sync_with(other_repo)
```

### Conflict Resolution

```python
from chora_store.conflict import LastWriteWinsResolver

repo = SyncableRepository(
    EntityRepository("./local.db"),
    site_id="my-laptop",
    conflict_resolver=LastWriteWinsResolver()
)
```

Available resolvers:
- `LastWriteWinsResolver` - Most recent timestamp wins
- `HigherVersionWinsResolver` - Higher version number wins
- `MergeFieldsResolver` - Merge non-conflicting fields
- `DeferResolver` - Queue for manual resolution
- `CallbackResolver` - Custom resolution logic

---

## Cloud Sync (Optional)

E2E encrypted sync via Cloudflare Workers:

```python
from chora_store import create_sync_client, SyncConfig

# Requires: pip install chora-store[cloud]
config = SyncConfig(
    server_url="https://chora-cloud.workers.dev",
    email="you@example.com",
    password="your-password"
)

client = create_sync_client(config)
client.sync(repo)  # Push/pull encrypted changes
```

---

## Advanced Search

```python
from chora_store import EntitySearch

search = EntitySearch(repo)

results = search.search(
    query="auth",
    filters={"type": "feature", "status": "in_progress"},
    facets=["type", "status"]
)

for entity in results.entities:
    print(entity.id)

for facet, counts in results.facets.items():
    print(f"{facet}: {counts}")
```

---

## Backups

```python
from chora_store import backup

# Create backup
backup_path = backup.create_backup(repo.db_path, "./backups")

# List backups
for b in backup.list_backups("./backups"):
    print(f"{b.timestamp}: {b.path}")

# Restore
backup.restore_backup(backup_path, "./restored.db")
```

---

## Testing

```bash
# Clone repo
git clone https://github.com/liminalcommons/chora-workspace
cd chora-workspace/packages/chora-store

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
```

---

## Documentation

- [Quickstart](https://github.com/liminalcommons/chora-workspace/blob/main/docs/quickstart.md)
- [Level 0: Solo Guide](https://github.com/liminalcommons/chora-workspace/blob/main/docs/guides/level-0-solo.md)
- [Level 1: Team Sync](https://github.com/liminalcommons/chora-workspace/blob/main/docs/guides/level-1-team.md)
- [Level 2: Cloud Sync](https://github.com/liminalcommons/chora-workspace/blob/main/docs/guides/level-2-cloud.md)

---

## Related Packages

- **chora-sync** - CRDT sync layer for chora-store
- **chora-crypto** - E2E encryption for cloud sync
- **chora-cloud** - Cloudflare Workers sync service

---

## License

MIT
