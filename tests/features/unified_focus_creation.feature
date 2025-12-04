@unified-focus
Feature: Unified Focus Creation Through Factory
  Focus entities MUST be created through Factory to ensure:
  - Structural governance (validation)
  - Stigmergic coordination (observer signals)
  - Epigenetic mutations (schema extensions)

  FocusManager is DEPRECATED. All focus operations route through Factory.

  Background:
    Given a fresh repository
    And a Factory with kernel schema

  # ==========================================================================
  # FACTORY AS PRIMARY PATH
  # ==========================================================================

  @primary
  Scenario: Factory creates focus with semantic ID
    When Factory.create is called with type "focus" target "feature-voice-canvas" agent "claude"
    Then a focus entity exists
    And the focus ID is "focus-claude-on-voice-canvas"
    And focus.status equals "open"
    And focus.data.target equals "feature-voice-canvas"
    And focus.data.agent equals "claude"

  @primary
  Scenario: Focus creation emits observer signal
    Given an observer is registered for CREATED events
    When Factory.create is called with type "focus" target "feature-test" agent "claude"
    Then the observer receives a CREATED event
    And the event contains the focus entity

  @primary
  Scenario: Focus inherits epigenetic fields
    Given the kernel has focus schema extensions
    When Factory.create is called with type "focus" target "feature-test" agent "claude"
    Then the focus has ttl_minutes field
    And the focus has trail field as empty list
    And the focus has started_at timestamp

  # ==========================================================================
  # VALIDATION (via Factory)
  # ==========================================================================

  @validation
  Scenario: Focus requires target field
    When I attempt to create focus without target
    Then creation fails with validation error mentioning "target"

  @validation
  Scenario: Focus requires agent field
    When I attempt to create focus without agent
    Then creation fails with validation error mentioning "agent"

  @validation
  Scenario: Focus target must be valid entity ID format
    When I attempt to create focus with target "not a valid id"
    Then creation fails with validation error mentioning "target"

  # ==========================================================================
  # FOCUS LIFECYCLE (via Factory.update)
  # ==========================================================================

  @lifecycle
  Scenario: Focus finalization via Factory
    Given a focus "focus-claude-on-test" exists with status "open"
    When Factory.update is called with status "finalized"
    Then focus.status equals "finalized"
    And focus.data.finalized_at is set

  @lifecycle
  Scenario: Focus unlock via Factory
    Given a focus "focus-claude-on-test" exists with status "open"
    When Factory.update is called with status "unlocked"
    Then focus.status equals "unlocked"

  @lifecycle
  Scenario: Trail update via Factory
    Given a focus "focus-claude-on-test" exists
    When Factory.update is called with trail ["learning-insight-1"]
    Then focus.data.trail contains "learning-insight-1"

  # ==========================================================================
  # DEPRECATION
  # ==========================================================================

  @deprecation
  Scenario: FocusManager.create_focus emits deprecation warning
    Given FocusManager is initialized
    When FocusManager.create_focus is called
    Then a deprecation warning is emitted
    And the warning mentions "Use Factory.create('focus', ...) instead"

  @deprecation
  Scenario: tool_engage uses Factory directly
    Given a feature "feature-test" exists for tool_engage
    When tool_engage is invoked with feature_id "feature-test"
    Then Factory.create was called with type "focus"
    And FocusManager was not used
