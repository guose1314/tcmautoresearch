# -*- coding: utf-8 -*-
"""TCMAutoResearch Web 启动入口。

启动方式::

    python -m src.web.main
    # 或指定端口
    python -m src.web.main --port 8080
"""

import argparse
import logging

import uvicorn

from src.web.app import create_app

logger = logging.getLogger(__name__)

# 构建 FastAPI 应用并注册路由
app = create_app()


def main() -> None:
    """解析命令行参数并启动 uvicorn 服务。"""
    parser = argparse.ArgumentParser(description="TCMAutoResearch Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    parser.add_argument("--log-level", default="info", help="日志级别 (默认: info)")
    args = parser.parse_args()

    logger.info("启动 Web 服务: %s:%s", args.host, args.port)
    uvicorn.run(
        "src.web.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
