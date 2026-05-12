"""序时本地 HTTP API。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from xushi import __version__
from xushi.capabilities import capabilities_payload
from xushi.config import Settings
from xushi.models import RunCallback, RunStatus, TaskCreate, TaskPatch
from xushi.runtime import run_scheduler_loop
from xushi.service import (
    IdempotencyConflictError,
    InvalidTaskConfigurationError,
    XushiService,
)


def api_response(
    data: Any = None,
    message: str = "ok",
    status_code: int = 200,
    errors: list[Any] | None = None,
) -> dict[str, Any]:
    """返回统一响应结构。"""
    return {
        "status": status_code,
        "code": status_code,
        "message": message,
        "data": data,
        "errors": errors or [],
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建 FastAPI 应用。"""
    app_settings = settings or Settings.from_env()
    service = XushiService(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(
            run_scheduler_loop(service, app_settings.scheduler_interval_seconds)
        )
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="序时 xushi", version=__version__, lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=api_response(
                None,
                detail,
                exc.status_code,
                [{"detail": exc.detail}],
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Any,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=api_response(
                None,
                "validation error",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                jsonable_encoder(exc.errors()),
            ),
        )

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization != f"Bearer {app_settings.api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return api_response({"name": "xushi", "status": "ok"})

    @app.get("/api/v1/capabilities")
    def capabilities() -> dict[str, Any]:
        """返回 CLI、HTTP API 和插件工具的 agent 能力清单。"""
        return api_response(capabilities_payload())

    @app.post("/api/v1/tasks", status_code=201, dependencies=[Depends(require_token)])
    def create_task(request: TaskCreate, response: Response) -> dict[str, Any]:
        try:
            task = service.create_task(request)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidTaskConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response.status_code = status.HTTP_201_CREATED
        return api_response(task.model_dump(mode="json"), "created", 201)

    @app.get("/api/v1/tasks", dependencies=[Depends(require_token)])
    def list_tasks(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        return api_response(
            [task.model_dump(mode="json") for task in service.list_tasks(limit=limit)]
        )

    @app.get("/api/v1/tasks/{task_id}", dependencies=[Depends(require_token)])
    def get_task(task_id: str) -> dict[str, Any]:
        task = service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return api_response(task.model_dump(mode="json"))

    @app.patch("/api/v1/tasks/{task_id}", dependencies=[Depends(require_token)])
    def update_task(task_id: str, patch: TaskPatch) -> dict[str, Any]:
        try:
            task = service.update_task(task_id, patch)
        except InvalidTaskConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return api_response(task.model_dump(mode="json"))

    @app.delete("/api/v1/tasks/{task_id}", dependencies=[Depends(require_token)])
    def delete_task(task_id: str) -> dict[str, Any]:
        if not service.delete_task(task_id):
            raise HTTPException(status_code=404, detail="task not found")
        return api_response({"id": task_id, "status": "archived"})

    @app.post(
        "/api/v1/tasks/{task_id}/runs",
        status_code=201,
        dependencies=[Depends(require_token)],
    )
    def trigger_task(task_id: str, response: Response) -> dict[str, Any]:
        try:
            run = service.trigger_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        response.status_code = status.HTTP_201_CREATED
        return api_response(run.model_dump(mode="json"), "created", 201)

    @app.get("/api/v1/runs", dependencies=[Depends(require_token)])
    def list_runs(
        task_id: str | None = None,
        status_filter: Annotated[RunStatus | None, Query(alias="status")] = None,
        active_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        runs = service.list_runs(
            task_id=task_id,
            status=status_filter,
            active_only=active_only,
            limit=limit,
        )
        return api_response([run.model_dump(mode="json") for run in runs])

    @app.get("/api/v1/notifications", dependencies=[Depends(require_token)])
    def list_notifications() -> dict[str, Any]:
        return api_response(
            [event.model_dump(mode="json") for event in service.list_notifications()]
        )

    @app.get("/api/v1/deliveries", dependencies=[Depends(require_token)])
    def list_deliveries(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        return api_response(
            [delivery.model_dump(mode="json") for delivery in service.list_deliveries(limit=limit)]
        )

    @app.post("/api/v1/deliveries/retry", dependencies=[Depends(require_token)])
    def retry_deliveries(
        limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    ) -> dict[str, Any]:
        deliveries = service.retry_failed_deliveries(limit=limit)
        return api_response([delivery.model_dump(mode="json") for delivery in deliveries])

    @app.post("/api/v1/config/reload", dependencies=[Depends(require_token)])
    def reload_config() -> dict[str, Any]:
        try:
            reloaded_settings = Settings.from_env()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="config reload failed") from exc
        return api_response(service.reload_runtime_settings(reloaded_settings))

    @app.get("/api/v1/metrics", dependencies=[Depends(require_token)])
    def metrics() -> dict[str, Any]:
        return api_response(service.metrics_snapshot())

    @app.post(
        "/api/v1/runs/{run_id}/confirm",
        dependencies=[Depends(require_token)],
        summary="Confirm a run",
        description="Confirm one run by run_id and stop related follow-up reminders.",
    )
    def confirm_run(run_id: str) -> dict[str, Any]:
        run = service.confirm_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return api_response(run.model_dump(mode="json"))

    @app.post(
        "/api/v1/tasks/{task_id}/runs/confirm-latest",
        dependencies=[Depends(require_token)],
        summary="Confirm latest pending primary run",
        description=(
            "When the user says a known task is done, confirm the task's latest "
            "pending primary run without triggering a new reminder."
        ),
    )
    def confirm_latest_run(task_id: str) -> dict[str, Any]:
        if service.get_task(task_id) is None:
            raise HTTPException(status_code=404, detail="task not found")
        run = service.confirm_latest_run(task_id)
        if run is None:
            raise HTTPException(status_code=404, detail="pending run not found")
        return api_response(run.model_dump(mode="json"))

    @app.post("/api/v1/runs/{run_id}/callback", dependencies=[Depends(require_token)])
    def callback_run(run_id: str, callback: RunCallback) -> dict[str, Any]:
        run = service.callback_run(run_id, callback)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return api_response(run.model_dump(mode="json"))

    @app.get("/api/v1/executors", dependencies=[Depends(require_token)])
    def list_executors() -> dict[str, Any]:
        return api_response(
            [executor.model_dump(mode="json") for executor in service.list_executors()]
        )

    @app.get("/", response_class=HTMLResponse)
    def web_console() -> str:
        return _web_console_html()

    return app


def _web_console_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>序时 xushi</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; color: #17202a; background: #f7f8fa; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 20px; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    h1 { font-size: 28px; margin: 0; }
    section {
      margin-top: 24px; background: white; border: 1px solid #e5e7eb;
      border-radius: 8px; padding: 16px;
    }
    input {
      padding: 8px 10px; border: 1px solid #cbd5e1;
      border-radius: 6px; min-width: 260px;
    }
    button {
      padding: 8px 12px; border: 0; border-radius: 6px;
      background: #1f6feb; color: white; cursor: pointer;
    }
    pre { overflow: auto; background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>序时 xushi</h1>
        <p>本地 agent 日程与调度底座</p>
      </div>
      <input id="token" type="password" placeholder="XUSHI_API_TOKEN">
    </header>
    <section>
      <button onclick="loadTasks()">刷新任务</button>
      <button onclick="loadRuns()">刷新运行记录</button>
      <button onclick="loadNotifications()">刷新通知</button>
      <pre id="output">输入 token 后查看本地任务。</pre>
    </section>
  </main>
  <script>
    async function api(path) {
      const token = document.getElementById('token').value;
      const res = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
      return await res.json();
    }
    async function loadTasks() {
      const tasks = await api('/api/v1/tasks');
      document.getElementById('output').textContent = JSON.stringify(tasks, null, 2);
    }
    async function loadRuns() {
      const runs = await api('/api/v1/runs');
      document.getElementById('output').textContent = JSON.stringify(runs, null, 2);
    }
    async function loadNotifications() {
      const events = await api('/api/v1/notifications');
      document.getElementById('output').textContent = JSON.stringify(events, null, 2);
    }
  </script>
</body>
</html>
"""
