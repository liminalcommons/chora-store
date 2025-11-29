"""
Cloud CLI - Simple invite/join commands for cloud sync.

Usage:
    cloud-setup: Configure your account (choose username/password)
    cloud-invite: Create workspace and generate invite link
    cloud-join <invite>: Join a workspace from invite link
"""

import os
import sys
import json
import base64
import secrets
import getpass
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


DEFAULT_SERVER = "https://chora-cloud.accounts-82f.workers.dev"


# Config file location
CONFIG_DIR = Path.home() / ".chora"
CONFIG_FILE = CONFIG_DIR / "cloud.json"


def load_config() -> dict:
    """Load cloud config from ~/.chora/cloud.json"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    """Save cloud config to ~/.chora/cloud.json"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def api_request(url: str, method: str = "GET", data: dict = None, token: str = None) -> dict:
    """Make API request to cloud server."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "chora-sync/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode('utf-8') if data else None
    request = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_data = json.loads(error_body)
            raise Exception(error_data.get("error", {}).get("message", error_body))
        except json.JSONDecodeError:
            raise Exception(error_body)
    except URLError as e:
        raise Exception(f"Connection failed: {e.reason}")


def create_invite() -> str:
    """Create a workspace and generate an invite link."""
    config = load_config()

    # Check for existing server config
    server = config.get("server")
    if not server:
        # Default to the deployed instance
        server = os.environ.get("CHORA_CLOUD_URL", DEFAULT_SERVER)

    print(f"  Using server: {server}")

    # Check health
    try:
        health = api_request(f"{server}/health")
        if health.get("status") != "ok":
            raise Exception("Server not healthy")
    except Exception as e:
        print(f"  Error: Cannot reach server - {e}")
        sys.exit(1)

    # Get or create account
    email = config.get("email")
    token = config.get("token")

    if not email or not token:
        # Generate anonymous account
        email = f"user-{secrets.token_hex(4)}@chora.local"
        password = secrets.token_urlsafe(16)

        print(f"  Creating account: {email}")

        try:
            api_request(f"{server}/api/accounts", "POST", {
                "email": email,
                "password": password
            })
        except Exception as e:
            # Account might exist, try login
            pass

        # Login
        result = api_request(f"{server}/api/login", "POST", {
            "email": email,
            "password": password
        })
        token = result["data"]["token"]

        # Save credentials
        config["server"] = server
        config["email"] = email
        config["password"] = password  # Saved locally for re-auth
        config["token"] = token
        save_config(config)
        print("  Account created and saved")

    # Create workspace
    print("  Creating workspace...")
    result = api_request(f"{server}/api/workspaces", "POST", {
        "name": "chora-shared"
    }, token)
    workspace_id = result["data"]["id"]
    print(f"  Workspace: {workspace_id}")

    # Generate encryption key
    key = secrets.token_bytes(32)
    key_b64 = base64.b64encode(key).decode('ascii')

    # Save workspace config locally
    config["workspace_id"] = workspace_id
    config["workspace_key"] = key_b64
    save_config(config)

    # Create invite blob
    invite_data = {
        "s": server,
        "w": workspace_id,
        "k": key_b64
    }
    invite_json = json.dumps(invite_data, separators=(',', ':'))
    invite_b64 = base64.urlsafe_b64encode(invite_json.encode()).decode('ascii')

    return f"chora://{invite_b64}"


def join_workspace(invite: str) -> None:
    """Join a workspace from an invite link."""
    # Parse invite
    if invite.startswith("chora://"):
        invite = invite[8:]

    try:
        invite_json = base64.urlsafe_b64decode(invite).decode('utf-8')
        invite_data = json.loads(invite_json)
    except Exception:
        print("  Error: Invalid invite link")
        sys.exit(1)

    server = invite_data.get("s")
    workspace_id = invite_data.get("w")
    key_b64 = invite_data.get("k")

    if not all([server, workspace_id, key_b64]):
        print("  Error: Incomplete invite link")
        sys.exit(1)

    print(f"  Server: {server}")
    print(f"  Workspace: {workspace_id}")

    # Check health
    try:
        health = api_request(f"{server}/health")
        if health.get("status") != "ok":
            raise Exception("Server not healthy")
    except Exception as e:
        print(f"  Error: Cannot reach server - {e}")
        sys.exit(1)

    # Load or create config
    config = load_config()

    # Get or create account on this server
    email = config.get("email")
    token = config.get("token")
    existing_server = config.get("server")

    if not email or not token or existing_server != server:
        # Generate anonymous account
        email = f"user-{secrets.token_hex(4)}@chora.local"
        password = secrets.token_urlsafe(16)

        print(f"  Creating account: {email}")

        try:
            api_request(f"{server}/api/accounts", "POST", {
                "email": email,
                "password": password
            })
        except Exception:
            pass

        # Login
        result = api_request(f"{server}/api/login", "POST", {
            "email": email,
            "password": password
        })
        token = result["data"]["token"]

    # Save config
    config["server"] = server
    config["email"] = email
    config["token"] = token
    config["workspace_id"] = workspace_id
    config["workspace_key"] = key_b64
    if 'password' not in config:
        config["password"] = password
    save_config(config)

    print("  Joined workspace successfully!")
    print(f"  Config saved to: {CONFIG_FILE}")


def show_status() -> None:
    """Show current cloud sync status."""
    config = load_config()

    if not config:
        print("  Not configured. Run: just cloud-invite")
        return

    print(f"  Server: {config.get('server', 'not set')}")
    print(f"  Account: {config.get('email', 'not set')}")
    print(f"  Workspace: {config.get('workspace_id', 'not set')}")
    print(f"  Key: {'set' if config.get('workspace_key') else 'not set'}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m chora_store.cloud_cli invite  - Create and share workspace")
        print("  python -m chora_store.cloud_cli join <invite-link>")
        print("  python -m chora_store.cloud_cli status")
        sys.exit(1)

    command = sys.argv[1]

    if command == "invite":
        print("")
        print("  Creating workspace invite...")
        print("")
        invite = create_invite()
        print("")
        print("  ╭──────────────────────────────────────────────────────────╮")
        print("  │  INVITE LINK                                             │")
        print("  ╰──────────────────────────────────────────────────────────╯")
        print("")
        print(f"  {invite}")
        print("")
        print("  Send this to your collaborator via Signal or similar.")
        print("  They run: just cloud-join <link>")
        print("")

    elif command == "join":
        if len(sys.argv) < 3:
            print("  Usage: just cloud-join <invite-link>")
            sys.exit(1)

        print("")
        print("  Joining workspace...")
        print("")
        join_workspace(sys.argv[2])
        print("")
        print("  You're connected! Run: just sync")
        print("")

    elif command == "status":
        print("")
        print("  Cloud Sync Status:")
        print("")
        show_status()
        print("")

    else:
        print(f"  Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
