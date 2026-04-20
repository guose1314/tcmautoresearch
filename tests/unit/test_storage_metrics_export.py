"""F-2: StorageObservability / DegradationGovernor Prometheus 导出单元测试。"""

from __future__ import annotations

import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from prometheus_client import CollectorRegistry


def _make_monitoring_service(*, storage_governance: bool = True) -> Any:
    """构造带有 mock 依赖的 MonitoringService。"""
    from src.infrastructure.monitoring import MonitoringService

    settings = MagicMock()
    settings.get_section.side_effect = lambda *a, default=None, **kw: (
        {"storage_governance": storage_governance} if a[0] == "monitoring" else (default or {})
    )
    settings.environment = "test"
    settings.root_path = "."
    settings.loaded_files = []
    settings.database_type = "sqlite"
    settings.database_config = {}
    settings.neo4j_enabled = False
    settings.materialize_runtime_config.return_value = {}

    architecture = MagicMock()
    architecture.get_architecture_summary.return_value = {}

    job_manager = MagicMock()
    job_manager.get_runtime_metrics.return_value = {}
    job_manager.get_storage_summary.return_value = {}

    return MonitoringService(settings, architecture, job_manager)


def _make_mock_factory() -> MagicMock:
    """构造 mock StorageBackendFactory。"""
    factory = MagicMock()
    factory.observability.get_health_report.return_value = {
        "health_score": 0.95,
        "window_metrics": {"success_rate": 0.98},
        "latency_ms": {"p50": 5.0, "p95": 12.5, "p99": 48.2},
        "lifetime_transactions": 1000,
        "lifetime_backfills": 3,
    }
    factory.degradation_governor.to_governance_report.return_value = {
        "current_mode": "dual_write",
        "is_degraded": False,
        "metrics": {
            "total_transactions": 100,
            "failed_transactions": 2,
            "compensations_applied": 1,
        },
    }
    factory.backfill_ledger.get_summary.return_value = {
        "total_entries": 10,
        "pending": 2,
        "completed": 7,
        "failed": 1,
        "has_pending": True,
    }
    return factory


class TestStorageGovernanceGaugeCreation(unittest.TestCase):
    """storage_governance 开关控制 gauge 注册。"""

    def test_gauges_registered_when_enabled(self):
        svc = _make_monitoring_service(storage_governance=True)
        self.assertIn("storage_health_score", svc._gauges)
        self.assertIn("storage_success_rate", svc._gauges)
        self.assertIn("storage_latency_p50_ms", svc._gauges)
        self.assertIn("storage_latency_p95_ms", svc._gauges)
        self.assertIn("storage_latency_p99_ms", svc._gauges)
        self.assertIn("storage_lifetime_transactions", svc._gauges)
        self.assertIn("storage_backfill_pending", svc._gauges)
        self.assertIn("storage_backfill_completed", svc._gauges)
        self.assertIn("storage_backfill_failed", svc._gauges)
        self.assertIn("storage_mode", svc._gauges)
        self.assertIn("storage_is_degraded", svc._gauges)
        self.assertIn("storage_failure_rate", svc._gauges)
        self.assertIn("storage_compensations_total", svc._gauges)

    def test_gauges_not_registered_when_disabled(self):
        svc = _make_monitoring_service(storage_governance=False)
        self.assertNotIn("storage_health_score", svc._gauges)
        self.assertNotIn("storage_is_degraded", svc._gauges)
        self.assertNotIn("storage_mode", svc._gauges)

    def test_base_gauges_always_present(self):
        svc = _make_monitoring_service(storage_governance=False)
        self.assertIn("system_health_score", svc._gauges)
        self.assertIn("jobs_total", svc._gauges)


