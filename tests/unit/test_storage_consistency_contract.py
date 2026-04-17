"""结构化存储一致性状态合同 — 契约测试。

验证：
- StorageConsistencyState 数据结构在所有场景下产出正确
- build_consistency_state 对每种后端组合返回正确 mode
- StorageBackendFactory.get_consistency_state() 与 build_consistency_state 保持一致
- TransactionResult.storage_mode 字段存在且可赋值
- consistency_state.to_dict() 包含所有必需字段
"""

import unittest
from datetime import datetime

from src.storage.consistency import (
    MODE_DUAL_WRITE,
    MODE_PG_ONLY,
    MODE_SQLITE_FALLBACK,
    MODE_UNINITIALIZED,
    STATUS_ACTIVE,
    STATUS_DEGRADED,
    STATUS_DISABLED,
    STATUS_SQLITE_FALLBACK,
    STATUS_UNINITIALIZED,
    StorageConsistencyState,
    build_consistency_state,
)
from src.storage.transaction import TransactionResult


class TestBuildConsistencyState(unittest.TestCase):
    """build_consistency_state 在各种后端组合下返回正确 mode。"""

    def test_dual_write_pg_and_neo4j_active(self):
        state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="active",
            neo4j_driver_connected=True,
        )
        self.assertEqual(state.mode, MODE_DUAL_WRITE)
        self.assertEqual(state.pg_status, STATUS_ACTIVE)
        self.assertEqual(state.neo4j_status, STATUS_ACTIVE)
        self.assertTrue(state.is_dual_write)
        self.assertFalse(state.is_degraded)
        self.assertIsNone(state.neo4j_degradation_reason)

    def test_pg_only_neo4j_disabled(self):
        state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=False,
            neo4j_status="skipped",
            neo4j_driver_connected=False,
        )
        self.assertEqual(state.mode, MODE_PG_ONLY)
        self.assertEqual(state.pg_status, STATUS_ACTIVE)
        self.assertEqual(state.neo4j_status, STATUS_DISABLED)
        self.assertTrue(state.is_pg_only)
        self.assertTrue(state.is_degraded)
        self.assertIsNotNone(state.neo4j_degradation_reason)

    def test_pg_only_neo4j_init_failed(self):
        state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="error: connection refused",
            neo4j_driver_connected=False,
        )
        self.assertEqual(state.mode, MODE_PG_ONLY)
        self.assertEqual(state.neo4j_status, STATUS_DEGRADED)
        self.assertIn("error", state.neo4j_degradation_reason)

    def test_sqlite_fallback(self):
        state = build_consistency_state(
            initialized=True,
            db_type="sqlite",
            pg_status="active",
            neo4j_enabled=False,
            neo4j_status="skipped",
            neo4j_driver_connected=False,
        )
        self.assertEqual(state.mode, MODE_SQLITE_FALLBACK)
        self.assertEqual(state.pg_status, STATUS_SQLITE_FALLBACK)
        self.assertTrue(state.is_degraded)

    def test_uninitialized(self):
        state = build_consistency_state(
            initialized=False,
            db_type="postgresql",
            pg_status="",
            neo4j_enabled=True,
            neo4j_status="",
            neo4j_driver_connected=False,
        )
        self.assertEqual(state.mode, MODE_UNINITIALIZED)
        self.assertEqual(state.pg_status, STATUS_UNINITIALIZED)
        self.assertEqual(state.neo4j_status, STATUS_UNINITIALIZED)
        self.assertFalse(state.initialized)

    def test_schema_drift_reflected(self):
        state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="active",
            neo4j_driver_connected=True,
            schema_drift_detected=True,
        )
        self.assertTrue(state.schema_drift_detected)
        self.assertIn("schema drift", state.summary)


