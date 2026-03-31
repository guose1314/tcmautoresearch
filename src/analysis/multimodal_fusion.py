# src/research/multimodal_fusion.py
"""
多模态融合引擎 - 整合文本、实体、语义图、统计特征四类模态。

核心能力：
- 各模态独立向量化（稀疏词频 / 计数统计 / 图拓扑指标）
- 基于 Softmax-Attention 的自适应权重融合
- 证据聚合：多源支持同一命题时提升置信度
- 输出：融合特征向量 + 置信度分布 + 各模态贡献度报告
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FusionStrategy(str, Enum):
    WEIGHTED_SUM = "weighted_sum"   # 加权求和
    ATTENTION    = "attention"      # Softmax 注意力加权
    MAX_POOL     = "max_pool"       # 逐维取最大值
    PRODUCT      = "product"        # 逐维乘积（强调共识）


@dataclass
class ModalityData:
    """单一模态的输入数据及元信息。"""
    name: str                          # 模态标识：text / entity / graph / stats
    features: Dict[str, float]        # 特征名 → 归一化特征值 (0-1)
    weight: float = 1.0               # 初始权重（会被注意力机制覆盖）
    confidence: float = 1.0           # 模态自身的可信度
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_vector(self, feature_keys: List[str]) -> List[float]:
        """按指定键顺序输出特征向量，缺失键填 0。"""
        return [self.features.get(k, 0.0) for k in feature_keys]


@dataclass
class FusionResult:
    """融合输出结果。"""
    strategy: FusionStrategy
    fused_features: Dict[str, float]     # 融合后的特征
    confidence: float                    # 综合置信度
    modality_weights: Dict[str, float]   # 各模态最终权重
    modality_contributions: Dict[str, float]  # 各模态对最终结果的贡献度
    evidence_score: float                # 证据聚合强度 (0-1)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "fused_features": {k: round(v, 4) for k, v in self.fused_features.items()},
            "confidence": round(self.confidence, 4),
            "modality_weights": {k: round(v, 4) for k, v in self.modality_weights.items()},
            "modality_contributions": {k: round(v, 4) for k, v in self.modality_contributions.items()},
            "evidence_score": round(self.evidence_score, 4),
            "timestamp": self.timestamp,
        }


class MultimodalFusionEngine:
    """
    多模态融合引擎。

    使用示例
    --------
    >>> engine = MultimodalFusionEngine(strategy=FusionStrategy.ATTENTION)
    >>> modalities = engine.extract_modalities(context)
    >>> result = engine.fuse(modalities)
    >>> print(result.confidence, result.modality_weights)
    """

    def __init__(
        self,
        strategy: FusionStrategy = FusionStrategy.ATTENTION,
        temperature: float = 1.0,     # Softmax 温度（越低越集中于最高分模态）
        min_confidence: float = 0.1,  # 置信度低于此值的模态质量降权
    ):
        self._strategy = strategy
        self._temperature = max(temperature, 0.01)
        self._min_conf = min_confidence
        self._fusion_history: List[FusionResult] = []

    # ------------------------------------------------------------------
    # 模态提取
    # ------------------------------------------------------------------

    def extract_modalities(self, context: Dict[str, Any]) -> List[ModalityData]:
        """
        从标准 context 字典中提取四类模态数据。
        缺失的模态将被跳过（不强制要求所有模态都存在）。
        """
        modalities: List[ModalityData] = []

        # ── 文本模态 ──
        text = context.get("processed_text", "")
        if text and isinstance(text, str):
            modalities.append(self._extract_text_modality(text))

        # ── 实体模态 ──
        entities = context.get("entities", [])
        if entities:
            modalities.append(self._extract_entity_modality(entities))

        # ── 语义图模态 ──
        graph = context.get("semantic_graph", {})
        if graph:
            modalities.append(self._extract_graph_modality(graph))

        # ── 统计模态 ──
        perf = context.get("performance_score")
        conf = context.get("confidence_score")
        if perf is not None or conf is not None:
            modalities.append(self._extract_stats_modality(context))

        return modalities

    # ------------------------------------------------------------------
    # 融合主逻辑
    # ------------------------------------------------------------------

    def fuse(
        self,
        modalities: List[ModalityData],
        strategy: Optional[FusionStrategy] = None,
    ) -> FusionResult:
        """
        将多个模态融合为统一表示。

        Parameters
        ----------
        modalities : list[ModalityData]
            待融合的模态列表，可由 extract_modalities() 产生或手动构造。
        strategy : FusionStrategy, optional
            覆盖实例的默认融合策略。
        """
        if not modalities:
            raise ValueError("至少需要一个模态才能执行融合")

        chosen_strategy = strategy or self._strategy
        all_keys = self._union_feature_keys(modalities)
        vectors = {m.name: m.to_vector(all_keys) for m in modalities}
        weights = self._compute_weights(modalities, chosen_strategy, vectors)

        fused_vector = self._apply_strategy(chosen_strategy, vectors, weights, all_keys)
        fused_features = dict(zip(all_keys, fused_vector))

        contributions = self._compute_contributions(modalities, vectors, weights, fused_vector, all_keys)
        evidence = self._compute_evidence_score(modalities, vectors, all_keys)
        confidence = self._compute_overall_confidence(modalities, weights, evidence)

        result = FusionResult(
            strategy=chosen_strategy,
            fused_features=fused_features,
            confidence=confidence,
            modality_weights={m.name: round(weights[m.name], 4) for m in modalities},
            modality_contributions=contributions,
            evidence_score=evidence,
        )
        self._fusion_history.append(result)
        if len(self._fusion_history) > 200:
            self._fusion_history.pop(0)
        logger.debug(
            "融合完成 strategy=%s confidence=%.3f modalities=%s",
            chosen_strategy.value, confidence, [m.name for m in modalities],
        )
        return result

    def get_fusion_history(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._fusion_history]

    # ------------------------------------------------------------------
    # 模态提取内部实现
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_modality(text: str) -> ModalityData:
        length = min(len(text), 10000)
        char_div = len(set(text)) / max(len(text), 1)         # 字符多样性
        digit_ratio = sum(c.isdigit() for c in text) / max(length, 1)
        features = {
            "text_length_norm": min(length / 5000, 1.0),
            "char_diversity": min(char_div, 1.0),
            "digit_density": min(digit_ratio * 5, 1.0),
        }
        return ModalityData(name="text", features=features, weight=1.0, confidence=0.9)

    @staticmethod
    def _extract_entity_modality(entities: Any) -> ModalityData:
        if isinstance(entities, dict):
            entity_list = list(entities.values())
        elif isinstance(entities, list):
            entity_list = entities
        else:
            entity_list = []
        count = len(entity_list)
        type_set: set = set()
        conf_sum = 0.0
        for e in entity_list:
            if isinstance(e, dict):
                type_set.add(e.get("type", "unknown"))
                conf_sum += float(e.get("confidence", 0.5))
        avg_conf = conf_sum / count if count else 0.5
        features = {
            "entity_density": min(count / 20, 1.0),
            "entity_type_diversity": min(len(type_set) / 10, 1.0),
            "entity_avg_confidence": avg_conf,
        }
        return ModalityData(name="entity", features=features, weight=1.0, confidence=avg_conf)

    @staticmethod
    def _extract_graph_modality(graph: Dict[str, Any]) -> ModalityData:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        n_nodes = len(nodes) if isinstance(nodes, (list, dict)) else 0
        n_edges = len(edges) if isinstance(edges, (list, dict)) else 0
        density = n_edges / max(n_nodes * (n_nodes - 1), 1)
        stats = graph.get("graph_statistics", {})
        features = {
            "graph_node_density": min(n_nodes / 50, 1.0),
            "graph_edge_density": min(density, 1.0),
            "graph_connectivity": min(float(stats.get("connected_components", 1)) / 5, 1.0),
        }
        return ModalityData(name="graph", features=features, weight=1.0, confidence=0.85)

    @staticmethod
    def _extract_stats_modality(context: Dict[str, Any]) -> ModalityData:
        perf = float(context.get("performance_score", 0.5))
        conf = float(context.get("confidence_score", 0.5))
        quality = float(context.get("quality_score", 0.5))
        features = {
            "performance": max(0.0, min(perf, 1.0)),
            "confidence": max(0.0, min(conf, 1.0)),
            "quality": max(0.0, min(quality, 1.0)),
        }
        modal_conf = (perf + conf) / 2
        return ModalityData(name="stats", features=features, weight=1.0, confidence=modal_conf)

    # ------------------------------------------------------------------
    # 权重计算
    # ------------------------------------------------------------------

    def _compute_weights(
        self,
        modalities: List[ModalityData],
        strategy: FusionStrategy,
        vectors: Dict[str, List[float]],
    ) -> Dict[str, float]:
        if strategy == FusionStrategy.ATTENTION:
            return self._attention_weights(modalities, vectors)
        # 其他策略用置信度加权
        raw = {m.name: max(m.confidence, self._min_conf) * m.weight for m in modalities}
        total = sum(raw.values()) or 1.0
        return {k: v / total for k, v in raw.items()}

    def _attention_weights(
        self,
        modalities: List[ModalityData],
        vectors: Dict[str, List[float]],
    ) -> Dict[str, float]:
        """Softmax 注意力：以各模态特征 L2 范数作为能量分数。"""
        scores = {}
        for m in modalities:
            vec = vectors[m.name]
            norm = math.sqrt(sum(v * v for v in vec)) if vec else 0.0
            scores[m.name] = (norm * m.confidence) / self._temperature
        # Softmax
        max_s = max(scores.values())
        exp_s = {k: math.exp(v - max_s) for k, v in scores.items()}
        total = sum(exp_s.values()) or 1.0
        return {k: v / total for k, v in exp_s.items()}

    # ------------------------------------------------------------------
    # 融合策略实现
    # ------------------------------------------------------------------

    @staticmethod
    def _union_feature_keys(modalities: List[ModalityData]) -> List[str]:
        keys: List[str] = []
        seen = set()
        for m in modalities:
            for k in m.features:
                if k not in seen:
                    keys.append(k)
                    seen.add(k)
        return keys

    def _apply_strategy(
        self,
        strategy: FusionStrategy,
        vectors: Dict[str, List[float]],
        weights: Dict[str, float],
        keys: List[str],
    ) -> List[float]:
        names = list(vectors.keys())
        dim = len(keys)
        if strategy == FusionStrategy.MAX_POOL:
            result = [0.0] * dim
            for name in names:
                for i, v in enumerate(vectors[name]):
                    result[i] = max(result[i], v * weights[name])
            return result
        if strategy == FusionStrategy.PRODUCT:
            result = [1.0] * dim
            for name in names:
                for i, v in enumerate(vectors[name]):
                    result[i] *= (v * weights[name] + (1 - weights[name]))  # 偏置避免全零
            return result
        # WEIGHTED_SUM 和 ATTENTION 均使用加权求和
        result = [0.0] * dim
        for name in names:
            w = weights[name]
            for i, v in enumerate(vectors[name]):
                result[i] += v * w
        return result

    # ------------------------------------------------------------------
    # 置信度 & 证据
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_evidence_score(
        modalities: List[ModalityData],
        vectors: Dict[str, List[float]],
        keys: List[str],
    ) -> float:
        """
        证据聚合强度：若多个模态在同一特征维度上均给出高值，则证据更强。
        使用逐特征最小值均值作为共识度量。
        """
        if len(modalities) < 2:
            return modalities[0].confidence if modalities else 0.0
        dim = len(keys)
        consensus = 0.0
        for i in range(dim):
            vals = [vectors[m.name][i] for m in modalities]
            consensus += min(vals)
        return consensus / dim if dim else 0.0

    @staticmethod
    def _compute_overall_confidence(
        modalities: List[ModalityData],
        weights: Dict[str, float],
        evidence: float,
    ) -> float:
        weighted_conf = sum(weights[m.name] * m.confidence for m in modalities)
        # 混入证据分提升综合置信度
        blended = 0.7 * weighted_conf + 0.3 * evidence
        return max(0.0, min(1.0, blended))

    @staticmethod
    def _compute_contributions(
        modalities: List[ModalityData],
        vectors: Dict[str, List[float]],
        weights: Dict[str, float],
        fused: List[float],
        keys: List[str],
    ) -> Dict[str, float]:
        """各模态对融合结果的方差贡献度（归一化）。"""
        fused_norm = math.sqrt(sum(v * v for v in fused)) or 1.0
        contribs_raw: Dict[str, float] = {}
        for m in modalities:
            vec = vectors[m.name]
            dot = sum(vec[i] * fused[i] for i in range(len(keys)))
            contribs_raw[m.name] = dot * weights[m.name] / fused_norm
        total = sum(abs(v) for v in contribs_raw.values()) or 1.0
        return {k: abs(v) / total for k, v in contribs_raw.items()}
