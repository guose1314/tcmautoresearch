# tests/test_module_base_coverage.py
"""
BaseModule / AsyncBaseModule 覆盖率补齐测试。
目标：module_base.py 从 75% 提升至 ≥90%。
"""
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.core.module_base import AsyncBaseModule, BaseModule, get_global_executor


class _StubModule(BaseModule):
    """最小可用的 BaseModule 具体子类。"""
    def __init__(self, config=None, *, init_ok=True, exec_result=None, cleanup_ok=True):
        super().__init__("stub_module", config)
        self._init_ok = init_ok
        self._exec_result = exec_result or {"success": True}
        self._cleanup_ok = cleanup_ok

    def _do_initialize(self) -> bool:
        return self._init_ok

    def _do_execute(self, context):
        if context.get("raise"):
            raise RuntimeError("boom")
        return dict(self._exec_result)

    def _do_cleanup(self) -> bool:
        if not self._cleanup_ok:
            raise RuntimeError("cleanup fail")
        return self._cleanup_ok


class _AsyncStubModule(AsyncBaseModule):
    def __init__(self, config=None, *, exec_result=None):
        super().__init__("async_stub", config)
        self._exec_result = exec_result or {"success": True}

    def _do_initialize(self):
        return True

    def _do_execute(self, context):
        if context.get("raise"):
            raise RuntimeError("async boom")
        return dict(self._exec_result)

    def _do_cleanup(self):
        return True


# ============================================================
# BaseModule 生命周期
# ============================================================
class TestBaseModuleLifecycle(unittest.TestCase):
    def test_init_success(self):
        m = _StubModule()
        self.assertTrue(m.initialize())
        self.assertTrue(m.initialized)
        self.assertEqual(m.status, "initialized")

    def test_init_failure(self):
        m = _StubModule(init_ok=False)
        self.assertFalse(m.initialize())
        self.assertFalse(m.initialized)

    def test_init_with_config_update(self):
        m = _StubModule()
        self.assertTrue(m.initialize({"extra_key": 42}))
        self.assertEqual(m.config["extra_key"], 42)

    def test_execute_not_initialized_raises(self):
        m = _StubModule()
        with self.assertRaises(RuntimeError):
            m.execute({"key": "val"})

    def test_execute_success(self):
        m = _StubModule(exec_result={"success": True, "quality_score": 0.95})
        m.initialize()
        result = m.execute({"key": "val"})
        self.assertTrue(result["success"])
        self.assertEqual(m.metrics["execution_count"], 1)

    def test_execute_failure_propagates(self):
        m = _StubModule()
        m.initialize()
        with self.assertRaises(RuntimeError):
            m.execute({"raise": True})
        self.assertFalse(m.metrics["last_success"])

    def test_cleanup_success(self):
        m = _StubModule()
        m.initialize()
        m.execute({"key": "val"})
        self.assertTrue(m.cleanup())
        self.assertFalse(m.initialized)
        self.assertEqual(m.status, "cleaned")
        self.assertEqual(m.metrics["execution_count"], 0)
        self.assertEqual(m.final_status, "cleaned")

    def test_cleanup_failure(self):
        m = _StubModule(cleanup_ok=False)
        m.initialize()
        self.assertFalse(m.cleanup())
        self.assertEqual(m.status, "error")


# ============================================================
# 指标更新 (_update_metrics)
# ============================================================
class TestUpdateMetrics(unittest.TestCase):
    def setUp(self):
        self.m = _StubModule()
        self.m.initialize()

    def test_quality_score_averaging(self):
        self.m.execute({"key": "v"})  # default success=True, no quality_score
        self.m._exec_result = {"success": True, "quality_score": 0.8}
        self.m.execute({"key": "v"})
        # quality_score 应当把两次调用做加权平均
        self.assertGreater(self.m.metrics["quality_score"], 0)

    def test_performance_score_update(self):
        self.m._exec_result = {"success": True, "performance_score": 0.7}
        self.m.execute({"key": "v"})
        self.assertAlmostEqual(self.m.metrics["performance_score"], 0.7, places=2)

    def test_academic_relevance_update(self):
        self.m._exec_result = {"success": True, "academic_relevance": 0.9}
        self.m.execute({"key": "v"})
        self.assertAlmostEqual(self.m.metrics["academic_relevance"], 0.9, places=2)

    def test_non_dict_result_does_not_crash(self):
        # _update_metrics 检查 isinstance(result, dict)
        self.m._update_metrics("not a dict", 0.1)
        self.assertFalse(self.m.metrics["last_success"])


# ============================================================
# 执行历史 (_record_execution_history)
# ============================================================
class TestRecordExecutionHistory(unittest.TestCase):
    def test_history_capped_at_100(self):
        m = _StubModule()
        m.initialize()
        for _ in range(110):
            m.execute({"key": "v"})
        self.assertLessEqual(len(m.performance_history), 100)

    def test_history_entry_structure(self):
        m = _StubModule()
        m.initialize()
        m.execute({"key": "v"})
        entry = m.performance_history[0]
        self.assertIn("timestamp", entry)
        self.assertIn("module", entry)
        self.assertIn("execution_time", entry)
        self.assertIn("success", entry)


