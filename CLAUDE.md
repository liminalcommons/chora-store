# chora-store

**The Engine**

This package implements the tensegrity physics defined in `chora-kernel`.

---

## Architecture

```
src/chora_store/
├── models.py       # Entity dataclass
├── repository.py   # SQLite persistence
├── physics.py      # Tensegrity computation
├── dynamics/       # The 4 Canonical Operators
│   ├── manifest.py    # MANIFEST: Create Matter
│   ├── bond.py        # BOND: Create Force
│   ├── transmute.py   # TRANSMUTE: Change State
│   └── sense.py       # SENSE: Read Network
├── cli.py          # Command-line interface
└── mcp.py          # MCP tool handlers
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

3. **Bond types enforce physics**
   - `yields`: inquiry → learning
   - `surfaces`: learning → principle
   - `clarifies`: principle → story
   - `specifies`: story → behavior
   - `implements`: behavior → tool
   - `verifies`: tool → behavior (critical tension)
   - `crystallized-from`: any → any (provenance)

---

## Database

**Location:** `~/.chora/chora.db`

Single `entities` table with virtual columns for graph traversal:

```sql
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Virtual columns for graph queries
    rel_from TEXT GENERATED ALWAYS AS (json_extract(data, '$.from_id')) VIRTUAL,
    rel_to TEXT GENERATED ALWAYS AS (json_extract(data, '$.to_id')) VIRTUAL,
    rel_type TEXT GENERATED ALWAYS AS (json_extract(data, '$.relationship_type')) VIRTUAL
)
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

*The engine runs the physics. You are the force.*
