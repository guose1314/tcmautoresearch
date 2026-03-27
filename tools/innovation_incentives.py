"""
Innovation incentive mechanism.

This tool evaluates an innovation contribution profile and produces:
1) Weighted innovation score
2) Incentive tier
3) Reward recommendations
4) Improvement suggestions
5) Adaptive learning updates (optional)

Usage:
    python tools/innovation_incentives.py --input docs/templates/innovation-profile.template.json
    python tools/innovation_incentives.py --input profile.json --output output/innovation-incentive-report.json
    python tools/innovation_incentives.py --input profile.json --feedback 4.5
"""

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DIMENSION_WEIGHTS = {
    "novelty": 30,
    "impact": 25,
    "validation": 20,
    "reuse": 15,
    "knowledge_sharing": 10,
}

LEARNING_RATE_DEFAULT = 0.15


TIER_THRESHOLDS = [
    (85, "Pioneer"),
    (70, "Catalyst"),
    (55, "Explorer"),
    (0, "Incubator"),
]


@dataclass
class ContributionProfile:
    title: str
    owner: str
    summary: str
    novelty: int
    impact: int
    validation: int
    reuse: int
    knowledge_sharing: int
    has_tests: bool = False
    has_docs: bool = False
    has_artifact: bool = False
    quality_gate_passed: bool = False
    feedback_score: Optional[float] = None
    linked_files: List[str] = field(default_factory=list)


@dataclass
class IncentiveReport:
    title: str
    owner: str
    score: int
    tier: str
    dimension_scores: Dict[str, int]
    bonus_points: Dict[str, int]
    reward_recommendations: List[str]
    improvement_actions: List[str]
    linked_files: List[str]
    active_weights: Dict[str, int]
    adaptive_learning: Dict[str, object]


@dataclass
class AdaptiveLearningState:
    dimension_weights: Dict[str, int]
    learning_rate: float = LEARNING_RATE_DEFAULT
    samples: int = 0


def _normalized_weights(weights: Dict[str, int]) -> Dict[str, int]:
    # Keep the score system stable by always normalizing to 100.
    base = {
        k: max(5, int(weights.get(k, DIMENSION_WEIGHTS[k])))
        for k in DIMENSION_WEIGHTS
    }
    total = sum(base.values())
    if total <= 0:
        return dict(DIMENSION_WEIGHTS)

    scaled = {
        k: max(5, round(v * 100 / total))
        for k, v in base.items()
    }
    diff = 100 - sum(scaled.values())
    if diff != 0:
        ordered = sorted(scaled.keys(), key=lambda x: scaled[x], reverse=(diff > 0))
        idx = 0
        while diff != 0 and ordered:
            key = ordered[idx % len(ordered)]
            next_val = scaled[key] + (1 if diff > 0 else -1)
            if next_val >= 5:
                scaled[key] = next_val
                diff += -1 if diff > 0 else 1
            idx += 1
    return scaled


def load_learning_state(path: Path) -> AdaptiveLearningState:
    if not path.exists():
        return AdaptiveLearningState(dimension_weights=dict(DIMENSION_WEIGHTS))
    data = json.loads(path.read_text(encoding="utf-8"))
    return AdaptiveLearningState(
        dimension_weights=_normalized_weights(data.get("dimension_weights", DIMENSION_WEIGHTS)),
        learning_rate=float(data.get("learning_rate", LEARNING_RATE_DEFAULT)),
        samples=int(data.get("samples", 0)),
    )


