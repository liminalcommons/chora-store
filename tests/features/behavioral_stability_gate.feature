Feature: Behavioral Stability Gate
  Features cannot transition to stable without passing behaviors.
  This ensures behavioral coverage before stability is claimed.

  Background:
    Given a fresh repository

  Scenario: Converging with no behaviors blocks stable
    Given a feature in converging status with no behaviors
    When transition to stable is attempted
    Then ValidationError is raised about behaviors required

  Scenario: Converging with untested behaviors blocks stable
    Given a feature in converging status with untested behaviors
    When transition to stable is attempted
    Then ValidationError is raised listing non-passing behaviors

  Scenario: Converging with all passing behaviors allows stable
    Given a feature in converging status with all behaviors passing
    When transition to stable is attempted
    Then transition succeeds and feature is stable

  Scenario: Stable feature with failing behavior emits drift
    Given a stable feature
    When a behavior is marked as failing
    Then a drift signal event is emitted
