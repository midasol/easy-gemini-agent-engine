"""Gemini Agent with Google Search and Google Workspace tools.

Uses GoogleSearchTool (bypass mode) for AFC compatibility with custom functions.
Workspace tools use OAuth token injected by Gemini Enterprise via tool_context.state.
"""

import os
import logging
from functools import cached_property

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# Enable nested event loops for Agent Engine compatibility
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from google.adk.agents.llm_agent import Agent
from google.adk.models import Gemini
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.genai import Client, types

from gemini_agent.workspace import (
    search_drive,
    read_document,
    read_presentation,
    read_spreadsheet,
)

# ---------------------------------------------------------------------------
# Secret Manager helper
# ---------------------------------------------------------------------------
_secretmanager = None


def _get_api_key() -> str | None:
    """Get Gemini API Key from env var or Secret Manager."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if not project_id:
        return None

    try:
        global _secretmanager
        if _secretmanager is None:
            from google.cloud import secretmanager
            _secretmanager = secretmanager

        client = _secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/gemini-api-key/versions/latest"
        response = client.access_secret_version(request={"name": name})
        api_key = response.payload.data.decode("UTF-8").strip()
        logger.info("Loaded API key from Secret Manager")
        return api_key
    except Exception as e:
        logger.warning(f"Failed to load API key from Secret Manager: {e}")
        return None


# ---------------------------------------------------------------------------
# GlobalGemini: forces global endpoint for Gemini 3 models
# ---------------------------------------------------------------------------
class GlobalGemini(Gemini):
    """Gemini model subclass that forces global endpoint."""

    @cached_property
    def api_client(self) -> Client:
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID", "")
        api_key = _get_api_key()

        client_kwargs: dict = {
            "http_options": types.HttpOptions(
                headers=self._tracking_headers(),
                retry_options=self.retry_options,
            ),
        }

        is_agent_engine = bool(os.getenv("GOOGLE_CLOUD_PROJECT"))

        if api_key and not is_agent_engine:
            client_kwargs["api_key"] = api_key
            logger.info("Using API key authentication (local)")
        else:
            client_kwargs["project"] = project
            client_kwargs["location"] = "global"
            logger.info("Using service account authentication (global endpoint)")

        return Client(**client_kwargs)


# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.getenv("AGENT_MODEL", "gemini-3.1-pro-preview")
MODEL = GlobalGemini(model=MODEL_NAME)

# ---------------------------------------------------------------------------
# Google Search (bypass mode for AFC compatibility with custom functions)
# ---------------------------------------------------------------------------
google_search = GoogleSearchTool(bypass_multi_tools_limit=True)

# ---------------------------------------------------------------------------
# Thinking config
# ---------------------------------------------------------------------------
GENERATE_CONTENT_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="HIGH",
    ),
)

# ---------------------------------------------------------------------------
# Root Agent
# ---------------------------------------------------------------------------
root_agent = Agent(
    model=MODEL,
    name="gemini_agent",
    description="General-purpose assistant with web search and Google Workspace document access",
    instruction=(
        "You are a helpful assistant. Use the available tools to provide accurate and comprehensive answers.\n\n"
        "IMPORTANT: When a user provides a Google Docs/Slides/Sheets URL or asks about their documents:\n"
        "1. Extract the document ID from the URL (the long string between /d/ and /edit or /view)\n"
        "2. Call the appropriate tool: read_document for Docs, read_presentation for Slides, read_spreadsheet for Sheets\n"
        "3. ALWAYS call the tool - never say you cannot access the document without trying first\n\n"
        "For Google Docs URLs like docs.google.com/document/d/DOCUMENT_ID/edit, call read_document with the document_id\n"
        "For Google Slides URLs like docs.google.com/presentation/d/PRESENTATION_ID/edit, call read_presentation with the presentation_id\n"
        "For Google Sheets URLs like docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit, call read_spreadsheet with the spreadsheet_id\n"
        "To search for files in Drive, use search_drive with a query"
    ),
    tools=[
        google_search,
        search_drive,
        read_document,
        read_presentation,
        read_spreadsheet,
    ],
    generate_content_config=GENERATE_CONTENT_CONFIG,
)

logger.info(f"Agent initialized: model={MODEL_NAME}")
