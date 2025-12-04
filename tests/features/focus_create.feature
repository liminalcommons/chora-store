Feature: Focus Creation from Natural Language
  The system detected a creation gap in the focus lifecycle.
  Current tools can analyze/finalize focus but not create it directly.
  This feature enables agents to create focus from natural language descriptions.

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 1: Basic Focus Creation
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Create focus from natural language goal
    When focus is created with goal "Implement cross-domain pattern detection"
    Then a focus entity exists with status "open"
    And the focus has goal_level set to true
    And the focus has entry_type "natural_language"

  Scenario: Create focus with explicit target entity
    Given a feature "feature-voice-canvas" exists
    When focus is created with goal "Work on voice canvas" targeting "feature-voice-canvas"
    Then the focus has target "feature-voice-canvas"
    And the focus links to the target entity

  Scenario: Create focus with agent attribution
    When focus is created with goal "Explore repository design" by agent "claude-opus"
    Then the focus has agent "claude-opus"

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 2: Intelligent Target Resolution
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Resolve target from goal text
    Given a feature "feature-authentication" exists with name "User Authentication"
    When focus is created with goal "Work on user authentication"
    Then the focus has target "feature-authentication"
    And no user confirmation was required

  Scenario: Handle ambiguous target by creating inquiry
    Given a feature "feature-auth-login" exists with name "Login Auth"
    And a feature "feature-auth-oauth" exists with name "OAuth Auth"
    When focus is created with goal "Work on auth"
    Then a focus entity exists with status "open"
    And the focus has a target starting with "inquiry-"
    And the focus includes candidate_targets in data

  Scenario: Create focus for inquiry exploration
    Given an inquiry "inquiry-how-to-improve-performance" exists
    When focus is created with goal "Explore performance inquiry"
    Then the focus has target "inquiry-how-to-improve-performance"
    And the focus has entry_type "natural_language"

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 3: Focus Properties
  # ═══════════════════════════════════════════════════════════════════════════════

  # Note: Epigenetic pattern inheritance is tested in factory tests
  # tool_focus_create delegates to factory.create which handles _epigenetics

  Scenario: Focus has default TTL
    When focus is created with goal "Quick investigation"
    Then the focus has ttl_minutes set to 240

  Scenario: Focus can have custom TTL
    When focus is created with goal "Extended research" with ttl_minutes 480
    Then the focus has ttl_minutes set to 480

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 4: Integration with Existing Tools
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Focus-create and engage produce similar results
    Given a feature "feature-test-integration" exists
    When focus is created with goal "Work on test integration" targeting "feature-test-integration"
    Then the focus structure matches engage output for same feature
