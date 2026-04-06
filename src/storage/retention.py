"""数据保留策略管理器 — 自动清理缓存、归档科研数字资产。

解决磁盘持续增长问题，提供：
1. 缓存过期清理（LLM/Embedding/Pipeline 缓存）
2. 输出产物自动归档（ZIP 压缩归档到 archive/ 目录）
3. 日志轮转清理
4. 临时文件清理
5. 策略可配置（保留天数、最大磁盘占用）

用法::

    manager = RetentionManager(config)
    report = manager.execute_policy()  # 执行所有策略
    report = manager.cleanup_cache()    # 仅清理缓存
    report = manager.archive_outputs()  # 仅归档输出
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CleanupAction:
    """单次清理操作记录。"""
    action: str
    target: str
    freed_bytes: int = 0
    items_removed: int = 0
    items_archived: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RetentionReport:
    """策略执行报告。"""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""
    total_freed_bytes: int = 0
    total_removed: int = 0
    total_archived: int = 0
    actions: List[CleanupAction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── 默认策略参数 ──────────────────────────────────────────────────────────

_DEFAULT_POLICY = {
    # 缓存清理
    "cache_max_age_days": 30,           # 缓存条目最大保留天数
    "cache_max_size_mb": 2048,          # 缓存总大小上限 (MB)
    "cache_namespaces": ["llm", "embed", "pipeline", "default"],

    # 输出归档
    "output_archive_after_days": 90,    # 输出产物 N 天后归档
    "output_archive_dir": "./archive",  # 归档目录
    "output_keep_types": ["database"],  # 始终保留不归档的类型
    "output_max_size_mb": 10240,        # 输出目录大小上限 (MB)

    # 日志清理
    "log_max_age_days": 60,             # 日志最大保留天数
    "log_dir": "./logs",

    # 临时文件
    "temp_max_age_hours": 24,           # 临时文件最大保留小时数
    "temp_patterns": ["tmp*", "*.tmp", "*.bak"],

    # 研究结果 DB
    "research_db_vacuum_enabled": True,  # 定期 VACUUM
}


class RetentionManager:
    """数据保留策略管理器。

    Parameters
    ----------
    config :
        项目配置字典（从 config.yml 加载）。retention 策略从
        ``config["retention"]`` 读取，不存在则使用默认值。
    root_dir :
        项目根目录（默认当前工作目录）。
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        root_dir: str | Path = ".",
    ):
        self._config = config or {}
        self._policy = {**_DEFAULT_POLICY, **(self._config.get("retention") or {})}
        self._root = Path(root_dir).resolve()

    # ── 主入口 ────────────────────────────────────────────────────────────

    def execute_policy(self) -> RetentionReport:
        """执行完整的数据保留策略。"""
        report = RetentionReport()

        self._run_step(report, self.cleanup_cache)
        self._run_step(report, self.archive_outputs)
        self._run_step(report, self.cleanup_logs)
        self._run_step(report, self.cleanup_temp)
        self._run_step(report, self.vacuum_databases)

        report.completed_at = datetime.now().isoformat()
        report.total_freed_bytes = sum(a.freed_bytes for a in report.actions)
        report.total_removed = sum(a.items_removed for a in report.actions)
        report.total_archived = sum(a.items_archived for a in report.actions)

        logger.info(
            "保留策略执行完成: 释放 %.1f MB, 删除 %d 项, 归档 %d 项",
            report.total_freed_bytes / (1024 * 1024),
            report.total_removed,
            report.total_archived,
        )
        return report

    # ── 缓存清理 ──────────────────────────────────────────────────────────

    def cleanup_cache(self) -> List[CleanupAction]:
        """清理过期及超限的缓存条目。"""
        actions: List[CleanupAction] = []
        cache_dir = self._root / "cache"
        if not cache_dir.exists():
            return actions

        max_age_days = int(self._policy.get("cache_max_age_days", 30))
        cutoff = time.time() - (max_age_days * 86400)

        # 遍历所有缓存数据库文件
        for db_file in cache_dir.rglob("*.db"):
            action = CleanupAction(action="cache_cleanup", target=str(db_file))
            try:
                conn = sqlite3.connect(str(db_file), timeout=10)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    # 获取所有 cache_ 开头的表
                    tables = [
                        row[0] for row in
                        conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cache_%'"
                        ).fetchall()
                    ]
                    for table in tables:
                        # 删除过期条目
                        cursor = conn.execute(
                            f"DELETE FROM [{table}] WHERE created_at < ?", (cutoff,)
                        )
                        action.items_removed += cursor.rowcount
                    conn.commit()

                    # VACUUM 回收空间
                    size_before = db_file.stat().st_size
                    conn.execute("VACUUM")
                    size_after = db_file.stat().st_size
                    action.freed_bytes = max(0, size_before - size_after)
                finally:
                    conn.close()
            except Exception as exc:
                action.error = str(exc)
                logger.warning("缓存清理失败 %s: %s", db_file, exc)

            actions.append(action)
        return actions

    # ── 输出归档 ──────────────────────────────────────────────────────────

    def archive_outputs(self) -> List[CleanupAction]:
        """将过期输出产物压缩归档。"""
        actions: List[CleanupAction] = []
        output_dir = self._root / self._config.get("output", {}).get("directory", "output")
        if not output_dir.exists():
            return actions

        archive_dir = self._root / self._policy.get("output_archive_dir", "archive")
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_after_days = int(self._policy.get("output_archive_after_days", 90))
        keep_types = set(self._policy.get("output_keep_types", ["database"]))
        cutoff = time.time() - (archive_after_days * 86400)

        # 按月份分组归档
        to_archive: Dict[str, List[Path]] = {}
        for item in output_dir.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir() and item.name in ("web_console_jobs", "development", "production"):
                continue  # 跳过特殊目录

            try:
                mtime = item.stat().st_mtime
            except OSError:
                continue

            if mtime >= cutoff:
                continue

            # 检查是否为保留类型
            ext = item.suffix.lower()
            if ext == ".db" and "database" in keep_types:
                continue

            month_key = datetime.fromtimestamp(mtime).strftime("%Y-%m")
            to_archive.setdefault(month_key, []).append(item)

        for month_key, items in to_archive.items():
            action = CleanupAction(
                action="archive_output",
                target=f"archive/{month_key}.zip",
            )
            zip_path = archive_dir / f"research_output_{month_key}.zip"
            try:
                with zipfile.ZipFile(str(zip_path), "a", zipfile.ZIP_DEFLATED) as zf:
                    existing = set(zf.namelist())
                    for item in items:
                        arcname = item.name
                        if item.is_dir():
                            for child in item.rglob("*"):
                                if child.is_file():
                                    child_arcname = f"{item.name}/{child.relative_to(item)}"
                                    if child_arcname not in existing:
                                        zf.write(str(child), child_arcname)
                                        action.items_archived += 1
                        else:
                            if arcname not in existing:
                                zf.write(str(item), arcname)
                                action.items_archived += 1

                # 归档成功后删除原文件
                for item in items:
                    try:
                        freed = self._get_size(item)
                        if item.is_dir():
                            shutil.rmtree(str(item))
                        else:
                            item.unlink()
                        action.freed_bytes += freed
                        action.items_removed += 1
                    except OSError as exc:
                        logger.warning("删除已归档文件失败 %s: %s", item, exc)

            except Exception as exc:
                action.error = str(exc)
                logger.warning("归档失败 %s: %s", month_key, exc)

            actions.append(action)
        return actions

    # ── 日志清理 ──────────────────────────────────────────────────────────

    def cleanup_logs(self) -> List[CleanupAction]:
        """清理过期日志文件。"""
        actions: List[CleanupAction] = []
        log_dir = self._root / self._policy.get("log_dir", "logs")
        if not log_dir.exists():
            return actions

        max_age_days = int(self._policy.get("log_max_age_days", 60))
        cutoff = time.time() - (max_age_days * 86400)

        action = CleanupAction(action="log_cleanup", target=str(log_dir))
        for log_file in log_dir.rglob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff:
                    freed = log_file.stat().st_size
                    log_file.unlink()
                    action.items_removed += 1
                    action.freed_bytes += freed
            except OSError as exc:
                logger.warning("日志清理失败 %s: %s", log_file, exc)

        if action.items_removed > 0:
            actions.append(action)
        return actions

    # ── 临时文件清理 ──────────────────────────────────────────────────────

    def cleanup_temp(self) -> List[CleanupAction]:
        """清理临时文件和目录。"""
        actions: List[CleanupAction] = []
        max_age_hours = int(self._policy.get("temp_max_age_hours", 24))
        cutoff = time.time() - (max_age_hours * 3600)

        action = CleanupAction(action="temp_cleanup", target=str(self._root))
        for pattern in self._policy.get("temp_patterns", ["tmp*"]):
            for item in self._root.glob(pattern):
                # 安全检查：仅清理项目根目录下的临时项
                if not str(item.resolve()).startswith(str(self._root)):
                    continue
                # 不清理 venv 和 .git
                rel = str(item.relative_to(self._root))
                if any(rel.startswith(skip) for skip in ("venv", ".git", "src", "tests", "data")):
                    continue

                try:
                    mtime = item.stat().st_mtime
                    if mtime >= cutoff:
                        continue
                    freed = self._get_size(item)
                    if item.is_dir():
                        shutil.rmtree(str(item))
                    else:
                        item.unlink()
                    action.items_removed += 1
                    action.freed_bytes += freed
                except OSError as exc:
                    logger.warning("临时文件清理失败 %s: %s", item, exc)

        if action.items_removed > 0:
            actions.append(action)
        return actions

    # ── 数据库 VACUUM ─────────────────────────────────────────────────────

    def vacuum_databases(self) -> List[CleanupAction]:
        """对 SQLite 数据库执行 VACUUM 回收空间。"""
        actions: List[CleanupAction] = []
        if not self._policy.get("research_db_vacuum_enabled", True):
            return actions

        db_paths = [
            self._root / "data" / "tcmautoresearch.db",
            self._root / "output" / "research_results.db",
        ]
        # 也检查环境特定 DB
        for env in ("development", "production"):
            db_paths.append(self._root / "data" / env / "tcmautoresearch.db")

        for db_path in db_paths:
            if not db_path.exists():
                continue
            action = CleanupAction(action="vacuum", target=str(db_path))
            try:
                size_before = db_path.stat().st_size
                conn = sqlite3.connect(str(db_path), timeout=30)
                try:
                    conn.execute("VACUUM")
                finally:
                    conn.close()
                size_after = db_path.stat().st_size
                action.freed_bytes = max(0, size_before - size_after)
            except Exception as exc:
                action.error = str(exc)
                logger.warning("VACUUM 失败 %s: %s", db_path, exc)
            actions.append(action)
        return actions

    # ── 磁盘用量报告 ─────────────────────────────────────────────────────

    def disk_usage_report(self) -> Dict[str, Any]:
        """生成磁盘用量报告。"""
        dirs = {
            "output": self._root / self._config.get("output", {}).get("directory", "output"),
            "cache": self._root / "cache",
            "logs": self._root / self._policy.get("log_dir", "logs"),
            "data": self._root / "data",
            "archive": self._root / self._policy.get("output_archive_dir", "archive"),
        }
        usage: Dict[str, Any] = {}
        total = 0
        for name, path in dirs.items():
            if path.exists():
                size = self._get_size(path)
                file_count = sum(1 for _ in path.rglob("*") if _.is_file())
                usage[name] = {
                    "path": str(path),
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "file_count": file_count,
                }
                total += size
            else:
                usage[name] = {"path": str(path), "size_bytes": 0, "size_mb": 0, "file_count": 0}

        return {
            "total_bytes": total,
            "total_mb": round(total / (1024 * 1024), 2),
            "breakdown": usage,
            "policy": dict(self._policy),
            "timestamp": datetime.now().isoformat(),
        }

    # ── 辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
        return total

    def _run_step(
        self,
        report: RetentionReport,
        func,
    ) -> None:
        try:
            result = func()
            if isinstance(result, list):
                report.actions.extend(result)
            else:
                report.actions.append(result)
        except Exception as exc:
            report.errors.append(f"{func.__name__}: {exc}")
            logger.error("保留策略步骤失败 %s: %s", func.__name__, exc)
