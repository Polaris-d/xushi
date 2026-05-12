"""daemon 后台循环测试。"""

from datetime import UTC, datetime

import pytest

from xushi.config import Settings
from xushi.daemon import main
from xushi.models import Schedule, TaskCreate
from xushi.runtime import run_scheduler_once
from xushi.service import XushiService


def test_daemon_help_exits_without_starting_server(monkeypatch, capsys) -> None:
    """daemon help 应直接输出帮助并退出, 不能启动常驻服务。"""

    def fail_run(*_args, **_kwargs) -> None:
        raise AssertionError("help command must not start uvicorn")

    monkeypatch.setattr("xushi.daemon.uvicorn.run", fail_run)

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    assert "xushi-daemon" in capsys.readouterr().out


def test_run_scheduler_once_triggers_due_tasks_and_follow_ups(tmp_path) -> None:
    service = XushiService(Settings(database_path=tmp_path / "xushi.db", api_token="test-token"))
    task = service.create_task(
        TaskCreate(
            title="到点提醒",
            schedule=Schedule(
                kind="one_shot",
                run_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            action={"type": "reminder", "payload": {"message": "到点了"}},
        )
    )

    runs = run_scheduler_once(service, now=datetime(2026, 5, 9, 12, 0, tzinfo=UTC))

    assert len(runs) == 1
    assert runs[0].task_id == task.id
