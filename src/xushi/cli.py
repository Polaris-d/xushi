"""序时命令行入口。"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Annotated

import typer

from xushi.config import Settings, default_config_path, write_initial_config
from xushi.models import Executor, TaskCreate
from xushi.service import XushiService

app = typer.Typer(help="序时 xushi 本地日程与 agent 调度工具。")


def _service() -> XushiService:
    return XushiService(Settings.from_env())


def _mask_token(token: str) -> str:
    """隐藏 token 中间部分。"""
    if len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


def _check_port(host: str, port: int) -> str:
    """检查端口当前是否可绑定。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return "occupied_or_blocked"
    return "available"


@app.command("init")
def init_config(
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(help="本地状态目录, 默认使用 ~/.xushi。"),
    ] = None,
    force: Annotated[bool, typer.Option(help="覆盖已有配置文件。")] = False,
    show_token: Annotated[bool, typer.Option(help="输出完整本地 token。")] = False,
) -> None:
    """初始化本地配置。"""
    try:
        payload = write_initial_config(config_path=config_path, state_dir=state_dir, force=force)
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    resolved_config_path = config_path or default_config_path()
    output = {
        "config_path": str(resolved_config_path),
        "database_path": payload["database_path"],
        "base_url": f"http://{payload['host']}:{payload['port']}",
        "api_token": payload["api_token"] if show_token else _mask_token(payload["api_token"]),
        "token_visible": show_token,
    }
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


@app.command()
def doctor(
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
) -> None:
    """检查本地配置和 daemon 启动条件。"""
    resolved_config_path = config_path or default_config_path()
    settings = Settings.from_env(config_path=resolved_config_path)
    database_parent = settings.database_path.parent
    database_parent.mkdir(parents=True, exist_ok=True)
    report = {
        "config_path": str(resolved_config_path),
        "config_exists": resolved_config_path.exists(),
        "database_path": str(settings.database_path),
        "database_parent_exists": database_parent.exists(),
        "host": settings.host,
        "port": settings.port,
        "port_status": _check_port(settings.host, settings.port),
        "scheduler_interval_seconds": settings.scheduler_interval_seconds,
        "api_token": _mask_token(settings.api_token),
    }
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))


@app.command()
def create(task_file: Path) -> None:
    """从 JSON 文件创建任务。"""
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    task = _service().create_task(TaskCreate.model_validate(payload))
    typer.echo(task.model_dump_json(indent=2))


@app.command("list")
def list_tasks() -> None:
    """列出任务。"""
    tasks = [task.model_dump(mode="json") for task in _service().list_tasks()]
    typer.echo(json.dumps(tasks, ensure_ascii=False, indent=2))


@app.command()
def trigger(task_id: str) -> None:
    """手动触发任务。"""
    run = _service().trigger_task(task_id)
    typer.echo(run.model_dump_json(indent=2))


@app.command()
def tick() -> None:
    """扫描并触发到期任务。"""
    runs = [run.model_dump(mode="json") for run in _service().tick()]
    typer.echo(json.dumps(runs, ensure_ascii=False, indent=2))


@app.command()
def executor(executor_file: Path) -> None:
    """创建或更新执行器。"""
    payload = json.loads(executor_file.read_text(encoding="utf-8"))
    saved = _service().save_executor(Executor.model_validate(payload))
    typer.echo(saved.model_dump_json(indent=2))


@app.command()
def notifications() -> None:
    """列出通知记录。"""
    events = [event.model_dump(mode="json") for event in _service().list_notifications()]
    typer.echo(json.dumps(events, ensure_ascii=False, indent=2))
