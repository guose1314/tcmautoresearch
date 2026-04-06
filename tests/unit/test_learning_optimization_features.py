import json
import os
import tempfile
import unittest
from pathlib import Path

from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
from src.core.algorithm_optimizer import AlgorithmOptimizer
from src.learning.adaptive_tuner import AdaptiveTuner
from src.learning.pattern_recognizer import PatternRecognizer
from src.learning.self_learning_engine import LearningRecord, SelfLearningEngine


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


# ---------------------------------------------------------------------------
# LearningRecord: phase + quality_dimensions 字段
# ---------------------------------------------------------------------------


class TestLearningRecordExtendedFields(unittest.TestCase):

    def test_to_dict_includes_phase_and_dimensions(self):
        rec = LearningRecord(
            task_id="abc",
            input_data={},
            output_data={},
            performance=0.75,
            timestamp="2026-01-01T00:00:00",
            phase="observe",
            quality_dimensions={"completeness": 0.8, "consistency": 0.7},
        )
        d = rec.to_dict()
        self.assertEqual(d["phase"], "observe")
        self.assertEqual(d["quality_dimensions"]["completeness"], 0.8)

    def test_from_dict_restores_phase_and_dimensions(self):
        data = {
            "task_id": "xyz",
            "performance": 0.6,
            "phase": "analyze",
            "quality_dimensions": {"evidence_quality": 0.9},
        }
        rec = LearningRecord.from_dict(data)
        self.assertEqual(rec.phase, "analyze")
        self.assertEqual(rec.quality_dimensions["evidence_quality"], 0.9)

    def test_to_dict_omits_none_fields(self):
        rec = LearningRecord(
            task_id="t1", input_data={}, output_data={},
            performance=0.5, timestamp="now",
        )
        d = rec.to_dict()
        self.assertNotIn("phase", d)
        self.assertNotIn("quality_dimensions", d)


# ---------------------------------------------------------------------------
# SelfLearningEngine: learn_from_quality_assessment
# ---------------------------------------------------------------------------


