"""
Backup utilities for chora-store.

Provides helpers for Litestream backup/restore operations.
"""

import os
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from string import Template


@dataclass
class BackupStatus:
    """Status of backup configuration and replication."""
    configured: bool
    running: bool
    config_path: Optional[Path]
    db_path: Path
    replica_type: Optional[str]
    last_sync: Optional[str]
    error: Optional[str] = None


@dataclass
class Snapshot:
    """A backup snapshot."""
    id: str
    timestamp: str
    size_bytes: int
    replica: str


def get_default_db_path() -> Path:
    """Get the default database path."""
    return Path.home() / ".chora" / "chora.db"


def get_default_config_path() -> Path:
    """Get the default litestream config path."""
    return Path.home() / ".chora" / "litestream.yml"


def get_template_path() -> Path:
    """Get the path to the litestream template."""
    return Path(__file__).parent.parent.parent / "litestream" / "litestream.yml.template"


def get_local_config_path() -> Path:
    """Get the path to the local dev config."""
    return Path(__file__).parent.parent.parent / "litestream" / "litestream-local.yml"


def is_litestream_installed() -> bool:
    """Check if litestream is installed."""
    return shutil.which("litestream") is not None


def setup_config(
    env_file: Optional[Path] = None,
    output_path: Optional[Path] = None,
    local: bool = False
) -> Path:
    """
    Generate litestream.yml from template using environment variables.

    Args:
        env_file: Path to .env file (optional, uses environment if not provided)
        output_path: Where to write config (default: ~/.chora/litestream.yml)
        local: Use local filesystem config instead of R2

    Returns:
        Path to generated config file
    """
    output_path = output_path or get_default_config_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if local:
        # Copy local config directly
        local_config = get_local_config_path()
        if not local_config.exists():
            raise FileNotFoundError(f"Local config not found: {local_config}")
        shutil.copy(local_config, output_path)
        return output_path

    # Load env file if provided
    env = dict(os.environ)
    if env_file and env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip().strip('"').strip("'")

    # Validate required variables
    required = ["R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]
    missing = [var for var in required if not env.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    # Read template and substitute
    template_path = get_template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path, encoding="utf-8") as f:
        template_content = f.read()

    # Use shell-style variable expansion
    # Handle ${VAR:-default} syntax manually
    import re

    def replace_var(match):
        var_expr = match.group(1)
        if ":-" in var_expr:
            var_name, default = var_expr.split(":-", 1)
            return env.get(var_name, default)
        return env.get(var_expr, match.group(0))

    config = re.sub(r'\$\{([^}]+)\}', replace_var, template_content)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(config)

    return output_path


def get_status(config_path: Optional[Path] = None) -> BackupStatus:
    """
    Get the current backup status.

    Args:
        config_path: Path to litestream config (default: ~/.chora/litestream.yml)

    Returns:
        BackupStatus with current state
    """
    config_path = config_path or get_default_config_path()
    db_path = get_default_db_path()

    if not config_path.exists():
        return BackupStatus(
            configured=False,
            running=False,
            config_path=None,
            db_path=db_path,
            replica_type=None,
            last_sync=None,
            error="Config not found. Run 'just backup-setup' first."
        )

    # Parse config to get replica type (before checking litestream installation)
    replica_type = None
    try:
        with open(config_path, encoding="utf-8") as f:
            content = f.read()
            if "type: s3" in content:
                replica_type = "s3 (Cloudflare R2)"
            elif "type: file" in content:
                replica_type = "file (local)"
    except Exception:
        pass

    if not is_litestream_installed():
        return BackupStatus(
            configured=True,
            running=False,
            config_path=config_path,
            db_path=db_path,
            replica_type=replica_type,
            last_sync=None,
            error="Litestream not installed. Run 'brew install litestream'."
        )

    # Check if litestream is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "litestream replicate"],
            capture_output=True,
            text=True
        )
        running = result.returncode == 0
    except Exception:
        running = False

    return BackupStatus(
        configured=True,
        running=running,
        config_path=config_path,
        db_path=db_path,
        replica_type=replica_type,
        last_sync=None
    )


def start(config_path: Optional[Path] = None, background: bool = False) -> subprocess.Popen:
    """
    Start litestream replication.

    Args:
        config_path: Path to litestream config
        background: Run in background

    Returns:
        Popen process handle
    """
    config_path = config_path or get_default_config_path()

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}. Run 'just backup-setup' first.")

    if not is_litestream_installed():
        raise RuntimeError("Litestream not installed. Run 'brew install litestream'.")

    cmd = ["litestream", "replicate", "-config", str(config_path)]

    if background:
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    else:
        return subprocess.Popen(cmd)


def stop() -> bool:
    """
    Stop any running litestream processes.

    Returns:
        True if a process was stopped
    """
    try:
        result = subprocess.run(
            ["pkill", "-f", "litestream replicate"],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


def restore(
    config_path: Optional[Path] = None,
    output_path: Optional[Path] = None
) -> Path:
    """
    Restore database from backup.

    Args:
        config_path: Path to litestream config
        output_path: Where to restore (default: original db path)

    Returns:
        Path to restored database
    """
    config_path = config_path or get_default_config_path()
    output_path = output_path or get_default_db_path()

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    if not is_litestream_installed():
        raise RuntimeError("Litestream not installed")

    # Backup existing db if it exists
    if output_path.exists():
        backup_path = output_path.with_suffix(".db.bak")
        shutil.copy(output_path, backup_path)

    result = subprocess.run(
        ["litestream", "restore", "-config", str(config_path), "-o", str(output_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Restore failed: {result.stderr}")

    return output_path


def list_snapshots(config_path: Optional[Path] = None) -> List[Snapshot]:
    """
    List available backup snapshots.

    Args:
        config_path: Path to litestream config

    Returns:
        List of available snapshots
    """
    config_path = config_path or get_default_config_path()

    if not config_path.exists():
        return []

    if not is_litestream_installed():
        return []

    result = subprocess.run(
        ["litestream", "snapshots", "-config", str(config_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return []

    # Parse output (format varies by litestream version)
    snapshots = []
    for line in result.stdout.strip().split("\n"):
        if line and not line.startswith("replica"):
            parts = line.split()
            if len(parts) >= 3:
                snapshots.append(Snapshot(
                    id=parts[0],
                    timestamp=parts[1] if len(parts) > 1 else "",
                    size_bytes=int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
                    replica=parts[3] if len(parts) > 3 else "default"
                ))

    return snapshots