def save_learning_state(state: AdaptiveLearningState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = asdict(state)
    serializable["dimension_weights"] = _normalized_weights(state.dimension_weights)
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_dimension(value: int, weight: int) -> int:
    bounded = max(0, min(5, int(value)))
    return round((bounded / 5) * weight)


def _bonus_points(profile: ContributionProfile) -> Dict[str, int]:
    return {
        "tests": 5 if profile.has_tests else 0,
        "docs": 3 if profile.has_docs else 0,
        "artifact": 2 if profile.has_artifact else 0,
        "quality_gate": 5 if profile.quality_gate_passed else 0,
    }


def _determine_tier(score: int) -> str:
    for threshold, name in TIER_THRESHOLDS:
        if score >= threshold:
            return name
    return "Incubator"


def _reward_recommendations(tier: str, score: int) -> List[str]:
    rewards = {
        "Pioneer": [
            "优先立项进入下一轮产品化或研究化路线。",
            "进入月度创新榜单候选，并给予跨模块资源支持。",
            "允许沉淀为标准模板、标准工具或标准流程。",
        ],
        "Catalyst": [
            "进入季度改进池，优先安排复用推广。",
            "建议在团队评审会上做一次经验分享。",
        ],
        "Explorer": [
            "鼓励继续补充验证与文档，进入观察名单。",
            "建议补齐测试或示例后再次评估。",
        ],
        "Incubator": [
            "暂不进入奖励池，先完成可验证最小闭环。",
            "建议缩小问题范围并补充证据链。",
        ],
    }
    result = list(rewards[tier])
    if score >= 90:
        result.append("建议申请专项激励或作为团队标准实践推广。")
    return result


def _improvement_actions(profile: ContributionProfile) -> List[str]:
    actions: List[str] = []
    if profile.validation < 4:
        actions.append("补充测试、回归证据或实验结果，提升验证强度。")
    if profile.reuse < 3:
        actions.append("把实现抽象为可复用组件、模板或脚本。")
    if profile.knowledge_sharing < 3:
        actions.append("增加文档、样例或复盘，降低团队吸收成本。")
    if not profile.has_docs:
        actions.append("补充机制说明、设计约束或使用说明文档。")
    if not profile.has_tests:
        actions.append("补充最小单测或验证脚本，形成闭环。")
    if not actions:
        actions.append("当前提交已具备较完整创新闭环，建议推进规模化复用。")
    return actions


def evaluate_profile(
    profile: ContributionProfile,
    active_weights: Optional[Dict[str, int]] = None,
) -> IncentiveReport:
    weights = _normalized_weights(active_weights or DIMENSION_WEIGHTS)
    dimension_scores = {
        name: _normalize_dimension(getattr(profile, name), weight)
        for name, weight in weights.items()
    }
    bonus_points = _bonus_points(profile)
    score = min(100, sum(dimension_scores.values()) + sum(bonus_points.values()))
    tier = _determine_tier(score)

    return IncentiveReport(
        title=profile.title,
        owner=profile.owner,
        score=score,
        tier=tier,
        dimension_scores=dimension_scores,
        bonus_points=bonus_points,
        reward_recommendations=_reward_recommendations(tier, score),
        improvement_actions=_improvement_actions(profile),
        linked_files=profile.linked_files,
        active_weights=weights,
        adaptive_learning={"state_updated": False},
    )


def apply_adaptive_learning(
    state: AdaptiveLearningState,
    profile: ContributionProfile,
    report: IncentiveReport,
    feedback: float,
) -> Dict[str, object]:
    bounded_feedback = max(0.0, min(5.0, float(feedback)))
    expected = bounded_feedback / 5.0
    predicted = report.score / 100.0
    error = expected - predicted

    before = _normalized_weights(state.dimension_weights)
    updated = dict(before)
    for name in DIMENSION_WEIGHTS:
        signal = max(0.0, min(1.0, float(getattr(profile, name)) / 5.0))
        delta = state.learning_rate * error * signal * 10
        updated[name] = max(5, int(round(updated[name] + delta)))

    after = _normalized_weights(updated)
    state.dimension_weights = after
    state.samples += 1

    return {
        "state_updated": True,
        "feedback": round(bounded_feedback, 4),
        "prediction": round(predicted * 5, 4),
        "error": round(error, 6),
        "samples": state.samples,
        "weights_before": before,
        "weights_after": after,
    }


def load_profile(path: Path) -> ContributionProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ContributionProfile(**data)


def save_report(report: IncentiveReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate innovation incentive profile")
    parser.add_argument("--input", required=True, help="Path to contribution profile JSON")
    parser.add_argument(
        "--output",
        default="output/innovation-incentive-report.json",
        help="Path to output report JSON",
    )
    parser.add_argument(
        "--state",
        default="output/innovation-learning-state.json",
        help="Path to adaptive learning state JSON",
    )
    parser.add_argument(
        "--feedback",
        type=float,
        default=None,
        help="Human feedback score for this evaluation (0-5). If provided, adaptive learning updates state.",
    )
    args = parser.parse_args()

    profile = load_profile(Path(args.input).resolve())
    state_path = Path(args.state).resolve()
    state = load_learning_state(state_path)

    report = evaluate_profile(profile, active_weights=state.dimension_weights)
    feedback = args.feedback if args.feedback is not None else profile.feedback_score
    if feedback is not None:
        report.adaptive_learning = apply_adaptive_learning(state, profile, report, feedback)
        report.active_weights = dict(state.dimension_weights)
        save_learning_state(state, state_path)

    save_report(report, Path(args.output).resolve())

    print("[innovation-incentive] title={title}".format(title=report.title))
    print("[innovation-incentive] owner={owner}".format(owner=report.owner))
    print("[innovation-incentive] score={score} tier={tier}".format(score=report.score, tier=report.tier))
    if feedback is not None:
        print("[innovation-incentive] adaptive-learning updated state={path}".format(path=state_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())