class TestStorageConsistencyStateContract(unittest.TestCase):
    """StorageConsistencyState 数据结构合同测试。"""

    def _make_dual_write(self) -> StorageConsistencyState:
        return build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="active",
            neo4j_driver_connected=True,
        )

    def test_to_dict_contains_required_keys(self):
        state = self._make_dual_write()
        d = state.to_dict()
        required_keys = {"mode", "pg_status", "neo4j_status", "schema_drift_detected",
                         "initialized", "db_type", "summary", "timestamp"}
        self.assertTrue(required_keys.issubset(set(d.keys())), f"缺少字段: {required_keys - set(d.keys())}")

    def test_to_dict_mode_matches_property(self):
        state = self._make_dual_write()
        self.assertEqual(state.to_dict()["mode"], state.mode)

    def test_summary_always_non_empty(self):
        for mode_kwargs in [
            {"initialized": True, "db_type": "postgresql", "pg_status": "active",
             "neo4j_enabled": True, "neo4j_status": "active", "neo4j_driver_connected": True},
            {"initialized": True, "db_type": "postgresql", "pg_status": "active",
             "neo4j_enabled": False, "neo4j_status": "skipped", "neo4j_driver_connected": False},
            {"initialized": True, "db_type": "sqlite", "pg_status": "active",
             "neo4j_enabled": False, "neo4j_status": "skipped", "neo4j_driver_connected": False},
            {"initialized": False, "db_type": "postgresql", "pg_status": "",
             "neo4j_enabled": True, "neo4j_status": "", "neo4j_driver_connected": False},
        ]:
            state = build_consistency_state(**mode_kwargs)
            self.assertTrue(len(state.summary) > 0, f"空 summary: {state.mode}")

    def test_degradation_reason_only_when_not_active(self):
        active = self._make_dual_write()
        self.assertIsNone(active.neo4j_degradation_reason)

        degraded = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="error: timeout",
            neo4j_driver_connected=False,
        )
        self.assertIsNotNone(degraded.neo4j_degradation_reason)

    def test_timestamp_is_valid_iso(self):
        state = self._make_dual_write()
        datetime.fromisoformat(state.timestamp)


class TestTransactionResultStorageMode(unittest.TestCase):
    """TransactionResult 包含 storage_mode 字段。"""

    def test_storage_mode_field_present(self):
        result = TransactionResult(success=True, storage_mode="dual_write")
        self.assertEqual(result.storage_mode, "dual_write")

    def test_storage_mode_default_empty(self):
        result = TransactionResult(success=True)
        self.assertEqual(result.storage_mode, "")


class TestTransactionResultObservationFields(unittest.TestCase):
    """TransactionResult 新增观测字段 — 契约测试。"""

    def test_neo4j_error_field_default_none(self):
        result = TransactionResult(success=True)
        self.assertIsNone(result.neo4j_error)

    def test_neo4j_error_field_assignable(self):
        result = TransactionResult(success=False, neo4j_error="connection refused")
        self.assertEqual(result.neo4j_error, "connection refused")

    def test_compensation_details_field_default_empty_list(self):
        result = TransactionResult(success=True)
        self.assertIsInstance(result.compensation_details, list)
        self.assertEqual(len(result.compensation_details), 0)

    def test_compensation_details_field_assignable(self):
        details = ["compensated: MATCH (n) DELETE n"]
        result = TransactionResult(success=False, compensation_details=details)
        self.assertEqual(result.compensation_details, details)

    def test_needs_backfill_field_default_false(self):
        result = TransactionResult(success=True)
        self.assertFalse(result.needs_backfill)

    def test_needs_backfill_field_assignable(self):
        result = TransactionResult(success=False, needs_backfill=True)
        self.assertTrue(result.needs_backfill)

    def test_all_observation_fields_coexist(self):
        result = TransactionResult(
            success=False,
            neo4j_error="timeout",
            compensation_details=["comp1", "comp2"],
            needs_backfill=True,
            compensations_applied=2,
            storage_mode="dual_write",
        )
        self.assertEqual(result.neo4j_error, "timeout")
        self.assertEqual(len(result.compensation_details), 2)
        self.assertTrue(result.needs_backfill)
        self.assertEqual(result.compensations_applied, 2)


