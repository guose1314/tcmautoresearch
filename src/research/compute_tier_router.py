# -*- coding: utf-8 -*-
"""Compute Tier Router — 动态算力分配。

参考 Mixture-of-Depths 思路，在应用层做轻量级成本控制：
  L1 规则层：规则引擎、词典匹配、知识图谱查询
  L2 检索总结层：嵌入检索、文献摘要、统计挖掘
  L3 LLM 深推理层：本地 Qwen 模型（算力最贵）

只有当低层级无法给出足够证据时才向上升级。

用法:
    from src.research.compute_tier_router import ComputeTierRouter, ComputeTier

    router = ComputeTierRouter(config)
    decision = router.decide(task_type="hypothesis", evidence=evidence_dict)
    # decision.tier -> ComputeTier.L1 / L2 / L3
    # decision.reason -> "sufficient_rule_evidence"
    # decision.should_use_llm -> False
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 算力层级
# ─────────────────────────────────────────────────────────────────────────────


class ComputeTier(IntEnum):
    """计算层级，数值越大代价越高。"""
    L1_RULES = 1       # 规则 / 词典 / 图谱
    L2_RETRIEVAL = 2   # 检索 + 统计总结
    L3_LLM = 3         # LLM 深推理


# ─────────────────────────────────────────────────────────────────────────────
# 决策结果
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierDecision:
    """路由决策结果。"""
    tier: ComputeTier
    reason: str
    evidence_scores: Dict[str, float]

    @property
    def should_use_llm(self) -> bool:
        return self.tier == ComputeTier.L3_LLM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.name,
            "tier_level": int(self.tier),
            "reason": self.reason,
            "should_use_llm": self.should_use_llm,
            "evidence_scores": dict(self.evidence_scores),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 任务类型定义 & 默认阈值
# ─────────────────────────────────────────────────────────────────────────────

# 每种任务类型对 L1/L2 层证据充分性的阈值
_DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "hypothesis": {
        "l1_entity_count": 3,        # KG 中相关实体数 ≥ 此值视为 L1 充分
        "l1_relationship_count": 2,  # KG 关系数
        "l1_rule_confidence": 0.6,   # 规则推理置信度
        "l2_retrieval_hits": 3,      # 检索命中数
        "l2_evidence_items": 5,      # 已有证据条目数
    },
    "gap_analysis": {
        "l1_entity_count": 5,
        "l1_relationship_count": 3,
        "l1_rule_confidence": 0.5,
        "l2_retrieval_hits": 5,
        "l2_evidence_items": 8,
    },
    "reflection": {
        "l1_entity_count": 2,
        "l1_relationship_count": 1,
        "l1_rule_confidence": 0.7,
        "l2_retrieval_hits": 2,
        "l2_evidence_items": 3,
    },
    "quality_scoring": {
        "l1_entity_count": 2,
        "l1_relationship_count": 1,
        "l1_rule_confidence": 0.65,
        "l2_retrieval_hits": 2,
        "l2_evidence_items": 3,
    },
    "summarization": {
        "l1_entity_count": 1,
        "l1_relationship_count": 0,
        "l1_rule_confidence": 0.0,
        "l2_retrieval_hits": 1,
        "l2_evidence_items": 2,
    },
    "translation": {
        # 翻译类任务几乎总需要 LLM
        "l1_entity_count": 999,
        "l1_relationship_count": 999,
        "l1_rule_confidence": 1.0,
        "l2_retrieval_hits": 999,
        "l2_evidence_items": 999,
    },
}

# 不在表中的任务类型使用此默认值
_FALLBACK_THRESHOLDS: Dict[str, float] = {
    "l1_entity_count": 3,
    "l1_relationship_count": 2,
    "l1_rule_confidence": 0.6,
    "l2_retrieval_hits": 3,
    "l2_evidence_items": 5,
}


# ─────────────────────────────────────────────────────────────────────────────
# 路由器
# ─────────────────────────────────────────────────────────────────────────────


class ComputeTierRouter:
    """根据已有证据的充分程度决定应使用哪个算力层级。

    Parameters
    ----------
    config : dict, optional
        可选配置覆盖:
        - compute_tier_router.enabled (bool): 是否启用路由（False 时总返回 L3）
        - compute_tier_router.force_tier (str): 强制层级 "L1" / "L2" / "L3"
        - compute_tier_router.thresholds (dict): 按任务类型覆盖阈值
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        raw_config = (config or {}).get("compute_tier_router") or {}
        self.enabled: bool = bool(raw_config.get("enabled", True))
        self._force_tier: Optional[str] = raw_config.get("force_tier")
        self._custom_thresholds: Dict[str, Dict[str, float]] = raw_config.get("thresholds") or {}

    def decide(
        self,
        task_type: str,
        evidence: Optional[Dict[str, Any]] = None,
        *,
        force_tier: Optional[str] = None,
    ) -> TierDecision:
        """评估证据充分性并决定算力层级。

        Parameters
        ----------
        task_type : str
            任务类型，如 "hypothesis", "gap_analysis", "reflection" 等
        evidence : dict, optional
            当前已有证据，可能包含:
            - entity_count (int): KG 中相关实体数
            - relationship_count (int): KG 关系数
            - rule_confidence (float): 规则推理置信度
            - retrieval_hits (int): 检索命中数
            - evidence_items (int): 已有证据条目数
            - kg_coverage (float): 图谱覆盖率 0-1
            - has_rule_result (bool): 规则引擎已产出结果
        force_tier : str, optional
            调用方强制指定层级

        Returns
        -------
        TierDecision
        """
        evidence = evidence or {}

        # 强制覆盖
        forced = force_tier or self._force_tier
        if forced:
            tier = self._parse_tier(forced)
            if tier is not None:
                return TierDecision(
                    tier=tier,
                    reason=f"forced_tier={forced}",
                    evidence_scores={},
                )

        # 未启用时默认 L3
        if not self.enabled:
            return TierDecision(
                tier=ComputeTier.L3_LLM,
                reason="router_disabled",
                evidence_scores={},
            )

        thresholds = self._get_thresholds(task_type)
        scores = self._compute_evidence_scores(evidence, thresholds)

        # L1 判定：规则层证据是否充分
        l1_sufficient = self._check_l1_sufficient(scores, thresholds)
        if l1_sufficient:
            logger.debug(
                "算力路由: %s -> L1 (规则层充分, scores=%s)", task_type, scores,
            )
            return TierDecision(
                tier=ComputeTier.L1_RULES,
                reason="sufficient_rule_evidence",
                evidence_scores=scores,
            )

        # L2 判定：检索层证据是否充分
        l2_sufficient = self._check_l2_sufficient(scores, thresholds)
        if l2_sufficient:
            logger.debug(
                "算力路由: %s -> L2 (检索层充分, scores=%s)", task_type, scores,
            )
            return TierDecision(
                tier=ComputeTier.L2_RETRIEVAL,
                reason="sufficient_retrieval_evidence",
                evidence_scores=scores,
            )

        # L3：需要 LLM 深推理
        logger.debug(
            "算力路由: %s -> L3 (证据不足, scores=%s)", task_type, scores,
        )
        return TierDecision(
            tier=ComputeTier.L3_LLM,
            reason="insufficient_lower_tier_evidence",
            evidence_scores=scores,
        )

    def _get_thresholds(self, task_type: str) -> Dict[str, float]:
        """获取任务类型的阈值配置。"""
        # 优先自定义 > 默认 > 兜底
        custom = self._custom_thresholds.get(task_type)
        if custom:
            return {**_FALLBACK_THRESHOLDS, **custom}
        default = _DEFAULT_THRESHOLDS.get(task_type)
        if default:
            return default
        return dict(_FALLBACK_THRESHOLDS)

    def _compute_evidence_scores(
        self,
        evidence: Dict[str, Any],
        thresholds: Dict[str, float],
    ) -> Dict[str, float]:
        """将原始证据转换为 0-1 归一化分数。"""
        scores: Dict[str, float] = {}

        # 实体数
        entity_count = int(evidence.get("entity_count") or 0)
        threshold = max(thresholds.get("l1_entity_count", 3), 1)
        scores["entity_ratio"] = min(entity_count / threshold, 1.0)

        # 关系数
        rel_count = int(evidence.get("relationship_count") or 0)
        threshold = max(thresholds.get("l1_relationship_count", 2), 1)
        scores["relationship_ratio"] = min(rel_count / threshold, 1.0)

        # 规则置信度
        rule_conf = float(evidence.get("rule_confidence") or 0.0)
        scores["rule_confidence"] = min(rule_conf, 1.0)

        # 检索命中数
        retrieval_hits = int(evidence.get("retrieval_hits") or 0)
        threshold = max(thresholds.get("l2_retrieval_hits", 3), 1)
        scores["retrieval_ratio"] = min(retrieval_hits / threshold, 1.0)

        # 证据条目数
        evidence_items = int(evidence.get("evidence_items") or 0)
        threshold = max(thresholds.get("l2_evidence_items", 5), 1)
        scores["evidence_ratio"] = min(evidence_items / threshold, 1.0)

        # KG 覆盖率（直接 0-1）
        scores["kg_coverage"] = float(evidence.get("kg_coverage") or 0.0)

        # 规则引擎已有结果
        scores["has_rule_result"] = 1.0 if evidence.get("has_rule_result") else 0.0

        return scores

    def _check_l1_sufficient(
        self,
        scores: Dict[str, float],
        thresholds: Dict[str, float],
    ) -> bool:
        """L1 充分条件：规则置信度达标 且 (实体+关系 达标 或 已有规则结果)。"""
        rule_threshold = thresholds.get("l1_rule_confidence", 0.6)

        # 如果规则引擎已经产出了结果，直接认为 L1 充分
        if scores.get("has_rule_result", 0) >= 1.0:
            return True

        # 置信度 + 实体/关系覆盖
        if scores.get("rule_confidence", 0) >= rule_threshold:
            if scores.get("entity_ratio", 0) >= 1.0 and scores.get("relationship_ratio", 0) >= 0.5:
                return True

        return False

    def _check_l2_sufficient(
        self,
        scores: Dict[str, float],
        thresholds: Dict[str, float],
    ) -> bool:
        """L2 充分条件：检索命中达标 且 证据条目达标。"""
        if scores.get("retrieval_ratio", 0) >= 1.0 and scores.get("evidence_ratio", 0) >= 1.0:
            return True
        # KG 高覆盖率也可视为 L2 充分
        if scores.get("kg_coverage", 0) >= 0.7:
            return True
        return False

    @staticmethod
    def _parse_tier(tier_str: str) -> Optional[ComputeTier]:
        """解析层级字符串。"""
        mapping = {
            "l1": ComputeTier.L1_RULES,
            "l1_rules": ComputeTier.L1_RULES,
            "l2": ComputeTier.L2_RETRIEVAL,
            "l2_retrieval": ComputeTier.L2_RETRIEVAL,
            "l3": ComputeTier.L3_LLM,
            "l3_llm": ComputeTier.L3_LLM,
        }
        return mapping.get(tier_str.lower().strip())
