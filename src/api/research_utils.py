"""Shared helpers for research-oriented REST endpoints."""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi.responses import FileResponse

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
) -> Dict[str, Any]:
    evidence_records = _as_list(evidence_protocol.get("evidence_records"))
    claims = _as_list(evidence_protocol.get("claims"))
    return {
        "evidence_count": len(evidence_records),
        "claim_count": len(claims),
        "association_rule_count": int(_safe_float(data_mining_summary.get("association_rule_count"), 0.0)),
        "cluster_count": int(_safe_float(data_mining_summary.get("cluster_count"), 0.0)),
        "primary_association": primary_association,
        "data_mining_summary": data_mining_summary,
        "data_mining_methods": data_mining_methods,
    }


def _build_dashboard_protocol_inputs(protocol_inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "study_type": protocol_inputs.get("study_type"),
        "primary_outcome": protocol_inputs.get("primary_outcome"),
        "intervention": protocol_inputs.get("intervention"),
        "comparison": protocol_inputs.get("comparison"),
    }


def build_research_dashboard_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
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
        ),
        "knowledge_graph_board": knowledge_graph_board,
        "protocol_inputs": _build_dashboard_protocol_inputs(protocol_inputs),
        "metadata": {
            "pipeline_cycle_name": pipeline_metadata.get("cycle_name"),
            "summary_generated": True,
        },
    }
