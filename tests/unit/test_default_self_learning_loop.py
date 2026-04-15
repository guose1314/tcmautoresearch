from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from src.learning.self_learning_engine import SelfLearningEngine
from src.research.phases.reflect_phase import ReflectPhaseMixin
from src.research.research_pipeline import ResearchPipeline


@dataclass
class _Cycle:
    outcomes: List[Dict[str, Any]] = field(default_factory=list)


class _ReflectHost(ReflectPhaseMixin):
    def __init__(self, pipeline: ResearchPipeline):
        self.pipeline = pipeline


def _full_outcome(phase: str = "observe") -> Dict[str, Any]:
    return {
        "phase": phase,
        "result": {
            "status": "completed",
            "phase": phase,
            "results": {"score": 0.9},
            "artifacts": ["paper.pdf"],
            "metadata": {"v": 1},
            "error": None,
        },
    }


def _cycle_assessment() -> Dict[str, Any]:
    return {
        "phase_assessments": [
            {
                "phase": "observe",
                "score": {
                    "overall_score": 0.82,
                    "completeness": 0.8,
                    "consistency": 0.78,
                    "evidence_quality": 0.84,
                    "grade_level": "high",
                },
            }
        ],
        "weaknesses": [],
        "strengths": [{"phase": "observe", "score": 0.82, "grade": "high"}],
        "overall_cycle_score": 0.82,
    }


class TestDefaultSelfLearningLoop(unittest.TestCase):
    def test_default_pipeline_self_learning_feeds_reflect_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = str(Path(tmp) / "learning.pkl")
            pipeline = ResearchPipeline(
                {
                    "self_learning": {
                        "enabled": True,
                        "learning_data_file": data_file,
                    }
                }
            )
            try:
                result = _ReflectHost(pipeline).execute_reflect_phase(
                    _Cycle(outcomes=[_full_outcome()]),
                    {},
                )
            finally:
                pipeline.cleanup()

        self.assertTrue(result["metadata"]["learning_fed"])
        self.assertIsInstance(result["learning_summary"], dict)
        self.assertIn("tuned_parameters", result["learning_summary"])

    def test_pipeline_restores_persisted_learning_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = str(Path(tmp) / "learning.pkl")
            engine = SelfLearningEngine({"learning_data_file": data_file})
            self.assertTrue(engine.initialize({}))
            self.assertIsNotNone(engine._adaptive_tuner)
            engine.learn_from_cycle_reflection(_cycle_assessment())
            engine._adaptive_tuner.set_parameter("max_concurrent_tasks", 6)
            engine._adaptive_tuner.set_parameter("quality_threshold", 0.74)
            engine.cleanup()

            pipeline = ResearchPipeline(
                {
                    "self_learning": {
                        "enabled": True,
                        "learning_data_file": data_file,
                    }
                }
            )
            try:
                strategy = pipeline.get_learning_strategy()
                previous_feedback = pipeline.get_previous_iteration_feedback()
                self.assertEqual(strategy["tuned_parameters"]["max_concurrent_tasks"], 6.0)
                self.assertAlmostEqual(strategy["tuned_parameters"]["quality_threshold"], 0.74)
                self.assertEqual(
                    previous_feedback["learning_summary"]["tuned_parameters"]["max_concurrent_tasks"],
                    6.0,
                )
                self.assertAlmostEqual(
                    pipeline._governance_config["minimum_stable_completion_rate"],
                    0.74,
                )
                self.assertEqual(pipeline.executor._max_workers, 6)
            finally:
                pipeline.cleanup()
