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
from xushi.upgrade import UpgradeError, UpgradeManager, default_bin_dir

app = typer.Typer(help="序时 xushi 本地日程与 agent 调度工具。")
upgrade_app = typer.Typer(help="手动安全升级序时。")
app.add_typer(upgrade_app, name="upgrade")


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


def _upgrade_manager(
    config_path: Path | None = None,
    install_dir: Path | None = None,
) -> UpgradeManager:
    """创建升级管理器。"""
    resolved_config_path = Path(config_path) if config_path else default_config_path()
    settings = Settings.from_env(config_path=resolved_config_path)
    resolved_install_dir = install_dir or default_bin_dir()
    return UpgradeManager(
        config_path=resolved_config_path,
        database_path=settings.database_path,
        state_dir=resolved_config_path.parent,
        install_dir=resolved_install_dir,
        host=settings.host,
        port=settings.port,
    )


def _echo_json(payload: object) -> None:
    """输出 JSON。"""
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


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
    _echo_json(output)


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
        "executors": [
            {
                "id": executor.id,
                "kind": executor.kind,
                "enabled": executor.enabled,
            }
            for executor in settings.executors
        ],
    }
    _echo_json(report)


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
    _echo_json(tasks)


@app.command()
def trigger(task_id: str) -> None:
    """手动触发任务。"""
    run = _service().trigger_task(task_id)
    typer.echo(run.model_dump_json(indent=2))


@app.command()
def tick() -> None:
    """扫描并触发到期任务。"""
    runs = [run.model_dump(mode="json") for run in _service().tick()]
    _echo_json(runs)


@app.command()
def executor(executor_file: Path) -> None:
    """校验 executor 配置片段。"""
    payload = json.loads(executor_file.read_text(encoding="utf-8"))
    executor_config = Executor.model_validate(payload)
    output = {
        "valid": True,
        "message": (
            "executor 需要写入 ~/.xushi/config.json 的 executors 数组, "
            "然后重启 daemon 生效。"
        ),
        "executor": executor_config.model_dump(mode="json"),
    }
    _echo_json(output)


@app.command("executors")
def list_executors() -> None:
    """列出当前配置中的 executor。"""
    executors = [executor.model_dump(mode="json") for executor in _service().list_executors()]
    _echo_json(executors)


@app.command()
def notifications() -> None:
    """列出通知记录。"""
    events = [event.model_dump(mode="json") for event in _service().list_notifications()]
    _echo_json(events)


@upgrade_app.command("status")
def upgrade_status(
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    install_dir: Annotated[
        Path | None,
        typer.Option(help="全局命令目录, 默认使用 XUSHI_BIN_DIR 或 ~/.xushi/bin。"),
    ] = None,
) -> None:
    """查看本机升级状态。"""
    _echo_json(_upgrade_manager(config_path, install_dir).status())


@upgrade_app.command("check")
def upgrade_check(
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="目标版本, 例如 v0.1.2。"),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    install_dir: Annotated[
        Path | None,
        typer.Option(help="全局命令目录, 默认使用 XUSHI_BIN_DIR 或 ~/.xushi/bin。"),
    ] = None,
) -> None:
    """检查指定版本是否高于当前版本。"""
    _echo_json(_upgrade_manager(config_path, install_dir).check(version))


@upgrade_app.command("backup")
def upgrade_backup(
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    install_dir: Annotated[
        Path | None,
        typer.Option(help="全局命令目录, 默认使用 XUSHI_BIN_DIR 或 ~/.xushi/bin。"),
    ] = None,
) -> None:
    """手动创建升级前备份。"""
    _echo_json(_upgrade_manager(config_path, install_dir).create_backup().to_json())


@upgrade_app.command("rollback")
def upgrade_rollback(
    backup_id: Annotated[
        str | None,
        typer.Argument(help="备份 ID。为空时恢复最新备份。"),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    install_dir: Annotated[
        Path | None,
        typer.Option(help="全局命令目录, 默认使用 XUSHI_BIN_DIR 或 ~/.xushi/bin。"),
    ] = None,
) -> None:
    """从升级备份恢复配置和数据库。"""
    try:
        _echo_json(_upgrade_manager(config_path, install_dir).rollback(backup_id).to_json())
    except UpgradeError as exc:
        raise typer.BadParameter(str(exc)) from exc


@upgrade_app.command("apply")
def upgrade_apply(
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="目标 tag 版本, 例如 v0.1.2。为空时下载 latest。"),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="跳过确认提示。")] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option(help="兼容旧参数; release 二进制升级不检查 git 工作区。"),
    ] = False,
    allow_running_daemon: Annotated[
        bool,
        typer.Option(help="允许 daemon 可能运行时继续升级。"),
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    install_dir: Annotated[
        Path | None,
        typer.Option(help="全局命令目录, 默认使用 XUSHI_BIN_DIR 或 ~/.xushi/bin。"),
    ] = None,
) -> None:
    """手动执行安全升级。"""
    if not yes:
        message = "升级前会创建数据备份, 并替换全局命令二进制。是否继续?"
        if not typer.confirm(message):
            raise typer.Abort()
    try:
        result = _upgrade_manager(config_path, install_dir).apply(
            target_version=version,
            allow_dirty=allow_dirty,
            allow_running_daemon=allow_running_daemon,
        )
    except UpgradeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _echo_json(result.to_json())