class TestStorageGovernanceGaugeUpdate(unittest.TestCase):
    """gauge 更新逻辑正确消费 observability / governor / backfill 报告。"""

    @patch("src.storage.StorageBackendFactory")
    def test_observability_gauges_set(self, mock_factory_cls):
        mock_factory_cls.return_value = _make_mock_factory()
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_health_score"]._value.get(), 0.95)
        self.assertAlmostEqual(svc._gauges["storage_success_rate"]._value.get(), 0.98)
        self.assertAlmostEqual(svc._gauges["storage_latency_p50_ms"]._value.get(), 5.0)
        self.assertAlmostEqual(svc._gauges["storage_latency_p95_ms"]._value.get(), 12.5)
        self.assertAlmostEqual(svc._gauges["storage_latency_p99_ms"]._value.get(), 48.2)
        self.assertAlmostEqual(svc._gauges["storage_lifetime_transactions"]._value.get(), 1000.0)

    @patch("src.storage.StorageBackendFactory")
    def test_governor_gauges_set(self, mock_factory_cls):
        mock_factory_cls.return_value = _make_mock_factory()
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_is_degraded"]._value.get(), 0.0)
        self.assertAlmostEqual(svc._gauges["storage_failure_rate"]._value.get(), 0.02)
        self.assertAlmostEqual(svc._gauges["storage_compensations_total"]._value.get(), 1.0)

    @patch("src.storage.StorageBackendFactory")
    def test_backfill_gauges_set(self, mock_factory_cls):
        mock_factory_cls.return_value = _make_mock_factory()
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_backfill_pending"]._value.get(), 2.0)
        self.assertAlmostEqual(svc._gauges["storage_backfill_completed"]._value.get(), 7.0)
        self.assertAlmostEqual(svc._gauges["storage_backfill_failed"]._value.get(), 1.0)

    @patch("src.storage.StorageBackendFactory")
    def test_mode_label_gauge_set(self, mock_factory_cls):
        mock_factory_cls.return_value = _make_mock_factory()
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        # dual_write should be 1, others 0
        mode_gauge = svc._gauges["storage_mode"]
        self.assertAlmostEqual(mode_gauge.labels(mode="dual_write")._value.get(), 1.0)
        self.assertAlmostEqual(mode_gauge.labels(mode="pg_only")._value.get(), 0.0)
        self.assertAlmostEqual(mode_gauge.labels(mode="sqlite_fallback")._value.get(), 0.0)

    @patch("src.storage.StorageBackendFactory")
    def test_degraded_flag_set_when_degraded(self, mock_factory_cls):
        f = _make_mock_factory()
        f.degradation_governor.to_governance_report.return_value["is_degraded"] = True
        mock_factory_cls.return_value = f
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_is_degraded"]._value.get(), 1.0)

    @patch("src.storage.StorageBackendFactory", side_effect=Exception("no db"))
    def test_factory_failure_graceful(self, mock_factory_cls):
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        # Should not raise, gauges stay at default 0
        self.assertAlmostEqual(svc._gauges["storage_health_score"]._value.get(), 0.0)

    @patch("src.storage.StorageBackendFactory")
    def test_zero_transactions_no_division_error(self, mock_factory_cls):
        f = _make_mock_factory()
        f.degradation_governor.to_governance_report.return_value["metrics"]["total_transactions"] = 0
        mock_factory_cls.return_value = f
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_failure_rate"]._value.get(), 0.0)

    def test_prometheus_export_contains_storage_gauges(self):
        svc = _make_monitoring_service(storage_governance=True)
        output = svc._registry
        # Verify gauge names appear in registry
        gauge_names = {m.name for m in output.collect() for s in m.samples}
        self.assertTrue(any("tcm_storage" in n for n in gauge_names))


class TestStorageFactoryBinding(unittest.TestCase):
    """bind_storage_factory / unbind_storage_factory 生命周期。"""

    def test_initially_unbound(self):
        svc = _make_monitoring_service(storage_governance=True)
        self.assertIsNone(svc.bound_storage_factory)

    def test_bind_and_unbind(self):
        svc = _make_monitoring_service(storage_governance=True)
        factory = _make_mock_factory()
        svc.bind_storage_factory(factory)
        self.assertIs(svc.bound_storage_factory, factory)
        svc.unbind_storage_factory()
        self.assertIsNone(svc.bound_storage_factory)

    def test_bound_factory_preferred_over_transient(self):
        """绑定 factory 后 gauge 更新不应创建临时 factory。"""
        svc = _make_monitoring_service(storage_governance=True)
        factory = _make_mock_factory()
        svc.bind_storage_factory(factory)
        svc._update_storage_governance_gauges()
        # Verify the bound factory's observability was called
        factory.observability.get_health_report.assert_called_once()
        factory.degradation_governor.to_governance_report.assert_called_once()
        factory.backfill_ledger.get_summary.assert_called_once()
        # Bound factory should NOT be closed
        factory.close.assert_not_called()

    @patch("src.storage.StorageBackendFactory")
    def test_transient_factory_closed_after_use(self, mock_factory_cls):
        """无绑定 factory 时临时 factory 应被关闭。"""
        transient = _make_mock_factory()
        mock_factory_cls.return_value = transient
        svc = _make_monitoring_service(storage_governance=True)
        svc._update_storage_governance_gauges()
        transient.close.assert_called_once()

    def test_bound_factory_gauges_reflect_live_data(self):
        svc = _make_monitoring_service(storage_governance=True)
        factory = _make_mock_factory()
        factory.observability.get_health_report.return_value["health_score"] = 0.88
        factory.observability.get_health_report.return_value["lifetime_transactions"] = 5000
        svc.bind_storage_factory(factory)
        svc._update_storage_governance_gauges()
        self.assertAlmostEqual(svc._gauges["storage_health_score"]._value.get(), 0.88)
        self.assertAlmostEqual(svc._gauges["storage_lifetime_transactions"]._value.get(), 5000.0)


class TestStorageHealthEndpointShape(unittest.TestCase):
    """F-2-4: /api/storage/health 端点返回形状检查。"""

    def test_route_registered(self):
        from src.api.routes.system import router
        paths = [route.path for route in router.routes]
        self.assertIn("/storage/health", paths)


if __name__ == "__main__":
    unittest.main()