class TestEventualConsistencyAnnotation(unittest.TestCase):
    """phase_orchestrator._classify_eventual_consistency 边界标注 — 契约测试。"""

    @staticmethod
    def _classify(mode, graph_enabled, graph_status, node_count):
        from src.research.phase_orchestrator import PhaseOrchestrator
        state = build_consistency_state(
            initialized=True,
            db_type="postgresql" if mode != MODE_SQLITE_FALLBACK else "sqlite",
            pg_status="active",
            neo4j_enabled=mode == MODE_DUAL_WRITE,
            neo4j_status="active" if mode == MODE_DUAL_WRITE else "skipped",
            neo4j_driver_connected=mode == MODE_DUAL_WRITE,
        )
        graph_report = {
            "enabled": graph_enabled,
            "status": graph_status,
            "node_count": node_count,
        }
        return PhaseOrchestrator._classify_eventual_consistency(state, graph_report)

    def test_dual_write_graph_ok_no_backfill(self):
        ec = self._classify(MODE_DUAL_WRITE, True, "active", 5)
        self.assertFalse(ec["graph_backfill_pending"])
        self.assertIsNone(ec["reason"])

    def test_pg_only_marks_backfill_pending(self):
        ec = self._classify(MODE_PG_ONLY, False, "skipped", 0)
        self.assertTrue(ec["graph_backfill_pending"])
        self.assertIn("backfill", ec["reason"])

    def test_dual_write_graph_failed_marks_backfill(self):
        ec = self._classify(MODE_DUAL_WRITE, True, "error", 0)
        self.assertTrue(ec["graph_backfill_pending"])
        self.assertIn("backfill", ec["reason"])

    def test_dual_write_graph_zero_nodes_marks_backfill(self):
        ec = self._classify(MODE_DUAL_WRITE, True, "active", 0)
        self.assertTrue(ec["graph_backfill_pending"])
        self.assertIn("backfill", ec["reason"])

    def test_sqlite_fallback_marks_backfill(self):
        ec = self._classify(MODE_SQLITE_FALLBACK, False, "skipped", 0)
        self.assertTrue(ec["graph_backfill_pending"])
        self.assertIn("backfill", ec["reason"])

    def test_result_has_required_keys(self):
        ec = self._classify(MODE_DUAL_WRITE, True, "active", 5)
        self.assertIn("graph_backfill_pending", ec)
        self.assertIn("reason", ec)


class TestMonitoringPersistenceConsistencyState(unittest.TestCase):
    """monitoring._build_persistence_summary 嵌入 consistency_state — 契约测试。"""

    def test_get_consistency_state_dict_method_exists(self):
        from src.infrastructure.monitoring import MonitoringService
        self.assertTrue(hasattr(MonitoringService, "_get_consistency_state_dict"))


class TestFactoryGetConsistencyState(unittest.TestCase):
    """StorageBackendFactory.get_consistency_state() 集成验证。"""

    def test_uninitialized_factory_returns_uninitialized_state(self):
        from src.storage.backend_factory import StorageBackendFactory

        factory = StorageBackendFactory({"database": {"type": "sqlite"}})
        state = factory.get_consistency_state()
        self.assertEqual(state.mode, MODE_UNINITIALIZED)
        self.assertFalse(state.initialized)

    def test_factory_neo4j_disabled_returns_correct_mode(self):
        from src.storage.backend_factory import StorageBackendFactory

        factory = StorageBackendFactory({
            "database": {"type": "postgresql"},
            "neo4j": {"enabled": False},
        })
        # 模拟已初始化但无 Neo4j
        factory._initialized = True
        factory._db_manager = object()  # 非 None 即可
        factory._neo4j_driver = None
        state = factory.get_consistency_state()
        self.assertEqual(state.mode, MODE_PG_ONLY)
        self.assertEqual(state.neo4j_status, STATUS_DISABLED)


class TestModeConstants(unittest.TestCase):
    """模式常量值稳定性。"""

    def test_mode_constants_are_strings(self):
        for mode in [MODE_DUAL_WRITE, MODE_PG_ONLY, MODE_SQLITE_FALLBACK, MODE_UNINITIALIZED]:
            self.assertIsInstance(mode, str)
            self.assertTrue(len(mode) > 0)

    def test_mode_constants_are_unique(self):
        modes = [MODE_DUAL_WRITE, MODE_PG_ONLY, MODE_SQLITE_FALLBACK, MODE_UNINITIALIZED]
        self.assertEqual(len(modes), len(set(modes)))

    def test_lazy_import_from_storage_package(self):
        from src.storage import (
            MODE_DUAL_WRITE as m1,
        )
        from src.storage import (
            MODE_PG_ONLY as m2,
        )
        from src.storage import (
            StorageConsistencyState as cls,
        )
        from src.storage import (
            build_consistency_state as fn,
        )
        self.assertEqual(m1, "dual_write")
        self.assertEqual(m2, "pg_only")
        self.assertTrue(callable(fn))
        self.assertTrue(hasattr(cls, "to_dict"))


if __name__ == "__main__":
    unittest.main()
