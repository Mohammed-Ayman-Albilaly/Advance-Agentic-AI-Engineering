# Step 08 — Final Execution & Submission Validation

Step 08 converts the remaining rubric claims into explicit executable proof gates.

## Live evidence commands

Run from the repository root after `pip install -r requirements.txt`:

```bash
python scripts/demo_step08_full_graph.py
python scripts/demo_step08_live_llm.py
python scripts/demo_step08_docker.py
python scripts/final_validate.py
```

Or attempt all four in sequence:

```bash
python scripts/run_step08_evidence.py
```

## Required success markers

The final gate looks for exact markers:

- `LIVE_OPENAI_SUCCESS=true`
- `REPLAN_LOOP_SUCCESS=true`
- `HITL_RESTART_RESUME_SUCCESS=true`
- `DOCKER_HEALTH_SUCCESS=true`
- `SUBMISSION_READY=true`

No evidence file is considered valid merely because it exists; the marker must report success.

## Evidence isolation

The OpenAI proof demonstrates live provider function calling against real SQLite-backed project tools. The graph/HITL proof intentionally uses the deterministic coordinator so LangGraph branching and persistence can be proven independently of provider availability. The Docker proof starts the API without an external LLM and validates the deployment artifact through `/health`.

## Security hardening added in Step 08

`SqliteCheckpointResource` enforces `LANGGRAPH_STRICT_MSGPACK=true` before importing/creating the SQLite saver, reducing unsafe checkpoint deserialization risk if the checkpoint database is tampered with.
