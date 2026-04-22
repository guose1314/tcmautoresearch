"""RLAIF-lite 偏好对数据集构建（Phase M-3）。

把 fallback quality matrix 中"baseline vs optimized"的产出对，转成
DPO/RLAIF-lite/LoRA 训练用的 (chosen, rejected) 偏好对。

公开 API：
  - RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION
  - PreferencePair / PreferenceDataset / LoRADatasetSpec
  - build_preference_pair(...)
  - build_dataset_from_fallback_records(records, *, min_score_delta=0.0)
  - export_dataset_to_jsonl(dataset, path)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION = "rlaif-preference-dataset-v1"

PathLike = Union[str, Path]


@dataclass
class PreferencePair:
    """一条偏好训练样本。"""

    prompt: str
    chosen: str
    rejected: str
    score_chosen: float
    score_rejected: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def score_delta(self) -> float:
        return float(self.score_chosen) - float(self.score_rejected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "score_chosen": float(self.score_chosen),
            "score_rejected": float(self.score_rejected),
            "score_delta": self.score_delta,
            "metadata": dict(self.metadata),
        }


@dataclass
class LoRADatasetSpec:
    """LoRA 微调时使用的最小数据集元描述。"""

    name: str
    base_model: str
    pair_count: int
    contract_version: str = RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_model": self.base_model,
            "pair_count": self.pair_count,
            "contract_version": self.contract_version,
            "extra": dict(self.extra),
        }


@dataclass
class PreferenceDataset:
    """偏好对集合 + 元数据。"""

    pairs: List[PreferencePair] = field(default_factory=list)
    spec: Optional[LoRADatasetSpec] = None
    contract_version: str = RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION

    def __len__(self) -> int:
        return len(self.pairs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "pair_count": len(self.pairs),
            "pairs": [p.to_dict() for p in self.pairs],
            "spec": self.spec.to_dict() if self.spec else None,
        }


def build_preference_pair(
    *,
    prompt: str,
    chosen: str,
    rejected: str,
    score_chosen: float,
    score_rejected: float,
    metadata: Optional[Mapping[str, Any]] = None,
) -> PreferencePair:
    if not prompt:
        raise ValueError("prompt 不能为空")
    if chosen == rejected:
        raise ValueError("chosen 与 rejected 不能相同")
    if float(score_chosen) < float(score_rejected):
        raise ValueError(
            f"score_chosen ({score_chosen}) 必须 >= score_rejected ({score_rejected})"
        )
    return PreferencePair(
        prompt=str(prompt),
        chosen=str(chosen),
        rejected=str(rejected),
        score_chosen=float(score_chosen),
        score_rejected=float(score_rejected),
        metadata=dict(metadata or {}),
    )


def _extract_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("text", "output", "content", "answer"):
            if key in value and isinstance(value[key], str):
                return value[key]
    return str(value)


def build_dataset_from_fallback_records(
    records: Iterable[Mapping[str, Any]],
    *,
    min_score_delta: float = 0.0,
    spec: Optional[LoRADatasetSpec] = None,
) -> PreferenceDataset:
    """从 FallbackQualityRecord 风格的 dict 列表里抽取偏好对。

    期望每条 record 至少含：
      - prompt: str
      - baseline_output / optimized_output: str 或带 'text' 的 dict
      - baseline_score / optimized_score: float
      - acceptance: 可选 bool（False 时仍可生成偏好对，但记入 metadata）
    """
    pairs: List[PreferencePair] = []
    for raw in records:
        prompt = _extract_text(raw.get("prompt"))
        baseline = _extract_text(raw.get("baseline_output"))
        optimized = _extract_text(raw.get("optimized_output"))
        try:
            baseline_score = float(raw.get("baseline_score"))
            optimized_score = float(raw.get("optimized_score"))
        except (TypeError, ValueError):
            continue
        if not prompt or not baseline or not optimized:
            continue
        if baseline == optimized:
            continue
        # 选择得分更高的一方为 chosen
        if optimized_score >= baseline_score:
            chosen, rejected = optimized, baseline
            score_chosen, score_rejected = optimized_score, baseline_score
        else:
            chosen, rejected = baseline, optimized
            score_chosen, score_rejected = baseline_score, optimized_score
        if (score_chosen - score_rejected) < float(min_score_delta):
            continue
        metadata = {
            "acceptance": raw.get("acceptance"),
            "reason": raw.get("reason"),
            "source_action": raw.get("action"),
        }
        pairs.append(
            PreferencePair(
                prompt=prompt,
                chosen=chosen,
                rejected=rejected,
                score_chosen=score_chosen,
                score_rejected=score_rejected,
                metadata=metadata,
            )
        )
    final_spec = spec
    if final_spec is not None:
        final_spec = LoRADatasetSpec(
            name=spec.name,
            base_model=spec.base_model,
            pair_count=len(pairs),
            contract_version=spec.contract_version,
            extra=dict(spec.extra),
        )
    return PreferenceDataset(pairs=pairs, spec=final_spec)


def export_dataset_to_jsonl(dataset: PreferenceDataset, path: PathLike) -> Path:
    """把 dataset 序列化为 jsonl（每行一个 PreferencePair）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for pair in dataset.pairs:
            fh.write(json.dumps(pair.to_dict(), ensure_ascii=False) + "\n")
    return target
