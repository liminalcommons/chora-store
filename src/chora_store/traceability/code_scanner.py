"""
Code Scanner: Discover undocumented behaviors in implementation.

This module scans Python code to find:
1. Factory pattern usage (entity creation)
2. Repository pattern usage (CRUD operations)
3. Observer signals (event handling)
4. Recurring structural patterns that may be undocumented behaviors

The goal is to surface "dark behaviors" - implemented functionality
that isn't captured in feature behaviors or test scenarios.
"""

import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple


@dataclass
class CodeBehavior:
    """A discovered behavior in code."""
    file_path: Path
    line_number: int
    behavior_type: str  # 'factory', 'repository', 'observer', 'pattern'
    action: str         # e.g., 'create', 'update', 'emit', 'transition'
    context: str        # Surrounding code context
    entity_type: Optional[str] = None  # If applicable
    confidence: float = 0.7  # How confident we are this is a behavior

    @property
    def id(self) -> str:
        """Generate a behavior ID from the discovery."""
        safe_path = self.file_path.stem.replace('_', '-')
        return f"behavior-discovered-{safe_path}-{self.behavior_type}-{self.action}-L{self.line_number}"

    def to_behavior_format(self) -> Dict[str, Any]:
        """Convert to kernel behavior format for documentation."""
        return {
            'id': self.id,
            'given': f"Code in {self.file_path.name}:{self.line_number}",
            'when': f"{self.behavior_type}.{self.action} is called",
            'then': f"Behavior executes ({self.context[:50]}...)",
            'verifiable_by': 'trace',  # Code behaviors need trace verification
            'status': 'untested',
            'source': 'discovered',
            'file': str(self.file_path),
            'line': self.line_number,
        }


