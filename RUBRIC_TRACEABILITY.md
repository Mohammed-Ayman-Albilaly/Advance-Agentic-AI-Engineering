# Rubric Traceability — UniFlow AI

| Rubric Area | Pts | Implementation | Evidence status |
|---|---:|---|---|
| Agentic Reasoning & Tool Use | 15 | Plan-and-Execute; OpenAI Responses API function-calling Coordinator; real SQLite tools; short-term shared state | Real tools + protocol tested. **Live OpenAI call still required.** |
| Graph-Based Orchestration | 20 | LangGraph `StateGraph`; nodes/edges; input branch; reviewer branch; bounded re-plan loop; HITL rejection loop | Topology/agent loop tested. **Live installed LangGraph run still required.** |
| Multi-Agent System & Role Specialization | 20 | Coordinator, Task Analysis, Planning, Reviewer; structured handoffs; centralized coordination | Implemented and executed in automated tests/evidence. |
| Security, Guardrails & Observability | 20 | Prompt-injection blocking; output/PII/secret protection; ownership boundaries; JSON logs; Prometheus tool/node/API/LLM metrics | Implemented and executed, including real blocked attack. |
| Production Readiness: Persistence, HITL & Cloud | 20 | Domain SQLite; LangGraph SQLite saver; `interrupt()` + resume; FastAPI; Dockerfile/Compose | FastAPI/domain persistence executed. **Live HITL restart/resume + Docker run required.** |
| Documentation & Evidence | 5 | Professional README; architecture; project spec; traceability; step docs; evidence directory | Implemented; final three runtime proof runs must be added before submission. |

## Non-Negotiable Failure Paths
- Prompt injection is actually blocked — **captured**.
- Retry/re-plan actually executes — **captured**.
- Human approval actually pauses and resumes — **source implemented; live LangGraph capture pending**.
- Persistent workflow state survives restart — **source implemented; live LangGraph capture pending**.
- Structured logs/metrics, not print-only — **captured**.
- LLM calls real project functions — **implementation/protocol tested; live provider capture pending**.

## Submission Gate
Do not mark the project final until all are captured:

1. Live OpenAI function call(s) to UniFlow real tools.
2. Real LangGraph reviewer re-plan loop, then interrupt → application restart → resume on the same `thread_id`.
3. `docker compose up --build` with a successful health/API response.


## Step 08 Machine Gate
Run `python scripts/final_validate.py`. Only treat the project as final when `evidence/step08_submission_gate.txt` contains `SUBMISSION_READY=true`.
