"""T5.6 — PolicyAdjuster 吸收 AdaptiveTuner 接口的回归测试。

验证：
- ``PolicyAdjuster.tune(metrics)`` 懒加载内嵌的 AdaptiveTuner 并返回参数快照。
- ``current_tuned_parameters()`` 与 ``set_tuned_parameter`` 协同。
- self_learning_engine / adaptive_tuner shim 仍能 re-export 原符号。
- 主链不直接 ``from src.learning.self_learning_engine import``。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.learning.policy_adjuster import PolicyAdjuster

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPolicyAdjusterTuneAbsorption(unittest.TestCase):
    def test_tune_returns_parameter_snapshot(self) -> None:
        adjuster = PolicyAdjuster()
        snap = adjuster.tune({"performance": 0.82, "quality": 0.78})
        self.assertIsInstance(snap, dict)
        self.assertIn("learning_threshold", snap)
        self.assertGreater(len(snap), 0)

    def test_current_tuned_parameters_after_tune(self) -> None:
        adjuster = PolicyAdjuster()
        adjuster.tune({"performance": 0.7})
        snap = adjuster.current_tuned_parameters()
        self.assertGreater(len(snap), 0)
        for v in snap.values():
            self.assertIsInstance(v, float)

    def test_set_tuned_parameter_overrides_value(self) -> None:
        adjuster = PolicyAdjuster()
        adjuster.tune({"performance": 0.5})  # ensure tuner exists
        adjuster.set_tuned_parameter("learning_threshold", 0.65)
        snap = adjuster.current_tuned_parameters()
        self.assertAlmostEqual(snap["learning_threshold"], 0.65, places=5)


class TestSelfLearningEngineShim(unittest.TestCase):
    def test_shim_reexports_legacy_symbols(self) -> None:
        from src.learning.self_learning_engine import (
            LearningRecord,
            SelfLearningEngine,
        )

        self.assertTrue(hasattr(SelfLearningEngine, "learn_from_cycle_reflection"))
        self.assertTrue(hasattr(LearningRecord, "to_dict"))

    def test_adaptive_tuner_shim_reexports(self) -> None:
        from src.learning.adaptive_tuner import AdaptiveTuner

        tuner = AdaptiveTuner()
        self.assertIn("learning_threshold", tuner.current_values())

    def test_shim_under_100_lines(self) -> None:
        path = REPO_ROOT / "src" / "learning" / "self_learning_engine.py"
        line_count = sum(1 for _ in path.open(encoding="utf-8"))
        self.assertLess(
            line_count,
            100,
            f"self_learning_engine.py 必须 <100 行 (当前 {line_count})",
        )

    def test_main_chain_does_not_import_legacy_module(self) -> None:
        """验收门：grep 'from src.learning.self_learning_engine' 在主链 (src/) 0 命中。"""
        pattern = re.compile(r"^from\s+src\.learning\.self_learning_engine\s+import")
        offenders = []
        for py_file in (REPO_ROOT / "src").rglob("*.py"):
            # shim 自己豁免
            if py_file.name == "self_learning_engine.py":
                continue
            try:
                for ln, line in enumerate(py_file.open(encoding="utf-8"), 1):
                    if pattern.match(line.strip()):
                        offenders.append(f"{py_file.relative_to(REPO_ROOT)}:{ln}")
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(
            offenders,
            [],
            f"主链不得直接 import self_learning_engine; 命中: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
