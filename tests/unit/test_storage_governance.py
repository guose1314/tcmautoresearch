"""存储治理与可观测性组件单元测试。

覆盖：
- DegradationGovernor: 模式变迁、指标累计、生产就绪判定
- BackfillLedger: 条目录入、状态流转、查询
- StorageObservability: 事务观测聚合、健康评分
- StorageBackendFactory 集成: 事务完成后自动记录观测
"""

import threading
import unittest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch

from src.storage.backfill_ledger import BackfillLedger
from src.storage.degradation_governor import DegradationGovernor, DegradationMetrics
from src.storage.observability import StorageObservability, _classify_health

# ── Fake TransactionResult ────────────────────────────────────────────────

@dataclass
class FakeTransactionResult:
    success: bool = True
    pg_committed: bool = True
    neo4j_committed: bool = True
    storage_mode: str = "dual_write"
    error: Optional[str] = None
    compensations_applied: int = 0
    neo4j_error: Optional[str] = None
    compensation_details: List[str] = field(default_factory=list)
    needs_backfill: bool = False
    total_ms: float = 10.0
    pg_flush_ms: float = 2.0
    neo4j_execute_ms: float = 5.0
    pg_commit_ms: float = 3.0
    neo4j_op_count: int = 2


# ══════════════════════════════════════════════════════════════════════════
# DegradationGovernor Tests
# ══════════════════════════════════════════════════════════════════════════


class TestDegradationGovernor(unittest.TestCase):

    def setUp(self):
        self.gov = DegradationGovernor()

    def test_initial_state_uninitialized(self):
        self.assertEqual(self.gov.current_mode, "uninitialized")
        self.assertFalse(self.gov.is_production_ready)
        self.assertFalse(self.gov.is_degraded)

    def test_set_initial_mode_dual_write(self):
        self.gov.set_initial_mode("dual_write")
        self.assertEqual(self.gov.current_mode, "dual_write")
        self.assertTrue(self.gov.is_production_ready)
        self.assertFalse(self.gov.is_degraded)

    def test_set_initial_mode_pg_only_not_production_ready(self):
        self.gov.set_initial_mode("pg_only")
        self.assertEqual(self.gov.current_mode, "pg_only")
        self.assertFalse(self.gov.is_production_ready)
        self.assertTrue(self.gov.is_degraded)

    def test_acknowledge_makes_pg_only_production_ready(self):
        self.gov.set_initial_mode("pg_only")
        self.assertFalse(self.gov.is_production_ready)
        result = self.gov.acknowledge_degradation("pg_only")
        self.assertTrue(result)
        self.assertTrue(self.gov.is_production_ready)

    def test_acknowledge_wrong_mode_rejected(self):
        self.gov.set_initial_mode("pg_only")
        result = self.gov.acknowledge_degradation("dual_write")
        self.assertFalse(result)
        self.assertFalse(self.gov.is_production_ready)

    def test_mode_transition_resets_acknowledgement(self):
        self.gov.set_initial_mode("pg_only")
        self.gov.acknowledge_degradation("pg_only")
        self.assertTrue(self.gov.is_production_ready)
        # 模式变迁重置确认
        self.gov.record_mode_transition("pg_only", "sqlite_fallback", reason="test")
        self.assertFalse(self.gov.is_production_ready)

    def test_record_transaction_result_success(self):
        self.gov.set_initial_mode("dual_write")
        result = FakeTransactionResult(success=True, storage_mode="dual_write")
        self.gov.record_transaction_result(result)
        metrics = self.gov.metrics
        self.assertEqual(metrics.total_transactions, 1)
        self.assertEqual(metrics.dual_write_transactions, 1)
        self.assertEqual(metrics.failed_transactions, 0)

    def test_record_transaction_result_neo4j_failure(self):
        self.gov.set_initial_mode("pg_only")
        result = FakeTransactionResult(
            success=False, storage_mode="pg_only",
            neo4j_error="connection refused",
            needs_backfill=True, compensations_applied=3,
        )
        self.gov.record_transaction_result(result)
        metrics = self.gov.metrics
        self.assertEqual(metrics.failed_transactions, 1)
        self.assertEqual(metrics.neo4j_failures, 1)
        self.assertEqual(metrics.compensations_applied, 3)
        self.assertEqual(metrics.backfill_pending_count, 1)

    def test_summary_text_dual_write(self):
        self.gov.set_initial_mode("dual_write")
        self.assertIn("dual_write", self.gov.summary)

    def test_summary_text_pg_only_unacknowledged(self):
        self.gov.set_initial_mode("pg_only")
        self.assertIn("未确认", self.gov.summary)

    def test_get_transitions_history(self):
        self.gov.set_initial_mode("dual_write")
        self.gov.record_mode_transition("dual_write", "pg_only", reason="Neo4j 超时")
        transitions = self.gov.get_transitions()
        self.assertEqual(len(transitions), 2)  # initial + manual
        self.assertEqual(transitions[-1]["to_mode"], "pg_only")
        self.assertEqual(transitions[-1]["reason"], "Neo4j 超时")

    def test_to_governance_report_structure(self):
        self.gov.set_initial_mode("dual_write")
        report = self.gov.to_governance_report()
        self.assertIn("current_mode", report)
        self.assertIn("is_production_ready", report)
        self.assertIn("metrics", report)
        self.assertIn("recent_transitions", report)
        self.assertEqual(report["current_mode"], "dual_write")

    def test_thread_safety(self):
        """并发写入不应抛出异常。"""
        self.gov.set_initial_mode("dual_write")
        errors = []

        def writer():
            try:
                for _ in range(50):
                    self.gov.record_transaction_result(
                        FakeTransactionResult(success=True)
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.gov.metrics.total_transactions, 200)


