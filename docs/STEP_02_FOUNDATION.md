# Step 2 — Technical Foundation

## Completed

- Environment-driven configuration with `.env.example`.
- Secrets excluded from Git through `.gitignore`.
- Validated Pydantic domain models.
- SQLite application-data schema.
- Repository methods for courses, tasks, availability, task status, and study plans.
- File-backed persistence test.
- Foreign-key enforcement.
- Shared LangGraph `StudyState` contract.
- Append-only reducer fields for tool events and errors.
- Dependency manifest.
- Automated foundation tests.

## Persistence Separation

UniFlow AI intentionally uses two SQLite files:

1. `data/uniflow.sqlite` — domain/application data.
2. `data/checkpoints.sqlite` — LangGraph workflow checkpoints (wired when the graph is built).

This separation prevents graph checkpoint internals from being mixed with application tables and makes restart/resume evidence easier to demonstrate.

## LLM Provider Decision

No fake or simulated LLM is wired into the foundation. The provider is explicitly `not_configured` until the Agents step. The code is structured so a real provider can be selected without changing the domain/persistence layers.

## Current Automated Evidence

Run:

```bash
python -m pytest -q
```

Foundation test coverage includes:

- course normalization and input constraints;
- invalid values rejected by Pydantic;
- unknown fields rejected;
- availability-time validation;
- study-session duration integrity;
- human rejection feedback validation;
- SQLite initialization/health;
- persistence after reopening the SQLite file;
- foreign-key failure path;
- persisted task-status update;
- study-plan JSON round trip;
- required shared-state fields.

## Next Step

Step 3 implements real callable tools and deterministic planning calculations before connecting them to LLM agents and the LangGraph workflow.


Initialize the application database from the repository root with:

```bash
python -m scripts.init_db
```
