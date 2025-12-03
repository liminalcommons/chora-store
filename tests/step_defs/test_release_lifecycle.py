"""
Step definitions for release_lifecycle.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load scenarios from feature file
scenarios('../features/release_lifecycle.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given(parsers.parse('a version identifier "{version}"'))
def version_identifier(context, version):
    """Store version for later use."""
    context['version'] = version


@given('a planned release')
def planned_release(factory, context):
    """Create a planned release."""
    release = factory.create('release', 'Test Release', version='v0.1.0')
    context['release'] = release
    assert release.status == 'planned'


@given('a planned release with features')
def planned_release_with_features(factory, context):
    """Create a planned release with features."""
    release = factory.create('release', 'Bundle Release', version='v0.2.0')

    # Add features
    entity = factory.repository.read(release.id)
    entity.data['features'] = ['feature-a', 'feature-b']
    factory.repository.update(entity)

    context['release'] = factory.repository.read(release.id)


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('Factory.create(release, title, version) is called')
def create_release(factory, context):
    """Create a release with the stored version."""
    version = context.get('version', 'v0.0.1')
    release = factory.create('release', 'Test Release', version=version)
    context['release'] = release


@when('features are added to the release')
def add_features_to_release(factory, context):
    """Add features to the release."""
    release = context['release']
    entity = factory.repository.read(release.id)
    entity.data['features'] = ['feature-x', 'feature-y', 'feature-z']
    factory.repository.update(entity)
    context['release'] = factory.repository.read(release.id)


@when(parsers.parse('the release transitions to "{status}" status'))
def transition_release(factory, context, status):
    """Transition release to new status."""
    release = context['release']
    context['release'] = factory.update(release.id, status=status)


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then(parsers.parse('a release entity exists with status "{status}"'))
def release_exists_with_status(context, status):
    """Verify release exists with expected status."""
    release = context['release']
    assert release is not None
    assert release.type == 'release'
    assert release.status == status


@then('the release has the specified version')
def release_has_version(context):
    """Verify release has the specified version."""
    release = context['release']
    expected_version = context.get('version')
    assert release.data.get('version') == expected_version


@then('Release.features contains the bundled feature IDs')
def release_contains_features(context):
    """Verify release contains bundled features."""
    release = context['release']
    assert 'features' in release.data
    assert len(release.data['features']) > 0


@then(parsers.parse('the release status is "{status}"'))
def release_status_is(context, status):
    """Verify release has expected status."""
    release = context['release']
    assert release.status == status
