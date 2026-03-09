# Easy Gemini Agent Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a simple Gemini ADK agent with built-in tools (Google Search, URL Context, Code Execution) and deploy it to Vertex AI Agent Engine.

**Architecture:** Google ADK `Agent` with `GlobalGemini` model class (forces global endpoint for Gemini 3 models). Built-in tools passed via `generate_content_config`. API Key loaded from env var or Secret Manager. Deployed via `vertexai.agent_engines`.

**Tech Stack:** Python 3.11+, google-adk, google-cloud-aiplatform, google-cloud-secret-manager, google-genai

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.gcloudignore`
- Create: `gemini_agent/__init__.py`

**Step 1: Initialize git repo**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && git init`

**Step 2: Create `pyproject.toml`**

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
]

[dependency-groups]
dev = [
    "pytest>=8.3.4,<9.0.0",
    "pytest-asyncio>=0.23.8,<1.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["gemini_agent"]

[tool.pytest.ini_options]
pythonpath = "."
asyncio_mode = "auto"
```

**Step 3: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
*.egg

# Virtual Environment
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
*~

# Environment variables
.env
.env.local
.env.*.local

# Logs
*.log

# OS
.DS_Store

# Testing
.pytest_cache/
.coverage
htmlcov/

# mypy
.mypy_cache/

# uv
uv.lock
```

**Step 4: Create `.gcloudignore`**

```
.git/
.gitignore
.venv/
venv/
__pycache__/
*.pyc
.idea/
.vscode/
.pytest_cache/
.coverage
htmlcov/
.env
.env.*
!.env.example
.DS_Store
uv.lock
docs/
tests/
```

**Step 5: Create `gemini_agent/__init__.py`**

```python
from . import agent
```

**Step 6: Commit**

```bash
git add pyproject.toml .gitignore .gcloudignore gemini_agent/__init__.py
git commit -m "chore: project scaffolding with pyproject.toml and gitignore"
```

---

### Task 2: Agent Core (`gemini_agent/agent.py`)

**Files:**
- Create: `gemini_agent/agent.py`

**Reference:** `/Users/sanggyulee/my-project/python-project/sap-adk-agent/sap_agent/agent.py` (lines 357-404 for GlobalGemini, lines 583-602 for model config, lines 1983-1994 for root_agent)

**Step 1: Create `gemini_agent/agent.py`**

```python
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
```

**Step 2: Verify module loads locally**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && python -c "from gemini_agent import agent; print('OK:', agent.MODEL_NAME)"`

Expected: Prints `OK: gemini-3.1-pro-preview` (may show warnings about missing credentials, that's fine)

**Step 3: Commit**

```bash
git add gemini_agent/agent.py
git commit -m "feat: add Gemini ADK agent with built-in tools and GlobalGemini"
```

---

### Task 3: Deploy Script (`scripts/deploy_agent_engine.py`)

**Files:**
- Create: `scripts/deploy_agent_engine.py`

**Reference:** `/Users/sanggyulee/my-project/python-project/sap-adk-agent/scripts/deploy_agent_engine.py`

**Step 1: Create `scripts/deploy_agent_engine.py`**

```python
"""Deploy Gemini Agent to Vertex AI Agent Engine.

Usage:
    # Create new Agent Engine
    python scripts/deploy_agent_engine.py --project <PROJECT_ID>

    # Update existing Agent Engine
    python scripts/deploy_agent_engine.py --project <PROJECT_ID> --update <RESOURCE_NAME>
"""

import argparse
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Deploy Gemini Agent to Vertex AI Agent Engine",
    )
    parser.add_argument(
        "--project", required=True, help="GCP project ID",
    )
    parser.add_argument(
        "--update", metavar="RESOURCE_NAME",
        help="Update existing Agent Engine (pass full resource name)",
    )
    parser.add_argument(
        "--region", default="us-central1", help="GCP region (default: us-central1)",
    )
    parser.add_argument(
        "--staging-bucket", default=None,
        help="GCS staging bucket (default: gs://<PROJECT_ID>_cloudbuild)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    PROJECT_ID = args.project
    LOCATION = args.region
    STAGING_BUCKET = args.staging_bucket or f"gs://{PROJECT_ID}_cloudbuild"

    os.environ["PROJECT_ID"] = PROJECT_ID
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

    print(f"Initializing Vertex AI SDK...")
    print(f"  Project:        {PROJECT_ID}")
    print(f"  Location:       {LOCATION}")
    print(f"  Staging Bucket: {STAGING_BUCKET}")

    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    # ---------------------------------------------------------------
    # Load API Key from Secret Manager
    # ---------------------------------------------------------------
    from google.cloud import secretmanager

    print("Loading API key from Secret Manager...")
    sm_client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{PROJECT_ID}/secrets/gemini-api-key/versions/latest"
    response = sm_client.access_secret_version(request={"name": secret_name})
    api_key = response.payload.data.decode("UTF-8").strip()
    print("  API key loaded successfully")

    env_vars = {"GEMINI_API_KEY": api_key}

    # ---------------------------------------------------------------
    # Prepare agent for deployment
    # ---------------------------------------------------------------
    import gemini_agent.agent

    print("Preparing agent for deployment...")
    print(f"  Agent Model: {gemini_agent.agent.MODEL_NAME}")

    app = agent_engines.AdkApp(
        agent=gemini_agent.agent.root_agent,
        enable_tracing=True,
    )

    SERVICE_ACCOUNT = f"agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    print(f"  Service Account: {SERVICE_ACCOUNT}")

    REQUIREMENTS = [
        "google-cloud-aiplatform[adk,agent_engines]>=1.128.0",
        "google-adk>=1.15.0",
        "google-cloud-secret-manager>=2.16.0",
        "nest-asyncio>=1.5.0",
        "python-dotenv>=1.0.0",
    ]

    RESOURCE_LIMITS = {"cpu": "2", "memory": "4Gi"}
    print(f"  Resource Limits: {RESOURCE_LIMITS}")

    # ---------------------------------------------------------------
    # Deploy / Update
    # ---------------------------------------------------------------
    try:
        if args.update:
            print(f"\nUpdating existing Agent Engine: {args.update}")
            remote_app = agent_engines.update(
                resource_name=args.update,
                agent_engine=app,
                requirements=REQUIREMENTS,
                extra_packages=["./gemini_agent"],
                display_name="Gemini Agent",
                env_vars=env_vars,
                resource_limits=RESOURCE_LIMITS,
            )
            print("Update finished!")
        else:
            print("\nCreating new Agent Engine...")
            remote_app = agent_engines.create(
                agent_engine=app,
                requirements=REQUIREMENTS,
                extra_packages=["./gemini_agent"],
                display_name="Gemini Agent",
                service_account=SERVICE_ACCOUNT,
                env_vars=env_vars,
                resource_limits=RESOURCE_LIMITS,
            )
            print("Deployment finished!")

        print(f"Resource Name: {remote_app.resource_name}")

    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scripts/deploy_agent_engine.py
git commit -m "feat: add Agent Engine deploy script"
```

---

### Task 4: Utility Scripts

**Files:**
- Create: `scripts/cleanup_agent_engines.py`
- Create: `scripts/test_agent_engine.py`

**Step 1: Create `scripts/cleanup_agent_engines.py`**

```python
"""Clean up all Agent Engines in a project."""

import os
import time
import vertexai
from vertexai import agent_engines

PROJECT_ID = os.getenv("PROJECT_ID", "[your-project-id]")
LOCATION = os.getenv("REGION", "us-central1")


def cleanup_all_engines():
    print(f"Initializing Vertex AI for project '{PROJECT_ID}' in '{LOCATION}'...")
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    print("Listing all Agent Engines...")
    try:
        engines = list(agent_engines.list())

        if not engines:
            print("No Agent Engines found to delete.")
            return

        print(f"Found {len(engines)} Agent Engines. Starting cleanup...")

        for engine in engines:
            resource_name = engine.resource_name
            print(f"\nTargeting: {resource_name}")
            print(f"  - Display Name: {engine.display_name}")

            try:
                print(f"  - Deleting with force=True...")
                engine.delete(force=True)
                print(f"  - Successfully deleted: {resource_name}")
                print("  - Waiting 10 seconds to respect rate limits...")
                time.sleep(10)
            except Exception as e:
                print(f"  - Failed to delete {resource_name}: {e}")
                if "RATE_LIMIT_EXCEEDED" in str(e):
                    print("  - Rate limit hit. Waiting 60 seconds...")
                    time.sleep(60)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    cleanup_all_engines()
```

**Step 2: Create `scripts/test_agent_engine.py`**

```python
"""Test a deployed Agent Engine."""

import os
import asyncio
import vertexai
from vertexai import agent_engines

PROJECT_ID = os.getenv("PROJECT_ID", "[your-project-id]")
LOCATION = os.getenv("REGION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", f"gs://{PROJECT_ID}_cloudbuild")
RESOURCE_NAME = os.getenv("RESOURCE_NAME", "[your-resource-name]")

print("Initializing Vertex AI SDK...")
vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)


