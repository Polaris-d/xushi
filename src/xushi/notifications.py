"""通知投递与事件模型。"""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class NotificationStatus(StrEnum):
    """通知投递状态。"""

    DELIVERED = "delivered"
    FALLBACK_LOGGED = "fallback_logged"
    FAILED = "failed"


class NotificationEvent(BaseModel):
    """通知事件。"""

    id: str
    run_id: str | None = None
    task_id: str | None = None
    kind: str = "reminder"
    channel: str = "system"
    title: str
    message: str
    status: NotificationStatus
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class NotificationDispatcher:
    """系统通知 best-effort 投递器。"""

    def notify(
        self,
        title: str,
        message: str,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        kind: str = "reminder",
    ) -> NotificationEvent:
        """投递通知并返回可审计事件。"""
        status = NotificationStatus.DELIVERED
        error = None
        try:
            self._notify_system(title, message)
        except Exception as exc:
            status = NotificationStatus.FALLBACK_LOGGED
            error = str(exc)
        return NotificationEvent(
            id=f"notification_{uuid4().hex}",
            run_id=run_id,
            task_id=task_id,
            kind=kind,
            title=title,
            message=message,
            status=status,
            error=error,
        )

    def _notify_system(self, title: str, message: str) -> None:
        system = platform.system().lower()
        if system == "windows":
            self._notify_windows(title, message)
            return
        if system == "darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return
        subprocess.run(
            ["notify-send", title, message],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def _notify_windows(self, title: str, message: str) -> None:
        escaped_title = title.replace("'", "''")
        escaped_message = message.replace("'", "''")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "$template = "
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02; "
            "$xml = "
            "[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template); "
            "$texts = $xml.GetElementsByTagName('text'); "
            f"$texts.Item(0).AppendChild($xml.CreateTextNode('{escaped_title}')) > $null; "
            f"$texts.Item(1).AppendChild($xml.CreateTextNode('{escaped_message}')) > $null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            "$notifier = "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('xushi'); "
            "$notifier.Show($toast);"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )


def notification_payload(event: NotificationEvent) -> dict[str, Any]:
    """返回可写入运行结果的通知摘要。"""
    return {
        "notification_id": event.id,
        "notification_status": event.status,
        "notification_channel": event.channel,
    }
