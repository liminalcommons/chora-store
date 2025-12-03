Feature: Release Lifecycle
  The bundling and shipping pathway. Releases are versioned milestones
  that bundle stable features into coherent shipments.

  Background:
    Given a fresh repository

  Scenario: Release creation
    Given a version identifier "v1.0.0"
    When Factory.create(release, title, version) is called
    Then a release entity exists with status "planned"
    And the release has the specified version

  Scenario: Release bundling
    Given a planned release
    When features are added to the release
    Then Release.features contains the bundled feature IDs

  Scenario: Release shipping
    Given a planned release with features
    When the release transitions to "released" status
    Then the release status is "released"
