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


def get_sync_version() -> int:
    """Get the last synced version from local config."""
    config = load_config()
    return config.get("sync_version", 0)


def set_sync_version(version: int) -> None:
    """Save the last synced version."""
    config = load_config()
    config["sync_version"] = version
    save_config(config)


def is_configured() -> bool:
    """Check if cloud sync is configured."""
    config = load_config()
    return bool(config.get("server") and config.get("workspace_id") and config.get("token"))


def ensure_token() -> str:
    """Ensure we have a valid token, re-authenticating if needed."""
    config = load_config()
    token = config.get("token")

    if not token:
        # Try to re-auth with saved credentials
        email = config.get("email")
        password = config.get("password")
        server = config.get("server")

        if email and password and server:
            result = api_request(f"{server}/api/login", "POST", {
                "email": email,
                "password": password
            })
            token = result["data"]["token"]
            config["token"] = token
            save_config(config)

    return token


def push_entity(entity_dict: dict) -> bool:
    """
    Push a single entity to the cloud.

    Called automatically when entities are created/updated.
    Returns True if successful, False otherwise.
    """
    if not is_configured():
        return False

    config = load_config()
    server = config.get("server")
    workspace_id = config.get("workspace_id")

    try:
        token = ensure_token()
        if not token:
            return False

        # Push to sync endpoint
        api_request(
            f"{server}/sync/{workspace_id}/changes",
            "POST",
            [{
                "entityId": entity_dict["id"],
                "changeType": "upsert",
                "data": json.dumps(entity_dict),
                "timestamp": entity_dict.get("updated_at", entity_dict.get("created_at")),
            }],
            token
        )
        return True
    except Exception as e:
        # Silently fail - sync is best-effort
        # Could log to debug file if needed
        return False


def pull_entities() -> list:
    """
    Pull entities from the cloud.

    Called on orient/startup to get remote changes.
    Returns list of entity dicts, or empty list if not configured/error.
    """
    if not is_configured():
        return []

    config = load_config()
    server = config.get("server")
    workspace_id = config.get("workspace_id")
    since_version = get_sync_version()

    try:
        token = ensure_token()
        if not token:
            return []

        # Pull from sync endpoint
        result = api_request(
            f"{server}/sync/{workspace_id}/changes?since={since_version}",
            "GET",
            None,
            token
        )

        changes = result.get("data", {}).get("changes", [])
        new_version = result.get("data", {}).get("version", since_version)

        # Update sync version
        if new_version > since_version:
            set_sync_version(new_version)

        # Parse entity data
        entities = []
        for change in changes:
            try:
                data = change.get("data")
                if data:
                    entity_dict = json.loads(data) if isinstance(data, str) else data
                    entities.append(entity_dict)
            except (json.JSONDecodeError, TypeError):
                continue

        return entities
    except Exception:
        # Silently fail - sync is best-effort
        return []


def sync_all() -> dict:
    """
    Full bidirectional sync.

    Returns dict with push_count, pull_count, errors.
    """
    from .repository import EntityRepository

    if not is_configured():
        return {"error": "Not configured. Run: just cloud-invite or just cloud-join"}

    config = load_config()
    server = config.get("server")
    workspace_id = config.get("workspace_id")
    since_version = get_sync_version()

    result = {
        "pushed": 0,
        "pulled": 0,
        "errors": [],
    }

    try:
        token = ensure_token()
        if not token:
            result["errors"].append("Authentication failed")
            return result

        repo = EntityRepository()

        # Push local changes
        local_changes = repo.get_changes_since(since_version)
        for entity, change_type in local_changes:
            try:
                api_request(
                    f"{server}/sync/{workspace_id}/changes",
                    "POST",
                    [{
                        "entityId": entity.id,
                        "changeType": change_type,
                        "data": json.dumps(entity.to_dict()),
                        "timestamp": entity.updated_at.isoformat(),
                        "version": entity.version,
                    }],
                    token
                )
                result["pushed"] += 1
            except Exception as e:
                result["errors"].append(f"Push {entity.id}: {e}")

        # Pull remote changes
        try:
            pull_result = api_request(
                f"{server}/sync/{workspace_id}/changes?since={since_version}",
                "GET",
                None,
                token
            )

            changes = pull_result.get("data", {}).get("changes", [])
            new_version = pull_result.get("data", {}).get("version", since_version)

            for change in changes:
                try:
                    data = change.get("data")
                    if data:
                        entity_dict = json.loads(data) if isinstance(data, str) else data
                        # Merge into local (upsert)
                        from .models import Entity
                        entity = Entity.from_dict(entity_dict)
                        existing = repo.read(entity.id)
                        if existing:
                            # Only update if remote is newer
                            if entity.version > existing.version:
                                repo.update(entity)
                                result["pulled"] += 1
                        else:
                            repo.create(entity)
                            result["pulled"] += 1
                except Exception as e:
                    result["errors"].append(f"Pull merge: {e}")

            # Update sync version
            set_sync_version(new_version)

        except Exception as e:
            result["errors"].append(f"Pull: {e}")

    except Exception as e:
        result["errors"].append(str(e))

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m chora_store.cloud_cli invite  - Create and share workspace")
        print("  python -m chora_store.cloud_cli join <invite-link>")
        print("  python -m chora_store.cloud_cli status")
        print("  python -m chora_store.cloud_cli sync    - Full bidirectional sync")
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

    elif command == "sync":
        print("")
        print("  Syncing with cloud...")
        print("")
        result = sync_all()
        if result.get("error"):
            print(f"  Error: {result['error']}")
        else:
            print(f"  Pushed: {result['pushed']} entities")
            print(f"  Pulled: {result['pulled']} entities")
            if result['errors']:
                print(f"  Errors: {len(result['errors'])}")
                for err in result['errors'][:5]:  # Show first 5
                    print(f"    - {err}")
            else:
                print("  Sync complete!")
        print("")

    else:
        print(f"  Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
