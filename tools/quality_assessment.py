"""
Quality assessment system.

This tool evaluates engineering quality by converting gate results into
dimension scores, overall score, grade, and actionable recommendations.

Usage:
    python tools/quality_assessment.py --gates-report output/quality-gate.json
    python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

import yaml

DEFAULT_WEIGHTS = {
    "gate_stability": 0.25,
    "test_reliability": 0.20,
    "logic_health": 0.20,
    "code_health": 0.20,
    "architecture_health": 0.15,
}


@dataclass(frozen=True)
class AssessmentThresholds:
    min_overall_score: float = 85.0
    min_dimension_score: float = 70.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    for key, value in (weights or {}).items():
        if key in merged:
            merged[key] = max(0.0, float(value))
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in merged.items()}


def _load_thresholds_from_config(config_path: Path) -> AssessmentThresholds:
    if not config_path.exists():
        return AssessmentThresholds()

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        # Some repositories keep partially-edited YAML during development.
        # Do not block quality assessment due to config parse issues.
        return AssessmentThresholds()

    section = (data.get("quality_assessment") or {})
    return AssessmentThresholds(
        min_overall_score=float(section.get("min_overall_score", 85.0)),
        min_dimension_score=float(section.get("min_dimension_score", 70.0)),
    )


def _index_gates(gate_results: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {str(item.get("name")): item for item in gate_results}


def metrics_from_gate_results(gate_results: List[Dict[str, object]]) -> Dict[str, float]:
    indexed = _index_gates(gate_results)
    total_gates = max(1, len(gate_results))
    passed_gates = sum(1 for item in gate_results if bool(item.get("success")))

    logic_gate = indexed.get("logic_checks", {})
    logic_metrics = logic_gate.get("metrics", {}) if isinstance(logic_gate.get("metrics", {}), dict) else {}
    logic_issues = float(logic_metrics.get("issue_count", 0) or 0)
    logic_errors = float(logic_metrics.get("error_count", 0) or 0)
    logic_health = 1.0 if logic_issues == 0 else _clamp(1.0 - (logic_errors / logic_issues))

    code_gate = indexed.get("code_quality", {})
    code_metrics = code_gate.get("metrics", {}) if isinstance(code_gate.get("metrics", {}), dict) else {}
    code_issues = float(code_metrics.get("issue_count", 0) or 0)
    code_errors = float(code_metrics.get("error_count", 0) or 0)
    code_warnings = float(code_metrics.get("warning_count", 0) or 0)
    if code_issues == 0:
        code_health = 1.0
    else:
        error_penalty = code_errors / code_issues
        warning_penalty = min(0.4, code_warnings / 150.0)
        code_health = _clamp(1.0 - error_penalty - warning_penalty)

    test_gate = indexed.get("quality_unit_tests", {})
    test_reliability = 1.0 if bool(test_gate.get("success")) else 0.0

    dependency_gate = indexed.get("dependency_graph", {})
    architecture_health = 1.0 if bool(dependency_gate.get("success")) else 0.0

    return {
        "gate_stability": _clamp(passed_gates / total_gates),
        "test_reliability": test_reliability,
        "logic_health": logic_health,
        "code_health": code_health,
        "architecture_health": architecture_health,
    }


def _grade(overall_score: float) -> str:
    if overall_score >= 90:
        return "A"
    if overall_score >= 80:
        return "B"
    if overall_score >= 70:
        return "C"
    return "D"


def _recommendations(failed_dimensions: List[str]) -> List[str]:
    mapping = {
        "gate_stability": "提升门禁稳定性，优先修复导致 gate 失败的阻断项。",
        "test_reliability": "补强单元测试稳定性与失败重现路径，减少不确定性。",
        "logic_health": "优先处理逻辑检查中的 ERROR，避免结构性回归。",
        "code_health": "持续降低复杂度与告警密度，分批重构高复杂函数。",
        "architecture_health": "保障依赖图生成与架构约束检查持续通过。",
    }
    if not failed_dimensions:
        return ["当前质量评估达标，建议维持小步迭代与持续监控。"]
    return [mapping[name] for name in failed_dimensions if name in mapping]


def assess_quality_metrics(
    metrics: Dict[str, float],
    thresholds: AssessmentThresholds,
    weights: Dict[str, float] | None = None,
) -> Dict[str, object]:
    normalized_weights = _normalize_weights(weights or DEFAULT_WEIGHTS)

    dimension_scores = {
        name: round(_clamp(float(value)) * 100.0, 2)
        for name, value in metrics.items()
    }

    overall_score = round(
        sum(dimension_scores.get(name, 0.0) * normalized_weights.get(name, 0.0) for name in normalized_weights),
        2,
    )

    failed_dimensions = [
        name
        for name, score in dimension_scores.items()
        if score < thresholds.min_dimension_score
    ]

    passed = overall_score >= thresholds.min_overall_score and not failed_dimensions
    return {
        "passed": passed,
        "overall_score": overall_score,
        "grade": _grade(overall_score),
        "dimension_scores": dimension_scores,
        "failed_dimensions": failed_dimensions,
        "thresholds": asdict(thresholds),
        "weights": normalized_weights,
        "recommendations": _recommendations(failed_dimensions),
    }


def assess_from_gate_results(
    gate_results: List[Dict[str, object]],
    config_path: Path,
) -> Dict[str, object]:
    thresholds = _load_thresholds_from_config(config_path)
    metrics = metrics_from_gate_results(gate_results)
    assessment = assess_quality_metrics(metrics, thresholds)
    assessment["derived_metrics"] = metrics
    return assessment


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quality assessment system")
    parser.add_argument("--gates-report", default="output/quality-gate.json", help="Path to quality gate report JSON")
    parser.add_argument("--config", default="config.yml", help="Path to config YAML")
    parser.add_argument("--output", default="output/quality-assessment.json", help="Path to quality assessment report")
    args = parser.parse_args()

    gate_report_path = Path(args.gates_report).resolve()
    config_path = Path(args.config).resolve()
    output_path = Path(args.output).resolve()

    gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
    gate_results = gate_report.get("results", [])
    assessment = assess_from_gate_results(gate_results, config_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[quality-assessment] passed={passed}".format(passed=assessment["passed"]))
    print("[quality-assessment] overall_score={score} grade={grade}".format(score=assessment["overall_score"], grade=assessment["grade"]))
    print("[quality-assessment] report={path}".format(path=output_path))
    return 0 if assessment["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())