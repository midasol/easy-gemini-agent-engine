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
