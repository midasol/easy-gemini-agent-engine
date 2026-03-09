"""Simple Gemini Agent with built-in tools for Agent Engine deployment.

Uses Google Search, URL Context, and Code Execution as built-in Gemini tools.
Supports both local development and Agent Engine deployment.
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
from google.adk.tools import google_search, url_context
from google.adk.tools.base_tool import BaseTool
from google.genai import Client, types

from gemini_agent.workspace.drive_tools import search_drive
from gemini_agent.workspace.docs_tools import read_document
from gemini_agent.workspace.slides_tools import read_presentation
from gemini_agent.workspace.sheets_tools import read_spreadsheet

# ---------------------------------------------------------------------------
# Secret Manager helper
# ---------------------------------------------------------------------------
_secretmanager = None


def _get_api_key() -> str | None:
    """Get Gemini API Key from env var or Secret Manager."""
    # 1. Check environment variable first (local dev or deploy-injected)
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key

    # 2. Try Secret Manager
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
    """Gemini model subclass that forces global endpoint.

    Agent Engine overrides GOOGLE_CLOUD_LOCATION to the deployment region,
    but Gemini 3 models require the global endpoint.
    """

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

        # Agent Engine (Vertex AI) does NOT support API keys.
        # Use API key only for local development (no project set).
        # On Agent Engine, always use service account auth + global endpoint.
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
def get_model_name() -> str:
    return os.getenv("AGENT_MODEL", "gemini-3.1-pro-preview")


MODEL_NAME = get_model_name()
MODEL = GlobalGemini(model=MODEL_NAME)

# ---------------------------------------------------------------------------
# CodeExecutionTool: ADK wrapper for Gemini built-in code execution
# ---------------------------------------------------------------------------
class CodeExecutionTool(BaseTool):
    """ADK tool wrapper for Gemini's built-in code execution capability."""

    def __init__(self):
        super().__init__(name="code_execution", description="code_execution")

    async def process_llm_request(self, *, tool_context, llm_request):
        llm_request.config = llm_request.config or types.GenerateContentConfig()
        llm_request.config.tools = llm_request.config.tools or []
        llm_request.config.tools.append(
            types.Tool(code_execution=types.ToolCodeExecution())
        )


code_execution = CodeExecutionTool()

# ---------------------------------------------------------------------------
# Thinking config (no tools — tools go through ADK tool system)
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

logger.info(f"Agent initialized: model={MODEL_NAME}")
