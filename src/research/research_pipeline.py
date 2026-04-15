# research/research_pipeline.py
"""
中医古籍全自动研究系统 - 专业学术研究流程管理模块
基于AI的科研闭环流程管理系统
"""

import logging
from datetime import datetime
from importlib import import_module
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

_OPTIONAL_RUNTIME_IMPORTS = {
    "CitationManager": ("src.generation.citation_manager", "CitationManager"),
    "PaperWriter": ("src.generation.paper_writer", "PaperWriter"),
    "OutputGenerator": ("src.generation.output_formatter", "OutputGenerator"),
    "ReportGenerator": ("src.generation.report_generator", "ReportGenerator"),
    "PhilologyService": ("src.analysis.philology_service", "PhilologyService"),
    "AdvancedEntityExtractor": ("src.analysis.entity_extractor", "AdvancedEntityExtractor"),
    "DocumentPreprocessor": ("src.analysis.preprocessor", "DocumentPreprocessor"),
    "SemanticGraphBuilder": ("src.analysis.semantic_graph", "SemanticGraphBuilder"),
    "ReasoningEngine": ("src.analysis.reasoning_engine", "ReasoningEngine"),
}


def _build_unavailable_module(symbol_name: str):
    """构造可 patch 的缺省模块占位类，避免可选依赖缺失时测试导入失败。"""

    class _UnavailableModule:
        def __init__(self, config: Optional[Dict[str, Any]] = None):
            self.config = config or {}
            self._symbol_name = symbol_name

        def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
            if config:
                self.config.update(config)
            return False

        def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return {"error": f"模块工厂默认依赖不可用: {self._symbol_name}"}

        def cleanup(self) -> None:
            return None

        def close(self) -> None:
            return None

    _UnavailableModule.__name__ = symbol_name
    _UnavailableModule._copilot_unavailable_placeholder = True
    return _UnavailableModule

# 供单测 patch 的符号；导入失败时在运行时再惰性加载。


def _try_import(module_path: str, symbol: str, fallback=None):
    """尝试导入符号，失败时记录 WARNING 并返回 fallback。"""
    try:
        mod = import_module(module_path)
        return getattr(mod, symbol)
    except Exception as exc:
        logger.warning("可选依赖 %s.%s 导入失败，降级为 stub: %s", module_path, symbol, exc)
        return fallback


LLMEngine = _try_import("src.llm.llm_engine", "LLMEngine")
CachedLLMService = _try_import("src.infra.llm_service", "CachedLLMService")
CitationManager = _try_import("src.generation.citation_manager", "CitationManager")
PaperWriter = _try_import("src.generation.paper_writer", "PaperWriter")
OutputGenerator = _try_import("src.generation.output_formatter", "OutputGenerator")
ReportGenerator = _try_import("src.generation.report_generator", "ReportGenerator")
SelfLearningEngine = _try_import("src.learning.self_learning_engine", "SelfLearningEngine")

