Feature: Quality Gate Active Reversion
  The quality gate pattern demonstrates homeostatic resistance -
  the system actively reverts features that claim stability without evidence.

  This is NOT passive prevention (blocking creation of invalid states).
  This is ACTIVE RESISTANCE (pushing entities backward when they violate rules).

  The pattern:
  - Injects `test_evidence` and `quality_gate_passed` fields
  - Reverts features claiming "stable" without evidence to "converging"
  - Marks quality_gate_passed=true when evidence is present

  Background:
    Given a fresh repository
    And a factory with epigenetic support
    And the quality-gate pattern is bootstrapped

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 1: Revert phantom stability
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Revert feature claiming stable without evidence
    Given a feature "feature-phantom" with status "stable" and no test_evidence
    When cron:daily hooks are executed
    Then the feature "feature-phantom" status is "converging"

  Scenario: Feature can be reverted multiple times
    Given a feature "feature-repeat-offender" with status "stable" and no test_evidence
    When cron:daily hooks are executed
    Then the feature "feature-repeat-offender" status is "converging"
    When the feature is manually set back to "stable" without evidence
    And cron:daily hooks are executed again
    Then the feature "feature-repeat-offender" status is "converging"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 2: Mark quality gate passed
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Mark quality_gate_passed when stable with evidence
    Given a feature "feature-proven" with status "stable" and test_evidence "http://tests.example"
    And the feature has quality_gate_passed as false
    When cron:daily hooks are executed
    Then the feature "feature-proven" has quality_gate_passed as true

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 3: Preserve valid stable features
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Valid stable feature remains stable
    Given a feature "feature-legitimate" with status "stable" and test_evidence "http://tests.example"
    And the feature has quality_gate_passed as true
    When cron:daily hooks are executed
    Then the feature "feature-legitimate" status is "stable"
    And the feature "feature-legitimate" has no drift_signals

  Scenario: Non-stable features are not affected
    Given a feature "feature-nascent" with status "nascent" and no test_evidence
    When cron:daily hooks are executed
    Then the feature "feature-nascent" status is "nascent"
