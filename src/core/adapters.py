"""Default Port-adapter implementations backed by the existing module factory.

Each adapter satisfies the corresponding Port ABC while delegating to modules
already registered in the pipeline's ModuleFactory.  This preserves full
backward-compatibility: the pipeline coordinator talks to Port interfaces,
and the adapters route calls to the concrete classes that existed before.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.ports import (
    AnalysisPort,
    CollectionPort,
    OutputPort,
    QualityPort,
    ResearchPort,
)

try:
    from src.generation.llm_context_adapter import (
        DEFAULT_LLM_ANALYSIS_MODULE_ALIASES,
        wrap_paper_writer_with_llm_context,
    )
except Exception:
    DEFAULT_LLM_ANALYSIS_MODULE_ALIASES = {}
    wrap_paper_writer_with_llm_context = None


class DefaultCollectionAdapter(CollectionPort):
    """Routes collection calls through the module factory."""

    def __init__(self, module_factory: Any, config: Dict[str, Any]) -> None:
        self._factory = module_factory
        self._config = config

    def collect_ctext_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        collector = self._factory.create("ctext_corpus_collector", context.get("ctext_config") or {})
        if not collector.initialize():
            return {"error": "CText 语料采集器初始化失败"}
        try:
            return collector.execute(context)
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            collector.cleanup()

    def collect_local_corpus(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collector = self._factory.create("local_corpus_collector", context.get("local_config") or {})
        if not collector.initialize():
            return {"error": "本地语料采集器初始化失败"}
        try:
            return collector.execute(context)
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            collector.cleanup()

    def search_literature(
        self,
        query: str,
        *,
        sources: Optional[List[str]]=None,
        max_results_per_source: int=20,
    ) -> Dict[str, Any]:
        retriever = self._factory.create("literature_retriever", {})
        try:
            return retriever.search(
                query=query,
                sources=sources or ["pubmed"],
                max_results_per_source=max_results_per_source,
            )
        finally:
            retriever.close()

    def cleanup(self) -> None:
        pass


class DefaultAnalysisAdapter(AnalysisPort):
    """Routes analysis calls through the module factory."""

    def __init__(self, module_factory: Any) -> None:
        self._factory = module_factory

    def create_preprocessor(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("document_preprocessor", config or {})

    def create_extractor(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("entity_extractor", config or {})

    def create_semantic_builder(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("semantic_graph_builder", config or {})

    def create_reasoning_engine(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("reasoning_engine", config or {})


class DefaultResearchAdapter(ResearchPort):
    """Wraps the existing HypothesisEngine behind the ResearchPort interface."""

    def __init__(self, hypothesis_engine: Any) -> None:
        self._engine = hypothesis_engine

    def execute_hypothesis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._engine.execute(context)

    def initialize_hypothesis_engine(self) -> None:
        self._engine.initialize()

    def cleanup_hypothesis_engine(self) -> None:
        self._engine.cleanup()


class DefaultQualityAdapter(QualityPort):
    """Wraps the existing QualityAssessor behind the QualityPort interface."""

    def __init__(self, quality_assessor: Any) -> None:
        self._assessor = quality_assessor

    def build_pipeline_analysis_summary(
        self,
        research_cycles: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        governance_config: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._assessor.build_pipeline_analysis_summary(
            research_cycles, failed_operations, governance_config, metadata,
        )

    def reset(self) -> None:
        self._assessor.reset()

    def get_quality_metrics(self) -> Dict[str, Any]:
        return self._assessor.quality_metrics

    def get_resource_usage(self) -> Dict[str, Any]:
        return self._assessor.resource_usage


class DefaultOutputAdapter(OutputPort):
    """Routes output-generation calls through the module factory."""

    def __init__(self, module_factory: Any) -> None:
        self._factory = module_factory

    def create_citation_manager(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("citation_manager", config or {})

    def create_paper_writer(self, config: Optional[Dict[str, Any]]=None) -> Any:
        paper_writer = self._factory.create("paper_writer", config or {})
        if not callable(wrap_paper_writer_with_llm_context):
            return paper_writer
        module_aliases = (
            dict(DEFAULT_LLM_ANALYSIS_MODULE_ALIASES)
            if isinstance(DEFAULT_LLM_ANALYSIS_MODULE_ALIASES, dict) and DEFAULT_LLM_ANALYSIS_MODULE_ALIASES
            else None
        )
        return wrap_paper_writer_with_llm_context(
            paper_writer,
            module_aliases=module_aliases,
        )

    def create_output_generator(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("output_generator", config or {})

    def create_report_generator(self, config: Optional[Dict[str, Any]]=None) -> Any:
        return self._factory.create("report_generator", config or {})
