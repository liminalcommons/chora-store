"""
File system watcher for chora workspaces.

Watches for file changes and triggers automation actions.
Uses watchdog library for cross-platform file monitoring.
"""

import os
import sys
import time
import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from datetime import datetime


class ChangeType(Enum):
    """Types of file system changes."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileChange:
    """A file system change event."""
    path: Path
    change_type: ChangeType
    timestamp: datetime
    old_path: Optional[Path] = None  # For moves


@dataclass
class WatchConfig:
    """Configuration for a watch pattern."""
    patterns: List[str]  # Glob patterns to watch (e.g., "*.yaml", ".chora/**/*")
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "*.pyc", "__pycache__", ".git", "*.swp", "*.swo", "*~"
    ])
    recursive: bool = True
    debounce_ms: int = 500  # Debounce rapid changes


@dataclass
class WatcherStatus:
    """Status of the file watcher."""
    running: bool
    watch_paths: List[Path]
    patterns: List[str]
    events_processed: int
    last_event: Optional[datetime]
    start_time: Optional[datetime]


class FileWatcher:
    """
    Watches file system for changes and triggers callbacks.

    Uses a simple polling approach that works without watchdog.
    For production use, install watchdog for efficient native events.
    """

    def __init__(
        self,
        watch_paths: List[str],
        config: Optional[WatchConfig] = None,
    ):
        """
        Initialize file watcher.

        Args:
            watch_paths: Directories to watch
            config: Watch configuration
        """
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.config = config or WatchConfig(patterns=["*"])
        self.callbacks: List[Callable[[FileChange], None]] = []
        self._running = False
        self._events_processed = 0
        self._last_event: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
        self._file_mtimes: Dict[Path, float] = {}
        self._known_files: Set[Path] = set()

    def add_callback(self, callback: Callable[[FileChange], None]) -> None:
        """Add a callback to be invoked on file changes."""
        self.callbacks.append(callback)

    def _matches_pattern(self, path: Path) -> bool:
        """Check if path matches any watch pattern."""
        path_str = str(path)

        # Check ignore patterns first
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_str, pattern):
                return False

        # Check watch patterns
        for pattern in self.config.patterns:
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_str, pattern):
                return True

        return False

    def _scan_files(self, base_path: Path) -> Dict[Path, float]:
        """Scan directory for files and their modification times."""
        files = {}

        try:
            if self.config.recursive:
                for root, dirs, filenames in os.walk(base_path):
                    # Filter out ignored directories
                    dirs[:] = [d for d in dirs if not any(
                        fnmatch.fnmatch(d, p) for p in self.config.ignore_patterns
                    )]

                    for filename in filenames:
                        path = Path(root) / filename
                        if self._matches_pattern(path):
                            try:
                                files[path] = path.stat().st_mtime
                            except (OSError, IOError):
                                pass
            else:
                for item in base_path.iterdir():
                    if item.is_file() and self._matches_pattern(item):
                        try:
                            files[item] = item.stat().st_mtime
                        except (OSError, IOError):
                            pass
        except (OSError, IOError):
            pass

        return files

    def _check_for_changes(self) -> List[FileChange]:
        """Check for file system changes since last scan."""
        changes = []
        current_files: Dict[Path, float] = {}

        for watch_path in self.watch_paths:
            current_files.update(self._scan_files(watch_path))

        current_paths = set(current_files.keys())
        known_paths = set(self._file_mtimes.keys())

        # Created files
        for path in current_paths - known_paths:
            changes.append(FileChange(
                path=path,
                change_type=ChangeType.CREATED,
                timestamp=datetime.now(),
            ))

        # Deleted files
        for path in known_paths - current_paths:
            changes.append(FileChange(
                path=path,
                change_type=ChangeType.DELETED,
                timestamp=datetime.now(),
            ))

        # Modified files
        for path in current_paths & known_paths:
            if current_files[path] != self._file_mtimes.get(path):
                changes.append(FileChange(
                    path=path,
                    change_type=ChangeType.MODIFIED,
                    timestamp=datetime.now(),
                ))

        self._file_mtimes = current_files
        return changes

    def _notify(self, change: FileChange) -> None:
        """Notify all callbacks of a change."""
        self._events_processed += 1
        self._last_event = change.timestamp

        for callback in self.callbacks:
            try:
                callback(change)
            except Exception as e:
                print(f"[watcher] Callback error: {e}", file=sys.stderr)

    def start(self, poll_interval: float = 1.0) -> None:
        """
        Start watching for file changes (blocking).

        Args:
            poll_interval: Seconds between file system scans
        """
        self._running = True
        self._start_time = datetime.now()

        # Initial scan
        for watch_path in self.watch_paths:
            self._file_mtimes.update(self._scan_files(watch_path))

        print(f"[watcher] Watching {len(self.watch_paths)} paths...")
        print(f"[watcher] Patterns: {self.config.patterns}")

        try:
            while self._running:
                changes = self._check_for_changes()

                for change in changes:
                    self._notify(change)

                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[watcher] Stopped")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the watcher."""
        self._running = False

    def get_status(self) -> WatcherStatus:
        """Get current watcher status."""
        return WatcherStatus(
            running=self._running,
            watch_paths=self.watch_paths,
            patterns=self.config.patterns,
            events_processed=self._events_processed,
            last_event=self._last_event,
            start_time=self._start_time,
        )