# 分析模块 — 延迟导入，支持依赖注入
PhilologyService = _try_import("src.analysis.philology_service", "PhilologyService")
AdvancedEntityExtractor = _try_import("src.analysis.entity_extractor", "AdvancedEntityExtractor")
DocumentPreprocessor = _try_import("src.analysis.preprocessor", "DocumentPreprocessor")
SemanticGraphBuilder = _try_import(
    "src.analysis.semantic_graph", "SemanticGraphBuilder",
    fallback=_build_unavailable_module("SemanticGraphBuilder"),
)
ReasoningEngine = _try_import(
    "src.analysis.reasoning_engine", "ReasoningEngine",
    fallback=_build_unavailable_module("ReasoningEngine"),
)


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
    PhilologyService = PhilologyService
    AdvancedEntityExtractor = AdvancedEntityExtractor
    SemanticGraphBuilder = SemanticGraphBuilder
    ReasoningEngine = ReasoningEngine
    PaperWriter = PaperWriter
    OutputGenerator = OutputGenerator
    ReportGenerator = ReportGenerator
    SelfLearningEngine = SelfLearningEngine

    _MODULE_KEYS = {
        "literature_retriever": "LiteratureRetriever",
        "local_corpus_collector": "LocalCorpusCollector",
        "ctext_corpus_collector": "CTextCorpusCollector",
        "philology_service": "PhilologyService",
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
        philology_service: Optional[Any] = None,
        extractor: Optional[Any] = None,
        graph_builder: Optional[Any] = None,
        reasoning_engine: Optional[Any] = None,
        llm_engine: Optional[Any] = None,
        self_learning_engine: Optional[Any] = None,
    ):
        self.config = config or {}
        self.event_bus = EventBus()
        self.module_factory = ModuleFactory.from_config(self.config.get("module_factory") or {})

        # 保存注入的实例，供工厂优先使用
        self._injected: Dict[str, Any] = {}
        if philology_service is not None:
            self._injected["philology_service"] = philology_service
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
        if self_learning_engine is not None:
            self.config["self_learning_engine"] = self_learning_engine

        self.self_learning_engine = self._bootstrap_self_learning_engine()
        self._learning_strategy: Dict[str, Any] = {}
        self.refresh_learning_runtime_feedback()

        self._register_default_module_providers()

        self._bootstrap_infrastructure()
        self._bootstrap_research_services()

        self.logger.info("研究流程管理器初始化完成")

    # ------------------------------------------------------------------
    # 初始化辅助方法
    # ------------------------------------------------------------------

    def _bootstrap_infrastructure(self) -> None:
        """基础设施初始化：线程池、治理配置、会话管理、审计绑定。"""
        learned_runtime_parameters = self._resolve_learned_runtime_parameters()
        learned_max_workers = learned_runtime_parameters.get("max_concurrent_tasks")
        configured_max_workers = self.config.get("max_workers")
        max_workers = configured_max_workers
        if max_workers is None and learned_max_workers is not None:
            try:
                max_workers = max(1, int(round(float(learned_max_workers))))
            except (TypeError, ValueError):
                max_workers = None

        # 使用全局共享线程池，与 BaseModule 保持一致
        self.executor = get_global_executor(max_workers=max_workers or 4)
        self.logger = logging.getLogger(__name__)
        self._failed_operations: List[Dict[str, Any]] = []
        minimum_stable_completion_rate = self.config.get("minimum_stable_completion_rate")
        if minimum_stable_completion_rate is None:
            minimum_stable_completion_rate = learned_runtime_parameters.get("quality_threshold", 0.8)
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
            "minimum_stable_completion_rate": float(minimum_stable_completion_rate),
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
                cls = self._resolve_default_module_class(_symbol)
                if cls is None:
                    raise RuntimeError(f"模块工厂默认依赖不可用: {_symbol}")
                return cls(cfg)

            self.module_factory.register(key, _provider)

    def _bootstrap_self_learning_engine(self) -> Any:
        learning_engine = self.config.get("self_learning_engine")
        if learning_engine is None:
            learning_engine = self._build_default_self_learning_engine()
            if learning_engine is not None:
                self.config["self_learning_engine"] = learning_engine

        if learning_engine is None:
            return None

        initialize = getattr(learning_engine, "initialize", None)
        if callable(initialize) and not getattr(learning_engine, "initialized", False):
            try:
                initialize({})
            except Exception as exc:
                logger.warning("SelfLearningEngine 默认初始化失败: %s", exc)
        return learning_engine

    def _build_default_self_learning_engine(self) -> Any:
        learning_config = self.config.get("self_learning")
        if not isinstance(learning_config, dict):
            return None
        if not bool(learning_config.get("enabled", False)):
            return None
        if SelfLearningEngine is None:
            logger.warning("SelfLearningEngine 不可用，跳过默认学习闭环接线")
            return None
        return SelfLearningEngine(dict(learning_config))

    def _resolve_learned_runtime_parameters(self) -> Dict[str, Any]:
        learned_runtime_parameters = self.config.get("learned_runtime_parameters")
        if isinstance(learned_runtime_parameters, dict):
            return dict(learned_runtime_parameters)
        return {}

    def refresh_learning_runtime_feedback(self) -> Dict[str, Any]:
        learning_engine = self.config.get("self_learning_engine")
        strategy: Dict[str, Any] = {}
        if learning_engine is not None and hasattr(learning_engine, "get_learning_strategy"):
            try:
                raw_strategy = learning_engine.get_learning_strategy()
                if isinstance(raw_strategy, dict):
                    strategy = dict(raw_strategy)
            except Exception as exc:
                logger.warning("刷新学习策略快照失败: %s", exc)

        self._learning_strategy = strategy
        if strategy:
            self.config["learning_strategy"] = dict(strategy)
            tuned_parameters = strategy.get("tuned_parameters")
            if isinstance(tuned_parameters, dict) and tuned_parameters:
                self.config["learned_runtime_parameters"] = dict(tuned_parameters)
                for key, value in tuned_parameters.items():
                    self.config.setdefault(key, value)

        if learning_engine is not None and hasattr(learning_engine, "build_previous_iteration_feedback"):
            try:
                previous_feedback = learning_engine.build_previous_iteration_feedback()
            except Exception as exc:
                logger.warning("构建上一轮学习反馈失败: %s", exc)
            else:
                if isinstance(previous_feedback, dict) and previous_feedback:
                    self.config["previous_iteration_feedback"] = dict(previous_feedback)

        return dict(self._learning_strategy)

    def get_learning_strategy(self) -> Dict[str, Any]:
        return self.refresh_learning_runtime_feedback()

    def get_previous_iteration_feedback(self) -> Dict[str, Any]:
        self.refresh_learning_runtime_feedback()
        previous_feedback = self.config.get("previous_iteration_feedback")
        if isinstance(previous_feedback, dict):
            return dict(previous_feedback)
        return {}

    @staticmethod
    def _is_unavailable_default_module_class(candidate: Any) -> bool:
        return candidate is None or bool(getattr(candidate, "_copilot_unavailable_placeholder", False))

    def _resolve_default_module_class(self, symbol_name: str) -> Any:
        cls = globals().get(symbol_name)
        if not self._is_unavailable_default_module_class(cls):
            return cls

        import_target = _OPTIONAL_RUNTIME_IMPORTS.get(symbol_name)
        if not import_target:
            return cls

        module_name, attribute_name = import_target
        try:
            module = import_module(module_name)
            resolved_class = getattr(module, attribute_name)
        except Exception as exc:
            self.logger.warning(
                "运行时惰性加载 %s (%s.%s) 失败，降级为 stub: %s",
                symbol_name, module_name, attribute_name, exc,
            )
            return cls

        globals()[symbol_name] = resolved_class
        setattr(self.__class__, symbol_name, resolved_class)
        return resolved_class

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

    def get_phase_handler(self, phase_name: str) -> Any:
        return self.phase_orchestrator.get_handler(phase_name)

    def _call_phase_handler_method(self, phase_name: str, method_name: str, *args: Any, **kwargs: Any) -> Any:
        handler = self.get_phase_handler(phase_name)
        method = getattr(handler, method_name, None)
        if method is None:
            raise AttributeError(f"阶段 {phase_name} 不支持方法: {method_name}")
        return method(*args, **kwargs)

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self.phase_orchestrator._build_runtime_metadata()

    def _start_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.phase_orchestrator._start_phase(metadata, phase_name, context)

    def _complete_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
        phase_status: str = "completed",
        error: Optional[str] = None,
    ) -> None:
        self.phase_orchestrator._complete_phase(
            metadata,
            phase_name,
            phase_entry,
            start_time,
            phase_status=phase_status,
            error=error,
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
        self.phase_orchestrator._fail_phase(
            metadata,
            failed_operations,
            phase_name,
            phase_entry,
            start_time,
            error,
        )

    def _validate_research_phase_request(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return self.phase_orchestrator._validate_research_phase_request(cycle_id)

    def _advance_research_cycle_phase(self, research_cycle: ResearchCycle, phase: ResearchPhase) -> None:
        self.phase_orchestrator._advance_research_cycle_phase(research_cycle, phase)

    def _build_phase_execution(
        self,
        phase: ResearchPhase,
        started_at: str,
        start_time: float,
        phase_context: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.phase_orchestrator._build_phase_execution(
            phase,
            started_at,
            start_time,
            phase_context,
            phase_result,
        )

    def _sync_phase_history_entry(
        self,
        phase_entry: Dict[str, Any],
        phase_execution: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> None:
        self.phase_orchestrator._sync_phase_history_entry(phase_entry, phase_execution, phase_result)

    def _apply_phase_result(
        self,
        research_cycle: ResearchCycle,
        phase: ResearchPhase,
        phase_result: Dict[str, Any],
    ) -> None:
        self.phase_orchestrator._apply_phase_result(research_cycle, phase, phase_result)

    def _record_phase_success(self, cycle_id: str, phase: ResearchPhase, start_time: float) -> None:
        self.phase_orchestrator._record_phase_success(cycle_id, phase, start_time)

    def _handle_phase_execution_failure(
        self,
        cycle_id: str,
        phase: ResearchPhase,
        start_time: float,
        exc: Exception,
    ) -> Dict[str, Any]:
        return self.phase_orchestrator._handle_phase_execution_failure(cycle_id, phase, start_time, exc)

    def _execute_phase_internal(
        self,
        phase: ResearchPhase,
        cycle: ResearchCycle,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.phase_orchestrator._execute_phase_internal(phase, cycle, context)

    def _collect_observe_corpus_if_enabled(self, context: Dict[str, Any]) -> Dict[str, Any] | None:
        return self._call_phase_handler_method("observe", "_collect_observe_corpus_if_enabled", context)

    def _build_observe_metadata(
        self,
        context: Dict[str, Any],
        observations: List[str],
        findings: List[str],
        corpus_result: Dict[str, Any] | None,
        ingestion_result: Dict[str, Any] | None,
        literature_result: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        return self._call_phase_handler_method(
            "observe",
            "_build_observe_metadata",
            context,
            observations,
            findings,
            corpus_result,
            ingestion_result,
            literature_result,
        )

    def _should_collect_ctext_corpus(self, context: Dict[str, Any]) -> bool:
        return bool(self._call_phase_handler_method("observe", "_should_collect_ctext_corpus", context))

    def _should_collect_local_corpus(self, context: Dict[str, Any]) -> bool:
        return bool(self._call_phase_handler_method("observe", "_should_collect_local_corpus", context))

    def _collect_local_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any] | None:
        return self._call_phase_handler_method("observe", "_collect_local_observation_corpus", context)

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        return str(self._call_phase_handler_method("observe", "_resolve_observe_data_source", context))

    def _resolve_whitelist_groups(self, context: Dict[str, Any]) -> List[str]:
        return list(self._call_phase_handler_method("observe", "_resolve_whitelist_groups", context))

    def _collect_ctext_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._call_phase_handler_method("observe", "_collect_ctext_observation_corpus", context)

    def _run_observe_ingestion_pipeline(self, corpus_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return self._call_phase_handler_method("observe", "_run_observe_ingestion_pipeline", corpus_result, context)

    def _extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        return list(self._call_phase_handler_method("observe", "_extract_corpus_text_entries", corpus_result))

    def _should_run_observe_ingestion(self, context: Dict[str, Any]) -> bool:
        return bool(self._call_phase_handler_method("observe", "_should_run_observe_ingestion", context))

    def _should_run_observe_literature(self, context: Dict[str, Any]) -> bool:
        return bool(self._call_phase_handler_method("observe", "_should_run_observe_literature", context))

    def _run_observe_literature_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._call_phase_handler_method("observe", "_run_observe_literature_pipeline", context)

    def _should_run_clinical_gap_analysis(self, context: Dict[str, Any]) -> bool:
        return bool(self.phase_orchestrator._should_run_clinical_gap_analysis(context))

    def _extract_literature_summaries(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.phase_orchestrator._extract_literature_summaries(records)

    def _build_evidence_matrix(
        self,
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.phase_orchestrator._build_evidence_matrix(summaries, context)

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
            if self.self_learning_engine is not None and hasattr(self.self_learning_engine, "cleanup"):
                self.self_learning_engine.cleanup()
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


__all__ = [
    "ResearchPipeline",
    "ResearchCycle",
    "ResearchPhase",
    "ResearchCycleStatus",
    "LLMEngine",
    "CachedLLMService",
    "GapAnalyzer",
]
