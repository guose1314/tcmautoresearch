# research/research_pipeline.py
"""
中医古籍全自动研究系统 - 专业学术研究流程管理模块
基于AI的科研闭环流程管理系统
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.semantic_graph import SemanticGraphBuilder
from src.collector.corpus_bundle import (
    CorpusBundle,
)
from src.collector.ctext_corpus_collector import CTextCorpusCollector
from src.collector.literature_retriever import LiteratureRetriever
from src.collector.local_collector import LocalCorpusCollector
from src.core.event_bus import EventBus
from src.core.module_base import get_global_executor
from src.core.module_factory import ModuleFactory
from src.core.phase_tracker import PhaseTrackerMixin
from src.hypothesis import HypothesisEngine
from src.research.gap_analyzer import GapAnalyzer
from src.research.pipeline_orchestrator import ResearchPipelineOrchestrator
from src.research.pipeline_phase_handlers import ResearchPhaseHandlers

# 配置日志
logger = logging.getLogger(__name__)

# 供单测 patch 的符号；导入失败时在运行时再惰性加载。
try:
    from src.llm.llm_engine import LLMEngine as _ImportedLLMEngine
except Exception:
    _ImportedLLMEngine = None

LLMEngine = _ImportedLLMEngine

try:
    from src.llm.llm_service import CachedLLMService as _ImportedCachedLLMService
except Exception:
    _ImportedCachedLLMService = None

CachedLLMService = _ImportedCachedLLMService

try:
    from src.generation.citation_manager import (
        CitationManager as _ImportedCitationManager,
    )
except Exception:
    _ImportedCitationManager = None

CitationManager = _ImportedCitationManager

try:
    from src.generation.paper_writer import PaperWriter as _ImportedPaperWriter
except Exception:
    _ImportedPaperWriter = None

PaperWriter = _ImportedPaperWriter

try:
    from src.generation.output_formatter import (
        OutputGenerator as _ImportedOutputGenerator,
    )
except Exception:
    _ImportedOutputGenerator = None

OutputGenerator = _ImportedOutputGenerator

class ResearchPhase(Enum):
    """
    研究阶段枚举
    """
    OBSERVE = "observe"          # 观察阶段
    HYPOTHESIS = "hypothesis"    # 假设阶段
    EXPERIMENT = "experiment"    # 实验阶段
    ANALYZE = "analyze"          # 分析阶段
    PUBLISH = "publish"          # 发布阶段
    REFLECT = "reflect"          # 反思阶段

class ResearchCycleStatus(Enum):
    """
    研究循环状态枚举
    """
    PENDING = "pending"      # 待处理
    ACTIVE = "active"        # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 已失败
    SUSPENDED = "suspended"  # 已暂停

@dataclass
class ResearchCycle:
    """
    研究循环数据结构
    """
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

class ResearchPipeline(PhaseTrackerMixin):
    """
    中医古籍全自动研究系统科研流程管理
    
    本模块实现了完整的科研闭环流程管理，包括：
    1. 研究循环设计与启动
    2. 多阶段任务执行与协调
    3. 质量控制与风险管理
    4. 成果产出与知识沉淀
    5. 反思改进与持续优化
    """

    ResearchPhase = ResearchPhase
    ResearchCycleStatus = ResearchCycleStatus
    ResearchCycle = ResearchCycle
    CitationManager = CitationManager
    LocalCorpusCollector = LocalCorpusCollector
    CTextCorpusCollector = CTextCorpusCollector
    LiteratureRetriever = LiteratureRetriever
    DocumentPreprocessor = DocumentPreprocessor
    AdvancedEntityExtractor = AdvancedEntityExtractor
    SemanticGraphBuilder = SemanticGraphBuilder
    PaperWriter = PaperWriter
    OutputGenerator = OutputGenerator

    _MODULE_KEYS = {
        "literature_retriever": "LiteratureRetriever",
        "local_corpus_collector": "LocalCorpusCollector",
        "ctext_corpus_collector": "CTextCorpusCollector",
        "document_preprocessor": "DocumentPreprocessor",
        "entity_extractor": "AdvancedEntityExtractor",
        "semantic_graph_builder": "SemanticGraphBuilder",
        "citation_manager": "CitationManager",
        "paper_writer": "PaperWriter",
        "output_generator": "OutputGenerator",
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化研究流程管理器
        
        Args:
            config (Dict[str, Any]): 配置参数
        """
        self.config = config or {}
        self.event_bus = EventBus()
        self.module_factory = ModuleFactory.from_config(self.config.get("module_factory") or {})
        self._register_default_module_providers()
        self._register_default_event_handlers()
        self.research_cycles = {}
        self.active_cycles = {}
        self.failed_cycles: List[ResearchCycle] = []
        self.execution_history = []
        # 使用全局共享线程池，与 BaseModule 保持一致
        self.executor = get_global_executor(max_workers=4)
        self.logger = logging.getLogger(__name__)
        self._failed_operations: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self._governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get(
                "persist_failed_operations",
                self.config.get("persist_failed_cycles", True),
            ),
            "minimum_stable_completion_rate": float(
                self.config.get("minimum_stable_completion_rate", 0.8)
            ),
            "export_contract_version": self.config.get("export_contract_version", "d44.v1"),
        }
        self.hypothesis_engine = HypothesisEngine(self.config.get("hypothesis_engine_config") or {})
        self.hypothesis_engine.initialize()
        self.phase_handlers = ResearchPhaseHandlers(self)
        self.orchestrator = ResearchPipelineOrchestrator(self, self.phase_handlers)
        
        # 初始化质量控制指标
        self.quality_metrics = {
            "cycle_completion_rate": 0.0,
            "phase_efficiency": 0.0,
            "researcher_productivity": 0.0,
            "quality_assurance": 0.0
        }
        
        # 初始化资源监控
        self.resource_usage = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "storage_usage": 0.0,
            "network_usage": 0.0
        }
        
        self.logger.info("研究流程管理器初始化完成")

    def _register_default_module_providers(self) -> None:
        for key, symbol_name in self._MODULE_KEYS.items():
            if self.module_factory.has(key):
                continue

            def _provider(cfg: Dict[str, Any], _symbol=symbol_name):
                cls = globals().get(_symbol)
                if cls is None:
                    raise RuntimeError(f"模块工厂默认依赖不可用: {_symbol}")
                return cls(cfg)

            self.module_factory.register(key, _provider)

    def create_module(self, key: str, config: Optional[Dict[str, Any]] = None) -> Any:
        """通过模块工厂创建依赖实例。"""
        return self.module_factory.create(key, config or {})

    def _register_default_event_handlers(self) -> None:
        self.event_bus.subscribe("phase.execute.requested", self._on_phase_execute_requested)
        self.event_bus.subscribe("cycle.create.requested", self._on_cycle_create_requested)
        self.event_bus.subscribe("cycle.start.requested", self._on_cycle_start_requested)
        self.event_bus.subscribe("cycle.phase.execute.requested", self._on_cycle_phase_execute_requested)
        self.event_bus.subscribe("cycle.complete.requested", self._on_cycle_complete_requested)
        self.event_bus.subscribe("cycle.suspend.requested", self._on_cycle_suspend_requested)
        self.event_bus.subscribe("cycle.resume.requested", self._on_cycle_resume_requested)

    def _on_phase_execute_requested(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        phase = payload.get("phase")
        cycle = payload.get("cycle")
        context = payload.get("context") or {}
        if phase is None or cycle is None:
            return None
        return self.phase_handlers.execute_phase_internal(phase, cycle, context)

    def _on_cycle_create_requested(self, payload: Dict[str, Any]) -> Optional[Any]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_name = payload.get("cycle_name")
        description = payload.get("description")
        objective = payload.get("objective")
        scope = payload.get("scope")
        researchers = payload.get("researchers")
        cycle_options = payload.get("cycle_options") or {}
        if not all(isinstance(value, str) and value for value in [cycle_name, description, objective, scope]):
            return None
        return self.orchestrator._create_research_cycle_local(
            cycle_name=cycle_name,
            description=description,
            objective=objective,
            scope=scope,
            researchers=researchers,
            **cycle_options,
        )

    def _on_cycle_start_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.orchestrator._start_research_cycle_local(cycle_id)

    def _on_cycle_phase_execute_requested(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        phase = payload.get("phase")
        if not isinstance(cycle_id, str) or not cycle_id or phase is None:
            return None
        return self.orchestrator._execute_research_phase_local(
            cycle_id,
            phase,
            payload.get("phase_context"),
        )

    def _on_cycle_complete_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.orchestrator._complete_research_cycle_local(cycle_id)

    def _on_cycle_suspend_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.orchestrator._suspend_research_cycle_local(cycle_id)

    def _on_cycle_resume_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.orchestrator._resume_research_cycle_local(cycle_id)

    def _initialize_cycle_tracking(self, cycle: ResearchCycle) -> None:
        cycle.metadata["phase_history"] = []
        cycle.metadata["phase_timings"] = {}
        cycle.metadata["completed_phases"] = []
        cycle.metadata["failed_phase"] = None
        cycle.metadata["final_status"] = cycle.status.value
        cycle.metadata["last_completed_phase"] = None
        cycle.metadata["failed_operations"] = []

    def _start_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self._governance_config.get("enable_phase_tracking", True):
            metadata.setdefault("phase_history", []).append(phase_entry)
        self.event_bus.publish(
            "phase.lifecycle.started",
            {
                "phase": phase_name,
                "started_at": phase_entry["started_at"],
                "context": phase_entry["context"],
            },
        )
        return phase_entry

    def _complete_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        if phase_name not in metadata.setdefault("completed_phases", []):
            metadata["completed_phases"].append(phase_name)
        metadata["last_completed_phase"] = phase_name
        metadata["final_status"] = "completed"
        self.event_bus.publish(
            "phase.lifecycle.completed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
            },
        )

    def _fail_phase(
        self,
        metadata: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
        error: str,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        metadata["failed_phase"] = phase_name
        metadata["final_status"] = "failed"
        self.event_bus.publish(
            "phase.lifecycle.failed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
                "error": error,
            },
        )
        self._record_failed_operation(
            failed_operations,
            phase_name,
            error,
            duration,
            phase_entry.get("context", {}),
        )

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

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(self._metadata)

    def _mark_cycle_failed(self, cycle: ResearchCycle, phase_name: str, error: str) -> None:
        cycle.status = ResearchCycleStatus.FAILED
        cycle.metadata["failed_phase"] = phase_name
        cycle.metadata["error"] = error
        cycle.metadata["final_status"] = cycle.status.value
        cycle.completed_at = datetime.now().isoformat()
        if cycle.started_at:
            cycle.duration = (
                datetime.fromisoformat(cycle.completed_at) - datetime.fromisoformat(cycle.started_at)
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

    def _build_cycle_analysis_summary(self, cycle: ResearchCycle) -> Dict[str, Any]:
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
            "last_phase": cycle.metadata.get("last_completed_phase", cycle.current_phase.value),
            "failed_phase": cycle.metadata.get("failed_phase", ""),
            "failed_operation_count": len(cycle.metadata.get("failed_operations", [])),
            "final_status": cycle.metadata.get("final_status", cycle.status.value),
        }

    def _build_pipeline_analysis_summary(self) -> Dict[str, Any]:
        total_cycles = len(self.research_cycles)
        completed_cycles = sum(
            1 for cycle in self.research_cycles.values() if cycle.status == ResearchCycleStatus.COMPLETED
        )
        failed_cycles = sum(
            1 for cycle in self.research_cycles.values() if cycle.status == ResearchCycleStatus.FAILED
        )
        completion_rate = (completed_cycles / total_cycles) if total_cycles else 0.0
        status = "idle"
        if self._failed_operations:
            status = "needs_followup"
        elif total_cycles > 0:
            status = (
                "stable"
                if completion_rate >= self._governance_config["minimum_stable_completion_rate"] and failed_cycles == 0
                else "degraded"
            )

        return {
            "total_cycles": total_cycles,
            "completed_cycles": completed_cycles,
            "failed_cycles": failed_cycles,
            "completion_rate": round(completion_rate, 4),
            "failed_operation_count": len(self._failed_operations),
            "status": status,
            "last_completed_phase": self._metadata.get("last_completed_phase"),
            "failed_phase": self._metadata.get("failed_phase"),
            "final_status": self._metadata.get("final_status", "initialized"),
        }

    def _serialize_phase_executions(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return {phase.value: self._serialize_value(execution) for phase, execution in cycle.phase_executions.items()}

    def _serialize_cycle(self, cycle: ResearchCycle) -> Dict[str, Any]:
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
            "phase_executions": self._serialize_phase_executions(cycle),
            "outcomes": self._serialize_value(cycle.outcomes),
            "deliverables": self._serialize_value(cycle.deliverables),
            "quality_metrics": self._serialize_value(cycle.quality_metrics),
            "risk_assessment": self._serialize_value(cycle.risk_assessment),
            "expert_reviews": self._serialize_value(cycle.expert_reviews),
            "tags": self._serialize_value(cycle.tags),
            "categories": self._serialize_value(cycle.categories),
            "metadata": self._serialize_value(cycle.metadata),
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        runtime_metadata = self._build_runtime_metadata()
        return {
            "contract_version": self._governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "research_pipeline_report",
            "active_cycle_count": len(self.active_cycles),
            "completed_phases": list(runtime_metadata.get("completed_phases", [])),
            "failed_phase": runtime_metadata.get("failed_phase"),
            "failed_operation_count": len(self._failed_operations),
            "final_status": runtime_metadata.get("final_status", "initialized"),
            "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        }
    
    def create_research_cycle(
        self,
        cycle_name: str,
        description: str,
        objective: str,
        scope: str,
        researchers: Optional[List[str]] = None,
        **cycle_options: Any,
    ) -> ResearchCycle:
        """创建研究循环（委托编排器执行）。"""
        return self.orchestrator.create_research_cycle(
            cycle_name=cycle_name,
            description=description,
            objective=objective,
            scope=scope,
            researchers=researchers,
            **cycle_options,
        )
    
    def start_research_cycle(self, cycle_id: str) -> bool:
        """启动研究循环（委托编排器执行）。"""
        return self.orchestrator.start_research_cycle(cycle_id)
    
    def execute_research_phase(
        self,
        cycle_id: str,
        phase: ResearchPhase,
        phase_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行研究阶段（委托编排器 + 阶段处理器执行）。"""
        return self.orchestrator.execute_research_phase(cycle_id, phase, phase_context)

    def _validate_research_phase_request(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        if cycle_id not in self.research_cycles:
            self.logger.warning(f"研究循环 {cycle_id} 不存在")
            return {"error": "循环不存在"}

        research_cycle = self.research_cycles[cycle_id]
        if research_cycle.status != ResearchCycleStatus.ACTIVE:
            self.logger.warning(f"研究循环 {cycle_id} 不处于活跃状态")
            return {"error": "循环未激活"}
        return None

    def _advance_research_cycle_phase(self, research_cycle: ResearchCycle, phase: ResearchPhase) -> None:
        phase_transitions = {
            ResearchPhase.OBSERVE: ResearchPhase.HYPOTHESIS,
            ResearchPhase.HYPOTHESIS: ResearchPhase.EXPERIMENT,
            ResearchPhase.EXPERIMENT: ResearchPhase.ANALYZE,
            ResearchPhase.ANALYZE: ResearchPhase.PUBLISH,
            ResearchPhase.PUBLISH: ResearchPhase.REFLECT,
            ResearchPhase.REFLECT: ResearchPhase.OBSERVE,
        }
        research_cycle.current_phase = phase_transitions.get(phase, research_cycle.current_phase)

    def _build_phase_execution(
        self,
        phase: ResearchPhase,
        started_at: str,
        start_time: float,
        phase_context: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "phase": phase.value,
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "duration": time.perf_counter() - start_time,
            "context": phase_context,
            "result": phase_result,
        }

    def _sync_phase_history_entry(
        self,
        phase_entry: Dict[str, Any],
        phase_execution: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> None:
        phase_entry["completed_at"] = phase_execution["completed_at"]
        phase_entry["duration"] = phase_execution["duration"]
        phase_entry["result"] = self._serialize_value(phase_result)

    def _apply_phase_result(
        self,
        research_cycle: ResearchCycle,
        phase: ResearchPhase,
        phase_result: Dict[str, Any],
    ) -> None:
        research_cycle.metadata["final_status"] = research_cycle.status.value
        if not isinstance(phase_result, dict):
            return

        research_cycle.outcomes.append({"phase": phase.value, "result": phase_result})
        if phase == ResearchPhase.PUBLISH:
            research_cycle.deliverables = phase_result.get("deliverables", [])
        if phase == ResearchPhase.ANALYZE:
            research_cycle.quality_metrics = phase_result.get("results", {})

    def _record_phase_success(self, cycle_id: str, phase: ResearchPhase, start_time: float) -> None:
        self.execution_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "action": "phase_executed",
                "cycle_id": cycle_id,
                "phase": phase.value,
                "duration": time.perf_counter() - start_time,
            }
        )

    def _handle_phase_execution_failure(
        self,
        cycle_id: str,
        phase: ResearchPhase,
        start_time: float,
        exc: Exception,
    ) -> Dict[str, Any]:
        self.logger.error(f"研究阶段执行失败: {exc}")
        if cycle_id not in self.research_cycles:
            return {"error": str(exc)}

        research_cycle = self.research_cycles[cycle_id]
        self._record_failed_phase_history(research_cycle, phase, start_time, str(exc))
        self._mark_cycle_failed(research_cycle, phase.value, str(exc))
        research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
        self.execution_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "action": "phase_failed",
                "cycle_id": cycle_id,
                "phase": phase.value,
                "error": str(exc),
            }
        )
        return {"error": str(exc)}

    def _record_failed_phase_history(
        self,
        research_cycle: ResearchCycle,
        phase: ResearchPhase,
        start_time: float,
        error: str,
    ) -> None:
        history = research_cycle.metadata.get("phase_history", [])
        if not history or history[-1].get("phase") != phase.value:
            return

        failure_details = {
            "cycle_id": research_cycle.cycle_id,
            "cycle_name": research_cycle.cycle_name,
            "status": research_cycle.status.value,
            "phase": phase.value,
        }
        history[-1]["context"] = self._serialize_value(
            {
                **(history[-1].get("context") or {}),
                **failure_details,
            }
        )
        self._fail_phase(
            research_cycle.metadata,
            research_cycle.metadata.setdefault("failed_operations", []),
            phase.value,
            history[-1],
            start_time,
            error,
        )
        history[-1]["completed_at"] = datetime.now().isoformat()
        history[-1]["duration"] = time.perf_counter() - start_time
        self._record_failed_operation(
            self._failed_operations,
            phase.value,
            error,
            time.perf_counter() - start_time,
            failure_details,
        )
    
    def _execute_phase_internal(self, phase: ResearchPhase, 
                              cycle: ResearchCycle,
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """内部执行阶段逻辑（通过事件路径调度，兼容回退）。"""
        payload = {
            "phase": phase,
            "cycle": cycle,
            "context": context,
        }
        result = self.event_bus.request("phase.execute.requested", payload)
        if isinstance(result, dict):
            return result
        return self.phase_handlers.execute_phase_internal(phase, cycle, context)
    
    def _execute_observe_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """执行观察阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_observe_phase(cycle, context)

    def _build_observe_seed_lists(self) -> Tuple[List[str], List[str]]:
        return self.phase_handlers._build_observe_seed_lists()

    def _collect_observe_corpus_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.phase_handlers._collect_observe_corpus_if_enabled(context)

    def _register_observe_collection_result(
        self,
        source_result: Optional[Dict[str, Any]],
        source_type: str,
        bundles: List[CorpusBundle],
        fallback_error: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return self.phase_handlers._register_observe_collection_result(
            source_result,
            source_type,
            bundles,
            fallback_error,
        )

    def _to_observe_corpus_bundle(
        self,
        source_result: Dict[str, Any],
        source_type: str,
    ) -> Optional[CorpusBundle]:
        return self.phase_handlers._to_observe_corpus_bundle(source_result, source_type)

    def _run_observe_literature_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.phase_handlers._run_observe_literature_if_enabled(context)

    def _run_observe_ingestion_if_enabled(
        self,
        corpus_result: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self.phase_handlers._run_observe_ingestion_if_enabled(corpus_result, context)

    def _append_corpus_observe_updates(
        self,
        corpus_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self.phase_handlers._append_corpus_observe_updates(corpus_result, observations, findings)

    def _append_ingestion_observe_updates(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self.phase_handlers._append_ingestion_observe_updates(ingestion_result, observations, findings)

    def _append_literature_observe_updates(
        self,
        literature_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self.phase_handlers._append_literature_observe_updates(literature_result, observations, findings)

    def _build_observe_metadata(
        self,
        context: Dict[str, Any],
        observations: List[str],
        findings: List[str],
        corpus_result: Optional[Dict[str, Any]],
        ingestion_result: Optional[Dict[str, Any]],
        literature_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self.phase_handlers._build_observe_metadata(
            context,
            observations,
            findings,
            corpus_result,
            ingestion_result,
            literature_result,
        )

    def _is_ctext_corpus_collected(self, corpus_result: Optional[Dict[str, Any]]) -> bool:
        return self.phase_handlers._is_ctext_corpus_collected(corpus_result)

    def _build_observe_ingestion_flags(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        ingestion_ok: bool,
    ) -> Tuple[bool, bool]:
        return self.phase_handlers._build_observe_ingestion_flags(ingestion_result, ingestion_ok)

    def _has_observe_evidence_matrix(
        self,
        literature_result: Optional[Dict[str, Any]],
        literature_ok: bool,
    ) -> bool:
        return self.phase_handlers._has_observe_evidence_matrix(literature_result, literature_ok)

    def _should_run_observe_ingestion(self, context: Dict[str, Any]) -> bool:
        return self.phase_handlers._should_run_observe_ingestion(context)

    def _should_run_observe_literature(self, context: Dict[str, Any]) -> bool:
        return self.phase_handlers._should_run_observe_literature(context)

    def _run_observe_literature_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.phase_handlers._run_observe_literature_pipeline(context)

    def _should_run_clinical_gap_analysis(self, context: Dict[str, Any]) -> bool:
        if "run_clinical_gap_analysis" in context:
            return bool(context.get("run_clinical_gap_analysis"))

        gap_config = self.config.get("clinical_gap_analysis", {})
        return bool(gap_config.get("enabled", False))

    def _run_clinical_gap_analysis(
        self,
        evidence_matrix: Dict[str, Any],
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        # 延迟导入：CachedLLMService 依赖 llama-cpp-python（重量级），只在实际调用时加载
        global CachedLLMService
        if CachedLLMService is None:
            from src.llm.llm_service import CachedLLMService as _CLS

            CachedLLMService = _CLS

        gap_config = self.config.get("clinical_gap_analysis", {})
        llm_config = self.config.get("models", {}).get("llm", {})

        # CachedLLMService 磁盘缓存：相同请求直接从 SQLite 返回，跳过 GPU 推理
        engine = CachedLLMService.from_gap_config(gap_config, llm_config)
        analyzer = GapAnalyzer(gap_config, llm_service=engine)
        analysis_context = {
            "evidence_matrix": evidence_matrix,
            "literature_summaries": summaries,
            "llm_service": engine,
            "clinical_question": context.get("clinical_question"),
            "literature_query": context.get("literature_query"),
            "research_topic": context.get("research_topic"),
            "gap_output_language": context.get("gap_output_language"),
            "gap_output_mode": context.get("gap_output_mode"),
            "output_language": context.get("output_language"),
            "use_llm_refinement": context.get("use_llm_refinement"),
        }

        try:
            engine.load()
            analyzer.initialize()
            result = analyzer.execute(analysis_context)
            stats = engine.cache_stats()
            self.logger.debug(
                "LLM 缓存统计: hits=%d misses=%d total_entries=%s",
                stats.get("session_hits", 0),
                stats.get("session_misses", 0),
                stats.get("total_entries", "n/a"),
            )
            result.setdefault("metadata", {})["cache_stats"] = stats
            return result
        except Exception as e:
            self.logger.error(f"Qwen 临床 Gap Analysis 失败: {e}")
            return {
                "clinical_question": str(
                    context.get("clinical_question")
                    or context.get("literature_query")
                    or gap_config.get("default_clinical_question")
                    or "中医干预在目标人群中的临床有效性与安全性证据缺口是什么？"
                ),
                "output_language": str(
                    context.get("gap_output_language")
                    or context.get("output_language")
                    or gap_config.get("default_output_language")
                    or gap_config.get("output_language", "zh")
                ),
                "error": str(e),
            }
        finally:
            analyzer.cleanup()
            engine.unload()

    def _extract_literature_summaries(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for item in records:
            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()
            text = abstract or title
            if not text:
                continue

            summaries.append(
                {
                    "source": item.get("source", ""),
                    "title": title,
                    "year": item.get("year"),
                    "doi": item.get("doi", ""),
                    "url": item.get("url", ""),
                    "summary_text": text[:1200],
                    "has_abstract": bool(abstract),
                }
            )
        return summaries

    def _build_evidence_matrix(
        self,
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        default_dimensions: Dict[str, List[str]] = {
            "condition_terms": ["covid", "diabetes", "cancer", "depression", "inflammation", "pain"],
            "intervention_terms": ["traditional chinese medicine", "tcm", "herb", "formula", "decoction", "acupuncture"],
            "outcome_terms": ["efficacy", "effectiveness", "safety", "survival", "risk", "response"],
            "method_terms": ["randomized", "meta-analysis", "cohort", "case-control", "network", "machine learning"],
        }

        dimension_keywords = context.get("evidence_dimensions") or default_dimensions
        records: List[Dict[str, Any]] = []
        dimension_hit_counts = {key: 0 for key in dimension_keywords.keys()}

        for item in summaries:
            text = f"{item.get('title', '')} {item.get('summary_text', '')}".lower()
            row_hits: Dict[str, List[str]] = {}

            for dimension, keywords in dimension_keywords.items():
                hits = [kw for kw in keywords if kw.lower() in text]
                row_hits[dimension] = hits
                if hits:
                    dimension_hit_counts[dimension] += 1

            coverage_score = sum(1 for hits in row_hits.values() if hits)
            records.append(
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "year": item.get("year"),
                    "coverage_score": coverage_score,
                    "dimension_hits": row_hits,
                }
            )

        records.sort(key=lambda r: r.get("coverage_score", 0), reverse=True)
        return {
            "dimension_count": len(dimension_keywords),
            "dimension_keywords": dimension_keywords,
            "dimension_hit_counts": dimension_hit_counts,
            "record_count": len(records),
            "records": records,
        }

    def _should_collect_ctext_corpus(self, context: Dict[str, Any]) -> bool:
        return self.phase_handlers._should_collect_ctext_corpus(context)

    def _should_collect_local_corpus(self, context: Dict[str, Any]) -> bool:
        return self.phase_handlers._should_collect_local_corpus(context)

    def _collect_local_observation_corpus(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.phase_handlers._collect_local_observation_corpus(context)

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        return self.phase_handlers._resolve_observe_data_source(context)

    def _resolve_whitelist_groups(self, context: Dict[str, Any]) -> List[str]:
        return self.phase_handlers._resolve_whitelist_groups(context)

    def _collect_ctext_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.phase_handlers._collect_ctext_observation_corpus(context)

    def _run_observe_ingestion_pipeline(self, corpus_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return self.phase_handlers._run_observe_ingestion_pipeline(corpus_result, context)

    def _extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """统一文本条目提取 — 兼容新 CorpusBundle 格式与旧 CText dict 格式。"""
        return self.phase_handlers._extract_corpus_text_entries(corpus_result)
    
    def _execute_hypothesis_phase(self, cycle: ResearchCycle, 
                                context: Dict[str, Any]) -> Dict[str, Any]:
        """执行假设阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_hypothesis_phase(cycle, context)

    def _build_hypothesis_context(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self.phase_handlers._build_hypothesis_context(cycle, context)

    def _infer_hypothesis_domain(
        self,
        cycle: ResearchCycle,
        observations: List[str],
        findings: List[str],
    ) -> str:
        return self.phase_handlers._infer_hypothesis_domain(cycle, observations, findings)
    
    def _execute_experiment_phase(self, cycle: ResearchCycle, 
                                context: Dict[str, Any]) -> Dict[str, Any]:
        """执行实验阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_experiment_phase(cycle, context)
    
    def _execute_analyze_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """执行分析阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_analyze_phase(cycle, context)
    
    def _execute_publish_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """执行发布阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_publish_phase(cycle, context)

    def _collect_citation_records(
        self,
        cycle: ResearchCycle,
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self.phase_handlers.collect_citation_records(cycle, context, literature_pipeline)
    
    def _execute_reflect_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """执行反思阶段（兼容入口，委托阶段处理器）。"""
        return self.phase_handlers.execute_reflect_phase(cycle, context)
    
    def complete_research_cycle(self, cycle_id: str) -> bool:
        """完成研究循环（委托编排器执行）。"""
        return self.orchestrator.complete_research_cycle(cycle_id)
    
    def suspend_research_cycle(self, cycle_id: str) -> bool:
        """暂停研究循环（委托编排器执行）。"""
        return self.orchestrator.suspend_research_cycle(cycle_id)
    
    def resume_research_cycle(self, cycle_id: str) -> bool:
        """恢复研究循环（委托编排器执行）。"""
        return self.orchestrator.resume_research_cycle(cycle_id)
    
    def get_cycle_status(self, cycle_id: str) -> Dict[str, Any]:
        """
        获取研究循环状态
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            Dict[str, Any]: 状态信息
        """
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
            "phase_executions": self._serialize_phase_executions(cycle),
            "metadata": self._serialize_value(cycle.metadata),
        }
    
    def get_all_cycles(self) -> List[Dict[str, Any]]:
        """
        获取所有研究循环
        
        Returns:
            List[Dict[str, Any]]: 循环列表
        """
        return [
            {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.cycle_name,
                "status": cycle.status.value,
                "current_phase": cycle.current_phase.value,
                "started_at": cycle.started_at,
                "research_objective": cycle.research_objective,
                "analysis_summary": self._serialize_value(cycle.metadata.get("analysis_summary", {})),
            } for cycle in self.research_cycles.values()
        ]
    
    def get_cycle_history(self, cycle_id: str) -> List[Dict[str, Any]]:
        """
        获取研究循环历史
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            List[Dict[str, Any]]: 历史记录
        """
        return [entry for entry in self.execution_history 
                if entry.get("cycle_id") == cycle_id]
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """
        获取流程管理摘要
        
        Returns:
            Dict[str, Any]: 摘要信息
        """
        total_cycles = len(self.research_cycles)
        active_cycles = len(self.active_cycles)
        completed_cycles = sum(1 for c in self.research_cycles.values() 
                             if c.status == ResearchCycleStatus.COMPLETED)
        failed_cycles = sum(1 for c in self.research_cycles.values() if c.status == ResearchCycleStatus.FAILED)
        
        # 计算质量指标
        if total_cycles > 0:
            completion_rate = completed_cycles / total_cycles
        else:
            completion_rate = 0.0
        
        return {
            "pipeline_summary": {
                "total_cycles": total_cycles,
                "active_cycles": active_cycles,
                "completed_cycles": completed_cycles,
                "failed_cycles": failed_cycles,
                "completion_rate": round(completion_rate, 4),
                "quality_metrics": self._serialize_value(self.quality_metrics),
                "resource_usage": self._serialize_value(self.resource_usage),
                "recent_activities": self._serialize_value(self.execution_history[-10:] if self.execution_history else []),
                "analysis_summary": self._build_pipeline_analysis_summary(),
                "report_metadata": self._build_report_metadata(),
                "failed_operations": self._serialize_value(self._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
        }
    
    def export_pipeline_data(self, output_path: str) -> bool:
        """
        导出流程数据
        
        Args:
            output_path (str): 输出路径
            
        Returns:
            bool: 导出是否成功
        """
        phase_entry = self._start_phase(self._metadata, "export_pipeline_data", {"output_path": output_path})
        start_time = time.perf_counter()
        try:
            pipeline_data = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                    "exported_file": os.path.basename(output_path),
                },
                "pipeline_info": {
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "pipeline_summary": self.get_pipeline_summary()
                },
                "research_cycles": [self._serialize_cycle(cycle) for cycle in self.research_cycles.values()],
                "failed_cycles": [self._serialize_cycle(cycle) for cycle in self.failed_cycles],
                "execution_history": self._serialize_value(self.execution_history),
                "quality_metrics": self._serialize_value(self.quality_metrics),
                "resource_usage": self._serialize_value(self.resource_usage),
                "failed_operations": self._serialize_value(self._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(pipeline_data, f, ensure_ascii=False, indent=2)
            self._complete_phase(self._metadata, "export_pipeline_data", phase_entry, start_time)
            
            self.logger.info(f"流程数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "export_pipeline_data", phase_entry, start_time, str(e))
            self.logger.error(f"流程数据导出失败: {e}")
            return False
    
    def _persist_result(self, cycle: ResearchCycle) -> bool:
        """
        将研究循环结果持久化到 SQLite 数据库。

        Args:
            cycle: 已完成（或失败）的研究循环对象

        Returns:
            bool: True 表示写入成功，False 表示写入失败（不阻断主链）
        """
        db_path = self.config.get(
            "result_store_path",
            os.path.join("output", "research_results.db"),
        )
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        ddl = """
        CREATE TABLE IF NOT EXISTS research_results (
            cycle_id          TEXT PRIMARY KEY,
            cycle_name        TEXT NOT NULL,
            status            TEXT NOT NULL,
            started_at        TEXT,
            completed_at      TEXT,
            duration          REAL,
            research_objective TEXT,
            outcomes_json     TEXT,
            metadata_json     TEXT,
            persisted_at      TEXT NOT NULL
        )
        """
        row = (
            cycle.cycle_id,
            cycle.cycle_name,
            cycle.status.value,
            cycle.started_at,
            cycle.completed_at,
            cycle.duration,
            cycle.research_objective,
            json.dumps(self._serialize_value(cycle.outcomes), ensure_ascii=False),
            json.dumps(self._serialize_value(cycle.metadata), ensure_ascii=False),
            datetime.now().isoformat(),
        )
        upsert = """
        INSERT OR REPLACE INTO research_results
            (cycle_id, cycle_name, status, started_at, completed_at, duration,
             research_objective, outcomes_json, metadata_json, persisted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(ddl)
                conn.execute(upsert, row)
            finally:
                conn.close()
            self.logger.info(f"研究结果已持久化: {cycle.cycle_id} → {db_path}")
            return True
        except Exception as exc:  # pragma: no cover
            self.logger.warning(f"研究结果持久化失败，已跳过: {exc}")
            return False

    def cleanup(self) -> bool:
        """
        清理资源
        
        Returns:
            bool: 清理是否成功
        """
        try:
            self.hypothesis_engine.cleanup()
            # 清空数据结构
            self.research_cycles.clear()
            self.active_cycles.clear()
            self.failed_cycles.clear()
            self.execution_history.clear()
            self._failed_operations.clear()
            self._metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "cleaned",
                "last_completed_phase": None,
            }
            self.quality_metrics = {
                "cycle_completion_rate": 0.0,
                "phase_efficiency": 0.0,
                "researcher_productivity": 0.0,
                "quality_assurance": 0.0
            }
            self.resource_usage = {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "storage_usage": 0.0,
                "network_usage": 0.0
            }
            
            self.logger.info("研究流程管理器资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")
            return False

# 导出主要类和函数
__all__ = [
    'ResearchPipeline',
    'ResearchCycle',
    'ResearchPhase',
    'ResearchCycleStatus',
    'LLMEngine'
]
