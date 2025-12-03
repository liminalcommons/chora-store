Feature: Focus as Stigmergic Coordination
  Enable agents to coordinate through focus marks - stigmergic signals
  that communicate what attention has settled on, what emerged during
  focus, and what led there.

  Background:
    Given a fresh repository

  # ═══════════════════════════════════════════════════════════════════════════════
  # FOCUS CREATION
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Focus created on commit
    Given an agent in constellation phase with awareness candidates
    When agent commits attention to an entity
    Then a focus is created with target and started_at timestamp

  Scenario: Focus captures provenance
    Given an agent committing focus from an inquiry
    When focus is created
    Then focus provenance links to the source inquiry

  # ═══════════════════════════════════════════════════════════════════════════════
  # FOCUS SURFACING (ORIENT)
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Orient surfaces unfinalized foci
    Given multiple foci exist with different statuses
    When agent runs orient
    Then only unfinalized foci are surfaced as awareness candidates

  Scenario: Orient shows other agent focus
    Given agent A has open focus on entity X
    When agent B runs orient
    Then agent B sees agent A's focus on X

  # ═══════════════════════════════════════════════════════════════════════════════
  # FOCUS LIFECYCLE
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Focus becomes stale after TTL
    Given an open focus with TTL configured
    When TTL duration passes without cycling
    Then focus transitions to stale status

  Scenario: Focus closed on attention shift
    Given an open focus on entity X
    When agent commits focus to different entity Y
    Then focus on X is closed and focus on Y is opened

  Scenario: Finalization harvests trail
    Given a focus with accumulated trail
    When focus is finalized
    Then trail is harvested and focus is archived

  # ═══════════════════════════════════════════════════════════════════════════════
  # FOCUS AS CONTAINER
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Learning links to active focus
    Given an open focus on inquiry X
    When learning is created during focused work
    Then learning links to the active focus

  Scenario: Trail accumulates during focus
    Given an open focus
    When agent touches entities during work
    Then touched entities are recorded in focus trail

  # ═══════════════════════════════════════════════════════════════════════════════
  # STIGMERGIC COORDINATION
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Focus mark persists across sessions
    Given a focus with trail and provenance
    When session ends
    Then focus mark persists in shared substrate

  Scenario: Focus is recoverable by new agent
    Given a previous session's focus mark exists
    When new agent orients and requests recovery
    Then agent can resume with target trail and provenance

  # ═══════════════════════════════════════════════════════════════════════════════
  # CLOSURE BY TARGET TYPE
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Inquiry focus can reopen naturally
    Given a closed focus on an inquiry
    When agent reopens focus on same inquiry
    Then new focus is created linked to prior focus

  Scenario: Goal reopen signals inquiry in disguise
    Given a closed focus on a goal that was closed by condition
    When focus is reopened on same goal
    Then system signals potential inquiry in disguise
