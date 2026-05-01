from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.research.phases.analyze_phase import AnalyzePhaseMixin
from src.research.tcm_reasoning import (
    PATTERN_FANGZHENG_DUIYING,
    PATTERN_JUNCHEN_ZUOSHI,
    PATTERN_SANYIN_ZHIYI,
    TCM_REASONING_CONTRACT_VERSION,
)


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


class _Pipeline:
    ResearchPhase = _Phase

    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.analysis_port = MagicMock()
        self.analysis_port.create_reasoning_engine.side_effect = RuntimeError(
            "no generic reasoning engine"
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
        self.pipeline = _Pipeline()


@dataclass
class _Cycle:
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    research_objective: str = "桂枝汤方证与三因制宜分析"


def _records() -> List[Dict[str, Any]]:
    return [
        {
            "formula": "桂枝汤",
            "syndrome": "太阳中风",
            "herbs": ["桂枝", "芍药", "甘草"],
        },
        {
            "formula": "小柴胡汤",
            "syndrome": "少阳证",
            "herbs": ["柴胡", "黄芩", "半夏"],
        },
    ]


def _relationships() -> List[Dict[str, Any]]:
    return [
        {
            "source": "咳嗽",
            "source_type": "symptom",
            "target": "风寒袭肺",
            "target_type": "syndrome",
            "type": "表现为",
        },
        {
            "source": "咳嗽",
            "source_type": "symptom",
            "target": "肺阴虚",
            "target_type": "syndrome",
            "type": "表现为",
        },
    ]


class AnalyzeTCMReasoningWiringTest(unittest.TestCase):
    def test_analyze_outputs_tcm_reasoning_trace(self) -> None:
        harness = _AnalyzeHarness()

        result = harness.execute_analyze_phase(
            _Cycle(),
            {
                "analysis_records": _records(),
                "relationships": _relationships(),
                "tcm_context_factors": ["夏季高温"],
            },
        )

        trace = result["results"]["tcm_reasoning"]
        self.assertEqual(trace["contract_version"], TCM_REASONING_CONTRACT_VERSION)
        self.assertGreater(len(trace["premises"]), 0)
        self.assertGreater(len(trace["steps"]), 0)
        self.assertIn(PATTERN_FANGZHENG_DUIYING, trace["pattern_coverage"])
        self.assertIn(PATTERN_JUNCHEN_ZUOSHI, trace["pattern_coverage"])
        self.assertIn(PATTERN_SANYIN_ZHIYI, trace["pattern_coverage"])

        metadata = result["metadata"]
        self.assertTrue(metadata["tcm_reasoning_generated"])
        self.assertEqual(
            metadata["tcm_reasoning_step_count"],
            len(trace["steps"]),
        )
        self.assertEqual(
            metadata["tcm_reasoning_contract_version"],
            TCM_REASONING_CONTRACT_VERSION,
        )
        self.assertIn("tcm_reasoning", metadata["analysis_modules"])

    def test_tcm_reasoning_can_be_disabled(self) -> None:
        harness = _AnalyzeHarness()

        result = harness.execute_analyze_phase(
            _Cycle(),
            {
                "analysis_records": _records(),
                "relationships": _relationships(),
                "run_tcm_reasoning": False,
            },
        )

        self.assertNotIn("tcm_reasoning", result["results"])
        metadata = result["metadata"]
        self.assertFalse(metadata["tcm_reasoning_generated"])
        self.assertEqual(metadata["tcm_reasoning_step_count"], 0)
        self.assertNotIn("tcm_reasoning", metadata["analysis_modules"])

    def test_graph_rag_claims_feed_tcm_reasoning_premises(self) -> None:
        harness = _AnalyzeHarness()
        graph_rag_claim = {
            "status": "applied",
            "reason": "retrieved",
            "scope": "local",
            "asset_type": "claim",
            "body": (
                "[claim:claim::cycle-1::cl-gz-1] (EvidenceClaim) "
                "claim_text=桂枝汤治疗太阳中风，方含桂枝、芍药、甘草；"
                "relation_type=supports；confidence=0.88"
            ),
            "citations": [
                {
                    "type": "EvidenceClaim",
                    "id": "claim::cycle-1::cl-gz-1",
                    "asset_type": "claim",
                }
            ],
            "traceability": {
                "node_ids": ["claim::cycle-1::cl-gz-1"],
                "source_phase": "analyze",
                "source_phases": ["analyze"],
            },
        }

        result = harness.execute_analyze_phase(
            _Cycle(),
            {
                "analysis_records": [],
                "relationships": [],
                "enable_graph_rag": False,
                "graph_rag_context": graph_rag_claim,
            },
        )

        trace = result["results"]["tcm_reasoning"]
        self.assertIn(PATTERN_FANGZHENG_DUIYING, trace["pattern_coverage"])
        self.assertIn(PATTERN_JUNCHEN_ZUOSHI, trace["pattern_coverage"])
        graph_premises = [
            premise
            for premise in trace["premises"]
            if premise.get("claim_id") == "cl-gz-1"
        ]
        self.assertGreaterEqual(len(graph_premises), 5)
        self.assertTrue(all(p.get("source_phase") == "analyze" for p in graph_premises))
        self.assertTrue(all(p.get("confidence") == 0.88 for p in graph_premises))
        for step in trace["steps"]:
            if step["pattern"] in {PATTERN_FANGZHENG_DUIYING, PATTERN_JUNCHEN_ZUOSHI}:
                self.assertIn("cl-gz-1", step["premise_refs"])

    def test_tcm_reasoning_failure_does_not_block_analyze(self) -> None:
        harness = _AnalyzeHarness()

        with patch(
            "src.research.phases.analyze_phase.run_tcm_reasoning",
            side_effect=RuntimeError("tcm reasoning down"),
        ):
            result = harness.execute_analyze_phase(
                _Cycle(),
                {
                    "analysis_records": _records(),
                    "relationships": _relationships(),
                },
            )

        self.assertEqual(result["status"], "completed")
        trace = result["results"]["tcm_reasoning"]
        self.assertEqual(trace["degraded_reason"], "tcm_reasoning_failed")
        self.assertIn("tcm reasoning down", trace["error"])
        self.assertEqual(trace["steps"], [])

        metadata = result["metadata"]
        self.assertFalse(metadata["tcm_reasoning_generated"])
        self.assertEqual(metadata["tcm_reasoning_step_count"], 0)
        self.assertIn("tcm reasoning down", metadata["tcm_reasoning_error"])


if __name__ == "__main__":
    unittest.main()
