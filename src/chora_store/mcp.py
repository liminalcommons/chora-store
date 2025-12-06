import json
import traceback
import functools
from typing import Optional, Dict
from fastmcp import FastMCP

from .repository import Repository
from .dynamics.manifest import Manifest
from .dynamics.bond import Bond
from .dynamics.transmute import Transmute
from .dynamics.sense import Sense

# Initialize Physics Engine
repo = Repository()
manifest_op = Manifest(repo)
bond_op = Bond(repo)
transmute_op = Transmute(repo)
sense_op = Sense(repo)

mcp = FastMCP(
    "chora-store",
    description="The Tensegrity Physics Engine (v4.0). Use these 4 tools to govern the universe."
)


def trace(func):
    """Decorator to log tool usage to the trace history. The system remembers its actions."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        inputs = {'args': args, 'kwargs': kwargs}
        try:
            result = func(*args, **kwargs)
            repo.log_trace(func.__name__, inputs, result)
            return result
        except Exception as e:
            repo.log_trace(func.__name__, inputs, None, error=str(e))
            raise
    return wrapper


@mcp.tool()
@trace
def manifest(type: str, title: str, data: str = "{}") -> str:
    """
    Genesis: Create a new Entity (Matter) from Eidos.

    Args:
        type: One of [inquiry, story, tool, behavior, principle, learning, focus]
        title: Human-readable title (will become semantic ID)
        data: JSON string of additional fields (optional)
    """
    try:
        kwargs = json.loads(data)
        entity = manifest_op.run(type, title, **kwargs)
        return f"Manifested: {entity.id} ({entity.status})"
    except Exception as e:
        return f"Genesis Failed: {str(e)}"


@mcp.tool()
@trace
def bond(verb: str, from_id: str, to_id: str) -> str:
    """
    Tension: Create a Relationship (Force) between entities.

    Args:
        verb: One of [yields, surfaces, clarifies, specifies, implements, verifies, crystallized-from]
        from_id: Source Entity ID
        to_id: Target Entity ID
    """
    try:
        rel = bond_op.run(verb, from_id, to_id)
        return f"Bonded: {rel.id} ({rel.status})"
    except Exception as e:
        return f"Tension Failed: {str(e)}"


@mcp.tool()
@trace
def transmute(source_id: str, operation: str, params: str = "{}") -> str:
    """
    Metabolism: Transform an entity's phase state.

    Args:
        source_id: The entity to transform
        operation: [crystallize, extract, specialize, update_status]
        params: JSON string of operation parameters
    """
    try:
        kwargs = json.loads(params)
        result = transmute_op.run(source_id, operation, **kwargs)
        return f"Transmuted: {source_id} -> {result.id} via {operation}"
    except Exception as e:
        return f"Metabolism Failed: {str(e)}\n{traceback.format_exc()}"


@mcp.tool()
@trace
def sense(query: str, target: Optional[str] = None) -> str:
    """
    Observer: Read the state of the tension network.

    Args:
        query: "orient" (global health), "constellation" (local context), or "voids" (generative gaps)
        target: Entity ID (required for constellation)
    """
    try:
        if query == "orient":
            data = sense_op.orient()
            return _format_orient(data)
        elif query == "constellation":
            if not target:
                return "Error: Target ID required for constellation"
            data = sense_op.constellation(target)
            return _format_constellation(data)
        elif query == "voids":
            voids = sense_op.scan_voids()
            if not voids:
                return "✓ Generative Flow is complete. No voids detected."
            return "⚠️  GENERATIVE VOIDS DETECTED\n" + "\n".join(voids)
        else:
            return f"Unknown query: {query}"
    except Exception as e:
        return f"Observation Failed: {str(e)}"


# --- Formatting Helpers ---

def _format_orient(data: Dict) -> str:
    lines = [f"## System Vitality: {data['vitality'].upper()}"]
    lines.append(f"Integrity: {data['integrity']:.0%}")

    if data['drift_count'] > 0:
        lines.append(f"\n⚠️  GRAVITY WARNING: {data['drift_count']} entities drifting")
        for e in data['drifting_entities']:
            lines.append(f"   - {e}")
    else:
        lines.append("✓ Tensegrity: All bonds holding")

    if data['active_focus']:
        lines.append("\n## Plasma (Active Focus)")
        for f in data['active_focus']:
            lines.append(f"🔥 {f}")

    if data['open_inquiries']:
        lines.append("\n## Gas (Open Inquiries)")
        for i in data['open_inquiries']:
            lines.append(f"💭 {i}")

    # Cognitive Compass: Show tools with phenomenological awareness
    tools = repo.list(type="tool", status="active")
    cognitive_tools = [t for t in tools if t.data.get("cognition")]
    if cognitive_tools:
        lines.append("\n## Cognitive Compass (Ready-at-Hand)")
        for t in cognitive_tools:
            vignette = t.data["cognition"].get("ready_at_hand", "")
            if vignette:
                lines.append(f"🔧 {t.title}: {vignette}")

    lines.append("\n## Entity Counts")
    for t, count in data['entity_counts'].items():
        if count > 0:
            lines.append(f"  {t}: {count}")

    return "\n".join(lines)


def _format_constellation(data: Dict) -> str:
    e = data['entity']
    p = data['physics']

    lines = [f"## {e['id']} ({e['status']})"]
    lines.append(f"Physics: {p['stability'].upper()} (Integrity: {p['integrity']:.2f})")

    # Trajectory: Show the narrative arc for Focus entities
    if "trajectory" in data and data["trajectory"]:
        lines.append("\n## Trajectory (The Narrative Arc)")
        for i, prev in enumerate(data["trajectory"], 1):
            lines.append(f"  {i}. 🔙 {prev['title']} ({prev['status']})")

    lines.append("\n## Upstream Forces (Acting ON this)")
    if data['network']['upstream']:
        for b in data['network']['upstream']:
            icon = "⚡" if b['bond'] == 'verifies' else "↑"
            status = " (stressed)" if b['status'] != 'active' else ""
            lines.append(f"{icon} {b['bond']} < {b['target']} [{b['target_id']}]{status}")
    else:
        lines.append("  (none)")

    lines.append("\n## Downstream Forces (Emanating FROM this)")
    if data['network']['downstream']:
        for b in data['network']['downstream']:
            icon = "↓"
            lines.append(f"{icon} {b['bond']} > {b['target']} [{b['target_id']}]")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
