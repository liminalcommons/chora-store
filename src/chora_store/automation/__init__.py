"""
Automation module for chora-store.

Provides file watchers and git hooks for local automation.
"""

from .triggers import TriggerRegistry, Action, Trigger
from .hooks import GitHooks, HookType, HookStatus
from .watcher import FileWatcher, ChoraWatcher, WatchConfig, FileChange, ChangeType, WatcherStatus, print_status

__all__ = [
    # Triggers
    "TriggerRegistry",
    "Action",
    "Trigger",
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
