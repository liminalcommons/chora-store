Feature: Cron Hooks for Automated Maintenance
  The system needs periodic maintenance tasks that agents can trigger.
  This includes auto-induction (clustering learnings into patterns) and
  feature TTL checking (flagging stale nascent features).

  Background:
    Given a fresh repository
    And a factory with epigenetic support

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 1: Daily Cron Firing
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Daily cron fires registered actions
    When the daily cron is fired
    Then auto_induction action executes
    And feature_ttl_check action executes

  Scenario: Daily cron returns list of executed actions
    When the daily cron is fired
    Then the result contains "auto_induction"
    And the result contains "feature_ttl_check"

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 2: Feature TTL Check
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Feature within TTL is not flagged
    Given a nascent feature "feature-fresh" created 5 days ago with TTL 30 days
    When the daily cron is fired
    Then feature "feature-fresh" has no drift signals

  Scenario: Feature past TTL is flagged for drift
    Given a nascent feature "feature-stale" created 40 days ago with TTL 30 days
    When the daily cron is fired
    Then feature "feature-stale" has drift signal "ttl_expired"

  Scenario: Already flagged feature is not re-flagged
    Given a nascent feature "feature-already-stale" created 40 days ago with TTL 30 days
    And feature "feature-already-stale" has drift signal "ttl_expired"
    When the daily cron is fired
    Then feature "feature-already-stale" has exactly 1 "ttl_expired" signal

  # ═══════════════════════════════════════════════════════════════════════════════
  # PHASE 3: Auto-Induction Integration
  # ═══════════════════════════════════════════════════════════════════════════════

  Scenario: Auto-induction runs without error on empty repository
    When the daily cron is fired
    Then auto_induction completes successfully

  Scenario: Auto-induction respects default thresholds
    Given 5 learnings exist in domain "test-cron"
    When the daily cron is fired
    Then auto_induction analyzes learnings
