# Rubric Traceability — UniFlow AI

| Rubric Area | Pts | Implementation | Evidence status |
|---|---:|---|---|
| Agentic Reasoning & Tool Use | 15 | Plan-and-Execute; OpenAI Responses API function-calling Coordinator; real SQLite tools; short-term shared state | Real tools + protocol tested. **Live OpenAI call captured** (`evidence/step08_live_openai.txt`). |
| Graph-Based Orchestration | 20 | LangGraph `StateGraph`; nodes/edges; input branch; reviewer branch; bounded re-plan loop; HITL rejection loop | **Real installed-LangGraph run captured**, including the re-plan loop (`evidence/step08_full_graph_hitl.txt`). |
| Multi-Agent System & Role Specialization | 20 | Coordinator, Task Analysis, Planning, Reviewer; structured handoffs; centralized coordination | Implemented and executed in automated tests/evidence. |
| Security, Guardrails & Observability | 20 | Prompt-injection blocking; output/PII/secret protection; ownership boundaries; JSON logs; Prometheus tool/node/API/LLM metrics | Implemented and executed, including real blocked attack. |
| Production Readiness: Persistence, HITL & Cloud | 20 | Domain SQLite; LangGraph SQLite saver; `interrupt()` + resume; FastAPI; Dockerfile/Compose | FastAPI/domain persistence executed. **Live HITL restart/resume captured** (`evidence/step08_full_graph_hitl.txt`). **Live Docker run still required** — Docker Desktop's engine was unresponsive in the last check. |
| Documentation & Evidence | 5 | Professional README; architecture; project spec; traceability; step docs; evidence directory | Implemented; two of three final runtime proof runs are captured, Docker pending. |

## Non-Negotiable Failure Paths
- Prompt injection is actually blocked — **captured**.
- Retry/re-plan actually executes — **captured**, including a real installed-LangGraph run.
- Human approval actually pauses and resumes — **captured** on the real installed LangGraph runtime with a real checkpoint-connection close/reopen simulating a restart.
- Persistent workflow state survives restart — **captured** in the same run (`HITL_RESTART_RESUME_SUCCESS=true`).
- Structured logs/metrics, not print-only — **captured**.
- LLM calls real project functions — **captured live** (`evidence/step08_live_openai.txt`, `LIVE_OPENAI_SUCCESS=true`).

## Submission Gate
Do not mark the project final until all are captured:

1. Live OpenAI function call(s) to UniFlow real tools. — **done**, `evidence/step08_live_openai.txt`.
2. Real LangGraph reviewer re-plan loop, then interrupt → application restart → resume on the same `thread_id`. — **done**, `evidence/step08_full_graph_hitl.txt`.
3. `docker compose up --build` with a successful health/API response. — **pending**, blocked on Docker Desktop's engine responding on this machine.


## Step 08 Machine Gate
Run `python scripts/final_validate.py`. Only treat the project as final when `evidence/step08_submission_gate.txt` contains `SUBMISSION_READY=true`.