# ══════════════════════════════════════════════════════════════════════════
# BackfillLedger Tests
# ══════════════════════════════════════════════════════════════════════════


class TestBackfillLedger(unittest.TestCase):

    def setUp(self):
        self.ledger = BackfillLedger()

    def test_record_pending_returns_entry_id(self):
        entry_id = self.ledger.record_pending(
            cycle_id="cycle-001", phase="observe", reason="Neo4j 写失败"
        )
        self.assertTrue(entry_id.startswith("bf-"))

    def test_get_pending_returns_entries(self):
        self.ledger.record_pending(cycle_id="c1", phase="observe", reason="fail")
        self.ledger.record_pending(cycle_id="c2", phase="hypothesis", reason="timeout")
        pending = self.ledger.get_pending()
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["cycle_id"], "c1")
        self.assertEqual(pending[1]["status"], "pending")

    def test_mark_completed(self):
        self.ledger.record_pending(cycle_id="c1", phase="observe", reason="fail")
        count = self.ledger.mark_completed("c1", phase="observe")
        self.assertEqual(count, 1)
        pending = self.ledger.get_pending()
        self.assertEqual(len(pending), 0)

    def test_mark_completed_wrong_cycle_no_effect(self):
        self.ledger.record_pending(cycle_id="c1", phase="observe", reason="fail")
        count = self.ledger.mark_completed("c2", phase="observe")
        self.assertEqual(count, 0)
        self.assertEqual(len(self.ledger.get_pending()), 1)

    def test_mark_failed(self):
        self.ledger.record_pending(cycle_id="c1", phase="observe", reason="fail")
        count = self.ledger.mark_failed("c1", phase="observe", error="retry exhausted")
        self.assertEqual(count, 1)
        summary = self.ledger.get_summary()
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["pending"], 0)

    def test_record_from_transaction_result_needs_backfill(self):
        result = FakeTransactionResult(
            success=False, needs_backfill=True,
            error="Neo4j timeout", neo4j_error="connection refused",
            compensation_details=["compensated node X"],
        )
        entry_id = self.ledger.record_from_transaction_result(
            result, cycle_id="c1", phase="observe"
        )
        self.assertIsNotNone(entry_id)
        pending = self.ledger.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["transaction_error"], "connection refused")

    def test_record_from_transaction_result_no_backfill(self):
        result = FakeTransactionResult(success=True, needs_backfill=False)
        entry_id = self.ledger.record_from_transaction_result(
            result, cycle_id="c1", phase="observe"
        )
        self.assertIsNone(entry_id)
        self.assertEqual(len(self.ledger.get_pending()), 0)

    def test_get_summary(self):
        self.ledger.record_pending(cycle_id="c1", phase="observe", reason="a")
        self.ledger.record_pending(cycle_id="c2", phase="observe", reason="b")
        self.ledger.mark_completed("c1")
        summary = self.ledger.get_summary()
        self.assertEqual(summary["total_entries"], 2)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertTrue(summary["has_pending"])
        self.assertIn("c2", summary["pending_cycle_ids"])


# ══════════════════════════════════════════════════════════════════════════
# StorageObservability Tests
# ══════════════════════════════════════════════════════════════════════════


