import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from gemini_agent.workspace.auth import get_user_credentials, WorkspaceAuthError


def _make_secret_payload(refresh_token="fake-refresh", client_id="fake-id", client_secret="fake-secret"):
    data = json.dumps({
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    payload = MagicMock()
    payload.data = data
    response = MagicMock()
    response.payload = payload
    return response


class TestGetUserCredentials:
    @patch("gemini_agent.workspace.auth._get_secret_client")
    def test_returns_credentials_from_secret_manager(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.access_secret_version.return_value = _make_secret_payload()
        mock_get_client.return_value = mock_client

        creds = get_user_credentials("user123", project_id="test-project")

        assert isinstance(creds, Credentials)
        assert creds.refresh_token == "fake-refresh"
        assert creds.client_id == "fake-id"
        assert creds.client_secret == "fake-secret"
        user_hash = hashlib.sha256("user123".encode()).hexdigest()[:16]
        mock_client.access_secret_version.assert_called_once_with(
            request={"name": f"projects/test-project/secrets/workspace_token_{user_hash}/versions/latest"}
        )

    @patch("gemini_agent.workspace.auth._get_secret_client")
    def test_raises_auth_error_when_secret_not_found(self, mock_get_client):
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = NotFound("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkspaceAuthError, match="not_authenticated"):
            get_user_credentials("unknown_user", project_id="test-project")