class TestLearnFromQualityAssessment(unittest.TestCase):

    def _make_engine(self, tmp_dir):
        data_file = str(Path(tmp_dir) / "test_learn.pkl")
        engine = SelfLearningEngine({"learning_data_file": data_file})
        engine.initialize({})
        return engine

    def test_accepts_quality_score_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)

            class FakeQS:
                overall_score = 0.85
                completeness = 0.9
                consistency = 0.8
                evidence_quality = 0.75
                grade_level = "high"

            ok = engine.learn_from_quality_assessment("observe", FakeQS())
            self.assertTrue(ok)
            self.assertEqual(len(engine.learning_records), 1)
            self.assertEqual(engine.learning_records[0].phase, "observe")
            self.assertAlmostEqual(engine.learning_records[0].performance, 0.85)
            self.assertIn("completeness", engine.learning_records[0].quality_dimensions)

    def test_accepts_dict_quality_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            qs = {
                "overall_score": 0.6,
                "completeness": 0.5,
                "consistency": 0.7,
                "evidence_quality": 0.6,
                "grade_level": "moderate",
            }
            ok = engine.learn_from_quality_assessment("hypothesis", qs)
            self.assertTrue(ok)
            rec = engine.learning_records[-1]
            self.assertEqual(rec.phase, "hypothesis")

    def test_rejects_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertFalse(engine.learn_from_quality_assessment("x", "bad"))

    def test_updates_ewma_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)

            class FakeQS:
                overall_score = 0.7
                completeness = 0.7
                consistency = 0.7
                evidence_quality = 0.7
                grade_level = "moderate"

            engine.learn_from_quality_assessment("observe", FakeQS())
            self.assertIsNotNone(engine._ewma_score)
            self.assertAlmostEqual(engine._ewma_score, 0.7)

    def test_updates_dimension_trends(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            qs = {"overall_score": 0.5, "completeness": 0.9, "consistency": 0.3, "evidence_quality": 0.4}
            engine.learn_from_quality_assessment("analyze", qs)
            engine.learn_from_quality_assessment("analyze", qs)
            trends = engine.get_dimension_trends()
            self.assertEqual(len(trends["completeness"]), 2)

    def test_logs_to_improvement_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            qs = {"overall_score": 0.5, "completeness": 0.5, "consistency": 0.5, "evidence_quality": 0.5}
            engine.learn_from_quality_assessment("publish", qs)
            entry = engine.model_improvement_log[-1]
            self.assertEqual(entry["type"], "quality_assessment")
            self.assertEqual(entry["phase"], "publish")


# ---------------------------------------------------------------------------
# SelfLearningEngine: learn_from_cycle_reflection
# ---------------------------------------------------------------------------


class TestLearnFromCycleReflection(unittest.TestCase):

    def _make_engine(self, tmp_dir):
        data_file = str(Path(tmp_dir) / "test_cycle.pkl")
        engine = SelfLearningEngine({"learning_data_file": data_file})
        engine.initialize({})
        return engine

    def _make_assessment(self, overall=0.65, weak_score=0.35, strong_score=0.9):
        from src.quality.quality_assessor import QualityScore
        return {
            "phase_assessments": [
                {"phase": "observe", "score": QualityScore(overall_score=strong_score, completeness=0.9, consistency=0.8, evidence_quality=0.85, grade_level="high")},
                {"phase": "analyze", "score": QualityScore(overall_score=weak_score, completeness=0.3, consistency=0.4, evidence_quality=0.2, grade_level="very_low")},
            ],
            "weaknesses": [{"phase": "analyze", "score": weak_score, "grade": "very_low", "issues": ["missing required: status"]}],
            "strengths": [{"phase": "observe", "score": strong_score, "grade": "high"}],
            "overall_cycle_score": overall,
        }

    def test_records_all_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(self._make_assessment())
            self.assertIn("observe", summary["recorded_phases"])
            self.assertIn("analyze", summary["recorded_phases"])
            self.assertEqual(len(engine.learning_records), 2)

    def test_identifies_weak_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(self._make_assessment())
            self.assertEqual(len(summary["weak_phases"]), 1)
            self.assertEqual(summary["weak_phases"][0]["phase"], "analyze")

    def test_generates_improvement_priorities(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(self._make_assessment())
            self.assertGreaterEqual(len(summary["improvement_priorities"]), 1)
            self.assertTrue(any("紧急" in p for p in summary["improvement_priorities"]))

    def test_cycle_trend_insufficient_data_initially(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(self._make_assessment())
            self.assertEqual(summary["cycle_trend"], "insufficient_data")

    def test_cycle_trend_after_multiple_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            # 注入历史循环日志
            for score in [0.4, 0.45, 0.5]:
                engine.model_improvement_log.append({
                    "type": "cycle_reflection",
                    "overall_score": score,
                })
            summary = engine.learn_from_cycle_reflection(self._make_assessment(overall=0.7))
            self.assertIn(summary["cycle_trend"], ("improving", "stable", "declining"))
            self.assertNotEqual(summary["cycle_trend"], "insufficient_data")

    def test_empty_assessment_returns_safe_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            summary = engine.learn_from_cycle_reflection({})
            self.assertEqual(summary["recorded_phases"], [])
            self.assertEqual(summary["weak_phases"], [])

    def test_logs_cycle_reflection_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine.learn_from_cycle_reflection(self._make_assessment())
            entries = [e for e in engine.model_improvement_log if e.get("type") == "cycle_reflection"]
            self.assertGreaterEqual(len(entries), 1)


# ---------------------------------------------------------------------------
# SelfLearningEngine: get_phase_performance
# ---------------------------------------------------------------------------


class TestGetPhasePerformance(unittest.TestCase):

    def test_no_records_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = str(Path(tmp) / "p.pkl")
            engine = SelfLearningEngine({"learning_data_file": data_file})
            engine.initialize({})
            result = engine.get_phase_performance("observe")
            self.assertEqual(result["record_count"], 0)

    def test_aggregates_phase_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_file = str(Path(tmp) / "p.pkl")
            engine = SelfLearningEngine({"learning_data_file": data_file})
            engine.initialize({})
            qs = {"overall_score": 0.8, "completeness": 0.9, "consistency": 0.7, "evidence_quality": 0.6}
            engine.learn_from_quality_assessment("observe", qs)
            qs2 = {"overall_score": 0.6, "completeness": 0.5, "consistency": 0.5, "evidence_quality": 0.5}
            engine.learn_from_quality_assessment("observe", qs2)
            result = engine.get_phase_performance("observe")
            self.assertEqual(result["record_count"], 2)
            self.assertAlmostEqual(result["avg_score"], 0.7)
            self.assertIn("completeness", result["avg_dimensions"])


if __name__ == "__main__":
    unittest.main()
