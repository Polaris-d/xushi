"""手动 CLI 安全升级能力。"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from xushi import __version__

MANIFEST_FILE = "manifest.json"
HISTORY_FILE = "upgrade_history.jsonl"
DEFAULT_REPO_SLUG = "Polaris-d/xushi"
BINARY_NAMES = ("xushi", "xushi-daemon")
POST_UPGRADE_NOTICE = (
    "升级完成后请重新运行 xushi doctor, 确认 xushi-daemon 使用新版本和正确配置, "
    "然后发送一条唯一测试提醒并让用户确认目标渠道已收到。"
)


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
class DownloadedAsset:
    """已下载安装的 release 资产。"""

    name: str
    url: str
    path: Path
    sha256: str
    pending_replace: bool = False

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 可序列化结构。"""
        return {
            "name": self.name,
            "url": self.url,
            "path": str(self.path),
            "sha256": self.sha256,
            "pending_replace": self.pending_replace,
        }


@dataclass(frozen=True)
class UpgradeResult:
    """升级执行结果。"""

    status: str
    backup_id: str
    target_version: str
    assets: tuple[DownloadedAsset, ...]

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 可序列化结构。"""
        return {
            "status": self.status,
            "backup_id": self.backup_id,
            "target_version": self.target_version,
            "mode": "release_binary",
            "post_upgrade_notice": POST_UPGRADE_NOTICE,
            "assets": [asset.to_json() for asset in self.assets],
        }


ReleaseDownloader = Callable[[str, Path], None]


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
        repo_slug: str | None = None,
        platform_tag: str | None = None,
        downloader: ReleaseDownloader | None = None,
    ) -> None:
        self.config_path = config_path
        self.database_path = database_path
        self.state_dir = state_dir
        self.install_dir = install_dir
        self.host = host
        self.port = port
        self.repo_slug = repo_slug or os.environ.get("XUSHI_REPO_SLUG", DEFAULT_REPO_SLUG)
        self.platform_tag = platform_tag or normalize_platform_tag()
        self.downloader = downloader or download_file

    def status(self) -> dict[str, Any]:
        """返回本机升级状态。"""
        return {
            "current_version": __version__,
            "install_mode": "release_binary",
            "install_dir": str(self.install_dir),
            "platform_tag": self.platform_tag,
            "repo_slug": self.repo_slug,
            "config_path": str(self.config_path),
            "database_path": str(self.database_path),
            "backup_dir": str(self._backup_root()),
            "commands": [str(self._target_path(name)) for name in BINARY_NAMES],
            "backups": [backup.to_json() for backup in self.list_backups()],
        }

    def check(self, target_version: str | None = None) -> dict[str, Any]:
        """检查指定目标版本是否需要升级。"""
        resolved_version = target_version or "latest"
        update_available = None
        if target_version and target_version != "latest":
            update_available = _version_key(target_version) > _version_key(__version__)
        return {
            "current_version": __version__,
            "target_version": resolved_version,
            "update_available": update_available,
            "mode": "release_binary",
            "asset_urls": [
                release_download_url(
                    repo_slug=self.repo_slug,
                    version=resolved_version,
                    asset_name=release_binary_name(name, self.platform_tag),
                )
                for name in BINARY_NAMES
            ],
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
        """执行 release 二进制安装形态的手动升级。"""
        _ = allow_dirty
        if not allow_running_daemon and not self._port_available():
            raise UpgradeError("daemon 可能正在运行; 请先停止 daemon 后再升级")

        resolved_version = target_version or "latest"
        backup = self.create_backup()
        try:
            assets = tuple(self._download_release_assets(resolved_version))
        except UpgradeError:
            self._append_history(
                {
                    "operation": "apply",
                    "backup_id": backup.id,
                    "target_version": resolved_version,
                    "created_at": datetime.now(tz=UTC).isoformat(),
                    "status": "failed",
                }
            )
            raise

        result = UpgradeResult(
            status="succeeded",
            backup_id=backup.id,
            target_version=resolved_version,
            assets=assets,
        )
        self._append_history({"operation": "apply", **result.to_json()})
        return result

    def _download_release_assets(self, version: str) -> list[DownloadedAsset]:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        assets: list[DownloadedAsset] = []
        for name in BINARY_NAMES:
            asset_name = release_binary_name(name, self.platform_tag)
            url = release_download_url(
                repo_slug=self.repo_slug,
                version=version,
                asset_name=asset_name,
            )
            target = self._target_path(name)
            temp = target.with_name(f"{target.name}.download")
            if temp.exists():
                temp.unlink()
            try:
                self.downloader(url, temp)
            except OSError as exc:
                raise UpgradeError(f"下载 release 资产失败: {url}\n{exc}") from exc
            _make_executable(temp)
            pending_replace = self._replace_binary(temp, target)
            checksum_path = temp if pending_replace else target
            assets.append(
                DownloadedAsset(
                    name=asset_name,
                    url=url,
                    path=target,
                    sha256=_sha256(checksum_path),
                    pending_replace=pending_replace,
                )
            )
        return assets

    def _target_path(self, name: str) -> Path:
        return self.install_dir / local_binary_name(name, self.platform_tag)

    def _replace_binary(self, temp: Path, target: Path) -> bool:
        if _is_current_windows_executable(target):
            _schedule_windows_self_replace(temp, target)
            return True
        try:
            if target.exists():
                target.unlink()
            temp.replace(target)
        except OSError as exc:
            raise UpgradeError(
                f"无法替换全局命令 {target}; 请确认相关进程已退出后重试"
            ) from exc
        return False

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


def default_bin_dir() -> Path:
    """返回默认全局命令安装目录。"""
    configured = os.environ.get("XUSHI_BIN_DIR") or os.environ.get("XUSHI_INSTALL_DIR")
    return Path(configured) if configured else Path.home() / ".xushi" / "bin"


def normalize_platform_tag(system: str | None = None, machine: str | None = None) -> str:
    """生成与 GitHub Release 二进制资产一致的平台标签。"""
    raw_system = (system or platform.system()).lower()
    raw_machine = (machine or platform.machine()).lower()
    os_name = {
        "darwin": "macos",
        "windows": "windows",
        "linux": "linux",
    }.get(raw_system)
    arch_name = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(raw_machine)
    if os_name is None:
        raise UpgradeError(f"不支持的操作系统: {raw_system}")
    if arch_name is None:
        raise UpgradeError(f"不支持的 CPU 架构: {raw_machine}")
    return f"{os_name}-{arch_name}"


def release_binary_name(binary_name: str, platform_tag: str | None = None) -> str:
    """返回 release 中的二进制资产名称。"""
    resolved_tag = platform_tag or normalize_platform_tag()
    suffix = ".exe" if resolved_tag.startswith("windows-") else ""
    return f"{binary_name}-{resolved_tag}{suffix}"


def local_binary_name(binary_name: str, platform_tag: str | None = None) -> str:
    """返回写入本地 bin 目录后的全局命令文件名。"""
    resolved_tag = platform_tag or normalize_platform_tag()
    suffix = ".exe" if resolved_tag.startswith("windows-") else ""
    return f"{binary_name}{suffix}"


def release_download_url(*, repo_slug: str, version: str, asset_name: str) -> str:
    """返回 GitHub Release 资产下载 URL。"""
    if version == "latest":
        return f"https://github.com/{repo_slug}/releases/latest/download/{asset_name}"
    return f"https://github.com/{repo_slug}/releases/download/{version}/{asset_name}"


def download_file(url: str, target: Path) -> None:
    """下载 URL 到本地文件。"""
    request = urlrequest.Request(url, headers={"user-agent": f"xushi/{__version__}"})
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlrequest.urlopen(request, timeout=60) as response, target.open("wb") as file:
        shutil.copyfileobj(response, file)


def _is_current_windows_executable(path: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        return path.resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _schedule_windows_self_replace(temp: Path, target: Path) -> None:
    script = target.with_name(f"{target.name}.replace.ps1")
    script.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue",
                f"Move-Item -Force -LiteralPath '{_ps_quote(temp)}' "
                f"-Destination '{_ps_quote(target)}'",
                "Remove-Item -Force -LiteralPath $MyInvocation.MyCommand.Path",
                "",
            ]
        ),
        encoding="utf-8",
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _ps_quote(path: Path) -> str:
    return str(path).replace("'", "''")


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


def _make_executable(path: Path) -> None:
    if path.suffix == ".exe":
        return
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


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
