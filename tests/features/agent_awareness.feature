Feature: Agent Awareness
  The greeting and orientation system. Provides temporal grounding,
  active work visibility, and narrative continuity for agents.

  Background:
    Given a fresh repository

  Scenario: Orient provides temporal grounding
    Given an agent arriving at the workspace
    When orient() is called
    Then output includes time since last orientation

  Scenario: Orient shows active work
    Given active features exist in the repository
    When get_workspace_context() is called
    Then the context includes active work items

  Scenario: Orient shows narrative
    Given a current focus exists
    When get_workspace_context() is called
    Then the context includes season and integrity score

  Scenario: Constellation shows linkage
    Given an entity with relationships
    When constellation(entity_id) is called
    Then output shows linked entities
