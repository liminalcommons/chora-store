"""
Automation module for chora-store.

Provides file watchers, git hooks, and cron triggers for local automation.
"""

from .triggers import (
    TriggerRegistry, Action, Trigger, EventType,
    get_registry, fire_daily_cron, fire_session_start,
)
from .hooks import GitHooks, HookType, HookStatus
from .watcher import FileWatcher, ChoraWatcher, WatchConfig, FileChange, ChangeType, WatcherStatus, print_status

__all__ = [
    # Triggers
    "TriggerRegistry",
    "Action",
    "Trigger",
    "EventType",
    "get_registry",
    "fire_daily_cron",
    "fire_session_start",
    # Git hooks
    "GitHooks",
    "HookType",
    "HookStatus",
    # File watcher
    "FileWatcher",
    "ChoraWatcher",
    "WatchConfig",
    "FileChange",
    "ChangeType",
    "WatcherStatus",
    "print_status",
]
