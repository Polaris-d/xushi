"""手动 CLI 安全升级能力。"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sqlite3
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xushi import __version__

MANIFEST_FILE = "manifest.json"
HISTORY_FILE = "upgrade_history.jsonl"


class UpgradeError(RuntimeError):
    """升级流程错误。"""


@dataclass(frozen=True)
class BackupFile:
    """备份文件记录。"""

    kind: str
    source: Path
    backup: Path
    sha256: str

    def to_json(self) -> dict[str, str]:
        """转换为 JSON 可序列化结构。"""
        return {
            "kind": self.kind,
            "source": str(self.source),
            "backup": str(self.backup),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class UpgradeBackup:
    """升级备份快照。"""

    id: str
    path: Path
    files: tuple[BackupFile, ...]
    created_at: datetime

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 可序列化结构。"""
        return {
            "id": self.id,
            "path": str(self.path),
            "created_at": self.created_at.isoformat(),
            "app_version": __version__,
            "files": [file.to_json() for file in self.files],
        }


@dataclass(frozen=True)
class CommandResult:
    """外部命令执行结果。"""

    command: list[str]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class UpgradeResult:
    """升级执行结果。"""

    status: str
    backup_id: str
    target_version: str | None
    commands: tuple[CommandResult, ...]

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 可序列化结构。"""
        return {
            "status": self.status,
            "backup_id": self.backup_id,
            "target_version": self.target_version,
            "commands": [
                {
                    "command": command.command,
                    "cwd": str(command.cwd),
                    "returncode": command.returncode,
                    "stdout": command.stdout,
                    "stderr": command.stderr,
                }
                for command in self.commands
            ],
        }


CommandRunner = Callable[[list[str], Path], CommandResult]


class UpgradeManager:
    """手动升级管理器。"""

    def __init__(
        self,
        *,
        config_path: Path,
        database_path: Path,
        state_dir: Path,
        install_dir: Path,
        host: str = "127.0.0.1",
        port: int = 18766,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.config_path = config_path
        self.database_path = database_path
        self.state_dir = state_dir
        self.install_dir = install_dir
        self.host = host
        self.port = port
        self.command_runner = command_runner or run_command

    def status(self) -> dict[str, Any]:
        """返回本机升级状态。"""
        return {
            "current_version": __version__,
            "install_dir": str(self.install_dir),
            "config_path": str(self.config_path),
            "database_path": str(self.database_path),
            "backup_dir": str(self._backup_root()),
            "backups": [backup.to_json() for backup in self.list_backups()],
        }

    def check(self, target_version: str | None = None) -> dict[str, Any]:
        """检查指定目标版本是否需要升级。"""
        return {
            "current_version": __version__,
            "target_version": target_version,
            "update_available": bool(
                target_version and _version_key(target_version) > _version_key(__version__)
            ),
            "mode": "manual_cli",
        }

    def create_backup(self, now: datetime | None = None) -> UpgradeBackup:
        """创建配置和数据库备份。"""
        created_at = now or datetime.now(tz=UTC)
        base_backup_id = f"upgrade-{created_at.strftime('%Y%m%dT%H%M%SZ')}"
        backup_id = base_backup_id
        backup_path = self._backup_root() / backup_id
        counter = 2
        while backup_path.exists():
            backup_id = f"{base_backup_id}-{counter}"
            backup_path = self._backup_root() / backup_id
            counter += 1
        backup_path.mkdir(parents=True, exist_ok=False)
        files: list[BackupFile] = []

        if self.config_path.exists():
            files.append(self._copy_file("config", self.config_path, backup_path / "config.json"))
        if self.database_path.exists():
            database_backup = backup_path / self.database_path.name
            self._backup_sqlite_database(database_backup)
            files.append(
                BackupFile(
                    kind="database",
                    source=self.database_path,
                    backup=database_backup,
                    sha256=_sha256(database_backup),
                )
            )
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.database_path}{suffix}")
            if sidecar.exists():
                files.append(
                    self._copy_file(f"database{suffix}", sidecar, backup_path / sidecar.name)
                )

        backup = UpgradeBackup(
            id=backup_id,
            path=backup_path,
            files=tuple(files),
            created_at=created_at,
        )
        (backup_path / MANIFEST_FILE).write_text(
            json.dumps(backup.to_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return backup

    def list_backups(self) -> list[UpgradeBackup]:
        """列出已有升级备份。"""
        backup_root = self._backup_root()
        if not backup_root.exists():
            return []
        backups: list[UpgradeBackup] = []
        for manifest_path in sorted(backup_root.glob(f"*/{MANIFEST_FILE}")):
            backups.append(_load_backup_manifest(manifest_path))
        return backups

    def rollback(self, backup_id: str | None = None) -> UpgradeBackup:
        """从备份恢复配置和数据库。"""
        backup = self._resolve_backup(backup_id)
        if any(file.kind == "database" for file in backup.files):
            self._remove_database_sidecars()
        for file in backup.files:
            file.source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file.backup, file.source)
        self._append_history(
            {
                "operation": "rollback",
                "backup_id": backup.id,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "status": "succeeded",
            }
        )
        return backup

    def apply(
        self,
        *,
        target_version: str | None = None,
        allow_dirty: bool = False,
        allow_running_daemon: bool = False,
    ) -> UpgradeResult:
        """执行 git 安装形态的手动升级。"""
        if not (self.install_dir / ".git").exists():
            raise UpgradeError(f"当前仅支持 git 安装目录升级: {self.install_dir}")
        if not allow_running_daemon and not self._port_available():
            raise UpgradeError("daemon 可能正在运行; 请先停止 daemon 后再升级")

        commands: list[CommandResult] = []
        if not allow_dirty:
            status_result = self._run(["git", "status", "--porcelain"])
            commands.append(status_result)
            if status_result.stdout.strip():
                raise UpgradeError("安装目录存在未提交改动, 请先处理后再升级")

        old_ref = self._run(["git", "rev-parse", "HEAD"])
        commands.append(old_ref)
        backup = self.create_backup()

        try:
            for command in self._upgrade_commands(target_version):
                commands.append(self._run(command))
        except UpgradeError:
            self._append_history(
                {
                    "operation": "apply",
                    "backup_id": backup.id,
                    "target_version": target_version,
                    "created_at": datetime.now(tz=UTC).isoformat(),
                    "status": "failed",
                }
            )
            raise

        result = UpgradeResult(
            status="succeeded",
            backup_id=backup.id,
            target_version=target_version,
            commands=tuple(commands),
        )
        self._append_history({"operation": "apply", **result.to_json()})
        return result

    def _upgrade_commands(self, target_version: str | None) -> list[list[str]]:
        commands = [["git", "fetch", "--tags", "--prune"]]
        if target_version:
            commands.append(["git", "checkout", "--detach", target_version])
        else:
            commands.append(["git", "pull", "--ff-only"])
        commands.append(["uv", "sync"])
        return commands

    def _run(self, command: list[str]) -> CommandResult:
        result = self.command_runner(command, self.install_dir)
        if result.returncode != 0:
            raise UpgradeError(
                f"命令执行失败: {' '.join(command)}\n{result.stderr or result.stdout}"
            )
        return result

    def _backup_root(self) -> Path:
        return self.state_dir / "backups"

    def _resolve_backup(self, backup_id: str | None) -> UpgradeBackup:
        backups = self.list_backups()
        if not backups:
            raise UpgradeError("没有可用备份")
        if backup_id is None:
            return backups[-1]
        for backup in backups:
            if backup.id == backup_id:
                return backup
        raise UpgradeError(f"未找到备份: {backup_id}")

    def _copy_file(self, kind: str, source: Path, target: Path) -> BackupFile:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return BackupFile(kind=kind, source=source, backup=target, sha256=_sha256(target))

    def _backup_sqlite_database(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as source_conn, sqlite3.connect(
            target
        ) as target_conn:
            source_conn.backup(target_conn)

    def _remove_database_sidecars(self) -> None:
        """恢复主数据库前移除现有 WAL/SHM sidecar。"""
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.database_path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()

    def _port_available(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((self.host, self.port))
            except OSError:
                return False
        return True

    def _append_history(self, payload: dict[str, Any]) -> None:
        history_path = self.state_dir / HISTORY_FILE
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_command(command: list[str], cwd: Path) -> CommandResult:
    """执行外部命令。"""
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=command,
        cwd=cwd,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _load_backup_manifest(manifest_path: Path) -> UpgradeBackup:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return UpgradeBackup(
        id=str(data["id"]),
        path=Path(data["path"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        files=tuple(
            BackupFile(
                kind=str(file["kind"]),
                source=Path(file["source"]),
                backup=Path(file["backup"]),
                sha256=str(file["sha256"]),
            )
            for file in data["files"]
        ),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_key(version: str) -> tuple[int, ...]:
    normalized = version.removeprefix("v")
    parts: list[int] = []
    for part in normalized.split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)
