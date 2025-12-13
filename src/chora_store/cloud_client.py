"""
Cloud Sync Client - HTTP client for syncing with chora-cloud.

Provides E2E encrypted sync with the chora-cloud Cloudflare Workers service.
Uses chora-crypto for encryption/decryption.
"""

import json
import uuid
import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# Try to import crypto components
try:
    from chora_crypto import (
        encrypt_entity,
        decrypt_entity,
        EncryptedBlob,
        WorkspaceKey,
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    encrypt_entity = None
    decrypt_entity = None
    EncryptedBlob = None
    WorkspaceKey = None


class CryptoNotAvailable(Exception):
    """Raised when chora-crypto is not installed."""
    pass


class SyncError(Exception):
    """Error during cloud sync operation."""
    pass


class AuthError(SyncError):
    """Authentication error."""
    pass


@dataclass
class SyncConfig:
    """
    Configuration for cloud sync.

    Attributes:
        server_url: Base URL of chora-cloud service
        workspace_id: ID of workspace to sync
        site_id: Unique identifier for this local site
        token: Authentication token (from login)
        workspace_key: Encryption key for E2E encryption
    """
    server_url: str
    workspace_id: str
    site_id: str
    token: Optional[str] = None
    workspace_key: Optional[Any] = None

    def __post_init__(self):
        # Ensure server_url has no trailing slash
        self.server_url = self.server_url.rstrip('/')

    @classmethod
    def from_file(cls, path: Path) -> "SyncConfig":
        """Load config from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)

    def to_file(self, path: Path) -> None:
        """Save config to JSON file (excludes sensitive data)."""
        data = {
            "server_url": self.server_url,
            "workspace_id": self.workspace_id,
            "site_id": self.site_id,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)


@dataclass
class EncryptedChange:
    """
    A single encrypted change for sync.

    The server only sees encrypted blobs - it cannot read the content.
    """
    id: str
    entity_id: str
    change_type: str  # "create", "update", "delete"
    encrypted_data: str  # base64 encoded
    nonce: str  # base64 encoded
    site_id: str
    timestamp: str  # ISO format
    version: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entityId": self.entity_id,
            "changeType": self.change_type,
            "encryptedData": self.encrypted_data,
            "nonce": self.nonce,
            "siteId": self.site_id,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EncryptedChange":
        return cls(
            id=d["id"],
            entity_id=d["entityId"],
            change_type=d["changeType"],
            encrypted_data=d["encryptedData"],
            nonce=d["nonce"],
            site_id=d["siteId"],
            timestamp=d["timestamp"],
            version=d["version"],
        )


@dataclass
class SyncResult:
    """Result of a sync operation."""
    pushed: int
    pulled: int
    local_version: int
    remote_version: int
    errors: List[str]

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class CloudSyncClient:
    """
    HTTP client for cloud sync with chora-cloud.

    Provides E2E encrypted sync:
    - All data is encrypted before leaving the client
    - Server only sees opaque blobs
    - Uses chora-crypto for encryption

    Example:
        config = SyncConfig(
            server_url="https://chora-cloud.workers.dev",
            workspace_id="ws-123",
            site_id="laptop-001",
        )
        client = CloudSyncClient(config)

        # Login
        client.login("user@example.com", "password")

        # Sync
        result = client.sync(changes_to_push, since_version=0)
    """

    def __init__(self, config: SyncConfig):
        """
        Initialize sync client.

        Args:
            config: Sync configuration

        Raises:
            CryptoNotAvailable: If chora-crypto is not installed
        """
        if not CRYPTO_AVAILABLE:
            raise CryptoNotAvailable(
                "chora-crypto is not installed. Install it with: pip install chora-crypto"
            )

        self.config = config
        self._timeout = 30

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to server.

        Args:
            method: HTTP method
            path: API path
            data: Request body (for POST/PUT)
            auth: Include auth header

        Returns:
            Response JSON

        Raises:
            SyncError: On request failure
            AuthError: On authentication failure
        """
        url = f"{self.config.server_url}{path}"

        headers = {
            "Content-Type": "application/json",
        }

        if auth and self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')

        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                error_data = json.loads(error_body)
                error_msg = error_data.get("message", error_body)
            except json.JSONDecodeError:
                error_msg = error_body

            if e.code == 401:
                raise AuthError(f"Authentication failed: {error_msg}")
            raise SyncError(f"Request failed ({e.code}): {error_msg}")
        except URLError as e:
            raise SyncError(f"Connection failed: {e.reason}")

    def health_check(self) -> bool:
        """
        Check if the server is available.

        Returns:
            True if server is healthy
        """
        try:
            result = self._request("GET", "/health", auth=False)
            return result.get("status") == "ok"
        except SyncError:
            return False

    def create_account(self, email: str, password: str) -> str:
        """
        Create a new account.

        Args:
            email: User email
            password: User password

        Returns:
            Account ID
        """
        result = self._request(
            "POST",
            "/api/accounts",
            data={"email": email, "password": password},
            auth=False,
        )
        return result["accountId"]

    def login(self, email: str, password: str) -> str:
        """
        Login and store auth token.

        Args:
            email: User email
            password: User password

        Returns:
            Auth token
        """
        result = self._request(
            "POST",
            "/api/login",
            data={"email": email, "password": password},
            auth=False,
        )
        self.config.token = result["token"]
        return result["token"]

    def create_workspace(self, name: str) -> str:
        """
        Create a new workspace.

        Args:
            name: Workspace name (encrypted by server)

        Returns:
            Workspace ID
        """
        result = self._request(
            "POST",
            "/api/workspaces",
            data={"name": name},
        )
        self.config.workspace_id = result["workspaceId"]
        return result["workspaceId"]

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """
        List user's workspaces.

        Returns:
            List of workspace info dicts
        """
        result = self._request("GET", "/api/workspaces")
        return result.get("workspaces", [])

    def push_changes(
        self,
        changes: List[Tuple[str, str, str, Any]],
    ) -> Tuple[int, int]:
        """
        Push encrypted changes to server.

        Args:
            changes: List of (entity_id, change_type, value_json) tuples

        Returns:
            Tuple of (accepted_count, new_server_version)
        """
        if not self.config.workspace_key:
            raise SyncError("Workspace key not set. Call set_workspace_key() first.")

        encrypted_changes = []
        for entity_id, change_type, db_version, value_json in changes:
            # Encrypt the value
            encrypted = encrypt_entity(
                {"value": value_json} if value_json else {},
                self.config.workspace_key,
            )

            change = EncryptedChange(
                id=str(uuid.uuid4()),
                entity_id=entity_id,
                change_type=change_type,
                encrypted_data=base64.b64encode(encrypted.ciphertext).decode('ascii'),
                nonce=base64.b64encode(encrypted.nonce).decode('ascii'),
                site_id=self.config.site_id,
                timestamp=datetime.utcnow().isoformat(),
                version=db_version,
            )
            encrypted_changes.append(change.to_dict())

        result = self._request(
            "POST",
            f"/sync/{self.config.workspace_id}/changes",
            data=encrypted_changes,
        )

        return result.get("acceptedChanges", 0), result.get("version", 0)

    def pull_changes(
        self,
        since_version: int = 0,
    ) -> Tuple[List[Tuple[str, str, int, Optional[str]]], int]:
        """
        Pull and decrypt changes from server.

        Args:
            since_version: Pull changes after this version

        Returns:
            Tuple of (changes, new_version)
            Changes are (entity_id, change_type, version, decrypted_value_json)
        """
        if not self.config.workspace_key:
            raise SyncError("Workspace key not set. Call set_workspace_key() first.")

        result = self._request(
            "GET",
            f"/sync/{self.config.workspace_id}/changes?since={since_version}",
        )

        decrypted_changes = []
        for change_data in result.get("changes", []):
            change = EncryptedChange.from_dict(change_data)

            # Skip our own changes
            if change.site_id == self.config.site_id:
                continue

            # Decrypt the value
            try:
                blob = EncryptedBlob(
                    nonce=base64.b64decode(change.nonce),
                    ciphertext=base64.b64decode(change.encrypted_data),
                )
                decrypted = decrypt_entity(blob, self.config.workspace_key)
                value_json = decrypted.get("value")
            except Exception:
                # Decryption failed - skip this change
                continue

            decrypted_changes.append((
                change.entity_id,
                change.change_type,
                change.version,
                value_json,
            ))

        return decrypted_changes, result.get("toVersion", since_version)

    def set_workspace_key(self, key: Any) -> None:
        """
        Set the workspace encryption key.

        Args:
            key: WorkspaceKey, MasterKey, or raw 32-byte key
        """
        self.config.workspace_key = key

    def sync(
        self,
        local_changes: List[Tuple[str, str, int, Any]],
        since_version: int = 0,
    ) -> SyncResult:
        """
        Bidirectional sync with server.

        Args:
            local_changes: Changes to push (entity_id, change_type, version, value)
            since_version: Pull changes after this version

        Returns:
            SyncResult with statistics
        """
        errors = []
        pushed = 0
        pulled = 0
        local_version = since_version
        remote_version = 0

        # Push local changes
        if local_changes:
            try:
                pushed, remote_version = self.push_changes(local_changes)
            except SyncError as e:
                errors.append(f"Push failed: {e}")

        # Pull remote changes
        try:
            changes, remote_version = self.pull_changes(since_version)
            pulled = len(changes)
        except SyncError as e:
            errors.append(f"Pull failed: {e}")

        return SyncResult(
            pushed=pushed,
            pulled=pulled,
            local_version=local_version,
            remote_version=remote_version,
            errors=errors,
        )


def create_sync_client(
    server_url: str,
    workspace_id: str,
    site_id: Optional[str] = None,
) -> CloudSyncClient:
    """
    Create a configured sync client.

    Args:
        server_url: chora-cloud server URL
        workspace_id: Workspace to sync
        site_id: Local site identifier (generated if not provided)

    Returns:
        Configured CloudSyncClient
    """
    if site_id is None:
        import socket
        site_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    config = SyncConfig(
        server_url=server_url,
        workspace_id=workspace_id,
        site_id=site_id,
    )

    return CloudSyncClient(config)
