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
