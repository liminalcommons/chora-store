Feature: Cross-Domain Pollination (Experiment 4)
  Test cross-domain pattern transfer: can insights from one domain
  seed patterns in another through metaphorical transfer?

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ════════════════════════════════════════════════════════════════════════════
  # PHASE 1: Manual Bridge Discovery
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Identify semantically similar learnings across domains
    Given learnings exist in domain "testing" about boundaries
    And learnings exist in domain "architecture" about boundaries
    When cross-domain similarity search is performed
    Then candidate pairs are returned with similarity scores
    And candidates span both domains

  Scenario: Create cross-domain bridge learning
    Given a validated cross-domain candidate pair
    When a bridge learning is created with bridge_metadata
    Then the learning has domain starting with "bridge:"
    And the learning has bridge_metadata with source and target domains

  Scenario: Bridge discovery generates potentiative trace
    Given a bridge learning was created
    When the discovery trace is generated
    Then a learning exists with domain "autoevolution-experiment"
    And the learning links to the bridge learning

  # ════════════════════════════════════════════════════════════════════════════
  # PHASE 2: Automated Detection
  # ════════════════════════════════════════════════════════════════════════════

  Scenario: Cross-domain detection is opt-in by default
    Given learnings exist in different domains with similar themes
    When the pattern inductor analyzes without cross_domain flag
    Then no cross-domain proposals are generated
    And only within-domain proposals may exist

  Scenario: Cross-domain proposals are detected when enabled
    Given learnings exist in different domains with similar themes
    When the pattern inductor analyzes with include_cross_domain=true
    Then cross-domain proposals are generated
    And the proposals have cross_domain=true
    And the proposals have source_domains from multiple domains

  Scenario: Cross-domain requires higher similarity threshold
    Given learnings exist with moderate cross-domain similarity
    When the pattern inductor analyzes with include_cross_domain=true
    Then no cross-domain proposals are generated
    And within-domain proposals may still be generated

  Scenario: Cross-domain proposals track lineage when approved
    Given learnings exist in different domains with similar themes
    When the pattern inductor approves a cross-domain proposal
    Then the created pattern has cross_domain=true
    And the created pattern has source_domains set
    And the created pattern has bridge_strength set
