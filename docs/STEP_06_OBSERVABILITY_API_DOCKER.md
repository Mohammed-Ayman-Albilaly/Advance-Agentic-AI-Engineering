# Step 6 — Observability, FastAPI & Docker

## Goal
Add production-facing observability and a reproducible service boundary without weakening the agentic architecture implemented in Steps 1–5.

## Structured Observability
UniFlow AI now emits machine-readable JSON Lines logs instead of relying on `print()` statements.

Captured fields include:
- timestamp
- event type
- thread ID
- graph node
- agent name
- tool name
- success/failure
- latency
- retry/re-plan events
- guardrail blocks
- human approval outcomes
- HTTP request status and latency

Logs are written to `LOG_PATH` (default: `logs/uniflow.jsonl`) using a rotating file handler.

## Prometheus Metrics
A dedicated Prometheus registry exposes `/metrics` with:
- `uniflow_workflow_executions_total`
- `uniflow_tool_calls_total`
- `uniflow_tool_latency_seconds`
- `uniflow_node_executions_total`
- `uniflow_node_latency_seconds`
- `uniflow_replans_total`
- `uniflow_guardrail_blocks_total`
- `uniflow_approval_decisions_total`
- `uniflow_api_requests_total`
- `uniflow_api_request_latency_seconds`

## FastAPI Surface
Implemented endpoints:
- `GET /health`
- `GET /metrics`
- `POST /courses`
- `GET /courses`
- `POST /tasks`
- `GET /tasks`
- `PATCH /tasks/{task_id}/status`
- `POST /availability`
- `GET /availability`
- `POST /workflow/start`
- `GET /workflow/{thread_id}`
- `POST /workflow/{thread_id}/resume`
- `GET /plans/{thread_id}`

Workflow endpoints use the genuine LangGraph runtime when the LangGraph dependencies are installed. They fail safely with HTTP 503 if those runtime dependencies are unavailable instead of silently substituting a fake workflow.

## Docker Artifact
The repository now contains:
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

The container runs as a non-root user, exposes port 8000, includes a healthcheck, and mounts persistent volumes for application/checkpoint data and logs.

## Executed Evidence
### Live HTTP execution
A real Uvicorn process was started locally in the preparation environment and returned:

```text
GET /health -> 200
{"status":"ok","app":"UniFlow AI","environment":"test"}

GET /metrics -> 200
uniflow_api_requests_total{method="GET",route="/health",status_code="200"} 1.0
```

See:
- `evidence/step06_uvicorn.log`
- `evidence/step06_live_http.txt`

### Real tool observability
The Coordinator Agent executed three real tools and emitted structured logs and Prometheus metrics:

```text
REAL_TOOL_CALLS: ['get_courses', 'get_tasks', 'get_availability_windows']
TOOL_CALL_SUCCESS: True
```

See:
- `evidence/step06_observability_api.txt`
- `evidence/step06-structured.jsonl`

### Tests
The complete regression suite is captured in:
- `evidence/step06_test_run.txt`

The only skipped tests are the existing real LangGraph/checkpoint runtime tests because the sandbox cannot install LangGraph. Those remain mandatory before final submission.

## Docker Runtime Limitation
The Docker CLI is not installed in the preparation sandbox. The Docker/Compose artifacts are statically tested (including YAML parsing), but a real `docker compose up --build` run must still be captured on a Docker-enabled machine before final submission evidence is declared complete.
