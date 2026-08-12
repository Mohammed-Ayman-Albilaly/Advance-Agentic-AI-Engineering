# UniFlow AI

**UniFlow AI** is a stateful multi-agent university study and task coordination system built for the **Advanced Agentic AI Systems Engineering** capstone.

The system converts persisted courses, academic tasks, deadlines, and study availability into a reviewed study plan. It combines OpenAI function calling, a LangGraph state graph, specialized agents, real Python/SQLite tools, security guardrails, human approval, persistent checkpoints, structured observability, FastAPI, and Docker packaging.

> **Capstone status:** implementation through Step 08 is complete. Automated tests and the locally available execution paths are captured. The final submission gate remains intentionally red until three environment-dependent proof runs succeed: live OpenAI function calling, real LangGraph re-plan + durable HITL restart/resume, and live Docker execution. See `docs/FINAL_SUBMISSION_CHECKLIST.md`.

## Problem
A normal to-do list stores deadlines but does not reason about urgency, workload, feasibility, conflicts, or re-planning. UniFlow AI adds an agentic workflow that inspects real persisted data, creates a schedule, reviews it, loops when the plan is infeasible, pauses for human approval, and persists the approved result.

## Architecture

```text
User
  ↓
Input Guardrail
  ├── blocked → END
  ↓
Coordinator Agent
  │   └── OpenAI function calling → real SQLite tools
  ↓
Task Analysis Agent
  ↓
Planning Agent ←────────────────────────┐
  ↓                                     │
Reviewer Agent                          │
  ├── re-plan ──────────────────────────┘
  ├── retry exhausted → Failed → END
  ↓ approved
Human Approval (LangGraph interrupt)
  ├── reject + feedback ────────────────┐
  └── approve                           │
       ↓                                │
Persist Final Plan                      │
       ↓                                │
Output Guardrail                        │
       ↓                                │
      END                               │
                                        └── Planning Agent
```

### Agents
- **CoordinatorAgent** — centralized coordinator. In live mode, it uses OpenAI Responses API function calling to inspect real project context.
- **TaskAnalysisAgent** — calculates urgency/priority and workload inputs through real tools.
- **PlanningAgent** — implements the plan stage and switches strategy after reviewer feedback.
- **ReviewerAgent** — independently validates capacity, deadlines, conflicts, and completeness.

### Reasoning pattern
The primary named course pattern is **Plan-and-Execute**. Reviewer self-critique strengthens the execution loop without replacing the explicit Plan-and-Execute design.

## Real tools
The project implements and executes real validated functions, including:

```text
add_course                    get_courses
add_task                      get_tasks
update_task_status            set_availability
get_available_hours           get_availability_windows
calculate_task_priority       calculate_weekly_workload
check_deadline_conflicts      validate_plan_capacity
save_study_plan               load_study_plan
```

The live LLM coordinator can call read-only context tools. The model never controls `user_id`; user scope is injected by trusted application code.

## Security
- Input prompt-injection/control-bypass guardrail.
- Output schema/data validation.
- Email and Saudi mobile-number masking.
- Secret-bearing output field blocking.
- SQLite ownership constraints.
- User-scoped plan loading.
- LLM tool schemas prevent model-controlled cross-user identifiers.
- Secrets only through environment variables / deployment secrets.
- Strict LangGraph checkpoint msgpack deserialization is enforced before opening the SQLite saver.

A real prompt-injection attack and output-protection path are captured in `evidence/`.

## Observability
Machine-readable JSON Lines logs and Prometheus metrics capture:

- tool calls and latency
- node success/failure and latency
- retries/re-plans
- guardrail blocks
- human approval/rejection
- workflow outcomes
- API request status/latency
- LLM calls, provider/model, latency, token counts, and failures

Metrics are exposed at `GET /metrics`.

## Persistence and HITL
Application data is stored in SQLite. LangGraph workflow state uses a separate file-backed SQLite checkpointer. A reviewer-approved plan reaches a real `interrupt()` node, and the same `thread_id` is used to resume after human input.

Final evidence must prove that this pause survives an application restart before submission.

## API
Main endpoints:

```text
GET   /health
GET   /metrics
POST  /courses
GET   /courses
POST  /tasks
GET   /tasks
PATCH /tasks/{task_id}/status
POST  /availability
GET   /availability
POST  /workflow/start
GET   /workflow/{thread_id}
POST  /workflow/{thread_id}/resume
GET   /plans/{thread_id}
```

## Requirements
- Python 3.11+ (Docker image uses Python 3.12)
- Project dependencies from `requirements.txt`
- For live agent evidence: an OpenAI API key
- For container evidence: Docker with Docker Compose

## Setup

### 1. Create a virtual environment

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env`.

Offline/test mode:

```env
LLM_PROVIDER=not_configured
LLM_MODEL=
OPENAI_API_KEY=
```

Live capstone mode:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.5
OPENAI_API_KEY=your_key_here
```

Never commit `.env` or a real API key.

### 4. Initialize database

```bash
python -m scripts.init_db
```

### 5. Run tests

```bash
python -m pytest -q
```

### 6. Run FastAPI

```bash
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Open the generated FastAPI docs at `/docs` and metrics at `/metrics`.

## Docker

```bash
docker compose up --build
```

The Compose configuration persists application/checkpoint data and structured logs through named volumes.

## Final execution gate

After installing dependencies and configuring the required local services, run:

```bash
python scripts/run_step08_evidence.py
```

Or run each proof independently:

```bash
python scripts/demo_step08_full_graph.py
python scripts/demo_step08_live_llm.py
python scripts/demo_step08_docker.py
python scripts/final_validate.py
```

The project is submission-ready only when `evidence/step08_submission_gate.txt` contains:

```text
SUBMISSION_READY=true
```

## Evidence
Important captured artifacts include:

```text
evidence/step03_tool_execution.txt
evidence/step04_multi_agent_replan.txt
evidence/step05_security_guardrails.txt
evidence/step06_live_http.txt
evidence/step06_observability_api.txt
evidence/step07_function_calling_protocol.txt
evidence/step07_test_run.txt
evidence/step08_submission_gate.txt
```

Step 07 protocol evidence deliberately labels the fake provider trajectory as **not live-provider evidence**. It proves the function-calling implementation while executing real SQLite tools. The final live OpenAI call must be captured separately before submission.

## Documentation
- `PROJECT_SPEC.md` — locked project scope and definition of done.
- `RUBRIC_TRACEABILITY.md` — requirement-to-implementation/evidence mapping.
- `docs/ARCHITECTURE.md` — state graph and component architecture.
- `docs/STEP_07_LLM_INTEGRATION.md` — OpenAI Responses API tool-calling design.
- `docs/FINAL_AUDIT.md` — implementation/evidence audit.
- `docs/STEP_08_FINAL_EXECUTION.md` — exact final proof commands.
- `docs/FINAL_SUBMISSION_CHECKLIST.md` — 100-point submission checklist and gate.

## Training Program Attribution
Completed under **Advanced Agentic AI Systems Engineering**, SDAIA Academy, delivered via Learning Space. 5-day on-site capstone cohort/session: **9–13 August 2026**.

SDAIA Academy GitHub: https://github.com/SDAIAAcademy

## Git practices for submission
The final GitHub repository must be built with meaningful incremental commits rather than one bulk upload. `.gitignore` excludes local secrets, databases, environments, logs, and generated artifacts that should not be committed. Evidence intended for evaluation remains in `evidence/`.
