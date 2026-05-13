"""序时命令行入口。"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Annotated, Any
from urllib import error, request

import typer

from xushi.bridges import (
    DEFAULT_HERMES_TOKEN_ENVS,
    DEFAULT_OPENCLAW_TOKEN_ENVS,
    parse_bool,
)
from xushi.capabilities import capabilities_payload
from xushi.config import (
    DEFAULT_DEV_TOKEN,
    DEFAULT_HOST,
    DEFAULT_PORT,
    Settings,
    default_config_path,
    load_config,
    write_initial_config,
)
from xushi.models import Executor, RunCallback, RunStatus, TaskCreate, TaskPatch
from xushi.plugins import bundled_plugin_status, install_bundled_plugin
from xushi.service import InvalidTaskConfigurationError, XushiService
from xushi.skills import bundled_skills_status, install_bundled_skills
from xushi.upgrade import UpgradeError, UpgradeManager, default_bin_dir


def configure_text_output_encoding() -> None:
    """配置文本输出编码, 避免 Windows CI 中中文 help 输出失败。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


configure_text_output_encoding()

app = typer.Typer(help="序时 xushi 本地日程与 agent 调度工具。")
upgrade_app = typer.Typer(help="手动安全升级序时。")
skills_app = typer.Typer(help="安装和检查随 xushi 版本携带的 xushi-skills。")
plugins_app = typer.Typer(help="安装和检查随 xushi 版本携带的 agent 插件。")
app.add_typer(upgrade_app, name="upgrade")
app.add_typer(skills_app, name="skills")
app.add_typer(plugins_app, name="plugins")


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


def _load_raw_config(config_path: Path | None = None) -> dict[str, Any]:
    """读取原始配置，不校验 executor 等运行时字段。"""
    try:
        return load_config(config_path)
    except (OSError, json.JSONDecodeError):
        return {}


