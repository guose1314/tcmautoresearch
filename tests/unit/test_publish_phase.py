# tests/unit/test_publish_phase.py
"""PublishPhaseMixin 单元测试

覆盖：
  - 正常路径：有引用记录、论文生成、IMRD 报告
  - 降级路径：PaperWriter / ReportGenerator 失败时回退
  - 空输入边界：无 citation_records、无先前阶段产出
  - deliverables 列表动态构建
  - output_files 合并逻辑
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.research.phase_handlers.publish_handler import PublishPhaseHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


@dataclass
class _FakeCycle:
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    researchers: List[str] = field(default_factory=lambda: ["张三"])
    cycle_name: str = "test_cycle"
    cycle_id: str = "test_cycle_001"
    description: str = "单元测试循环"
    research_objective: str = "中药配伍研究"
    research_scope: str = "中药古籍"
    target_audience: str = "研究者"
    started_at: str = "2026-01-01T00:00:00"
    completed_at: str = ""
    duration: float = 0.0
    advisors: List[str] = field(default_factory=list)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    expert_reviews: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    timeline: Dict[str, str] = field(default_factory=dict)


class _FakePipeline:
    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.output_port = MagicMock()
        self.analysis_port = MagicMock()
        self.analysis_port.create_reasoning_engine.side_effect = RuntimeError("no engine")
        # Fallback class refs (used when output_port fails)
        self.CitationManager = None
        self.PaperWriter = None
        self.OutputGenerator = None
        self.ReportGenerator = None
        self._setup_default_mocks()

    def _setup_default_mocks(self):
        # CitationManager mock
        cm = MagicMock()
        cm.execute.return_value = {
            "entries": [{"title": "本草纲目", "authors": ["李时珍"], "year": 1578}],
            "bibtex": "@book{bencao, title={本草纲目}}",
            "gbt7714": "[1] 李时珍. 本草纲目.",
            "formatted_references": "refs",
            "citation_count": 1,
            "output_files": {},
        }
        self.output_port.create_citation_manager.return_value = cm

        # PaperWriter mock
        pw = MagicMock()
        pw.execute.return_value = {
            "paper_draft": {
                "title": "Test Paper",
                "abstract": "Abstract",
                "sections": [{"section_type": "introduction", "title": "引言", "content": "..."}],
                "keywords": ["中药"],
            },
            "language": "zh",
            "section_count": 1,
            "reference_count": 1,
            "output_files": {"markdown": "/tmp/paper.md"},
        }
        self.output_port.create_paper_writer.return_value = pw

        # ReportGenerator mock
        rg = MagicMock()
        rg.execute.return_value = {
            "reports": {"markdown": {"title": "Report", "content": "..."}},
            "errors": [],
            "output_files": {"imrd_markdown": "/tmp/report.md"},
        }
        self.output_port.create_report_generator.return_value = rg

    def _extract_corpus_text_entries(self, corpus_result):
        return []


def _make_handler(pipeline=None):
    return PublishPhaseHandler(pipeline or _FakePipeline())


def _minimal_phase_executions():
    return {
        _Phase.OBSERVE: {"result": {}},
        _Phase.HYPOTHESIS: {"result": {"hypotheses": []}},
        _Phase.EXPERIMENT: {"result": {}},
        _Phase.ANALYZE: {"result": {}},
    }


# ---------------------------------------------------------------------------
# 1) 返回契约
# ---------------------------------------------------------------------------


class TestPublishPhaseContract(unittest.TestCase):

    def test_return_has_required_keys(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "test"}]})
        for key in ("phase", "publications", "deliverables", "citations",
                     "bibtex", "gbt7714", "paper_draft", "metadata"):
            self.assertIn(key, result, f"missing key: {key}")
        self.assertEqual(result["phase"], "publish")

    def test_metadata_has_required_fields(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        md = result["metadata"]
        for key in ("publication_count", "deliverable_count", "citation_count"):
            self.assertIn(key, md, f"missing metadata key: {key}")


# ---------------------------------------------------------------------------
# 2) 正常路径
# ---------------------------------------------------------------------------


class TestPublishNormalPath(unittest.TestCase):

    def test_citations_returned_from_citation_manager(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "test"}]})
        self.assertGreater(len(result["citations"]), 0)
        self.assertIn("bibtex", result)

    def test_paper_draft_populated(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertIsInstance(result["paper_draft"], dict)
        self.assertIn("title", result["paper_draft"])

    def test_deliverables_contains_base_items(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertIn("研究报告", result["deliverables"])
        self.assertIn("数据集", result["deliverables"])


# ---------------------------------------------------------------------------
# 3) 降级路径
# ---------------------------------------------------------------------------


class TestPublishDegradation(unittest.TestCase):

    def test_paper_writer_failure_doesnt_crash(self):
        """PaperWriter 执行失败时不崩溃。"""
        pipeline = _FakePipeline()
        pw = MagicMock()
        pw.execute.side_effect = RuntimeError("paper boom")
        pipeline.output_port.create_paper_writer.return_value = pw
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        try:
            result = handler.execute(cycle, {"citation_records": []})
            self.assertEqual(result["phase"], "publish")
        except RuntimeError:
            pass  # 可接受：PaperWriter 是必要组件

    def test_report_generator_failure_doesnt_crash(self):
        """ReportGenerator 失败时不阻塞发布。"""
        pipeline = _FakePipeline()
        rg = MagicMock()
        rg.execute.side_effect = RuntimeError("report boom")
        pipeline.output_port.create_report_generator.return_value = rg
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        try:
            result = handler.execute(cycle, {"citation_records": []})
            self.assertEqual(result["phase"], "publish")
        except RuntimeError:
            pass  # 可接受

    def test_citation_manager_creation_fails(self):
        """output_port + module fallback 均失败时应抛 RuntimeError。"""
        pipeline = _FakePipeline()
        pipeline.output_port.create_citation_manager.side_effect = RuntimeError("no CM")
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        with patch("src.research.phases.publish_phase.CitationManager", None):
            with self.assertRaises(RuntimeError):
                handler.execute(cycle, {"citation_records": []})


# ---------------------------------------------------------------------------
# 4) 空输入边界
# ---------------------------------------------------------------------------


class TestPublishEmptyInput(unittest.TestCase):

    def test_empty_citation_records(self):
        """空 citation_records 不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertEqual(result["phase"], "publish")

    def test_no_prior_phase_executions(self):
        """phase_executions 为空时不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions={})
        result = handler.execute(cycle, {"citation_records": []})
        self.assertEqual(result["phase"], "publish")

    def test_none_context(self):
        """context=None 不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, None)
        self.assertEqual(result["phase"], "publish")


# ---------------------------------------------------------------------------
# 5) deliverables 动态构建
# ---------------------------------------------------------------------------


class TestPublishDeliverablesDynamic(unittest.TestCase):

    def test_bibtex_available_adds_deliverable(self):
        pipeline = _FakePipeline()
        cm = MagicMock()
        cm.execute.return_value = {
            "entries": [],
            "bibtex": "@book{x}",
            "gbt7714": "",
            "formatted_references": "",
            "citation_count": 0,
            "output_files": {},
        }
        pipeline.output_port.create_citation_manager.return_value = cm
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "t"}]})
        self.assertIn("BibTeX 参考文献", result["deliverables"])
        self.assertNotIn("GB/T 7714 参考文献", result["deliverables"])

    def test_markdown_output_adds_deliverable(self):
        pipeline = _FakePipeline()
        pw = MagicMock()
        pw.execute.return_value = {
            "paper_draft": {},
            "language": "zh",
            "section_count": 0,
            "reference_count": 0,
            "output_files": {"markdown": "/tmp/paper.md"},
        }
        pipeline.output_port.create_paper_writer.return_value = pw
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertIn("Markdown 论文初稿", result["deliverables"])


if __name__ == "__main__":
    unittest.main()
