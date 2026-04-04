# research/research_pipeline.py
"""
中医古籍全自动研究系统 - 专业学术研究流程管理模块
基于AI的科研闭环流程管理系统
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.collector.ctext_corpus_collector import CTextCorpusCollector
from src.collector.literature_retriever import LiteratureRetriever
from src.collector.local_collector import LocalCorpusCollector
from src.core.adapters import (
    DefaultAnalysisAdapter,
    DefaultCollectionAdapter,
    DefaultOutputAdapter,
    DefaultQualityAdapter,
    DefaultResearchAdapter,
)
from src.core.event_bus import EventBus
from src.core.module_base import get_global_executor
from src.core.module_factory import ModuleFactory
from src.quality.quality_assessor import QualityAssessor
from src.research.audit_history import AuditHistory
from src.research.gap_analyzer import GapAnalyzer
from src.research.hypothesis_engine import HypothesisEngine
from src.research.phase_orchestrator import PhaseOrchestrator
from src.research.pipeline_orchestrator import ResearchPipelineOrchestrator
from src.research.pipeline_phase_handlers import ResearchPhaseHandlers
from src.research.study_session_manager import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
    StudySessionManager,
)

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

try:
    from src.generation.report_generator import (
        ReportGenerator as _ImportedReportGenerator,
    )
except Exception:
    _ImportedReportGenerator = None

ReportGenerator = _ImportedReportGenerator

# 分析模块 — 延迟导入，支持依赖注入
try:
    from src.analysis.entity_extractor import (
        AdvancedEntityExtractor as _ImportedAdvancedEntityExtractor,
    )
except Exception:
    _ImportedAdvancedEntityExtractor = None

AdvancedEntityExtractor = _ImportedAdvancedEntityExtractor

try:
    from src.analysis.preprocessor import (
        DocumentPreprocessor as _ImportedDocumentPreprocessor,
    )
except Exception:
    _ImportedDocumentPreprocessor = None

DocumentPreprocessor = _ImportedDocumentPreprocessor

try:
    from src.analysis.semantic_graph import (
        SemanticGraphBuilder as _ImportedSemanticGraphBuilder,
    )
except Exception:
    _ImportedSemanticGraphBuilder = None

SemanticGraphBuilder = _ImportedSemanticGraphBuilder

try:
    from src.analysis.reasoning_engine import (
        ReasoningEngine as _ImportedReasoningEngine,
    )
except Exception:
    _ImportedReasoningEngine = None

ReasoningEngine = _ImportedReasoningEngine


class ResearchPipeline:
    """中医古籍全自动研究系统科研流程管理。"""

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
    ReasoningEngine = ReasoningEngine
    PaperWriter = PaperWriter
    OutputGenerator = OutputGenerator
    ReportGenerator = ReportGenerator

    _MODULE_KEYS = {
        "literature_retriever": "LiteratureRetriever",
        "local_corpus_collector": "LocalCorpusCollector",
        "ctext_corpus_collector": "CTextCorpusCollector",
        "document_preprocessor": "DocumentPreprocessor",
        "entity_extractor": "AdvancedEntityExtractor",
        "semantic_graph_builder": "SemanticGraphBuilder",
        "reasoning_engine": "ReasoningEngine",
        "citation_manager": "CitationManager",
        "paper_writer": "PaperWriter",
        "output_generator": "OutputGenerator",
        "report_generator": "ReportGenerator",
    }

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        preprocessor: Optional[Any] = None,
        extractor: Optional[Any] = None,
        graph_builder: Optional[Any] = None,
        reasoning_engine: Optional[Any] = None,
        llm_engine: Optional[Any] = None,
    ):
        self.config = config or {}
        self.event_bus = EventBus()
        self.module_factory = ModuleFactory.from_config(self.config.get("module_factory") or {})

        # 保存注入的实例，供工厂优先使用
        self._injected: Dict[str, Any] = {}
        if preprocessor is not None:
            self._injected["document_preprocessor"] = preprocessor
        if extractor is not None:
            self._injected["entity_extractor"] = extractor
        if graph_builder is not None:
            self._injected["semantic_graph_builder"] = graph_builder
        if reasoning_engine is not None:
            self._injected["reasoning_engine"] = reasoning_engine
        if llm_engine is not None:
            self._injected["llm_engine"] = llm_engine
            # 同时写入 config 供 hypothesis_engine 等组件使用
            self.config.setdefault("llm_engine", llm_engine)

        self._register_default_module_providers()

        self._bootstrap_infrastructure()
        self._bootstrap_research_services()

        self.logger.info("研究流程管理器初始化完成")

    # ------------------------------------------------------------------
    # 初始化辅助方法
    # ------------------------------------------------------------------

    def _bootstrap_infrastructure(self) -> None:
        """基础设施初始化：线程池、治理配置、会话管理、审计绑定。"""
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

        self.session_manager = StudySessionManager(self._governance_config)
        self.audit_history = AuditHistory(self.session_manager.execution_history)
        self.audit_history.attach_to_event_bus(self.event_bus)
        self.research_cycles = self.session_manager.research_cycles
        self.active_cycles = self.session_manager.active_cycles
        self.failed_cycles = self.session_manager.failed_cycles
        self.execution_history = self.audit_history.entries

    def _bootstrap_research_services(self) -> None:
        """研究服务初始化：质量评估、假设引擎、阶段编排器、Port适配器。"""
        self.quality_assessor = QualityAssessor()
        self.quality_metrics = self.quality_assessor.quality_metrics
        self.resource_usage = self.quality_assessor.resource_usage

        self.hypothesis_engine = HypothesisEngine(
            self.config.get("hypothesis_engine_config") or {},
            llm_engine=self.config.get("llm_engine") or self.config.get("llm_service"),
        )
        self.hypothesis_engine.initialize()

        self.phase_orchestrator = PhaseOrchestrator(self)
        self.phase_handlers = ResearchPhaseHandlers(self)
        self.orchestrator = ResearchPipelineOrchestrator(self, self.phase_handlers)

        # Port adapters — bounded-context interfaces (Phase 2)
        self.collection_port = DefaultCollectionAdapter(self.module_factory, self.config)
        self.analysis_port = DefaultAnalysisAdapter(self.module_factory)
        self.research_port = DefaultResearchAdapter(self.hypothesis_engine)
        self.quality_port = DefaultQualityAdapter(self.quality_assessor)
        self.output_port = DefaultOutputAdapter(self.module_factory)

    def _register_default_module_providers(self) -> None:
        for key, symbol_name in self._MODULE_KEYS.items():
            if self.module_factory.has(key):
                continue

            # 若有注入实例，优先使用（忽略后续传入的 config）
            injected = self._injected.get(key)
            if injected is not None:
                def _injected_provider(cfg: Dict[str, Any], _inst=injected):
                    return _inst
                self.module_factory.register(key, _injected_provider)
                continue

            def _provider(cfg: Dict[str, Any], _symbol=symbol_name):
                cls = globals().get(_symbol)
                if cls is None:
                    raise RuntimeError(f"模块工厂默认依赖不可用: {_symbol}")
                return cls(cfg)

            self.module_factory.register(key, _provider)

    def create_module(self, key: str, config: Optional[Dict[str, Any]] = None) -> Any:
        return self.module_factory.create(key, config or {})

    def _initialize_cycle_tracking(self, cycle: ResearchCycle) -> None:
        self.session_manager.initialize_cycle_tracking(cycle)

    def _mark_cycle_failed(self, cycle: ResearchCycle, phase_name: str, error: str) -> None:
        self.session_manager.mark_cycle_failed(cycle, phase_name, error)

    def _build_cycle_analysis_summary(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return self.session_manager.build_cycle_analysis_summary(cycle)

    def _build_pipeline_analysis_summary(self) -> Dict[str, Any]:
        return self.quality_assessor.build_pipeline_analysis_summary(
            self.research_cycles,
            self._failed_operations,
            self._governance_config,
            self._metadata,
        )

    def _serialize_phase_executions(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return self.session_manager.serialize_phase_executions(cycle)

    def _serialize_cycle(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return self.session_manager.serialize_cycle(cycle)

    def _build_report_metadata(self) -> Dict[str, Any]:
        runtime_metadata = self.phase_orchestrator._build_runtime_metadata()
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
        return self.orchestrator.create_research_cycle(
            cycle_name=cycle_name,
            description=description,
            objective=objective,
            scope=scope,
            researchers=researchers,
            **cycle_options,
        )

    def start_research_cycle(self, cycle_id: str) -> bool:
        return self.orchestrator.start_research_cycle(cycle_id)

    def execute_research_phase(
        self,
        cycle_id: str,
        phase: ResearchPhase,
        phase_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.orchestrator.execute_research_phase(cycle_id, phase, phase_context)

    def complete_research_cycle(self, cycle_id: str) -> bool:
        return self.orchestrator.complete_research_cycle(cycle_id)

    def suspend_research_cycle(self, cycle_id: str) -> bool:
        return self.orchestrator.suspend_research_cycle(cycle_id)

    def resume_research_cycle(self, cycle_id: str) -> bool:
        return self.orchestrator.resume_research_cycle(cycle_id)

    def get_cycle_status(self, cycle_id: str) -> Dict[str, Any]:
        return self.session_manager.get_cycle_status(cycle_id)

    def get_all_cycles(self) -> List[Dict[str, Any]]:
        return self.session_manager.get_all_cycles()

    def get_cycle_history(self, cycle_id: str) -> List[Dict[str, Any]]:
        return self.session_manager.get_cycle_history(cycle_id)

    def get_pipeline_summary(self) -> Dict[str, Any]:
        return self.phase_orchestrator.get_pipeline_summary()

    def export_pipeline_data(self, output_path: str) -> bool:
        return self.phase_orchestrator.export_pipeline_data(output_path)

    def _persist_result(self, cycle: ResearchCycle) -> bool:
        return self.phase_orchestrator._persist_result(cycle)

    def _run_clinical_gap_analysis(
        self,
        evidence_matrix: Dict[str, Any],
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        import src.research.phase_orchestrator as phase_orchestrator_module

        phase_orchestrator_module.CachedLLMService = CachedLLMService
        phase_orchestrator_module.GapAnalyzer = GapAnalyzer
        return self.phase_orchestrator._run_clinical_gap_analysis(evidence_matrix, summaries, context)

    def cleanup(self) -> bool:
        try:
            self.hypothesis_engine.cleanup()
            self.audit_history.detach_from_event_bus()
            self.research_cycles.clear()
            self.active_cycles.clear()
            self.failed_cycles.clear()
            self.audit_history.clear()
            self._failed_operations.clear()
            self._metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "cleaned",
                "last_completed_phase": None,
            }
            self.quality_assessor.reset()

            self.logger.info("研究流程管理器资源清理完成")
            return True

        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")
            return False

    def __getattr__(self, name: str) -> Any:
        """将未定义的属性访问委托到 phase_orchestrator。

        委托目标包含: get_pipeline_summary, export_pipeline_data,
        _build_runtime_metadata, _persist_result 等 PhaseOrchestrator 公开方法。
        """
        try:
            phase_orchestrator = object.__getattribute__(self, "phase_orchestrator")
            return getattr(phase_orchestrator, name)
        except AttributeError as exc:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'") from exc


__all__ = [
    "ResearchPipeline",
    "ResearchCycle",
    "ResearchPhase",
    "ResearchCycleStatus",
    "LLMEngine",
    "CachedLLMService",
    "GapAnalyzer",
]
