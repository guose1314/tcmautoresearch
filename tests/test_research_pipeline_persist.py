"""
tests/test_research_pipeline_persist.py
ResearchPipeline._persist_result() 单元测试
"""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from src.research.research_pipeline import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
    ResearchPipeline,
)


def _make_cycle(
    cycle_id: str = "cycle_test_001",
    status: ResearchCycleStatus = ResearchCycleStatus.COMPLETED,
) -> ResearchCycle:
    cycle = ResearchCycle(
        cycle_id=cycle_id,
        cycle_name="测试循环",
        description="单元测试用",
        research_objective="验证持久化",
    )
    cycle.status = status
    cycle.started_at = "2026-01-01T00:00:00"
    cycle.completed_at = datetime.now().isoformat()
    cycle.duration = 42.0
    cycle.outcomes = [{"phase": "observe", "result": {"observations": ["obs1"]}}]
    return cycle


class TestPersistResultBasic(unittest.TestCase):
    """基本读写测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_returns_true_on_success(self):
        cycle = _make_cycle()
        result = self.pipeline._persist_result(cycle)
        self.assertTrue(result)

    def test_creates_db_file(self):
        self.pipeline._persist_result(_make_cycle())
        self.assertTrue(os.path.isfile(self.db_path))

    def test_row_written(self):
        cycle = _make_cycle("cycle_abc")
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT cycle_id, cycle_name, status FROM research_results WHERE cycle_id=?",
            ("cycle_abc",),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "cycle_abc")
        self.assertEqual(row[1], "测试循环")
        self.assertEqual(row[2], "completed")

    def test_outcomes_serialized_as_json(self):
        cycle = _make_cycle()
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute(
            "SELECT outcomes_json FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()[0]
        conn.close()
        data = json.loads(raw)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) > 0)

    def test_metadata_serialized_as_json(self):
        cycle = _make_cycle()
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute(
            "SELECT metadata_json FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()[0]
        conn.close()
        data = json.loads(raw)
        self.assertIsInstance(data, dict)

    def test_persisted_at_is_set(self):
        self.pipeline._persist_result(_make_cycle())
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT persisted_at FROM research_results").fetchone()
        conn.close()
        self.assertIsNotNone(row[0])
        # 格式为 ISO 8601
        datetime.fromisoformat(row[0])

    def test_duration_stored(self):
        cycle = _make_cycle()
        cycle.duration = 99.5
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT duration FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()
        conn.close()
        self.assertAlmostEqual(row[0], 99.5)


class TestPersistResultUpsert(unittest.TestCase):
    """幂等写入 / upsert 测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_upsert_overwrites_existing(self):
        cycle = _make_cycle("cycle_dup")
        self.pipeline._persist_result(cycle)
        # 更新状态后再写
        cycle.status = ResearchCycleStatus.FAILED
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT status FROM research_results WHERE cycle_id=?", ("cycle_dup",)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "failed")

    def test_multiple_cycles_stored(self):
        for i in range(5):
            self.pipeline._persist_result(_make_cycle(f"cycle_{i:03d}"))
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM research_results").fetchone()[0]
        conn.close()
        self.assertEqual(count, 5)


class TestPersistResultErrorHandling(unittest.TestCase):
    """错误处理：失败不阻断主链"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_returns_false_on_db_error(self):
        cycle = _make_cycle()
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("boom")):
            result = self.pipeline._persist_result(cycle)
        self.assertFalse(result)

    def test_does_not_raise_on_error(self):
        cycle = _make_cycle()
        with patch("sqlite3.connect", side_effect=Exception("unexpected")):
            try:
                self.pipeline._persist_result(cycle)
            except Exception:
                self.fail("_persist_result() should not propagate exceptions")


class TestPersistResultDefaultPath(unittest.TestCase):
    """默认路径（output/research_results.db）测试"""

    def test_creates_output_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "subdir", "research_results.db")
            pipeline = ResearchPipeline({"result_store_path": db_path})
            pipeline._persist_result(_make_cycle())
            self.assertTrue(os.path.isfile(db_path))


class TestPersistResultIntegration(unittest.TestCase):
    """complete_research_cycle() 调用 _persist_result() 集成测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_complete_cycle_triggers_persist(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="集成测试循环",
            description="desc",
            objective="obj",
            scope="scope",
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        self.pipeline.complete_research_cycle(cycle.cycle_id)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "completed")


if __name__ == "__main__":
    unittest.main()
