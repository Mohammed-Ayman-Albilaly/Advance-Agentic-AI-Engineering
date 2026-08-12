# Step 07 — OpenAI Function Calling Integration

## Purpose
Step 07 adds a genuine provider integration path so UniFlow AI can satisfy the capstone requirement that an agent reasons and calls real functions rather than relying only on deterministic orchestration logic.

## Provider
The live implementation uses the OpenAI **Responses API** through the official Python SDK. The provider is selected only through environment variables. No API key is committed to the repository.

## Agent Integration
The `CoordinatorAgent` has two explicit modes:

1. `llm_function_calling` — capstone/live mode. The OpenAI model must inspect persisted student context using function calls.
2. `deterministic_offline` — safe development/test mode when an LLM is not configured. This mode is never presented as live LLM evidence.

## Function-Calling Tools
The model is given these read-only functions:

- `get_courses`
- `get_tasks`
- `get_availability_windows`
- `get_available_hours`

The first three are mandatory before the model may finish the coordinator stage.

### Ownership security boundary
The model cannot provide a `user_id` argument. The current authenticated/project user scope is injected by trusted Python code when the real tool executes. This prevents a prompt or model output from selecting another student's identifier.

## Function-calling loop
1. The model receives the student's high-level request and tool schemas.
2. Until all required context tools have executed, tool choice is required.
3. The application validates each call and executes the real SQLite-backed `StudyTools` method.
4. The tool output is returned as `function_call_output`.
5. After mandatory observations exist, the model returns a concise coordination brief.
6. The downstream Task Analysis, Planning, and Reviewer agents continue through the shared LangGraph state.

The prompt explicitly requests only a concise execution summary and does not request private chain-of-thought.

## Data handling
`store=False` is used for Responses API calls in this implementation. API keys stay in `.env`/deployment secrets and are excluded through `.gitignore`.

## Observability
OpenAI calls now add structured logs and Prometheus metrics for:

- provider
- model
- agent
- success/failure
- latency
- input tokens
- output tokens
- thread ID

Existing tool-call observability continues to capture the real functions selected by the model.

## Failure behavior
- `LLM_PROVIDER=openai` without an API key fails closed.
- Missing `LLM_MODEL` fails closed.
- Unknown tools are rejected.
- Non-empty/model-controlled arguments are rejected for the user-scoped context tools.
- Invalid JSON tool arguments are rejected.
- The model cannot finish before mandatory tools have run.
- The function-calling loop has a fixed maximum round count.

## Evidence status
The provider protocol, real SQLite tool execution, ownership boundary, metrics, and failure paths are covered by automated tests and Step 07 protocol evidence.

**A fake Responses client is used only to test the tool-calling protocol without spending credentials. It is not counted as final live-provider rubric evidence.** A real `OPENAI_API_KEY` is required to capture the final live function-calling run before submission.
