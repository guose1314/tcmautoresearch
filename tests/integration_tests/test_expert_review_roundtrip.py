"""T7.2: tools/export_for_expert_review + tools/import_expert_review 闭环测试。

验收门
======

1. 用 5 个真实结构（含 hypothesis phase output + observe collation）的 cycle 走
   ``export → 标注 expert_grade → import``，最终 PG 中应有 5 条
   ``feedback_scope="expert_review"`` 的 ``research_learning_feedback`` 行。
2. 把这 5 条专家反馈通过 :class:`ExpertReviewFeedbackRepo` 适配进
   :class:`LearningLoopOrchestrator.prepare_cycle`，下一轮 ``prompt_bias_blocks``
   必须包含针对 hypothesis 的偏置块（即专家反馈被 LFITL 翻译成可注入下一轮
   prompt 的 bias_text）。
3. 第二次 import 同一个 jsonl 应是幂等的，不再新增行。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.learning.expert_review_feedback_repo import ExpertReviewFeedbackRepo
from src.research.learning_loop_orchestrator import LearningLoopOrchestrator
from tools.export_for_expert_review import export
from tools.import_expert_review import import_records


_FIXTURE_TOPICS = [
    ("cycle-001", "118-增订医方歌诀"),
    ("cycle-002", "121-医方歌括"),
    ("cycle-003", "196-产后十八论"),
    ("cycle-004", "287-脉诀考证"),
    ("cycle-005", "503-脉诀"),
]

_EXPERT_GRADES = ["A", "B", "C", "D", "D"]  # 至少 2 个 D 触发 high severity


def _build_phase_outputs(cycle_id: str, topic: str) -> List[Dict[str, Any]]:
    """模拟一个完成态 cycle 的 hypothesis + observe phase 输出。"""
    return [
        {
            "phase": "observe",
            "status": "completed",
            "output": {
                "collation_result": {
                    "document_count": 1,
                    "strategies_enabled": ["cross", "intra", "external", "rational"],
                    "succeeded_total": 3,
                    "failed_total": 1,
                    "reports": [
                        {
                            "document_id": f"{cycle_id}-doc",
                            "summary": {"total": 4, "succeeded": 3, "failed": 1},
                            "strategies": {
                                "cross": {"succeeded": True, "error": ""},
                                "intra": {"succeeded": True, "error": ""},
                                "external": {"succeeded": True, "error": ""},
                                "rational": {
                                    "succeeded": False,
                                    "error": "self_refine_runner not configured",
                                },
                            },
                        }
                    ],
                }
            },
        },
        {
            "phase": "hypothesis",
            "status": "completed",
            "output": {
                "results": {
                    "hypotheses": [
                        {
                            "id": f"{cycle_id}-h1",
                            "statement": f"假说: {topic} 中的方剂可能对应的证候是XX",
                            "methodology_tag": "evidence_based",
                            "evidence_grade": "B",
                            "evidence_bundle": [
                                {"source": "internal_kg", "weight": 0.8},
                            ],
                        }
                    ]
                }
            },
        },
    ]


class ExpertReviewRoundtripTest(unittest.TestCase):
    def setUp(self) -> None:
        # 临时目录承载 SQLite + jsonl
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_root = Path(self._tmp.name)
        self.db_path = tmp_root / "tcm.db"
        self.connection_string = f"sqlite:///{self.db_path.as_posix()}"
        self.review_jsonl = tmp_root / "round_1.jsonl"

        # 初始化 DB schema
        db = DatabaseManager(self.connection_string)
        db.init_db()
        repo = ResearchSessionRepository(db)
        # 写 5 条 cycle + phase output，让 export 拿得到完整 snapshot
        for cycle_id, topic in _FIXTURE_TOPICS:
            repo.create_session(
                {
                    "cycle_id": cycle_id,
                    "cycle_name": topic,
                    "research_objective": f"研究主题: {topic}",
                    "status": "completed",
                    "current_phase": "publish",
                }
            )
            for phase_payload in _build_phase_outputs(cycle_id, topic):
                added = repo.add_phase_execution(cycle_id, phase_payload)
                self.assertIsNotNone(added)
        # 关闭 setUp 内的 DB 句柄，避免 Windows 文件锁
        db.engine.dispose()

    # ----------------------------------------------------------------- #

    def _annotate_jsonl(self) -> None:
        """专家在 jsonl 旁标 expert_grade + expert_notes。"""
        lines = self.review_jsonl.read_text(encoding="utf-8").splitlines()
        annotated: List[str] = []
        for idx, raw in enumerate(lines):
            record = json.loads(raw)
            record["expert_grade"] = _EXPERT_GRADES[idx % len(_EXPERT_GRADES)]
            record["expert_notes"] = (
                f"专家备注 {idx}: {'通过' if record['expert_grade'] in {'A', 'B'} else '需复核'}"
            )
            annotated.append(json.dumps(record, ensure_ascii=False))
        self.review_jsonl.write_text("\n".join(annotated) + "\n", encoding="utf-8")

    # ----------------------------------------------------------------- #

    def test_export_import_roundtrip_drives_lfitl_prompt_bias(self) -> None:
        # ---- 1. 导出 5 篇 ----
        export_summary = export(
            connection_string=self.connection_string,
            cycle_ids=[c for c, _ in _FIXTURE_TOPICS],
            output=self.review_jsonl,
        )
        self.assertEqual(export_summary["records_written"], 5)
        self.assertEqual(export_summary["cycles_exported"], 5)
        self.assertEqual(export_summary["cycles_skipped"], [])

        # 每一行都缺 expert_grade
        raw_lines = self.review_jsonl.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(raw_lines), 5)
        for raw in raw_lines:
            payload = json.loads(raw)
            self.assertIsNone(payload["expert_grade"])
            self.assertIn("four_pass_collation", payload)
            self.assertIn("hypothesis_statement", payload)
            self.assertEqual(payload["evidence_grade"], "B")

        # ---- 2. 专家批注 ----
        self._annotate_jsonl()

        # ---- 3. 导入回 PG ----
        import_summary = import_records(
            connection_string=self.connection_string,
            input_path=self.review_jsonl,
            weight=5.0,
        )
        self.assertEqual(import_summary["records_inserted"], 5)
        self.assertEqual(import_summary["records_duplicate"], 0)
        self.assertEqual(import_summary["records_skipped"], [])
        self.assertEqual(len(import_summary["cycles_touched"]), 5)

        # ---- 4. 幂等：再 import 一次，0 新增、5 duplicate ----
        import_summary_2 = import_records(
            connection_string=self.connection_string,
            input_path=self.review_jsonl,
            weight=5.0,
        )
        self.assertEqual(import_summary_2["records_inserted"], 0)
        self.assertEqual(import_summary_2["records_duplicate"], 5)

        # ---- 5. PG 中确实落了 5 条 expert_review 行 ----
        db = DatabaseManager(self.connection_string)
        db.init_db()
        try:
            repo = ResearchSessionRepository(db)
            page = repo.list_learning_feedback(
                feedback_scope="expert_review", limit=50
            )
            self.assertEqual(page["total"], 5)
            grades = sorted(item["grade_level"] for item in page["items"])
            self.assertEqual(grades, sorted(_EXPERT_GRADES))
            for item in page["items"]:
                meta = item["metadata"]
                self.assertEqual(meta["origin"], "expert_review")
                self.assertEqual(meta["weight"], 5.0)
                self.assertTrue(meta["expert_review_id"])
                self.assertEqual(meta["source_phase"], "hypothesis")

            # ---- 6. LFITL 接入：下一轮 prepare_cycle 必须看到专家偏置 ----
            adapter = ExpertReviewFeedbackRepo(repo)
            recent = adapter.recent(limit=20)
            self.assertEqual(len(recent), 5)
            # 至少一条 high severity (来自 D)
            self.assertTrue(any(r["severity"] == "high" for r in recent))
            # source_phase 全部 hypothesis（导入时强制写入 metadata.source_phase）
            self.assertTrue(all(r["source_phase"] == "hypothesis" for r in recent))

            llo = LearningLoopOrchestrator(feedback_repo=adapter)
            prep = llo.prepare_cycle(SimpleNamespace(config={}))
            self.assertIsNotNone(prep["lfitl_plan"])
            bias_blocks = prep["prompt_bias_blocks"]
            self.assertIn(
                "hypothesis",
                bias_blocks,
                msg=f"专家反馈未编译进 hypothesis prompt bias: {bias_blocks!r}",
            )
            block = bias_blocks["hypothesis"]
            self.assertEqual(block["severity"], "high")
            # bias_text 应携带 expert_review 规则 id
            self.assertIn("expert_review", block["bias_text"].lower())
        finally:
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
