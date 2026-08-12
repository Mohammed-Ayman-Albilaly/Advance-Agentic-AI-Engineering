# UniFlow AI Architecture

## Architecture Style
UniFlow AI is a stateful, centralized multi-agent system orchestrated by LangGraph.

## Core Vocabulary
- **State:** `StudyState`, the shared object read and updated by graph nodes.
- **Nodes:** Coordinator, Task Analysis, Planning, Reviewer, Ready for Approval, Failed.
- **Edges:** deterministic transitions between sequential nodes.
- **Conditional edge:** Reviewer selects approval, re-plan, or terminal failure.
- **Loop:** Reviewer -> Planning when a plan requires repair.
- **Agents:** specialized components with distinct responsibilities.
- **Tools:** real validated Python/SQLite operations invoked by agents.

## Current Graph

```text
START -> Coordinator -> Task Analysis -> Planning -> Reviewer
                                            ^          |
                                            |          | replan
                                            +----------+

Reviewer --approved--> Ready for Approval -> END
Reviewer --retry exhausted--> Failed -> END
```

Step 5 replaces the temporary Ready-for-Approval terminal with a real LangGraph human-in-the-loop interrupt and persistent SQLite checkpointer.

## Step 5 Security and HITL Extension

The graph entry point is now an enforced input guardrail. Blocked requests terminate before any coordinator/tool access. Reviewer-approved plans reach a dynamic `human_approval` node that pauses with LangGraph `interrupt()`. Rejected plans return to the planning loop; approved plans are persisted through the real study-plan tool and then pass the output/data-protection guardrail before completion.

Durable graph state is designed around a file-backed LangGraph SQLite checkpointer keyed by `thread_id`. The application data database and the LangGraph checkpoint database remain separate so workflow recovery and domain persistence can be verified independently.

## Step 6 — Production Boundary and Observability

The API boundary is implemented with FastAPI. HTTP middleware records request count, status code and latency. Prometheus metrics are exposed at `/metrics`, and JSON Lines structured logs capture graph/tool/security/HITL events.

The production packaging artifact consists of a non-root Python container plus Docker Compose persistent volumes. The application SQLite database and LangGraph checkpoint SQLite database are intentionally separate but share a durable data volume in the container deployment.

The API does not replace LangGraph when its dependency is missing. Workflow endpoints return a safe dependency error instead of running a hand-rolled fallback, preserving the rubric requirement that the orchestration be genuine.

## Step 7 — Live LLM Function-Calling Boundary

The Coordinator now supports a live `llm_function_calling` mode through the OpenAI Responses API. The model receives strict read-only function schemas and must call the persisted context tools before it can complete coordination. Tool results are returned to the model as function-call outputs, after which a concise coordination brief is written into shared state.

The model cannot choose a user identifier. Tool ownership scope is injected from trusted state by the executor, preventing cross-user data selection through model-generated arguments. Provider calls use `store=False`, and structured LLM metrics record latency/tokens/success alongside the existing tool events.

When `LLM_PROVIDER=not_configured`, the Coordinator intentionally uses the existing deterministic offline path. This mode supports development but is not counted as live LLM capstone evidence.
