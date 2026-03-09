# Google Workspace Integration Design

## Overview

Google OAuth를 활용하여 유저가 접근 가능한 Google Docs, Slides, Sheets, Drive 문서를 에이전트가 조회할 수 있도록 하는 기능. Google API Client를 직접 사용하는 Tool function 기반 접근 방식.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   유저       │────▶│  Cloud Run       │────▶│  Secret Manager     │
│ (브라우저)   │◀────│  OAuth Callback  │     │  (per-user tokens)  │
└─────────────┘     └──────────────────┘     └─────────┬───────────┘
                                                        │
┌─────────────┐     ┌──────────────────┐               │
│   클라이언트 │────▶│  Agent Engine    │◀──────────────┘
│ (API 호출)   │◀────│  (Gemini ADK)    │
└─────────────┘     └───────┬──────────┘
                            │
                    ┌───────▼──────────┐
                    │  Google APIs     │
                    │  - Drive v3      │
                    │  - Docs v1       │
                    │  - Slides v1     │
                    │  - Sheets v4     │
                    └──────────────────┘
```

### Flow

1. **유저 인증**: Cloud Run OAuth callback 서버 `/auth/{user_id}` → Google 동의 화면 → callback → refresh token → Secret Manager `workspace-token-{user_id}`에 저장
2. **에이전트 사용**: 클라이언트가 Agent Engine에 `user_id` 포함 쿼리 → Gemini가 workspace tool 호출 → Secret Manager에서 refresh token 로드 → access token 발급 → Google API 호출

### OAuth Scopes

```python
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
```

## Cloud Run OAuth Callback Server

### Structure

```
cloud-run-oauth-callback/
├── main.py
├── Dockerfile
├── requirements.txt
└── deploy.sh
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/{user_id}` | GET | Google OAuth 동의 화면으로 리다이렉트 |
| `/callback` | GET | OAuth callback → refresh token을 Secret Manager에 저장 |
| `/status/{user_id}` | GET | 유저 인증 상태 확인 |
| `/revoke/{user_id}` | POST | 유저 token 삭제 (연결 해제) |

### Core Logic

- `/auth/{user_id}`: user_id를 state에 포함 + CSRF 토큰, Google OAuth URL로 리다이렉트
- `/callback`: authorization code → token 교환 → Secret Manager에 `workspace-token-{user_id}` 저장 (JSON: refresh_token, client_id, client_secret)

### Security

- `/revoke`는 인증된 관리자만 호출 가능
- `state` 파라미터에 CSRF 방지용 랜덤 토큰 포함
- Cloud Run은 IAP 또는 조직 내부 접근으로 제한 가능

## Agent Tool Functions

### File Structure

```
gemini_agent/workspace/
├── __init__.py
├── auth.py              # Secret Manager → Credentials
├── drive_tools.py       # search_drive
├── docs_tools.py        # read_document
├── slides_tools.py      # read_presentation
└── sheets_tools.py      # read_spreadsheet
```

### auth.py

```python
def get_user_credentials(user_id: str) -> google.oauth2.credentials.Credentials:
    # Secret Manager에서 workspace-token-{user_id} 로드
    # refresh_token으로 Credentials 객체 생성 (access_token 자동 갱신)
```

### Tools

| Tool | Function | Parameters | Description |
|------|----------|-----------|-------------|
| Drive 검색 | `search_drive` | `query: str`, `max_results: int = 10` | Drive API `files.list`로 검색 |
| Docs 읽기 | `read_document` | `document_id: str` | Docs API로 전체 텍스트 추출 |
| Slides 읽기 | `read_presentation` | `presentation_id: str` | Slides API로 슬라이드별 텍스트/노트 추출 |
| Sheets 읽기 | `read_spreadsheet` | `spreadsheet_id: str`, `range: str = ""` | Sheets API로 셀 데이터 조회 |

### user_id 전달

ADK `tool_context.user_id`를 통해 세션의 user_id를 가져옴.

## Error Handling

| Scenario | Handling |
|----------|----------|
| 유저 토큰 없음 | `not_authenticated` 에러 + 인증 URL 안내 |
| 토큰 만료 + refresh 실패 | 토큰 삭제 → 재인증 안내 |
| 문서 접근 권한 없음 (403) | `access_denied` 에러 반환 |
| 문서 미존재 (404) | `not_found` 에러 반환 |
| API 할당량 초과 (429) | exponential backoff 1회 재시도 |

### Large Document Handling

- Docs/Slides: 50,000자 초과 시 truncate + `truncated: true`
- Sheets: 500행 초과 시 truncate
- Drive 검색: max_results 기본 10, 최대 50

## Response Formats

```python
# search_drive
{"total_results": 3, "files": [{"id": "...", "name": "...", "type": "document", "modified": "...", "owner": "..."}]}

# read_document
{"title": "...", "content": "...", "word_count": 1523}

# read_presentation
{"title": "...", "slide_count": 12, "slides": [{"slide_number": 1, "title": "...", "body": "...", "notes": "..."}]}

# read_spreadsheet
{"title": "...", "sheet_name": "Sheet1", "row_count": 50, "headers": [...], "rows": [[...]]}
```

## GCP Infrastructure

### Additional APIs

```
drive.googleapis.com
docs.googleapis.com
slides.googleapis.com
sheets.googleapis.com
run.googleapis.com
```

### Additional Secrets

- `oauth-client-config`: OAuth client_id / client_secret (JSON)
- `workspace-token-{user_id}`: per-user refresh token (자동 생성)

### IAM

- Agent Engine SA: `roles/secretmanager.secretAccessor` (기존)
- Cloud Run SA: `roles/secretmanager.secretAccessor` + `roles/secretmanager.secretVersionAdder`

### Additional Dependencies (pyproject.toml)

```toml
"google-api-python-client>=2.100.0,<3.0.0"
"google-auth>=2.20.0,<3.0.0"
"google-auth-oauthlib>=1.0.0,<2.0.0"
```

## Final Project Structure

```
easy-gemini-agent-engine/
├── gemini_agent/
│   ├── __init__.py
│   ├── agent.py
│   └── workspace/
│       ├── __init__.py
│       ├── auth.py
│       ├── drive_tools.py
│       ├── docs_tools.py
│       ├── slides_tools.py
│       └── sheets_tools.py
├── cloud-run-oauth-callback/
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── deploy.sh
├── scripts/
│   ├── setup_gcp_prerequisites.sh
│   ├── deploy_agent_engine.py
│   ├── test_agent_engine.py
│   └── cleanup_agent_engines.py
├── pyproject.toml
├── README.md
└── .gitignore
```

## Future Work

- 공유/권한 관리 tool 추가 (`share_document`, `update_permissions`)
- 파일 메타데이터 조회 tool
- 파일 다운로드/내보내기 tool
