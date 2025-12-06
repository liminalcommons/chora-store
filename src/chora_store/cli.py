import sys
import json
from .mcp import manifest, bond, transmute, sense


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m chora_store.cli <tool> [args...]")
        print("\nTools:")
        print("  sense orient              - System vitality")
        print("  sense constellation <id>  - Local physics")
        print("  sense voids               - Generative gaps")
        print("  manifest <type> <title>   - Create entity")
        print("  bond <verb> <from> <to>   - Create relationship")
        print("  transmute <id> <op>       - Transform entity")
        sys.exit(1)

    tool = sys.argv[1]
    args = sys.argv[2:]

    # FastMCP 2.x wraps tools as FunctionTool objects; access underlying fn via .fn
    _manifest = manifest.fn if hasattr(manifest, 'fn') else manifest
    _bond = bond.fn if hasattr(bond, 'fn') else bond
    _transmute = transmute.fn if hasattr(transmute, 'fn') else transmute
    _sense = sense.fn if hasattr(sense, 'fn') else sense

    try:
        if tool == "sense":
            query = args[0] if len(args) > 0 else "orient"
            target = args[1] if len(args) > 1 else None
            print(_sense(query, target))

        elif tool == "manifest":
            if len(args) < 2:
                print("Error: manifest requires <type> <title>")
                sys.exit(1)
            type_ = args[0]
            title = args[1]
            data = args[2] if len(args) > 2 else "{}"
            print(_manifest(type_, title, data))

        elif tool == "bond":
            if len(args) < 3:
                print("Error: bond requires <verb> <from_id> <to_id>")
                sys.exit(1)
            print(_bond(args[0], args[1], args[2]))

        elif tool == "transmute":
            if len(args) < 2:
                print("Error: transmute requires <id> <operation>")
                sys.exit(1)
            params = args[2] if len(args) > 2 else "{}"
            print(_transmute(args[0], args[1], params))

        else:
            print(f"Unknown tool: {tool}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
