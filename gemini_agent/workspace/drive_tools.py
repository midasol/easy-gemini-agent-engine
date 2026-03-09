"""Google Drive search tool for ADK agent."""

import logging

from googleapiclient.discovery import build

from gemini_agent.workspace.auth import get_user_credentials, WorkspaceAuthError

logger = logging.getLogger(__name__)

MIME_TYPE_MAP = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.presentation": "presentation",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.folder": "folder",
    "application/pdf": "pdf",
}


def search_drive(query: str, max_results: int = 10, tool_context=None) -> dict:
    """Search the user's Google Drive for files matching the query.

    Args:
        query: Search term to find in file names and content.
        max_results: Maximum number of results to return (default 10, max 50).
        tool_context: ADK tool context (provides user_id).

    Returns:
        Dict with total_results and list of matching files.
    """
    user_id = tool_context.user_id if tool_context else None
    if not user_id:
        return {"error": "no_user_id", "message": "user_id가 필요합니다."}

    max_results = min(max_results, 50)

    try:
        creds = get_user_credentials(user_id)
    except WorkspaceAuthError as e:
        return {"error": e.error_code, "message": e.message}

    try:
        service = build("drive", "v3", credentials=creds)
        response = service.files().list(
            q=f"fullText contains '{query}'",
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, owners)",
            orderBy="modifiedTime desc",
        ).execute()

        files = []
        for f in response.get("files", []):
            owners = f.get("owners", [])
            files.append({
                "id": f["id"],
                "name": f["name"],
                "type": MIME_TYPE_MAP.get(f.get("mimeType", ""), f.get("mimeType", "unknown")),
                "modified": f.get("modifiedTime", "")[:10],
                "owner": owners[0]["emailAddress"] if owners else "unknown",
            })

        return {"total_results": len(files), "files": files}

    except Exception as e:
        logger.error(f"Drive search failed for user {user_id}: {e}")
        return {"error": "api_error", "message": f"Drive 검색 실패: {str(e)}"}
