"""
Quality improvement archive.

This tool archives each quality cycle by combining:
1) quality gate report
2) quality assessment report
3) continuous improvement report

It writes:
- JSONL timeline for machine tracking
- Markdown dossier for human review
- latest JSON summary

Usage:
    python tools/quality_improvement_archive.py
    python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def build_archive_entry(
    gate_report: Dict[str, object],
    assessment_report: Dict[str, object],
    improvement_report: Dict[str, object],
) -> Dict[str, object]:
    gate_results = gate_report.get("results", [])
    failed_gates = []
    if isinstance(gate_results, list):
        failed_gates = [
            str(item.get("name"))
            for item in gate_results
            if isinstance(item, dict) and not bool(item.get("success"))
        ]

    action_backlog = improvement_report.get("action_backlog", [])
    return {
        "timestamp": _utc_now_iso(),
        "overall_success": bool(gate_report.get("overall_success", False)),
        "quality_score": float(assessment_report.get("overall_score", 0.0) or 0.0),
        "quality_grade": str(assessment_report.get("grade", "D")),
        "trend_status": str((improvement_report.get("trend") or {}).get("status", "unknown")),
        "trend_delta": float((improvement_report.get("trend") or {}).get("score_delta", 0.0) or 0.0),
        "failed_gates": failed_gates,
        "failed_dimensions": assessment_report.get("failed_dimensions", []),
        "action_backlog_count": len(action_backlog) if isinstance(action_backlog, list) else 0,
        "next_cycle_targets": improvement_report.get("next_cycle_targets", {}),
    }


def _to_md_lines(entry: Dict[str, object]) -> List[str]:
    lines = [
        "# Quality Improvement Archive Entry",
        "",
        "## Snapshot",
        "",
        "- Timestamp: {0}".format(entry.get("timestamp", "")),
        "- Overall Success: {0}".format(entry.get("overall_success", False)),
        "- Quality Score: {0}".format(entry.get("quality_score", 0.0)),
        "- Quality Grade: {0}".format(entry.get("quality_grade", "D")),
        "- Trend Status: {0}".format(entry.get("trend_status", "unknown")),
        "- Trend Delta: {0}".format(entry.get("trend_delta", 0.0)),
        "",
        "## Risks",
        "",
        "- Failed Gates: {0}".format(", ".join(entry.get("failed_gates", [])) or "None"),
        "- Failed Dimensions: {0}".format(", ".join(entry.get("failed_dimensions", [])) or "None"),
        "",
        "## Improvement Backlog",
        "",
        "- Backlog Count: {0}".format(entry.get("action_backlog_count", 0)),
        "- Next Cycle Targets: {0}".format(json.dumps(entry.get("next_cycle_targets", {}), ensure_ascii=False)),
        "",
    ]
    return lines


def write_archive(
    entry: Dict[str, object],
    history_path: Path,
    dossier_dir: Path,
    latest_output: Path,
) -> Dict[str, Path]:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    dossier_dir.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)

    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    ts = str(entry.get("timestamp", "")).replace(":", "-")
    safe_ts = ts.replace("+00-00", "Z").replace(" ", "_")
    md_path = dossier_dir / "quality-improvement-{0}.md".format(safe_ts)
    md_path.write_text("\n".join(_to_md_lines(entry)), encoding="utf-8")

    latest_output.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "history": history_path,
        "dossier": md_path,
        "latest": latest_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive quality improvement outputs")
    parser.add_argument("--gate-report", default="output/quality-gate.json", help="Path to quality gate report")
    parser.add_argument("--assessment-report", default="output/quality-assessment.json", help="Path to quality assessment report")
    parser.add_argument("--improvement-report", default="output/continuous-improvement.json", help="Path to continuous improvement report")
    parser.add_argument("--history", default="output/quality-improvement-archive.jsonl", help="Path to archive JSONL")
    parser.add_argument("--dossier-dir", default="docs/quality-archive", help="Directory for markdown dossiers")
    parser.add_argument("--output", default="output/quality-improvement-archive-latest.json", help="Path to latest archive summary")
    args = parser.parse_args()

    gate_report = _safe_load_json(Path(args.gate_report).resolve())
    assessment_report = _safe_load_json(Path(args.assessment_report).resolve())
    improvement_report = _safe_load_json(Path(args.improvement_report).resolve())

    entry = build_archive_entry(gate_report, assessment_report, improvement_report)
    outputs = write_archive(
        entry,
        Path(args.history).resolve(),
        Path(args.dossier_dir).resolve(),
        Path(args.output).resolve(),
    )

    print("[quality-archive] score={score} grade={grade}".format(
        score=entry.get("quality_score", 0.0),
        grade=entry.get("quality_grade", "D"),
    ))
    print("[quality-archive] history={path}".format(path=outputs["history"]))
    print("[quality-archive] dossier={path}".format(path=outputs["dossier"]))
    print("[quality-archive] latest={path}".format(path=outputs["latest"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
