import json
import os
import tempfile
import unittest
from pathlib import Path

from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
from src.core.algorithm_optimizer import AlgorithmOptimizer
from src.learning.adaptive_tuner import AdaptiveTuner
from src.learning.pattern_recognizer import PatternRecognizer
from src.learning.self_learning_engine import SelfLearningEngine


class TestOptimizationAndLearningFeatures(unittest.TestCase):
    def test_algorithm_optimizer_can_select_and_benchmark(self):
        optimizer = AlgorithmOptimizer(exploration_c=1.0, config={"export_contract_version": "d38.v1"})

        def fast_algo(context):
            return {"quality_score": 0.7, "result": "fast"}

        def accurate_algo(context):
            return {"quality_score": 0.9, "result": "accurate"}

        optimizer.register("fast", fast_algo, tags=["text"])
        optimizer.register("accurate", accurate_algo, tags=["text"])

        name, result = optimizer.run_best({"x": 1}, candidate_tags=["text"])
        self.assertIn(name, {"fast", "accurate"})
        self.assertIn("quality_score", result)

        report = optimizer.benchmark({"x": 1}, candidate_tags=["text"])
        self.assertIn(report["winner"], {"fast", "accurate"})
        self.assertEqual(set(report["results"].keys()), {"fast", "accurate"})
        self.assertIn("analysis_summary", report)
        self.assertIn("report_metadata", report)

        summary = optimizer.get_optimization_summary()
        self.assertEqual(summary["analysis_summary"]["status"], "stable")
        self.assertEqual(
            [phase["phase"] for phase in summary["metadata"]["phase_history"][:2]],
            ["run_best", "invoke_algorithm"],
        )
        self.assertEqual(summary["report_metadata"]["contract_version"], "d38.v1")
        self.assertEqual(summary["report_metadata"]["final_status"], "completed")

    def test_algorithm_optimizer_tracks_failed_operations(self):
        optimizer = AlgorithmOptimizer(config={"export_contract_version": "d38.v1"})

        def failing_algo(context):
            raise RuntimeError("boom")

        optimizer.register("failing", failing_algo, tags=["text"])

        with self.assertRaises(RuntimeError):
            optimizer.run_best({"x": 1}, candidate_tags=["text"])

        summary = optimizer.get_optimization_summary()
        self.assertEqual(summary["analysis_summary"]["failed_operation_count"], 2)
        self.assertEqual(summary["analysis_summary"]["status"], "needs_followup")
        self.assertIn(summary["analysis_summary"]["failed_phase"], {"invoke_algorithm", "run_best"})
        self.assertEqual(summary["failed_operations"][0]["operation"], "invoke_algorithm")
        self.assertIn("details", summary["failed_operations"][0])

    def test_algorithm_optimizer_export_uses_json_safe_contract(self):
        optimizer = AlgorithmOptimizer(config={"export_contract_version": "d38.v1"})

        def stable_algo(context):
            return {"quality_score": 0.88, "result": "stable"}

        optimizer.register("stable", stable_algo, tags=["text"])
        optimizer.benchmark({"x": 1}, candidate_tags=["text"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "optimizer-report.json")
            exported = optimizer.export_optimization_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d38.v1")
        self.assertEqual(payload["optimizer_summary"]["profiles"]["stable"]["name"], "stable")
        self.assertIn("report_metadata", payload["optimizer_summary"])

    def test_algorithm_optimizer_cleanup_resets_runtime_state(self):
        optimizer = AlgorithmOptimizer(config={"export_contract_version": "d38.v1"})

        def stable_algo(context):
            return {"quality_score": 0.88, "result": "stable"}

        optimizer.register("stable", stable_algo, tags=["text"])
        optimizer.run_best({"x": 1}, candidate_tags=["text"])

        cleaned = optimizer.cleanup()
        summary = optimizer.get_optimization_summary()

        self.assertTrue(cleaned)
        self.assertEqual(summary["analysis_summary"]["status"], "idle")
        self.assertEqual(summary["analysis_summary"]["total_calls"], 0)
        self.assertEqual(summary["metadata"]["final_status"], "cleaned")

    def test_pattern_recognizer_detects_patterns(self):
        recognizer = PatternRecognizer(min_frequency=2, anomaly_z_threshold=2.0)
        for _ in range(12):
            recognizer.analyze(
                {
                    "topic": "伤寒论",
                    "entities": [{"name": "桂枝汤", "type": "formula", "confidence": 0.9}],
                    "performance_score": 0.8,
                    "confidence_score": 0.85,
                }
            )

        patterns = recognizer.analyze(
            {
                "topic": "伤寒论",
                "entities": [{"name": "桂枝汤", "type": "formula", "confidence": 0.95}],
                "performance_score": 0.82,
                "confidence_score": 0.87,
            }
        )
        self.assertTrue(len(patterns) > 0)

    def test_adaptive_tuner_updates_parameters(self):
        tuner = AdaptiveTuner(performance_target=0.8)
        last = None
        for _ in range(20):
            last = tuner.step({"performance": 0.6, "quality": 0.6, "confidence": 0.6})

        self.assertIsNotNone(last)
        if last is None:
            self.fail("tuner.step did not return parameter dict")
        self.assertIn("learning_threshold", last)
        self.assertTrue(0.4 <= last["learning_threshold"] <= 0.9)
        self.assertGreaterEqual(len(tuner.get_update_log()), 1)

    def test_multimodal_fusion_produces_confidence(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.ATTENTION)
        context = {
            "processed_text": "桂枝汤用于太阳中风证。",
            "entities": [
                {"name": "桂枝汤", "type": "formula", "confidence": 0.92},
                {"name": "桂枝", "type": "herb", "confidence": 0.88},
            ],
            "semantic_graph": {
                "nodes": [{"id": 1}, {"id": 2}],
                "edges": [{"source": 1, "target": 2}],
            },
            "performance_score": 0.81,
            "confidence_score": 0.86,
            "quality_score": 0.84,
        }
        modalities = engine.extract_modalities(context)
        result = engine.fuse(modalities)
        self.assertTrue(0.0 <= result.confidence <= 1.0)
        self.assertTrue(len(result.fused_features) > 0)

    def test_self_learning_engine_has_new_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = str(Path(tmp) / "learning_data.pkl")
            engine = SelfLearningEngine({"learning_data_file": data_file})
            self.assertTrue(engine.initialize({}))
            output = engine.execute(
                {
                    "processed_text": "麻黄汤主治太阳伤寒。",
                    "entities": [{"name": "麻黄汤", "type": "formula", "confidence": 0.9}],
                    "semantic_graph": {"nodes": [{"id": 1}], "edges": []},
                    "reasoning_results": {"diagnosis": "太阳伤寒"},
                    "confidence_score": 0.86,
                    "quality_score": 0.82,
                }
            )
        self.assertIn("learning_suggestions", output)
        self.assertIn("discovered_patterns", output)
        self.assertIn("tuned_parameters", output)
        self.assertIn("ewma_performance", output)


if __name__ == "__main__":
    unittest.main()
