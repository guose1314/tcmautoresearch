# research/study_session_manager.py
"""
StudySessionManager — 研究会话状态管理器

从 ResearchPipeline 抽取的周期状态管理职责，包含：
  - 研究阶段枚举 (ResearchPhase)
  - 研究循环状态枚举 (ResearchCycleStatus)
  - 研究循环数据结构 (ResearchCycle)
  - 循环状态的增删改查方法
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.phase_tracker import PhaseTrackerMixin


class ResearchPhase(Enum):
    """研究阶段枚举"""
    OBSERVE = "observe"          # 观察阶段
    HYPOTHESIS = "hypothesis"    # 假设阶段
    EXPERIMENT = "experiment"    # 实验方案阶段
    EXPERIMENT_EXECUTION = "experiment_execution"  # 外部实验结果导入阶段
    ANALYZE = "analyze"          # 分析阶段
    PUBLISH = "publish"          # 发布阶段
    REFLECT = "reflect"          # 反思阶段


class ResearchCycleStatus(Enum):
    """研究循环状态枚举"""
    PENDING = "pending"      # 待处理
    ACTIVE = "active"        # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 已失败
    SUSPENDED = "suspended"  # 已暂停


@dataclass
class ResearchCycle:
    """研究循环数据结构"""
    # 基础信息
    cycle_id: str
    cycle_name: str
    description: str

    # 状态信息
    status: ResearchCycleStatus = ResearchCycleStatus.PENDING
    current_phase: ResearchPhase = ResearchPhase.OBSERVE
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration: float = 0.0

    # 研究目标和范围
    research_objective: str = ""
    research_scope: str = ""
    target_audience: str = ""

    # 研究参与者
    researchers: List[str] = field(default_factory=list)
    advisors: List[str] = field(default_factory=list)

    # 资源配置
    resources: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    timeline: Dict[str, str] = field(default_factory=dict)

    # 阶段执行信息
    phase_executions: Dict[ResearchPhase, Dict[str, Any]] = field(default_factory=dict)

    # 研究成果
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)

    # 质量控制
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)

    # 专家评审
    expert_reviews: List[Dict[str, Any]] = field(default_factory=list)

    # 标签和分类
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StudySessionManager(PhaseTrackerMixin):
    """
    研究会话状态管理器

    负责管理研究循环的存储、查询和状态变更，
    将循环生命周期数据从 ResearchPipeline 中解耦。
    """

    def __init__(self, governance_config: Dict[str, Any]):
        self._governance_config = governance_config
        self.research_cycles: Dict[str, ResearchCycle] = {}
        self.active_cycles: Dict[str, ResearchCycle] = {}
        self.failed_cycles: List[ResearchCycle] = []
        self.execution_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _record_failed_operation(
        self,
        failed_operations: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._governance_config.get("persist_failed_operations", True):
            return
        failed_operations.append(
            {
                "operation": operation,
                "error": error,
                "details": self._serialize_value(details or {}),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration, 6),
            }
        )

    # ------------------------------------------------------------------
    # 循环状态初始化与变更
    # ------------------------------------------------------------------

    def initialize_cycle_tracking(self, cycle: ResearchCycle) -> None:
        """初始化循环元数据中的追踪字段。"""
        cycle.metadata["phase_history"] = []
        cycle.metadata["phase_timings"] = {}
        cycle.metadata["completed_phases"] = []
        cycle.metadata["failed_phase"] = None
        cycle.metadata["final_status"] = cycle.status.value
        cycle.metadata["last_completed_phase"] = None
        cycle.metadata["failed_operations"] = []

    def mark_cycle_failed(
        self, cycle: ResearchCycle, phase_name: str, error: str
    ) -> None:
        """将循环标记为失败并更新内部存储。"""
        cycle.status = ResearchCycleStatus.FAILED
        cycle.metadata["failed_phase"] = phase_name
        cycle.metadata["error"] = error
        cycle.metadata["final_status"] = cycle.status.value
        cycle.completed_at = datetime.now().isoformat()
        if cycle.started_at:
            cycle.duration = (
                datetime.fromisoformat(cycle.completed_at)
                - datetime.fromisoformat(cycle.started_at)
            ).total_seconds()
        if cycle.cycle_id in self.active_cycles:
            del self.active_cycles[cycle.cycle_id]
        if all(existing.cycle_id != cycle.cycle_id for existing in self.failed_cycles):
            self.failed_cycles.append(cycle)
        self._record_failed_operation(
            cycle.metadata.setdefault("failed_operations", []),
            phase_name,
            error,
            cycle.duration,
            {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.cycle_name,
                "status": cycle.status.value,
                "failed_phase": phase_name,
            },
        )

    # ------------------------------------------------------------------
    # 循环分析摘要
    # ------------------------------------------------------------------

    def build_cycle_analysis_summary(self, cycle: ResearchCycle) -> Dict[str, Any]:
        """构建单个研究循环的分析摘要。"""
        completed_phases = cycle.metadata.get("completed_phases", [])
        total_outcomes = len(cycle.outcomes)
        total_deliverables = len(cycle.deliverables)
        summary_status = "pending"
        if cycle.status == ResearchCycleStatus.FAILED:
            summary_status = "needs_followup"
        elif cycle.status == ResearchCycleStatus.COMPLETED:
            summary_status = "stable"
        elif cycle.status == ResearchCycleStatus.SUSPENDED:
            summary_status = "paused"
        elif cycle.status == ResearchCycleStatus.ACTIVE:
            summary_status = "in_progress"

        return {
            "status": summary_status,
            "completed_phase_count": len(completed_phases),
            "completed_phases": completed_phases,
            "outcome_count": total_outcomes,
            "deliverable_count": total_deliverables,
            "last_phase": cycle.metadata.get(
                "last_completed_phase", cycle.current_phase.value
            ),
            "failed_phase": cycle.metadata.get("failed_phase", ""),
            "failed_operation_count": len(cycle.metadata.get("failed_operations", [])),
            "final_status": cycle.metadata.get("final_status", cycle.status.value),
        }

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------

    def serialize_phase_executions(self, cycle: ResearchCycle) -> Dict[str, Any]:
        """将阶段执行记录序列化为 JSON 安全结构。"""
        return {
            phase.value: self._serialize_value(execution)
            for phase, execution in cycle.phase_executions.items()
        }

    def serialize_cycle(self, cycle: ResearchCycle) -> Dict[str, Any]:
        """将 ResearchCycle 完整序列化为字典。"""
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "description": cycle.description,
            "status": cycle.status.value,
            "current_phase": cycle.current_phase.value,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "duration": cycle.duration,
            "research_objective": cycle.research_objective,
            "research_scope": cycle.research_scope,
            "target_audience": cycle.target_audience,
            "researchers": cycle.researchers,
            "advisors": cycle.advisors,
            "resources": self._serialize_value(cycle.resources),
            "budget": cycle.budget,
            "timeline": self._serialize_value(cycle.timeline),
            "phase_executions": self.serialize_phase_executions(cycle),
            "outcomes": self._serialize_value(cycle.outcomes),
            "deliverables": self._serialize_value(cycle.deliverables),
            "quality_metrics": self._serialize_value(cycle.quality_metrics),
            "risk_assessment": self._serialize_value(cycle.risk_assessment),
            "expert_reviews": self._serialize_value(cycle.expert_reviews),
            "tags": self._serialize_value(cycle.tags),
            "categories": self._serialize_value(cycle.categories),
            "metadata": self._serialize_value(cycle.metadata),
        }

    # ------------------------------------------------------------------
    # 循环查询 API
    # ------------------------------------------------------------------

    def get_cycle_status(self, cycle_id: str) -> Dict[str, Any]:
        """获取单个研究循环的状态快照。"""
        if cycle_id not in self.research_cycles:
            return {"error": "循环不存在"}
        cycle = self.research_cycles[cycle_id]
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "status": cycle.status.value,
            "current_phase": cycle.current_phase.value,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "duration": cycle.duration,
            "research_objective": cycle.research_objective,
            "research_scope": cycle.research_scope,
            "phase_executions": self.serialize_phase_executions(cycle),
            "metadata": self._serialize_value(cycle.metadata),
        }

    def get_all_cycles(self) -> List[Dict[str, Any]]:
        """获取所有研究循环的摘要列表。"""
        return [
            {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.cycle_name,
                "status": cycle.status.value,
                "current_phase": cycle.current_phase.value,
                "started_at": cycle.started_at,
                "research_objective": cycle.research_objective,
                "analysis_summary": self._serialize_value(
                    cycle.metadata.get("analysis_summary", {})
                ),
            }
            for cycle in self.research_cycles.values()
        ]

    def get_cycle_history(self, cycle_id: str) -> List[Dict[str, Any]]:
        """从执行历史中筛选指定循环的条目。"""
        return [
            entry
            for entry in self.execution_history
            if entry.get("cycle_id") == cycle_id
        ]
