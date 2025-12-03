Feature: Capability System
  The 7th Noun (Tool/Field). Dynamic capabilities exposed to agents via hot-reload.
  Tools are entities with handlers that can be invoked.

  Background:
    Given a fresh repository

  Scenario: Tools are queryable
    Given tool entities exist in the repository
    When repository.list(entity_type=tool) is called
    Then all registered tools are returned

  Scenario: Tool has handler structure
    Given a tool entity
    When tool data is inspected
    Then handler with type "llm" or "reference" or "compose" is present

  Scenario: Tool hot reload
    Given the repository has some tools
    When a new tool entity is created
    Then the tool is immediately available via list

  Scenario: Tool is invocable
    Given an active tool with handler
    When the tool is retrieved
    Then handler is present and tool can be invoked
