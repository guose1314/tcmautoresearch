# tests/test_algorithm_optimizer_coverage.py
"""
AlgorithmOptimizer 覆盖率补齐测试。
目标：algorithm_optimizer.py 从 89% 提升至 ≥90%。
"""
import json
import os
import tempfile
import unittest

from src.core.algorithm_optimizer import AlgorithmOptimizer, AlgorithmProfile


def _fast_algo(context):
    return {"quality_score": 0.9, "data": "fast"}


def _slow_algo(context):
    return {"quality_score": 0.6, "data": "slow"}


def _failing_algo(context):
    raise RuntimeError("algo error")


class TestAlgorithmProfile(unittest.TestCase):
    def test_defaults(self):
        p = AlgorithmProfile(name="test")
        self.assertEqual(p.avg_time, float("inf"))
        self.assertEqual(p.avg_quality, 0.0)

    def test_ucb1_never_called(self):
        p = AlgorithmProfile(name="test")
        self.assertEqual(p.ucb1_score(10), float("inf"))

    def test_ucb1_called(self):
        p = AlgorithmProfile(name="test", call_count=5, total_quality=4.0, total_time=1.0)
        score = p.ucb1_score(20)
        self.assertIsInstance(score, float)
        self.assertGreater(score, 0)

    def test_to_dict(self):
        p = AlgorithmProfile(name="test", call_count=2, total_time=0.5, total_quality=1.6)
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertIsNotNone(d["avg_time_ms"])
        self.assertEqual(d["avg_quality"], 0.8)


class TestAlgorithmOptimizerRegistration(unittest.TestCase):
    def test_register_and_list(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo, tags=["text"])
        opt.register("slow", _slow_algo, tags=["entity"])
        self.assertEqual(sorted(opt.list_algorithms()), ["fast", "slow"])

    def test_register_overwrite(self):
        opt = AlgorithmOptimizer()
        opt.register("a", _fast_algo)
        opt.register("a", _slow_algo)
        self.assertEqual(len(opt.list_algorithms()), 1)

    def test_get_profile(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo, tags=["text"])
        p = opt.get_profile("fast")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "fast")

    def test_get_profile_missing(self):
        opt = AlgorithmOptimizer()
        self.assertIsNone(opt.get_profile("none"))

    def test_get_all_profiles(self):
        opt = AlgorithmOptimizer()
        opt.register("a", _fast_algo)
        opt.register("b", _slow_algo)
        profiles = opt.get_all_profiles()
        self.assertEqual(len(profiles), 2)


class TestRunBest(unittest.TestCase):
    def test_no_candidates_raises(self):
        opt = AlgorithmOptimizer()
        with self.assertRaises(ValueError):
            opt.run_best({})

    def test_run_best_success(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo, tags=["text"])
        opt.register("slow", _slow_algo, tags=["text"])
        name, result = opt.run_best({})
        self.assertIn(name, ["fast", "slow"])
        self.assertIn("quality_score", result)

    def test_run_best_with_tags(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo, tags=["text"])
        opt.register("slow", _slow_algo, tags=["entity"])
        name, result = opt.run_best({}, candidate_tags=["entity"])
        self.assertEqual(name, "slow")

    def test_run_best_failure(self):
        opt = AlgorithmOptimizer()
        opt.register("bad", _failing_algo)
        with self.assertRaises(RuntimeError):
            opt.run_best({})

    def test_ucb1_explores_uncalled(self):
        """UCB1 优先探索未调用过的算法"""
        opt = AlgorithmOptimizer()
        opt.register("called", _fast_algo, tags=["t"])
        opt.register("new", _slow_algo, tags=["t"])
        # 先调用 called 几次
        for _ in range(3):
            opt.run_best({}, candidate_tags=["t"])
        # 'new' 至少会被探索一次
        p = opt.get_profile("new")
        self.assertGreater(p.call_count, 0)


class TestBenchmark(unittest.TestCase):
    def test_benchmark_all(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo)
        opt.register("slow", _slow_algo)
        report = opt.benchmark({})
        self.assertIn("winner", report)
        self.assertIn("profiles", report)
        self.assertEqual(report["winner"], "fast")

    def test_benchmark_no_candidates(self):
        opt = AlgorithmOptimizer()
        with self.assertRaises(ValueError):
            opt.benchmark({})

    def test_benchmark_with_tags(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo, tags=["text"])
        opt.register("slow", _slow_algo, tags=["entity"])
        report = opt.benchmark({}, candidate_tags=["text"])
        self.assertEqual(len(report["profiles"]), 1)


class TestExportOptimizationData(unittest.TestCase):
    def test_export_success(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo)
        opt.run_best({})
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            self.assertTrue(opt.export_optimization_data(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("report_metadata", data)
        finally:
            os.unlink(path)

    def test_export_failure(self):
        opt = AlgorithmOptimizer()
        self.assertFalse(opt.export_optimization_data("/nonexistent/dir/file.json"))


class TestAnalysisSummary(unittest.TestCase):
    def test_idle_no_calls(self):
        opt = AlgorithmOptimizer()
        s = opt._build_analysis_summary()
        self.assertEqual(s["status"], "idle")

    def test_stable_after_good_calls(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo)
        opt.run_best({})
        s = opt._build_analysis_summary()
        self.assertEqual(s["status"], "stable")

    def test_needs_followup_after_failure(self):
        opt = AlgorithmOptimizer()
        opt.register("bad", _failing_algo)
        try:
            opt.run_best({})
        except RuntimeError:
            pass
        s = opt._build_analysis_summary()
        self.assertEqual(s["status"], "needs_followup")


class TestCleanup(unittest.TestCase):
    def test_cleanup_resets(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo)
        opt.run_best({})
        self.assertTrue(opt.cleanup())
        self.assertEqual(opt.list_algorithms(), [])
        self.assertEqual(opt._total_calls, 0)


class TestGetOptimizationSummary(unittest.TestCase):
    def test_summary_structure(self):
        opt = AlgorithmOptimizer()
        opt.register("fast", _fast_algo)
        opt.run_best({})
        summary = opt.get_optimization_summary()
        self.assertIn("profiles", summary)
        self.assertIn("analysis_summary", summary)
        self.assertIn("report_metadata", summary)


if __name__ == "__main__":
    unittest.main()
