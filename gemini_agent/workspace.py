"""Google Workspace tools for ADK agent.

Supports two OAuth modes:
1. Gemini Enterprise: token injected into tool_context.state[AUTH_ID]
2. ADK OAuth flow: request_credential / get_auth_response fallback
"""

import os
import re
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Must match the authorization name set in Gemini Enterprise agent registration
CLIENT_AUTH_NAME = "workspace-tools"

WORKSPACE_SCOPES = {
    "https://www.googleapis.com/auth/drive.readonly": "View Google Drive files",
    "https://www.googleapis.com/auth/documents.readonly": "View Google Docs",
    "https://www.googleapis.com/auth/presentations.readonly": "View Google Slides",
    "https://www.googleapis.com/auth/spreadsheets.readonly": "View Google Sheets",
}


def _build_auth_config():
    """Build ADK AuthConfig for Google Workspace OAuth2."""
    from google.adk.auth.auth_credential import (
        AuthCredential,
        AuthCredentialTypes,
        OAuth2Auth,
    )
    from google.adk.auth.auth_tool import AuthConfig
    from fastapi.openapi.models import (
        OAuth2 as OAuth2Scheme,
        OAuthFlowAuthorizationCode,
        OAuthFlows,
    )

    auth_scheme = OAuth2Scheme(
        flows=OAuthFlows(
            authorizationCode=OAuthFlowAuthorizationCode(
                authorizationUrl="https://accounts.google.com/o/oauth2/auth",
                tokenUrl="https://oauth2.googleapis.com/token",
                scopes=WORKSPACE_SCOPES,
            )
        )
    )

    auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2,
        oauth2=OAuth2Auth(
            client_id=os.getenv("OAUTH_CLIENT_ID", ""),
            client_secret=os.getenv("OAUTH_CLIENT_SECRET", ""),
        ),
    )

    return AuthConfig(
        auth_scheme=auth_scheme,
        raw_auth_credential=auth_credential,
    )


def _get_access_token(tool_context) -> str | None:
    """Extract OAuth token. Returns None if auth is pending."""
    state_dict = (
        tool_context.state.to_dict()
        if hasattr(tool_context.state, "to_dict")
        else tool_context.state
    )
    logger.info(f"tool_context.state keys: {list(state_dict.keys())}")

    # 1) Try exact AUTH_ID key
    token = state_dict.get(CLIENT_AUTH_NAME)
    if token:
        logger.info("Found token via exact AUTH_ID key")
        return token

    # 2) Try AUTH_ID_<number> pattern (codelab format)
    escaped = re.escape(CLIENT_AUTH_NAME)
    pattern = re.compile(fr"^{escaped}_\d+$")
    for k, v in state_dict.items():
        if pattern.match(k) and isinstance(v, str):
            logger.info(f"Found token via pattern key: {k}")
            return v

    # 3) Fallback: any long string value that looks like a token
    for k, v in state_dict.items():
        if isinstance(v, str) and len(v) > 50:
            logger.info(f"Found potential token in key: {k}")
            return v

    # 4) Try ADK OAuth flow (request_credential / get_auth_response)
    logger.info("No token in state. Trying ADK auth flow...")
    try:
        auth_config = _build_auth_config()
        auth_response = tool_context.get_auth_response(auth_config)
        if auth_response and auth_response.oauth2:
            token = auth_response.oauth2.access_token
            if token:
                logger.info("Got token via get_auth_response")
                return token

        # Request credentials — triggers auth button in Gemini Enterprise
        logger.info("Requesting credentials via request_credential...")
        tool_context.request_credential(auth_config)
        return None  # Signal that auth is pending
    except Exception as e:
        logger.warning(f"ADK auth flow failed: {e}")

    raise ValueError(
        "Google Workspace 인증이 필요합니다. 에이전트 채팅에서 승인을 진행해주세요."
    )


def _get_credentials(tool_context) -> Credentials | None:
    """Build google-auth Credentials. Returns None if auth is pending."""
    token = _get_access_token(tool_context)
    if token is None:
        return None
    return Credentials(token=token)

_AUTH_PENDING_RESPONSE = {
    "status": "authorization_required",
    "message": "Google Workspace 접근 권한이 필요합니다. 승인 버튼을 클릭해 주세요.",
}


