"""
Traceability Module: Feature-Behavior-Test-Pattern Coherence.

This module bridges the gap between:
- Feature behaviors (documented in entity.yaml)
- Test scenarios (documented in .feature files)
- Code implementations (where patterns are applied)
- Patterns (reusable solutions)

Phase 1: LINK - Bridge existing tests to feature entities
Phase 2: DISCOVER - Find undocumented behaviors in code
Phase 3: AUDIT - Categorize as pattern-aligned/one-off/emergent
Phase 4: EMERGE - Document candidates as new patterns
Phase 5: COVER - Complete coverage top-down
"""

from .scanner import GherkinScanner, Scenario, Feature
from .bridge import BehaviorBridge, tool_link_all_tests
from .code_scanner import CodeScanner, CodeBehavior, tool_scan_code, tool_find_dark_behaviors
from .pattern_auditor import PatternAuditor, tool_pattern_audit, tool_find_emergent_patterns, tool_audit_behavior
from .reifier import PatternReifier, tool_reify_patterns, tool_align_behaviors, tool_pattern_coverage
from .visibility import tool_canary_alerts, tool_entities_by_pattern, tool_autoevolution_status

__all__ = [
    'GherkinScanner',
    'Scenario',
    'Feature',
    'BehaviorBridge',
    'tool_link_all_tests',
    'CodeScanner',
    'CodeBehavior',
    'tool_scan_code',
    'tool_find_dark_behaviors',
    'PatternAuditor',
    'tool_pattern_audit',
    'tool_find_emergent_patterns',
    'tool_audit_behavior',
    'PatternReifier',
    'tool_reify_patterns',
    'tool_align_behaviors',
    'tool_pattern_coverage',
    'tool_canary_alerts',
    'tool_entities_by_pattern',
    'tool_autoevolution_status',
]
