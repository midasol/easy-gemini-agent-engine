"""Google Docs read tool for ADK agent."""

import logging

from googleapiclient.discovery import build

from gemini_agent.workspace.auth import get_user_credentials, WorkspaceAuthError

logger = logging.getLogger(__name__)

MAX_CHARS = 50_000


def _extract_text(doc: dict) -> str:
    """Extract plain text from a Docs API document response."""
    text_parts = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for elem in paragraph.get("elements", []):
            text_run = elem.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts).strip()


def read_document(document_id: str, tool_context=None) -> dict:
    """Read a Google Docs document and return its text content.

    Args:
        document_id: The Google Docs document ID.
        tool_context: ADK tool context (provides user_id).

    Returns:
        Dict with title, content text, and word count.
    """
    user_id = tool_context.user_id if tool_context else None
    if not user_id:
        return {"error": "no_user_id", "message": "user_id가 필요합니다."}

    try:
        creds = get_user_credentials(user_id)
    except WorkspaceAuthError as e:
        return {"error": e.error_code, "message": e.message}

    try:
        service = build("docs", "v1", credentials=creds)
        doc = service.documents().get(documentId=document_id).execute()

        title = doc.get("title", "Untitled")
        content = _extract_text(doc)
        truncated = len(content) > MAX_CHARS

        if truncated:
            content = content[:MAX_CHARS]

        return {
            "title": title,
            "content": content,
            "word_count": len(content.split()),
            "truncated": truncated,
        }

    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "HttpError 404" in error_str:
            return {"error": "not_found", "message": "문서를 찾을 수 없습니다."}
        if "403" in error_str or "HttpError 403" in error_str:
            return {"error": "access_denied", "message": "해당 문서에 대한 접근 권한이 없습니다."}
        logger.error(f"Docs read failed for user {user_id}: {e}")
        return {"error": "api_error", "message": f"문서 읽기 실패: {error_str}"}
