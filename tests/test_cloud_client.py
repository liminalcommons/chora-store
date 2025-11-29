"""
Tests for CloudSyncClient.

Tests the cloud sync client without requiring a real server.
Uses mocking for HTTP requests.
"""

import json
import base64
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chora_store.cloud_client import (
    CloudSyncClient,
    SyncConfig,
    SyncResult,
    SyncError,
    AuthError,
    EncryptedChange,
    create_sync_client,
    CRYPTO_AVAILABLE,
)


class TestSyncConfig:
    """Tests for SyncConfig."""

    def test_config_creation(self):
        """Test creating a sync config."""
        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        assert config.server_url == "https://example.com"
        assert config.workspace_id == "ws-123"
        assert config.site_id == "site-001"
        assert config.token is None
        assert config.workspace_key is None

    def test_config_strips_trailing_slash(self):
        """Test that trailing slash is stripped from server URL."""
        config = SyncConfig(
            server_url="https://example.com/",
            workspace_id="ws-123",
            site_id="site-001",
        )
        assert config.server_url == "https://example.com"

    def test_config_to_file(self):
        """Test saving config to file."""
        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="secret-token",  # Should not be saved
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = Path(f.name)

        try:
            config.to_file(path)

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert data["server_url"] == "https://example.com"
            assert data["workspace_id"] == "ws-123"
            assert data["site_id"] == "site-001"
            assert "token" not in data  # Token should not be saved
        finally:
            path.unlink()

    def test_config_from_file(self):
        """Test loading config from file."""
        data = {
            "server_url": "https://example.com",
            "workspace_id": "ws-123",
            "site_id": "site-001",
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)

        try:
            config = SyncConfig.from_file(path)
            assert config.server_url == "https://example.com"
            assert config.workspace_id == "ws-123"
            assert config.site_id == "site-001"
        finally:
            path.unlink()


class TestEncryptedChange:
    """Tests for EncryptedChange."""

    def test_change_creation(self):
        """Test creating an encrypted change."""
        change = EncryptedChange(
            id="change-123",
            entity_id="entity-456",
            change_type="create",
            encrypted_data=base64.b64encode(b"encrypted").decode(),
            nonce=base64.b64encode(b"nonce").decode(),
            site_id="site-001",
            timestamp="2024-01-01T00:00:00Z",
            version=1,
        )
        assert change.id == "change-123"
        assert change.entity_id == "entity-456"
        assert change.change_type == "create"
        assert change.version == 1

    def test_change_to_dict(self):
        """Test serializing change to dict."""
        change = EncryptedChange(
            id="change-123",
            entity_id="entity-456",
            change_type="update",
            encrypted_data="ZW5jcnlwdGVk",
            nonce="bm9uY2U=",
            site_id="site-001",
            timestamp="2024-01-01T00:00:00Z",
            version=2,
        )

        d = change.to_dict()
        assert d["id"] == "change-123"
        assert d["entityId"] == "entity-456"
        assert d["changeType"] == "update"
        assert d["encryptedData"] == "ZW5jcnlwdGVk"
        assert d["version"] == 2

    def test_change_from_dict(self):
        """Test deserializing change from dict."""
        d = {
            "id": "change-123",
            "entityId": "entity-456",
            "changeType": "delete",
            "encryptedData": "ZW5jcnlwdGVk",
            "nonce": "bm9uY2U=",
            "siteId": "site-001",
            "timestamp": "2024-01-01T00:00:00Z",
            "version": 3,
        }

        change = EncryptedChange.from_dict(d)
        assert change.id == "change-123"
        assert change.entity_id == "entity-456"
        assert change.change_type == "delete"
        assert change.version == 3


class TestSyncResult:
    """Tests for SyncResult."""

    def test_successful_result(self):
        """Test successful sync result."""
        result = SyncResult(
            pushed=5,
            pulled=3,
            local_version=10,
            remote_version=12,
            errors=[],
        )
        assert result.success is True
        assert result.pushed == 5
        assert result.pulled == 3

    def test_failed_result(self):
        """Test failed sync result."""
        result = SyncResult(
            pushed=0,
            pulled=0,
            local_version=10,
            remote_version=10,
            errors=["Connection failed"],
        )
        assert result.success is False


@pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="chora-crypto not installed")
class TestCloudSyncClient:
    """Tests for CloudSyncClient."""

    def test_client_creation(self):
        """Test creating a sync client."""
        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)
        assert client.config.server_url == "https://example.com"

    @patch('chora_store.cloud_client.urlopen')
    def test_health_check_success(self, mock_urlopen):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)
        assert client.health_check() is True

    @patch('chora_store.cloud_client.urlopen')
    def test_health_check_failure(self, mock_urlopen):
        """Test failed health check."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)
        assert client.health_check() is False

    @patch('chora_store.cloud_client.urlopen')
    def test_login_success(self, mock_urlopen):
        """Test successful login."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"token": "test-token", "accountId": "acc-123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)
        token = client.login("user@example.com", "password")

        assert token == "test-token"
        assert client.config.token == "test-token"

    @patch('chora_store.cloud_client.urlopen')
    def test_login_failure(self, mock_urlopen):
        """Test failed login."""
        error_body = b'{"error": "AUTH_FAILED", "message": "Invalid credentials"}'
        mock_response = MagicMock()
        mock_response.read.return_value = error_body
        mock_error = HTTPError(
            "https://example.com/api/login",
            401,
            "Unauthorized",
            {},
            BytesIO(error_body),
        )
        mock_urlopen.side_effect = mock_error

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)

        with pytest.raises(AuthError):
            client.login("user@example.com", "wrong-password")

    @patch('chora_store.cloud_client.urlopen')
    def test_create_account(self, mock_urlopen):
        """Test account creation."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"accountId": "acc-new-123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)
        account_id = client.create_account("new@example.com", "password")

        assert account_id == "acc-new-123"

    @patch('chora_store.cloud_client.urlopen')
    def test_create_workspace(self, mock_urlopen):
        """Test workspace creation."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"workspaceId": "ws-new-123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        workspace_id = client.create_workspace("My Workspace")

        assert workspace_id == "ws-new-123"
        assert client.config.workspace_id == "ws-new-123"

    @patch('chora_store.cloud_client.urlopen')
    def test_list_workspaces(self, mock_urlopen):
        """Test listing workspaces."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"workspaces": [{"id": "ws-1"}, {"id": "ws-2"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        workspaces = client.list_workspaces()

        assert len(workspaces) == 2
        assert workspaces[0]["id"] == "ws-1"

    def test_push_without_key_fails(self):
        """Test that push fails without workspace key."""
        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)

        with pytest.raises(SyncError, match="Workspace key not set"):
            client.push_changes([("entity-1", "create", 1, {"data": "test"})])

    def test_pull_without_key_fails(self):
        """Test that pull fails without workspace key."""
        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)

        with pytest.raises(SyncError, match="Workspace key not set"):
            client.pull_changes(since_version=0)


class TestCreateSyncClient:
    """Tests for create_sync_client helper."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="chora-crypto not installed")
    def test_create_client_with_site_id(self):
        """Test creating client with explicit site ID."""
        client = create_sync_client(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="my-site",
        )
        assert client.config.site_id == "my-site"
        assert client.config.workspace_id == "ws-123"

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="chora-crypto not installed")
    def test_create_client_generates_site_id(self):
        """Test that site ID is generated if not provided."""
        client = create_sync_client(
            server_url="https://example.com",
            workspace_id="ws-123",
        )
        assert client.config.site_id is not None
        assert len(client.config.site_id) > 0


@pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="chora-crypto not installed")
class TestEncryptionIntegration:
    """Tests for encryption integration."""

    def test_set_workspace_key(self):
        """Test setting workspace key."""
        from chora_crypto import generate_workspace_key

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
        )
        client = CloudSyncClient(config)

        key = generate_workspace_key("ws-123")
        client.set_workspace_key(key)

        assert client.config.workspace_key is not None

    @patch('chora_store.cloud_client.urlopen')
    def test_push_encrypts_data(self, mock_urlopen):
        """Test that push encrypts data."""
        from chora_crypto import generate_workspace_key

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"acceptedChanges": 1, "version": 1}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        client.set_workspace_key(generate_workspace_key("ws-123"))

        accepted, version = client.push_changes([
            ("entity-1", "create", 1, json.dumps({"name": "Test"})),
        ])

        assert accepted == 1
        assert version == 1

        # Verify the request was made
        assert mock_urlopen.called

    @patch('chora_store.cloud_client.urlopen')
    def test_pull_decrypts_data(self, mock_urlopen):
        """Test that pull decrypts data."""
        from chora_crypto import generate_workspace_key, encrypt_entity, EncryptedBlob

        key = generate_workspace_key("ws-123")

        # Encrypt test data
        test_data = {"value": json.dumps({"name": "Test Entity"})}
        encrypted = encrypt_entity(test_data, key)

        # Create mock response with encrypted change
        response_data = {
            "changes": [{
                "id": "change-123",
                "entityId": "entity-456",
                "changeType": "create",
                "encryptedData": base64.b64encode(encrypted.ciphertext).decode(),
                "nonce": base64.b64encode(encrypted.nonce).decode(),
                "siteId": "other-site",  # Different site so it's not skipped
                "timestamp": "2024-01-01T00:00:00Z",
                "version": 1,
            }],
            "fromVersion": 0,
            "toVersion": 1,
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        client.set_workspace_key(key)

        changes, version = client.pull_changes(since_version=0)

        assert version == 1
        assert len(changes) == 1
        entity_id, change_type, ver, value = changes[0]
        assert entity_id == "entity-456"
        assert change_type == "create"
        # Value should be decrypted
        assert value is not None

    @patch('chora_store.cloud_client.urlopen')
    def test_pull_skips_own_changes(self, mock_urlopen):
        """Test that pull skips changes from own site."""
        from chora_crypto import generate_workspace_key, encrypt_entity

        key = generate_workspace_key("ws-123")

        # Encrypt test data
        test_data = {"value": json.dumps({"name": "Test"})}
        encrypted = encrypt_entity(test_data, key)

        # Create mock response with change from same site
        response_data = {
            "changes": [{
                "id": "change-123",
                "entityId": "entity-456",
                "changeType": "create",
                "encryptedData": base64.b64encode(encrypted.ciphertext).decode(),
                "nonce": base64.b64encode(encrypted.nonce).decode(),
                "siteId": "site-001",  # Same site - should be skipped
                "timestamp": "2024-01-01T00:00:00Z",
                "version": 1,
            }],
            "fromVersion": 0,
            "toVersion": 1,
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        client.set_workspace_key(key)

        changes, version = client.pull_changes(since_version=0)

        assert len(changes) == 0  # Should skip own changes


class TestSyncOperations:
    """Tests for high-level sync operations."""

    @pytest.mark.skipif(not CRYPTO_AVAILABLE, reason="chora-crypto not installed")
    @patch('chora_store.cloud_client.urlopen')
    def test_sync_push_and_pull(self, mock_urlopen):
        """Test full sync operation."""
        from chora_crypto import generate_workspace_key

        # Set up mock responses for push and pull
        responses = [
            b'{"acceptedChanges": 1, "version": 2}',  # Push response
            b'{"changes": [], "fromVersion": 0, "toVersion": 2}',  # Pull response
        ]
        response_iter = iter(responses)

        def mock_response_factory(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.read.return_value = next(response_iter)
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        mock_urlopen.side_effect = mock_response_factory

        config = SyncConfig(
            server_url="https://example.com",
            workspace_id="ws-123",
            site_id="site-001",
            token="test-token",
        )
        client = CloudSyncClient(config)
        client.set_workspace_key(generate_workspace_key("ws-123"))

        result = client.sync(
            local_changes=[("entity-1", "create", 1, json.dumps({"name": "Test"}))],
            since_version=0,
        )

        assert result.success is True
        assert result.pushed == 1
        assert result.pulled == 0
