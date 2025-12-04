Feature: Autoevolutionary Loop SELECT Phase
  The SELECT phase evaluates experimental pattern fitness by parsing metric
  queries and calculating values. This enables the system to make promotion
  or deprecation recommendations based on observed outcomes.

  The autoevolutionary loop has 5 phases:
    LEARN -> MUTATE -> EXPRESS -> SELECT -> INHERIT

  This feature covers the SELECT phase - fitness evaluation and recommendations.

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: IS NOT NULL filters entities correctly
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: IS NOT NULL excludes empty and null values
    Given an experimental pattern "pattern-quality-gate" with metrics
    And a feature "feature-with-evidence" with test_evidence "http://tests.example"
    And a feature "feature-empty-evidence" with test_evidence ""
    And a feature "feature-null-evidence" with test_evidence null
    When the evaluator executes "count(features WHERE test_evidence IS NOT NULL)"
    Then the result is 1

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: IS NULL treats empty string as null
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: IS NULL matches both null and empty string
    Given an experimental pattern "pattern-quality-gate" with metrics
    And a feature "feature-with-evidence" with test_evidence "http://tests.example"
    And a feature "feature-empty-evidence" with test_evidence ""
    And a feature "feature-null-evidence" with test_evidence null
    When the evaluator executes "count(features WHERE test_evidence IS NULL)"
    Then the result is 2

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Ratio queries with simple denominators work
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Ratio with simple denominator calculates correctly
    Given an experimental pattern "pattern-lifecycle" with metrics
    And 3 features with status "stable"
    And 7 features with status "nascent"
    When the evaluator executes "count(features WHERE status='stable') / count(features)"
    Then the result is 0.3

  Scenario: Ratio handles divide by zero gracefully
    Given an experimental pattern "pattern-empty" with metrics
    When the evaluator executes "count(features WHERE status='stable') / count(features)"
    Then the result is 0.0

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Pattern evaluation returns non-null metrics
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Evaluate pattern returns metrics with values
    Given an experimental pattern with fitness metrics:
      | name            | query                                                    | target |
      | completion_rate | count(features WHERE status='stable') / count(features) | 0.5    |
      | drift_rate      | count(features WHERE status='drifting') / count(features) | 0.1   |
    And 5 features with status "stable"
    And 5 features with status "nascent"
    When PatternEvaluator.evaluate_pattern is called
    Then all metrics have non-null current_value
    And the completion_rate metric value is 0.5
    And the completion_rate metric is achieved

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Recommendations based on observation period
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Pattern within observation period gets continue recommendation
    Given an experimental pattern created 10 days ago with 90 day observation
    And metrics that meet targets
    When PatternEvaluator.evaluate_pattern is called
    Then the recommendation is "continue"
    And observation_period_elapsed is false

  Scenario: Pattern past observation period with success gets promote recommendation
    Given an experimental pattern created 100 days ago with 90 day observation
    And metrics that meet targets
    When PatternEvaluator.evaluate_pattern is called
    Then the recommendation is "promote"
    And observation_period_elapsed is true

  Scenario: Pattern past observation period with failure gets deprecate recommendation
    Given an experimental pattern created 100 days ago with 90 day observation
    And metrics that fail targets
    When PatternEvaluator.evaluate_pattern is called
    Then the recommendation is "deprecate"

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: Compound conditions in queries
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Query with AND condition
    Given an experimental pattern "pattern-compound" with metrics
    And a feature "feature-stable-tested" with status "stable" and test_evidence "http://example.com"
    And a feature "feature-stable-untested" with status "stable" and test_evidence ""
    And a feature "feature-nascent-tested" with status "nascent" and test_evidence "http://example.com"
    When the evaluator executes "count(features WHERE status='stable' AND test_evidence IS NOT NULL)"
    Then the result is 1

  # ════════════════════════════════════════════════════════════════════════════
  # BEHAVIOR: evaluate_all processes all experimental patterns
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: evaluate_all returns reports for all experimental patterns
    Given 3 experimental schema-extension patterns with metrics
    And features for each pattern
    When PatternEvaluator.evaluate_all is called
    Then 3 fitness reports are returned
    And all reports have a recommendation
