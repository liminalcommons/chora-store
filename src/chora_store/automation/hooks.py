"""
Git hook management for chora workspaces.

Installs and manages git hooks for automation.
"""

import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional


class HookType(Enum):
    """Types of git hooks."""
    PRE_COMMIT = "pre-commit"
    POST_COMMIT = "post-commit"
    PRE_PUSH = "pre-push"
    COMMIT_MSG = "commit-msg"


# Hook script templates
HOOK_TEMPLATES = {
    HookType.PRE_COMMIT: '''#!/usr/bin/env bash
# chora pre-commit hook
# Runs validation before allowing commit

set -e

echo "[chora] Running pre-commit checks..."

# Run lint
if command -v just &> /dev/null; then
    just lint 2>/dev/null || {
        echo "[chora] ❌ Lint failed. Fix errors before committing."
        exit 1
    }
fi

echo "[chora] ✅ Pre-commit checks passed"
''',

    HookType.POST_COMMIT: '''#!/usr/bin/env bash
# chora post-commit hook
# Runs after successful commit

echo "[chora] Post-commit hook triggered"

# Optional: Notify backup system
# just backup-status 2>/dev/null || true
''',

    HookType.PRE_PUSH: '''#!/usr/bin/env bash
# chora pre-push hook
# Runs validation before pushing

set -e

echo "[chora] Running pre-push checks..."

# Run tests
if command -v just &> /dev/null; then
    just test 2>/dev/null || {
        echo "[chora] ❌ Tests failed. Fix errors before pushing."
        exit 1
    }
fi

echo "[chora] ✅ Pre-push checks passed"
''',

    HookType.COMMIT_MSG: '''#!/usr/bin/env bash
# chora commit-msg hook
# Validates commit message format

COMMIT_MSG_FILE=$1
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Check for conventional commit format (optional)
# Allowed prefixes: feat, fix, docs, style, refactor, test, chore
if ! echo "$COMMIT_MSG" | grep -qE "^(feat|fix|docs|style|refactor|test|chore)(\(.+\))?: .+"; then
    # Only warn, don't block
    echo "[chora] ⚠️  Consider using conventional commit format:"
    echo "         feat|fix|docs|style|refactor|test|chore(scope): description"
fi
''',
}


@dataclass
class HookStatus:
    """Status of a git hook."""
    hook_type: HookType
    installed: bool
    is_chora_hook: bool
    path: Optional[Path]


class GitHooks:
    """
    Manages git hooks for a repository.
    """

    def __init__(self, repo_path: str = "."):
        """
        Initialize git hooks manager.

        Args:
            repo_path: Path to git repository root
        """
        self.repo_path = Path(repo_path).resolve()
        self.hooks_dir = self.repo_path / ".git" / "hooks"

    def _ensure_git_repo(self) -> bool:
        """Check if we're in a git repository."""
        return (self.repo_path / ".git").is_dir()

    def _get_hook_path(self, hook_type: HookType) -> Path:
        """Get path to a hook script."""
        return self.hooks_dir / hook_type.value

    def install(self, hook_type: HookType, force: bool = False) -> bool:
        """
        Install a git hook.

        Args:
            hook_type: Type of hook to install
            force: Overwrite existing hook if present

        Returns:
            True if installed successfully
        """
        if not self._ensure_git_repo():
            print(f"Not a git repository: {self.repo_path}")
            return False

        hook_path = self._get_hook_path(hook_type)

        # Check for existing hook
        if hook_path.exists() and not force:
            # Check if it's already a chora hook
            content = hook_path.read_text()
            if "chora" in content:
                print(f"Hook {hook_type.value} is already installed")
                return True
            else:
                print(f"Existing {hook_type.value} hook found. Use force=True to overwrite.")
                return False

        # Write hook script
        template = HOOK_TEMPLATES.get(hook_type)
        if not template:
            print(f"No template for hook type: {hook_type}")
            return False

        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(template)

        # Make executable
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        print(f"Installed {hook_type.value} hook")
        return True

    def uninstall(self, hook_type: HookType) -> bool:
        """
        Uninstall a git hook.

        Args:
            hook_type: Type of hook to uninstall

        Returns:
            True if uninstalled successfully
        """
        hook_path = self._get_hook_path(hook_type)

        if not hook_path.exists():
            print(f"Hook {hook_type.value} not installed")
            return True

        # Only remove if it's a chora hook
        content = hook_path.read_text()
        if "chora" not in content:
            print(f"Hook {hook_type.value} is not a chora hook, not removing")
            return False

        hook_path.unlink()
        print(f"Uninstalled {hook_type.value} hook")
        return True

    def install_all(self, force: bool = False) -> int:
        """
        Install all default hooks.

        Args:
            force: Overwrite existing hooks

        Returns:
            Number of hooks installed
        """
        installed = 0
        for hook_type in [HookType.PRE_COMMIT, HookType.POST_COMMIT]:
            if self.install(hook_type, force=force):
                installed += 1
        return installed

    def uninstall_all(self) -> int:
        """
        Uninstall all chora hooks.

        Returns:
            Number of hooks uninstalled
        """
        uninstalled = 0
        for hook_type in HookType:
            if self.uninstall(hook_type):
                uninstalled += 1
        return uninstalled

    def get_status(self, hook_type: HookType) -> HookStatus:
        """
        Get status of a hook.

        Args:
            hook_type: Type of hook to check

        Returns:
            HookStatus with installation info
        """
        hook_path = self._get_hook_path(hook_type)

        if not hook_path.exists():
            return HookStatus(
                hook_type=hook_type,
                installed=False,
                is_chora_hook=False,
                path=None,
            )

        content = hook_path.read_text()
        is_chora = "chora" in content

        return HookStatus(
            hook_type=hook_type,
            installed=True,
            is_chora_hook=is_chora,
            path=hook_path,
        )

    def get_all_status(self) -> List[HookStatus]:
        """Get status of all hooks."""
        return [self.get_status(ht) for ht in HookType]

    def print_status(self) -> None:
        """Print status of all hooks."""
        print("=== Git Hooks Status ===")

        if not self._ensure_git_repo():
            print("  Not a git repository")
            return

        for status in self.get_all_status():
            if status.installed:
                chora_marker = "✅ chora" if status.is_chora_hook else "⚠️ custom"
                print(f"  {status.hook_type.value}: {chora_marker}")
            else:
                print(f"  {status.hook_type.value}: not installed")
