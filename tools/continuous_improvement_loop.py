"""
Continuous improvement loop.

This tool turns quality assessment outputs into an iterative improvement cycle:
1) Persist history snapshots
2) Compute trend status
3) Generate prioritized action backlog
4) Propose next-cycle targets

Usage:
    python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json
    python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --output output/continuous-improvement.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_assessment(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_history(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def append_history(path: Path, snapshot: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def _trend_status(delta: float) -> str:
    if delta > 0.5:
        return "improving"
    if delta < -0.5:
        return "regressing"
    return "stable"


def _build_snapshot(assessment: Dict[str, object]) -> Dict[str, object]:
    return {
        "timestamp": _utc_now_iso(),
        "overall_score": float(assessment.get("overall_score", 0.0) or 0.0),
        "grade": str(assessment.get("grade", "D")),
        "passed": bool(assessment.get("passed", False)),
        "dimension_scores": assessment.get("dimension_scores", {}),
        "failed_dimensions": assessment.get("failed_dimensions", []),
    }


def _action_for_dimension(name: str) -> Dict[str, object]:
    mapping = {
        "gate_stability": ("P0", "修复阻断项并恢复所有 gate 的稳定通过率。"),
        "test_reliability": ("P0", "补充失败场景回归测试并提升测试稳定性。"),
        "logic_health": ("P1", "清理逻辑检查告警，优先处理结构性风险。"),
        "code_health": ("P1", "继续拆解高复杂函数并降低告警密度。"),
        "architecture_health": ("P1", "保障依赖关系图和架构约束持续更新。"),
    }
    priority, action = mapping.get(name, ("P2", "补充质量证据并跟踪下一轮结果。"))
    return {
        "priority": priority,
        "dimension": name,
        "action": action,
    }


def _select_lowest_dimensions(dimension_scores: Dict[str, object], count: int = 2) -> List[str]:
    pairs = []
    for name, score in dimension_scores.items():
        try:
            pairs.append((name, float(score)))
        except Exception:
            continue
    pairs.sort(key=lambda item: item[1])
    return [name for name, _ in pairs[:count]]


def build_cycle_report(
    assessment: Dict[str, object],
    history: List[Dict[str, object]],
) -> Dict[str, object]:
    snapshot = _build_snapshot(assessment)

    previous_score = None
    if history:
        previous_score = float(history[-1].get("overall_score", 0.0) or 0.0)

    current_score = float(snapshot.get("overall_score", 0.0) or 0.0)
    score_delta = round(current_score - (previous_score if previous_score is not None else current_score), 2)
    status = _trend_status(score_delta)

    failed_dimensions = list(snapshot.get("failed_dimensions", []))
    dimension_scores = snapshot.get("dimension_scores", {})

    focus_dimensions = failed_dimensions or _select_lowest_dimensions(dimension_scores, count=2)
    actions = [_action_for_dimension(name) for name in focus_dimensions]

    target_score = min(100.0, round(current_score + 2.0, 2))
    next_cycle_targets = {
        "target_overall_score": target_score,
        "focus_dimensions": focus_dimensions,
        "max_new_warnings": 0,
    }

    return {
        "cycle_timestamp": snapshot["timestamp"],
        "current_snapshot": snapshot,
        "trend": {
            "status": status,
            "score_delta": score_delta,
            "previous_score": previous_score,
            "current_score": current_score,
            "history_points": len(history) + 1,
        },
        "action_backlog": actions,
        "next_cycle_targets": next_cycle_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run continuous improvement loop")
    parser.add_argument(
        "--assessment-report",
        default="output/quality-assessment.json",
        help="Path to quality assessment report",
    )
    parser.add_argument(
        "--history",
        default="output/quality-history.jsonl",
        help="Path to historical snapshots (JSON Lines)",
    )
    parser.add_argument(
        "--output",
        default="output/continuous-improvement.json",
        help="Path to continuous improvement report",
    )
    args = parser.parse_args()

    assessment_path = Path(args.assessment_report).resolve()
    history_path = Path(args.history).resolve()
    output_path = Path(args.output).resolve()

    assessment = load_assessment(assessment_path)
    history = load_history(history_path)
    report = build_cycle_report(assessment, history)

    append_history(history_path, report["current_snapshot"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[continuous-improvement] trend={status} delta={delta}".format(
        status=report["trend"]["status"],
        delta=report["trend"]["score_delta"],
    ))
    print("[continuous-improvement] report={path}".format(path=output_path))
    print("[continuous-improvement] history={path}".format(path=history_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())