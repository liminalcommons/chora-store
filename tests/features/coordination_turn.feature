Feature: The Coordination Turn (v0.4.0)
  Orient as coordination surface, enabling multi-agent awareness
  through presence sensing, hierarchy of attention, and cross-scale visibility.

  Background:
    Given a fresh repository

  # ═══════════════════════════════════════════════════════════════════════════════
  # Feature: Presence via Change Lens
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Recent changes are surfaced with agent attribution
    Given multiple agents have made changes to the workspace
    When orient is invoked
    Then recent changes are surfaced with agent attribution

  Scenario: Context includes recent changes with timestamps and agents
    Given an entity was modified by another agent
    When get_workspace_context() is called
    Then context includes recent_changes with timestamps and agents

  Scenario: Context indicates solo work mode
    Given no changes by others exist
    When orient is invoked
    Then context indicates solo work mode

  # ═══════════════════════════════════════════════════════════════════════════════
  # Feature: Hierarchy of Attention
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Orient filters by scale
    Given entities exist at inner, adjacent, and far scales
    When orient is invoked with scope filter
    Then only entities matching scale are returned

  Scenario: Inner scope returns immediate work
    Given inner scope is active tasks and current features
    When get_workspace_context with scope="inner" is called
    Then only immediate work items are returned

  Scenario: Far scope returns systemic entities
    Given far scope includes patterns and learnings
    When get_workspace_context with scope="far" is called
    Then systemic entities patterns and releases are included

  # ═══════════════════════════════════════════════════════════════════════════════
  # Feature: Cross-Scale Visibility
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Revolt trajectories are surfaced
    Given learnings have crystallized into patterns
    When cross-scale summary is requested
    Then learning to pattern trajectories are surfaced

  Scenario: Remember trajectories are surfaced
    Given patterns are influencing current work
    When cross-scale summary is requested
    Then pattern to feature influences are surfaced

  Scenario: Both cycle summaries are included
    Given fast cycle tasks and slow cycle patterns exist
    When orient is invoked
    Then both cycle summaries are included in context

  # ═══════════════════════════════════════════════════════════════════════════════
  # Feature: Orient as Coordination Surface
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Individual context is included
    Given individual context my work exists
    When orient is invoked
    Then personal work summary is included

  Scenario: Collective context is included
    Given collective context team work exists
    When orient is invoked
    Then shared workspace summary is included

  Scenario: Both contexts are unified without duplication
    Given both individual and collective contexts exist
    When orient unifies them
    Then context includes both without duplication

  Scenario: Coordination signals surface based on attention
    Given coordination signals are present
    When orient processes them
    Then relevant signals surface based on attention hierarchy