def _coerce_port(value: Any) -> int:
    """把端口配置转成整数，失败时回退默认端口。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_PORT


def _daemon_connection(
    *,
    config_path: Path | None,
    base_url: str | None,
    token: str | None,
) -> tuple[str, str]:
    """解析调用运行中 daemon 所需的地址和 token。"""
    file_config = _load_raw_config(config_path)
    host = os.environ.get("XUSHI_HOST", str(file_config.get("host", DEFAULT_HOST)))
    port = _coerce_port(os.environ.get("XUSHI_PORT", file_config.get("port", DEFAULT_PORT)))
    resolved_base_url = (
        base_url or os.environ.get("XUSHI_BASE_URL") or f"http://{host}:{port}"
    ).rstrip("/")
    resolved_token = (
        token
        or os.environ.get("XUSHI_API_TOKEN")
        or str(file_config.get("api_token", DEFAULT_DEV_TOKEN))
    )
    return resolved_base_url, resolved_token


def _post_daemon_json(
    path: str,
    *,
    config_path: Path | None,
    base_url: str | None,
    token: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    """向运行中 daemon 发送 POST 请求并返回 JSON。"""
    resolved_base_url, resolved_token = _daemon_connection(
        config_path=config_path,
        base_url=base_url,
        token=token,
    )
    req = request.Request(
        f"{resolved_base_url}{path}",
        data=b"",
        headers={"Authorization": f"Bearer {resolved_token}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {
                "status": exc.code,
                "code": exc.code,
                "message": f"daemon request failed: HTTP {exc.code}",
                "data": None,
                "errors": [{"detail": body}],
            }
        _echo_json(payload)
        raise typer.Exit(1) from exc
    except (OSError, TimeoutError) as exc:
        typer.echo(f"daemon request failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    except json.JSONDecodeError as exc:
        typer.echo(f"daemon returned invalid JSON: {exc}", err=True)
        raise typer.Exit(1) from exc


def _executor_report(executor: Executor) -> dict[str, Any]:
    """生成 executor 的安装诊断信息。"""
    config = executor.config
    token_env = config.get("token_env")
    inline_token = bool(config.get("token"))
    default_token_envs = _default_token_envs(executor)
    default_token_env_present = [name for name in default_token_envs if os.environ.get(name)]
    diagnostics: list[str] = []

    token_env_present = bool(os.environ.get(str(token_env))) if token_env else None
    token_required = _executor_token_required(executor)
    token_available = inline_token or bool(token_env_present) or bool(default_token_env_present)
    if token_required and not token_available:
        if token_env:
            if not token_env_present:
                diagnostics.append(f"token_env_not_present_in_process:{token_env}")
        elif default_token_envs:
            diagnostics.append(
                f"default_token_envs_not_present:{','.join(default_token_envs)}"
            )
        else:
            diagnostics.append("token_env_missing")
    if inline_token:
        diagnostics.append("inline_token_configured_prefer_token_env")

    mode = str(config.get("mode") or _default_executor_mode(executor))
    webhook_url = config.get("webhook_url")
    insecure_tls = parse_bool(str(config.get("insecure_tls", "false")))
    if insecure_tls and webhook_url and str(webhook_url).startswith("http://"):
        diagnostics.append("insecure_tls_has_no_effect_for_http_url")

    if executor.kind == "openclaw" and mode == "hooks_agent":
        if not config.get("agent_id") and not config.get("agentId"):
            diagnostics.append("agent_id_missing_routes_to_openclaw_default_agent")
        if webhook_url and str(webhook_url).startswith("http://"):
            diagnostics.append("if_openclaw_tls_enabled_use_https_webhook_url")

    return {
        "id": executor.id,
        "kind": executor.kind,
        "enabled": executor.enabled,
        "mode": mode,
        "webhook_url": webhook_url,
        "token_env": token_env,
        "default_token_envs": list(default_token_envs),
        "default_token_env_present": default_token_env_present,
        "token_env_present": token_env_present,
        "token_available": token_available,
        "inline_token_configured": inline_token,
        "token_required": token_required,
        "agent_id": config.get("agent_id") or config.get("agentId"),
        "deliver": config.get("deliver"),
        "insecure_tls": insecure_tls,
        "diagnostics": diagnostics,
    }


def _executor_token_required(executor: Executor) -> bool:
    """判断 executor 是否需要鉴权 token。"""
    if executor.kind == "hermes":
        return parse_bool(str(executor.config.get("token_required", "true")))
    return executor.kind != "webhook"


def _default_executor_mode(executor: Executor) -> str:
    """返回 executor 默认模式。"""
    if executor.kind == "openclaw":
        return "hooks_agent"
    if executor.kind == "hermes":
        return "agent_webhook"
    return "template"


def _default_token_envs(executor: Executor) -> tuple[str, ...]:
    """返回 executor 默认 token 环境变量。"""
    if executor.kind == "openclaw":
        return DEFAULT_OPENCLAW_TOKEN_ENVS
    if executor.kind == "hermes":
        return DEFAULT_HERMES_TOKEN_ENVS
    return ()


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
        "base_url": f"http://{settings.host}:{settings.port}",
        "port_status": _check_port(settings.host, settings.port),
        "scheduler_interval_seconds": settings.scheduler_interval_seconds,
        "api_token": _mask_token(settings.api_token),
        "executors": [_executor_report(executor) for executor in settings.executors],
    }
    _echo_json(report)


@app.command()
def capabilities() -> None:
    """列出 CLI、HTTP API 和插件工具的 agent 能力清单。"""
    _echo_json(capabilities_payload())


@app.command()
def create(task_file: Path) -> None:
    """从 JSON 文件创建任务。"""
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    try:
        task = _service().create_task(TaskCreate.model_validate(payload))
    except InvalidTaskConfigurationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(task.model_dump_json(indent=2))


@app.command("list")
def list_tasks(
    limit: Annotated[int | None, typer.Option(help="最多返回多少条任务。")] = None,
) -> None:
    """列出任务。"""
    tasks = [task.model_dump(mode="json") for task in _service().list_tasks(limit=limit)]
    _echo_json(tasks)


@app.command("get")
def get_task(task_id: str) -> None:
    """查看单个任务详情。"""
    task = _service().get_task(task_id)
    if task is None:
        raise typer.BadParameter("task not found")
    typer.echo(task.model_dump_json(indent=2))


@app.command("update")
def update_task(task_id: str, patch_file: Path) -> None:
    """从 JSON 文件部分更新任务。"""
    payload = json.loads(patch_file.read_text(encoding="utf-8"))
    service = _service()
    try:
        task = service.update_task(task_id, TaskPatch.model_validate(payload))
    except InvalidTaskConfigurationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if task is None:
        raise typer.BadParameter("task not found")
    typer.echo(task.model_dump_json(indent=2))


@app.command("delete")
def delete_task(task_id: str) -> None:
    """归档任务并取消仍打开的运行记录。"""
    if not _service().delete_task(task_id):
        raise typer.BadParameter("task not found")
    _echo_json({"id": task_id, "status": "archived"})


@app.command()
def trigger(task_id: str) -> None:
    """手动触发任务。"""
    run = _service().trigger_task(task_id)
    typer.echo(run.model_dump_json(indent=2))


@app.command("complete")
def complete_task(task_id: str) -> None:
    """按任务记录完成，必要时创建手动完成锚点。"""
    service = _service()
    if service.get_task(task_id) is None:
        raise typer.BadParameter("task not found")
    run = service.complete_task(task_id)
    if run is None:
        raise typer.BadParameter("task has no completable run or completion anchor")
    typer.echo(run.model_dump_json(indent=2))


@app.command("runs")
def list_runs(
    task_id: Annotated[
        str | None,
        typer.Option(help="按任务 ID 过滤。"),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(help="按运行状态过滤, 如 pending_confirmation、following_up。"),
    ] = None,
    active_only: Annotated[bool, typer.Option(help="只显示仍需处理的运行记录。")] = False,
    limit: Annotated[int | None, typer.Option(help="最多返回多少条记录。")] = None,
) -> None:
    """列出运行记录。"""
    try:
        run_status = RunStatus(status) if status else None
    except ValueError as exc:
        raise typer.BadParameter(f"无效运行状态: {status}") from exc
    runs = [
        run.model_dump(mode="json")
        for run in _service().list_runs(
            task_id=task_id,
            status=run_status,
            active_only=active_only,
            limit=limit,
        )
    ]
    _echo_json(runs)


@app.command("confirm-latest")
def confirm_latest(task_id: str) -> None:
    """确认某任务最近一次待确认运行记录。"""
    service = _service()
    if service.get_task(task_id) is None:
        raise typer.BadParameter("task not found")
    run = service.confirm_latest_run(task_id)
    if run is None:
        raise typer.BadParameter("pending run not found")
    typer.echo(run.model_dump_json(indent=2))


@app.command("confirm")
def confirm_run(run_id: str) -> None:
    """确认指定运行记录已完成。"""
    run = _service().confirm_run(run_id)
    if run is None:
        raise typer.BadParameter("run not found")
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
            "然后调用 xushi reload-config 或重启 daemon 生效。"
        ),
        "executor": executor_config.model_dump(mode="json"),
    }
    _echo_json(output)


@app.command("reload-config")
def reload_config(
    config_path: Annotated[
        Path | None,
        typer.Option(help="配置文件路径, 默认使用 ~/.xushi/config.json。"),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(help="运行中 daemon 的 HTTP 地址, 默认由 XUSHI_BASE_URL 或配置文件推导。"),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option(help="运行中 daemon 当前接受的 API token, 默认从环境变量或配置文件读取。"),
    ] = None,
    timeout_seconds: Annotated[
        int,
        typer.Option(help="请求 daemon 的超时时间。"),
    ] = 10,
) -> None:
    """显式重新加载运行中 daemon 的 executor 和全局免打扰配置。"""
    payload = _post_daemon_json(
        "/api/v1/config/reload",
        config_path=config_path,
        base_url=base_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    _echo_json(payload)


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


@app.command()
def deliveries(
    limit: Annotated[int | None, typer.Option(help="最多返回多少条投递记录。")] = None,
) -> None:
    """列出投递计划。"""
    items = [
        delivery.model_dump(mode="json") for delivery in _service().list_deliveries(limit=limit)
    ]
    _echo_json(items)


@app.command("callback")
def callback_run(
    run_id: str,
    status: Annotated[
        str,
        typer.Option(help="最终状态, 只能是 succeeded 或 failed。"),
    ],
    result_file: Annotated[
        Path | None,
        typer.Option(help="包含 result 对象的 JSON 文件。"),
    ] = None,
    error_message: Annotated[
        str | None,
        typer.Option("--error", help="失败原因或补充错误信息。"),
    ] = None,
) -> None:
    """提交长任务最终结果。"""
    result_payload = {}
    if result_file is not None:
        result_payload = json.loads(result_file.read_text(encoding="utf-8"))
        if not isinstance(result_payload, dict):
            raise typer.BadParameter("result file must contain a JSON object")
    try:
        callback = RunCallback(status=status, result=result_payload, error=error_message)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    run = _service().callback_run(run_id, callback)
    if run is None:
        raise typer.BadParameter("run not found")
    typer.echo(run.model_dump_json(indent=2))


@app.command("retry-deliveries")
def retry_deliveries(
    limit: Annotated[
        int | None,
        typer.Option(help="最多重试多少条 failed delivery。"),
    ] = None,
) -> None:
    """重试仍需要投递的 failed delivery。"""
    items = [
        delivery.model_dump(mode="json")
        for delivery in _service().retry_failed_deliveries(limit=limit)
    ]
    _echo_json(items)


@skills_app.command("status")
def skills_status(
    targets: Annotated[
        str,
        typer.Option(help="逗号分隔的目标, 当前支持 openclaw,hermes。"),
    ] = "openclaw,hermes",
    openclaw_skills_dir: Annotated[
        Path | None,
        typer.Option(help="OpenClaw skills 根目录。"),
    ] = None,
    hermes_skills_dir: Annotated[
        Path | None,
        typer.Option(help="Hermes skills 根目录。"),
    ] = None,
) -> None:
    """查看内置 xushi-skills 与目标目录状态。"""
    try:
        _echo_json(
            bundled_skills_status(
                targets,
                openclaw_skills_dir=openclaw_skills_dir,
                hermes_skills_dir=hermes_skills_dir,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@skills_app.command("install")
def skills_install(
    targets: Annotated[
        str,
        typer.Option(help="逗号分隔的目标, 当前支持 openclaw,hermes。"),
    ] = "openclaw,hermes",
    openclaw_skills_dir: Annotated[
        Path | None,
        typer.Option(help="OpenClaw skills 根目录。"),
    ] = None,
    hermes_skills_dir: Annotated[
        Path | None,
        typer.Option(help="Hermes skills 根目录。"),
    ] = None,
) -> None:
    """从当前 xushi 应用内置资源安装 xushi-skills。"""
    try:
        _echo_json(
            install_bundled_skills(
                targets,
                openclaw_skills_dir=openclaw_skills_dir,
                hermes_skills_dir=hermes_skills_dir,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@plugins_app.command("status")
def plugin_status(
    target: Annotated[
        str,
        typer.Argument(help="插件目标, 当前支持 openclaw。"),
    ] = "openclaw",
    openclaw_plugins_dir: Annotated[
        Path | None,
        typer.Option(help="OpenClaw plugins 根目录。"),
    ] = None,
) -> None:
    """查看内置插件与目标目录状态。"""
    try:
        _echo_json(
            bundled_plugin_status(target, openclaw_plugins_dir=openclaw_plugins_dir)
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@plugins_app.command("install")
def plugin_install(
    target: Annotated[
        str,
        typer.Argument(help="插件目标, 当前支持 openclaw。"),
    ] = "openclaw",
    openclaw_plugins_dir: Annotated[
        Path | None,
        typer.Option(help="OpenClaw plugins 根目录。"),
    ] = None,
) -> None:
    """从当前 xushi 应用内置资源安装 agent 插件。"""
    try:
        _echo_json(
            install_bundled_plugin(target, openclaw_plugins_dir=openclaw_plugins_dir)
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


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
