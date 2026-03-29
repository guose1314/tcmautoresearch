import unittest
from importlib.util import find_spec

from src.core import __all__ as core_all
from src.cycle.iteration_cycle import IterationConfig, IterationCycle
from src.cycle.test_driven_iteration import TestDrivenIterationManager


class TestCoreAndCycleQuality(unittest.TestCase):
    def test_core_exports_are_unique(self):
        self.assertEqual(len(core_all), len(set(core_all)))

    def test_iteration_cycle_reuses_global_executor(self):
        c1 = IterationCycle(IterationConfig(max_concurrent_tasks=2))
        c2 = IterationCycle(IterationConfig(max_concurrent_tasks=2))
        self.assertIs(c1.executor, c2.executor)

    def test_iteration_cycle_executor_with_different_max_concurrent_tasks(self):
        c1 = IterationCycle(IterationConfig(max_concurrent_tasks=1))
        c2 = IterationCycle(IterationConfig(max_concurrent_tasks=3))
        self.assertIsNotNone(c1.executor)
        self.assertIsNotNone(c2.executor)
    def test_iteration_manager_framework_registry_contains_expected_frameworks(self):
        manager = TestDrivenIterationManager()
        self.assertIn("unittest", manager.test_frameworks)
        self.assertIn("custom", manager.test_frameworks)

        has_pytest = find_spec("pytest") is not None
        if has_pytest:
            self.assertIn("pytest", manager.test_frameworks)

    def test_iteration_cycle_optimization_generates_ranked_actions(self):
        cycle = IterationCycle(
            IterationConfig(
                optimization_quality_threshold=0.8,
                optimization_confidence_threshold=0.8,
                max_optimization_actions=3,
            )
        )

        result = cycle.optimize_process(
            {
                "quality_metrics": {"quality_score": 0.62},
                "confidence_scores": {"entity": 0.71, "reasoning": 0.69},
            }
        )

        self.assertEqual(result["optimization_status"], "optimization_required")
        self.assertEqual(len(result["optimization_actions"]), 2)
        self.assertEqual(result["optimization_actions"][0]["priority"], "high")
        self.assertEqual(result["optimization_actions"][1]["priority"], "medium")
        self.assertEqual(result["optimization_summary"]["highest_priority"], "high")
        self.assertAlmostEqual(result["optimization_summary"]["quality_threshold"], 0.8)

    def test_iteration_cycle_optimization_handles_empty_analysis_results(self):
        cycle = IterationCycle(IterationConfig())

        result = cycle.optimize_process({})

        self.assertEqual(result["optimization_status"], "no_action_needed")
        self.assertEqual(result["optimization_actions"], [])
        self.assertEqual(result["optimization_summary"]["action_count"], 0)
        self.assertEqual(result["optimization_summary"]["highest_priority"], "none")

    def test_iteration_cycle_optimization_respects_max_actions(self):
        cycle = IterationCycle(
            IterationConfig(
                optimization_quality_threshold=0.9,
                optimization_confidence_threshold=0.95,
                max_optimization_actions=1,
            )
        )

        result = cycle.optimize_process(
            {
                "quality_metrics": {"quality_score": 0.6},
                "confidence_scores": {"entity": 0.7, "reasoning": 0.75},
            }
        )

        self.assertEqual(len(result["optimization_actions"]), 1)
        self.assertEqual(result["optimization_actions"][0]["action"], "process_optimization")


if __name__ == "__main__":
    unittest.main()
