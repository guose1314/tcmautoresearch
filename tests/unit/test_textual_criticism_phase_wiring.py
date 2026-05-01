from __future__ import annotations

import logging
import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.research.phase_result import build_phase_result
from src.research.phases.analyze_phase import AnalyzePhaseMixin
from src.research.phases.observe_phase import ObservePhaseMixin
from src.research.textual_criticism import (
    AUTHENTICITY_AUTHENTIC,
    VERDICT_CONTRACT_VERSION,
    assess_catalog_batch,
    build_textual_criticism_summary,
    normalize_authenticity_verdicts,
)


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


class _ObservePipeline:
    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger("test_textual_criticism_observe")
        self.knowledge_graph = None


class _ObserveHarness(ObservePhaseMixin):
    def __init__(self, ingestion_result: Dict[str, Any]) -> None:
        self.pipeline = _ObservePipeline()
        self._ingestion_result = ingestion_result

    def _collect_observe_corpus_if_enabled(
        self,
        _context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"documents": [{"urn": "doc-shanghan", "title": "宋本伤寒论"}]}

    def _run_observe_literature_if_enabled(self, _context: Dict[str, Any]) -> None:
        return None

    def _run_observe_ingestion_if_enabled(
        self,
        _corpus_result: Dict[str, Any],
        _context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._ingestion_result

    def _run_observe_collation_if_enabled(
        self,
        _corpus_result: Dict[str, Any],
        _ingestion_result: Dict[str, Any],
        _context: Dict[str, Any],
    ) -> None:
        return None

    def _build_observe_philology_artifacts(
        self,
        _ingestion_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return []

    def _build_observe_graph_assets(
        self,
        _cycle_id: str,
        _ingestion_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {}

    def _build_observe_metadata(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {}

    def _append_corpus_observe_updates(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _append_ingestion_observe_updates(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _append_literature_observe_updates(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _append_collation_observe_updates(self, *args: Any, **kwargs: Any) -> None:
        return None


@dataclass
class _ObserveCycle:
    cycle_id: str = "cycle-textual"
    research_objective: str = "伤寒论少阳证治考据"
    description: str = ""
    cycle_name: str = ""


class _AnalyzePipeline:
    ResearchPhase = _Phase

    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.analysis_port = MagicMock()
        self.analysis_port.create_reasoning_engine.side_effect = RuntimeError(
            "no engine"
        )
        self._learning_phase_manifests: list[Dict[str, Any]] = []

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)


class _AnalyzeHarness(AnalyzePhaseMixin):
    _RELATION_SOURCE_PRIORITY = {
        "observe_reasoning_engine": 3,
        "observe_semantic_graph": 2,
        "pipeline_hypothesis_context": 1,
    }

    def __init__(self) -> None:
        self.pipeline = _AnalyzePipeline()


@dataclass
class _AnalyzeCycle:
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    research_objective: str = "伤寒论少阳证治考据"


def _catalog_ingestion_result() -> Dict[str, Any]:
    return {
        "documents": [
            {
                "urn": "doc-shanghan",
                "title": "宋本伤寒论",
                "metadata": {
                    "version_metadata": {
                        "catalog_id": "catalog::shanghanlun",
                        "work_title": "伤寒论",
                        "dynasty": "东汉",
                        "author": "张机",
                        "citation_refs": ["ctext:shanghanlun"],
                        "witness_key": "witness:song-edition",
                    }
                },
            }
        ],
        "processed_document_count": 1,
        "aggregate": {},
    }


def _sample_records() -> List[Dict[str, Any]]:
    return [
        {"formula": "小柴胡汤", "syndrome": "少阳", "herbs": ["柴胡", "黄芩", "半夏"]},
        {
            "formula": "桂枝汤",
            "syndrome": "太阳中风",
            "herbs": ["桂枝", "芍药", "甘草"],
        },
    ]


class ObserveTextualCriticismWiringTest(unittest.TestCase):
    def test_observe_outputs_textual_criticism_payload(self) -> None:
        harness = _ObserveHarness(_catalog_ingestion_result())

        result = harness.execute_observe_phase(_ObserveCycle(), {})

        textual_criticism = result["results"]["textual_criticism"]
        verdicts = textual_criticism["verdicts"]
        self.assertEqual(
            textual_criticism["contract_version"], VERDICT_CONTRACT_VERSION
        )
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0]["catalog_id"], "catalog::shanghanlun")
        self.assertEqual(verdicts[0]["authenticity"], AUTHENTICITY_AUTHENTIC)
        self.assertIn("ctext:shanghanlun", verdicts[0]["citation_refs"])
        self.assertIn("witness:song-edition", verdicts[0]["witness_keys"])
        self.assertEqual(textual_criticism["summary"]["verdict_count"], 1)
        self.assertGreaterEqual(textual_criticism["summary"]["citation_ref_count"], 3)
        self.assertEqual(textual_criticism["summary"]["witness_key_count"], 1)

        metadata = result["metadata"]
        self.assertTrue(metadata["textual_criticism_generated"])
        self.assertEqual(metadata["textual_criticism_verdict_count"], 1)
        self.assertEqual(
            metadata["textual_criticism_contract_version"], VERDICT_CONTRACT_VERSION
        )

    def test_textual_criticism_failure_does_not_block_observe(self) -> None:
        harness = _ObserveHarness(_catalog_ingestion_result())

        with patch(
            "src.research.phases.observe_phase.assess_catalog_batch",
            side_effect=RuntimeError("criticism service down"),
        ):
            result = harness.execute_observe_phase(_ObserveCycle(), {})

        self.assertEqual(result["status"], "completed")
        textual_criticism = result["results"]["textual_criticism"]
        self.assertEqual(textual_criticism["verdicts"], [])
        self.assertEqual(
            textual_criticism["degraded_reason"], "textual_criticism_failed"
        )
        self.assertIn("criticism service down", textual_criticism["error"])

        metadata = result["metadata"]
        self.assertFalse(metadata["textual_criticism_generated"])
        self.assertEqual(
            metadata["textual_criticism_degraded_reason"],
            "textual_criticism_failed",
        )


class AnalyzeTextualCriticismWiringTest(unittest.TestCase):
    def test_analyze_consumes_observe_textual_criticism(self) -> None:
        raw_verdicts = assess_catalog_batch(
            [
                {
                    "catalog_id": "catalog::shanghanlun",
                    "work_title": "伤寒论",
                    "dynasty": "东汉",
                    "author": "张机",
                    "citation_refs": ["ctext:shanghanlun"],
                    "witness_key": "witness:song-edition",
                }
            ]
        )
        verdicts = normalize_authenticity_verdicts(raw_verdicts)
        observe_textual_criticism = {
            "verdicts": verdicts,
            "summary": build_textual_criticism_summary(verdicts),
            "contract_version": VERDICT_CONTRACT_VERSION,
        }
        observe_result = build_phase_result(
            "observe",
            results={"textual_criticism": observe_textual_criticism},
        )
        cycle = _AnalyzeCycle(
            phase_executions={_Phase.OBSERVE: {"result": observe_result}}
        )
        harness = _AnalyzeHarness()

        result = harness.execute_analyze_phase(
            cycle,
            {"analysis_records": _sample_records()},
        )

        textual_criticism = result["results"]["textual_criticism"]
        self.assertEqual(
            textual_criticism["contract_version"], VERDICT_CONTRACT_VERSION
        )
        self.assertEqual(textual_criticism["summary"]["verdict_count"], 1)
        self.assertEqual(
            result["results"]["textual_criticism_summary"]["verdict_count"], 1
        )
        self.assertEqual(textual_criticism["source_phase"], "observe")
        self.assertIn(
            "ctext:shanghanlun",
            textual_criticism["verdicts"][0]["citation_refs"],
        )
        self.assertIn(
            "witness:song-edition",
            textual_criticism["verdicts"][0]["witness_keys"],
        )

        metadata = result["metadata"]
        self.assertTrue(metadata["textual_criticism_consumed"])
        self.assertEqual(metadata["textual_criticism_verdict_count"], 1)
        self.assertIn("textual_criticism", metadata["analysis_modules"])


if __name__ == "__main__":
    unittest.main()
