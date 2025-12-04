Feature: Full Autoevolution Loop E2E
  End-to-end test of the complete autoevolutionary cycle:
    LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT

  This proves the loop functions as a complete system, not just
  individual components working in isolation.

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 1: Full loop from bootstrap to promotion
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Full autoevolution cycle to promotion
    # MUTATE: Pattern exists in kernel
    Given a bootstrapped experimental pattern with fitness metrics

    # EXPRESS: Create entities with pattern injection
    And 10 features are created via the factory
    And 6 of the features are transitioned to stable

    # SELECT: Pattern has aged past observation period
    And the pattern is aged 100 days
    And metrics meet the success criteria

    # SELECT -> INHERIT: Evaluate and execute
    When evaluate_all is called
    And execute_recommendation is called for promote

    # INHERIT: Pattern adopted, learning created
    Then the pattern status is "adopted"
    And a learning entity exists with domain "epigenetic-experiment"
    And the learning captures the pattern name

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 2: Full loop to deprecation
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Full autoevolution cycle to deprecation
    Given a bootstrapped experimental pattern with fitness metrics
    And 10 features are created via the factory
    And only 2 of the features are transitioned to stable
    And the pattern is aged 100 days

    When evaluate_all is called
    And execute_recommendation is called for deprecate

    Then the pattern status is "deprecated"
    And a learning entity exists with domain "epigenetic-experiment"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 3: Loop preserves entity integrity
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Loop execution does not corrupt entity data
    Given a bootstrapped experimental pattern with fitness metrics
    And 5 features are created via the factory
    And the features have custom data fields

    When evaluate_all is called

    Then all features retain their custom data fields
    And all features retain their epigenetic tags

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR 4: Pattern continues within observation period
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Pattern within observation period continues
    Given a bootstrapped experimental pattern with fitness metrics
    And 5 features are created via the factory
    And the pattern is aged 30 days

    When evaluate_all is called
    And execute_recommendation is called for continue

    Then the pattern status is "experimental"
    And no learning entity is created
