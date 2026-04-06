"""统一输出资产目录 — output/ 下所有产物的索引与查询接口。

解决 JSON 文件散落在 output/ 下无统一查询入口的问题。
OutputCatalog 维护一个 SQLite 索引库，自动扫描+注册研究产物，
提供按类型、时间、周期 ID、关键词等多维查询能力。

用法::

    catalog = OutputCatalog("./output")
    catalog.scan()                              # 首次全量扫描
    catalog.register("cycle_abc_report.md", artifact_type="report", cycle_id="abc")
    results = catalog.query(artifact_type="report", after="2026-01-01")
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ── 产物类型分类 ─────────────────────────────────────────────────────────

ARTIFACT_TYPES = {
    "session_result": re.compile(r"research_session_\d+\.json$"),
    "cycle_result": re.compile(r"cycle_demo_results_\d+\.json$"),
    "imrd_report_md": re.compile(r"cycle_.*_imrd_report\.md$"),
    "imrd_report_docx": re.compile(r"cycle_.*_imrd_report\.docx$"),
    "quality_history": re.compile(r"quality-history\.jsonl$"),
    "quality_archive": re.compile(r"quality-improvement-archive.*\.json[l]?$"),
    "quality_feedback": re.compile(r"quality-feedback\.json$"),
    "quality_gate": re.compile(r"quality-gate\.json$"),
    "literature_result": re.compile(r"literature_retrieval_result\.json$"),
    "ctext_manifest": re.compile(r"ctext_batch_manifest\.json$"),
    "figure": re.compile(r"\.(png|svg|tiff|jpg)$", re.IGNORECASE),
    "job_state": re.compile(r"web_console_jobs/.+\.json$"),
    "database": re.compile(r"\.db$"),
}

_CYCLE_ID_PATTERN = re.compile(r"cycle_(\d+_[a-f0-9]+|\w+)")


@dataclass
class ArtifactRecord:
    """输出产物记录。"""
    path: str
    filename: str
    artifact_type: str
    size_bytes: int
    created_at: str
    modified_at: str
    cycle_id: Optional[str] = None
    metadata_json: str = "{}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS artifacts (
    path          TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    modified_at   TEXT NOT NULL,
    cycle_id      TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    indexed_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_cycle ON artifacts(cycle_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_modified ON artifacts(modified_at);
"""


