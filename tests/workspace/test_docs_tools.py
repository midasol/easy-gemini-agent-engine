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
