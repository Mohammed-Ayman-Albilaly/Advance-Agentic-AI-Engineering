# UniFlow AI — Final Submission Checklist

## 100-point rubric gate

| Deliverable | Points | Implementation | Evidence gate |
|---|---:|---|---|
| Agentic Reasoning & Tool Use | 15 | Plan-and-Execute, OpenAI function calling, real SQLite-backed tools, shared state | `LIVE_OPENAI_SUCCESS=true` — **captured** |
| Graph-Based Orchestration | 20 | LangGraph StateGraph, nodes/edges, conditional branches, bounded re-plan loop | `REPLAN_LOOP_SUCCESS=true` — **captured** |
| Multi-Agent System | 20 | Coordinator, Task Analysis, Planning, Reviewer; structured handoffs/shared state | Existing executed multi-agent tests/evidence + full graph trace |
| Security, Guardrails & Observability | 20 | Input attack block, output protection/PII masking, ownership boundaries, JSON logs, Prometheus metrics | Existing security and observability evidence |
| Persistence, HITL & Cloud | 20 | SQLite saver, interrupt/resume, restart-safe thread, FastAPI, Docker Compose | `HITL_RESTART_RESUME_SUCCESS=true` — **captured**; `DOCKER_HEALTH_SUCCESS=true` — **pending** |
| Documentation & Evidence | 5 | README, architecture, traceability, evidence directory, program attribution | All final evidence present except Docker; gate not yet green |

## Submission gate

Run:

```bash
python scripts/final_validate.py
```

Only treat the repository as final when the report contains:

```text
SUBMISSION_READY=true
```

## GitHub gate after runtime evidence

Before publishing the final submission:

- [ ] Confirm `.env` is not tracked.
- [ ] Confirm no API keys/secrets appear in repository history.
- [ ] Keep `.env.example` only.
- [ ] Add captured Step 08 evidence.
- [ ] Run the full test suite.
- [ ] Use meaningful incremental commits rather than one bulk upload.
- [ ] Confirm README program attribution and SDAIA Academy reference.
- [ ] Push only after the local submission gate is green.
