# Step 4 — Multi-Agent System & LangGraph Orchestration

## Goal
Implement the project's specialized agent layer and the genuine LangGraph graph topology required by the capstone rubric.

## Coordination Strategy
UniFlow AI uses **centralized coordination**:

1. `CoordinatorAgent` gathers user-scoped context using real tools.
2. `TaskAnalysisAgent` calculates task priority/urgency using real tool calls.
3. `PlanningAgent` creates a concrete schedule using **Plan-and-Execute** reasoning.
4. `ReviewerAgent` independently validates capacity, deadline coverage, and completeness.
5. Reviewer feedback conditionally routes back to Planning when repair is required.

Agents communicate through the shared `StudyState` and append structured `agent_messages` rather than one prompt pretending to be several personas.

## LangGraph Topology

```text
START
  |
  v
CoordinatorAgent
  |
  v
TaskAnalysisAgent
  |
  v
PlanningAgent <------------------+
  |                              |
  v                              |
ReviewerAgent                    |
  |                              |
  +-- approved --> Ready         |
  |                 |            |
  |                 v            |
  |                END           |
  |                              |
  +-- replan --------------------+
  |
  +-- retry limit --> Failed --> END
```

`app/graph/workflow.py` uses a real `StateGraph`, normal edges, and `add_conditional_edges` for reviewer routing. The re-plan edge creates the required loop, and `retry_count` provides deterministic termination.

## Re-planning Behavior
The first planning pass uses `priority_first`. This is a reasonable initial heuristic, but it can reserve early capacity for a later high-priority task.

If Reviewer detects that a nearer-deadline task is under-planned, it returns:

```text
review_status = replan_required
retry_count += 1
```

The PlanningAgent reads that shared state and switches to:

```text
deadline_first_replan
```

This means reviewer feedback changes subsequent behavior; the second attempt is not a duplicate of the first.

## Distinct Responsibilities

### CoordinatorAgent
Real tools used:
- `get_courses`
- `get_tasks`
- `get_availability_windows`

Output:
- intent
- current domain context
- structured handoff to TaskAnalysisAgent

### TaskAnalysisAgent
Real tools used:
- `calculate_task_priority` once per pending task

Output:
- analyzed task structures
- structured handoff to PlanningAgent

### PlanningAgent
Reads:
- tasks
- analyzed tasks
- availability
- retry count
- reviewer feedback/state

Produces:
- planning strategy
- proposed plan
- unscheduled hours
- structured review request

### ReviewerAgent
Real tools used:
- `validate_plan_capacity`
- `check_deadline_conflicts`

Also checks:
- task-hour coverage
- deadline compliance

Produces:
- `approved` or `replan_required`
- reviewer feedback
- retry count

## Shared State Additions
Step 4 adds:
- `planning_strategy`
- `unscheduled_hours`
- `agent_messages` (append-only reducer)
- `graph_trace` (append-only reducer)

Existing `tool_events` and `errors` remain append-only reducer channels.

## Failure/Termination Policy
A plan that continues to fail review may loop only up to `MAX_REPLANS`. When the limit is exhausted, the graph routes to `failed`, records the failure, and terminates instead of looping forever.

## Test Evidence
Step 4 tests cover:
- Coordinator real tool calls and structured handoff.
- TaskAnalysis per-task tool invocation.
- First-plan rejection.
- Reviewer feedback changing the next planning strategy.
- Successful repaired plan.
- Impossible-capacity unscheduled hours.
- Machine-testable graph topology with conditional reviewer routes and a loop.

The execution sandbox used to prepare this checkpoint cannot download LangGraph, so the graph compile test is intentionally skipped there when the package is absent. The project pins LangGraph in `requirements.txt`, and the graph implementation follows its public `StateGraph`/conditional-edge API. A real graph runtime execution remains mandatory before final capstone submission and will be captured once dependencies are available.
