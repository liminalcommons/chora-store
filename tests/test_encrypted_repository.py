"""
Tests for EncryptedEntityRepository.
"""

import pytest
import tempfile
import os
import sys

# Add chora-crypto to path for testing
crypto_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "chora-crypto", "src"
)
if os.path.exists(crypto_path):
    sys.path.insert(0, crypto_path)

from chora_store.repository import EntityRepository
from chora_store.models import Entity

# Try to import encryption components
try:
    from chora_store.encrypted_repository import (
        EncryptedEntityRepository,
        EncryptionNotAvailable,
        CRYPTO_AVAILABLE,
    )
    from chora_crypto import (
        derive_master_key,
        derive_workspace_key,
        generate_workspace_key,
    )
except ImportError:
    CRYPTO_AVAILABLE = False


# Skip all tests if crypto not available
pytestmark = pytest.mark.skipif(
    not CRYPTO_AVAILABLE,
    reason="chora-crypto not available"
)


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def workspace_key():
    """Generate a workspace key for testing."""
    return generate_workspace_key("test-workspace")


@pytest.fixture
def repo(temp_db):
    """Create base repository."""
    return EntityRepository(db_path=temp_db)


@pytest.fixture
def encrypted_repo(repo, workspace_key):
    """Create encrypted repository."""
    return EncryptedEntityRepository(repo, workspace_key)


def make_entity(id: str = "feature-test", **kwargs) -> Entity:
    """Helper to create test entities."""
    defaults = {
        "type": "feature",
        "status": "planned",
        "data": {"name": "Test Feature", "description": "A test feature", "secret": "sensitive-data"},
    }
    defaults.update(kwargs)
    return Entity(id=id, **defaults)


class TestEncryptedCRUD:
    """Test encrypted CRUD operations."""

    def test_create_encrypts_data(self, encrypted_repo, repo):
        """Data is encrypted when stored."""
        entity = make_entity()
        created = encrypted_repo.create(entity)

        # Check returned entity has decrypted data
        assert created.data["secret"] == "sensitive-data"

        # Check raw storage is encrypted
        raw = repo.read(entity.id)
        assert "_encrypted" in raw.data
        assert "sensitive-data" not in str(raw.data)

    def test_read_decrypts_data(self, encrypted_repo):
        """Data is decrypted when read."""
        entity = make_entity()
        encrypted_repo.create(entity)

        read = encrypted_repo.read(entity.id)
        assert read.data["secret"] == "sensitive-data"
        assert read.data["name"] == "Test Feature"

    def test_update_encrypts_data(self, encrypted_repo, repo):
        """Updated data is encrypted."""
        entity = make_entity()
        created = encrypted_repo.create(entity)

        updated = encrypted_repo.update(
            created.copy(data={"name": "Updated", "new_secret": "new-sensitive"})
        )

        # Returned entity has decrypted data
        assert updated.data["new_secret"] == "new-sensitive"

        # Raw storage is encrypted
        raw = repo.read(entity.id)
        assert "_encrypted" in raw.data
        assert "new-sensitive" not in str(raw.data)

    def test_delete(self, encrypted_repo):
        """Delete works normally."""
        entity = make_entity()
        encrypted_repo.create(entity)

        result = encrypted_repo.delete(entity.id)
        assert result is True

        assert encrypted_repo.read(entity.id) is None

    def test_list_decrypts_all(self, encrypted_repo):
        """List returns decrypted entities."""
        encrypted_repo.create(make_entity("feature-one", data={"secret": "one"}))
        encrypted_repo.create(make_entity("feature-two", data={"secret": "two"}))

        entities = encrypted_repo.list()
        assert len(entities) == 2

        secrets = {e.data.get("secret") for e in entities}
        assert secrets == {"one", "two"}


class TestMetadataQueryable:
    """Test that metadata remains queryable."""

    def test_list_by_type(self, encrypted_repo):
        """Can filter by type (not encrypted)."""
        encrypted_repo.create(make_entity("feature-one", type="feature"))
        encrypted_repo.create(Entity(
            id="pattern-one",
            type="pattern",
            status="proposed",
            data={"name": "Test Pattern"},
        ))

        features = encrypted_repo.list(entity_type="feature")
        assert len(features) == 1
        assert features[0].type == "feature"

    def test_list_by_status(self, encrypted_repo):
        """Can filter by status (not encrypted)."""
        encrypted_repo.create(make_entity("feature-one", status="planned"))
        encrypted_repo.create(make_entity("feature-two", status="in_progress"))

        planned = encrypted_repo.list(status="planned")
        assert len(planned) == 1
        assert planned[0].status == "planned"


class TestDifferentKeys:
    """Test encryption with different keys."""

    def test_wrong_key_fails(self, repo, workspace_key):
        """Cannot decrypt with wrong key."""
        from chora_crypto import DecryptionError

        # Create with one key
        encrypted_repo1 = EncryptedEntityRepository(repo, workspace_key)
        encrypted_repo1.create(make_entity())

        # Try to read with different key
        other_key = generate_workspace_key("other-workspace")
        encrypted_repo2 = EncryptedEntityRepository(repo, other_key)

        with pytest.raises(DecryptionError):
            encrypted_repo2.read("feature-test")

    def test_derived_key_works(self, repo):
        """Can use key derived from password."""
        master_key, salt = derive_master_key("test-password")
        workspace_key = derive_workspace_key(master_key, "my-workspace")

        encrypted_repo = EncryptedEntityRepository(repo, workspace_key)

        entity = make_entity()
        encrypted_repo.create(entity)

        read = encrypted_repo.read(entity.id)
        assert read.data["secret"] == "sensitive-data"


class TestVersionTracking:
    """Test that version tracking works with encryption."""

    def test_changes_decrypted(self, encrypted_repo):
        """get_changes_since returns decrypted entities."""
        entity = make_entity()
        encrypted_repo.create(entity)
        encrypted_repo.update(entity.copy(
            data={"name": "Updated", "secret": "updated-secret"},
            version=1,
        ))

        changes = encrypted_repo.get_changes_since(0)
        assert len(changes) >= 2

        # All changes should have decrypted data
        for entity, change_type in changes:
            assert "_encrypted" not in entity.data


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_data(self, encrypted_repo):
        """Can encrypt/decrypt empty data."""
        entity = make_entity(data={})
        created = encrypted_repo.create(entity)
        assert created.data == {}

        read = encrypted_repo.read(entity.id)
        assert read.data == {}

    def test_nested_data(self, encrypted_repo):
        """Can encrypt/decrypt nested data structures."""
        nested_data = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"],
                    "secret": "deep-secret",
                },
            },
            "list": [1, 2, {"nested": "value"}],
        }

        entity = make_entity(data=nested_data)
        encrypted_repo.create(entity)

        read = encrypted_repo.read(entity.id)
        assert read.data["level1"]["level2"]["secret"] == "deep-secret"
        assert read.data["list"][2]["nested"] == "value"

    def test_unicode_data(self, encrypted_repo):
        """Can encrypt/decrypt unicode data."""
        unicode_data = {
            "emoji": "🔐🚀",
            "chinese": "中文数据",
            "arabic": "بيانات عربية",
        }

        entity = make_entity(data=unicode_data)
        encrypted_repo.create(entity)

        read = encrypted_repo.read(entity.id)
        assert read.data["emoji"] == "🔐🚀"
        assert read.data["chinese"] == "中文数据"