async def main():
    print(f"Connecting to Agent Engine: {RESOURCE_NAME}")
    try:
        remote_app = agent_engines.get(RESOURCE_NAME)

        print("Creating session...")
        session = await remote_app.async_create_session(user_id="test_user")
        print(f"Session created: {session}")

        query = "What is the current weather in Seoul, South Korea?"
        print(f"\nSending query: '{query}'")

        async for event in remote_app.async_stream_query(
            user_id="test_user",
            session_id=session["id"],
            message=query,
        ):
            print(event)

    except Exception as e:
        print(f"Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Commit**

```bash
git add scripts/cleanup_agent_engines.py scripts/test_agent_engine.py
git commit -m "feat: add cleanup and test scripts for Agent Engine"
```

---

### Task 5: GCP Prerequisites Script

**Files:**
- Create: `scripts/setup_gcp_prerequisites.sh`

**Reference:** `/Users/sanggyulee/my-project/python-project/sap-adk-agent/scripts/setup_gcp_prerequisites.sh`

**Step 1: Create `scripts/setup_gcp_prerequisites.sh`**

```bash
#!/bin/bash
# ============================================================================
# GCP Prerequisites Setup for Gemini Agent Engine
# ============================================================================
set -e

PROJECT_ID="${PROJECT_ID:-[your-project-id]}"
REGION="${REGION:-us-central1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Step 0: Set Project
echo ""
echo "============================================================================"
echo "Step 0: Setting up GCP project"
echo "============================================================================"
gcloud config set project $PROJECT_ID
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
log_success "Project Number: $PROJECT_NUMBER"

# Step 1: Enable APIs
echo ""
echo "============================================================================"
echo "Step 1: Enabling required APIs"
echo "============================================================================"
APIS=(
    "aiplatform.googleapis.com"
    "secretmanager.googleapis.com"
    "cloudbuild.googleapis.com"
    "storage.googleapis.com"
    "iam.googleapis.com"
    "iamcredentials.googleapis.com"
)
for api in "${APIS[@]}"; do
    log_info "Enabling $api..."
    gcloud services enable $api --quiet
done
log_success "All required APIs enabled."

# Step 2: Create Service Account
echo ""
echo "============================================================================"
echo "Step 2: Creating Service Account"
echo "============================================================================"
SA_NAME="agent-engine-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Service account $SA_NAME already exists."
else
    log_info "Creating service account $SA_NAME..."
    gcloud iam service-accounts create $SA_NAME \
        --project=$PROJECT_ID \
        --display-name="Gemini Agent Engine Service Account"
    log_success "Service account created: $SA_EMAIL"
fi

# Step 3: Assign IAM Roles
echo ""
echo "============================================================================"
echo "Step 3: Assigning IAM roles"
echo "============================================================================"
SA_ROLES=(
    "roles/aiplatform.user"
    "roles/secretmanager.secretAccessor"
    "roles/storage.objectViewer"
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
    "roles/serviceusage.serviceUsageConsumer"
)
for role in "${SA_ROLES[@]}"; do
    log_info "Granting $role to $SA_NAME..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --condition=None \
        --quiet
done
log_success "All roles assigned."

# Step 4: Configure Service Agents
echo ""
echo "============================================================================"
echo "Step 4: Configuring GCP-managed Service Agents"
echo "============================================================================"
SERVICE_AGENTS=(
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
    "service-${PROJECT_NUMBER}@gcp-sa-aiplatform-cc.iam.gserviceaccount.com"
)
for sa in "${SERVICE_AGENTS[@]}"; do
    log_info "Granting serviceUsageConsumer to $sa..."
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$sa" \
        --role="roles/serviceusage.serviceUsageConsumer" \
        --condition=None \
        --quiet 2>/dev/null || log_warning "Could not grant role to $sa (may not exist yet)"
done
log_success "Service agents configured."

# Step 5: Create Staging Bucket
echo ""
echo "============================================================================"
echo "Step 5: Setting up Staging Bucket"
echo "============================================================================"
STAGING_BUCKET="${PROJECT_ID}_cloudbuild"
if gsutil ls -b gs://$STAGING_BUCKET > /dev/null 2>&1; then
    log_warning "Staging bucket gs://$STAGING_BUCKET already exists."
else
    log_info "Creating staging bucket gs://$STAGING_BUCKET..."
    gsutil mb -l $REGION gs://$STAGING_BUCKET
    log_success "Staging bucket created."
fi

# Step 6: Create Secret for API Key
echo ""
echo "============================================================================"
echo "Step 6: Setting up Secret Manager for API Key"
echo "============================================================================"
SECRET_NAME="gemini-api-key"
if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    log_warning "Secret $SECRET_NAME already exists."
else
    log_info "Creating secret $SECRET_NAME..."
    gcloud secrets create $SECRET_NAME \
        --project=$PROJECT_ID \
        --replication-policy="automatic"
    log_success "Secret created."
fi

log_info "Add your Gemini API key:"
echo ""
echo "  echo 'YOUR_GEMINI_API_KEY' | gcloud secrets versions add $SECRET_NAME --data-file=-"
echo ""

# Summary
echo ""
echo "============================================================================"
echo "Setup Complete!"
echo "============================================================================"
echo ""
log_success "Project: $PROJECT_ID"
log_success "Region: $REGION"
log_success "Service Account: $SA_EMAIL"
log_success "Staging Bucket: gs://$STAGING_BUCKET"
log_success "Secret Name: $SECRET_NAME"
echo ""
echo "Next Steps:"
echo "  1. Add Gemini API key to Secret Manager"
echo "  2. Run: python scripts/deploy_agent_engine.py --project $PROJECT_ID"
echo ""
```

**Step 2: Make executable**

Run: `chmod +x scripts/setup_gcp_prerequisites.sh`

**Step 3: Commit**

```bash
git add scripts/setup_gcp_prerequisites.sh
git commit -m "feat: add GCP prerequisites setup script"
```

---

### Task 6: README

**Files:**
- Create: `README.md`

**Step 1: Create `README.md`**

```markdown
# Easy Gemini Agent Engine

Simple Gemini ADK agent with built-in tools deployed to Vertex AI Agent Engine.

## Features

- **Google Search** - Real-time web search
- **URL Context** - Read and analyze web pages
- **Code Execution** - Execute Python code
- **Thinking (HIGH)** - Enhanced reasoning capabilities
- **Gemini 3.1 Pro Preview** model with global endpoint

## Prerequisites

- Python 3.11+
- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Gemini API key

## Quick Start

### 1. Set up GCP resources

```bash
export PROJECT_ID="your-project-id"
bash scripts/setup_gcp_prerequisites.sh
```

### 2. Add your Gemini API key to Secret Manager

```bash
echo "YOUR_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

### 3. Deploy to Agent Engine

```bash
python scripts/deploy_agent_engine.py --project $PROJECT_ID
```

### 4. Test the deployed agent

```bash
export RESOURCE_NAME="projects/.../reasoningEngines/..."
python scripts/test_agent_engine.py
```

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup_gcp_prerequisites.sh` | Set up GCP APIs, service account, IAM, secrets |
| `scripts/deploy_agent_engine.py` | Deploy or update Agent Engine |
| `scripts/test_agent_engine.py` | Test deployed agent |
| `scripts/cleanup_agent_engines.py` | Delete all Agent Engines in project |

## Update Existing Deployment

```bash
python scripts/deploy_agent_engine.py --project $PROJECT_ID --update <RESOURCE_NAME>
```

## Local Development

```bash
# Install dependencies
uv sync

# Set API key
export GEMINI_API_KEY="your-api-key"

# Verify agent loads
python -c "from gemini_agent import agent; print(agent.MODEL_NAME)"
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with quick start guide"
```

---

### Task 7: Install Dependencies & Verify

**Step 1: Create venv and install**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && uv sync`

**Step 2: Verify agent module loads**

Run: `cd /Users/sanggyulee/my-project/python-project/easy-gemini-agent-engine && uv run python -c "from gemini_agent import agent; print('Model:', agent.MODEL_NAME)"`

Expected: `Model: gemini-3.1-pro-preview`

**Step 3: Final commit if any adjustments needed**

```bash
git add -A
git commit -m "chore: verify project setup and dependencies"
```