class PatternUsageVisitor(ast.NodeVisitor):
    """AST visitor that finds pattern usage in code."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.behaviors: List[CodeBehavior] = []
        self.imports: Set[str] = set()
        self.current_function: Optional[str] = None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            for alias in node.names:
                self.imports.add(f"{node.module}.{alias.name}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Call(self, node: ast.Call) -> None:
        self._check_factory_call(node)
        self._check_repository_call(node)
        self._check_observer_call(node)
        self.generic_visit(node)

    def _check_factory_call(self, node: ast.Call) -> None:
        """Detect Factory pattern usage."""
        # Look for factory.create(), EntityFactory(), etc.
        func_name = self._get_call_name(node)
        if not func_name:
            return

        if 'factory' in func_name.lower() or 'create' in func_name.lower():
            entity_type = self._extract_entity_type(node)
            context = self._get_context(node)

            self.behaviors.append(CodeBehavior(
                file_path=self.file_path,
                line_number=node.lineno,
                behavior_type='factory',
                action='create',
                context=context,
                entity_type=entity_type,
                confidence=0.8 if 'factory' in func_name.lower() else 0.5,
            ))

    def _check_repository_call(self, node: ast.Call) -> None:
        """Detect Repository pattern usage."""
        func_name = self._get_call_name(node)
        if not func_name:
            return

        repo_methods = ['read', 'update', 'delete', 'list', 'create', 'orient', 'save']
        for method in repo_methods:
            if method in func_name.lower() and ('repo' in func_name.lower() or 'repository' in func_name.lower()):
                context = self._get_context(node)
                self.behaviors.append(CodeBehavior(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    behavior_type='repository',
                    action=method,
                    context=context,
                    confidence=0.7,
                ))
                break

    def _check_observer_call(self, node: ast.Call) -> None:
        """Detect Observer/event pattern usage."""
        func_name = self._get_call_name(node)
        if not func_name:
            return

        observer_keywords = ['emit', 'notify', 'observe', 'signal', 'event', 'trigger', 'hook']
        for keyword in observer_keywords:
            if keyword in func_name.lower():
                context = self._get_context(node)
                self.behaviors.append(CodeBehavior(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    behavior_type='observer',
                    action=keyword,
                    context=context,
                    confidence=0.6,
                ))
                break

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        return None

    def _extract_entity_type(self, node: ast.Call) -> Optional[str]:
        """Try to extract entity type from a factory call."""
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value in ['inquiry', 'feature', 'focus', 'learning', 'pattern', 'release', 'tool']:
                    return arg.value
        for keyword in node.keywords:
            if keyword.arg in ['entity_type', 'type'] and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
        return None

    def _get_context(self, node: ast.Call) -> str:
        """Get code context around the call."""
        if self.current_function:
            return f"in {self.current_function}()"
        return "at module level"


class CodeScanner:
    """
    Scans Python code to discover undocumented behaviors.

    Finds:
    - Factory pattern usage (entity creation)
    - Repository pattern usage (CRUD)
    - Observer signals (events)
    - Recurring patterns that may be candidates for documentation
    """

    def __init__(self, source_paths: Optional[List[Path]] = None):
        """
        Initialize scanner.

        Args:
            source_paths: Directories/files to scan. Defaults to chora-store/src.
        """
        if source_paths is None:
            base = Path(__file__).parent.parent  # chora_store module
            source_paths = [base]
        self.source_paths = source_paths

    def scan_file(self, file_path: Path) -> List[CodeBehavior]:
        """Scan a single Python file for behaviors."""
        try:
            content = file_path.read_text()
            tree = ast.parse(content)

            visitor = PatternUsageVisitor(file_path)
            visitor.visit(tree)

            return visitor.behaviors
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return []
        except Exception as e:
            print(f"Error scanning {file_path}: {e}")
            return []

    def scan_directory(self, directory: Path) -> List[CodeBehavior]:
        """Scan a directory for Python files."""
        behaviors = []

        for py_file in directory.glob('**/*.py'):
            # Skip test files and __pycache__
            if 'test' in str(py_file) or '__pycache__' in str(py_file):
                continue

            file_behaviors = self.scan_file(py_file)
            behaviors.extend(file_behaviors)

        return behaviors

    def scan_all(self) -> List[CodeBehavior]:
        """Scan all configured source paths."""
        all_behaviors = []

        for path in self.source_paths:
            if path.is_file():
                all_behaviors.extend(self.scan_file(path))
            elif path.is_dir():
                all_behaviors.extend(self.scan_directory(path))

        return all_behaviors

    def categorize_behaviors(
        self,
        behaviors: List[CodeBehavior]
    ) -> Dict[str, List[CodeBehavior]]:
        """
        Categorize discovered behaviors by type.

        Returns dict with keys: factory, repository, observer, pattern
        """
        categories: Dict[str, List[CodeBehavior]] = {
            'factory': [],
            'repository': [],
            'observer': [],
            'pattern': [],
        }

        for b in behaviors:
            if b.behavior_type in categories:
                categories[b.behavior_type].append(b)

        return categories

    def find_undocumented(
        self,
        behaviors: List[CodeBehavior],
        documented_behaviors: List[Dict]
    ) -> List[CodeBehavior]:
        """
        Find behaviors that don't match any documented behavior.

        Args:
            behaviors: Discovered code behaviors
            documented_behaviors: Behaviors from entity definitions

        Returns:
            List of undocumented behaviors (dark behaviors)
        """
        # Build a set of documented behavior identifiers
        documented_ids = set()
        for b in documented_behaviors:
            # Normalize behavior identifier
            when = b.get('when', '').lower()
            then = b.get('then', '').lower()
            documented_ids.add((when, then))

        undocumented = []
        for behavior in behaviors:
            # Check if this behavior is documented
            behavior_key = (
                f"{behavior.behavior_type}.{behavior.action}".lower(),
                behavior.context.lower()
            )

            # Fuzzy match against documented behaviors
            matched = False
            for doc_when, doc_then in documented_ids:
                if behavior.action in doc_when or behavior.behavior_type in doc_when:
                    matched = True
                    break

            if not matched:
                undocumented.append(behavior)

        return undocumented

    def generate_report(self, behaviors: List[CodeBehavior]) -> str:
        """Generate a report of discovered behaviors."""
        lines = ['CODE BEHAVIOR SCAN REPORT', '=' * 60]

        categories = self.categorize_behaviors(behaviors)

        lines.append(f"Total behaviors discovered: {len(behaviors)}")
        for cat, cat_behaviors in categories.items():
            lines.append(f"  {cat}: {len(cat_behaviors)}")
        lines.append('')

        # Group by file
        by_file: Dict[Path, List[CodeBehavior]] = {}
        for b in behaviors:
            if b.file_path not in by_file:
                by_file[b.file_path] = []
            by_file[b.file_path].append(b)

        for file_path, file_behaviors in sorted(by_file.items()):
            lines.append(f"\n{file_path.name}:")
            for b in file_behaviors:
                conf = int(b.confidence * 100)
                lines.append(f"  L{b.line_number}: [{b.behavior_type}] {b.action} ({conf}%)")
                lines.append(f"         {b.context}")

        return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP TOOL INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

def tool_scan_code(directory: str = "src/chora_store") -> str:
    """
    Scan Python code for undocumented behaviors.

    Discovers Factory, Repository, and Observer pattern usage
    that may represent undocumented behaviors.

    Args:
        directory: Directory to scan (relative to chora-store)

    Returns:
        Report of discovered behaviors
    """
    base = Path(__file__).parent.parent.parent.parent  # chora-store root
    target_dir = base / directory

    if not target_dir.exists():
        return f"Directory not found: {target_dir}"

    scanner = CodeScanner([target_dir])
    behaviors = scanner.scan_all()

    if not behaviors:
        return "No behaviors discovered in code."

    return scanner.generate_report(behaviors)


def tool_find_dark_behaviors() -> str:
    """
    Find "dark behaviors" - implemented but undocumented functionality.

    Compares code patterns against documented feature behaviors
    to surface functionality gaps.

    Returns:
        Report of undocumented behaviors needing documentation
    """
    from ..repository import EntityRepository

    # Scan code
    base = Path(__file__).parent.parent  # chora_store module
    scanner = CodeScanner([base])
    code_behaviors = scanner.scan_all()

    # Get documented behaviors from features
    repo = EntityRepository()
    features = repo.list(entity_type='feature', limit=1000)

    documented = []
    for f in features:
        behaviors = f.data.get('behaviors', [])
        documented.extend(behaviors)

    # Find undocumented
    undocumented = scanner.find_undocumented(code_behaviors, documented)

    lines = ['DARK BEHAVIORS REPORT', '=' * 60]
    lines.append(f"Code behaviors found: {len(code_behaviors)}")
    lines.append(f"Documented behaviors: {len(documented)}")
    lines.append(f"Potentially undocumented: {len(undocumented)}")
    lines.append('')

    if undocumented:
        lines.append("UNDOCUMENTED BEHAVIORS (need review):")
        categories = scanner.categorize_behaviors(undocumented)

        for cat, cat_behaviors in categories.items():
            if cat_behaviors:
                lines.append(f"\n  {cat.upper()} ({len(cat_behaviors)}):")
                for b in cat_behaviors[:10]:  # Limit to top 10 per category
                    lines.append(f"    {b.file_path.name}:{b.line_number}")
                    lines.append(f"      {b.action}: {b.context}")
                if len(cat_behaviors) > 10:
                    lines.append(f"    ... and {len(cat_behaviors) - 10} more")

        lines.append('')
        lines.append("Actions:")
        lines.append("  1. Review if these represent real behaviors")
        lines.append("  2. Add to feature behaviors if significant")
        lines.append("  3. Create tests for verified behaviors")
    else:
        lines.append("No undocumented behaviors found. Good coverage!")

    return '\n'.join(lines)
