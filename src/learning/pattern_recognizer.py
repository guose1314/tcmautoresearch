# src/learning/pattern_recognizer.py
"""
模式识别器 - 从历史数据中自动发现频率、序列、相关性与异常模式。

职责：
- 频率模式：发现高频实体/术语
- 序列模式：在迭代历史中识别重复出现的处理序列
- 相关性模式：分析特征间线性相关关系
- 异常模式：使用 Z-score 检测统计离群点
"""
from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    FREQUENCY    = "frequency"      # 高频特征
    SEQUENCE     = "sequence"       # 时序/序列模式
    CORRELATION  = "correlation"    # 特征间相关
    ANOMALY      = "anomaly"        # 统计离群


@dataclass
class DiscoveredPattern:
    """单条已发现模式的元数据及证据。"""
    pattern_id: str
    pattern_type: PatternType
    description: str
    confidence: float                        # 0-1
    frequency: int = 0                       # 出现次数（频率/序列类有意义）
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    examples: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "confidence": round(self.confidence, 4),
            "frequency": self.frequency,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "examples": self.examples[:5],   # 最多 5 个示例
            "metadata": self.metadata,
        }


class PatternRecognizer:
    """
    模式识别器：对流式上下文数据执行多维模式挖掘。

    使用示例
    --------
    >>> recognizer = PatternRecognizer(min_frequency=3)
    >>> patterns = recognizer.analyze(context)
    >>> for p in patterns:
    ...     print(p.description, p.confidence)
    """

    # 滑动窗口大小（用于序列分析）
    _SEQ_WINDOW = 3

    def __init__(
        self,
        min_frequency: int = 2,
        anomaly_z_threshold: float = 2.5,
        correlation_min: float = 0.6,
        history_limit: int = 500,
    ):
        self._min_freq = min_frequency
        self._z_thresh = anomaly_z_threshold
        self._corr_min = correlation_min
        self._history_limit = history_limit

        # 历史积累
        self._entity_counter: Counter = Counter()
        self._seq_counter: Counter = Counter()
        self._feature_history: Dict[str, List[float]] = defaultdict(list)
        self._context_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def analyze(self, context: Dict[str, Any]) -> List[DiscoveredPattern]:
        """
        分析单个上下文，返回本次检测到的所有模式。
        同时将上下文累入历史窗口供后续分析。
        """
        self._ingest(context)
        patterns: List[DiscoveredPattern] = []
        patterns.extend(self._find_frequency_patterns())
        patterns.extend(self._find_sequence_patterns())
        patterns.extend(self._find_correlation_patterns())
        patterns.extend(self._detect_anomaly_patterns(context))
        logger.debug("本次识别到 %d 条模式", len(patterns))
        return patterns

    def get_top_patterns(
        self,
        n: int = 10,
        pattern_type: Optional[PatternType] = None,
    ) -> List[DiscoveredPattern]:
        """返回置信度最高的 n 条模式，可按类型过滤。"""
        all_patterns = self.analyze({})          # 不传入新数据，仅汇总已有历史
        if pattern_type:
            all_patterns = [p for p in all_patterns if p.pattern_type == pattern_type]
        all_patterns.sort(key=lambda p: (-p.confidence, -p.frequency))
        return all_patterns[:n]

    # ------------------------------------------------------------------
    # 数据摄入
    # ------------------------------------------------------------------

    def _ingest(self, context: Dict[str, Any]) -> None:
        """将上下文特征累入历史窗口。"""
        if not context:
            return

        entities = context.get("entities", [])
        self._ingest_entities(entities)
        self._ingest_topic_sequence(context)
        self._ingest_numeric_features(context, entities)
        self._trim_feature_history()

    def _ingest_entities(self, entities: Any) -> None:
        """累积实体频率信息。"""
        if isinstance(entities, list):
            for entity in entities:
                key = entity.get("name", "") if isinstance(entity, dict) else str(entity)
                if key:
                    self._entity_counter[key] += 1
            return

        if isinstance(entities, dict):
            for name in entities:
                self._entity_counter[str(name)] += 1

    def _ingest_topic_sequence(self, context: Dict[str, Any]) -> None:
        """累积 topic 序列并更新 n-gram 计数。"""
        topic = context.get("topic", context.get("query", ""))
        if not topic or not isinstance(topic, str):
            return

        self._context_history.append({"topic": topic})
        if len(self._context_history) > self._history_limit:
            self._context_history.pop(0)

        topics = [item["topic"] for item in self._context_history]
        for window in _ngrams(topics, self._SEQ_WINDOW):
            self._seq_counter[window] += 1

    def _ingest_numeric_features(self, context: Dict[str, Any], entities: Any) -> None:
        """累积数值特征历史。"""
        perf = context.get("performance_score")
        conf = context.get("confidence_score")
        ent_cnt = len(entities) if isinstance(entities, (list, dict)) else 0

        if perf is not None:
            self._feature_history["performance"].append(float(perf))
        if conf is not None:
            self._feature_history["confidence"].append(float(conf))
        self._feature_history["entity_count"].append(float(ent_cnt))

    def _trim_feature_history(self) -> None:
        """按 history_limit 裁剪特征历史。"""
        for values in self._feature_history.values():
            if len(values) > self._history_limit:
                del values[0]

    # ------------------------------------------------------------------
    # 频率模式
    # ------------------------------------------------------------------

    def _find_frequency_patterns(self) -> List[DiscoveredPattern]:
        patterns = []
        total = sum(self._entity_counter.values()) or 1
        for entity, count in self._entity_counter.most_common(20):
            if count < self._min_freq:
                break
            freq_ratio = count / total
            confidence = min(freq_ratio * 10, 1.0)          # 频率越高置信越高，封顶 1.0
            p = DiscoveredPattern(
                pattern_id=f"freq_{_safe_id(entity)}",
                pattern_type=PatternType.FREQUENCY,
                description=f"高频实体/术语「{entity}」出现 {count} 次，占比 {freq_ratio:.1%}",
                confidence=confidence,
                frequency=count,
                examples=[entity],
                metadata={"ratio": round(freq_ratio, 4)},
            )
            patterns.append(p)
        return patterns

    # ------------------------------------------------------------------
    # 序列模式
    # ------------------------------------------------------------------

    def _find_sequence_patterns(self) -> List[DiscoveredPattern]:
        patterns = []
        total = sum(self._seq_counter.values()) or 1
        for seq, count in self._seq_counter.most_common(10):
            if count < self._min_freq:
                break
            confidence = min(count / total * 15, 1.0)
            label = " → ".join(seq)
            p = DiscoveredPattern(
                pattern_id=f"seq_{'_'.join(_safe_id(s) for s in seq)}",
                pattern_type=PatternType.SEQUENCE,
                description=f"重复出现处理序列「{label}」，计 {count} 次",
                confidence=confidence,
                frequency=count,
                examples=list(seq),
                metadata={"seq_len": len(seq)},
            )
            patterns.append(p)
        return patterns

    # ------------------------------------------------------------------
    # 相关性模式
    # ------------------------------------------------------------------

    def _find_correlation_patterns(self) -> List[DiscoveredPattern]:
        """计算特征对 Pearson 相关系数，超过阈值则报告。"""
        patterns = []
        keys = list(self._feature_history.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                ka, kb = keys[i], keys[j]
                a, b = self._feature_history[ka], self._feature_history[kb]
                n = min(len(a), len(b))
                if n < 5:
                    continue
                r = _pearson(a[-n:], b[-n:])
                if abs(r) >= self._corr_min:
                    direction = "正" if r > 0 else "负"
                    p = DiscoveredPattern(
                        pattern_id=f"corr_{ka}_{kb}",
                        pattern_type=PatternType.CORRELATION,
                        description=(
                            f"特征「{ka}」与「{kb}」存在强{direction}相关 "
                            f"(r={r:.3f}, n={n})"
                        ),
                        confidence=min(abs(r), 1.0),
                        frequency=n,
                        metadata={"pearson_r": round(r, 4), "feature_a": ka, "feature_b": kb},
                    )
                    patterns.append(p)
        return patterns

    # ------------------------------------------------------------------
    # 异常模式
    # ------------------------------------------------------------------

    def _detect_anomaly_patterns(self, context: Dict[str, Any]) -> List[DiscoveredPattern]:
        """对当前上下文中的数值特征做 Z-score 检测。"""
        patterns = []
        checks = {
            "performance_score": context.get("performance_score"),
            "confidence_score": context.get("confidence_score"),
            "entity_count": len(context.get("entities", [])) if context else None,
        }
        for feat, val in checks.items():
            if val is None:
                continue
            history = self._feature_history.get(feat, [])
            if len(history) < 10:
                continue
            z = _zscore(float(val), history)
            if abs(z) >= self._z_thresh:
                direction = "异常高" if z > 0 else "异常低"
                p = DiscoveredPattern(
                    pattern_id=f"anomaly_{feat}_{datetime.now().strftime('%H%M%S')}",
                    pattern_type=PatternType.ANOMALY,
                    description=(
                        f"特征「{feat}」当前值 {val:.3f} 为{direction} "
                        f"(Z={z:.2f}，均值={_mean(history):.3f})"
                    ),
                    confidence=min(abs(z) / (self._z_thresh * 2), 1.0),
                    frequency=1,
                    examples=[val],
                    metadata={"z_score": round(z, 3), "feature": feat, "value": float(val)},
                )
                patterns.append(p)
        return patterns


# ------------------------------------------------------------------
# 纯函数工具
# ------------------------------------------------------------------

def _ngrams(seq: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    return [tuple(seq[i: i + n]) for i in range(len(seq) - n + 1)]


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    variance = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(variance)


def _zscore(val: float, history: List[float]) -> float:
    m, s = _mean(history), _std(history)
    return (val - m) / s if s > 1e-9 else 0.0


def _pearson(a: List[float], b: List[float]) -> float:
    n = len(a)
    ma, mb = _mean(a), _mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den_a = math.sqrt(sum((v - ma) ** 2 for v in a))
    den_b = math.sqrt(sum((v - mb) ** 2 for v in b))
    if den_a * den_b < 1e-9:
        return 0.0
    return num / (den_a * den_b)


def _safe_id(s: str) -> str:
    """将任意字符串压缩为合法 ID 片段（最多 20 字符）。"""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)[:20]
