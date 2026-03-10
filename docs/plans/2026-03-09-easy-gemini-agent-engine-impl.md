# Easy Gemini Agent Engine - Deployment Guide

This guide covers deploying the Gemini ADK agent with Google Search and Workspace tools to Vertex AI Agent Engine, and registering it with Gemini Enterprise for end-user access.

## Prerequisites

- Python 3.11+, `uv` package manager
- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Access to Gemini Enterprise admin console

## Step 1: GCP Setup

```bash
export PROJECT_ID="your-project-id"
bash scripts/setup_gcp_prerequisites.sh
```

This creates:
- Required APIs (aiplatform, secretmanager, cloudbuild, storage, iam)
- Service account `agent-engine-sa` with appropriate roles
- Staging bucket `gs://$PROJECT_ID_cloudbuild`
- Secret `gemini-api-key` in Secret Manager

## Step 2: Deploy to Agent Engine

### New deployment

```bash
python scripts/deploy_agent_engine.py --project $PROJECT_ID
```

### Update existing deployment

```bash
python scripts/deploy_agent_engine.py \
  --project $PROJECT_ID \
  --update "projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/ENGINE_ID"
```

Save the **Resource Name** from the output (e.g., `projects/123/locations/us-central1/reasoningEngines/456`).

## Step 3: Create OAuth 2.0 Client

1. Go to **Google Cloud Console** > **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Add **Authorized redirect URIs**:
   - `https://vertexaisearch.cloud.google.com/oauth-redirect`
   - `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`
5. Note the **Client ID** and **Client Secret**

## Step 4: Create Authorization Resource

Construct the Authorization URI with the following parameters:

| Parameter | Value |
|-----------|-------|
| Base URL | `https://accounts.google.com/o/oauth2/v2/auth` |
| `client_id` | Your OAuth Client ID |
| `redirect_uri` | `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html` |
| `scope` | `drive.readonly`, `documents.readonly`, `presentations.readonly`, `spreadsheets.readonly`, `cloud-platform` (각각 `https://www.googleapis.com/auth/` 접두사) |
| `include_granted_scopes` | `true` |
| `response_type` | `code` |
| `access_type` | `offline` |
| `prompt` | `consent` |

> **Note**: `scope`의 여러 스코프 사이 공백은 `%20`으로 인코딩해야 합니다.

Create the authorization resource via REST API:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: $PROJECT_ID" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/authorizations?authorizationId=workspace-tools" \
  -d '{
    "displayName": "Workspace Tools Auth",
    "server_side_oauth2": {
      "client_id": "YOUR_OAUTH_CLIENT_ID",
      "client_secret": "YOUR_OAUTH_CLIENT_SECRET",
      "token_uri": "https://oauth2.googleapis.com/token",
      "authorization_uri": "YOUR_AUTHORIZATION_URI"
    }
  }'
```

> **Note**: The `authorizationId` (`workspace-tools`) must match `CLIENT_AUTH_NAME` in `gemini_agent/workspace.py`.

## Step 5: Register Agent in Gemini Enterprise

```bash
APP_ID="your-gemini-enterprise-app-id"

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: $PROJECT_ID" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$APP_ID/assistants/default_assistant/agents" \
  -d '{
    "displayName": "Gemini Agent",
    "description": "Assistant with web search and Google Workspace document access",
    "adk_agent_definition": {
      "provisioned_reasoning_engine": {
        "reasoning_engine": "projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/ENGINE_ID"
      }
    },
    "authorization_config": {
      "tool_authorizations": [
        "projects/PROJECT_NUMBER/locations/global/authorizations/workspace-tools"
      ]
    }
  }'
```

### Critical: `tool_authorizations` vs `agent_authorization`

| Field | Behavior |
|-------|----------|
| `authorization_config.tool_authorizations` | Token injected into `tool_context.state` per tool call. **Use this.** |
| `authorization_config.agent_authorization` | Agent-level auth — does NOT inject token into `tool_context.state`. |

## Step 6: Verify

1. Open Gemini Enterprise web app
2. Select the registered agent (`Gemini Agent`)
3. Send a message requesting Workspace content, e.g.:
   - "이 문서 요약해줘: https://docs.google.com/document/d/DOC_ID/edit"
   - "내 드라이브에서 프로젝트 관련 파일 검색해줘"
4. An **authorization button** should appear
5. Click to authorize via Google OAuth
6. The agent reads and responds with the document content

## Managing Agents

### List agents

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: $PROJECT_ID" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$APP_ID/assistants/default_assistant/agents" \
  | python3 -m json.tool
```

### Delete an agent

```bash
AGENT_ID="agent-id-from-list"

curl -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: $PROJECT_ID" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/collections/default_collection/engines/$APP_ID/assistants/default_assistant/agents/$AGENT_ID"
```

### List authorization resources

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/$PROJECT_NUMBER/locations/global/authorizations" \
  | python3 -m json.tool
```

## Troubleshooting

### Authorization button doesn't appear

- Verify agent is registered with `tool_authorizations` (not `agent_authorization`)
- Check that the authorization resource exists and is linked to the agent
- Ensure only one agent uses a given authorization resource

### `tool_context.state` is empty

- Confirm `CLIENT_AUTH_NAME` in `workspace.py` matches the authorization resource ID
- Check that the agent was registered with `tool_authorizations`
- Look for token keys: exact match (`workspace-tools`), numbered pattern (`workspace-tools_123`), or any long string

### AFC disabled warning

- Ensure `GoogleSearchTool(bypass_multi_tools_limit=True)` is used
- Do NOT use `url_context` or `code_execution` alongside custom function tools

### OAuth redirect_uri mismatch

- Add both redirect URIs to OAuth Client:
  - `https://vertexaisearch.cloud.google.com/oauth-redirect`
  - `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`
- Authorization URI must use `redirect_uri=.../static/oauth/oauth.html`

### Check Agent Engine logs

```bash
ENGINE_ID="your-engine-id"

gcloud logging read \
  'resource.type="aiplatform.googleapis.com/ReasoningEngine" resource.labels.reasoning_engine_id="'$ENGINE_ID'"' \
  --project=$PROJECT_ID \
  --limit=30 \
  --format='value(timestamp, severity, textPayload)' \
  --freshness=10m
```
