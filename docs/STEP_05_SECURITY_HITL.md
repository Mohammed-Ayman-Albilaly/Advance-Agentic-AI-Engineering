# Step 05 — Security Guardrails, Durable Checkpointing & HITL

## Objective
Add enforced security controls and a real LangGraph human-approval design without weakening the graph requirements built in Step 04.

## Implemented Components

### 1. Input Guardrail
`app/guardrails/core.py` contains an enforced `InputGuardrail` that blocks imperative attempts to:
- override system/developer/security instructions;
- reveal protected prompts, secrets, or stored student data;
- bypass human approval, reviewer, or security controls.

The rules are intentionally scoped so normal academic requests and educational discussion of prompt injection are not blocked.

### 2. Output/Data-Protection Guardrail
`OutputGuardrail` performs two independent controls:
- forbidden internal/secret-bearing field detection;
- PII masking for email addresses and Saudi mobile numbers.

A final plan must also pass the `StudyPlan` Pydantic schema before it can be returned as completed output.

### 3. Dynamic Human-in-the-Loop Node
The graph now contains `human_approval` after reviewer approval. The node calls LangGraph `interrupt()` with a JSON-serializable plan-review payload.

Resume input is validated through `ApprovalDecision`:
- `approved` promotes the reviewed proposal to a final approved plan;
- `rejected` requires feedback, increments the retry counter, and routes back to planning.

All side effects are after `interrupt()` because LangGraph restarts an interrupted node from its beginning when it resumes.

### 4. Durable SQLite Checkpoint Resource
`SqliteCheckpointResource` owns a file-backed SQLite connection and `SqliteSaver`. Its connection remains open while the compiled graph uses the saver and can be closed/reopened to demonstrate restart-safe continuation.

The intended runtime uses:
```python
config = {"configurable": {"thread_id": thread_id}}
```
for both initial invocation and resume.

### 5. Final Persistence
After human approval, `persist_final` calls the real `save_study_plan` tool. Only then does the graph pass the persisted plan through the output guardrail and terminate successfully.

## Current Graph

```text
START
  -> input_guardrail
       -> blocked -> END
       -> coordinator
          -> task_analysis
          -> planning
          -> reviewer
               -> replan -> planning
               -> failed -> END
               -> human_approval [interrupt]
                    -> rejected -> planning
                    -> failed -> END
                    -> approved
                         -> persist_final
                         -> output_guardrail
                         -> END
```

## Executed Evidence in This Environment
`evidence/step05_security_guardrails.txt` contains a real execution showing:
- prompt-injection attempt blocked;
- explicit matched security rules;
- email and phone masking;
- secret-bearing `api_key` field blocked.

`evidence/step05_test_run.txt` contains the regression test run.

Result at preparation time:
- **43 passed**
- **2 skipped** only because LangGraph and its SQLite checkpoint package cannot be downloaded in this sandbox.

## Runtime Evidence Still Required
The repository includes `scripts/demo_step05_hitl.py` for a dependency-enabled environment. It is designed to:
1. run the real graph until `interrupt()`;
2. close the SQLite checkpoint connection to simulate application restart;
3. reopen the same checkpoint database;
4. resume with `Command(resume={"decision": "approved"})` and the same `thread_id`;
5. verify that the approved plan was persisted in the application database.

This script must be executed and its captured output added to `evidence/` before final submission. The project does **not** claim the HITL persistence rubric evidence until that run succeeds.
