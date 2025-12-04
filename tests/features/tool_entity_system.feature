@tool-entity-system
Feature: Tool Entity System
  Tools are the 7th Noun - dynamic affordances that agents can invoke.
  They must be governed by features with phenomenological cognition.

  Background:
    Given the kernel schema supports tool entities
    And the pattern-tool-cognition-lifecycle is active

  # ==========================================================================
  # Wave 1: Tool Entity Infrastructure
  # ==========================================================================

  @wave1
  Scenario: Tool entity can be created with handler
    Given I have a handler definition for "orient"
    When I create a tool entity with that handler
    Then the tool entity exists with status "active"
    And the tool has interfaces ["mcp", "cli"]

  @wave1
  Scenario: Tool entity requires handler field
    When I try to create a tool entity without a handler
    Then the creation fails with a validation error
    And the error mentions "handler is required"

  @wave1
  Scenario: Tool entity links to governing feature
    Given a feature "feature-cognitive-cycle-tools" exists
    When I create tool "tool-orient" with origin "feature-cognitive-cycle-tools"
    Then the tool's cognition.origin equals "feature-cognitive-cycle-tools"

  @wave1
  Scenario: Tool with cognition.core appears in Quick Reference
    Given a tool "tool-orient" with cognition.core = true
    When I run claudemd-regen
    Then CLAUDE.md Quick Reference includes "orient"

  # ==========================================================================
  # Wave 2: Cognitive Cycle Tools
  # ==========================================================================

  @wave2
  Scenario: Orient tool returns workspace state
    When I invoke tool-orient
    Then I receive season, integrity, active_work, and suggestions

  @wave2
  Scenario: Constellation tool returns entity relationships
    Given an entity "feature-test" exists with links
    When I invoke tool-constellation with entity_id "feature-test"
    Then I receive upstream, downstream, and sibling relationships

  @wave2
  Scenario: Get entity returns complete data
    Given an entity "feature-test" exists
    When I invoke tool-get-entity with id "feature-test"
    Then I receive the complete entity with id, type, status, data

  @wave2
  Scenario: List entities filters by type
    Given entities of type "learning" exist
    When I invoke tool-list-entities with type "learning"
    Then I receive only learning entities

  # ==========================================================================
  # Wave 3: Pattern Metabolism Tools
  # ==========================================================================

  @wave3
  Scenario: Induction clusters related learnings
    Given at least 5 learning entities exist with similar content
    When I invoke tool-induction
    Then I receive clusters of related learnings
    And each cluster has a suggested pattern name

  @wave3
  Scenario: Synthesize transforms cluster into pattern
    Given an induction cluster with 3+ learnings
    When I invoke tool-synthesize-learnings with the cluster
    Then a new pattern entity is created
    And the pattern links back to source learnings

  @wave3
  Scenario: Suggest patterns returns applicable patterns
    Given patterns exist for entity type "feature"
    When I invoke tool-suggest-patterns for "feature"
    Then I receive a list of applicable patterns
    And each pattern includes its governance fields

  # ==========================================================================
  # Wave 4: Transformation Verbs
  # ==========================================================================

  @wave4
  Scenario: Crystallize transforms inquiry to feature
    Given an inquiry "inquiry-test-idea" exists with status "active"
    When I invoke tool-crystallize with inquiry_id "inquiry-test-idea"
    Then a new feature "feature-test-idea" is created
    And the inquiry status becomes "reified"
    And the feature has origin "inquiry-test-idea"

  @wave4
  Scenario: Engage creates focus on feature
    Given a feature "feature-test" exists with status "nascent"
    When I invoke tool-engage with feature_id "feature-test"
    Then a focus entity is created targeting "feature-test"
    And the focus has status "open"

  @wave4
  Scenario: Finalize extracts learning and archives
    Given an entity "feature-old" exists
    When I invoke tool-finalize with entity_id "feature-old" and reason "no longer needed"
    Then a learning is created with insight "no longer needed"
    And the entity status becomes "finalizing"

  # ==========================================================================
  # Wave 5: Release Coherence Tools
  # ==========================================================================

  @wave5
  Scenario: Wobble test detects imbalances
    Given a release "release-v1" exists with incomplete features
    When I invoke tool-wobble-test with release_id "release-v1"
    Then I receive a list of imbalances
    And each imbalance has type and description

  @wave5
  Scenario: Pre-release check returns GO/WAIT/STOP
    Given a release "release-v1" exists
    When I invoke tool-pre-release-check with release_id "release-v1"
    Then I receive a recommendation of GO, WAIT, or STOP
    And the recommendation includes reasons

  # ==========================================================================
  # Wave 5: Meta-Cognition Tools
  # ==========================================================================

  @wave5
  Scenario: Notice emerging tools senses latent affordances
    Given recent friction patterns exist in learnings
    When I invoke tool-notice-emerging-tools
    Then I receive suggested tools that want to exist
    And each suggestion has a confidence score

  @wave5
  Scenario: CLAUDE.md regen updates generated sections
    Given tools with cognition exist
    When I invoke tool-claudemd-regen with action "regen"
    Then CLAUDE.md generated sections are updated
    And the tool count matches actual tools

  # ==========================================================================
  # Lifecycle Coupling (from pattern-tool-cognition-lifecycle)
  # ==========================================================================

  @lifecycle
  Scenario: Core tools protected from deprecation
    Given a tool "tool-orient" with cognition.cognitive_status = "core"
    When I try to deprecate the tool
    Then the deprecation is blocked
    And the error mentions "Core tools cannot be deprecated"

  @lifecycle
  Scenario: Deprecated tool cognition is archived
    Given a tool "tool-old" with cognition exists
    When the tool status changes to "deprecated"
    Then cognition.archived_at is set
    And cognition.cognitive_status becomes "deprecated"

  @lifecycle
  Scenario: Stale experimental cognition triggers alert
    Given a tool with experimental cognition unchanged for 60+ days
    When the staleness check runs
    Then a tool.cognition.stale event is emitted

  # ==========================================================================
  # Wave 6: Entity CRUD Tools (Dogfooding)
  # ==========================================================================

  @wave6
  Scenario: Create entity surfaces discovery for existing entity
    Given a feature "feature-voice-canvas" exists with status "drifting"
    When I invoke tool-create-entity with type "feature" and title "Voice Canvas"
    Then I receive a discovery gate response
    And the response mentions "feature-voice-canvas"

  @wave6
  Scenario: Create entity proceeds with skip_discovery
    Given a feature "feature-voice-canvas" exists
    When I invoke tool-create-entity with type "feature" and title "Voice Canvas Two" and skip_discovery=True
    Then a new entity "feature-voice-canvas-two" is created

  @wave6
  Scenario: Create entity returns next steps suggestion
    When I invoke tool-create-entity with type "feature" and title "New Feature" and skip_discovery=True
    Then the response includes next steps for "feature"

  @wave6
  Scenario: Update entity changes data field
    Given an entity "feature-test-update" exists
    When I invoke tool-update-entity with entity_id "feature-test-update" and priority = "high"
    Then the entity's data.priority equals "high"

  @wave6
  Scenario: Update entity validates status transition
    Given a feature "feature-test-status" in status "nascent"
    When I invoke tool-update-entity with entity_id "feature-test-status" and status = "stable"
    Then the update shows a warning
    And the response mentions blocked transition

  @wave6
  Scenario: Update entity allows valid transition
    Given a feature "feature-test-valid" in status "nascent"
    When I invoke tool-update-entity with entity_id "feature-test-valid" and status = "converging"
    Then the status becomes "converging"
