@autonomous_reification
Feature: Autonomous Pattern Reification
  As a self-improving system
  I want patterns to emerge and be governed autonomously
  So that wisdom crystallizes without human intervention

  Background:
    Given a clean test repository
    And the autonomous reification pattern is loaded

  # ═══════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Full pipeline runs on orient
  # ═══════════════════════════════════════════════════════════════════════════

  @pipeline
  Scenario: Full Phase 6 pipeline runs when orient is called
    Given there are features with behaviors
    And some behaviors are not aligned to patterns
    When the phase6.full pipeline is invoked
    Then emergent candidates are detected
    And patterns may be reified from candidates
    And behaviors are aligned to patterns
    And experimental patterns are evaluated

  @pipeline
  Scenario: Pipeline reports execution summary
    Given the phase6.full pipeline is invoked
    Then the result includes candidate count
    And the result includes patterns created count
    And the result includes behaviors aligned count

  # ═══════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Behaviors align on feature stable
  # ═══════════════════════════════════════════════════════════════════════════

  @alignment
  Scenario: Behaviors get aligned when feature reaches stable
    Given a feature with unaligned behaviors
    When the feature transitions to stable status
    Then phase6.align is triggered
    And behaviors receive implements_pattern field

  @alignment
  Scenario: Already aligned behaviors are not modified
    Given a feature with aligned behaviors
    When phase6.align runs
    Then the existing implements_pattern values are preserved

  # ═══════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Circular hooks are prevented
  # ═══════════════════════════════════════════════════════════════════════════

  @guard
  Scenario: ProcessingContext prevents circular hook execution
    Given a hook that updates an entity
    When the hook is already processing for that entity
    Then the guard returns False
    And the hook body is skipped

  @guard
  Scenario: Different entities can be processed by same hook
    Given a hook processing entity A
    When the same hook is triggered for entity B
    Then the guard allows processing entity B

  # ═══════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Patterns are reified from candidates
  # ═══════════════════════════════════════════════════════════════════════════

  @reification
  Scenario: High confidence candidates become patterns
    Given an emergent candidate with confidence 0.8
    And the candidate is not covered by existing patterns
    When reify_all is called with min_confidence 0.7
    Then a pattern entity is created with status proposed
    And reification_source is set to autonomous
    And source_behaviors contains the candidate behavior IDs

  @reification
  Scenario: Low confidence candidates are not reified
    Given an emergent candidate with confidence 0.5
    When reify_all is called with min_confidence 0.7
    Then no pattern is created for that candidate

  @reification
  Scenario: Candidates covered by existing patterns are skipped
    Given an emergent candidate that matches pattern-factory keywords
    When reify_all is called
    Then no duplicate pattern is created
    And behaviors are aligned to the existing pattern

  # ═══════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Experimental patterns are evaluated
  # ═══════════════════════════════════════════════════════════════════════════

  @evaluation
  Scenario: Patterns past observation period are evaluated
    Given an autonomous pattern with status experimental
    And the pattern was created 35 days ago
    When phase6.evaluate runs
    Then PatternEvaluator is invoked for that pattern
    And last_fitness_check is updated

  @evaluation
  Scenario: Patterns within observation period are not evaluated
    Given an autonomous pattern with status experimental
    And the pattern was created 10 days ago
    When phase6.evaluate runs
    Then PatternEvaluator is not invoked for that pattern

  @evaluation
  Scenario: Successful patterns are promoted
    Given an autonomous pattern that meets fitness criteria
    When phase6.evaluate runs
    Then the pattern status becomes adopted
    And auto_promoted is set to true

  @evaluation
  Scenario: Failed patterns are deprecated
    Given an autonomous pattern that fails fitness criteria
    When phase6.evaluate runs
    Then the pattern status becomes deprecated
    And auto_deprecated is set to true
