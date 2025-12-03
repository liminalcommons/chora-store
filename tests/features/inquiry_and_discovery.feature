Feature: Inquiry and Discovery
  The spark-to-structure pathway. Inquiries hold questions until intent
  crystallizes into features. Discovery tools ensure "search before create" pattern.

  Background:
    Given a fresh repository

  Scenario: Inquiry creation
    Given a spark "What if we could automate testing?"
    When Factory.create(inquiry, title) is called
    Then an inquiry entity exists with status "active"

  Scenario: Inquiry resolution
    Given an active inquiry
    When the exploration reaches conclusion
    Then the inquiry can transition to "resolved" status

  Scenario: Inquiry reification
    Given an active inquiry with clear intent
    When the inquiry is reified
    Then the inquiry status is "reified"
    And a feature can be created with origin link to the inquiry

  Scenario: Discovery tool available
    Given an agent considering creating a new entity
    When tools are queried
    Then a discover tool exists and is active
