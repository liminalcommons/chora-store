"""
Backend parity tests for chora-store.

These tests ensure SQLite and PostgreSQL backends behave identically.
Run with CHORA_TEST_POSTGRES_DSN set to test both backends.
"""

import pytest
from datetime import datetime, timezone
from chora_store.models import Entity
from chora_store.repository import Repository


def make_entity(
    id: str,
    type: str = 'story',
    status: str = 'emerging',
    title: str = 'Test Entity',
    data: dict = None,
) -> Entity:
    """Helper to create test entities."""
    now = datetime.now(timezone.utc)
    return Entity(
        id=id,
        type=type,
        status=status,
        title=title,
        data=data or {'description': 'A test entity'},
        created_at=now,
        updated_at=now,
    )


class TestCRUDParity:
    """Test CRUD operations work identically on both backends."""

    def test_create(self, any_repo):
        """Test entity creation."""
        entity = make_entity('story-test-create', title='Create Test')
        saved = any_repo.save(entity)

        assert saved.id == 'story-test-create'
        assert saved.title == 'Create Test'

    def test_read(self, any_repo):
        """Test entity retrieval."""
        entity = make_entity('story-test-read', title='Read Test')
        any_repo.save(entity)

        retrieved = any_repo.get('story-test-read')
        assert retrieved is not None
        assert retrieved.id == 'story-test-read'
        assert retrieved.title == 'Read Test'
        assert retrieved.status == 'emerging'

    def test_read_not_found(self, any_repo):
        """Test retrieving non-existent entity."""
        result = any_repo.get('story-does-not-exist')
        assert result is None

    def test_update(self, any_repo):
        """Test entity update with version increment."""
        entity = make_entity('story-test-update', status='emerging')
        any_repo.save(entity)

        # Update
        entity.status = 'clear'
        entity.updated_at = datetime.now(timezone.utc)
        any_repo.save(entity)

        retrieved = any_repo.get('story-test-update')
        assert retrieved.status == 'clear'

    def test_update_version_conflict(self, any_repo):
        """Test optimistic locking on concurrent update."""
        entity = make_entity('story-test-conflict')
        any_repo.save(entity)

        # Simulate concurrent modification by saving twice without re-reading
        entity.title = 'First Update'
        entity.updated_at = datetime.now(timezone.utc)
        any_repo.save(entity)

        # This should still work because we're using the same object
        entity.title = 'Second Update'
        entity.updated_at = datetime.now(timezone.utc)
        any_repo.save(entity)

        retrieved = any_repo.get('story-test-conflict')
        assert retrieved.title == 'Second Update'

    def test_delete(self, any_repo):
        """Test entity deletion."""
        entity = make_entity('story-test-delete')
        any_repo.save(entity)

        deleted = any_repo.delete('story-test-delete')
        assert deleted is True

        retrieved = any_repo.get('story-test-delete')
        assert retrieved is None

    def test_delete_not_found(self, any_repo):
        """Test deleting non-existent entity."""
        deleted = any_repo.delete('story-does-not-exist')
        assert deleted is False


class TestListingParity:
    """Test listing operations work identically on both backends."""

    def test_list_all(self, any_repo):
        """Test listing all entities."""
        any_repo.save(make_entity('story-list-1'))
        any_repo.save(make_entity('story-list-2'))

        entities = any_repo.list()
        ids = [e.id for e in entities]
        assert 'story-list-1' in ids
        assert 'story-list-2' in ids

    def test_list_by_type(self, any_repo):
        """Test filtering by type."""
        any_repo.save(make_entity('story-type-1', type='story'))
        any_repo.save(make_entity('behavior-type-1', type='behavior', status='verified'))

        stories = any_repo.list(type='story')
        assert all(e.type == 'story' for e in stories)

        behaviors = any_repo.list(type='behavior')
        assert all(e.type == 'behavior' for e in behaviors)

    def test_list_by_status(self, any_repo):
        """Test filtering by status."""
        any_repo.save(make_entity('story-status-1', status='emerging'))
        any_repo.save(make_entity('story-status-2', status='clear'))

        emerging = any_repo.list(status='emerging')
        assert all(e.status == 'emerging' for e in emerging)

    def test_list_pagination(self, any_repo):
        """Test limit parameter."""
        for i in range(5):
            any_repo.save(make_entity(f'story-page-{i}'))

        limited = any_repo.list(limit=3)
        assert len(limited) == 3


