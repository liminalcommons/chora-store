"""
Agent identity for presence sensing.

This module provides agent identification for change attribution.
It's kept minimal to avoid circular dependencies.
"""

import os
import socket
import getpass


def get_current_agent() -> str:
    """
    Get the current agent identifier for change attribution.

    Priority:
    1. CHORA_AGENT environment variable (explicit identity)
    2. user@host (default identity)

    This enables presence sensing - knowing who made changes.
    """
    agent = os.environ.get('CHORA_AGENT')
    if agent:
        return agent
    # Default: user@host for unique identification
    try:
        user = getpass.getuser()
        host = socket.gethostname().split('.')[0]  # Short hostname
        return f"{user}@{host}"
    except Exception:
        return "unknown"