# ============================================================
# 学术洞察 & 建议
# ============================================================
class TestAcademicInsightsAndRecommendations(unittest.TestCase):
    def test_high_quality_insight(self):
        m = _StubModule(exec_result={"success": True, "quality_score": 0.95})
        m.initialize()
        m.execute({"key": "v"})
        self.assertTrue(any(i["type"] == "high_quality" for i in m.academic_insights))

    def test_academic_value_insight(self):
        m = _StubModule(exec_result={"success": True, "academic_relevance": 0.9})
        m.initialize()
        m.execute({"key": "v"})
        self.assertTrue(any(i["type"] == "academic_value" for i in m.academic_insights))

    def test_quality_improvement_recommendation(self):
        m = _StubModule(exec_result={"success": True, "quality_score": 0.5})
        m.initialize()
        m.execute({"key": "v"})
        self.assertTrue(any(r["type"] == "quality_improvement" for r in m.recommendations))

    def test_performance_optimization_recommendation(self):
        m = _StubModule(exec_result={"success": True, "performance_score": 0.3})
        m.initialize()
        m.execute({"key": "v"})
        self.assertTrue(any(r["type"] == "performance_optimization" for r in m.recommendations))

    def test_no_recommendation_for_high_scores(self):
        m = _StubModule(exec_result={"success": True, "quality_score": 0.95, "performance_score": 0.95})
        m.initialize()
        m.execute({"key": "v"})
        self.assertEqual(len(m.recommendations), 0)


# ============================================================
# 报告 & 导出
# ============================================================
class TestReportsAndExport(unittest.TestCase):
    def test_get_metrics(self):
        m = _StubModule()
        m.initialize()
        metrics = m.get_metrics()
        self.assertEqual(metrics["module_name"], "stub_module")
        self.assertIn("report_metadata", metrics)

    def test_get_module_info(self):
        m = _StubModule(config={"version": "2.0"})
        m.initialize()
        info = m.get_module_info()
        self.assertEqual(info["version"], "2.0")
        self.assertIn("recommendations", info)

    def test_get_performance_report_empty(self):
        m = _StubModule()
        m.initialize()
        report = m.get_performance_report()
        self.assertIn("message", report)
        self.assertIn("analysis_summary", report)

    def test_get_performance_report_with_history(self):
        m = _StubModule()
        m.initialize()
        m.execute({"key": "v"})
        report = m.get_performance_report()
        self.assertIn("success_rate", report)
        self.assertIn("average_execution_time", report)

    def test_export_module_data(self):
        m = _StubModule()
        m.initialize()
        m.execute({"key": "v"})
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            self.assertTrue(m.export_module_data(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("report_metadata", data)
            self.assertIn("module_info", data)
        finally:
            os.unlink(path)

    def test_export_module_data_invalid_path(self):
        m = _StubModule()
        m.initialize()
        self.assertFalse(m.export_module_data("/nonexistent/dir/file.json"))


# ============================================================
# 健康评分
# ============================================================
class TestHealthScore(unittest.TestCase):
    def test_health_no_history(self):
        m = _StubModule()
        m.initialize()
        health = m.get_module_health()
        self.assertIn("health_score", health)
        self.assertIsInstance(health["health_score"], float)

    def test_health_with_history(self):
        m = _StubModule(exec_result={"success": True, "quality_score": 0.9})
        m.initialize()
        m.execute({"key": "v"})
        health = m.get_module_health()
        self.assertGreater(health["health_score"], 0)

    def test_resource_usage(self):
        m = _StubModule()
        m.initialize()
        health = m.get_module_health()
        self.assertIn("resource_usage", health)

    def test_quality_assessment(self):
        m = _StubModule()
        m.initialize()
        health = m.get_module_health()
        self.assertIn("quality_assessment", health)
        qa = health["quality_assessment"]
        self.assertIn("overall_quality", qa)


# ============================================================
# 分析摘要 (_build_analysis_summary)
# ============================================================
class TestAnalysisSummary(unittest.TestCase):
    def test_idle_status(self):
        m = _StubModule()
        s = m._build_analysis_summary()
        self.assertEqual(s["status"], "idle")

    def test_stable_status(self):
        m = _StubModule(exec_result={"success": True})
        m.initialize()
        m.execute({"key": "v"})
        s = m._build_analysis_summary()
        self.assertIn(s["status"], ("stable", "needs_followup"))

    def test_needs_followup_on_failed_phase(self):
        m = _StubModule()
        m.initialize()
        m.failed_phase = "some_phase"
        m.performance_history.append({"success": True})
        s = m._build_analysis_summary()
        self.assertEqual(s["status"], "needs_followup")

    def test_cleaned_status_resets_to_idle(self):
        m = _StubModule()
        m.initialize()
        m.execute({"key": "v"})
        m.cleanup()
        s = m._build_analysis_summary()
        self.assertEqual(s["status"], "idle")


# ============================================================
# 全局线程池
# ============================================================
class TestGlobalExecutor(unittest.TestCase):
    def test_get_global_executor_returns_executor(self):
        executor = get_global_executor(2)
        self.assertIsNotNone(executor)

    def test_reuse_same_workers(self):
        e1 = get_global_executor(3)
        e2 = get_global_executor(3)
        self.assertIs(e1, e2)

    def test_change_workers_recreates(self):
        e1 = get_global_executor(2)
        e2 = get_global_executor(5)
        self.assertIsNot(e1, e2)


# ============================================================
# AsyncBaseModule
# ============================================================
class TestAsyncBaseModule(unittest.TestCase):
    def test_async_execute_success(self):
        m = _AsyncStubModule(exec_result={"success": True, "quality_score": 0.8})
        m.initialize()
        result = asyncio.run(m.async_execute({"key": "v"}))
        self.assertTrue(result["success"])
        self.assertEqual(m.metrics["execution_count"], 1)

    def test_async_execute_not_initialized(self):
        m = _AsyncStubModule()
        with self.assertRaises(RuntimeError):
            asyncio.run(m.async_execute({"key": "v"}))

    def test_async_execute_failure(self):
        m = _AsyncStubModule()
        m.initialize()
        with self.assertRaises(RuntimeError):
            asyncio.run(m.async_execute({"raise": True}))
        self.assertFalse(m.metrics["last_success"])


if __name__ == "__main__":
    unittest.main()