class TestStorageObservability(unittest.TestCase):

    def setUp(self):
        self.obs = StorageObservability(window_size=50)

    def test_empty_report(self):
        report = self.obs.get_health_report()
        self.assertEqual(report["health_score"], 1.0)
        self.assertEqual(report["status"], "no_data")
        self.assertEqual(report["window_size"], 0)

    def test_all_success_healthy(self):
        for _ in range(10):
            self.obs.record(FakeTransactionResult(success=True, total_ms=5.0))
        report = self.obs.get_health_report()
        self.assertGreaterEqual(report["health_score"], 0.95)
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["window_metrics"]["success_count"], 10)

    def test_failures_reduce_health(self):
        for _ in range(8):
            self.obs.record(FakeTransactionResult(success=True))
        for _ in range(2):
            self.obs.record(FakeTransactionResult(success=False, needs_backfill=True))
        report = self.obs.get_health_report()
        self.assertLess(report["health_score"], 0.95)
        self.assertEqual(report["window_metrics"]["failure_count"], 2)

    def test_latency_percentiles(self):
        for i in range(20):
            self.obs.record(FakeTransactionResult(success=True, total_ms=float(i + 1)))
        report = self.obs.get_health_report()
        self.assertGreater(report["latency_ms"]["p95"], report["latency_ms"]["p50"])

    def test_mode_distribution(self):
        for _ in range(5):
            self.obs.record(FakeTransactionResult(storage_mode="dual_write"))
        for _ in range(3):
            self.obs.record(FakeTransactionResult(storage_mode="pg_only"))
        report = self.obs.get_health_report()
        self.assertEqual(report["mode_distribution"]["dual_write"], 5)
        self.assertEqual(report["mode_distribution"]["pg_only"], 3)

    def test_recent_failures(self):
        self.obs.record(FakeTransactionResult(success=True))
        self.obs.record(FakeTransactionResult(
            success=False, compensations_applied=2, needs_backfill=True
        ))
        failures = self.obs.get_recent_failures()
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["compensations_applied"], 2)

    def test_lifetime_counters(self):
        for _ in range(5):
            self.obs.record(FakeTransactionResult(success=True))
        self.obs.record(FakeTransactionResult(success=False))
        report = self.obs.get_health_report()
        self.assertEqual(report["lifetime_transactions"], 6)
        self.assertEqual(report["lifetime_failures"], 1)


class TestClassifyHealth(unittest.TestCase):

    def test_healthy(self):
        self.assertEqual(_classify_health(1.0), "healthy")
        self.assertEqual(_classify_health(0.95), "healthy")

    def test_degraded(self):
        self.assertEqual(_classify_health(0.90), "degraded")
        self.assertEqual(_classify_health(0.80), "degraded")

    def test_unhealthy(self):
        self.assertEqual(_classify_health(0.70), "unhealthy")

    def test_critical(self):
        self.assertEqual(_classify_health(0.30), "critical")


# ══════════════════════════════════════════════════════════════════════════
# StorageBackendFactory Integration Tests
# ══════════════════════════════════════════════════════════════════════════


class TestBackendFactoryGovernanceIntegration(unittest.TestCase):
    """验证 StorageBackendFactory 正确暴露治理组件。"""

    def _make_factory(self, *, initialize: bool = False):
        """创建使用 tempfile 的 SQLite Factory。"""
        import tempfile

        from src.storage.backend_factory import StorageBackendFactory

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        factory = StorageBackendFactory({"database": {"type": "sqlite", "path": self._tmp.name}})
        if initialize:
            factory.initialize()
        return factory

    def tearDown(self):
        import os
        if hasattr(self, "_tmp") and os.path.exists(self._tmp.name):
            try:
                os.unlink(self._tmp.name)
            except OSError:
                pass

    def test_factory_has_governance_attributes(self):
        factory = self._make_factory()
        self.assertIsInstance(factory.degradation_governor, DegradationGovernor)
        self.assertIsInstance(factory.backfill_ledger, BackfillLedger)
        self.assertIsInstance(factory.observability, StorageObservability)

    def test_factory_initialize_sets_governor_mode(self):
        factory = self._make_factory(initialize=True)
        try:
            # SQLite → sqlite_fallback 模式
            self.assertEqual(
                factory.degradation_governor.current_mode, "sqlite_fallback"
            )
            self.assertTrue(factory.degradation_governor.is_degraded)
        finally:
            factory.close()

    def test_factory_get_governance_report(self):
        factory = self._make_factory(initialize=True)
        try:
            report = factory.get_governance_report()
            self.assertIn("consistency_state", report)
            self.assertIn("degradation", report)
            self.assertIn("backfill", report)
            self.assertIn("observability", report)
            self.assertEqual(report["consistency_state"]["mode"], "sqlite_fallback")
        finally:
            factory.close()

    def test_transaction_records_observability(self):
        """事务完成后自动记录到 observability。"""
        factory = self._make_factory(initialize=True)
        try:
            with factory.transaction() as txn:
                # 空事务，验证观测记录
                pass
            health = factory.observability.get_health_report()
            self.assertGreaterEqual(health["lifetime_transactions"], 1)
        finally:
            factory.close()


if __name__ == "__main__":
    unittest.main()