class ChoraWatcher:
    """
    Pre-configured watcher for chora workspaces.

    Watches .chora/ directory and triggers appropriate actions.
    """

    # Default patterns for chora files
    CHORA_PATTERNS = [
        "*.yaml",
        "*.yml",
        "*.md",
    ]

    # Directories to watch
    CHORA_DIRS = [
        ".chora",
        "docs/plans",
        "docs/research",
    ]

    def __init__(self, workspace_path: str = "."):
        """
        Initialize chora watcher.

        Args:
            workspace_path: Path to workspace root
        """
        self.workspace = Path(workspace_path).resolve()

        # Build watch paths that exist
        watch_paths = []
        for dir_name in self.CHORA_DIRS:
            dir_path = self.workspace / dir_name
            if dir_path.exists():
                watch_paths.append(str(dir_path))

        # Fall back to workspace if no dirs exist
        if not watch_paths:
            watch_paths = [str(self.workspace)]

        config = WatchConfig(
            patterns=self.CHORA_PATTERNS,
            ignore_patterns=[
                "*.pyc", "__pycache__", ".git", "*.swp", "*.swo", "*~",
                "node_modules", ".next", "*.lock"
            ],
            recursive=True,
        )

        self.watcher = FileWatcher(watch_paths, config)
        self.watcher.add_callback(self._on_change)

    def _on_change(self, change: FileChange) -> None:
        """Handle a file change event."""
        rel_path = change.path.relative_to(self.workspace) if change.path.is_relative_to(self.workspace) else change.path

        icon = {
            ChangeType.CREATED: "✨",
            ChangeType.MODIFIED: "📝",
            ChangeType.DELETED: "🗑️",
            ChangeType.MOVED: "📦",
        }.get(change.change_type, "•")

        print(f"[chora] {icon} {change.change_type.value}: {rel_path}")

        # Trigger specific actions based on path
        self._trigger_actions(change)

    def _trigger_actions(self, change: FileChange) -> None:
        """Trigger actions based on the changed file."""
        path_str = str(change.path)

        # Pattern capabilities - auto-regenerate awareness docs
        if "patterns/" in path_str and change.change_type != ChangeType.DELETED:
            print("[chora] 💡 Pattern changed - consider running: just awareness-update")

        # Capabilities - auto-regenerate capabilities doc
        if "capabilities/" in path_str and change.change_type != ChangeType.DELETED:
            print("[chora] 💡 Capability changed - consider running: just capabilities-update")

        # Features - validate manifest
        if "features/" in path_str and path_str.endswith(".yaml"):
            print("[chora] 💡 Feature changed - consider running: just manifest-validate")

        # Living context updated
        if "living_context.md" in path_str:
            print("[chora] 📋 Living context updated")

    def start(self, poll_interval: float = 1.0) -> None:
        """Start watching (blocking)."""
        print(f"[chora] Starting workspace watcher: {self.workspace}")
        self.watcher.start(poll_interval)

    def stop(self) -> None:
        """Stop watching."""
        self.watcher.stop()

    def get_status(self) -> WatcherStatus:
        """Get watcher status."""
        return self.watcher.get_status()


def print_status(watcher: ChoraWatcher) -> None:
    """Print watcher status."""
    status = watcher.get_status()

    print("=== Chora Watcher Status ===")
    print(f"  Running: {'✅ yes' if status.running else '❌ no'}")
    print(f"  Watch paths: {len(status.watch_paths)}")
    for path in status.watch_paths:
        print(f"    - {path}")
    print(f"  Patterns: {', '.join(status.patterns)}")
    print(f"  Events processed: {status.events_processed}")
    if status.last_event:
        print(f"  Last event: {status.last_event.isoformat()}")
    if status.start_time:
        print(f"  Started: {status.start_time.isoformat()}")
