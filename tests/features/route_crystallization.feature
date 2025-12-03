Feature: Route Crystallization
  The Push-Right principle in action: inference traces crystallize into routes.

  Background:
    Given a fresh database

  Scenario: Traces crystallize into route
    Given 5 similar inference traces for the same input
    When auto_crystallize is called
    Then a route is created with status "canary"
    And the route stores the consistent output

  Scenario: Route promotes after hits
    Given a canary route with 10 successful hits
    When promote_route is called
    Then route status is "active"

  Scenario: Route deprecates on high miss rate
    Given an active route
    When 4 of 10 lookups are misses
    Then route status is "deprecated"

  Scenario: Route lookup bypasses inference
    Given a crystallized active route for synthesis
    And learnings that match the route input
    When tiered_synthesize is called
    Then resolution uses data tier
    And the route hit count increases

  Scenario: Routes track source learning IDs
    Given 5 similar inference traces for learnings "learning-a" and "learning-b"
    When auto_crystallize is called
    Then the crystallized route has source_learning_ids containing "learning-a"
    And the crystallized route has source_learning_ids containing "learning-b"
