"""序时 daemon 启动入口。"""

from __future__ import annotations

import uvicorn

from xushi.api import create_app
from xushi.config import Settings


def main() -> None:
    """启动本地 HTTP 服务。"""
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