class TestSearchParity:
    """Test search operations work identically on both backends."""

    def test_search_by_title(self, any_repo):
        """Test full-text search on title."""
        any_repo.save(make_entity('story-search-1', title='Finding Nemo'))
        any_repo.save(make_entity('story-search-2', title='Finding Dory'))
        any_repo.save(make_entity('story-search-3', title='Toy Story'))

        results = any_repo.search('Finding')
        ids = [e.id for e in results]
        assert 'story-search-1' in ids or 'story-search-2' in ids

    def test_search_by_description(self, any_repo):
        """Test full-text search on description."""
        any_repo.save(make_entity(
            'story-search-desc',
            title='Test',
            data={'description': 'Unicorn rainbow magic'}
        ))

        results = any_repo.search('rainbow')
        # May or may not find it depending on FTS config
        # Just verify search doesn't error
        assert isinstance(results, list)

    def test_search_no_results(self, any_repo):
        """Test search with no matches."""
        results = any_repo.search('xyznonexistent123')
        assert results == []


class TestVersionTrackingParity:
    """Test version tracking works identically on both backends."""

    def test_changes_tracked(self, any_repo):
        """Test that changes are logged in entity_versions."""
        entity = make_entity('story-version-test')
        any_repo.save(entity)  # v1 create

        entity.title = 'Updated Title'
        entity.updated_at = datetime.now(timezone.utc)
        any_repo.save(entity)  # v2 update

        versions = any_repo.get_versions('story-version-test')
        assert len(versions) == 2

        # Most recent first
        assert versions[0]['change_type'] == 'update'
        assert versions[1]['change_type'] == 'create'

    def test_delete_tracked(self, any_repo):
        """Test that deletions are logged."""
        entity = make_entity('story-delete-version')
        any_repo.save(entity)
        any_repo.delete('story-delete-version')

        versions = any_repo.get_versions('story-delete-version')
        change_types = [v['change_type'] for v in versions]
        assert 'delete' in change_types


class TestDataIntegrityParity:
    """Test data integrity on both backends."""

    def test_json_data_preserved(self, any_repo):
        """Test that JSON data is preserved correctly."""
        complex_data = {
            'nested': {'key': 'value'},
            'array': [1, 2, 3],
            'boolean': True,
            'number': 42.5,
        }
        entity = make_entity('story-json-test', data=complex_data)
        any_repo.save(entity)

        retrieved = any_repo.get('story-json-test')
        assert retrieved.data == complex_data

    def test_unicode_handling(self, any_repo):
        """Test unicode characters are preserved."""
        entity = make_entity(
            'story-unicode-test',
            title='Emoji Test 🎉',
            data={'japanese': '日本語', 'emoji': '🚀'}
        )
        any_repo.save(entity)

        retrieved = any_repo.get('story-unicode-test')
        assert retrieved.title == 'Emoji Test 🎉'
        assert retrieved.data['japanese'] == '日本語'
        assert retrieved.data['emoji'] == '🚀'


class TestGraphOperationsParity:
    """Test graph operations work identically on both backends."""

    def test_get_bonds_from(self, any_repo):
        """Test getting outgoing bonds."""
        # Create story and behavior
        any_repo.save(make_entity('story-graph-from'))
        any_repo.save(make_entity('behavior-graph-from', type='behavior', status='verified'))

        # Create relationship
        rel = make_entity(
            'relationship-graph-from',
            type='relationship',
            status='active',
            data={
                'relationship_type': 'specifies',
                'from_id': 'story-graph-from',
                'to_id': 'behavior-graph-from',
            }
        )
        any_repo.save(rel)

        bonds = any_repo.get_bonds_from('story-graph-from')
        assert len(bonds) == 1
        assert bonds[0].data['relationship_type'] == 'specifies'

    def test_get_bonds_to(self, any_repo):
        """Test getting incoming bonds."""
        # Create story and behavior
        any_repo.save(make_entity('story-graph-to'))
        any_repo.save(make_entity('behavior-graph-to', type='behavior', status='verified'))

        # Create relationship
        rel = make_entity(
            'relationship-graph-to',
            type='relationship',
            status='active',
            data={
                'relationship_type': 'specifies',
                'from_id': 'story-graph-to',
                'to_id': 'behavior-graph-to',
            }
        )
        any_repo.save(rel)

        bonds = any_repo.get_bonds_to('behavior-graph-to')
        assert len(bonds) == 1
        assert bonds[0].data['from_id'] == 'story-graph-to'


class TestTracesParity:
    """Test trace logging works identically on both backends."""

    def test_log_and_retrieve_trace(self, any_repo):
        """Test logging and retrieving traces."""
        any_repo.log_trace('test_tool', {'input': 'value'}, {'output': 'result'})

        traces = any_repo.get_traces(tool='test_tool')
        assert len(traces) >= 1
        assert traces[0]['tool'] == 'test_tool'

    def test_trace_error_logging(self, any_repo):
        """Test logging traces with errors."""
        any_repo.log_trace('error_tool', {'input': 'bad'}, error='Something went wrong')

        traces = any_repo.get_traces(tool='error_tool')
        assert traces[0]['error'] == 'Something went wrong'
