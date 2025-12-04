Feature: Perturbation Experiments for Autoevolution
  These experiments test ways to make the autoevolutionary loop
  more generative - discovering more patterns, faster.

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # EXPERIMENT 2: Meta-Loop Pattern (Self-Awareness)
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Patterns created via induction have loop_generation
    Given learnings exist that can cluster into a pattern
    When the pattern inductor approves a proposal
    Then the created pattern has loop_generation set
    And the loop_generation is at least 1

  Scenario: Patterns created via induction have induced_from_count
    Given learnings exist that can cluster into a pattern
    When the pattern inductor approves a proposal
    Then the created pattern has induced_from_count set
    And the induced_from_count matches the source learning count

  Scenario: Loop generation increments across evolutionary cycles
    Given a pattern exists with loop_generation 1
    And learnings are captured about that pattern
    When those learnings cluster and induce a new pattern
    Then the new pattern has loop_generation 2

  # ════════════════════════════════════════════════════════════════════════════
  # EXPERIMENT 3: Automated Induction (Continuous MUTATE)
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Auto-induction tool finds proposals
    Given learnings exist in sufficient quantity to cluster
    When auto_induction is called with auto_approve=false
    Then the report shows proposals found

  Scenario: Auto-induction approves high-confidence proposals
    Given learnings exist that form high-confidence clusters
    When auto_induction is called with confidence_threshold=0.7
    Then patterns are created for proposals above threshold
    And the patterns have loop_generation set

  Scenario: Auto-induction skips low-confidence proposals
    Given learnings exist that form low-confidence clusters
    When auto_induction is called with confidence_threshold=0.9
    Then the report shows proposals skipped
    And no patterns are created

  Scenario: Auto-induction respects max_approvals limit
    Given learnings exist that would generate 5 proposals
    When auto_induction is called with max_approvals=2
    Then at most 2 patterns are created
    And remaining proposals are marked as skipped
