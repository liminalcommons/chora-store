Feature: Autoevolutionary Loop VISIBILITY Phase
  The VISIBILITY phase makes the autoevolutionary loop observable.
  Tools surface canary alerts, entities affected by patterns, and
  overall autoevolution status.

  This completes observability for the loop:
    LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT -> (observe via VISIBILITY)

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 1: Surface canary alerts
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Surface critical alerts
    Given an experimental pattern "pattern-problem" with reversion signals
    When canary_alerts is called
    Then at least 1 alert is returned
    And an alert has severity "critical"

  Scenario: Surface warning alerts
    Given an experimental pattern "pattern-warning" with drift signals
    When canary_alerts is called
    Then at least 1 alert is returned
    And an alert has severity "warning"

  Scenario: No alerts when none exist
    Given an experimental pattern "pattern-healthy" with no issues
    When canary_alerts is called
    Then 0 alerts are returned

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 2: List entities by pattern
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: List entities affected by pattern
    Given an experimental pattern "pattern-test"
    And 5 features with epigenetic tag "pattern-test"
    When entities_by_pattern is called with "pattern-test"
    Then 5 entities are returned
    And all entities have the pattern in their epigenetics

  Scenario: No entities when pattern has no affected entities
    Given an experimental pattern "pattern-unused"
    When entities_by_pattern is called with "pattern-unused"
    Then 0 entities are returned

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 3: Autoevolution status dashboard
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Show autoevolution status with experimental patterns
    Given 3 experimental patterns with fitness metrics
    And features for each experimental pattern
    When autoevolution_status is called
    Then the status shows 3 experimental patterns
    And the status includes recommendation counts

  Scenario: Status includes fitness metrics
    Given an experimental pattern "pattern-evaluated" created 100 days ago
    And 6 stable features with epigenetic tag "pattern-evaluated"
    When autoevolution_status is called
    Then the status patterns include "pattern-evaluated"
    And the pattern status shows metrics achieved

  Scenario: Empty status when no experimental patterns
    When autoevolution_status is called
    Then the status shows 0 experimental patterns
