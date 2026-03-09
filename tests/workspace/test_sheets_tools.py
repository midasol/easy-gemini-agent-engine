from unittest.mock import MagicMock, patch

from gemini_agent.workspace.sheets_tools import read_spreadsheet


class TestReadSpreadsheet:
    @patch("gemini_agent.workspace.sheets_tools.get_user_credentials")
    @patch("gemini_agent.workspace.sheets_tools.build")
    def test_read_returns_formatted_data(self, mock_build, mock_get_creds):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Sales Data"},
            "sheets": [{"properties": {"title": "Sheet1"}}],
        }

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
