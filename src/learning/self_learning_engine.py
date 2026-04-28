"""T5.6 — ``self_learning_engine`` 兼容 shim（下版本删除）。

历史背景
========

旧版 ``SelfLearningEngine`` 曾是 838 行单体类，承担：

1. **调参 (AdaptiveTuner)** — 已迁移至 :mod:`src.learning.policy_adjuster`
   及内部包 :mod:`src.learning.policy_adjuster_internals.adaptive_tuner`。
2. **图谱模式挖掘** — 已迁移至 :mod:`src.learning.graph_pattern_miner`
   (LFITL 上下文，T5.2)。
3. **质量评估反馈** — 由 :class:`PolicyAdjuster.ingest_cycle_assessment`
   接管 (T5.1)。

本文件仅保留 ``LearningRecord`` / ``SelfLearningEngine`` 两个名字以维持
现有测试、研究流水线 ``_try_import`` 兜底路径的二进制兼容。

**任何新代码不得直接 import 本模块。** 主链导入将走：

* 调参 → :class:`src.learning.policy_adjuster.PolicyAdjuster`
* 挖掘 → :class:`src.learning.graph_pattern_miner.GraphPatternMiner`

验收门：``grep "from src.learning.self_learning_engine"`` 在主链命中数为 0
（仅 tests/* 和本 shim 文件本身允许命中）。
"""

from __future__ import annotations

from src.learning.policy_adjuster_internals.self_learning_legacy import (  # noqa: F401
    LearningRecord,
    SelfLearningEngine,
)

__all__ = ["LearningRecord", "SelfLearningEngine"]
