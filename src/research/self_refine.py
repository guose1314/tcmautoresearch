"""J-4 Self-Refine：通用的"评分 → 修订 → 再评分"自修订原语。

设计目标:
  - 与具体 LLM/规则解耦：scorer / refiner 均为 callable，调用方注入
  - 纯函数式 + dataclass 结果，便于落 metadata 与对比 quality delta
  - 提供默认 deterministic scorer/refiner，使 hypothesis/publish 在没有 LLM
    时也能跑出可观测的 self_refine 元数据，不破坏既有 fallback 路径

公开 API:
  - SelfRefineRound / SelfRefineResult dataclass
  - SELF_REFINE_CONTRACT_VERSION
  - default_text_quality_scorer / default_structural_refiner
  - run_self_refine(initial_text, *, scorer=, refiner=, max_rounds=, min_delta=)
  - build_self_refine_metadata(result)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

SELF_REFINE_CONTRACT_VERSION = "self-refine-v1"

# 默认参数：保守一点，避免在真实 phase 中放大调用次数
DEFAULT_MAX_ROUNDS = 2
DEFAULT_MIN_DELTA = 0.0  # 只要不变差就接受，与 Phase I-4 fallback 同源理念

# 默认结构化打分关键词（中医学术写作 / 论证常见信号）
_STRUCTURAL_KEYWORDS = (
    "证据", "结论", "理由", "假说", "依据", "出处", "对照",
    "病机", "证候", "治法", "方义",
)


def _as_text(value: Any) -> str:
    return str(value or "")


def default_text_quality_scorer(text: str) -> float:
    """Deterministic 0..1 文本质量打分，用作默认 scorer。

    维度（线性加权）:
      - length_score:    0..1 ≈ min(1, len/600)
      - keyword_density: 命中 _STRUCTURAL_KEYWORDS 的比例
      - sentence_score:  0..1 ≈ min(1, sentence_count/4)
    """
    body = _as_text(text).strip()
    if not body:
        return 0.0
    length_score = min(1.0, len(body) / 600.0)
    hit = sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in body)
    keyword_density = min(1.0, hit / max(1, len(_STRUCTURAL_KEYWORDS) // 2))
    sentences = [seg for seg in re.split(r"[。！？!?；;\n]", body) if seg.strip()]
    sentence_score = min(1.0, len(sentences) / 4.0)
    composite = 0.4 * length_score + 0.4 * keyword_density + 0.2 * sentence_score
    return round(min(1.0, max(0.0, composite)), 4)


def default_structural_refiner(text: str, score: float, round_index: int) -> str:
    """默认 refiner：基于打分追加结构化补充段，不破坏原文。

    设计为幂等 + 可追加：每轮只追加一种类型的补充，避免重复堆砌相同模板。
    """
    body = _as_text(text).rstrip()
    appendices: List[str] = []
    if "证据" not in body and round_index == 0:
        appendices.append("【证据补充】请补充至少 2 条文献证据并标注出处。")
    if "结论" not in body and round_index <= 1:
        appendices.append("【结论收束】请用一句话明确给出可证伪的结论。")
    if score < 0.5 and "理由" not in body:
        appendices.append("【理由展开】请扩展病机/治法理由链，说明因果。")
    if not appendices:
        appendices.append("【自修订】文本已较完整，可在后续轮次微调表述。")
    return body + "\n\n" + "\n".join(appendices)


@dataclass
class SelfRefineRound:
    """一轮自修订的轨迹。"""

    round_index: int = 0
    text: str = ""
    score: float = 0.0
    delta: float = 0.0  # 与上一轮 score 的差


@dataclass
class SelfRefineResult:
    """run_self_refine 的标准化输出。"""

    rounds: List[SelfRefineRound] = field(default_factory=list)
    initial_score: float = 0.0
    final_score: float = 0.0
    quality_delta: float = 0.0  # final_score - initial_score
    accepted: bool = False  # 是否接受最终版本（>= initial_score - min_delta）
    final_text: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rounds": [asdict(r) for r in self.rounds],
            "initial_score": self.initial_score,
            "final_score": self.final_score,
            "quality_delta": self.quality_delta,
            "accepted": self.accepted,
            "final_text": self.final_text,
            "reason": self.reason,
            "contract_version": SELF_REFINE_CONTRACT_VERSION,
        }


def run_self_refine(
    initial_text: Any,
    *,
    scorer: Optional[Callable[[str], float]] = None,
    refiner: Optional[Callable[[str, float, int], str]] = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    min_delta: float = DEFAULT_MIN_DELTA,
) -> SelfRefineResult:
    """对 initial_text 执行最多 max_rounds 轮自修订。

    决策规则:
      - 每轮调用 refiner(text, score, round_index) → 新文本，再 scorer → 新 score
      - 若新 score 比当前最佳更高，则更新最佳并继续
      - 若 refiner 抛异常或 scorer 抛异常，立即终止，沿用此前最佳并标记 reason
      - 最终 accepted = final_score >= initial_score - min_delta
    """
    body = _as_text(initial_text).strip()
    score_fn = scorer or default_text_quality_scorer
    refine_fn = refiner or default_structural_refiner
    try:
        rounds_cap = max(0, int(max_rounds))
    except (TypeError, ValueError):
        rounds_cap = DEFAULT_MAX_ROUNDS
    try:
        threshold = float(min_delta)
    except (TypeError, ValueError):
        threshold = DEFAULT_MIN_DELTA

    try:
        initial_score = float(score_fn(body))
    except Exception:
        return SelfRefineResult(
            rounds=[],
            initial_score=0.0,
            final_score=0.0,
            quality_delta=0.0,
            accepted=False,
            final_text=body,
            reason="scorer_failed",
        )

    best_text = body
    best_score = initial_score
    rounds: List[SelfRefineRound] = [
        SelfRefineRound(round_index=0, text=body, score=round(initial_score, 4), delta=0.0)
    ]
    reason = "no_rounds"

    for index in range(1, rounds_cap + 1):
        try:
            candidate = _as_text(refine_fn(best_text, best_score, index - 1))
        except Exception:
            reason = f"refiner_failed_round_{index}"
            break
        try:
            candidate_score = float(score_fn(candidate))
        except Exception:
            reason = f"scorer_failed_round_{index}"
            break
        delta = round(candidate_score - best_score, 4)
        rounds.append(
            SelfRefineRound(
                round_index=index,
                text=candidate,
                score=round(candidate_score, 4),
                delta=delta,
            )
        )
        if candidate_score > best_score:
            best_text = candidate
            best_score = candidate_score
            reason = f"improved_round_{index}"
        else:
            reason = f"plateau_round_{index}"
            break  # 没有提升就停，保持最小副作用

    quality_delta = round(best_score - initial_score, 4)
    accepted = best_score >= initial_score - threshold
    return SelfRefineResult(
        rounds=rounds,
        initial_score=round(initial_score, 4),
        final_score=round(best_score, 4),
        quality_delta=quality_delta,
        accepted=bool(accepted),
        final_text=best_text,
        reason=reason,
    )


def build_self_refine_metadata(result: SelfRefineResult) -> Dict[str, Any]:
    """将 SelfRefineResult 折叠成 phase metadata 字段集。

    Phase 端约定字段:
      self_refine_initial_score / self_refine_final_score /
      self_refine_quality_delta / self_refine_round_count /
      self_refine_accepted / self_refine_reason / self_refine_trace
    """
    return {
        "self_refine_initial_score": result.initial_score,
        "self_refine_final_score": result.final_score,
        "self_refine_quality_delta": result.quality_delta,
        "self_refine_round_count": max(0, len(result.rounds) - 1),
        "self_refine_accepted": bool(result.accepted),
        "self_refine_reason": result.reason,
        "self_refine_trace": [asdict(r) for r in result.rounds],
        "self_refine_contract_version": SELF_REFINE_CONTRACT_VERSION,
    }


__all__ = [
    "SELF_REFINE_CONTRACT_VERSION",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_MIN_DELTA",
    "SelfRefineRound",
    "SelfRefineResult",
    "default_text_quality_scorer",
    "default_structural_refiner",
    "run_self_refine",
    "build_self_refine_metadata",
]
