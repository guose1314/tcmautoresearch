# -*- coding: utf-8 -*-
"""T6.3 — Outbox worker CLI 入口（供 watchdog Start-Job 拉起）。

用法::

    python tools/run_outbox_worker.py --config config.yml --environment production
    python tools/run_outbox_worker.py --connection-string sqlite:///data/tcmautoresearch.db

设计要点
========

* 复用 ``src.web.app.create_app`` 同款数据库连接逻辑，避免漂移。
* 默认 handler 是一个安全的 **no-op**：仅记日志、不再投递到 Neo4j —— 由后续
  T-spec 决定真正的 Neo4j 投递路径（当前 stage 只要 worker 能稳定运行）。
* 所有日志写到 ``logs/outbox_worker.log``，watchdog 只关心进程生命周期。
* SIGINT/SIGTERM 调 ``worker.stop()``，配合 asyncio 优雅退出。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 允许从仓库根目录直接运行：python tools/run_outbox_worker.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.infrastructure.persistence import DatabaseManager  # noqa: E402
from src.storage.outbox import OutboxWorker, PgOutboxStore  # noqa: E402

LOG_FILE = _REPO_ROOT / "logs" / "outbox_worker.log"

logger = logging.getLogger("tcmar.outbox_worker")


def _configure_logging(log_file: Path = LOG_FILE) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(fmt)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 避免重复 handler（多次调用安全）
    root.handlers = [handler, stream]


def _build_connection_string_from_config(
    config_path: str, environment: Optional[str]
) -> str:
    """复用 web app 的配置加载，避免 DSN 计算逻辑漂移。"""
    from src.infrastructure.runtime_config_assembler import build_runtime_assembly

    assembly = build_runtime_assembly(
        config_path=config_path, environment=environment, entrypoint="outbox_worker"
    )
    cfg = dict(assembly.runtime_config or {})
    db_cfg: Dict[str, Any] = cfg.get("database", {}) or {}
    db_type = str(db_cfg.get("type", "sqlite")).strip().lower()
    if db_type == "sqlite":
        path = str(
            db_cfg.get("path") or os.path.join("data", "tcmautoresearch.db")
        ).strip()
        return f"sqlite:///{os.path.abspath(path)}"
    if db_type in ("postgresql", "postgres", "pg"):
        explicit = str(
            db_cfg.get("connection_string")
            or db_cfg.get("database_url")
            or db_cfg.get("url")
            or ""
        ).strip()
        if explicit:
            return explicit
        from urllib.parse import quote_plus

        host = str(db_cfg.get("host", "localhost")).strip()
        port = int(db_cfg.get("port", 5432))
        name = str(db_cfg.get("name", "tcmautoresearch")).strip()
        user = str(db_cfg.get("user", "postgres")).strip()
        pass_env = str(db_cfg.get("password_env", "TCM_DB_PASSWORD")).strip()
        password = os.environ.get(pass_env, "")
        return (
            f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{name}"
        )
    return str(
        db_cfg.get("connection_string")
        or db_cfg.get("database_url")
        or db_cfg.get("url")
        or ""
    ).strip()


def _default_handler(event: Dict[str, Any]) -> None:
    """占位 handler：仅记日志。真实的 Neo4j 投递由后续 T-spec 接入。"""
    logger.info(
        "outbox event drained id=%s type=%s aggregate=%s/%s",
        event.get("id"),
        event.get("event_type"),
        event.get("aggregate_type"),
        event.get("aggregate_id"),
    )


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TCMAutoResearch outbox worker")
    parser.add_argument("--config", default="config.yml", help="配置文件路径")
    parser.add_argument(
        "--environment",
        default=os.environ.get("TCM_ENVIRONMENT") or "production",
        help="环境名（development/production/test）",
    )
    parser.add_argument(
        "--connection-string",
        default=os.environ.get("TCM_DATABASE_URL"),
        help="显式数据库 DSN；提供后忽略 --config 的 database 块",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=1.0, help="轮询间隔（秒）"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="单次 claim 的最大事件数"
    )
    parser.add_argument(
        "--log-file",
        default=str(LOG_FILE),
        help="日志文件路径（默认 logs/outbox_worker.log）",
    )
    return parser.parse_args(argv)


async def _run_async(worker: OutboxWorker) -> None:
    loop = asyncio.get_running_loop()
    stop_signaled = asyncio.Event()

    def _request_stop(*_: Any) -> None:
        stop_signaled.set()

    # SIGTERM 在 Windows 上不可用；忽略 NotImplementedError。
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, ValueError):
            # Windows 上 add_signal_handler 不支持；走 KeyboardInterrupt 路径
            pass

    worker_task = asyncio.create_task(worker.run_forever(), name="outbox-worker")
    stop_task = asyncio.create_task(stop_signaled.wait(), name="stop-watch")
    done, pending = await asyncio.wait(
        {worker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    if stop_task in done and not worker_task.done():
        await worker.stop()
        await worker_task
    for task in pending:
        task.cancel()


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    _configure_logging(Path(args.log_file))

    if args.connection_string:
        conn_str = args.connection_string
        logger.info("using DSN from --connection-string / TCM_DATABASE_URL")
    else:
        conn_str = _build_connection_string_from_config(args.config, args.environment)
        logger.info("using DSN from config: %s", args.config)

    if not conn_str:
        logger.error("no database connection string available; aborting")
        return 2

    db = DatabaseManager(connection_string=conn_str)
    db.init_db()
    store = PgOutboxStore(db)
    worker = OutboxWorker(
        store,
        handler=_default_handler,
        poll_interval=args.poll_interval,
        batch_size=args.batch_size,
    )

    logger.info(
        "outbox worker starting (poll=%.2fs, batch=%d, dsn=%s)",
        args.poll_interval,
        args.batch_size,
        conn_str,
    )
    try:
        asyncio.run(_run_async(worker))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down")
    logger.info("outbox worker exited cleanly (stats=%s)", worker.stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
