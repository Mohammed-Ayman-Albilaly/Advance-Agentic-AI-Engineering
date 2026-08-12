"""FastAPI application for UniFlow AI."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.runtime import RuntimeDependencyError, WorkflowRuntime
from app.api.schemas import (
    AvailabilityRequest,
    CourseRequest,
    TaskRequest,
    TaskStatusRequest,
    WorkflowResumeRequest,
    WorkflowResponse,
    WorkflowStartRequest,
)
from app.config import Settings, get_settings
from app.observability import Observability, set_observability
from app.persistence import Database
from app.tools import StudyTools
from app.tools.runtime import ToolExecutionError


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    observability: Observability | None = None,
    workflow_runtime: WorkflowRuntime | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    database = database or Database(settings.database_path)
    database.initialize()
    observer = observability or Observability(log_path=settings.log_path, log_level=settings.log_level)
    set_observability(observer)
    tools = StudyTools(database)
    runtime = workflow_runtime or WorkflowRuntime(
        tools,
        settings.checkpoint_database_path,
        max_replans=settings.max_replans,
        settings=settings,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.initialize()
        observer.log("application_start", app=settings.app_name, env=settings.app_env)
        try:
            yield
        finally:
            runtime.close()
            observer.log("application_stop", app=settings.app_name)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Multi-agent university study and task coordination system.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.tools = tools
    app.state.observability = observer
    app.state.workflow_runtime = runtime

    @app.middleware("http")
    async def observe_http(request: Request, call_next):
        started = perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", request.url.path)
            code = response.status_code if response is not None else 500
            observer.record_api_request(
                method=request.method,
                route=str(route),
                status_code=code,
                latency_seconds=perf_counter() - started,
            )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok" if database.health_check() else "degraded",
            "app": settings.app_name,
            "environment": settings.app_env,
            "llm_provider": settings.llm_provider,
            "llm_configured": (
                settings.llm_provider == "openai"
                and settings.openai_api_key is not None
                and bool(settings.openai_api_key.get_secret_value().strip())
                and bool(settings.llm_model.strip())
            ),
        }

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(observer.registry), media_type=CONTENT_TYPE_LATEST)

    @app.post("/courses", status_code=status.HTTP_201_CREATED)
    def create_course(payload: CourseRequest) -> dict:
        try:
            return tools.add_course(
                payload.user_id,
                code=payload.code,
                name=payload.name,
                credit_hours=payload.credit_hours,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="course already exists or violates ownership rules") from exc

    @app.get("/courses")
    def list_courses(user_id: str = Query(min_length=1, max_length=128)) -> list[dict]:
        return tools.get_courses(user_id)

    @app.post("/tasks", status_code=status.HTTP_201_CREATED)
    def create_task(payload: TaskRequest) -> dict:
        try:
            return tools.add_task(
                payload.user_id,
                title=payload.title,
                course_id=payload.course_id,
                deadline=payload.deadline,
                estimated_hours=payload.estimated_hours,
                difficulty=payload.difficulty,
                user_priority=payload.user_priority,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="task references an invalid or foreign-owned course") from exc

    @app.get("/tasks")
    def list_tasks(
        user_id: str = Query(min_length=1, max_length=128),
        include_done: bool = False,
    ) -> list[dict]:
        return tools.get_tasks(user_id, include_done=include_done)

    @app.patch("/tasks/{task_id}/status")
    def set_task_status(task_id: str, payload: TaskStatusRequest) -> dict:
        try:
            return tools.update_task_status(payload.user_id, task_id=task_id, status=payload.status)
        except ToolExecutionError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc

    @app.post("/availability", status_code=status.HTTP_201_CREATED)
    def create_availability(payload: AvailabilityRequest) -> dict:
        try:
            return tools.set_availability(
                payload.user_id,
                study_date=payload.date,
                start_time=payload.start_time,
                end_time=payload.end_time,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="availability window already exists") from exc

    @app.get("/availability")
    def list_availability(user_id: str = Query(min_length=1, max_length=128)) -> list[dict]:
        return tools.get_availability_windows(user_id)

    def _runtime_error(exc: RuntimeDependencyError) -> HTTPException:
        return HTTPException(status_code=503, detail=str(exc))

    @app.post("/workflow/start", response_model=WorkflowResponse)
    def start_workflow(payload: WorkflowStartRequest) -> dict:
        try:
            return runtime.start(
                user_id=payload.user_id,
                user_request=payload.user_request,
                thread_id=payload.thread_id,
            )
        except RuntimeDependencyError as exc:
            raise _runtime_error(exc) from exc

    @app.get("/workflow/{thread_id}", response_model=WorkflowResponse)
    def get_workflow(thread_id: str, user_id: str = Query(min_length=1, max_length=128)) -> dict:
        try:
            return runtime.get_state(thread_id=thread_id, user_id=user_id)
        except RuntimeDependencyError as exc:
            raise _runtime_error(exc) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/workflow/{thread_id}/resume", response_model=WorkflowResponse)
    def resume_workflow(thread_id: str, payload: WorkflowResumeRequest) -> dict:
        if payload.decision.value == "pending":
            raise HTTPException(status_code=422, detail="decision must be approved or rejected")
        if payload.decision.value == "rejected" and not payload.feedback:
            raise HTTPException(status_code=422, detail="feedback is required when rejecting a plan")
        try:
            return runtime.resume(
                thread_id=thread_id,
                user_id=payload.user_id,
                decision=payload.decision.value,
                feedback=payload.feedback,
            )
        except RuntimeDependencyError as exc:
            raise _runtime_error(exc) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/plans/{thread_id}")
    def get_plan(thread_id: str, user_id: str = Query(min_length=1, max_length=128)) -> dict:
        plan = tools.load_study_plan(thread_id=thread_id, user_id=user_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="plan not found")
        return plan

    return app


app = create_app()
