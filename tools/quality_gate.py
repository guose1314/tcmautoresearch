"""
Unified quality gate for the repository.

This script consolidates three baseline controls:
1) Static logic checks
2) Dependency graph regeneration
3) Code quality static checks
4) Focused quality-tool unit tests
5) Quality assessment scoring
6) Continuous improvement loop
7) Quality improvement archive
8) Quality feedback mechanism

Usage:
    python tools/quality_gate.py
    python tools/quality_gate.py --report output/quality-gate.json
"""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

from tools.code_quality_checks import run_checks as run_code_quality_checks
from tools.continuous_improvement_loop import build_cycle_report, load_history
from tools.generate_dependency_graph import build_dependency_graph, write_outputs
from tools.logic_checks import run_checks
from tools.quality_assessment import assess_from_gate_results
from tools.quality_feedback import (
    build_feedback_report,
    build_issue_drafts,
    write_issue_drafts,
)
from tools.quality_improvement_archive import build_archive_entry, write_archive

DEFAULT_TEST_MODULES = [
    "tests.unit.test_logic_checks",
    "tests.unit.test_code_quality_checks",
    "tests.unit.test_continuous_improvement_loop",
    "tests.unit.test_dependency_graph_tool",
    "tests.unit.test_quality_assessment",
    "tests.unit.test_quality_improvement_archive",
    "tests.unit.test_quality_feedback",
]


@dataclass
class GateResult:
    name: str
    success: bool
    metrics: Dict[str, object] = field(default_factory=dict)
    details: Dict[str, object] = field(default_factory=dict)


def _serialize_issue(issue: object, root: Path) -> Dict[str, object]:
    file_path = getattr(issue, "file_path")
    normalized_file = (
        str(file_path.relative_to(root)).replace("\\", "/")
        if file_path.is_absolute()
        else str(file_path)
    )
    return {
        "severity": getattr(issue, "severity"),
        "file": normalized_file,
        "line": getattr(issue, "line"),
        "message": getattr(issue, "message"),
    }


def _build_issue_gate_result(name: str, issues: List[object], root: Path) -> GateResult:
    errors = [issue for issue in issues if getattr(issue, "severity") == "ERROR"]
    warnings = [issue for issue in issues if getattr(issue, "severity") != "ERROR"]
    return GateResult(
        name=name,
        success=len(errors) == 0,
        metrics={
            "issue_count": len(issues),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        details={
            "issues": [_serialize_issue(issue, root) for issue in issues]
        },
    )


def run_logic_gate(root: Path) -> GateResult:
    issues = run_checks(root)
    return _build_issue_gate_result("logic_checks", issues, root)


def run_dependency_graph_gate(root: Path, output_dir: Path) -> GateResult:
    graph = build_dependency_graph(root)
    outputs = write_outputs(graph, output_dir)
    return GateResult(
        name="dependency_graph",
        success=True,
        metrics={
            "module_count": graph["module_count"],
            "module_edge_count": graph["module_edge_count"],
            "package_count": graph["package_count"],
            "package_edge_count": graph["package_edge_count"],
        },
        details={
            "outputs": {
                name: str(path.relative_to(root)).replace("\\", "/")
                for name, path in outputs.items()
            }
        },
    )


def run_code_quality_gate(root: Path) -> GateResult:
    issues = run_code_quality_checks(root)
    return _build_issue_gate_result("code_quality", issues, root)


def run_unit_test_gate(root: Path, test_modules: List[str]) -> GateResult:
    command = [sys.executable, "-m", "unittest", *test_modules]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return GateResult(
        name="quality_unit_tests",
        success=completed.returncode == 0,
        metrics={
            "return_code": completed.returncode,
            "test_module_count": len(test_modules),
        },
        details={
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    )


def run_quality_assessment_gate(root: Path, gate_results: List[GateResult]) -> GateResult:
    assessment = assess_from_gate_results([asdict(item) for item in gate_results], root / "config.yml")
    output_path = root / "output" / "quality-assessment.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")
    return GateResult(
        name="quality_assessment",
        success=bool(assessment.get("passed")),
        metrics={
            "overall_score": assessment.get("overall_score", 0),
            "grade": assessment.get("grade", "D"),
            "failed_dimension_count": len(assessment.get("failed_dimensions", [])),
        },
        details={
            "assessment_report": str(output_path.relative_to(root)).replace("\\", "/"),
            "failed_dimensions": assessment.get("failed_dimensions", []),
            "recommendations": assessment.get("recommendations", []),
        },
    )


def run_continuous_improvement_gate(root: Path) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    history_path = root / "output" / "quality-history.jsonl"
    output_path = root / "output" / "continuous-improvement.json"

    if not assessment_path.exists():
        return GateResult(
            name="continuous_improvement",
            success=False,
            metrics={"history_points": 0},
            details={"error": "quality assessment report is missing"},
        )

    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    history = load_history(history_path)
    report = build_cycle_report(assessment, history)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report["current_snapshot"], ensure_ascii=False) + "\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return GateResult(
        name="continuous_improvement",
        success=True,
        metrics={
            "history_points": report["trend"].get("history_points", 0),
            "score_delta": report["trend"].get("score_delta", 0),
            "trend_status": report["trend"].get("status", "stable"),
            "backlog_count": len(report.get("action_backlog", [])),
        },
        details={
            "continuous_report": str(output_path.relative_to(root)).replace("\\", "/"),
            "history_file": str(history_path.relative_to(root)).replace("\\", "/"),
        },
    )


