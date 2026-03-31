"""Shared helpers for research-oriented REST endpoints."""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi.responses import FileResponse

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent

SUMMARY_FIELD_LABELS = {
    "observation_count": "观察记录数",
    "key_findings": "关键发现",
    "reason": "原因说明",
    "evidence_count": "证据条目数",
    "literature_count": "文献数量",
    "entity_count": "实体数量",
    "relationship_count": "关系数量",
    "hypothesis": "核心假设",
    "hypotheses": "假设列表",
    "experiment_count": "实验数量",
    "recommendations": "研究建议",
}

PHASE_LABELS = {
    "observe": "观察阶段",
    "hypothesis": "假设阶段",
    "experiment": "实验阶段",
    "analyze": "分析阶段",
    "publish": "发布阶段",
    "reflect": "复盘阶段",
    "summarize": "总结阶段",
}

STATUS_LABELS = {
    "queued": "排队中",
    "running": "进行中",
    "completed": "已完成",
    "partial": "部分完成",
    "failed": "失败",
    "skipped": "已跳过",
}

OUTPUT_FILE_CONTAINER_KEYS = {"output_files", "report_files"}
OUTPUT_FILE_VALUE_KEYS = {
    "output_file",
    "output_markdown",
    "markdown_file",
    "docx_file",
    "pdf_file",
    "html_file",
    "report_path",
    "result_path",
}


def normalize_research_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    return {
        "topic": topic,
        "orchestrator_config": payload.get("orchestrator_config") or {},
        "phase_contexts": payload.get("phase_contexts") or {},
        "cycle_name": payload.get("cycle_name"),
        "description": payload.get("description"),
        "scope": payload.get("scope"),
    }


def format_phase_name(phase: str) -> str:
    return PHASE_LABELS.get(phase, phase or "-")


def format_status(status: str) -> str:
    return STATUS_LABELS.get(status, status or "-")


def format_summary_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value) if value else "-"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def format_summary_lines(summary: Dict[str, Any]) -> list[str]:
    lines = []
    for key, value in summary.items():
        if value in (None, ""):
            continue
        lines.append(f"- {SUMMARY_FIELD_LABELS.get(key, key)}：{format_summary_value(value)}")
    return lines or ["- 无摘要"]


def build_report_stem(job_id: str, result: Dict[str, Any]) -> str:
    cycle_id = str(result.get("cycle_id") or job_id).strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", cycle_id).strip("-._")
    return cleaned or job_id


def build_markdown_report(job_id: str, result: Dict[str, Any]) -> str:
    topic = str(result.get("topic") or "未命名研究主题")
    phases = result.get("phases") or []
    pipeline_metadata = result.get("pipeline_metadata") or {}
    lines = [
        "# 研究任务报告",
        "",
        f"- 研究主题：{topic}",
        f"- 周期 ID：{result.get('cycle_id') or job_id}",
        f"- 执行状态：{format_status(str(result.get('status') or ''))}",
        f"- 开始时间：{result.get('started_at') or '-'}",
        f"- 完成时间：{result.get('completed_at') or '-'}",
        f"- 总耗时：{result.get('total_duration_sec') or '-'} 秒",
        f"- 周期名称：{pipeline_metadata.get('cycle_name') or '-'}",
        f"- 研究范围：{pipeline_metadata.get('scope') or '-'}",
        "",
        "## 阶段摘要",
        "",
    ]

    if not phases:
        lines.append("当前结果未返回阶段详情。")
    else:
        for phase in phases:
            phase_name = format_phase_name(str(phase.get("phase") or ""))
            lines.extend(
                [
                    f"### {phase_name}",
                    f"- 状态：{format_status(str(phase.get('status') or ''))}",
                    f"- 耗时：{phase.get('duration_sec') or '-'} 秒",
                ]
            )
            error = str(phase.get("error") or "").strip()
            if error:
                lines.append(f"- 错误：{error}")
            lines.extend(format_summary_lines(phase.get("summary") or {}))
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def iter_output_file_candidates(value: Any) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in OUTPUT_FILE_CONTAINER_KEYS and isinstance(nested, dict):
                for nested_key, nested_value in nested.items():
                    if isinstance(nested_value, str):
                        yield (str(nested_key), nested_value)
                continue
            if key_lower in OUTPUT_FILE_VALUE_KEYS and isinstance(nested, str):
                yield (key_text, nested)
                continue
            if key_lower.endswith("_path") and isinstance(nested, str):
                yield (key_text, nested)
                continue
            if isinstance(nested, (dict, list)):
                yield from iter_output_file_candidates(nested)
    elif isinstance(value, list):
        for item in value:
            yield from iter_output_file_candidates(item)


def is_safe_workspace_file(path_text: str) -> Optional[Path]:
    try:
        candidate = Path(path_text).expanduser().resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if not candidate.is_file():
        return None
    try:
        candidate.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None
    return candidate


def score_report_candidate(kind: str, candidate: Path, requested_format: str) -> Optional[int]:
    suffix = candidate.suffix.lower()
    kind_lower = kind.lower()
    name_lower = candidate.name.lower()
    if requested_format == "json":
        if suffix == ".json" or "json" in kind_lower:
            return 200
        return None
    if requested_format == "markdown":
        if suffix in {".md", ".markdown"} or "markdown" in kind_lower:
            return 200
        return None
    if requested_format == "auto":
        base_scores = {
            ".docx": 220,
            ".pdf": 210,
            ".md": 200,
            ".markdown": 200,
            ".html": 180,
            ".htm": 180,
            ".txt": 160,
        }
        score = base_scores.get(suffix)
        if score is None:
            return None
        if any(token in kind_lower for token in ("report", "paper", "markdown", "docx")):
            score += 15
        if any(token in name_lower for token in ("report", "paper", "draft", "summary")):
            score += 10
        return score
    return None


def resolve_preferred_report_artifact(result: Dict[str, Any], requested_format: str) -> Optional[Path]:
    best_match: Optional[tuple[int, Path]] = None
    for kind, path_text in iter_output_file_candidates(result):
        safe_path = is_safe_workspace_file(path_text)
        if safe_path is None:
            continue
        score = score_report_candidate(kind, safe_path, requested_format)
        if score is None:
            continue
        if best_match is None or score > best_match[0]:
            best_match = (score, safe_path)
    return best_match[1] if best_match else None


def build_artifact_file_response(path: Path) -> FileResponse:
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream", filename=path.name)