"""Shared helpers for research-oriented REST endpoints."""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi.responses import FileResponse

from src.research.observe_philology import (
    build_observe_philology_filter_contract,
    filter_observe_philology_assets,
    resolve_observe_philology_assets,
)
from src.research.phase_result import get_phase_artifact_map, get_phase_value

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_OBSERVE_PHASE_CONTEXT = {
    "data_source": "local",
    "use_local_corpus": True,
    "collect_local_corpus": True,
    "local_data_dir": str((WORKSPACE_ROOT / "data").resolve()),
    "use_ctext_whitelist": False,
    "run_preprocess_and_extract": True,
    "run_literature_retrieval": False,
}

DEFAULT_PUBLISH_PHASE_CONTEXT = {
    "allow_pipeline_citation_fallback": False,
}

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
    "experiment_count": "方案数量",
    "protocol_design_count": "方案设计数",
    "success_rate": "方案完成率",
    "design_completion_rate": "方案完成率",
    "imported_record_count": "导入记录数",
    "imported_relationship_count": "导入关系数",
    "sampling_event_count": "采样事件数",
    "imported_artifact_count": "导入工件数",
    "execution_status": "执行状态",
    "real_world_validation_status": "真实验证状态",
    "recommendations": "研究建议",
}

PHASE_LABELS = {
    "observe": "观察阶段",
    "hypothesis": "假设阶段",
    "experiment": "实验方案阶段",
    "experiment_execution": "实验执行阶段",
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
REVIEW_WORKBENCH_SECTION_META = {
    "catalog_version_lineage": {
        "title": "目录谱系",
        "description": "沿用 catalog review artifact，按作品、谱系、见证本收口目录学校核。",
        "empty_message": "当前筛选结果下没有可审核的目录谱系。",
    },
    "terminology_row": {
        "title": "术语标准表",
        "description": "围绕 canonical、标签、见证文献与术语依据做人工复核。",
        "empty_message": "当前筛选结果下没有术语标准表条目。",
    },
    "collation_entry": {
        "title": "校勘条目",
        "description": "对异文替换、疑似脱文和衍文条目做人工校勘。",
        "empty_message": "当前筛选结果下没有校勘条目。",
    },
    "fragment_candidate": {
        "title": "辑佚候选",
        "description": "统一审核疑似辑佚补线索、佚文候选和引文来源候选。",
        "empty_message": "当前筛选结果下没有辑佚候选。",
    },
    "claim": {
        "title": "考据 Claim",
        "description": "对 evidence protocol 中的候选论断做人工取舍与补据。",
        "empty_message": "当前筛选结果下没有可审核的 claim。",
    },
}


def _normalize_optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _normalize_phase_contexts(raw_phase_contexts: Any) -> Dict[str, Any]:
    phase_contexts: Dict[str, Any] = {}
    if isinstance(raw_phase_contexts, dict):
        for key, value in raw_phase_contexts.items():
            phase_name = str(key)
            if isinstance(value, dict):
                phase_contexts[phase_name] = dict(value)
            else:
                phase_contexts[phase_name] = value

    observe_context = phase_contexts.get("observe")
    if isinstance(observe_context, dict):
        merged_observe_context = dict(DEFAULT_OBSERVE_PHASE_CONTEXT)
        merged_observe_context.update(observe_context)
        phase_contexts["observe"] = merged_observe_context
    else:
        phase_contexts["observe"] = dict(DEFAULT_OBSERVE_PHASE_CONTEXT)

    publish_context = phase_contexts.get("publish")
    if isinstance(publish_context, dict):
        merged_publish_context = dict(DEFAULT_PUBLISH_PHASE_CONTEXT)
        merged_publish_context.update(publish_context)
        phase_contexts["publish"] = merged_publish_context
    else:
        phase_contexts["publish"] = dict(DEFAULT_PUBLISH_PHASE_CONTEXT)

    return phase_contexts


def normalize_research_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    phase_contexts = _normalize_phase_contexts(payload.get("phase_contexts") or {})
    return {
        "topic": topic,
        "orchestrator_config": payload.get("orchestrator_config") or {},
        "phase_contexts": phase_contexts,
        "cycle_name": payload.get("cycle_name"),
        "description": payload.get("description"),
        "scope": payload.get("scope"),
        "study_type": _normalize_optional_text(payload.get("study_type")),
        "primary_outcome": _normalize_optional_text(payload.get("primary_outcome")),
        "intervention": _normalize_optional_text(payload.get("intervention")),
        "comparison": _normalize_optional_text(payload.get("comparison")),
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


def _build_markdown_overview_lines(
    job_id: str,
    result: Dict[str, Any],
    pipeline_metadata: Dict[str, Any],
    topic: str,
) -> list[str]:
    return [
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


def _build_markdown_phase_block(phase: Dict[str, Any]) -> list[str]:
    phase_name = format_phase_name(str(phase.get("phase") or ""))
    lines = [
        f"### {phase_name}",
        f"- 状态：{format_status(str(phase.get('status') or ''))}",
        f"- 耗时：{phase.get('duration_sec') or '-'} 秒",
    ]
    error = str(phase.get("error") or "").strip()
    if error:
        lines.append(f"- 错误：{error}")
    lines.extend(format_summary_lines(_as_dict(phase.get("summary"))))
    lines.append("")
    return lines


def _build_markdown_phase_lines(phases: list[Any]) -> list[str]:
    normalized_phases = [phase for phase in phases if isinstance(phase, dict)]
    if not normalized_phases:
        return ["当前结果未返回阶段详情。"]

    lines: list[str] = []
    for phase in normalized_phases:
        lines.extend(_build_markdown_phase_block(phase))
    return lines


def build_markdown_report(job_id: str, result: Dict[str, Any]) -> str:
    topic = str(result.get("topic") or "未命名研究主题")
    phases = _as_list(result.get("phases"))
    pipeline_metadata = _as_dict(result.get("pipeline_metadata"))
    lines = _build_markdown_overview_lines(job_id, result, pipeline_metadata, topic)
    lines.extend(_build_markdown_phase_lines(phases))

    return "\n".join(lines).strip() + "\n"


def _iter_output_container_candidates(value: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    for nested_key, nested_value in value.items():
        if isinstance(nested_value, str):
            yield (str(nested_key), nested_value)


def _is_output_file_value_candidate(key_lower: str, value: Any) -> bool:
    return isinstance(value, str) and (
        key_lower in OUTPUT_FILE_VALUE_KEYS or key_lower.endswith("_path")
    )


def _iter_output_dict_candidates(value: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    for key, nested in value.items():
        key_text = str(key)
        key_lower = key_text.lower()
        if key_lower in OUTPUT_FILE_CONTAINER_KEYS and isinstance(nested, dict):
            yield from _iter_output_container_candidates(nested)
            continue
        if _is_output_file_value_candidate(key_lower, nested):
            yield (key_text, nested)
            continue
        if isinstance(nested, (dict, list)):
            yield from iter_output_file_candidates(nested)


def iter_output_file_candidates(value: Any) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        yield from _iter_output_dict_candidates(value)
        return

    if isinstance(value, list):
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
    for kind, path_text in _iter_report_artifact_candidates(result):
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
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        media_type = "text/markdown; charset=utf-8"
    elif suffix == ".json":
        media_type = "application/json"
    else:
        guessed_media_type, _ = mimetypes.guess_type(str(path))
        media_type = guessed_media_type or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


def _safe_float(value: Any, default: float=0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric:
        return default
    return numeric


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resolve_publish_phase_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    if str(result.get("phase") or "").strip().lower() == "publish":
        return result

    phase_results = _as_dict(result.get("phase_results"))
    return _as_dict(phase_results.get("publish"))


def _resolve_publish_highlight_payload(result: Dict[str, Any], key: str) -> Dict[str, Any]:
    publish_result = _resolve_publish_phase_result(result)
    nested = _as_dict(get_phase_value(publish_result, key))
    if nested:
        return nested
    return _as_dict(result.get(key))


def _resolve_observe_phase_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    phase_results = _as_dict(result.get("phase_results"))
    return _as_dict(phase_results.get("observe"))


def _resolve_observe_philology(result: Dict[str, Any]) -> Dict[str, Any]:
    observe_phase_result = _resolve_observe_phase_result(result)
    return resolve_observe_philology_assets(
        observe_philology=result.get("observe_philology"),
        artifacts=_as_list(observe_phase_result.get("artifacts")),
        observe_phase_result=observe_phase_result,
    )


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _unique_texts(values: Iterable[Any]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _as_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _normalize_workbench_review_status(value: Any) -> str:
    normalized = _as_text(value).lower()
    if normalized in {"pending", "accepted", "rejected", "needs_source"}:
        return normalized
    return "pending"


def _build_review_workbench_asset_key(asset_type: str, *parts: tuple[str, Any]) -> str:
    normalized_parts = [
        f"{name}={_as_text(value)}"
        for name, value in parts
        if _as_text(value)
    ]
    return f"{asset_type}::{'|'.join(normalized_parts) if normalized_parts else 'unkeyed'}"


def _build_filter_candidate_map(**kwargs: Any) -> Dict[str, list[str]]:
    return {
        field_name: _unique_texts(values if isinstance(values, list) else [values])
        for field_name, values in kwargs.items()
        if _unique_texts(values if isinstance(values, list) else [values])
    }


def _build_review_workbench_decision_lookup(observe_philology: Dict[str, Any]) -> Dict[tuple[str, str], Dict[str, Any]]:
    lookup: Dict[tuple[str, str], Dict[str, Any]] = {}
    for decision in _as_dict_list(observe_philology.get("review_workbench_decisions")):
        asset_type = _as_text(decision.get("asset_type")).lower()
        asset_key = _as_text(decision.get("asset_key"))
        if asset_type and asset_key:
            lookup[(asset_type, asset_key)] = decision
    return lookup


def _apply_review_workbench_decision(item: Dict[str, Any], decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not decision:
        return item
    updated = dict(item)
    updated["review_status"] = _normalize_workbench_review_status(decision.get("review_status") or item.get("review_status"))
    updated["needs_manual_review"] = bool(decision.get("needs_manual_review"))
    updated["review_reasons"] = _as_list(decision.get("review_reasons")) or _as_list(item.get("review_reasons"))
    updated["review_source"] = _as_text(decision.get("review_source") or item.get("review_source") or "manual_review")
    for field_name in ("reviewer", "reviewed_at", "decision_basis"):
        value = _as_text(decision.get(field_name) or item.get(field_name))
        if value:
            updated[field_name] = value
    return updated


def _item_matches_catalog_filters(item: Dict[str, Any], active_filters: Dict[str, Any]) -> bool:
    filter_candidates = _as_dict(item.get("filter_candidates"))
    for field_name in ("document_title", "work_title", "version_lineage_key", "witness_key"):
        expected = _as_text(active_filters.get(field_name))
        if not expected:
            continue
        candidates = _unique_texts([
            item.get(field_name),
            *(_as_list(filter_candidates.get(field_name))),
        ])
        if expected not in candidates:
            return False
    return True


def _build_review_workbench_section(asset_type: str, items: list[Dict[str, Any]]) -> Dict[str, Any]:
    meta = REVIEW_WORKBENCH_SECTION_META.get(asset_type, {})
    return {
        "asset_type": asset_type,
        "title": meta.get("title") or asset_type,
        "description": meta.get("description") or "",
        "empty_message": meta.get("empty_message") or "当前没有可审核条目。",
        "count": len(items),
        "items": items,
    }


def _build_catalog_lineage_review_items(observe_philology: Dict[str, Any]) -> list[Dict[str, Any]]:
    catalog_summary = _as_dict(observe_philology.get("catalog_summary"))
    lineages = _as_dict_list(catalog_summary.get("version_lineages"))
    items: list[Dict[str, Any]] = []
    for lineage in lineages:
        version_lineage_key = _as_text(lineage.get("version_lineage_key") or lineage.get("work_fragment_key"))
        if not version_lineage_key:
            continue
        witnesses = _as_dict_list(lineage.get("witnesses"))
        witness_keys = _unique_texts(witness.get("witness_key") for witness in witnesses)
        document_titles = _unique_texts((witness.get("title") or witness.get("document_title")) for witness in witnesses)
        item = {
            "asset_type": "catalog_version_lineage",
            "asset_key": version_lineage_key,
            "submission_mode": "catalog",
            "review_status": _normalize_workbench_review_status(lineage.get("review_status")),
            "needs_manual_review": bool(lineage.get("needs_manual_review", True)),
            "review_reasons": _as_list(lineage.get("review_reasons")),
            "review_source": _as_text(lineage.get("review_source")),
            "reviewer": _as_text(lineage.get("reviewer")),
            "reviewed_at": _as_text(lineage.get("reviewed_at")),
            "decision_basis": _as_text(lineage.get("decision_basis")),
            "title": _as_text(lineage.get("work_title")) or _as_text(lineage.get("fragment_title")) or "未标注作品",
            "subtitle": " · ".join(
                part
                for part in (
                    _as_text(lineage.get("fragment_title")),
                    _as_text(lineage.get("dynasty")),
                    _as_text(lineage.get("author")),
                    _as_text(lineage.get("edition")),
                )
                if part
            ) or version_lineage_key,
            "summary_lines": [
                f"见证本：{int(_safe_float(lineage.get('witness_count'), float(len(witnesses))))}",
                f"待人工复核：{'是' if bool(lineage.get('needs_manual_review', True)) else '否'}",
                f"谱系键：{version_lineage_key}",
            ],
            "work_title": _as_text(lineage.get("work_title")),
            "fragment_title": _as_text(lineage.get("fragment_title")),
            "version_lineage_key": version_lineage_key,
            "witness_key": witness_keys[0] if len(witness_keys) == 1 else "",
            "document_title": document_titles[0] if len(document_titles) == 1 else "",
            "filter_candidates": _build_filter_candidate_map(
                work_title=lineage.get("work_title"),
                version_lineage_key=version_lineage_key,
                witness_key=witness_keys,
                document_title=document_titles,
            ),
        }
        items.append(item)
    return items


def _build_terminology_review_items(
    observe_philology: Dict[str, Any],
    decision_lookup: Dict[tuple[str, str], Dict[str, Any]],
) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for row in _as_dict_list(observe_philology.get("terminology_standard_table")):
        asset_key = _build_review_workbench_asset_key(
            "terminology_row",
            ("document_urn", row.get("document_urn")),
            ("document_title", row.get("document_title")),
            ("version_lineage_key", row.get("version_lineage_key")),
            ("witness_key", row.get("witness_key")),
            ("canonical", row.get("canonical")),
            ("label", row.get("label")),
        )
        observed_forms = _as_list(row.get("observed_forms"))
        notes = _as_list(row.get("notes"))
        item = {
            "asset_type": "terminology_row",
            "asset_key": asset_key,
            "submission_mode": "generic",
            "review_status": _normalize_workbench_review_status(row.get("review_status")),
            "needs_manual_review": bool(row.get("needs_manual_review", True)),
            "review_reasons": _as_list(row.get("review_reasons")) or ["terminology_machine_generated"],
            "reviewer": _as_text(row.get("reviewer")),
            "reviewed_at": _as_text(row.get("reviewed_at")),
            "decision_basis": _as_text(row.get("decision_basis")),
            "title": _as_text(row.get("canonical")) or "未命名术语",
            "subtitle": _as_text(row.get("label")) or _as_text(row.get("status")) or "术语标准表",
            "summary_lines": [
                f"观测形态：{'、'.join(str(item) for item in observed_forms[:3]) if observed_forms else '-'}",
                f"文献：{_as_text(row.get('document_title')) or '-'}",
                f"备注：{_as_text(notes[0]) if notes else '-'}",
            ],
            "document_title": _as_text(row.get("document_title")),
            "document_urn": _as_text(row.get("document_urn")),
            "work_title": _as_text(row.get("work_title")),
            "fragment_title": _as_text(row.get("fragment_title")),
            "version_lineage_key": _as_text(row.get("version_lineage_key")),
            "witness_key": _as_text(row.get("witness_key")),
            "canonical": _as_text(row.get("canonical")),
            "label": _as_text(row.get("label")),
            "filter_candidates": _build_filter_candidate_map(
                document_title=row.get("document_title"),
                work_title=row.get("work_title"),
                version_lineage_key=row.get("version_lineage_key"),
                witness_key=row.get("witness_key"),
            ),
        }
        items.append(_apply_review_workbench_decision(item, decision_lookup.get(("terminology_row", asset_key))))
    return items


def _build_collation_review_items(
    observe_philology: Dict[str, Any],
    decision_lookup: Dict[tuple[str, str], Dict[str, Any]],
) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for entry in _as_dict_list(observe_philology.get("collation_entries")):
        asset_key = _build_review_workbench_asset_key(
            "collation_entry",
            ("document_urn", entry.get("document_urn")),
            ("witness_urn", entry.get("witness_urn")),
            ("version_lineage_key", entry.get("version_lineage_key")),
            ("witness_key", entry.get("witness_key")),
            ("difference_type", entry.get("difference_type")),
            ("base_text", entry.get("base_text")),
            ("witness_text", entry.get("witness_text")),
        )
        item = {
            "asset_type": "collation_entry",
            "asset_key": asset_key,
            "submission_mode": "generic",
            "review_status": _normalize_workbench_review_status(entry.get("review_status")),
            "needs_manual_review": bool(entry.get("needs_manual_review", True)),
            "review_reasons": _as_list(entry.get("review_reasons")) or ["collation_machine_generated"],
            "reviewer": _as_text(entry.get("reviewer")),
            "reviewed_at": _as_text(entry.get("reviewed_at")),
            "decision_basis": _as_text(entry.get("decision_basis")),
            "title": f"{_as_text(entry.get('base_text')) or '-'} / {_as_text(entry.get('witness_text')) or '-'}",
            "subtitle": _as_text(entry.get("difference_type")) or "校勘条目",
            "summary_lines": [
                f"底本：{_as_text(entry.get('document_title')) or '-'}",
                f"见证本：{_as_text(entry.get('witness_title')) or _as_text(entry.get('witness_witness_key')) or '-'}",
                f"谱系：{_as_text(entry.get('version_lineage_key')) or '-'}",
            ],
            "document_title": _as_text(entry.get("document_title")),
            "document_urn": _as_text(entry.get("document_urn")),
            "work_title": _as_text(entry.get("work_title")),
            "fragment_title": _as_text(entry.get("fragment_title")),
            "version_lineage_key": _as_text(entry.get("version_lineage_key")),
            "witness_key": _as_text(entry.get("witness_key")),
            "difference_type": _as_text(entry.get("difference_type")),
            "base_text": _as_text(entry.get("base_text")),
            "witness_text": _as_text(entry.get("witness_text")),
            "filter_candidates": _build_filter_candidate_map(
                document_title=[entry.get("document_title"), entry.get("witness_title")],
                work_title=[entry.get("work_title"), entry.get("base_work_title"), entry.get("witness_work_title")],
                version_lineage_key=[entry.get("version_lineage_key"), entry.get("base_version_lineage_key"), entry.get("witness_version_lineage_key")],
                witness_key=[entry.get("witness_key"), entry.get("base_witness_key"), entry.get("witness_witness_key")],
            ),
        }
        items.append(_apply_review_workbench_decision(item, decision_lookup.get(("collation_entry", asset_key))))
    return items


def _build_fragment_candidate_review_items(
    observe_philology: Dict[str, Any],
    decision_lookup: Dict[tuple[str, str], Dict[str, Any]],
    active_filters: Dict[str, Any],
) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for candidate_kind in ("fragment_candidates", "lost_text_candidates", "citation_source_candidates"):
        for entry in _as_dict_list(observe_philology.get(candidate_kind)):
            asset_key = _build_review_workbench_asset_key(
                "fragment_candidate",
                ("candidate_kind", candidate_kind),
                ("fragment_candidate_id", entry.get("fragment_candidate_id") or entry.get("candidate_id") or entry.get("id")),
                ("document_urn", entry.get("document_urn")),
                ("version_lineage_key", entry.get("version_lineage_key")),
                ("witness_key", entry.get("witness_key")),
                ("fragment_title", entry.get("fragment_title") or entry.get("title")),
            )
            item = {
                "asset_type": "fragment_candidate",
                "asset_key": asset_key,
                "submission_mode": "generic",
                "review_status": _normalize_workbench_review_status(entry.get("review_status")),
                "needs_manual_review": bool(entry.get("needs_manual_review", True)),
                "review_reasons": _as_list(entry.get("review_reasons")) or ["fragment_candidate_machine_generated"],
                "reviewer": _as_text(entry.get("reviewer")),
                "reviewed_at": _as_text(entry.get("reviewed_at")),
                "decision_basis": _as_text(entry.get("decision_basis")),
                "title": _as_text(entry.get("fragment_title") or entry.get("title") or entry.get("document_title")) or "未命名辑佚候选",
                "subtitle": candidate_kind,
                "summary_lines": [
                    f"匹配分：{entry.get('match_score') if entry.get('match_score') is not None else '-'}",
                    f"依据：{_as_text(entry.get('reconstruction_basis')) or '-'}",
                    f"来源：{'、'.join(str(item) for item in _as_list(entry.get('source_refs'))[:3]) if _as_list(entry.get('source_refs')) else '-'}",
                ],
                "candidate_kind": candidate_kind,
                "document_title": _as_text(entry.get("document_title")),
                "document_urn": _as_text(entry.get("document_urn")),
                "work_title": _as_text(entry.get("work_title")),
                "fragment_title": _as_text(entry.get("fragment_title")),
                "version_lineage_key": _as_text(entry.get("version_lineage_key")),
                "witness_key": _as_text(entry.get("witness_key")),
                "fragment_candidate_id": _as_text(entry.get("fragment_candidate_id") or entry.get("candidate_id") or entry.get("id")),
                "filter_candidates": _build_filter_candidate_map(
                    document_title=[entry.get("document_title"), entry.get("witness_title")],
                    work_title=[entry.get("work_title"), entry.get("base_work_title"), entry.get("witness_work_title")],
                    version_lineage_key=[entry.get("version_lineage_key"), entry.get("base_version_lineage_key"), entry.get("witness_version_lineage_key")],
                    witness_key=[entry.get("witness_key"), entry.get("base_witness_key"), entry.get("witness_witness_key")],
                ),
            }
            item = _apply_review_workbench_decision(item, decision_lookup.get(("fragment_candidate", asset_key)))
            if _item_matches_catalog_filters(item, active_filters):
                items.append(item)
    return items


def _build_evidence_record_lookup(evidence_protocol: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for record in _as_dict_list(evidence_protocol.get("evidence_records")):
        evidence_id = _as_text(record.get("evidence_id") or record.get("id"))
        if evidence_id:
            lookup[evidence_id] = record
    return lookup


def _build_claim_filter_candidates(claim: Dict[str, Any], evidence_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, list[str]]:
    linked_records = [
        evidence_lookup[evidence_id]
        for evidence_id in (_as_list(claim.get("evidence_ids")) or [])
        if _as_text(evidence_id) in evidence_lookup
    ]
    provenances = [
        _as_dict(record.get("provenance"))
        for record in linked_records
    ]
    return _build_filter_candidate_map(
        document_title=[claim.get("document_title"), *(provenance.get("document_title") for provenance in provenances)],
        work_title=[claim.get("work_title"), *(provenance.get("work_title") for provenance in provenances)],
        version_lineage_key=[claim.get("version_lineage_key"), *(provenance.get("version_lineage_key") for provenance in provenances)],
        witness_key=[claim.get("witness_key"), *(provenance.get("witness_key") for provenance in provenances)],
    )


def _build_claim_review_items(
    evidence_protocol: Dict[str, Any],
    decision_lookup: Dict[tuple[str, str], Dict[str, Any]],
    active_filters: Dict[str, Any],
) -> list[Dict[str, Any]]:
    evidence_lookup = _build_evidence_record_lookup(evidence_protocol)
    items: list[Dict[str, Any]] = []
    for claim in _as_dict_list(evidence_protocol.get("claims")):
        claim_id = _as_text(claim.get("claim_id") or claim.get("id"))
        source_entity = _as_text(claim.get("source_entity") or claim.get("source"))
        target_entity = _as_text(claim.get("target_entity") or claim.get("target"))
        relation_type = _as_text(claim.get("relation_type") or claim.get("type") or "related")
        evidence_ids = _as_list(claim.get("evidence_ids"))
        filter_candidates = _build_claim_filter_candidates(claim, evidence_lookup)
        item = {
            "asset_type": "claim",
            "asset_key": _build_review_workbench_asset_key(
                "claim",
                ("claim_id", claim_id),
                ("source_entity", source_entity),
                ("target_entity", target_entity),
                ("relation_type", relation_type),
                ("evidence_ids", ",".join(str(item) for item in evidence_ids)),
            ),
            "submission_mode": "generic",
            "review_status": _normalize_workbench_review_status(claim.get("review_status")),
            "needs_manual_review": bool(claim.get("needs_manual_review", True)),
            "review_reasons": _as_list(claim.get("review_reasons")) or ["claim_candidate_generated"],
            "reviewer": _as_text(claim.get("reviewer")),
            "reviewed_at": _as_text(claim.get("reviewed_at")),
            "decision_basis": _as_text(claim.get("decision_basis")),
            "title": f"{source_entity or '未知源'} -> {target_entity or '未知目标'}",
            "subtitle": relation_type or "claim",
            "summary_lines": [
                f"支持数：{claim.get('support_count') if claim.get('support_count') is not None else '-'}",
                f"置信度：{claim.get('confidence') if claim.get('confidence') is not None else '-'}",
                f"证据 IDs：{'、'.join(str(item) for item in evidence_ids[:4]) if evidence_ids else '-'}",
            ],
            "document_title": _unique_texts(filter_candidates.get("document_title", []))[0] if filter_candidates.get("document_title") else "",
            "work_title": _unique_texts(filter_candidates.get("work_title", []))[0] if filter_candidates.get("work_title") else "",
            "version_lineage_key": _unique_texts(filter_candidates.get("version_lineage_key", []))[0] if filter_candidates.get("version_lineage_key") else "",
            "witness_key": _unique_texts(filter_candidates.get("witness_key", []))[0] if filter_candidates.get("witness_key") else "",
            "claim_id": claim_id,
            "source_entity": source_entity,
            "target_entity": target_entity,
            "relation_type": relation_type,
            "filter_candidates": filter_candidates,
        }
        item = _apply_review_workbench_decision(item, decision_lookup.get(("claim", item["asset_key"])))
        if _item_matches_catalog_filters(item, active_filters):
            items.append(item)
    return items


def _build_review_workbench(
    evidence_protocol: Dict[str, Any],
    observe_philology: Dict[str, Any],
    active_filters: Dict[str, Any],
) -> Dict[str, Any]:
    decision_lookup = _build_review_workbench_decision_lookup(observe_philology)
    sections = [
        _build_review_workbench_section("catalog_version_lineage", _build_catalog_lineage_review_items(observe_philology)),
        _build_review_workbench_section("terminology_row", _build_terminology_review_items(observe_philology, decision_lookup)),
        _build_review_workbench_section("collation_entry", _build_collation_review_items(observe_philology, decision_lookup)),
        _build_review_workbench_section("fragment_candidate", _build_fragment_candidate_review_items(observe_philology, decision_lookup, active_filters)),
        _build_review_workbench_section("claim", _build_claim_review_items(evidence_protocol, decision_lookup, active_filters)),
    ]
    return {
        "sections": sections,
        "section_count": len(sections),
        "total_item_count": sum(int(section.get("count") or 0) for section in sections),
    }


def _iter_report_artifact_candidates(result: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    for container in (result, _resolve_publish_phase_result(result)):
        if not isinstance(container, dict) or not container:
            continue
        for kind, path_text in get_phase_artifact_map(container).items():
            candidate = (str(kind), str(path_text))
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate

    for kind, path_text in iter_output_file_candidates(result):
        candidate = (str(kind), str(path_text))
        if candidate in seen:
            continue
        seen.add(candidate)
        yield candidate


def _resolve_primary_association(
    analysis_results: Dict[str, Any],
    research_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    statistical_analysis = _as_dict(get_phase_value(analysis_results, "statistical_analysis"))
    return _as_dict(get_phase_value(statistical_analysis, "primary_association"))


def _resolve_data_mining_summary(
    analysis_results: Dict[str, Any],
    research_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    data_mining_result = _as_dict(get_phase_value(analysis_results, "data_mining_result"))
    if not data_mining_result:
        return {}

    summary: Dict[str, Any] = {}
    for field_name in ("record_count", "transaction_count", "item_count"):
        value = data_mining_result.get(field_name)
        if value not in (None, ""):
            summary[field_name] = value

    methods_executed = [
        str(item).strip()
        for item in _as_list(data_mining_result.get("methods_executed"))
        if str(item).strip()
    ]
    if methods_executed:
        summary["methods_executed"] = methods_executed
        summary["method_count"] = len(methods_executed)

    association_rules = _as_list(_as_dict(data_mining_result.get("association_rules")).get("rules"))
    cluster_summary = _as_list(_as_dict(data_mining_result.get("clustering")).get("cluster_summary"))
    frequency_chi_square = _as_dict(data_mining_result.get("frequency_chi_square"))
    chi_square_top = _as_list(frequency_chi_square.get("chi_square_top"))
    herb_frequency = _as_list(frequency_chi_square.get("herb_frequency"))

    summary["association_rule_count"] = len(association_rules)
    summary["cluster_count"] = len(cluster_summary)
    summary["frequency_signal_count"] = len(chi_square_top)
    summary["high_frequency_herb_count"] = len(herb_frequency)
    return summary


def _count_phase_statuses(phases: list[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for phase in phases:
        status = str(phase.get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _status_score(status: str) -> float:
    mapping = {
        "completed": 1.0,
        "running": 0.68,
        "partial": 0.55,
        "queued": 0.35,
        "pending": 0.3,
        "skipped": 0.5,
        "failed": 0.18,
    }
    return mapping.get(status, 0.3)


def _quality_score(quality_metrics: Dict[str, Any]) -> float:
    confidence = _safe_float(quality_metrics.get("confidence_score"), -1.0)
    completeness = _safe_float(quality_metrics.get("completeness"), -1.0)
    values = [item for item in (confidence, completeness) if item >= 0]
    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


def _extract_graph_terms(value: Any) -> list[str]:
    terms: list[str] = []
    for item in _as_list(value):
        text = ""
        if isinstance(item, dict):
            for key in ("name", "label", "herb", "syndrome", "value"):
                candidate = str(item.get(key) or "").strip()
                if candidate:
                    text = candidate
                    break
        else:
            text = str(item).strip()
        if text:
            terms.append(text)
    return terms


def _resolve_graph_weight(similarity_score: Any, evidence_score: Any) -> float:
    values = []
    for raw_value in (similarity_score, evidence_score):
        numeric = _safe_float(raw_value, -1.0)
        if numeric < 0:
            continue
        values.append(max(0.0, min(1.0, numeric)))
    if not values:
        return 0.0
    return sum(values) / len(values)


def _ensure_graph_node(
    node_map: Dict[str, Dict[str, Any]],
    node_id: str,
    node_type: str,
) -> None:
    if not node_id:
        return

    existing = node_map.get(node_id)
    if existing is None:
        node_map[node_id] = {
            "id": node_id,
            "label": node_id,
            "type": node_type,
            "degree": 0,
            "weight": 0.0,
        }
        return

    if node_type == "formula":
        existing["type"] = "formula"


def _resolve_graph_match_names(match: Dict[str, Any]) -> tuple[str, str]:
    formula_name = str(match.get("formula_name") or "").strip()
    similar_formula_name = str(
        match.get("similar_formula_name") or match.get("formula_id") or ""
    ).strip()
    return formula_name, similar_formula_name


def _build_graph_edge_item(
    match: Dict[str, Any],
    formula_name: str,
    similar_formula_name: str,
) -> tuple[Dict[str, Any], float]:
    similarity_score = _safe_float(match.get("similarity_score"), -1.0)
    evidence_score = _safe_float(match.get("evidence_score"), -1.0)
    weight = _resolve_graph_weight(similarity_score, evidence_score)
    shared_herbs = _extract_graph_terms(match.get("shared_herbs"))
    shared_syndromes = _extract_graph_terms(match.get("shared_syndromes"))
    retrieval_sources = [
        str(item).strip()
        for item in _as_list(match.get("retrieval_sources"))
        if str(item).strip()
    ]
    edge_item = {
        "source": formula_name,
        "target": similar_formula_name,
        "relation": "类方关联",
        "weight": round(weight, 3),
        "similarity_score": round(similarity_score, 3) if similarity_score >= 0 else None,
        "evidence_score": round(evidence_score, 3) if evidence_score >= 0 else None,
        "shared_herb_count": len(shared_herbs),
        "shared_syndrome_count": len(shared_syndromes),
        "shared_herbs": shared_herbs,
        "shared_syndromes": shared_syndromes,
        "graph_evidence_source": str(match.get("graph_evidence_source") or "").strip(),
        "retrieval_sources": retrieval_sources,
    }
    return edge_item, weight


def _update_graph_node_metrics(
    node_map: Dict[str, Dict[str, Any]],
    node_id: str,
    weight: float,
) -> None:
    node = node_map.get(node_id)
    if node is None:
        return
    node["degree"] = int(_safe_float(node.get("degree"), 0.0)) + 1
    node["weight"] = max(_safe_float(node.get("weight"), 0.0), weight)


def _append_graph_match(
    node_map: Dict[str, Dict[str, Any]],
    edge_items: list[Dict[str, Any]],
    match: Dict[str, Any],
) -> None:
    formula_name, similar_formula_name = _resolve_graph_match_names(match)
    if not formula_name or not similar_formula_name:
        return

    _ensure_graph_node(node_map, formula_name, "formula")
    _ensure_graph_node(node_map, similar_formula_name, "similar_formula")
    edge_item, weight = _build_graph_edge_item(match, formula_name, similar_formula_name)
    edge_items.append(edge_item)
    _update_graph_node_metrics(node_map, formula_name, weight)
    _update_graph_node_metrics(node_map, similar_formula_name, weight)


def _normalize_graph_nodes(node_map: Dict[str, Dict[str, Any]]) -> list[Dict[str, Any]]:
    nodes = list(node_map.values())
    nodes.sort(key=lambda item: (-_safe_float(item.get("degree"), 0.0), str(item.get("label") or "")))
    for node in nodes:
        node["weight"] = round(max(0.0, min(1.0, _safe_float(node.get("weight"), 0.0))), 3)
    return nodes


def _sort_graph_edges(edge_items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    edge_items.sort(
        key=lambda item: (
            -_safe_float(item.get("weight"), 0.0),
            str(item.get("source") or ""),
            str(item.get("target") or ""),
        )
    )
    return edge_items


def _resolve_analysis_relation_count(analysis_results: Dict[str, Any]) -> Optional[int]:
    relation_statistics = _as_dict(analysis_results.get("relation_statistics"))
    statistics = _as_dict(analysis_results.get("statistics"))
    for candidate in (
        relation_statistics.get("total_relations"),
        statistics.get("relation_count"),
        analysis_results.get("relation_count"),
    ):
        if candidate not in (None, ""):
            return int(_safe_float(candidate, 0.0))
    return None


def _resolve_graph_formula_count(
    graph_summary: Dict[str, Any],
    nodes: list[Dict[str, Any]],
) -> int:
    formula_count = int(_safe_float(graph_summary.get("formula_count"), -1.0))
    if formula_count >= 0:
        return formula_count
    return len({node.get("id") for node in nodes if node.get("type") == "formula"})


def _resolve_graph_match_count(
    graph_summary: Dict[str, Any],
    edge_items: list[Dict[str, Any]],
) -> int:
    match_count = int(_safe_float(graph_summary.get("match_count"), -1.0))
    if match_count >= 0:
        return match_count
    return len(edge_items)


def _build_graph_stats(
    graph_summary: Dict[str, Any],
    analysis_results: Dict[str, Any],
    nodes: list[Dict[str, Any]],
    edge_items: list[Dict[str, Any]],
) -> Dict[str, Any]:
    stats = {
        "node_count": len(nodes),
        "edge_count": len(edge_items),
        "formula_count": _resolve_graph_formula_count(graph_summary, nodes),
        "match_count": _resolve_graph_match_count(graph_summary, edge_items),
        "max_degree": max((int(_safe_float(node.get("degree"), 0.0)) for node in nodes), default=0),
        "max_weight": round(max((_safe_float(edge.get("weight"), 0.0) for edge in edge_items), default=0.0), 3),
    }
    analysis_relation_count = _resolve_analysis_relation_count(analysis_results)
    if analysis_relation_count is not None:
        stats["analysis_relation_count"] = analysis_relation_count
    return stats


def _build_graph_highlights(edge_items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    highlights = []
    for edge in edge_items[:6]:
        highlights.append(
            {
                "title": f"{edge.get('source') or '-'} -> {edge.get('target') or '-'}",
                "relation": edge.get("relation") or "类方关联",
                "weight": edge.get("weight"),
                "similarity_score": edge.get("similarity_score"),
                "evidence_score": edge.get("evidence_score"),
                "shared_herbs": edge.get("shared_herbs") or [],
                "shared_syndromes": edge.get("shared_syndromes") or [],
            }
        )
    return highlights


def _build_knowledge_graph_board(result: Dict[str, Any]) -> Dict[str, Any]:
    research_artifact = _resolve_publish_highlight_payload(result, "research_artifact")
    analysis_results = _resolve_publish_highlight_payload(result, "analysis_results")
    graph_summary = _as_dict(research_artifact.get("similar_formula_graph_evidence_summary"))
    matches = [item for item in _as_list(graph_summary.get("matches")) if isinstance(item, dict)]

    node_map: Dict[str, Dict[str, Any]] = {}
    edge_items: list[Dict[str, Any]] = []

    for match in matches:
        _append_graph_match(node_map, edge_items, match)

    nodes = _normalize_graph_nodes(node_map)
    sorted_edges = _sort_graph_edges(edge_items)
    source = "research_artifact.similar_formula_graph_evidence_summary" if graph_summary else "unavailable"

    return {
        "source": source,
        "stats": _build_graph_stats(graph_summary, analysis_results, nodes, sorted_edges),
        "nodes": nodes,
        "edges": sorted_edges,
        "highlights": _build_graph_highlights(sorted_edges),
    }


def _resolve_dashboard_total_duration_sec(
    result: Dict[str, Any],
    phases: list[Dict[str, Any]],
) -> float:
    total_duration_sec = _safe_float(result.get("total_duration_sec"), 0.0)
    if total_duration_sec > 0:
        return total_duration_sec
    return sum(_safe_float(phase.get("duration_sec"), 0.0) for phase in phases)


def _resolve_dashboard_data_mining_methods(
    analysis_results: Dict[str, Any],
    data_mining_summary: Dict[str, Any],
) -> list[str]:
    data_mining_result = _as_dict(get_phase_value(analysis_results, "data_mining_result"))
    raw_methods = data_mining_result.get("methods_executed")
    if not raw_methods:
        raw_methods = data_mining_summary.get("methods_executed")
    return [
        str(item).strip()
        for item in _as_list(raw_methods)
        if str(item).strip()
    ]


def _build_dashboard_phase_items(phases: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    phase_items = []
    for index, phase in enumerate(phases, start=1):
        phase_name = str(phase.get("phase") or f"phase_{index}")
        phase_status = str(phase.get("status") or "pending")
        phase_items.append(
            {
                "index": index,
                "phase": phase_name,
                "label": format_phase_name(phase_name),
                "status": phase_status,
                "status_label": format_status(phase_status),
                "duration_sec": _safe_float(phase.get("duration_sec"), 0.0),
                "summary": _as_dict(phase.get("summary")),
                "error": str(phase.get("error") or ""),
            }
        )
    return phase_items


def _build_dashboard_overview(
    snapshot: Dict[str, Any],
    result: Dict[str, Any],
    status: str,
    progress: float,
    current_phase: str,
    total_duration_sec: float,
    health_score: float,
) -> Dict[str, Any]:
    return {
        "status": status,
        "status_label": format_status(status),
        "progress": round(progress, 3),
        "current_phase": current_phase,
        "current_phase_label": format_phase_name(current_phase),
        "total_duration_sec": round(total_duration_sec, 3),
        "started_at": result.get("started_at") or snapshot.get("started_at") or "",
        "completed_at": result.get("completed_at") or snapshot.get("completed_at") or "",
        "health_score": round(health_score, 3),
    }


def _build_dashboard_phase_board(
    phase_status_counts: Dict[str, int],
    total_phase_count: int,
    completed_phase_count: int,
    phase_completion_rate: float,
    phase_items: list[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "total": total_phase_count,
        "completed": completed_phase_count,
        "failed": phase_status_counts.get("failed", 0),
        "partial": phase_status_counts.get("partial", 0),
        "skipped": phase_status_counts.get("skipped", 0),
        "running": phase_status_counts.get("running", 0),
        "completion_rate": round(phase_completion_rate, 3),
        "items": phase_items,
    }


def _build_dashboard_evidence_board(
    evidence_protocol: Dict[str, Any],
    primary_association: Dict[str, Any],
    data_mining_summary: Dict[str, Any],
    data_mining_methods: list[str],
    observe_philology: Dict[str, Any],
    philology_filter_contract: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_records = _as_list(evidence_protocol.get("evidence_records"))
    claims = _as_list(evidence_protocol.get("claims"))
    catalog_summary = _as_dict(observe_philology.get("catalog_summary"))
    catalog_metrics = _as_dict(catalog_summary.get("summary"))
    active_catalog_filters = _as_dict(philology_filter_contract.get("active_filters"))
    catalog_document_count = int(
        _safe_float(
            observe_philology.get("catalog_document_count") or catalog_metrics.get("catalog_document_count"),
            0.0,
        )
    )
    review_workbench = _build_review_workbench(evidence_protocol, observe_philology, active_catalog_filters)
    return {
        "evidence_count": len(evidence_records),
        "claim_count": len(claims),
        "association_rule_count": int(_safe_float(data_mining_summary.get("association_rule_count"), 0.0)),
        "cluster_count": int(_safe_float(data_mining_summary.get("cluster_count"), 0.0)),
        "primary_association": primary_association,
        "data_mining_summary": data_mining_summary,
        "data_mining_methods": data_mining_methods,
        "philology": observe_philology,
        "terminology_standard_table_count": int(_safe_float(observe_philology.get("terminology_standard_table_count"), 0.0)),
        "collation_entry_count": int(_safe_float(observe_philology.get("collation_entry_count"), 0.0)),
        "philology_document_count": max(
            int(_safe_float(observe_philology.get("document_count"), 0.0)),
            catalog_document_count,
        ),
        "catalog_summary": catalog_summary,
        "catalog_document_count": catalog_document_count,
        "version_lineage_count": int(
            _safe_float(observe_philology.get("version_lineage_count") or catalog_metrics.get("version_lineage_count"), 0.0)
        ),
        "witness_count": int(
            _safe_float(observe_philology.get("witness_count") or catalog_metrics.get("witness_count"), 0.0)
        ),
        "fragment_candidate_count": int(_safe_float(observe_philology.get("fragment_candidate_count"), 0.0)),
        "missing_catalog_metadata_count": int(
            _safe_float(
                observe_philology.get("missing_catalog_metadata_count")
                or catalog_metrics.get("missing_core_metadata_count"),
                0.0,
            )
        ),
        "active_catalog_filters": active_catalog_filters,
        "catalog_filter_options": _as_dict(philology_filter_contract.get("options")),
        "review_workbench": review_workbench,
    }


def _build_dashboard_protocol_inputs(protocol_inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "study_type": protocol_inputs.get("study_type"),
        "primary_outcome": protocol_inputs.get("primary_outcome"),
        "intervention": protocol_inputs.get("intervention"),
        "comparison": protocol_inputs.get("comparison"),
    }


def build_research_dashboard_payload(
    snapshot: Dict[str, Any],
    *,
    philology_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a visualization-friendly dashboard payload from a job snapshot."""

    job_id = str(snapshot.get("job_id") or "").strip()
    topic = str(snapshot.get("topic") or "").strip()
    status = str(snapshot.get("status") or "queued").strip() or "queued"
    progress = max(0.0, min(100.0, _safe_float(snapshot.get("progress"), 0.0)))
    current_phase = str(snapshot.get("current_phase") or "").strip()

    result = _as_dict(snapshot.get("result"))
    phases_raw = _as_list(result.get("phases"))
    phases: list[Dict[str, Any]] = [phase for phase in phases_raw if isinstance(phase, dict)]
    phase_status_counts = _count_phase_statuses(phases)
    total_phase_count = len(phases)
    completed_phase_count = phase_status_counts.get("completed", 0)
    phase_completion_rate = (completed_phase_count / total_phase_count) if total_phase_count > 0 else 0.0

    total_duration_sec = _resolve_dashboard_total_duration_sec(result, phases)

    pipeline_metadata = _as_dict(result.get("pipeline_metadata"))
    protocol_inputs = _as_dict(pipeline_metadata.get("protocol_inputs"))

    analysis_results = _resolve_publish_highlight_payload(result, "analysis_results")
    research_artifact = _resolve_publish_highlight_payload(result, "research_artifact")
    quality_metrics = _as_dict(analysis_results.get("quality_metrics"))
    evidence_protocol = _as_dict(analysis_results.get("evidence_protocol"))
    primary_association = _resolve_primary_association(analysis_results, research_artifact)
    data_mining_summary = _resolve_data_mining_summary(analysis_results, research_artifact)
    data_mining_methods = _resolve_dashboard_data_mining_methods(analysis_results, data_mining_summary)
    observe_philology_raw = _resolve_observe_philology(result)
    philology_filter_contract = build_observe_philology_filter_contract(observe_philology_raw, philology_filters)
    observe_philology = filter_observe_philology_assets(observe_philology_raw, philology_filters)
    knowledge_graph_board = _build_knowledge_graph_board(result)
    phase_items = _build_dashboard_phase_items(phases)

    quality_score = _quality_score(quality_metrics)
    health_score = max(
        0.0,
        min(1.0, 0.55 * _status_score(status) + 0.25 * phase_completion_rate + 0.2 * quality_score),
    )

    return {
        "job_id": job_id,
        "topic": topic,
        "cycle_id": str(result.get("cycle_id") or "").strip(),
        "overview": _build_dashboard_overview(
            snapshot,
            result,
            status,
            progress,
            current_phase,
            total_duration_sec,
            health_score,
        ),
        "phase_board": _build_dashboard_phase_board(
            phase_status_counts,
            total_phase_count,
            completed_phase_count,
            phase_completion_rate,
            phase_items,
        ),
        "quality_board": {
            "confidence_score": _safe_float(quality_metrics.get("confidence_score"), 0.0),
            "completeness": _safe_float(quality_metrics.get("completeness"), 0.0),
            "quality_score": round(quality_score, 3),
        },
        "evidence_board": _build_dashboard_evidence_board(
            evidence_protocol,
            primary_association,
            data_mining_summary,
            data_mining_methods,
            observe_philology,
            philology_filter_contract,
        ),
        "knowledge_graph_board": knowledge_graph_board,
        "protocol_inputs": _build_dashboard_protocol_inputs(protocol_inputs),
        "metadata": {
            "pipeline_cycle_name": pipeline_metadata.get("cycle_name"),
            "summary_generated": True,
        },
    }
