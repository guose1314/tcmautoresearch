"""结构化存储一致性状态合同。

提供 :class:`StorageConsistencyState` — 一个稳定、对调用方友好的数据结构，
将分散在 ``StorageBackendFactory``、``TransactionResult``、``health_check``、
``monitoring`` 与 backfill 报告中的存储状态统一收口为单一合同。

调用方（runtime metadata、dashboard、运维检查）可通过此合同一眼区分：
- **dual_write** — PG + Neo4j 实时双写完成
- **pg_only**    — 仅 PG 可用，Neo4j 未启用或初始化失败
- **sqlite_fallback** — 非 PostgreSQL 环境
- **uninitialized**   — 工厂尚未初始化
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

# ── 模式常量 ──────────────────────────────────────────────────────────────

MODE_DUAL_WRITE = "dual_write"
MODE_PG_ONLY = "pg_only"
MODE_SQLITE_FALLBACK = "sqlite_fallback"
MODE_UNINITIALIZED = "uninitialized"

_VALID_MODES = frozenset({
    MODE_DUAL_WRITE,
    MODE_PG_ONLY,
    MODE_SQLITE_FALLBACK,
    MODE_UNINITIALIZED,
})

# ── 后端状态常量 ──────────────────────────────────────────────────────────

STATUS_ACTIVE = "active"
STATUS_DEGRADED = "degraded"
STATUS_DISABLED = "disabled"
STATUS_ERROR = "error"
STATUS_SQLITE_FALLBACK = "sqlite_fallback"
STATUS_UNINITIALIZED = "uninitialized"


@dataclass
class StorageConsistencyState:
    """结构化存储一致性状态 — 单一事实源。

    Attributes
    ----------
    mode :
        运行模式，取值为 ``MODE_*`` 常量之一。
    pg_status :
        关系型数据库状态：active | sqlite_fallback | error | uninitialized。
    neo4j_status :
        图数据库状态：active | degraded | disabled | error | uninitialized。
    neo4j_degradation_reason :
        Neo4j 降级原因（仅在 neo4j_status 非 active 时有值）。
    schema_drift_detected :
        是否检测到 schema drift（仅 PostgreSQL 环境生效）。
    initialized :
        工厂是否已完成初始化。
    db_type :
        后端数据库类型：postgresql | sqlite。
    timestamp :
        本次状态快照的 ISO 时间戳。
    """

    mode: str
    pg_status: str = STATUS_UNINITIALIZED
    neo4j_status: str = STATUS_UNINITIALIZED
    neo4j_degradation_reason: Optional[str] = None
    schema_drift_detected: bool = False
    initialized: bool = False
    db_type: str = "sqlite"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # ── 便捷查询 ──────────────────────────────────────────────────────

    @property
    def is_dual_write(self) -> bool:
        return self.mode == MODE_DUAL_WRITE

    @property
    def is_pg_only(self) -> bool:
        return self.mode == MODE_PG_ONLY

    @property
    def is_degraded(self) -> bool:
        return self.mode in (MODE_PG_ONLY, MODE_SQLITE_FALLBACK)

    @property
    def summary(self) -> str:
        """人类可读的单行状态摘要。"""
        if self.mode == MODE_DUAL_WRITE:
            base = "PG + Neo4j 实时双写"
        elif self.mode == MODE_PG_ONLY:
            base = f"仅 PG 模式（Neo4j: {self.neo4j_status}）"
        elif self.mode == MODE_SQLITE_FALLBACK:
            base = "SQLite 降级模式"
        else:
            base = "存储未初始化"

        if self.schema_drift_detected:
            base += " | schema drift 待治理"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（适用于 JSON 输出、runtime metadata 嵌入）。"""
        result: Dict[str, Any] = {
            "mode": self.mode,
            "pg_status": self.pg_status,
            "neo4j_status": self.neo4j_status,
            "schema_drift_detected": self.schema_drift_detected,
            "initialized": self.initialized,
            "db_type": self.db_type,
            "summary": self.summary,
            "timestamp": self.timestamp,
        }
        if self.neo4j_degradation_reason:
            result["neo4j_degradation_reason"] = self.neo4j_degradation_reason
        return result


def build_consistency_state(
    *,
    initialized: bool,
    db_type: str,
    pg_status: str,
    neo4j_enabled: bool,
    neo4j_status: str,
    neo4j_driver_connected: bool,
    schema_drift_detected: bool = False,
) -> StorageConsistencyState:
    """从工厂报告字段构造 :class:`StorageConsistencyState`。

    这是唯一推荐的构造路径 — 所有消费方（factory、monitoring、runtime）
    都应通过此函数获得一致的状态判定逻辑。
    """
    if not initialized:
        return StorageConsistencyState(
            mode=MODE_UNINITIALIZED,
            pg_status=STATUS_UNINITIALIZED,
            neo4j_status=STATUS_UNINITIALIZED,
            initialized=False,
            db_type=db_type,
        )

    # PG 状态
    normalized_pg_status: str
    if db_type != "postgresql":
        normalized_pg_status = STATUS_SQLITE_FALLBACK
    elif pg_status == "active":
        normalized_pg_status = STATUS_ACTIVE
    else:
        normalized_pg_status = STATUS_ERROR

    # Neo4j 状态
    normalized_neo4j_status: str
    neo4j_reason: Optional[str] = None
    if not neo4j_enabled:
        normalized_neo4j_status = STATUS_DISABLED
        neo4j_reason = "配置未启用 Neo4j"
    elif neo4j_status == "active" and neo4j_driver_connected:
        normalized_neo4j_status = STATUS_ACTIVE
    elif neo4j_status == "skipped":
        normalized_neo4j_status = STATUS_DISABLED
        neo4j_reason = "Neo4j 初始化被跳过"
    else:
        normalized_neo4j_status = STATUS_DEGRADED
        neo4j_reason = str(neo4j_status) if neo4j_status.startswith("error") else "Neo4j 连接不可用"

    # 模式判定
    if normalized_pg_status == STATUS_SQLITE_FALLBACK:
        mode = MODE_SQLITE_FALLBACK
    elif normalized_neo4j_status == STATUS_ACTIVE:
        mode = MODE_DUAL_WRITE
    else:
        mode = MODE_PG_ONLY

    return StorageConsistencyState(
        mode=mode,
        pg_status=normalized_pg_status,
        neo4j_status=normalized_neo4j_status,
        neo4j_degradation_reason=neo4j_reason,
        schema_drift_detected=schema_drift_detected,
        initialized=True,
        db_type=db_type,
    )
