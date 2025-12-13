"""
Encrypted Entity Repository - encryption layer for chora-store.

Wraps EntityRepository to provide transparent encryption of entity data.
Metadata (id, type, status) remains queryable; sensitive data is encrypted.

For local-first sync: data is encrypted before sync to server.
"""

import json
from typing import List, Optional, Tuple, Union

from .models import Entity
from .repository import EntityRepository

# Import chora-crypto if available
try:
    from chora_crypto import (
        WorkspaceKey,
        MasterKey,
        encrypt_entity as crypto_encrypt,
        decrypt_entity as crypto_decrypt,
        EncryptedBlob,
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    WorkspaceKey = None
    MasterKey = None


class EncryptionNotAvailable(Exception):
    """Raised when encryption is requested but chora-crypto is not installed."""
    pass


class EncryptedEntityRepository:
    """
    Entity repository with transparent data encryption.

    Wraps an EntityRepository and encrypts/decrypts entity data automatically.
    Entity metadata (id, type, status) remains in plaintext for querying.

    Usage:
        from chora_crypto import derive_master_key, derive_workspace_key

        # Setup encryption
        master_key, salt = derive_master_key("password")
        workspace_key = derive_workspace_key(master_key, "my-workspace")

        # Create encrypted repository
        repo = EntityRepository(db_path)
        encrypted_repo = EncryptedEntityRepository(repo, workspace_key)

        # Use normally - encryption is transparent
        entity = encrypted_repo.create(Entity(...))
    """

    def __init__(
        self,
        repository: EntityRepository,
        key: Union["WorkspaceKey", "MasterKey", bytes],
    ):
        """
        Initialize encrypted repository.

        Args:
            repository: Underlying EntityRepository
            key: Encryption key (WorkspaceKey, MasterKey, or raw 32-byte key)

        Raises:
            EncryptionNotAvailable: If chora-crypto is not installed
        """
        if not CRYPTO_AVAILABLE:
            raise EncryptionNotAvailable(
                "chora-crypto is required for encryption. "
                "Install with: pip install chora-crypto"
            )

        self.repo = repository
        self.key = key

    def _encrypt_data(self, data: dict) -> str:
        """Encrypt entity data dict to base64 string."""
        # Create a minimal entity dict for encryption
        # We only encrypt the data field contents
        blob = crypto_encrypt({"data": data}, self.key)
        return blob.to_base64()

    def _decrypt_data(self, encrypted: str) -> dict:
        """Decrypt base64 string back to entity data dict."""
        blob = EncryptedBlob.from_base64(encrypted)
        decrypted = crypto_decrypt(blob, self.key)
        return decrypted.get("data", {})

    def _is_encrypted(self, data_str: str) -> bool:
        """Check if data string is encrypted (base64 blob)."""
        # Encrypted data will be base64 and start with expected prefix
        # Plain JSON data will start with { or be empty
        if not data_str:
            return False
        return not data_str.startswith("{") and not data_str.startswith("[")

    def create(self, entity: Entity) -> Entity:
        """Create entity with encrypted data."""
        # Encrypt the data field
        encrypted_data = self._encrypt_data(entity.data)

        # Create entity with encrypted data stored as JSON string
        # We store {"_encrypted": "base64..."} to mark it as encrypted
        encrypted_entity = entity.copy(
            data={"_encrypted": encrypted_data}
        )

        created = self.repo.create(encrypted_entity)

        # Return with decrypted data
        return created.copy(data=entity.data)

    def read(self, entity_id: str) -> Optional[Entity]:
        """Read entity and decrypt data."""
        entity = self.repo.read(entity_id)
        if entity is None:
            return None

        return self._decrypt_entity(entity)

    def update(self, entity: Entity) -> Entity:
        """Update entity with encrypted data."""
        # Encrypt the data field
        encrypted_data = self._encrypt_data(entity.data)

        encrypted_entity = entity.copy(
            data={"_encrypted": encrypted_data}
        )

        updated = self.repo.update(encrypted_entity)

        # Return with decrypted data
        return updated.copy(data=entity.data)

    def delete(self, entity_id: str) -> bool:
        """Delete entity."""
        return self.repo.delete(entity_id)

    def list(
        self,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """List entities with decrypted data."""
        entities = self.repo.list(
            entity_type=entity_type,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [self._decrypt_entity(e) for e in entities]

    def search(self, query: str, limit: int = 20) -> List[Entity]:
        """
        Search entities.

        Note: FTS search only works on unencrypted metadata (id, type, status).
        Searching within encrypted data requires decrypting all entities.
        """
        entities = self.repo.search(query, limit)
        return [self._decrypt_entity(e) for e in entities]

    def get_changes_since(self, since_version: int) -> List[Tuple[Entity, str]]:
        """Get changes with decrypted data."""
        changes = self.repo.get_changes_since(since_version)
        return [(self._decrypt_entity(e), change_type) for e, change_type in changes]

    def _decrypt_entity(self, entity: Entity) -> Entity:
        """Decrypt entity data if encrypted."""
        if "_encrypted" in entity.data:
            decrypted_data = self._decrypt_data(entity.data["_encrypted"])
            return entity.copy(data=decrypted_data)
        return entity


def create_encrypted_repository(
    db_path: str,
    key: Union["WorkspaceKey", "MasterKey", bytes],
) -> EncryptedEntityRepository:
    """
    Convenience function to create an encrypted repository.

    Args:
        db_path: Path to SQLite database
        key: Encryption key

    Returns:
        EncryptedEntityRepository instance
    """
    repo = EntityRepository(db_path)
    return EncryptedEntityRepository(repo, key)
