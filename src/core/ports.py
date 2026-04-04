"""Bounded-context Port interfaces for the research pipeline.

Each Port defines the contract boundary between the pipeline coordinator
and a specific domain.  Concrete adapters implement these ABCs and are
injected into the pipeline at construction time, replacing the former
12+ direct class dependencies with 5 clean seams.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CollectionPort — corpus collection & literature retrieval
# ---------------------------------------------------------------------------

class CollectionPort(ABC):
    """Boundary for all data-collection operations."""

    @abstractmethod
    def collect_ctext_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Collect corpus from the ctext whitelist source."""

    @abstractmethod
    def collect_local_corpus(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Collect corpus from local file sources."""

    @abstractmethod
    def search_literature(
        self,
        query: str,
        *,
        sources: Optional[List[str]] = None,
        max_results_per_source: int = 20,
    ) -> Dict[str, Any]:
        """Run a literature search and return consolidated results."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources held by the collection subsystem."""


# ---------------------------------------------------------------------------
# AnalysisPort — preprocessing, extraction, semantic modelling, reasoning
# ---------------------------------------------------------------------------

class AnalysisPort(ABC):
    """Boundary for the document-analysis pipeline."""

    @abstractmethod
    def create_preprocessor(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable DocumentPreprocessor instance."""

    @abstractmethod
    def create_extractor(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable AdvancedEntityExtractor instance."""

    @abstractmethod
    def create_semantic_builder(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable SemanticGraphBuilder instance."""

    @abstractmethod
    def create_reasoning_engine(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable ReasoningEngine instance."""


# ---------------------------------------------------------------------------
# ResearchPort — hypothesis engine & cycle lifecycle
# ---------------------------------------------------------------------------

class ResearchPort(ABC):
    """Boundary for research-cycle management and hypothesis generation."""

    @abstractmethod
    def execute_hypothesis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run hypothesis generation for the given context."""

    @abstractmethod
    def initialize_hypothesis_engine(self) -> None:
        """Warm-up / initialize the hypothesis engine."""

    @abstractmethod
    def cleanup_hypothesis_engine(self) -> None:
        """Release resources held by the hypothesis engine."""


# ---------------------------------------------------------------------------
# QualityPort — quality assessment, audit, governance
# ---------------------------------------------------------------------------

class QualityPort(ABC):
    """Boundary for quality inspection and governance."""

    @abstractmethod
    def build_pipeline_analysis_summary(
        self,
        research_cycles: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        governance_config: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Produce an analysis summary of the pipeline run."""

    @abstractmethod
    def reset(self) -> None:
        """Reset accumulated quality metrics."""

    @abstractmethod
    def get_quality_metrics(self) -> Dict[str, Any]:
        """Return current quality metrics snapshot."""

    @abstractmethod
    def get_resource_usage(self) -> Dict[str, Any]:
        """Return current resource-usage snapshot."""


# ---------------------------------------------------------------------------
# OutputPort — citation, paper, report, export
# ---------------------------------------------------------------------------

class OutputPort(ABC):
    """Boundary for all output-generation operations."""

    @abstractmethod
    def create_citation_manager(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable CitationManager instance."""

    @abstractmethod
    def create_paper_writer(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable PaperWriter instance."""

    @abstractmethod
    def create_output_generator(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable OutputGenerator instance."""

    @abstractmethod
    def create_report_generator(self, config: Optional[Dict[str, Any]] = None) -> Any:
        """Return an initializable ReportGenerator instance."""
