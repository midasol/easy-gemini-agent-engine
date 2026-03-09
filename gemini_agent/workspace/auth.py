"""Per-user Google OAuth credentials loaded from Secret Manager."""

import hashlib
import json
import logging
import os

from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"

_sm_client = None


class WorkspaceAuthError(Exception):
    """Raised when a user's workspace credentials are missing or invalid."""

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code}] {message}")


def _get_secret_client():
    global _sm_client
    if _sm_client is None:
        from google.cloud import secretmanager
        _sm_client = secretmanager.SecretManagerServiceClient()
    return _sm_client


def get_user_credentials(user_id: str, project_id: str | None = None) -> Credentials:
    """Load OAuth credentials for a user from Secret Manager.

    Reads secret `workspace-token-{user_id}` containing JSON with
    refresh_token, client_id, client_secret.
    """
    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if not project:
        raise WorkspaceAuthError("config_error", "GOOGLE_CLOUD_PROJECT not set")

    user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    secret_name = f"projects/{project}/secrets/workspace_token_{user_hash}/versions/latest"

    try:
        client = _get_secret_client()
        response = client.access_secret_version(request={"name": secret_name})
        token_data = json.loads(response.payload.data.decode("UTF-8"))
    except Exception as e:
        error_str = str(e)
        if "NotFound" in type(e).__name__ or "404" in error_str:
            raise WorkspaceAuthError(
                "not_authenticated",
                f"Google Workspace 연동이 필요합니다. 인증을 먼저 진행해주세요. (user: {user_id})"
            ) from e
        raise WorkspaceAuthError("token_error", f"토큰 로드 실패: {error_str}") from e

    creds = Credentials(
        token=None,
        refresh_token=token_data["refresh_token"],
        token_uri=TOKEN_URI,
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=SCOPES,
    )

    logger.info(f"Loaded workspace credentials for user: {user_id}")
    return creds
