Feature: Factory Governance
  The Threshold - Factory enforces Zoning Laws (Integrity). It validates
  entity types, statuses, IDs, and required fields.

  Background:
    Given a fresh repository

  Scenario: Invalid entity type rejected
    When Factory.create is called with type "foo"
    Then ValidationError is raised for invalid type

  Scenario: Invalid initial status rejected
    When Factory.create is called with status "shipped"
    Then ValidationError is raised for invalid status

  Scenario: Semantic ID generation
    When Factory.create("feature", "Voice Canvas") is called
    Then entity ID is "feature-voice-canvas"

  Scenario: Duplicate ID rejected
    Given an entity with ID "feature-test" exists
    When Factory.create("feature", "Test") is called
    Then ValidationError is raised for duplicate ID

  Scenario: Direct skip to stable rejected
    Given a feature in status "nascent"
    When transition to "stable" is attempted
    Then ValidationError is raised for skipping converging

  Scenario: Stable requires behaviors
    Given a feature in status "converging" with no behaviors
    When transition to "stable" is attempted
    Then ValidationError is raised for missing behaviors

  Scenario: Feature without origin allowed
    When Factory.create("feature", "Standalone Feature") is called
    Then feature is created successfully

  Scenario: Origin link can be added
    Given a feature and inquiry exist
    When origin link is added to feature
    Then feature.data.origin equals inquiry ID