def run_quality_improvement_archive_gate(root: Path, gate_report: Dict[str, object]) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    improvement_path = root / "output" / "continuous-improvement.json"
    if not assessment_path.exists() or not improvement_path.exists():
        return GateResult(
            name="quality_improvement_archive",
            success=False,
            metrics={"archive_entry_written": 0},
            details={"error": "assessment or improvement report is missing"},
        )

    assessment_report = json.loads(assessment_path.read_text(encoding="utf-8"))
    improvement_report = json.loads(improvement_path.read_text(encoding="utf-8"))
    entry = build_archive_entry(gate_report, assessment_report, improvement_report)

    outputs = write_archive(
        entry,
        root / "output" / "quality-improvement-archive.jsonl",
        root / "docs" / "quality-archive",
        root / "output" / "quality-improvement-archive-latest.json",
    )

    return GateResult(
        name="quality_improvement_archive",
        success=True,
        metrics={
            "archive_entry_written": 1,
            "quality_score": entry.get("quality_score", 0.0),
            "trend_status": entry.get("trend_status", "unknown"),
        },
        details={
            "history_file": str(outputs["history"].relative_to(root)).replace("\\", "/"),
            "dossier_file": str(outputs["dossier"].relative_to(root)).replace("\\", "/"),
            "latest_file": str(outputs["latest"].relative_to(root)).replace("\\", "/"),
        },
    )


def run_quality_feedback_gate(root: Path) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    improvement_path = root / "output" / "continuous-improvement.json"
    archive_latest_path = root / "output" / "quality-improvement-archive-latest.json"
    if not assessment_path.exists() or not improvement_path.exists() or not archive_latest_path.exists():
        return GateResult(
            name="quality_feedback",
            success=False,
            metrics={"priority_action_count": 0},
            details={"error": "required inputs for quality feedback are missing"},
        )

    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    improvement = json.loads(improvement_path.read_text(encoding="utf-8"))
    archive_latest = json.loads(archive_latest_path.read_text(encoding="utf-8"))
    feedback = build_feedback_report(assessment, improvement, archive_latest)

    json_path = root / "output" / "quality-feedback.json"
    md_path = root / "output" / "quality-feedback.md"
    issue_dir = root / "output" / "quality-feedback-issues"
    issue_index = root / "output" / "quality-feedback-issues.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "# Quality Feedback Report\n\n"
        "- Level: {level}\n"
        "- Score: {score}\n"
        "- Trend: {trend} ({delta})\n".format(
            level=feedback.get("feedback_level", "unknown"),
            score=feedback.get("overall_score", 0.0),
            trend=feedback.get("trend_status", "unknown"),
            delta=feedback.get("trend_delta", 0.0),
        ),
        encoding="utf-8",
    )

    issue_drafts = build_issue_drafts(feedback.get("owner_notifications", []), feedback)
    issue_index_payload = write_issue_drafts(issue_drafts, issue_dir, issue_index)

    priority_count = len(feedback.get("priority_actions", []))
    owner_notifications = feedback.get("owner_notifications", [])
    owner_count = len(owner_notifications)
    owner_todo_count = sum(int(item.get("todo_count", 0)) for item in owner_notifications)
    level = str(feedback.get("feedback_level", "unknown"))
    return GateResult(
        name="quality_feedback",
        success=True,
        metrics={
            "feedback_level": level,
            "priority_action_count": priority_count,
            "owner_count": owner_count,
            "owner_todo_count": owner_todo_count,
            "issue_draft_count": issue_index_payload.get("count", 0),
        },
        details={
            "feedback_json": str(json_path.relative_to(root)).replace("\\", "/"),
            "feedback_markdown": str(md_path.relative_to(root)).replace("\\", "/"),
            "feedback_issue_index": str(issue_index.relative_to(root)).replace("\\", "/"),
            "feedback_issue_dir": str(issue_dir.relative_to(root)).replace("\\", "/"),
        },
    )


def build_report(results: List[GateResult]) -> Dict[str, object]:
    overall_success = all(result.success for result in results)
    return {
        "overall_success": overall_success,
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified quality gate")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--report", default="output/quality-gate.json", help="Report output path")
    parser.add_argument("--graph-output", default="docs/architecture", help="Dependency graph output directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve()
    graph_output = (root / args.graph_output).resolve()

    core_results = [
        run_logic_gate(root),
        run_dependency_graph_gate(root, graph_output),
        run_code_quality_gate(root),
        run_unit_test_gate(root, DEFAULT_TEST_MODULES),
    ]
    assessment_result = run_quality_assessment_gate(root, core_results)
    improvement_result = run_continuous_improvement_gate(root)
    pre_archive_results = [*core_results, assessment_result, improvement_result]
    pre_archive_report = build_report(pre_archive_results)
    archive_result = run_quality_improvement_archive_gate(root, pre_archive_report)
    feedback_result = run_quality_feedback_gate(root)
    results = [*pre_archive_results, archive_result, feedback_result]
    report = build_report(results)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[quality-gate] overall_success={status}".format(status=report["overall_success"]))
    print("[quality-gate] report={path}".format(path=report_path.relative_to(root)))
    for result in results:
        print(
            "- {name}: success={success} metrics={metrics}".format(
                name=result.name,
                success=result.success,
                metrics=result.metrics,
            )
        )

    return 0 if report["overall_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())