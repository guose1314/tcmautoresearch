# core/phase_tracker.py
"""
PhaseTrackerMixin — 阶段追踪工具混入类

统一提供以下三组能力，消除跨模块重复代码：
  1. _serialize_value           — 通用 JSON 安全序列化（所有文件共享）
  2. _build_runtime_metadata_from_dict — 元数据快照辅助（所有文件调用）
  3. Pattern-A 阶段方法          — 针对使用 self.phase_history 等扁平属性的模块

Pattern-A 使用约定（继承类须在 __init__ 初始化以下属性）：
  - self.governance_config: Dict[str, Any]
      需含 "enable_phase_tracking" (bool) 和 "persist_failed_operations" (bool)
  - self.phase_history: List[Dict[str, Any]]
  - self.phase_timings: Dict[str, float]
  - self.completed_phases: List[str]
  - self.failed_phase: Optional[str]
  - self.final_status: Any
  - self.last_completed_phase: Optional[str]
  - self.failed_operations: List[Dict[str, Any]]
"""

import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PhaseTrackerMixin:
    """共享阶段追踪工具混入类。"""

    # ──────────────────────────────────────────────────────────────────
    # 通用序列化（所有 13 个模块共享）
    # ──────────────────────────────────────────────────────────────────

    def _serialize_value(self, value: Any) -> Any:
        """将嵌套对象递归转换为 JSON 安全结构。"""
        primitive = self._serialize_primitive(value)
        if primitive is not None:
            return primitive

        mapping_like = self._serialize_mapping_like(value)
        if mapping_like is not None:
            return mapping_like

        sequence_like = self._serialize_sequence_like(value)
        if sequence_like is not None:
            return sequence_like

        dataclass_like = self._serialize_dataclass_like(value)
        if dataclass_like is not None:
            return dataclass_like

        if callable(value):
            return getattr(value, "__name__", "callable")
        return value

    def _serialize_primitive(self, value: Any) -> Any:
        """序列化基础类型，无法处理时返回 None。"""
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        return None

    def _serialize_mapping_like(self, value: Any) -> Optional[Dict[str, Any]]:
        """序列化映射类型（dict/defaultdict）。"""
        if isinstance(value, (defaultdict, dict)):
            return {str(k): self._serialize_value(v) for k, v in value.items()}
        return None

    def _serialize_sequence_like(self, value: Any) -> Optional[List[Any]]:
        """序列化列表与元组。"""
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(i) for i in value]
        return None

    def _serialize_dataclass_like(self, value: Any) -> Optional[Dict[str, Any]]:
        """序列化 dataclass 实例。"""
        if hasattr(value, "__dataclass_fields__"):
            return {
                fn: self._serialize_value(getattr(value, fn))
                for fn in value.__dataclass_fields__
            }
        return None

    # ──────────────────────────────────────────────────────────────────
    # 运行时元数据快照辅助（所有模块调用）
    # ──────────────────────────────────────────────────────────────────

    def _build_runtime_metadata_from_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """从阶段追踪字典构建标准运行时元数据快照。"""
        return {
            "phase_history": self._serialize_value(d.get("phase_history", [])),
            "phase_timings": self._serialize_value(d.get("phase_timings", {})),
            "completed_phases": list(d.get("completed_phases", [])),
            "failed_phase": d.get("failed_phase"),
            "final_status": d.get("final_status", "initialized"),
            "last_completed_phase": d.get("last_completed_phase"),
        }

    # ──────────────────────────────────────────────────────────────────
    # Pattern-A 阶段方法
    # 依赖：self.governance_config / self.phase_history / self.phase_timings /
    #       self.completed_phases / self.failed_phase / self.final_status /
    #       self.last_completed_phase / self.failed_operations
    # ──────────────────────────────────────────────────────────────────

    def _start_phase(
        self, phase_name: str, details: Optional[Dict[str, Any]] = None
    ) -> float:
        started_at = time.time()
        if self.governance_config.get("enable_phase_tracking", True):  # type: ignore[attr-defined]
            self.phase_history.append(  # type: ignore[attr-defined]
                {
                    "phase": phase_name,
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "details": self._serialize_value(details or {}),
                }
            )
        return started_at

    def _complete_phase(
        self,
        phase_name: str,
        phase_started_at: float,
        details: Optional[Dict[str, Any]] = None,
        final_status: Optional[str] = None,
    ) -> None:
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)  # type: ignore[attr-defined]
        if phase_name not in self.completed_phases:  # type: ignore[attr-defined]
            self.completed_phases.append(phase_name)  # type: ignore[attr-defined]
        self.last_completed_phase = phase_name  # type: ignore[attr-defined]
        self.failed_phase = None  # type: ignore[attr-defined]
        self.final_status = final_status or self.final_status  # type: ignore[attr-defined]

        if not self.governance_config.get("enable_phase_tracking", True):  # type: ignore[attr-defined]
            return

        for phase in reversed(self.phase_history):  # type: ignore[attr-defined]
            if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
                phase["status"] = "completed"
                phase["ended_at"] = datetime.now().isoformat()
                phase["duration_seconds"] = round(duration, 6)
                if details:
                    phase["details"] = self._serialize_value(
                        {**phase.get("details", {}), **details}
                    )
                break

    def _fail_phase(
        self,
        phase_name: str,
        phase_started_at: float,
        error: Exception,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)  # type: ignore[attr-defined]
        self.failed_phase = phase_name  # type: ignore[attr-defined]
        self.final_status = "failed"  # type: ignore[attr-defined]
        self._record_failed_operation(phase_name, error, details, duration)

        if not self.governance_config.get("enable_phase_tracking", True):  # type: ignore[attr-defined]
            return

        for phase in reversed(self.phase_history):  # type: ignore[attr-defined]
            if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
                phase["status"] = "failed"
                phase["ended_at"] = datetime.now().isoformat()
                phase["duration_seconds"] = round(duration, 6)
                phase["error"] = str(error)
                if details:
                    phase["details"] = self._serialize_value(
                        {**phase.get("details", {}), **details}
                    )
                break

    def _record_failed_operation(
        self,
        operation_name: str,
        error: Exception,
        details: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        if not self.governance_config.get("persist_failed_operations", True):  # type: ignore[attr-defined]
            return
        self.failed_operations.append(  # type: ignore[attr-defined]
            {
                "operation": operation_name,
                "error": str(error),
                "details": self._serialize_value(details or {}),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration_seconds or 0.0, 6),
            }
        )

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(
            {
                "phase_history": self.phase_history,  # type: ignore[attr-defined]
                "phase_timings": self.phase_timings,  # type: ignore[attr-defined]
                "completed_phases": self.completed_phases,  # type: ignore[attr-defined]
                "failed_phase": self.failed_phase,  # type: ignore[attr-defined]
                "final_status": self.final_status,  # type: ignore[attr-defined]
                "last_completed_phase": self.last_completed_phase,  # type: ignore[attr-defined]
            }
        )
