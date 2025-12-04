Feature: Distillation System
  Same-type consolidation of entities. Multiple learnings become one canonical
  learning, multiple inquiries become one canonical inquiry. Source entities
  are marked 'subsumed' with provenance. Un-subsumption is reversible within
  a 30-day window.

  Background:
    Given a fresh repository

  # ═══════════════════════════════════════════════════════════════════════════
  # Learning Distillation
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Find learning distillation candidates
    Given multiple learnings with similar insights about "testing patterns"
    When distillation candidates are found for "learning"
    Then at least one candidate cluster is returned
    And the candidate has confidence above 0.5

  Scenario: Apply learning distillation
    Given a distillation proposal for learnings
    When the distillation is applied
    Then a canonical learning is created with "subsumes" array
    And source learnings have status "subsumed"
    And source learnings have "subsumed_by" set to canonical ID
    And source learnings have "prior_status" stored

  # ═══════════════════════════════════════════════════════════════════════════
  # Inquiry Distillation
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Find inquiry distillation candidates using core_concern
    Given multiple inquiries with similar core_concerns about "agent awareness"
    When distillation candidates are found for "inquiry"
    Then at least one candidate cluster is returned
    And the candidate sources include core_concern in LLM context

  Scenario: Apply inquiry distillation merges terrain
    Given a distillation proposal for inquiries with terrain
    When the distillation is applied
    Then a canonical inquiry is created
    And the canonical has merged terrain from sources

  # ═══════════════════════════════════════════════════════════════════════════
  # Feature Distillation
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Find feature distillation candidates using description and problem
    Given multiple features with similar descriptions about "validation"
    When distillation candidates are found for "feature"
    Then at least one candidate cluster is returned
    And the candidate sources include description in LLM context

  Scenario: Apply feature distillation merges requirements and behaviors
    Given a distillation proposal for features with requirements
    When the distillation is applied
    Then a canonical feature is created
    And the canonical has merged requirements from sources
    And the canonical has merged behaviors from sources

  Scenario: Feature distillation uses higher threshold
    Given multiple features with moderate similarity
    When distillation is attempted with threshold 0.70
    Then features below threshold are not clustered

  # ═══════════════════════════════════════════════════════════════════════════
  # Pattern Distillation
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Find pattern distillation candidates using problem and solution
    Given multiple patterns with similar problems about "governance"
    When distillation candidates are found for "pattern"
    Then at least one candidate cluster is returned
    And the candidate sources include problem and solution in LLM context

  Scenario: Pattern distillation only clusters same subtype
    Given patterns with subtype "meta" and patterns with subtype "architectural"
    When distillation candidates are found for "pattern"
    Then candidates only contain same-subtype patterns
    And no cluster mixes subtypes

  Scenario: Apply pattern distillation preserves mechanics from primary source
    Given a distillation proposal for patterns with mechanics
    When the distillation is applied
    Then a canonical pattern is created
    And the canonical has mechanics from primary source only
    And mechanics are not merged from other sources

  Scenario: Pattern distillation uses highest threshold
    Given multiple patterns with moderate similarity
    When distillation is attempted with threshold 0.75
    Then patterns below threshold are not clustered

  # ═══════════════════════════════════════════════════════════════════════════
  # Un-subsumption (Reversibility)
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Un-subsume within window restores entity
    Given a subsumed learning within the 30-day window
    When unsubsume is called on the entity
    Then the entity status is restored to "captured"
    And "subsumed_by" is removed
    And the canonical's subsumes array is updated

  Scenario: Un-subsume after window is blocked
    Given a subsumed learning beyond the 30-day window
    When unsubsume is called on the entity
    Then the operation fails with "permanent" message
    And the entity remains subsumed

  Scenario: Un-subsume all from canonical
    Given a canonical with 3 subsumed sources
    When unsubsume_all is called on the canonical
    Then all sources are restored
    And the canonical is marked as "drifting"

  # ═══════════════════════════════════════════════════════════════════════════
  # Bulk Distillation
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Bulk distillation groups by domain
    Given learnings in domains "metabolic" and "epigenetic"
    When bulk distillation is called with group_by "domain"
    Then proposals are returned per domain
    And each domain's candidates only contain entities from that domain

  # ═══════════════════════════════════════════════════════════════════════════
  # Edge Cases
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Subsumed entities are excluded from candidates
    Given a subsumed learning
    And a non-subsumed learning
    When distillation candidates are found for "learning"
    Then the subsumed learning is not in any candidate

  Scenario: Un-subsume with missing prior_status uses type default
    Given a subsumed learning without prior_status field
    When unsubsume is called on the entity
    Then the entity status is restored to "captured"

  # ═══════════════════════════════════════════════════════════════════════════
  # Cross-Domain Bridge Detection
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Cross-domain bridges are detected when enabled
    Given learnings in domain "metabolic" about "trace crystallization"
    And learnings in domain "epigenetic" about "trace crystallization"
    When pattern induction is run with cross_domain enabled
    Then a cross-domain bridge proposal is returned
    And the bridge has source_domains including both domains
    And the bridge has bridge_strength above 0.5

  Scenario: Cross-domain bridges are not detected when disabled
    Given learnings in domain "metabolic" about "trace crystallization"
    And learnings in domain "epigenetic" about "trace crystallization"
    When pattern induction is run with cross_domain disabled
    Then no cross-domain bridge proposals are returned

  Scenario: Cross-domain bridge requires semantic similarity
    Given learnings in domain "metabolic" about "trace crystallization"
    And learnings in domain "security" about "authentication tokens"
    When pattern induction is run with cross_domain enabled
    Then no bridge is formed between unrelated domains
