"""存储可观测性聚合 — 滚动事务指标与健康评分。

将离散的 ``TransactionResult.to_observation_dict()`` 数据聚合为
运维可消费的时序指标与健康分数。

用法::

    obs = StorageObservability()
    obs.record(txn_result)   # 每次事务后调用
    report = obs.get_health_report()
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

_WINDOW_SIZE = 500  # 滚动窗口大小（最近 N 笔事务）


@dataclass
class _ObservationRecord:
    """单笔事务观测快照。"""
    success: bool
    storage_mode: str
    total_ms: float
    pg_flush_ms: float
    neo4j_execute_ms: float
    pg_commit_ms: float
    neo4j_op_count: int
    needs_backfill: bool
    compensations_applied: int
    timestamp: float  # monotonic time for windowing


class StorageObservability:
    """滚动事务指标聚合器。

    线程安全：内部使用 Lock 保护状态。
    """

    def __init__(self, window_size: int = _WINDOW_SIZE) -> None:
        self._lock = threading.Lock()
        self._window: Deque[_ObservationRecord] = deque(maxlen=window_size)
        self._total_count = 0
        self._total_failures = 0
        self._total_compensations = 0
        self._total_backfills = 0
        self._started_at = time.monotonic()

    def record(self, result: Any) -> None:
        """记录一笔事务结果观测。

        Parameters
        ----------
        result :
            TransactionResult 实例（或 duck-type 兼容对象）。
        """
        obs = _ObservationRecord(
            success=bool(getattr(result, "success", True)),
            storage_mode=str(getattr(result, "storage_mode", "")),
            total_ms=float(getattr(result, "total_ms", 0.0)),
            pg_flush_ms=float(getattr(result, "pg_flush_ms", 0.0)),
            neo4j_execute_ms=float(getattr(result, "neo4j_execute_ms", 0.0)),
            pg_commit_ms=float(getattr(result, "pg_commit_ms", 0.0)),
            neo4j_op_count=int(getattr(result, "neo4j_op_count", 0)),
            needs_backfill=bool(getattr(result, "needs_backfill", False)),
            compensations_applied=int(getattr(result, "compensations_applied", 0)),
            timestamp=time.monotonic(),
        )
        with self._lock:
            self._window.append(obs)
            self._total_count += 1
            if not obs.success:
                self._total_failures += 1
            self._total_compensations += obs.compensations_applied
            if obs.needs_backfill:
                self._total_backfills += 1

    def get_health_report(self) -> Dict[str, Any]:
        """生成存储健康报告（基于滚动窗口）。"""
        with self._lock:
            window = list(self._window)
            total = self._total_count
            total_failures = self._total_failures
            total_compensations = self._total_compensations
            total_backfills = self._total_backfills

        if not window:
            return {
                "health_score": 1.0,
                "window_size": 0,
                "lifetime_transactions": total,
                "status": "no_data",
            }

        # 窗口内指标
        successes = sum(1 for o in window if o.success)
        failures = len(window) - successes
        backfills = sum(1 for o in window if o.needs_backfill)
        compensations = sum(o.compensations_applied for o in window)

        # 延迟分位数
        latencies = sorted(o.total_ms for o in window)
        p50 = latencies[len(latencies) // 2] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
        avg_ms = sum(latencies) / len(latencies) if latencies else 0

        # Neo4j 延迟
        neo4j_latencies = sorted(o.neo4j_execute_ms for o in window if o.neo4j_op_count > 0)
        neo4j_p50 = neo4j_latencies[len(neo4j_latencies) // 2] if neo4j_latencies else 0
        neo4j_p95 = neo4j_latencies[int(len(neo4j_latencies) * 0.95)] if neo4j_latencies else 0

        # 模式分布
        mode_counts: Dict[str, int] = {}
        for o in window:
            mode_counts[o.storage_mode] = mode_counts.get(o.storage_mode, 0) + 1

        # 健康分数（0.0 ~ 1.0）
        success_rate = successes / len(window) if window else 1.0
        backfill_penalty = min(backfills / len(window), 0.3) if window else 0.0
        health_score = max(0.0, success_rate - backfill_penalty)

        return {
            "health_score": round(health_score, 4),
            "status": _classify_health(health_score),
            "window_size": len(window),
            "lifetime_transactions": total,
            "lifetime_failures": total_failures,
            "lifetime_compensations": total_compensations,
            "lifetime_backfills": total_backfills,
            "window_metrics": {
                "success_count": successes,
                "failure_count": failures,
                "backfill_count": backfills,
                "compensation_count": compensations,
                "success_rate": round(success_rate, 4),
            },
            "latency_ms": {
                "avg": round(avg_ms, 2),
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2),
            },
            "neo4j_latency_ms": {
                "p50": round(neo4j_p50, 2),
                "p95": round(neo4j_p95, 2),
            },
            "mode_distribution": mode_counts,
            "uptime_sec": round(time.monotonic() - self._started_at, 1),
        }

    def get_recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的失败事务观测。"""
        with self._lock:
            failures = [o for o in self._window if not o.success]
        return [
            {
                "storage_mode": o.storage_mode,
                "total_ms": round(o.total_ms, 2),
                "neo4j_op_count": o.neo4j_op_count,
                "compensations_applied": o.compensations_applied,
                "needs_backfill": o.needs_backfill,
            }
            for o in failures[-limit:]
        ]


def _classify_health(score: float) -> str:
    """将健康分数分级为状态标签。"""
    if score >= 0.95:
        return "healthy"
    elif score >= 0.80:
        return "degraded"
    elif score >= 0.50:
        return "unhealthy"
    return "critical"
