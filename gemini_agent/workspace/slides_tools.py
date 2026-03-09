"""Google Slides read tool for ADK agent."""

import logging

from googleapiclient.discovery import build

from gemini_agent.workspace.auth import get_user_credentials, WorkspaceAuthError

logger = logging.getLogger(__name__)

MAX_CHARS = 50_000


def _extract_text_from_elements(elements: list) -> str:
    """Extract text from Slides text elements."""
    parts = []
    for elem in elements:
        text_run = elem.get("textRun")
        if text_run:
            parts.append(text_run.get("content", ""))
    return "".join(parts).strip()


def _extract_slide_text(slide: dict) -> tuple[str, str, str]:
    """Extract title, body, and notes from a slide.

    Returns (title, body, notes). Title is the first text box, body is the rest.
    """
    texts = []
    for element in slide.get("pageElements", []):
        shape = element.get("shape")
        if not shape or "text" not in shape:
            continue
        text = _extract_text_from_elements(shape["text"].get("textElements", []))
        if text:
            texts.append(text)

    title = texts[0] if texts else ""
    body = "\n".join(texts[1:]) if len(texts) > 1 else ""

    # Speaker notes
    notes = ""
    notes_page = slide.get("slideProperties", {}).get("notesPage", {})
    for element in notes_page.get("pageElements", []):
        shape = element.get("shape")
        if not shape or "text" not in shape:
            continue
        note_text = _extract_text_from_elements(shape["text"].get("textElements", []))
        if note_text:
            notes = note_text
            break

    return title, body, notes


def read_presentation(presentation_id: str, tool_context=None) -> dict:
    """Read a Google Slides presentation and return slide contents.

    Args:
        presentation_id: The Google Slides presentation ID.
        tool_context: ADK tool context (provides user_id).

    Returns:
        Dict with title, slide_count, and per-slide title/body/notes.
    """
    user_id = tool_context.user_id if tool_context else None
    if not user_id:
        return {"error": "no_user_id", "message": "user_id가 필요합니다."}

    try:
        creds = get_user_credentials(user_id)
    except WorkspaceAuthError as e:
        return {"error": e.error_code, "message": e.message}

    try:
        service = build("slides", "v1", credentials=creds)
        pres = service.presentations().get(presentationId=presentation_id).execute()

        title = pres.get("title", "Untitled")
        raw_slides = pres.get("slides", [])

        slides = []
        total_chars = 0
        for i, slide in enumerate(raw_slides, 1):
            slide_title, body, notes = _extract_slide_text(slide)
            slide_text_len = len(slide_title) + len(body) + len(notes)
            total_chars += slide_text_len

            slides.append({
                "slide_number": i,
                "title": slide_title,
                "body": body,
                "notes": notes,
            })

            if total_chars > MAX_CHARS:
                slides[-1]["body"] = slides[-1]["body"][:1000] + "..."
                return {
                    "title": title,
                    "slide_count": len(raw_slides),
                    "slides": slides,
                    "truncated": True,
                }

        return {
            "title": title,
            "slide_count": len(raw_slides),
            "slides": slides,
        }

    except Exception as e:
        error_str = str(e)
        if "404" in error_str:
            return {"error": "not_found", "message": "프레젠테이션을 찾을 수 없습니다."}
        if "403" in error_str:
            return {"error": "access_denied", "message": "해당 프레젠테이션에 대한 접근 권한이 없습니다."}
        logger.error(f"Slides read failed for user {user_id}: {e}")
        return {"error": "api_error", "message": f"프레젠테이션 읽기 실패: {error_str}"}
