# Google Workspace Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Google OAuth + Workspace tool functions so the agent can search Drive and read Docs/Slides/Sheets on behalf of authenticated users.

**Architecture:** Cloud Run OAuth callback server handles user authentication and stores refresh tokens in Secret Manager. Agent Engine tool functions load per-user credentials from Secret Manager and call Google APIs (Drive v3, Docs v1, Slides v1, Sheets v4) directly via `google-api-python-client`.

**Tech Stack:** Python 3.11+, Flask (OAuth server), google-api-python-client, google-auth, google-auth-oauthlib, google-cloud-secret-manager, Google ADK

---

### Task 1: Add Workspace Dependencies

**Files:**
- Modify: `pyproject.toml:7-13`

**Step 1: Add dependencies to pyproject.toml**

Add 3 new dependencies to the `dependencies` list in `pyproject.toml`:

```toml
[project]
name = "easy-gemini-agent-engine"
version = "0.1.0"
description = "Simple Gemini agent with built-in tools for Agent Engine deployment"
license = {text = "Apache-2.0"}
requires-python = ">=3.11,<3.14"
dependencies = [
    "google-adk>=1.15.0,<2.0.0",
    "google-cloud-aiplatform[agent-engines]>=1.128.0,<2.0.0",
    "google-cloud-secret-manager>=2.16.0,<3.0.0",
    "nest-asyncio>=1.5.0,<2.0.0",
    "python-dotenv>=1.0.0,<2.0.0",
    "google-api-python-client>=2.100.0,<3.0.0",
    "google-auth>=2.20.0,<3.0.0",
    "google-auth-oauthlib>=1.0.0,<2.0.0",
]
```

