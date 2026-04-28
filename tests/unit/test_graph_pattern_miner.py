"""T5.3: GraphPatternMiner 单测。

happy path：mock 一个 neo4j driver，让它返回两条 (label, rel, label) 记录，
断言 miner 把它们映射成 :class:`Pattern`，且 confidence 用 totals 归一。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.contexts.lfitl import (
    FeedbackTranslator,
    GraphPatternMiner,
    Pattern,
)


def _record(payload: Dict[str, Any]):
    rec = MagicMock()
    rec.get.side_effect = lambda key, default=None: payload.get(key, default)
    rec.__getitem__ = lambda self, key: payload[key]
    return rec


def _build_driver(neg_rows: List[Dict[str, Any]], total_rows: List[Dict[str, Any]]):
    """Two consecutive ``session.run`` calls return neg rows then totals."""

    neg_records = [_record(r) for r in neg_rows]
    tot_records = [_record(r) for r in total_rows]
    session = MagicMock(name="Session")
    # session.run is iterated -> list(...). Use side_effect of two iterables.
    session.run.side_effect = [iter(neg_records), iter(tot_records)]
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    inner = MagicMock()
    inner.session = MagicMock(return_value=cm)
    wrapper = MagicMock()
    wrapper.driver = inner
    return wrapper, session


class TestGraphPatternMinerHappyPath(unittest.TestCase):
    def test_mine_returns_patterns_with_confidence(self) -> None:
        neg_rows = [
            {"la": ["Symptom"], "rt": "INDICATES", "lb": ["Syndrome"], "support": 6},
            {"la": ["Herb"], "rt": "TREATS", "lb": ["Symptom"], "support": 3},
        ]
        total_rows = [
            {"la": ["Symptom"], "rt": "INDICATES", "lb": ["Syndrome"], "total": 12},
            {"la": ["Herb"], "rt": "TREATS", "lb": ["Symptom"], "total": 6},
        ]
        driver, session = _build_driver(neg_rows, total_rows)

        miner = GraphPatternMiner(min_support=2, limit=10)
        patterns = miner.mine(driver, since_ts=1000.0)

        self.assertEqual(len(patterns), 2)
        self.assertTrue(all(isinstance(p, Pattern) for p in patterns))
        first = patterns[0]
        self.assertEqual(first.node_labels, ["Symptom", "Syndrome"])
        self.assertEqual(first.rel_types, ["INDICATES"])
        self.assertEqual(first.support, 6)
        self.assertAlmostEqual(first.confidence, 0.5)
        # Cypher invocation arguments
        first_call = session.run.call_args_list[0]
        self.assertIn("MATCH (a)-[r]->(b)", first_call.args[0])
        self.assertEqual(first_call.kwargs["min_support"], 2)
        self.assertEqual(first_call.kwargs["since_ts"], 1000.0)

    def test_missing_driver_returns_empty_list(self) -> None:
        miner = GraphPatternMiner()
        self.assertEqual(miner.mine(None), [])

    def test_translator_consumes_miner_output(self) -> None:
        miner = MagicMock()
        miner.mine.return_value = [
            Pattern(
                node_labels=["Herb", "Symptom"],
                rel_types=["TREATS"],
                support=4,
                confidence=0.8,
                last_negative_count=4,
            )
        ]
        translator = FeedbackTranslator(
            pattern_miner=miner,
            neo4j_driver=MagicMock(),  # truthy
        )
        plan = translator.translate(
            [
                {
                    "source_phase": "hypothesis",
                    "severity": "high",
                    "issue_fields": ["dosage"],
                }
            ]
        )
        miner.mine.assert_called_once()
        # mined_patterns 出现在 plan 与 summary
        self.assertEqual(plan.summary["mined_pattern_count"], 1)
        self.assertEqual(len(plan.mined_patterns), 1)
        # bias_text 应包含模式描述
        self.assertEqual(len(plan.prompt_bias_actions), 1)
        bias_text = plan.prompt_bias_actions[0].bias_text
        self.assertIn("(Herb)-[TREATS]->(Symptom)", bias_text)


if __name__ == "__main__":
    unittest.main()
