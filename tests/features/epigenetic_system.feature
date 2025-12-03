Feature: Epigenetic System
  The autoevolution mechanism. Experimental patterns can inject fields,
  define hooks, track fitness, and be monitored by canaries.

  Background:
    Given a fresh repository

  Scenario: Schema extension injects fields
    Given an experimental schema-extension pattern with inject_fields
    When Factory creates an entity of the target type
    Then the entity includes the injected fields with defaults

  Scenario: Hook loading by trigger type
    Given an experimental pattern with hooks for trigger "cron:daily"
    When load_epigenetic_hooks is called for "cron:daily"
    Then hooks matching the trigger are returned

  Scenario: Hook execution on matching condition
    Given an entity matching a hook condition
    When run_epigenetic_hooks is called
    Then the hook action executes

  Scenario: Pattern fitness evaluation
    Given an experimental pattern with fitness criteria
    When PatternEvaluator.evaluate_pattern is called
    Then a recommendation is returned

  Scenario: Canary monitoring detects problems
    Given a pattern causing excessive reversions
    When CanaryMonitor.check_all is called
    Then alerts are generated with severity

  Scenario: Pattern induction from learnings
    Given multiple learnings with overlapping keywords
    When PatternInductor.analyze is called
    Then a pattern proposal is generated with confidence score
