"""分层 Dossier 压缩器 — 为 7B 模型提供多级上下文压缩。

DossierLayerCompressor 将研究上下文压缩为三个层级：
- Layer 0 (critical): 仅核心事实，≤512 tokens（用于紧急/简单调用）
- Layer 1 (core): 核心证据 + 实体 + 假说摘要，≤1536 tokens（标准调用）
- Layer 2 (full): 完整上下文，≤3072 tokens（复杂推理调用）

选择哪一层由 DynamicInvocationStrategy 的 budget 决策驱动。

用法::

    compressor = DossierLayerCompressor()
    layers = compressor.compress(dossier_sections)
    # layers.get_layer(0) → 512 token 以内的精简摘要
    # layers.get_layer(1) → 1536 token 以内的核心内容
    # layers.get_layer(2) → 完整内容
    # layers.select_for_budget(available_tokens) → 自动选层
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 层级配置 ──────────────────────────────────────────────────────────────

_LAYER_BUDGETS: Dict[int, int] = {
    0: 512,   # critical
    1: 1536,  # core
    2: 3072,  # full
}

_LAYER_NAMES: Dict[int, str] = {
    0: "critical",
    1: "core",
    2: "full",
}

# 各层级包含的 section 及其优先级权重
_LAYER_SECTION_SPECS: Dict[int, List[Tuple[str, float]]] = {
    # Layer 0: 仅最关键信息
    0: [
        ("objective", 0.30),
        ("evidence_summary", 0.40),
        ("hypothesis_summary", 0.30),
    ],
    # Layer 1: 核心内容
    1: [
        ("objective", 0.10),
        ("evidence", 0.25),
        ("entities", 0.20),
        ("hypothesis_history", 0.15),
        ("graph_summary", 0.15),
        ("terminology", 0.15),
    ],
    # Layer 2: 完整内容
    2: [
        ("objective", 0.06),
        ("evidence", 0.22),
        ("entities", 0.12),
        ("graph", 0.12),
        ("terminology", 0.08),
        ("version_info", 0.08),
        ("controversies", 0.10),
        ("hypothesis_history", 0.10),
        ("corpus_digest", 0.12),
    ],
}

# token 估算：中文约 1.5 字符/token
_CHARS_PER_TOKEN_CN = 1.5
_CHARS_PER_TOKEN_EN = 4.0


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数。"""
    if not text:
        return 0
    # 简单启发式：按中文字符占比估算
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en_chars = len(text) - cn_chars
    return int(cn_chars / _CHARS_PER_TOKEN_CN + en_chars / _CHARS_PER_TOKEN_EN)


def _trim_to_tokens(text: str, max_tokens: int) -> str:
    """将文本截断到近似 max_tokens。"""
    if not text:
        return ""
    estimated = _estimate_tokens(text)
    if estimated <= max_tokens:
        return text
    # 按比例截断
    ratio = max_tokens / estimated
    target_chars = int(len(text) * ratio * 0.95)  # 留 5% 余量
    return text[:target_chars] + "\n[...]"


@dataclass
class CompressedLayer:
    """单层压缩结果。"""

    level: int
    name: str
    text: str
    estimated_tokens: int
    sections_included: List[str]

    def __bool__(self) -> bool:
        return bool(self.text.strip())


@dataclass
class LayeredDossier:
    """多层压缩后的 dossier。"""

    layers: Dict[int, CompressedLayer] = field(default_factory=dict)
    source_sections: List[str] = field(default_factory=list)

    def get_layer(self, level: int) -> Optional[CompressedLayer]:
        """获取指定层级。"""
        return self.layers.get(level)

    def select_for_budget(self, available_tokens: int) -> CompressedLayer:
        """根据可用 token 预算自动选择最大可用层。

        选择逻辑：选可用层中 estimated_tokens <= available_tokens 的最高层。
        若所有层都超预算，返回 Layer 0 的截断版本。
        """
        best: Optional[CompressedLayer] = None
        for level in sorted(self.layers.keys(), reverse=True):
            layer = self.layers[level]
            if layer.estimated_tokens <= available_tokens:
                return layer
            if best is None:
                best = layer

        # 所有层都超预算 → 截断 Layer 0
        layer_0 = self.layers.get(0)
        if layer_0:
            trimmed_text = _trim_to_tokens(layer_0.text, available_tokens)
            return CompressedLayer(
                level=0,
                name="critical_trimmed",
                text=trimmed_text,
                estimated_tokens=min(layer_0.estimated_tokens, available_tokens),
                sections_included=layer_0.sections_included,
            )

        # 完全无内容
        return CompressedLayer(level=0, name="empty", text="", estimated_tokens=0, sections_included=[])

    @property
    def max_level(self) -> int:
        return max(self.layers.keys()) if self.layers else 0

    def to_metadata(self) -> Dict[str, Any]:
        """返回层级元数据（用于日志/诊断）。"""
        return {
            "layer_count": len(self.layers),
            "source_section_count": len(self.source_sections),
            "layers": {
                level: {
                    "name": layer.name,
                    "estimated_tokens": layer.estimated_tokens,
                    "sections": layer.sections_included,
                }
                for level, layer in sorted(self.layers.items())
            },
        }


class DossierLayerCompressor:
    """将 dossier sections 压缩为多层级结构。

    Parameters
    ----------
    layer_budgets :
        可选覆盖各层 token 预算。
    """

    def __init__(self, layer_budgets: Optional[Dict[int, int]] = None) -> None:
        self._budgets = layer_budgets or dict(_LAYER_BUDGETS)

    def compress(self, sections: Dict[str, str]) -> LayeredDossier:
        """将原始 sections 压缩为 LayeredDossier。

        Parameters
        ----------
        sections :
            section_name → 文本内容。
            常见 keys: objective, evidence, entities, graph, terminology,
            version_info, controversies, hypothesis_history, corpus_digest,
            evidence_summary, hypothesis_summary, graph_summary
        """
        result = LayeredDossier(source_sections=list(sections.keys()))

        for level, budget in sorted(self._budgets.items()):
            layer = self._compress_layer(sections, level, budget)
            result.layers[level] = layer

        return result

    def _compress_layer(self, sections: Dict[str, str], level: int, budget: int) -> CompressedLayer:
        """压缩单个层级。"""
        spec = _LAYER_SECTION_SPECS.get(level, _LAYER_SECTION_SPECS[2])
        parts: List[str] = []
        included: List[str] = []

        for section_name, weight in spec:
            # 查找 section（支持 fallback 名称）
            text = self._resolve_section(sections, section_name)
            if not text:
                continue

            section_budget = int(budget * weight)
            trimmed = _trim_to_tokens(text, section_budget)
            if trimmed.strip():
                parts.append(f"### {section_name}\n{trimmed}")
                included.append(section_name)

        combined = "\n\n".join(parts)
        # 最终整体 budget 约束
        combined = _trim_to_tokens(combined, budget)

        return CompressedLayer(
            level=level,
            name=_LAYER_NAMES.get(level, f"layer_{level}"),
            text=combined,
            estimated_tokens=_estimate_tokens(combined),
            sections_included=included,
        )

    @staticmethod
    def _resolve_section(sections: Dict[str, str], name: str) -> str:
        """解析 section，支持 fallback 名称。"""
        # 直接匹配
        if name in sections:
            return sections[name]

        # 尝试 summary 后缀
        summary_key = f"{name}_summary"
        if summary_key in sections:
            return sections[summary_key]

        # 尝试去掉 _summary 后缀
        if name.endswith("_summary"):
            base_key = name[: -len("_summary")]
            if base_key in sections:
                return sections[base_key]

        return ""
