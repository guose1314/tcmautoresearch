from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict

from src.research.phase_handlers.experiment_execution_handler import (
    ExperimentExecutionPhaseHandler,
)


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


@dataclass
class _FakeCycle:
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)


class _FakePipeline:
    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self._learning_phase_manifests: list = []

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)


def _make_handler(pipeline=None):
    return ExperimentExecutionPhaseHandler(pipeline or _FakePipeline())


def _minimal_phase_executions():
    return {
        _Phase.EXPERIMENT: {
            "result": {
                "phase": "experiment",
                "status": "completed",
                "results": {
                    "protocol_design": {
                        "hypothesis_id": "hyp-1",
                        "protocol_source": "template",
                    },
                    "selected_hypothesis": {
                        "hypothesis_id": "hyp-1",
                        "title": "四君子汤改善脾气虚证",
                    },
                    "study_protocol": {
                        "protocol_source": "template",
                    },
                },
                "metadata": {"protocol_source": "template"},
                "error": None,
            }
        }
    }


class TestExperimentExecutionLearningStrategy(unittest.TestCase):

    def test_learning_strategy_filters_low_confidence_execution_relationships(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())

        result = handler.execute(
            cycle,
            {
                "analysis_records": [
                    {"formula": "四君子汤", "syndrome": "脾气虚证", "herbs": ["党参", "白术"]},
                ],
                "analysis_relationships": [
                    {
                        "source": "四君子汤",
                        "target": "党参",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.62, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": "四君子汤",
                        "target": "白术",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.91, "source": "observe_semantic_graph"},
                    },
                ],
                "learning_strategy": {"tuned_parameters": {"confidence_threshold": 0.8}},
            },
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]["analysis_relationships"]), 1)
        self.assertEqual(result["metadata"]["imported_relationship_count"], 1)
        self.assertTrue(result["metadata"]["learning_strategy_applied"])

    def test_learning_strategy_can_disable_document_fallback_import(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())

        result = handler.execute(
            cycle,
            {
                "documents": [
                    {
                        "title": "外部实验记录",
                        "semantic_relationships": [
                            {
                                "source": "四君子汤",
                                "target": "党参",
                                "type": "contains",
                                "source_type": "formula",
                                "target_type": "herb",
                            },
                            {
                                "source": "四君子汤",
                                "target": "脾气虚证",
                                "type": "targets",
                                "source_type": "formula",
                                "target_type": "syndrome",
                            },
                        ],
                    }
                ],
                "learning_strategy": {
                    "experiment_execution_allow_document_fallback_import": False,
                },
            },
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["results"]["analysis_records"], [])
        self.assertEqual(result["results"]["analysis_relationships"], [])
        self.assertEqual(len(result["results"]["documents"]), 1)
        self.assertFalse(result["metadata"]["document_fallback_import_enabled"])

    def test_learning_strategy_limits_execution_import_volume(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())

        result = handler.execute(
            cycle,
            {
                "analysis_records": [
                    {"formula": "四君子汤", "syndrome": "脾气虚证", "herbs": ["党参", "白术"]},
                    {"formula": "补中益气汤", "syndrome": "中气下陷", "herbs": ["黄芪", "人参"]},
                    {"formula": "理中汤", "syndrome": "脾胃虚寒", "herbs": ["干姜", "人参"]},
                ],
                "analysis_relationships": [
                    {
                        "source": "四君子汤",
                        "target": "党参",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.9, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": "补中益气汤",
                        "target": "黄芪",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.88, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": "理中汤",
                        "target": "干姜",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.86, "source": "observe_semantic_graph"},
                    },
                ],
                "sampling_events": [
                    {"batch": "b1", "size": 12},
                    {"batch": "b2", "size": 10},
                ],
                "learning_strategy": {
                    "experiment_execution_max_records": 2,
                    "experiment_execution_max_relationships": 2,
                    "experiment_execution_max_sampling_events": 1,
                },
            },
        )

        self.assertEqual(len(result["results"]["analysis_records"]), 2)
        self.assertEqual(len(result["results"]["analysis_relationships"]), 2)
        self.assertEqual(len(result["results"]["sampling_events"]), 1)
        self.assertEqual(result["metadata"]["imported_record_count"], 2)
        self.assertEqual(result["metadata"]["sampling_event_count"], 1)


if __name__ == "__main__":
    unittest.main()