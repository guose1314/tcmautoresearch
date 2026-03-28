"""
Quality feedback mechanism.

This tool converts quality artifacts into actionable, graded feedback:
1) structured feedback JSON
2) readable markdown summary
3) owner-grouped notification todos
4) issue draft artifacts for template mapping

Usage:
    python tools/quality_feedback.py
    python tools/quality_feedback.py --output output/quality-feedback.json --markdown output/quality-feedback.md
    python tools/quality_feedback.py --issue-dir output/quality-feedback-issues
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

DIMENSION_OWNER_MAP = {
    "gate_stability": "quality-governance",
    "test_reliability": "qa-engineering",
    "logic_health": "architecture-maintainers",
    "code_health": "module-owners",
    "architecture_health": "architecture-maintainers",
}


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


def _feedback_level(overall_score: float, failed_count: int) -> str:
    if failed_count > 0:
        return "critical"
    if overall_score < 80:
        return "warning"
    if overall_score < 90:
        return "attention"
    return "healthy"


def _dimension_feedback(name: str, score: float, failed_dimensions: List[str]) -> Dict[str, object]:
    is_failed = name in failed_dimensions
    level = "critical" if is_failed else ("attention" if score < 85 else "ok")
    owner = DIMENSION_OWNER_MAP.get(name, "quality-governance")

    action_map = {
        "gate_stability": "修复阻断 gate 并恢复稳定通过率。",
        "test_reliability": "补强失败场景回归测试，降低不稳定性。",
        "logic_health": "清理逻辑类风险并补充结构性约束。",
        "code_health": "分批拆解高复杂函数并持续降告警。",
        "architecture_health": "保持依赖图与架构约束一致。",
    }
    return {
        "dimension": name,
        "score": score,
        "level": level,
        "owner": owner,
        "action": action_map.get(name, "补充证据并持续跟踪。"),
    }


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown-owner"


def _priority_from_level(level: str) -> str:
    if level == "critical":
        return "P0"
    if level == "attention":
        return "P1"
    return "P2"


def build_owner_notifications(priority_actions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for item in priority_actions:
        owner = str(item.get("owner", "quality-governance"))
        grouped.setdefault(owner, []).append(
            {
                "dimension": item.get("dimension", "unknown"),
                "priority": _priority_from_level(str(item.get("level", "ok"))),
                "action": item.get("action", ""),
                "score": item.get("score", 0.0),
            }
        )

    result = []
    for owner, todos in grouped.items():
        todos.sort(key=lambda row: (row["priority"], row["dimension"]))
        result.append(
            {
                "owner": owner,
                "todo_count": len(todos),
                "todos": todos,
            }
        )
    result.sort(key=lambda row: row["owner"])
    return result


def build_issue_drafts(
    owner_notifications: List[Dict[str, object]],
    report: Dict[str, object],
) -> List[Dict[str, object]]:
    issue_drafts: List[Dict[str, object]] = []
    score = report.get("overall_score", 0.0)
    trend_status = report.get("trend_status", "unknown")
    for owner_row in owner_notifications:
        owner = str(owner_row.get("owner", "quality-governance"))
        todos = owner_row.get("todos", [])
        title = "[Quality][{owner}] Action Backlog ({count} items)".format(
            owner=owner,
            count=len(todos),
        )

        body_lines = [
            "## Summary",
            "",
            "- Owner: {0}".format(owner),
            "- Quality Score: {0}".format(score),
            "- Trend: {0}".format(trend_status),
            "",
            "## Action Items",
            "",
        ]
        for item in todos:
            body_lines.append(
                "- [{priority}] {dimension}: {action} (score={score})".format(
                    priority=item.get("priority", "P2"),
                    dimension=item.get("dimension", "unknown"),
                    action=item.get("action", ""),
                    score=item.get("score", 0.0),
                )
            )
        body_lines.extend([
            "",
            "## Acceptance",
            "",
            "- [ ] Action items are implemented",
            "- [ ] Quality gate is green",
            "- [ ] Updated artifacts are archived",
        ])

        slug_owner = _slug(owner)
        issue_drafts.append(
            {
                "owner": owner,
                "title": title,
                "labels": ["quality", "improvement", "feedback"],
                "template": "quality-action.md",
                "output_file": "quality-action-{owner}.md".format(owner=slug_owner),
                "body": "\n".join(body_lines),
            }
        )
    return issue_drafts


def write_issue_drafts(issue_drafts: List[Dict[str, object]], issue_dir: Path, issue_index: Path) -> Dict[str, object]:
    issue_dir.mkdir(parents=True, exist_ok=True)
    issue_index.parent.mkdir(parents=True, exist_ok=True)

    items = []
    for draft in issue_drafts:
        file_name = str(draft.get("output_file", "quality-action.md"))
        file_path = issue_dir / file_name
        md = [
            "# {0}".format(draft.get("title", "Quality Action")),
            "",
            "Template: {0}".format(draft.get("template", "quality-action.md")),
            "Labels: {0}".format(", ".join(draft.get("labels", []))),
            "",
            draft.get("body", ""),
            "",
        ]
        file_path.write_text("\n".join(md), encoding="utf-8")
        items.append(
            {
                "owner": draft.get("owner", "quality-governance"),
                "title": draft.get("title", "Quality Action"),
                "labels": draft.get("labels", []),
                "template": draft.get("template", "quality-action.md"),
                "file": str(file_path).replace("\\", "/"),
            }
        )

    index_payload = {"count": len(items), "items": items}
    issue_index.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_payload


def build_feedback_report(
    assessment: Dict[str, object],
    improvement: Dict[str, object],
    archive_latest: Dict[str, object],
) -> Dict[str, object]:
    overall_score = float(assessment.get("overall_score", 0.0) or 0.0)
    grade = str(assessment.get("grade", "D"))
    failed_dimensions = list(assessment.get("failed_dimensions", []))
    dimension_scores = assessment.get("dimension_scores", {})
    trend_status = str((improvement.get("trend") or {}).get("status", archive_latest.get("trend_status", "unknown")))
    trend_delta = float((improvement.get("trend") or {}).get("score_delta", archive_latest.get("trend_delta", 0.0)) or 0.0)

    dimension_feedback = []
    for name, raw_score in dimension_scores.items():
        try:
            score = float(raw_score)
        except Exception:
            continue
        dimension_feedback.append(_dimension_feedback(name, score, failed_dimensions))

    priority_actions = [
        item for item in dimension_feedback
        if item["level"] in {"critical", "attention"}
    ]
    owner_notifications = build_owner_notifications(priority_actions)
    issue_drafts = build_issue_drafts(owner_notifications, {
        "overall_score": overall_score,
        "trend_status": trend_status,
    })

    feedback_level = _feedback_level(overall_score, len(failed_dimensions))
    headline_map = {
        "healthy": "质量状态健康，建议持续小步改进。",
        "attention": "质量状态可用但存在改进空间，建议执行优先行动。",
        "warning": "质量状态偏弱，建议立即推进专项改进。",
        "critical": "存在关键质量风险，需优先处理失败维度。",
    }

    return {
        "timestamp": _utc_now_iso(),
        "feedback_level": feedback_level,
        "headline": headline_map[feedback_level],
        "overall_score": overall_score,
        "grade": grade,
        "trend_status": trend_status,
        "trend_delta": trend_delta,
        "failed_dimensions": failed_dimensions,
        "dimension_feedback": dimension_feedback,
        "priority_actions": priority_actions,
        "owner_notifications": owner_notifications,
        "issue_drafts": [
            {
                "owner": item.get("owner", "quality-governance"),
                "title": item.get("title", ""),
                "template": item.get("template", "quality-action.md"),
                "output_file": item.get("output_file", "quality-action.md"),
                "labels": item.get("labels", []),
            }
            for item in issue_drafts
        ],
        "acknowledgements": [
            "质量门已自动执行并生成报告。",
            "改进档案已沉淀，可用于追溯和复盘。",
        ] if overall_score >= 90 else ["建议复核改进行动并确认责任归属。"],
    }


def _to_markdown(report: Dict[str, object]) -> str:
    lines = [
        "# Quality Feedback Report",
        "",
        "- Timestamp: {0}".format(report.get("timestamp", "")),
        "- Level: {0}".format(report.get("feedback_level", "unknown")),
        "- Headline: {0}".format(report.get("headline", "")),
        "- Overall Score: {0}".format(report.get("overall_score", 0.0)),
        "- Grade: {0}".format(report.get("grade", "D")),
        "- Trend: {0} ({1})".format(report.get("trend_status", "unknown"), report.get("trend_delta", 0.0)),
        "",
        "## Failed Dimensions",
        "",
        "- {0}".format(", ".join(report.get("failed_dimensions", [])) or "None"),
        "",
        "## Priority Actions",
        "",
    ]

    actions = report.get("priority_actions", [])
    if not actions:
        lines.append("- No priority actions.")
    else:
        for item in actions:
            lines.append(
                "- [{level}] {dimension} -> {action} (owner: {owner})".format(
                    level=item.get("level", "ok"),
                    dimension=item.get("dimension", "unknown"),
                    action=item.get("action", ""),
                    owner=item.get("owner", "quality-governance"),
                )
            )

    lines.extend([
        "",
        "## Owner Notifications",
        "",
    ])
    owner_rows = report.get("owner_notifications", [])
    if not owner_rows:
        lines.append("- No owner-specific todos.")
    else:
        for row in owner_rows:
            lines.append(
                "- {owner}: {count} items".format(
                    owner=row.get("owner", "quality-governance"),
                    count=row.get("todo_count", 0),
                )
            )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate quality feedback report")
    parser.add_argument("--assessment", default="output/quality-assessment.json", help="Path to quality assessment report")
    parser.add_argument("--improvement", default="output/continuous-improvement.json", help="Path to continuous improvement report")
    parser.add_argument("--archive-latest", default="output/quality-improvement-archive-latest.json", help="Path to latest archive snapshot")
    parser.add_argument("--output", default="output/quality-feedback.json", help="Path to feedback JSON")
    parser.add_argument("--markdown", default="output/quality-feedback.md", help="Path to feedback markdown")
    parser.add_argument("--issue-dir", default="output/quality-feedback-issues", help="Output directory for issue draft markdown files")
    parser.add_argument("--issue-index", default="output/quality-feedback-issues.json", help="Output JSON index for issue draft mapping")
    args = parser.parse_args()

    assessment = _safe_load_json(Path(args.assessment).resolve())
    improvement = _safe_load_json(Path(args.improvement).resolve())
    archive_latest = _safe_load_json(Path(args.archive_latest).resolve())

    report = build_feedback_report(assessment, improvement, archive_latest)

    output_path = Path(args.output).resolve()
    markdown_path = Path(args.markdown).resolve()
    issue_dir = Path(args.issue_dir).resolve()
    issue_index = Path(args.issue_index).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_to_markdown(report), encoding="utf-8")

    issue_drafts = build_issue_drafts(report.get("owner_notifications", []), report)
    issue_index_payload = write_issue_drafts(issue_drafts, issue_dir, issue_index)

    print("[quality-feedback] level={level} score={score}".format(
        level=report.get("feedback_level", "unknown"),
        score=report.get("overall_score", 0.0),
    ))
    print("[quality-feedback] json={path}".format(path=output_path))
    print("[quality-feedback] markdown={path}".format(path=markdown_path))
    print("[quality-feedback] issue-drafts={count} index={path}".format(
        count=issue_index_payload.get("count", 0),
        path=issue_index,
    ))

    return 0 if report.get("feedback_level") != "critical" else 1


if __name__ == "__main__":
    raise SystemExit(main())
