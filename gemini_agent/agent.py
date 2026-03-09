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
from google.genai import Client, types

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

        if api_key:
            client_kwargs["api_key"] = api_key
            logger.info("Using API key authentication")
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
# Built-in Tools & Thinking via generate_content_config
# ---------------------------------------------------------------------------
GENERATE_CONTENT_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="HIGH",
    ),
    tools=[
        types.Tool(google_search=types.GoogleSearch()),
        types.Tool(url_context=types.UrlContext()),
        types.Tool(code_execution=types.ToolCodeExecution()),
    ],
)

# ---------------------------------------------------------------------------
# Root Agent
# ---------------------------------------------------------------------------
root_agent = Agent(
    model=MODEL,
    name="gemini_agent",
    description="General-purpose assistant with web search, URL reading, and code execution capabilities",
    instruction="You are a helpful assistant. Use the available tools to provide accurate and comprehensive answers.",
    generate_content_config=GENERATE_CONTENT_CONFIG,
)

logger.info(f"Agent initialized: model={MODEL_NAME}")
