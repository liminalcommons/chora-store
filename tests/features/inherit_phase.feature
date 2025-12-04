Feature: Autoevolutionary Loop INHERIT Phase
  The INHERIT phase executes recommendations from the SELECT phase by
  transitioning pattern status and capturing experiment outcomes as learnings.

  This completes the autoevolution loop:
    LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT

  "Soft adoption" means:
    - Pattern status changes are executed automatically
    - No kernel YAML is mutated (human approval required for that)
    - Experiment outcomes are captured as learnings for organizational memory

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 1: Promote pattern on success
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Promote pattern when recommendation is promote
    Given an experimental pattern "pattern-success" ready for promotion
    And a fitness report with recommendation "promote"
    When execute_recommendation is called
    Then the pattern status is "adopted"
    And a learning entity is created
    And the learning domain is "epigenetic-experiment"

  Scenario: Promotion sets adopted timestamp and duration
    Given an experimental pattern "pattern-success" ready for promotion
    And a fitness report with recommendation "promote"
    When execute_recommendation is called
    Then the pattern data includes "adopted_at"
    And the pattern data includes "experimental_duration_days"
    And the pattern data includes "final_metrics"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 2: Deprecate pattern on failure
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Deprecate pattern when recommendation is deprecate
    Given an experimental pattern "pattern-failure" that failed metrics
    And a fitness report with recommendation "deprecate"
    When execute_recommendation is called
    Then the pattern status is "deprecated"
    And a learning entity is created
    And the learning domain is "epigenetic-experiment"

  Scenario: Deprecation records failure context
    Given an experimental pattern "pattern-failure" that failed metrics
    And a fitness report with recommendation "deprecate"
    When execute_recommendation is called
    Then the pattern data includes "deprecated_at"
    And the pattern data includes "deprecation_reason"
    And the pattern data includes "final_metrics"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 3: Continue pattern within observation
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Continue keeps pattern status unchanged
    Given an experimental pattern "pattern-observing" within observation period
    And a fitness report with recommendation "continue"
    When execute_recommendation is called
    Then the pattern status is "experimental"
    And no learning entity is created

  Scenario: Continue does not modify pattern data
    Given an experimental pattern "pattern-observing" within observation period
    And a fitness report with recommendation "continue"
    When execute_recommendation is called
    Then the pattern data does not include "adopted_at"
    And the pattern data does not include "deprecated_at"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 4: Canary emergency deprecation
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Canary auto-disable on critical alert
    Given an experimental pattern "pattern-problem"
    And a canary alert with severity "critical" for the pattern
    When auto_disable is called with the alert
    Then the pattern status is "deprecated"
    And the pattern data includes "disabled_by_canary" as true
    And a learning entity is created
    And the learning domain is "epigenetic-canary"

  Scenario: Canary warning does not auto-disable
    Given an experimental pattern "pattern-warning"
    And a canary alert with severity "warning" for the pattern
    When auto_disable is called with the alert
    Then the pattern status is "experimental"
    And no learning entity is created

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 5: Harvest experiment learnings
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Promotion learning captures experiment summary
    Given an experimental pattern "pattern-harvest" with full metrics
    And the pattern has 15 affected entities
    And a fitness report with recommendation "promote"
    When execute_recommendation is called
    Then the learning insight contains "Experiment Outcome"
    And the learning insight contains the pattern name
    And the learning insight contains metrics results
    And the learning links include the pattern id

  Scenario: Deprecation learning captures failure analysis
    Given an experimental pattern "pattern-failed" with failed metrics
    And a fitness report with recommendation "deprecate"
    When execute_recommendation is called
    Then the learning insight contains "deprecated"
    And the learning insight contains metrics results
    And the learning impact is "high"
