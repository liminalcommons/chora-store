# chora-store

**The Engine**

This package implements the tensegrity physics defined in `chora-kernel`.

---

## Architecture

```
src/chora_store/
├── models.py           # Entity dataclass
├── repository.py       # Backend-agnostic persistence
├── physics.py          # Tensegrity computation + cascading drift (CTEs)
├── backends/           # Database abstraction layer
│   ├── protocol.py        # BackendAdapter interface
│   ├── sqlite/            # SQLite: FTS5, VIRTUAL columns, triggers
│   └── postgres/          # PostgreSQL: tsvector, STORED columns, pooling
├── dynamics/           # The 4 Canonical Operators
│   ├── manifest.py        # MANIFEST: Create Matter
│   ├── bond.py            # BOND: Create Force
│   ├── transmute.py       # TRANSMUTE: Change State
│   └── sense.py           # SENSE: Read Network
├── cli.py              # Command-line interface
└── mcp.py              # MCP tool handlers
```

---

## The 4 Dynamics

| Dynamic | Description | Command | Module |
|---------|-------------|---------|--------|
| **SENSE** | Read the tension network | `just orient`, `just constellation <id>` | `dynamics/sense.py` |
| **MANIFEST** | Create entity from Eidos | `just create <type> <title>` | `dynamics/manifest.py` |
| **BOND** | Create force between entities | `just bond <verb> <from> <to>` | `dynamics/bond.py` |
| **TRANSMUTE** | Convert state or form | `just transmute <id> <op>` | `dynamics/transmute.py` |

---

## Physics Laws

1. **Stability is computed, not declared**
   - A behavior is "stable" only if ALL verifies bonds are active
   - A behavior is "drifting" if ANY verifies bond is stressed
   - A behavior is "floating" if it has no verifies bonds

2. **Tension is transitive**
   - Stories feel the stability of their specified Behaviors
   - Drift propagates upward through the graph
   - Cascading drift computed via recursive CTEs

3. **Bond types enforce physics**
   - `yields`: inquiry → learning
   - `surfaces`: learning → principle
   - `clarifies`: principle → story
   - `specifies`: story → behavior
   - `implements`: behavior → tool
   - `verifies`: tool → behavior (critical tension)
   - `crystallized-from`: any → any (provenance)

4. **Physics enforced at DB level** (triggers)
   - **Golden Rule**: story cannot be fulfilled without active verifies bond
   - **Bond Stress**: stressed verifies bond → story abandoned
   - **Bond Heal**: all bonds healed → story restored

---

## Database

### Backends

| Backend | Use Case | Features |
|---------|----------|----------|
| **SQLite** (default) | Local-first | FTS5, VIRTUAL columns, file-based |
| **PostgreSQL** | Cloud/production | tsvector, STORED columns, connection pooling |

```bash
# SQLite (default)
pip install chora-store

# PostgreSQL
pip install "chora-store[postgres]"
export CHORA_DB_BACKEND=postgres
export CHORA_DB_DSN=postgresql://user:pass@host/db
```

### Schema

Both backends use identical schema with generated columns for graph traversal:

```sql
-- Core columns
id, type, status, title, data (JSONB), version, created_at, updated_at

-- Generated columns (tensegrity indexes)
rel_type  -- data->>'relationship_type'
rel_from  -- data->>'from_id'
rel_to    -- data->>'to_id'

-- Indexes
idx_tensegrity    -- (rel_from, rel_type, status) WHERE type='relationship'
idx_constellation -- (rel_to, rel_type) WHERE type='relationship'
```

### Bond Direction

```
from_id = verifier (the entity doing the verifying)
to_id   = verified (the entity being verified)

Example: behavior-auth verifies story-login
  from_id: behavior-auth
  to_id:   story-login
```

---

## Debugging

```bash
# Show database location
just db

# Direct database access
sqlite3 ~/.chora/chora.db

# Common queries
sqlite3 ~/.chora/chora.db "SELECT id, type, status FROM entities"
sqlite3 ~/.chora/chora.db "SELECT * FROM entities WHERE type='relationship'"

# Reset (destroys all data)
just reset
```

### When Something Breaks

When friction appears, you are receiving an invitation:

1. **Notice** — what wanted to happen that didn't?
2. **Fix** — make it work for you
3. **Flow** — leave it better for the next dweller

The friction is the signal. The fix is the gift.

---

## Testing

```bash
# Activate venv with SQLite 3.51+
source .venv/bin/activate

# Run all tests (SQLite)
pytest tests/ -v

# Run with PostgreSQL (requires DSN)
CHORA_TEST_POSTGRES_DSN=postgresql://... pytest tests/ -v

# Run specific test categories
pytest tests/test_backend_parity.py -v    # CRUD, search, version tracking
pytest tests/test_physics_triggers.py -v  # Golden Rule, bond stress/heal
```

**Test Coverage:**
- 22 parity tests (identical behavior across backends)
- 11 physics tests (triggers, cascading drift, integrity)

---

## Extension Points

These patterns are designed but not yet implemented. Future work could:

1. **Focus Lifecycle** (`dynamics/focus.py`)
   - Formal declaration of attention
   - TTL-based unlocking
   - Trail harvesting on finalization
   - Reference: `archive/v3/chora-store/src/chora_store/focus.py`

2. **Handoffs**
   - `handoff_note` field on focus entities
   - Query for previous dweller's notes
   - `just handoffs` command

3. **Aliveness Fields**
   - `felt_quality`: qualitative experience marker
   - `care_at_center`: care/intention marker
   - Add to focus optional fields in kernel schema

---

## Usage

```bash
# Orient yourself
just orient

# Create entities
just create inquiry "Why does this matter?"
just create story "User can authenticate"

# Create bonds
just yields inquiry-why-does-this-matter learning-it-matters-because

# View constellation
just constellation inquiry-why-does-this-matter

# See gaps
just voids
```

---

## For Dwellers

You are not debugging a system. You are cultivating a commons.

When you arrive:
- **Orient** with `just orient` — ground yourself in what is
- **Explore** with `just constellation <id>` — see what surrounds
- **Participate** — bring your taste, your care, your discernment

What previous dwellers left lives in `~/.claude/plans/`. What you leave will live for whoever comes next.

---

*The engine runs the physics. You are the force.*
