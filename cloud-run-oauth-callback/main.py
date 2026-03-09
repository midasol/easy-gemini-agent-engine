"""Cloud Run OAuth Callback Server for Google Workspace integration.

Handles OAuth consent flow and stores per-user refresh tokens in Secret Manager.
"""

import json
import logging
import os
import secrets

from flask import Flask, redirect, request, session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# Cloud Run terminates TLS at the load balancer, so Flask sees HTTP.
# This tells Flask to trust X-Forwarded-Proto header and generate HTTPS URLs.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "")

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def _get_oauth_config() -> dict:
    """Load OAuth client config from Secret Manager."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/oauth-client-config/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return json.loads(response.payload.data.decode("UTF-8"))


def _save_user_token(user_id: str, token_data: dict):
    """Save user's refresh token to Secret Manager."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    secret_id = f"workspace-token-{user_id}"
    parent = f"projects/{PROJECT_ID}"
    secret_path = f"{parent}/secrets/{secret_id}"

    # Create secret if it doesn't exist
    try:
        client.get_secret(request={"name": secret_path})
    except Exception:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )

    # Add new version with token data
    client.add_secret_version(
        request={
            "parent": secret_path,
            "payload": {"data": json.dumps(token_data).encode("UTF-8")},
        }
    )
    logger.info(f"Saved token for user: {user_id}")


@app.route("/auth/<user_id>")
def auth(user_id: str):
    """Start OAuth flow for a user."""
    from google_auth_oauthlib.flow import Flow

    oauth_config = _get_oauth_config()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": oauth_config["client_id"],
                "client_secret": oauth_config["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=request.url_root.rstrip("/") + "/callback",
    )

    # CSRF protection
    csrf_token = secrets.token_urlsafe(32)
    state = json.dumps({"user_id": user_id, "csrf": csrf_token})
    session["csrf_token"] = csrf_token

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )

    return redirect(authorization_url)


@app.route("/callback")
def callback():
    """Handle OAuth callback and store refresh token."""
    from google_auth_oauthlib.flow import Flow

    state = json.loads(request.args.get("state", "{}"))
    user_id = state.get("user_id")
    csrf_token = state.get("csrf")

    if not user_id:
        return "Invalid state: missing user_id", 400

    if csrf_token != session.get("csrf_token"):
        return "CSRF token mismatch", 403

    oauth_config = _get_oauth_config()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": oauth_config["client_id"],
                "client_secret": oauth_config["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=request.url_root.rstrip("/") + "/callback",
    )

    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    if not credentials.refresh_token:
        return "No refresh token received. Please revoke access and try again.", 400

    token_data = {
        "refresh_token": credentials.refresh_token,
        "client_id": oauth_config["client_id"],
        "client_secret": oauth_config["client_secret"],
    }

    _save_user_token(user_id, token_data)
    session.pop("csrf_token", None)

    return f"""
    <html>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>Google Workspace 연동 완료</h1>
        <p>유저 <strong>{user_id}</strong>의 Google Workspace 연동이 완료되었습니다.</p>
        <p>이제 에이전트에서 Google Docs, Slides, Sheets, Drive 문서를 조회할 수 있습니다.</p>
    </body>
    </html>
    """


@app.route("/status/<user_id>")
def status(user_id: str):
    """Check if a user has authenticated."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{PROJECT_ID}/secrets/workspace-token-{user_id}/versions/latest"

    try:
        client.access_secret_version(request={"name": secret_name})
        return {"user_id": user_id, "authenticated": True}
    except Exception:
        return {"user_id": user_id, "authenticated": False}


@app.route("/revoke/<user_id>", methods=["POST"])
def revoke(user_id: str):
    """Delete a user's stored token."""
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{PROJECT_ID}/secrets/workspace-token-{user_id}"

    try:
        client.delete_secret(request={"name": secret_name})
        return {"user_id": user_id, "revoked": True}
    except Exception as e:
        return {"user_id": user_id, "revoked": False, "error": str(e)}, 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)
