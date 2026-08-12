# Step 03 — Real Tools & Planning Logic

## Goal
Provide executable, deterministic tools that future UniFlow agents can call. The tools use validated domain models and the SQLite repository rather than hardcoded prompt responses.

## Implemented tools
- `add_course`
- `get_courses`
- `add_task`
- `get_tasks`
- `update_task_status`
- `set_availability`
- `get_available_hours`
- `calculate_task_priority`
- `calculate_weekly_workload`
- `check_deadline_conflicts`
- `validate_plan_capacity`
- `save_study_plan`
- `load_study_plan`

## Planning logic
### Priority score
The score combines deadline urgency, user priority, difficulty, and estimated effort. The output is an `AnalyzedTask`, so downstream agents receive structured data rather than free-form text.

### Capacity
Overlapping availability windows are merged before hours are counted. This prevents inflated capacity from duplicate/overlapping input.

### Deadline conflicts
Pending tasks are ordered by deadline. At each deadline, cumulative required workload is compared with cumulative declared capacity available before that deadline. A shortfall becomes a concrete conflict for the Reviewer/Planner loop.

### Plan validation
A proposed plan is rejected when a session:
- references an unknown task/course,
- associates a task with the wrong course,
- falls outside declared availability,
- overlaps another session, or
- allocates more hours to a task than its current estimate.

## Failure/retry path
`execute_with_retry` retries only `TransientToolError`. Validation, ownership, and integrity problems are deliberately not retried. Tests demonstrate both:
1. first attempt fails and second succeeds;
2. retry budget is exhausted and an explicit `RetryExhaustedError` is raised.

This mechanism will be wired into LangGraph nodes later so the captured graph run can prove an actual retry/fallback path.

## Data isolation hardening
The SQLite task foreign key is composite `(user_id, course_id) -> courses(user_id, id)`. This prevents one user from attaching a task to another user's course even if a course ID is guessed. Study-plan lookup is also user-scoped at the tool boundary.

## Deadline boundary correctness
Capacity checks clip availability to the exact current time and exact deadline time. Hours that already passed today or occur after a same-day deadline are not counted as usable capacity. Dedicated regression tests cover both cases.

## Step 03 verification
The complete test suite contains **25 passing tests** after Step 03. Captured execution output is stored in `evidence/step03_tool_execution.txt`.
