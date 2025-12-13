"""
chora-store: SQLite entity store with Physics Engine validation.

The Physics Engine enforces Structural Governance - invalid entities cannot exist.

Optional integrations:
- EncryptedEntityRepository: E2E encryption (requires chora-crypto)
- SyncableRepository: CRDT sync between databases (requires chora-sync)
"""

from .models import Entity, ValidationError, InvalidEntityType
from .factory import EntityFactory
from .repository import EntityRepository
from .observer import EntityObserver
from .search import EntitySearch, SearchResult, FacetCount, SearchFacets
from . import backup

# Optional: Encryption support (requires chora-crypto)
try:
    from .encrypted_repository import (
        EncryptedEntityRepository,
        EncryptionNotAvailable,
        CRYPTO_AVAILABLE,
    )
except ImportError:
    EncryptedEntityRepository = None
    EncryptionNotAvailable = None
    CRYPTO_AVAILABLE = False

# Optional: Sync support (requires chora-sync)
try:
    from .syncable_repository import (
        SyncableRepository,
        SyncNotAvailable,
        SYNC_AVAILABLE,
    )
except ImportError:
    SyncableRepository = None
    SyncNotAvailable = None
    SYNC_AVAILABLE = False

# Optional: Cloud sync support (requires chora-crypto)
try:
    from .cloud_client import (
        CloudSyncClient,
        SyncConfig,
        SyncResult,
        SyncError,
        AuthError,
        CryptoNotAvailable,
        create_sync_client,
    )
    CLOUD_SYNC_AVAILABLE = True
except ImportError:
    CloudSyncClient = None
    SyncConfig = None
    SyncResult = None
    SyncError = None
    AuthError = None
    CryptoNotAvailable = None
    create_sync_client = None
    CLOUD_SYNC_AVAILABLE = False

__version__ = "0.1.0"
__all__ = [
    # Core
    "Entity",
    "EntityFactory",
    "EntityRepository",
    "EntityObserver",
    "EntitySearch",
    "SearchResult",
    "FacetCount",
    "SearchFacets",
    "ValidationError",
    "InvalidEntityType",
    "backup",
    # Optional: Encryption
    "EncryptedEntityRepository",
    "EncryptionNotAvailable",
    "CRYPTO_AVAILABLE",
    # Optional: Sync
    "SyncableRepository",
    "SyncNotAvailable",
    "SYNC_AVAILABLE",
    # Optional: Cloud sync
    "CloudSyncClient",
    "SyncConfig",
    "SyncResult",
    "SyncError",
    "AuthError",
    "CryptoNotAvailable",
    "create_sync_client",
    "CLOUD_SYNC_AVAILABLE",
]