# ---------------------------------------------------------------------------
# Drive Search
# ---------------------------------------------------------------------------
def search_drive(query: str, max_results: int = 10, tool_context=None) -> dict:
    """Search the user's Google Drive for files matching the query.

    Args:
        query: Search term to find in file names and content.
        max_results: Maximum number of results to return (default 10, max 50).
        tool_context: ADK tool context (provides OAuth token).

    Returns:
        Dict with total_results and list of matching files.
    """
    creds = _get_credentials(tool_context)
    if creds is None:
        return _AUTH_PENDING_RESPONSE
    max_results = min(max_results, 50)

    service = build("drive", "v3", credentials=creds)
    response = (
        service.files()
        .list(
            q=f"fullText contains '{query}'",
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, owners)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )

    mime_map = {
        "application/vnd.google-apps.document": "document",
        "application/vnd.google-apps.presentation": "presentation",
        "application/vnd.google-apps.spreadsheet": "spreadsheet",
        "application/vnd.google-apps.folder": "folder",
        "application/pdf": "pdf",
    }

    files = []
    for f in response.get("files", []):
        owners = f.get("owners", [])
        files.append(
            {
                "id": f["id"],
                "name": f["name"],
                "type": mime_map.get(f.get("mimeType", ""), f.get("mimeType", "unknown")),
                "modified": f.get("modifiedTime", "")[:10],
                "owner": owners[0]["emailAddress"] if owners else "unknown",
            }
        )

    return {"total_results": len(files), "files": files}


# ---------------------------------------------------------------------------
# Google Docs
# ---------------------------------------------------------------------------
def read_document(document_id: str, tool_context=None) -> dict:
    """Read the text content of a Google Docs document.

    Args:
        document_id: The Google Docs document ID.
        tool_context: ADK tool context (provides OAuth token).

    Returns:
        Dict with document title and text content.
    """
    creds = _get_credentials(tool_context)
    if creds is None:
        return _AUTH_PENDING_RESPONSE
    service = build("docs", "v1", credentials=creds)
    doc = service.documents().get(documentId=document_id).execute()

    title = doc.get("title", "Untitled")
    text_parts = []

    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for elem in paragraph.get("elements", []):
            text_run = elem.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))

    content = "".join(text_parts).strip()
    if len(content) > 50000:
        content = content[:50000] + "\n... (truncated)"

    return {"title": title, "content": content}


# ---------------------------------------------------------------------------
# Google Slides
# ---------------------------------------------------------------------------
def read_presentation(presentation_id: str, tool_context=None) -> dict:
    """Read the text content of a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID.
        tool_context: ADK tool context (provides OAuth token).

    Returns:
        Dict with presentation title and slides content.
    """
    creds = _get_credentials(tool_context)
    if creds is None:
        return _AUTH_PENDING_RESPONSE
    service = build("slides", "v1", credentials=creds)
    pres = service.presentations().get(presentationId=presentation_id).execute()

    title = pres.get("title", "Untitled")
    slides_data = []

    for i, slide in enumerate(pres.get("slides", []), 1):
        slide_texts = []
        for element in slide.get("pageElements", []):
            shape = element.get("shape")
            if not shape:
                continue
            text_elements = (
                shape.get("text", {}).get("textElements", [])
            )
            for te in text_elements:
                text_run = te.get("textRun")
                if text_run:
                    slide_texts.append(text_run.get("content", ""))

        slides_data.append(
            {"slide_number": i, "content": "".join(slide_texts).strip()}
        )

    return {"title": title, "total_slides": len(slides_data), "slides": slides_data}


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------
def read_spreadsheet(spreadsheet_id: str, sheet_name: str = "", tool_context=None) -> dict:
    """Read the content of a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID.
        sheet_name: Optional sheet name. If empty, reads the first sheet.
        tool_context: ADK tool context (provides OAuth token).

    Returns:
        Dict with spreadsheet title, headers, and rows.
    """
    creds = _get_credentials(tool_context)
    if creds is None:
        return _AUTH_PENDING_RESPONSE
    service = build("sheets", "v4", credentials=creds)

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    title = meta.get("properties", {}).get("title", "Untitled")

    if not sheet_name:
        sheets = meta.get("sheets", [])
        if sheets:
            sheet_name = sheets[0].get("properties", {}).get("title", "Sheet1")
        else:
            sheet_name = "Sheet1"

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_name)
        .execute()
    )

    values = result.get("values", [])
    if not values:
        return {"title": title, "sheet": sheet_name, "headers": [], "rows": [], "total_rows": 0}

    headers = values[0]
    rows = values[1:500]

    return {
        "title": title,
        "sheet": sheet_name,
        "headers": headers,
        "rows": rows,
        "total_rows": len(values) - 1,
        "truncated": len(values) - 1 > 500,
    }