**Step 2: Install dependencies**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && uv sync`

Expected: Dependencies install successfully.

**Step 3: Verify imports work**

Run: `uv run python -c "from googleapiclient.discovery import build; from google.oauth2.credentials import Credentials; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add google workspace dependencies"
```

---

### Task 2: Workspace Auth Helper (`gemini_agent/workspace/auth.py`)

**Files:**
- Create: `gemini_agent/workspace/__init__.py`
- Create: `gemini_agent/workspace/auth.py`
- Test: `tests/workspace/test_auth.py`

**Step 1: Create workspace package init**

Create `gemini_agent/workspace/__init__.py`:

```python
```

(Empty file — just makes it a package.)

**Step 2: Write failing test for `get_user_credentials`**

Create `tests/__init__.py` (empty) and `tests/workspace/__init__.py` (empty) if they don't exist.

Create `tests/workspace/test_auth.py`:

```python
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
        mock_client.access_secret_version.assert_called_once_with(
            request={"name": "projects/test-project/secrets/workspace-token-user123/versions/latest"}
        )

    @patch("gemini_agent.workspace.auth._get_secret_client")
    def test_raises_auth_error_when_secret_not_found(self, mock_get_client):
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = NotFound("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(WorkspaceAuthError, match="not_authenticated"):
            get_user_credentials("unknown_user", project_id="test-project")
```

**Step 3: Run test to verify it fails**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && uv run pytest tests/workspace/test_auth.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'gemini_agent.workspace.auth'`

**Step 4: Implement `auth.py`**

Create `gemini_agent/workspace/auth.py`:

```python
"""Per-user Google OAuth credentials loaded from Secret Manager."""

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
        super().__init__(message)


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

    secret_name = f"projects/{project}/secrets/workspace-token-{user_id}/versions/latest"

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
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/workspace/test_auth.py -v`

Expected: 2 passed

**Step 6: Commit**

```bash
git add gemini_agent/workspace/ tests/
git commit -m "feat: add workspace auth helper with per-user Secret Manager tokens"
```

---

### Task 3: Drive Search Tool (`gemini_agent/workspace/drive_tools.py`)

**Files:**
- Create: `gemini_agent/workspace/drive_tools.py`
- Test: `tests/workspace/test_drive_tools.py`

**Step 1: Write failing test**

Create `tests/workspace/test_drive_tools.py`:

```python
from unittest.mock import MagicMock, patch

from gemini_agent.workspace.drive_tools import search_drive


class TestSearchDrive:
    @patch("gemini_agent.workspace.drive_tools.get_user_credentials")
    @patch("gemini_agent.workspace.drive_tools.build")
    def test_search_returns_formatted_results(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "abc123",
                    "name": "Q1 Report",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2026-03-08T10:00:00Z",
                    "owners": [{"emailAddress": "kim@example.com"}],
                },
            ]
        }

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = search_drive("Q1", tool_context=tool_context)

        assert result["total_results"] == 1
        assert result["files"][0]["id"] == "abc123"
        assert result["files"][0]["name"] == "Q1 Report"
        assert result["files"][0]["type"] == "document"

    @patch("gemini_agent.workspace.drive_tools.get_user_credentials")
    @patch("gemini_agent.workspace.drive_tools.build")
    def test_search_empty_results(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.files().list().execute.return_value = {"files": []}

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = search_drive("nonexistent", tool_context=tool_context)

        assert result["total_results"] == 0
        assert result["files"] == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workspace/test_drive_tools.py -v`

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement drive_tools.py**

Create `gemini_agent/workspace/drive_tools.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workspace/test_drive_tools.py -v`

Expected: 2 passed

**Step 5: Commit**

```bash
git add gemini_agent/workspace/drive_tools.py tests/workspace/test_drive_tools.py
git commit -m "feat: add Drive search tool"
```

---

### Task 4: Docs Read Tool (`gemini_agent/workspace/docs_tools.py`)

**Files:**
- Create: `gemini_agent/workspace/docs_tools.py`
- Test: `tests/workspace/test_docs_tools.py`

**Step 1: Write failing test**

Create `tests/workspace/test_docs_tools.py`:

```python
from unittest.mock import MagicMock, patch

from gemini_agent.workspace.docs_tools import read_document


class TestReadDocument:
    @patch("gemini_agent.workspace.docs_tools.get_user_credentials")
    @patch("gemini_agent.workspace.docs_tools.build")
    def test_read_returns_formatted_content(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.documents().get().execute.return_value = {
            "title": "Q1 Report",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Hello world\n"}},
                            ]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Second paragraph\n"}},
                            ]
                        }
                    },
                ]
            },
        }

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = read_document("doc123", tool_context=tool_context)

        assert result["title"] == "Q1 Report"
        assert "Hello world" in result["content"]
        assert "Second paragraph" in result["content"]
        assert result["word_count"] > 0
        assert "truncated" not in result or result["truncated"] is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workspace/test_docs_tools.py -v`

Expected: FAIL

**Step 3: Implement docs_tools.py**

Create `gemini_agent/workspace/docs_tools.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workspace/test_docs_tools.py -v`

Expected: 1 passed

**Step 5: Commit**

```bash
git add gemini_agent/workspace/docs_tools.py tests/workspace/test_docs_tools.py
git commit -m "feat: add Docs read tool"
```

---

### Task 5: Slides Read Tool (`gemini_agent/workspace/slides_tools.py`)

**Files:**
- Create: `gemini_agent/workspace/slides_tools.py`
- Test: `tests/workspace/test_slides_tools.py`

**Step 1: Write failing test**

Create `tests/workspace/test_slides_tools.py`:

```python
from unittest.mock import MagicMock, patch

from gemini_agent.workspace.slides_tools import read_presentation


class TestReadPresentation:
    @patch("gemini_agent.workspace.slides_tools.get_user_credentials")
    @patch("gemini_agent.workspace.slides_tools.build")
    def test_read_returns_formatted_slides(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.presentations().get().execute.return_value = {
            "title": "Project Proposal",
            "slides": [
                {
                    "pageElements": [
                        {
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "Slide Title\n"}},
                                    ]
                                },
                            }
                        },
                        {
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "Slide body text\n"}},
                                    ]
                                },
                            }
                        },
                    ],
                    "slideProperties": {
                        "notesPage": {
                            "pageElements": [
                                {
                                    "shape": {
                                        "text": {
                                            "textElements": [
                                                {"textRun": {"content": "Speaker notes\n"}},
                                            ]
                                        }
                                    }
                                }
                            ]
                        }
                    },
                },
            ],
        }

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = read_presentation("pres123", tool_context=tool_context)

        assert result["title"] == "Project Proposal"
        assert result["slide_count"] == 1
        assert result["slides"][0]["slide_number"] == 1
        assert "Slide Title" in result["slides"][0]["title"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workspace/test_slides_tools.py -v`

Expected: FAIL

**Step 3: Implement slides_tools.py**

Create `gemini_agent/workspace/slides_tools.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workspace/test_slides_tools.py -v`

Expected: 1 passed

**Step 5: Commit**

```bash
git add gemini_agent/workspace/slides_tools.py tests/workspace/test_slides_tools.py
git commit -m "feat: add Slides read tool"
```

---

### Task 6: Sheets Read Tool (`gemini_agent/workspace/sheets_tools.py`)

**Files:**
- Create: `gemini_agent/workspace/sheets_tools.py`
- Test: `tests/workspace/test_sheets_tools.py`

**Step 1: Write failing test**

Create `tests/workspace/test_sheets_tools.py`:

```python
from unittest.mock import MagicMock, patch

from gemini_agent.workspace.sheets_tools import read_spreadsheet


class TestReadSpreadsheet:
    @patch("gemini_agent.workspace.sheets_tools.get_user_credentials")
    @patch("gemini_agent.workspace.sheets_tools.build")
    def test_read_returns_formatted_data(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock spreadsheets().get() for title/sheet names
        mock_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Sales Data"},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }

        # Mock spreadsheets().values().get() for cell data
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Date", "Revenue", "Cost"],
                ["2026-01-01", "1000000", "500000"],
                ["2026-01-02", "1200000", "600000"],
            ]
        }

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = read_spreadsheet("sheet123", tool_context=tool_context)

        assert result["title"] == "Sales Data"
        assert result["sheet_name"] == "Sheet1"
        assert result["headers"] == ["Date", "Revenue", "Cost"]
        assert len(result["rows"]) == 2
        assert result["row_count"] == 2

    @patch("gemini_agent.workspace.sheets_tools.get_user_credentials")
    @patch("gemini_agent.workspace.sheets_tools.build")
    def test_read_with_custom_range(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Data"},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }

        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [["A", "B"], ["1", "2"]]
        }

        tool_context = MagicMock()
        tool_context.user_id = "user1"

        result = read_spreadsheet("sheet123", range="A1:B2", tool_context=tool_context)

        assert result["headers"] == ["A", "B"]
        assert result["rows"] == [["1", "2"]]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/workspace/test_sheets_tools.py -v`

Expected: FAIL

**Step 3: Implement sheets_tools.py**

Create `gemini_agent/workspace/sheets_tools.py`:

```python
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

        # Get spreadsheet metadata
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = meta.get("properties", {}).get("title", "Untitled")
        sheets = meta.get("sheets", [])
        sheet_name = sheets[0]["properties"]["title"] if sheets else "Sheet1"

        # Determine range
        read_range = range if range else sheet_name

        # Get values
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/workspace/test_sheets_tools.py -v`

Expected: 2 passed

**Step 5: Commit**

```bash
git add gemini_agent/workspace/sheets_tools.py tests/workspace/test_sheets_tools.py
git commit -m "feat: add Sheets read tool"
```

---

### Task 7: Register Workspace Tools in Agent (`gemini_agent/agent.py`)

**Files:**
- Modify: `gemini_agent/agent.py:141-148`

**Step 1: Add workspace tool imports and register them**

Add imports after line 25 and update `root_agent` tools list.

Add after existing imports (line 25):

```python
from gemini_agent.workspace.drive_tools import search_drive
from gemini_agent.workspace.docs_tools import read_document
from gemini_agent.workspace.slides_tools import read_presentation
from gemini_agent.workspace.sheets_tools import read_spreadsheet
```

Update `root_agent` (replace lines 141-148):

```python
root_agent = Agent(
    model=MODEL,
    name="gemini_agent",
    description="General-purpose assistant with web search, URL reading, code execution, and Google Workspace document access",
    instruction=(
        "You are a helpful assistant. Use the available tools to provide accurate and comprehensive answers. "
        "When users ask about their documents, use search_drive to find files, then use read_document, "
        "read_presentation, or read_spreadsheet to read the content."
    ),
    tools=[
        google_search, url_context, code_execution,
        search_drive, read_document, read_presentation, read_spreadsheet,
    ],
    generate_content_config=GENERATE_CONTENT_CONFIG,
)
```

**Step 2: Verify module loads**

Run: `uv run python -c "from gemini_agent import agent; print('Tools:', [t.name if hasattr(t, 'name') else t.__name__ for t in agent.root_agent.tools])"`

Expected: Should list all 7 tools including the 4 workspace tools.

**Step 3: Commit**

```bash
git add gemini_agent/agent.py
git commit -m "feat: register workspace tools in agent"
```

---

### Task 8: Cloud Run OAuth Callback Server

**Files:**
- Create: `cloud-run-oauth-callback/main.py`
- Create: `cloud-run-oauth-callback/requirements.txt`
- Create: `cloud-run-oauth-callback/Dockerfile`
- Create: `cloud-run-oauth-callback/deploy.sh`

**Step 1: Create `cloud-run-oauth-callback/requirements.txt`**

```
flask>=3.0.0,<4.0.0
google-auth>=2.20.0,<3.0.0
google-auth-oauthlib>=1.0.0,<2.0.0
google-cloud-secret-manager>=2.16.0,<3.0.0
gunicorn>=22.0.0,<23.0.0
```

**Step 2: Create `cloud-run-oauth-callback/main.py`**

```python
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
```

**Step 3: Create `cloud-run-oauth-callback/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
```

**Step 4: Create `cloud-run-oauth-callback/deploy.sh`**

```bash
#!/bin/bash
set -e

PROJECT_ID="${PROJECT_ID:?PROJECT_ID must be set}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="workspace-oauth-callback"

echo "Building and deploying Cloud Run service: $SERVICE_NAME"

gcloud run deploy $SERVICE_NAME \
    --project=$PROJECT_ID \
    --region=$REGION \
    --source=. \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
    --allow-unauthenticated \
    --memory=256Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --quiet

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --project=$PROJECT_ID \
    --region=$REGION \
    --format='value(status.url)')

echo ""
echo "Deployed: $SERVICE_URL"
echo ""
echo "IMPORTANT: Add this redirect URI to your OAuth Client ID:"
echo "  ${SERVICE_URL}/callback"
echo ""
echo "Auth URL for users:"
echo "  ${SERVICE_URL}/auth/{user_id}"
echo ""
```

**Step 5: Commit**

```bash
git add cloud-run-oauth-callback/
git commit -m "feat: add Cloud Run OAuth callback server for Google Workspace"
```

---

### Task 9: Update GCP Prerequisites Script

**Files:**
- Modify: `scripts/setup_gcp_prerequisites.sh`

**Step 1: Add Workspace APIs and oauth-client-config secret**

After the existing API list (line 34-41), add the new APIs. After the gemini-api-key secret section (line 137), add the oauth-client-config secret section.

Add to the `APIS` array (after `iamcredentials.googleapis.com`):

```bash
    "drive.googleapis.com"
    "docs.googleapis.com"
    "slides.googleapis.com"
    "sheets.googleapis.com"
    "run.googleapis.com"
```

Add the `roles/secretmanager.secretVersionAdder` role to `SA_ROLES` array (the Agent Engine SA needs to read workspace tokens, which it already can via `secretAccessor`).

Add a new step after Step 6:

```bash
# Step 7: Create Secret for OAuth Client Config
echo ""
echo "============================================================================"
echo "Step 7: Setting up OAuth Client Config Secret"
echo "============================================================================"
OAUTH_SECRET_NAME="oauth-client-config"
if gcloud secrets describe $OAUTH_SECRET_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Secret $OAUTH_SECRET_NAME already exists."
else
    log_info "Creating secret $OAUTH_SECRET_NAME..."
    gcloud secrets create $OAUTH_SECRET_NAME \
        --project=$PROJECT_ID \
        --replication-policy="automatic"
    log_success "Secret created."
fi

log_info "Add your OAuth client config:"
echo ""
echo "  echo '{\"client_id\": \"YOUR_CLIENT_ID\", \"client_secret\": \"YOUR_CLIENT_SECRET\"}' | \\"
echo "    gcloud secrets versions add $OAUTH_SECRET_NAME --data-file=-"
echo ""
```

Update the Summary section to include OAuth instructions:

```bash
echo "Next Steps:"
echo "  1. Add Gemini API key to Secret Manager"
echo "  2. Create OAuth Client ID in Cloud Console (APIs & Credentials > Web application)"
echo "  3. Add OAuth client config to Secret Manager (see above)"
echo "  4. Deploy OAuth callback: cd cloud-run-oauth-callback && bash deploy.sh"
echo "  5. Add callback URL as redirect URI in OAuth Client ID settings"
echo "  6. Deploy Agent Engine: python scripts/deploy_agent_engine.py --project $PROJECT_ID"
```

**Step 2: Commit**

```bash
git add scripts/setup_gcp_prerequisites.sh
git commit -m "feat: add Workspace APIs and OAuth config to GCP prerequisites"
```

---

### Task 10: Update Deploy Script

**Files:**
- Modify: `scripts/deploy_agent_engine.py:83-89`

**Step 1: Add workspace dependencies to REQUIREMENTS list**

Update the `REQUIREMENTS` list (lines 83-89) to include workspace dependencies:

```python
    REQUIREMENTS = [
        "google-cloud-aiplatform[adk,agent_engines]>=1.128.0",
        "google-adk>=1.15.0",
        "google-cloud-secret-manager>=2.16.0",
        "nest-asyncio>=1.5.0",
        "python-dotenv>=1.0.0",
        "google-api-python-client>=2.100.0",
        "google-auth>=2.20.0",
        "google-auth-oauthlib>=1.0.0",
    ]
```

**Step 2: Commit**

```bash
git add scripts/deploy_agent_engine.py
git commit -m "feat: add workspace dependencies to deploy script"
```

---

### Task 11: Run All Tests & Final Verification

**Step 1: Run all tests**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && uv run pytest tests/ -v`

Expected: All tests pass (auth: 2, drive: 2, docs: 1, slides: 1, sheets: 2 = 8 total)

**Step 2: Verify agent module loads with all tools**

Run: `uv run python -c "from gemini_agent import agent; print('Model:', agent.MODEL_NAME); print('Tools:', len(agent.root_agent.tools))"`

Expected: `Model: gemini-3.1-pro-preview`, `Tools: 7`

**Step 3: Final commit if needed**

```bash
git add -A
git status
# Only commit if there are changes
```
