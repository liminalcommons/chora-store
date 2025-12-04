@wave8 @metabolic
Feature: Metabolic Cycle Activation (Compound Leverage)
  The system has self-extending capabilities that need activation, not addition.
  Wave 8 closes the autopoietic loop: Pattern -> Tool -> Observation -> Learning -> Pattern

  This feature captures the compound leverage mechanisms being activated.

  Background:
    Given a fresh repository
    And a Factory with kernel schema

  # ==========================================================================
  # PHASE A: FIRST GENERATIVE TOOL
  # Pattern -> Tool link: Tools that create entities
  # ==========================================================================

  @phaseA @generative
  Scenario: Generative tool can be created with handler type "generative"
    When I create a tool entity with handler type "generative"
    And the handler has prompt_template and output_type
    Then the tool entity exists with status "active"
    And the tool has handler.type equals "generative"

  @phaseA @generative
  Scenario: tool-propose-pattern generates pattern proposals from learning clusters
    Given tool "tool-propose-pattern" exists with generative handler
    And learnings "learning-a", "learning-b", "learning-c" exist
    When I invoke tool-propose-pattern with those learning IDs
    Then a pattern proposal YAML is generated
    And the proposal has type "pattern" and status "proposed"

  @phaseA @generative
  Scenario: Generative handler with approval_required returns spec for review
    Given tool "tool-propose-pattern" has approval_required = true
    When I invoke tool-propose-pattern with learning IDs
    Then the response contains "[APPROVAL REQUIRED]"
    And the response contains the generated YAML spec
    And no entity is persisted yet

  @phaseA @generative @trace
  Scenario: Generative tool invocations create traces
    Given tool "tool-propose-pattern" exists
    When I invoke tool-propose-pattern
    Then a trace is captured with tool_id and input_signature

  # ==========================================================================
  # PHASE B: ROUTE CRYSTALLIZATION
  # Observation -> Optimization: Traces compound into routes
  # ==========================================================================

  @phaseB @crystallization
  Scenario: Orient surfaces route crystallization candidates
    Given 5 traces exist with matching input signatures
    And the traces have 95% output consistency
    When I run orient
    Then the output includes crystallization candidates
    And the candidate shows trace count and consistency

  @phaseB @crystallization
  Scenario: High-confidence routes auto-crystallize during orient
    Given crystallization candidates with >= 95% consistency exist
    When I run orient
    Then routes are automatically crystallized
    And the output confirms route creation

  @phaseB @crystallization
  Scenario: Route table find_crystallization_candidates works
    Given multiple traces with similar signatures exist
    When I call find_crystallization_candidates with min_traces=3
    Then candidates are returned with signature, trace_count, and consistency

  # ==========================================================================
  # PHASE C: ORIENT DOGFOODING
  # Tool Composition: Orient uses tools rather than hardcoding
  # ==========================================================================

  @phaseC @dogfooding
  Scenario: Orient invokes tool-induction for pattern emergence
    Given learnings exist with potential clusters
    When I run orient
    Then tool-induction is invoked internally
    And pattern emergence signals appear in output

  @phaseC @dogfooding
  Scenario: Orient tool invocations generate traces
    When I run orient with tool dogfooding enabled
    Then traces are captured for each tool invocation
    And the traces feed route crystallization

  @phaseC @dogfooding
  Scenario: Orient shows synthesis opportunities from tools
    Given 5+ captured learnings exist
    When I run orient
    Then synthesis opportunities are shown
    And they come from tool-induction results

  # ==========================================================================
  # PHASE D: INDUCTION AUTOMATION
  # Learning -> Pattern link: Induction auto-triggers
  # ==========================================================================

  @phaseD @automation
  Scenario: Epigenetic hook auto-invokes induction on learning threshold
    Given 4 captured learnings exist
    And the hook "learning-batch-induction" is active
    When a 5th learning is created
    Then tool-induction is auto-invoked via hook
    And induction results are emitted

  @phaseD @automation
  Scenario: invoke_tool action handler works in observer
    Given an epigenetic hook with action "invoke_tool('tool-induction')"
    When the hook condition is met
    Then the observer invokes the tool
    And the tool result is captured

  @phaseD @automation
  Scenario: Induction surfaces pattern proposal opportunities
    Given induction finds a cluster of 3+ learnings
    When tool-induction completes
    Then the result suggests tool-propose-pattern as next step
    And the cluster theme is included

  # ==========================================================================
  # PHASE E: LOOP CLOSURE
  # Pattern -> Tool emergence: Full autopoietic cycle
  # ==========================================================================

  @phaseE @loop-closure
  Scenario: Adopted pattern triggers tool emergence evaluation
    Given pattern "pattern-test" with status "experimental"
    And the pattern has mechanics and fitness data
    When the pattern status changes to "adopted"
    Then tool-notice-emerging-tools is invoked
    And the pattern is evaluated for tool candidacy

  @phaseE @loop-closure
  Scenario: Full autopoietic cycle is observable
    Given learnings accumulate and cluster
    When induction triggers and proposes a pattern
    And the pattern is adopted
    Then the pattern-to-tool evaluation fires
    And the cycle can repeat

  # ==========================================================================
  # INQUIRIES EMERGING FROM THIS WORK
  # ==========================================================================

  # inquiry-metabolic-cycle-as-operational-not-aspirational
  # - "The system can digest but digestion doesn't happen"
  # - "What activates the existing compound mechanisms?"
  # - Resolved by: This Wave 8 implementation

  # inquiry-learning-lifecycle-evolution (existing, Nov 28 2025)
  # - "What happens to learnings over time?"
  # - "How do we manage their interrelations?"
  # - Partially addressed by: Phase D induction automation

  # ==========================================================================
  # LEARNINGS TO CAPTURE
  # ==========================================================================

  # learning-compound-vs-additive-leverage
  # - "Activating existing mechanisms is multiplicative, adding new is additive"
  # - "The system already has L5 generative handlers, route crystallization, hooks"
  # - Implication: Prefer activation over creation

  # learning-autopoietic-loop-has-gaps
  # - "Pattern->Tool: No generative tools exist"
  # - "Tool->Observation: Traces not analyzed"
  # - "Learning->Pattern: Induction not auto-invoked"
  # - Implication: Each gap blocks compound leverage

  # learning-dogfooding-gaps-in-orient
  # - "Orient hardcodes 400 lines of reporting logic"
  # - "Could invoke tools for composition"
  # - Implication: Tool invocations would generate traces for crystallization
