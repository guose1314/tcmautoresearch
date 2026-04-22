"""Phase L-1 — `PhaseOrchestrator` 拆分外观层。

将既有 :class:`src.research.phase_orchestrator.PhaseOrchestrator` 巨石类按
**职责** 拆出三个窄接口外观（facade），用于业务侧逐步去耦：

- :class:`PhaseRunner` —— 仅承担相位执行调度（dispatch + handler 查找）
- :class:`PhasePersistence` —— 仅承担 cycle / phase / artifact 的持久化
- :class:`PhaseGraphExporter` —— 仅承担向 Neo4j 投影与流水线数据导出

设计约束：
- 不修改 ``PhaseOrchestrator`` 任何 API；外观仅 **委托** 现有方法。
- 只暴露已经存在且稳定的入口，保留私有方法不被外部访问。
- 允许调用方按需注入 mock 外观，便于针对单一职责写单元测试。

契约版本：``phase-orchestrator-facade-v1``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - 仅类型注解使用
    from src.research.phase_orchestrator import PhaseOrchestrator

CONTRACT_VERSION = "phase-orchestrator-facade-v1"
PHASE_FACADE_CONTRACT_VERSION = CONTRACT_VERSION

__all__ = [
    "CONTRACT_VERSION",
    "PHASE_FACADE_CONTRACT_VERSION",
    "PhaseRunner",
    "PhasePersistence",
    "PhaseGraphExporter",
    "PhaseOrchestratorFacades",
    "build_phase_orchestrator_facades",
]


@dataclass(frozen=True)
class PhaseRunner:
    """仅承担相位调度的窄外观。

    暴露：
      - :meth:`get_handler` —— 取阶段处理器
      - :meth:`execute` —— 触发相位执行
    """

    orchestrator: "PhaseOrchestrator"

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    def get_handler(self, phase_name: str) -> Any:
        return self.orchestrator.get_handler(phase_name)

    def execute(
        self,
        phase: Any,
        cycle: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """触发相位执行（委托至 ``PhaseOrchestrator._execute_phase_internal``）。

        与既有 ``PhaseOrchestrator`` 行为完全等价，但调用方不再需要持有完整
        编排器实例的 ``pipeline``、``event_bus`` 等内部状态。
        """
        ctx: Dict[str, Any] = dict(context or {})
        return self.orchestrator._execute_phase_internal(phase, cycle, ctx)


@dataclass(frozen=True)
class PhasePersistence:
    """仅承担 cycle 持久化的窄外观（PG / repository 写入）。"""

    orchestrator: "PhaseOrchestrator"

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    def persist_phase_executions(
        self,
        repository: Any,
        cycle: Any,
        session: Any = None,
    ) -> Dict[str, Dict[str, Any]]:
        return self.orchestrator._persist_cycle_phase_executions(repository, cycle, session=session)

    def persist_artifacts(
        self,
        repository: Any,
        cycle: Any,
        phase_records: Dict[str, Dict[str, Any]],
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        return self.orchestrator._persist_cycle_artifacts(repository, cycle, phase_records, session=session)

    def persist_learning_feedback(
        self,
        repository: Any,
        cycle: Any,
        phase_records: Dict[str, Dict[str, Any]],
        session: Any = None,
    ) -> Dict[str, Any]:
        return self.orchestrator._persist_cycle_learning_feedback(
            repository, cycle, phase_records, session=session
        )

    def persist_observe_documents(
        self,
        repository: Any,
        cycle: Any,
        phase_records: Dict[str, Dict[str, Any]],
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        return self.orchestrator._persist_cycle_observe_documents(
            repository, cycle, phase_records, session=session
        )


@dataclass(frozen=True)
class PhaseGraphExporter:
    """仅承担图谱投影 / 流水线导出的窄外观（Neo4j 写入 + JSON 导出）。"""

    orchestrator: "PhaseOrchestrator"

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    def project_cycle_to_neo4j(
        self,
        neo4j_driver: Any,
        cycle: Any,
        session_record: Dict[str, Any],
        phase_records: Dict[str, Dict[str, Any]],
        artifact_records: List[Dict[str, Any]],
        observe_documents: List[Dict[str, Any]],
        transaction: Any = None,
    ) -> Dict[str, Any]:
        return self.orchestrator._project_cycle_to_neo4j(
            neo4j_driver,
            cycle,
            session_record,
            phase_records,
            artifact_records,
            observe_documents,
            transaction=transaction,
        )

    def export_pipeline_data(self, output_path: str) -> bool:
        return self.orchestrator.export_pipeline_data(output_path)

    def get_pipeline_summary(self) -> Dict[str, Any]:
        return self.orchestrator.get_pipeline_summary()


@dataclass(frozen=True)
class PhaseOrchestratorFacades:
    """三个窄外观的复合容器，便于一次性注入到上层服务。"""

    runner: PhaseRunner
    persistence: PhasePersistence
    exporter: PhaseGraphExporter

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


def build_phase_orchestrator_facades(orchestrator: "PhaseOrchestrator") -> PhaseOrchestratorFacades:
    """以单个 ``PhaseOrchestrator`` 实例构造三个窄外观。"""
    return PhaseOrchestratorFacades(
        runner=PhaseRunner(orchestrator=orchestrator),
        persistence=PhasePersistence(orchestrator=orchestrator),
        exporter=PhaseGraphExporter(orchestrator=orchestrator),
    )
