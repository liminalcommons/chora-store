"""
Tests for EntityObserver - Stigmergic coordination.
"""

import pytest
from datetime import datetime

from chora_store.observer import EntityObserver, EntityEvent, ChangeType
from chora_store.models import Entity


def make_entity(id: str = "feature-test") -> Entity:
    """Helper to create test entities."""
    return Entity(
        id=id,
        type="feature",
        status="planned",
        data={"name": "Test"},
    )


class TestEventEmission:
    """Test event emission."""

    def test_emit_create_event(self):
        """Test emitting create event."""
        observer = EntityObserver()
        entity = make_entity()

        event = observer.emit(ChangeType.CREATED, entity)

        assert event.entity_id == entity.id
        assert event.change_type == ChangeType.CREATED
        assert event.new_status == entity.status

    def test_emit_update_event(self):
        """Test emitting update event with old status."""
        observer = EntityObserver()
        entity = make_entity()
        entity = entity.copy(status="in_progress")

        event = observer.emit(ChangeType.UPDATED, entity, old_status="planned")

        assert event.change_type == ChangeType.UPDATED
        assert event.old_status == "planned"
        assert event.new_status == "in_progress"

    def test_emit_delete_event(self):
        """Test emitting delete event."""
        observer = EntityObserver()
        entity = make_entity()

        event = observer.emit(ChangeType.DELETED, entity)

        assert event.change_type == ChangeType.DELETED
        assert event.entity is None  # Deleted entities don't include entity


class TestCallbacks:
    """Test callback registration and invocation."""

    def test_callback_invoked(self):
        """Test that registered callback is invoked."""
        observer = EntityObserver()
        events = []

        observer.on_change(lambda e: events.append(e))
        observer.emit(ChangeType.CREATED, make_entity())

        assert len(events) == 1

    def test_multiple_callbacks(self):
        """Test that multiple callbacks are invoked."""
        observer = EntityObserver()
        results = {"a": 0, "b": 0}

        observer.on_change(lambda e: results.update({"a": results["a"] + 1}))
        observer.on_change(lambda e: results.update({"b": results["b"] + 1}))
        observer.emit(ChangeType.CREATED, make_entity())

        assert results["a"] == 1
        assert results["b"] == 1

    def test_callback_unregister(self):
        """Test unregistering callback."""
        observer = EntityObserver()
        events = []
        callback = lambda e: events.append(e)

        observer.on_change(callback)
        observer.emit(ChangeType.CREATED, make_entity())
        assert len(events) == 1

        observer.off_change(callback)
        observer.emit(ChangeType.CREATED, make_entity())
        assert len(events) == 1  # Still 1, callback not called

    def test_callback_error_doesnt_stop_others(self):
        """Test that callback errors don't stop other callbacks."""
        observer = EntityObserver()
        events = []

        def bad_callback(e):
            raise Exception("Oops")

        observer.on_change(bad_callback)
        observer.on_change(lambda e: events.append(e))

        # Should not raise, should still call second callback
        observer.emit(ChangeType.CREATED, make_entity())
        assert len(events) == 1


class TestEventLog:
    """Test event logging."""

    def test_events_logged(self):
        """Test that events are logged."""
        observer = EntityObserver()

        observer.emit(ChangeType.CREATED, make_entity("feature-test1"))
        observer.emit(ChangeType.UPDATED, make_entity("feature-test2"))

        events = observer.get_recent_events()
        assert len(events) == 2

    def test_filter_by_type(self):
        """Test filtering events by entity type."""
        observer = EntityObserver()

        observer.emit(ChangeType.CREATED, make_entity("feature-test"))
        observer.emit(ChangeType.CREATED, Entity(
            id="pattern-test", type="pattern", status="proposed", data={}
        ))

        feature_events = observer.get_recent_events(entity_type="feature")
        assert len(feature_events) == 1
        assert feature_events[0].entity_type == "feature"

    def test_filter_by_change_type(self):
        """Test filtering events by change type."""
        observer = EntityObserver()

        observer.emit(ChangeType.CREATED, make_entity("feature-test1"))
        observer.emit(ChangeType.UPDATED, make_entity("feature-test2"))

        create_events = observer.get_recent_events(change_type=ChangeType.CREATED)
        assert len(create_events) == 1
        assert create_events[0].change_type == ChangeType.CREATED

    def test_log_limit(self):
        """Test that log respects max size."""
        observer = EntityObserver()
        observer._max_log_size = 5

        for i in range(10):
            observer.emit(ChangeType.CREATED, make_entity(f"feature-test{i}"))

        events = observer.get_recent_events(limit=100)
        assert len(events) == 5  # Only last 5 kept

    def test_clear_log(self):
        """Test clearing the event log."""
        observer = EntityObserver()

        observer.emit(ChangeType.CREATED, make_entity())
        assert len(observer.get_recent_events()) == 1

        observer.clear_log()
        assert len(observer.get_recent_events()) == 0
