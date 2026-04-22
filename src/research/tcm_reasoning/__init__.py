"""TCM reasoning sub-domain — 中医专属推理引擎。

把"同病异治 / 异病同治 / 三因制宜 / 方证对应 / 君臣佐使"等中医核心方法
显式建模为可审计的 trace + rules，可被 reflect 阶段评分回收。
"""

from .trace_contract import (
    REASONING_PATTERNS,
    PATTERN_TONGBING_YIZHI,
    PATTERN_YIBING_TONGZHI,
    PATTERN_SANYIN_ZHIYI,
    PATTERN_FANGZHENG_DUIYING,
    PATTERN_JUNCHEN_ZUOSHI,
    TCM_REASONING_CONTRACT_VERSION,
    TCMReasoningPremise,
    TCMReasoningStep,
    TCMReasoningTrace,
)
from .tcm_reasoning_service import (
    DEFAULT_RULE_NAMES,
    TCMReasoningRule,
    apply_rule,
    build_default_rules,
    build_tcm_reasoning_metadata,
    rule_fangzheng_duiying,
    rule_junchen_zuoshi,
    rule_sanyin_zhiyi,
    rule_tongbing_yizhi,
    rule_yibing_tongzhi,
    run_tcm_reasoning,
)

__all__ = [
    "REASONING_PATTERNS",
    "PATTERN_TONGBING_YIZHI",
    "PATTERN_YIBING_TONGZHI",
    "PATTERN_SANYIN_ZHIYI",
    "PATTERN_FANGZHENG_DUIYING",
    "PATTERN_JUNCHEN_ZUOSHI",
    "TCM_REASONING_CONTRACT_VERSION",
    "TCMReasoningPremise",
    "TCMReasoningStep",
    "TCMReasoningTrace",
    "DEFAULT_RULE_NAMES",
    "TCMReasoningRule",
    "apply_rule",
    "build_default_rules",
    "build_tcm_reasoning_metadata",
    "rule_fangzheng_duiying",
    "rule_junchen_zuoshi",
    "rule_sanyin_zhiyi",
    "rule_tongbing_yizhi",
    "rule_yibing_tongzhi",
    "run_tcm_reasoning",
]
