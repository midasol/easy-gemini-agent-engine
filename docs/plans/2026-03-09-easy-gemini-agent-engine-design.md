# Easy Gemini Agent Engine - Design Document

## Overview

Simple Gemini ADK agent with built-in tools (Google Search, URL Context, Code Execution) deployed to Vertex AI Agent Engine. Based on `sap-adk-agent` project structure with all SAP/PSC components removed.

## Architecture

### Agent (`gemini_agent/agent.py`)

- **Model**: `GlobalGemini` subclass forcing global endpoint (required for Gemini 3 models on Agent Engine)
- **Model name**: `gemini-3.1-pro-preview` (overridable via `AGENT_MODEL` env var)
- **Built-in tools**: Google Search, URL Context, Code Execution — passed via `generate_content_config`
- **Thinking**: HIGH level
- **Instruction**: Minimal (general-purpose assistant)
- **API Key**: Loaded from `GEMINI_API_KEY` env var or Secret Manager (`gemini-api-key` secret)

### Project Structure

```
easy-gemini-agent-engine/
├── gemini_agent/
│   ├── __init__.py
│   └── agent.py
├── scripts/
│   ├── deploy_agent_engine.py
│   ├── cleanup_agent_engines.py
│   ├── setup_gcp_prerequisites.sh
│   └── test_agent_engine.py
├── pyproject.toml
├── .gitignore
├── .gcloudignore
└── README.md
```

### Deployment Script (`scripts/deploy_agent_engine.py`)

- Args: `--project`, `--update`, `--region`, `--staging-bucket`
- Loads `gemini-api-key` from Secret Manager → sets `GEMINI_API_KEY` env var
- Uses `agent_engines.AdkApp` with `enable_tracing=True`
- No PSC (`psc_interface_config` removed)
- No SAP credentials mapping
- `extra_packages=["./gemini_agent"]`

### GCP Prerequisites (`scripts/setup_gcp_prerequisites.sh`)

- APIs: aiplatform, secretmanager, cloudbuild, storage, iam, iamcredentials (no dns, servicenetworking)
- Service account: `agent-engine-sa` with standard roles (no networkAdmin, dns.peer)
- Secret: `gemini-api-key` (plain string, not JSON)
- No PSC infrastructure

### Dependencies (minimal)

- `google-adk>=1.15.0`
- `google-cloud-aiplatform[agent-engines]>=1.128.0`
- `google-cloud-secret-manager>=2.16.0`
- `nest-asyncio>=1.5.0`

## What was removed from sap-adk-agent

- `sap_agent/sap_gw_connector/` (SAP OData connector)
- `sap_agent/sap_auth_config.py` (SAP OAuth config)
- `sap_agent/services.yaml` (SAP service definitions)
- `cloud-run-oauth-callback/` (OAuth callback server)
- `scripts/setup_psc_infrastructure.sh` (PSC networking)
- SAP-specific test scripts
- SAP tool functions (sap_authenticate, sap_list_services, sap_query, sap_get_entity)
- Per-user authenticator/token management
- All SAP-related dependencies (xmltodict, aiohttp, authlib, cryptography, pydantic-settings, structlog, tenacity)