class OutputCatalog:
    """output/ 目录下的产物统一索引。

    Parameters
    ----------
    output_dir :
        输出目录路径（默认 ``./output``）。
    catalog_db :
        索引数据库名称（默认 ``.output_catalog.db``，位于 output_dir 内）。
    """

    def __init__(
        self,
        output_dir: str | Path = "./output",
        catalog_db: str = ".output_catalog.db",
    ):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._output_dir / catalog_db
        self._lock = threading.Lock()
        self._init_db()

    # ── 初始化 ────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(_CATALOG_DDL)
        finally:
            conn.close()

    # ── 扫描 ──────────────────────────────────────────────────────────────

    def scan(self, full: bool = False) -> int:
        """扫描 output/ 目录，注册新发现的产物到索引。

        Parameters
        ----------
        full :
            True = 重建全量索引；False = 仅索引尚未注册的文件。

        Returns
        -------
        int
            新注册的产物数量。
        """
        registered = 0
        conn = self._get_conn()
        try:
            if full:
                conn.execute("DELETE FROM artifacts")
                conn.commit()

            existing = set()
            if not full:
                cursor = conn.execute("SELECT path FROM artifacts")
                existing = {row[0] for row in cursor.fetchall()}

            for root, _dirs, files in os.walk(str(self._output_dir)):
                for filename in files:
                    if filename.startswith("."):
                        continue
                    filepath = os.path.join(root, filename)
                    relpath = os.path.relpath(filepath, str(self._output_dir)).replace("\\", "/")
                    if relpath in existing:
                        continue

                    artifact_type = self._classify(relpath, filename)
                    cycle_id = self._extract_cycle_id(filename)
                    try:
                        stat = os.stat(filepath)
                    except OSError:
                        continue

                    conn.execute(
                        """INSERT OR REPLACE INTO artifacts
                           (path, filename, artifact_type, size_bytes,
                            created_at, modified_at, cycle_id, metadata_json, indexed_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            relpath,
                            filename,
                            artifact_type,
                            stat.st_size,
                            datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            cycle_id,
                            "{}",
                            datetime.now().isoformat(),
                        ),
                    )
                    registered += 1
            conn.commit()
        finally:
            conn.close()

        logger.info("OutputCatalog 扫描完成: 新增 %d 条记录", registered)
        return registered

    # ── 注册 ──────────────────────────────────────────────────────────────

    def register(
        self,
        relpath: str,
        *,
        artifact_type: Optional[str] = None,
        cycle_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """手动注册一个产物到索引。"""
        filepath = self._output_dir / relpath
        if not filepath.exists():
            logger.warning("注册失败：文件不存在 %s", filepath)
            return False

        filename = filepath.name
        stat = filepath.stat()
        artifact_type = artifact_type or self._classify(relpath, filename)
        cycle_id = cycle_id or self._extract_cycle_id(filename)

        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO artifacts
                   (path, filename, artifact_type, size_bytes,
                    created_at, modified_at, cycle_id, metadata_json, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relpath.replace("\\", "/"),
                    filename,
                    artifact_type,
                    stat.st_size,
                    datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    cycle_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # ── 查询 ──────────────────────────────────────────────────────────────

    def query(
        self,
        *,
        artifact_type: Optional[str] = None,
        cycle_id: Optional[str] = None,
        filename_contains: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        min_size: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "modified_at DESC",
    ) -> List[Dict[str, Any]]:
        """多维查询产物索引。"""
        clauses: List[str] = []
        params: List[Any] = []

        if artifact_type:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        if cycle_id:
            clauses.append("cycle_id = ?")
            params.append(cycle_id)
        if filename_contains:
            clauses.append("filename LIKE ?")
            params.append(f"%{filename_contains}%")
        if after:
            clauses.append("modified_at >= ?")
            params.append(after)
        if before:
            clauses.append("modified_at <= ?")
            params.append(before)
        if min_size is not None:
            clauses.append("size_bytes >= ?")
            params.append(min_size)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        # Whitelist order_by to prevent injection
        allowed_orders = {
            "modified_at DESC", "modified_at ASC",
            "created_at DESC", "created_at ASC",
            "size_bytes DESC", "size_bytes ASC",
            "filename ASC", "filename DESC",
            "artifact_type ASC", "artifact_type DESC",
        }
        if order_by not in allowed_orders:
            order_by = "modified_at DESC"

        sql = f"SELECT * FROM artifacts {where} ORDER BY {order_by} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = self._get_conn()
        try:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def count(self, *, artifact_type: Optional[str] = None) -> int:
        """统计产物数量。"""
        conn = self._get_conn()
        try:
            if artifact_type:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE artifact_type = ?",
                    (artifact_type,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM artifacts")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def summary(self) -> Dict[str, Any]:
        """返回产物索引摘要统计。"""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
            by_type = {}
            for row in conn.execute(
                "SELECT artifact_type, COUNT(*), SUM(size_bytes) "
                "FROM artifacts GROUP BY artifact_type"
            ).fetchall():
                by_type[row[0]] = {"count": row[1], "total_bytes": row[2] or 0}
            cycles = conn.execute(
                "SELECT COUNT(DISTINCT cycle_id) FROM artifacts WHERE cycle_id IS NOT NULL"
            ).fetchone()[0]
            return {
                "total_artifacts": total,
                "by_type": by_type,
                "distinct_cycles": cycles,
                "output_dir": str(self._output_dir),
                "catalog_db": str(self._db_path),
            }
        finally:
            conn.close()

    def get_absolute_path(self, relpath: str) -> str:
        """将相对路径转为绝对路径。"""
        return str(self._output_dir / relpath)

    def remove_stale(self) -> int:
        """移除索引中已不存在于磁盘的记录。"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT path FROM artifacts")
            stale = []
            for row in cursor.fetchall():
                if not (self._output_dir / row[0]).exists():
                    stale.append(row[0])
            if stale:
                conn.executemany("DELETE FROM artifacts WHERE path = ?", [(p,) for p in stale])
                conn.commit()
            logger.info("移除 %d 条过期索引记录", len(stale))
            return len(stale)
        finally:
            conn.close()

    # ── 分类辅助 ──────────────────────────────────────────────────────────

    @staticmethod
    def _classify(relpath: str, filename: str) -> str:
        for atype, pattern in ARTIFACT_TYPES.items():
            if pattern.search(relpath):
                return atype
        ext = Path(filename).suffix.lower()
        ext_map = {
            ".json": "json_data",
            ".jsonl": "jsonl_data",
            ".md": "markdown",
            ".docx": "document",
            ".pdf": "pdf",
            ".txt": "text",
            ".csv": "csv",
            ".html": "html",
        }
        return ext_map.get(ext, "unknown")

    @staticmethod
    def _extract_cycle_id(filename: str) -> Optional[str]:
        match = _CYCLE_ID_PATTERN.search(filename)
        return match.group(1) if match else None
