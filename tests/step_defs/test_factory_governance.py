"""
Step definitions for factory_governance.feature
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.models import Entity, ValidationError

# Load scenarios from feature file
scenarios('../features/factory_governance.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given(parsers.parse('an entity with ID "{entity_id}" exists'))
def entity_exists(factory, context, entity_id):
    """Create an entity with specific ID."""
    feature = factory.create('feature', 'Test')
    context['existing_id'] = feature.id


@given('a feature in status "nascent"')
def feature_nascent(factory, context):
    """Create a nascent feature."""
    feature = factory.create('feature', 'Nascent Feature')
    context['feature'] = feature
    context['feature_id'] = feature.id


@given('a feature in status "converging" with no behaviors')
def feature_converging_no_behaviors(factory, context):
    """Create converging feature without behaviors."""
    feature = factory.create('feature', 'No Behaviors')
    # Transition to converging
    updated = factory.update(feature.id, status='converging')
    context['feature'] = updated
    context['feature_id'] = updated.id


@given('a feature and inquiry exist')
def feature_and_inquiry(factory, context):
    """Create both feature and inquiry."""
    inquiry = factory.create('inquiry', 'Test Inquiry', spark='Why?')
    feature = factory.create('feature', 'Linkable Feature')
    context['inquiry'] = inquiry
    context['feature'] = feature


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when(parsers.parse('Factory.create is called with type "{entity_type}"'))
def create_invalid_type(factory, context, entity_type):
    """Try to create entity with invalid type."""
    try:
        factory.create(entity_type, 'Test')
        context['error'] = None
    except (ValidationError, ValueError, KeyError) as e:
        context['error'] = e


@when(parsers.parse('Factory.create is called with status "{status}"'))
def create_invalid_status(factory, context, status):
    """Try to create entity with invalid status."""
    try:
        factory.create('feature', 'Test', status=status)
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when('Factory.create("feature", "Voice Canvas") is called')
def create_voice_canvas(factory, context):
    """Create feature with specific title."""
    feature = factory.create('feature', 'Voice Canvas')
    context['created'] = feature


@when('Factory.create("feature", "Test") is called')
def create_test_feature(factory, context):
    """Try to create feature named Test."""
    try:
        feature = factory.create('feature', 'Test')
        context['created'] = feature
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when('transition to "stable" is attempted')
def transition_to_stable(factory, context):
    """Attempt transition to stable."""
    try:
        factory.update(context['feature_id'], status='stable')
        context['error'] = None
    except ValidationError as e:
        context['error'] = e


@when('Factory.create("feature", "Standalone Feature") is called')
def create_standalone(factory, context):
    """Create feature without origin."""
    feature = factory.create('feature', 'Standalone Feature')
    context['created'] = feature


@when('origin link is added to feature')
def add_origin_link(factory, context):
    """Link feature to inquiry."""
    feature = context['feature']
    inquiry = context['inquiry']
    updated = factory.update(feature.id, origin=inquiry.id)
    context['updated'] = updated


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('ValidationError is raised for invalid type')
def error_invalid_type(context):
    """Verify error for invalid type."""
    assert context['error'] is not None, "Expected error for invalid type"


@then('ValidationError is raised for invalid status')
def error_invalid_status(context):
    """Verify error for invalid status."""
    assert context['error'] is not None, "Expected error for invalid status"


@then('entity ID is "feature-voice-canvas"')
def verify_semantic_id(context):
    """Verify semantic ID generation."""
    assert context['created'].id == 'feature-voice-canvas'


@then('ValidationError is raised for duplicate ID')
def error_duplicate_id(context):
    """Verify error for duplicate ID."""
    assert context['error'] is not None, "Expected error for duplicate ID"


@then('ValidationError is raised for skipping converging')
def error_skip_converging(context):
    """Verify error for skipping converging status."""
    assert context['error'] is not None, "Expected error for skipping converging"


@then('ValidationError is raised for missing behaviors')
def error_missing_behaviors(context):
    """Verify error for missing behaviors."""
    assert context['error'] is not None, "Expected error for missing behaviors"


@then('feature is created successfully')
def feature_created(context):
    """Verify feature was created."""
    assert context['created'] is not None
    assert context['created'].type == 'feature'


@then('feature.data.origin equals inquiry ID')
def verify_origin_link(context):
    """Verify origin link was added."""
    updated = context['updated']
    inquiry = context['inquiry']
    assert updated.data.get('origin') == inquiry.id
