"""PipelineContext — 编排层共享上下文容器。

将 ResearchPipeline 内部的共享可变状态收敛为一个显式数据类，
替代原有各编排器 / 阶段处理器对 ``pipeline`` 整体引用的隐式依赖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PipelineContext:
    """编排层共享上下文。

    由 ``ResearchPipeline.__init__`` 创建，传递给
    ``PhaseOrchestrator``、``ResearchPipelineOrchestrator``
    和 ``ResearchPhaseHandlers``，取代原来的 ``self.pipeline`` 反向引用。

    Attributes 全部为引用语义——修改会反映到所有持有者。
    """

    # ── 配置与基础设施 ──────────────────────────────────────────
    config: Dict[str, Any]
    event_bus: Any  # EventBus
    module_factory: Any  # ModuleFactory
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    # ── 治理 ────────────────────────────────────────────────────
    governance_config: Dict[str, Any] = field(default_factory=dict)

    # ── 可变运行时状态 ──────────────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)
    failed_operations: List[Dict[str, Any]] = field(default_factory=list)

    # ── 研究循环数据 ────────────────────────────────────────────
    research_cycles: Dict[str, Any] = field(default_factory=dict)
    active_cycles: Dict[str, Any] = field(default_factory=dict)
    failed_cycles: List[Any] = field(default_factory=list)

    # ── 领域服务 ────────────────────────────────────────────────
    session_manager: Any = None  # StudySessionManager
    quality_assessor: Any = None  # QualityAssessor
    hypothesis_engine: Any = None  # HypothesisEngine
    audit_history: Any = None  # AuditHistory
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
