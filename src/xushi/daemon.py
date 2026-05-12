"""序时 daemon 启动入口。"""

from __future__ import annotations

import argparse

import uvicorn

from xushi.api import create_app
from xushi.config import Settings


def main(argv: list[str] | None = None) -> None:
    """启动本地 HTTP 服务。"""
    parser = argparse.ArgumentParser(
        prog="xushi-daemon",
        description="启动序时 xushi 本地 HTTP daemon。",
    )
    parser.parse_args(argv)

    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
