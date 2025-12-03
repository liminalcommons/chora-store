Feature: Tiered Resolution
  The push-right pattern for synthesis operations. Operations try cheaper tiers
  first and escalate when needed. All tier attempts capture traces for future
  crystallization.

  Background:
    Given a fresh repository

  Scenario: Workflow tier synthesis succeeds with high confidence
    Given multiple learnings with high keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then synthesis succeeds at the workflow tier
    And a trace is captured for the workflow tier

  Scenario: Workflow tier escalates to inference on low confidence
    Given multiple learnings with low keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then synthesis escalates to inference tier
    And traces are captured for both workflow and inference tiers

  Scenario: Max tier constraint is respected
    Given multiple learnings with low keyword overlap
    When tiered_synthesize is called with max_tier "workflow"
    Then synthesis does not escalate beyond workflow
    And an escalation reason is provided

  Scenario: Insufficient learnings returns early
    Given only one learning
    When tiered_synthesize is called with the learning IDs
    Then synthesis fails with an error about insufficient learnings
    And no traces are captured

  Scenario: Trace captures operation details
    Given multiple learnings with high keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then the trace includes operation_type "synthesize"
    And the trace includes the input learning IDs
    And the trace includes reasoning steps
