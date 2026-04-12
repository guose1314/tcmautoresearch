# -*- coding: utf-8 -*-
"""TCMAutoResearch Web 启动入口。

启动方式::

    python -m src.web.main --config config.yml --environment development
    python -m src.web.main --port 8080 --reload
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Optional, Sequence

import uvicorn

from src.web.app import create_app

logger = logging.getLogger(__name__)

_CONFIG_PATH_ENV = "TCM_CONFIG_PATH"


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TCMAutoResearch Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    parser.add_argument("--log-level", default="info", help="日志级别 (默认: info)")
    parser.add_argument("--config", dest="config_path", default=None, help="主配置文件路径")
    parser.add_argument("--environment", default=None, help="目标配置环境")
    return parser


def create_uvicorn_app():
    return create_app(
        config_path=_normalize_optional_text(os.getenv(_CONFIG_PATH_ENV)),
        environment=_normalize_optional_text(os.getenv("TCM_ENV")),
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    """解析命令行参数并启动 uvicorn 服务。"""
    parser = _build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    config_path = _normalize_optional_text(args.config_path)
    environment = _normalize_optional_text(args.environment)
    if config_path is None:
        os.environ.pop(_CONFIG_PATH_ENV, None)
    else:
        os.environ[_CONFIG_PATH_ENV] = config_path
    if environment is None:
        os.environ.pop("TCM_ENV", None)
    else:
        os.environ["TCM_ENV"] = environment

    logger.info("启动 Web 服务: %s:%s (config=%s, environment=%s)", args.host, args.port, config_path or "<default>", environment or "<auto>")
    uvicorn.run(
        "src.web.main:create_uvicorn_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
