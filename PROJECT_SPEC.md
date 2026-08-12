# UniFlow AI — Final Project Specification

## 1. Project Identity
**Project name:** UniFlow AI  
**Type:** Multi-agent university study and task coordination system  
**Primary goal:** Convert a student's courses, tasks, deadlines, workload, and available study time into a realistic study plan that is analyzed, reviewed, approved by the user, persisted, and safely resumed.

## 2. Core Problem
Students often have several courses, assignments, quizzes, exams, and limited study time. A static to-do list does not reason about urgency, workload, conflicts, feasibility, or re-planning.

UniFlow AI solves this by using multiple specialized agents coordinated by a real state graph.

## 3. In Scope
- Add and manage courses.
- Add and manage academic tasks.
- Store deadlines, estimated effort, priority inputs, and task status.
- Store weekly study availability.
- Analyze urgency and workload.
- Generate a proposed study plan.
- Detect conflicts and infeasible plans.
- Review the generated plan.
- Re-plan when review fails.
- Pause for human approval before saving a final plan.
- Persist workflow state across application restarts.
- Block prompt-injection attempts.
- Validate/mask sensitive output where applicable.
- Produce structured logs and metrics.
- Expose the system through FastAPI.
- Package the application with Docker.
- Capture execution evidence for happy paths and failure/security paths.

## 4. Explicitly Out of Scope for the Capstone Core
These are intentionally excluded unless all rubric requirements are already complete:
- Blackboard/LMS integration.
- Google Calendar OAuth.
- Email integration.
- Mobile app.
- Complex authentication/authorization.
- Real university SIS integration.
- Payment or subscription features.

## 5. Reasoning Pattern
The primary named reasoning pattern is **Plan-and-Execute**:
1. Understand the student's goal and constraints.
2. Analyze tasks and workload.
3. Create a plan.
4. Execute checks through real tools.
5. Review the plan.
6. Re-plan when a condition fails.
7. Pause for human approval.
8. Save the approved plan.

A reviewer/self-critique stage is also used to strengthen plan quality, but Plan-and-Execute is the primary documented pattern.

## 6. Agent Roles
### Coordinator Agent
- Interprets the user request.
- Determines the workflow intent.
- Routes state to the appropriate downstream steps.
- Coordinates specialized agents through shared graph state.

### Task Analysis Agent
- Normalizes task data.
- Evaluates urgency, workload, deadline proximity, and priority.
- Calls real tools for calculations and conflict checks.

### Planning Agent
- Builds a realistic study schedule from analyzed tasks and availability.
- Uses tool results rather than hardcoded output.
- Produces structured plan data.

### Reviewer Agent
- Validates feasibility.
- Checks missed deadlines, overload, ignored tasks, and conflicts.
- Returns APPROVED or REPLAN_REQUIRED with structured feedback.

## 7. Real Tools
Initial tool contract:
- `add_course`
- `add_task`
- `get_courses`
- `get_tasks`
- `set_availability`
- `get_available_hours`
- `calculate_task_priority`
- `calculate_weekly_workload`
- `check_deadline_conflicts`
- `validate_plan_capacity`
- `save_study_plan`
- `load_study_plan`
- `update_task_status`

All tools must execute real Python logic and/or persistent database operations.

## 8. Shared Graph State
The graph state will include:
- `thread_id`
- `user_request`
- `intent`
- `courses`
- `tasks`
- `availability`
- `analyzed_tasks`
- `proposed_plan`
- `conflicts`
- `review_status`
- `reviewer_feedback`
- `retry_count`
- `approval_status`
- `final_plan`
- `guardrail_status`
- `errors`
- `tool_events`

Every graph node reads from and/or updates this shared object.

## 9. Graph Behavior
Required graph characteristics:
- Real nodes and edges.
- At least one conditional edge.
- At least one loop.
- Shared state.
- Deterministic termination condition.
- Persistent checkpointing.

Primary flow:
START
→ Input Guardrail
→ Coordinator
→ Task Analysis
→ Planning
→ Conflict/Capacity Check
→ Reviewer

Reviewer conditional:
- APPROVED → Human Approval
- REPLAN_REQUIRED → Planning

Human approval conditional:
- APPROVE → Save Plan → Output Guardrail → END
- REJECT → Planning

Retry termination:
- Re-planning is capped by a configured maximum retry count.
- If the retry limit is reached, the graph returns a safe failure status with actionable feedback.

## 10. Human-in-the-Loop
The graph must perform a real interrupt before final persistence.

The user may:
- Approve the proposed plan.
- Reject the plan.
- Provide rejection feedback.

The same graph thread must resume from the stored checkpoint.

## 11. Persistence
Two persistence layers:
1. Application data in SQLite:
   - courses
   - tasks
   - availability
   - saved plans
2. LangGraph persistent checkpointer:
   - workflow state
   - thread continuation
   - HITL pause/resume state

Restart test:
1. Start workflow.
2. Reach interrupt.
3. Stop application.
4. Restart application.
5. Resume the same thread.
6. Complete approval.

## 12. Security and Guardrails
### Input Guardrail
Must detect and block a demonstrated prompt-injection attempt, including instructions attempting to:
- Override system rules.
- Reveal system prompts.
- Expose stored student data.
- Bypass approval or security flow.

### Output/Data Guardrail
Will validate structured output and protect sensitive fields. The implementation may include:
- PII masking for selected fields.
- Schema validation.
- Removal of internal prompts/system metadata from user-facing output.

Security behavior must be enforced in code, not described only in comments.

## 13. Observability
No reliance on plain `print()` for rubric evidence.

Structured events will capture:
- timestamp
- thread_id
- node
- agent
- tool name
- success/failure
- latency
- retry count
- guardrail block
- approval outcome

Metrics will include at minimum:
- workflow executions
- tool calls
- failed tool calls
- retries
- blocked attacks
- approvals
- rejections
- node latency

## 14. API
FastAPI will expose the core workflow.

Planned endpoints:
- `GET /health`
- `POST /courses`
- `GET /courses`
- `POST /tasks`
- `GET /tasks`
- `POST /availability`
- `POST /workflow/start`
- `GET /workflow/{thread_id}`
- `POST /workflow/{thread_id}/resume`
- `GET /plans/{thread_id}`
- `GET /metrics`

Exact payload schemas will be implemented with Pydantic.

## 15. Cloud/Production Artifact
Required deployment artifacts:
- `Dockerfile`
- `docker-compose.yml`
- FastAPI service

The project will run locally through Docker as the reproducible deployment proof.

## 16. Required Evidence Scenarios
The repository must contain captured evidence for:
1. Normal successful planning run.
2. Real tool calls.
3. Multi-agent state transitions.
4. Conditional branch.
5. Reviewer-triggered re-plan loop.
6. Simulated tool or validation failure and retry/fallback.
7. Prompt-injection attack blocked.
8. Output/data guardrail enforcement.
9. Human approval pause.
10. Human approval resume.
11. Persistent restart/resume.
12. Structured logs/metrics.
13. Docker/FastAPI execution.

## 17. Definition of Done
The project is not complete until:
- All rubric deliverables have executable implementations.
- All required failure/security paths are demonstrated.
- Tests pass.
- Evidence is captured.
- README and architecture documentation are complete.
- Secrets are excluded from Git.
- Docker execution succeeds.
- Git history is incremental and meaningful before final submission.
