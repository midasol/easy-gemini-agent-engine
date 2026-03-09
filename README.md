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
