"""Google Sheets read tool for ADK agent."""

import logging

from googleapiclient.discovery import build

from gemini_agent.workspace.auth import get_user_credentials, WorkspaceAuthError

logger = logging.getLogger(__name__)

MAX_ROWS = 500


def read_spreadsheet(spreadsheet_id: str, range: str = "", tool_context=None) -> dict:
    """Read a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID.
        range: Cell range to read (e.g., "A1:D10"). Defaults to entire first sheet.
        tool_context: ADK tool context (provides user_id).

    Returns:
        Dict with title, sheet_name, headers, rows, and row_count.
    """
    user_id = tool_context.user_id if tool_context else None
    if not user_id:
        return {"error": "no_user_id", "message": "user_id가 필요합니다."}

    try:
        creds = get_user_credentials(user_id)
    except WorkspaceAuthError as e:
        return {"error": e.error_code, "message": e.message}

    try:
        service = build("sheets", "v4", credentials=creds)

        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = meta.get("properties", {}).get("title", "Untitled")
        sheets = meta.get("sheets", [])
        sheet_name = sheets[0]["properties"]["title"] if sheets else "Sheet1"

        read_range = range if range else sheet_name

        values_response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=read_range,
        ).execute()

        values = values_response.get("values", [])

        if not values:
            return {
                "title": title,
                "sheet_name": sheet_name,
                "headers": [],
                "rows": [],
                "row_count": 0,
            }

        headers = values[0]
        rows = values[1:]
        total_rows = len(rows)
        truncated = total_rows > MAX_ROWS

        if truncated:
            rows = rows[:MAX_ROWS]

        result = {
            "title": title,
            "sheet_name": sheet_name,
            "headers": headers,
            "rows": rows,
            "row_count": total_rows,
        }

        if truncated:
            result["truncated"] = True

        return result

    except Exception as e:
        error_str = str(e)
        if "404" in error_str:
            return {"error": "not_found", "message": "스프레드시트를 찾을 수 없습니다."}
        if "403" in error_str:
            return {"error": "access_denied", "message": "해당 스프레드시트에 대한 접근 권한이 없습니다."}
        logger.error(f"Sheets read failed for user {user_id}: {e}")
        return {"error": "api_error", "message": f"스프레드시트 읽기 실패: {error_str}"}
