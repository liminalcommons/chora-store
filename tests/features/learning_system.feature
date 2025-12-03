Feature: Learning System
  The wisdom accumulation pathway. Learnings capture insights from experience
  and can crystallize into patterns through induction.

  Background:
    Given a fresh repository

  Scenario: Learning capture
    Given an insight "Testing is important for quality"
    When Factory.create(learning, title, insight) is called
    Then a learning entity exists with status "captured"

  Scenario: Learning validation
    Given a captured learning
    When the learning is reviewed and confirmed useful
    Then the learning can transition to "validated" status

  Scenario: Learning application
    Given a validated learning
    When the learning is incorporated into practice
    Then the learning transitions to "applied" status

  Scenario: Learning to pattern induction
    Given multiple validated learnings with common themes
    When PatternInductor.analyze() is called
    Then pattern proposals can be generated
