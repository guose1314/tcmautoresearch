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


def _normalize_optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


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


def _build_knowledge_graph_board(result: Dict[str, Any]) -> Dict[str, Any]:
    research_artifact = _as_dict(result.get("research_artifact"))
    analysis_results = _as_dict(result.get("analysis_results"))
    graph_summary = _as_dict(research_artifact.get("similar_formula_graph_evidence_summary"))
    matches = [item for item in _as_list(graph_summary.get("matches")) if isinstance(item, dict)]

    node_map: Dict[str, Dict[str, Any]] = {}
    edge_items: list[Dict[str, Any]] = []

    def ensure_node(node_id: str, node_type: str) -> None:
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

    for match in matches:
        formula_name = str(match.get("formula_name") or "").strip()
        similar_formula_name = str(match.get("similar_formula_name") or match.get("formula_id") or "").strip()
        if not formula_name or not similar_formula_name:
            continue

        ensure_node(formula_name, "formula")
        ensure_node(similar_formula_name, "similar_formula")

        similarity_score = _safe_float(match.get("similarity_score"), -1.0)
        evidence_score = _safe_float(match.get("evidence_score"), -1.0)
        weight = _resolve_graph_weight(similarity_score, evidence_score)
        shared_herbs = _extract_graph_terms(match.get("shared_herbs"))
        shared_syndromes = _extract_graph_terms(match.get("shared_syndromes"))
        retrieval_sources = [
            str(item).strip() for item in _as_list(match.get("retrieval_sources")) if str(item).strip()
        ]

        edge_items.append(
            {
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
        )

        source_node = node_map.get(formula_name)
        target_node = node_map.get(similar_formula_name)
        if source_node is not None:
            source_node["degree"] = int(_safe_float(source_node.get("degree"), 0.0)) + 1
            source_node["weight"] = max(_safe_float(source_node.get("weight"), 0.0), weight)
        if target_node is not None:
            target_node["degree"] = int(_safe_float(target_node.get("degree"), 0.0)) + 1
            target_node["weight"] = max(_safe_float(target_node.get("weight"), 0.0), weight)

    nodes = list(node_map.values())
    nodes.sort(key=lambda item: (-_safe_float(item.get("degree"), 0.0), str(item.get("label") or "")))
    for node in nodes:
        node["weight"] = round(max(0.0, min(1.0, _safe_float(node.get("weight"), 0.0))), 3)

    edge_items.sort(
        key=lambda item: (
            -_safe_float(item.get("weight"), 0.0),
            str(item.get("source") or ""),
            str(item.get("target") or ""),
        )
    )

    relation_statistics = _as_dict(analysis_results.get("relation_statistics"))
    statistics = _as_dict(analysis_results.get("statistics"))
    analysis_relation_count = relation_statistics.get("total_relations")
    if analysis_relation_count in (None, ""):
        analysis_relation_count = statistics.get("relation_count")
    if analysis_relation_count in (None, ""):
        analysis_relation_count = analysis_results.get("relation_count")

    node_count = len(nodes)
    edge_count = len(edge_items)
    formula_count = int(_safe_float(graph_summary.get("formula_count"), -1.0))
    if formula_count < 0:
        formula_count = len({node.get("id") for node in nodes if node.get("type") == "formula"})
    match_count = int(_safe_float(graph_summary.get("match_count"), -1.0))
    if match_count < 0:
        match_count = edge_count

    stats = {
        "node_count": node_count,
        "edge_count": edge_count,
        "formula_count": formula_count,
        "match_count": match_count,
        "max_degree": max((int(_safe_float(node.get("degree"), 0.0)) for node in nodes), default=0),
        "max_weight": round(max((_safe_float(edge.get("weight"), 0.0) for edge in edge_items), default=0.0), 3),
    }
    if analysis_relation_count not in (None, ""):
        stats["analysis_relation_count"] = int(_safe_float(analysis_relation_count, 0.0))

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

    source = "research_artifact.similar_formula_graph_evidence_summary"
    if not graph_summary:
        source = "unavailable"

    return {
        "source": source,
        "stats": stats,
        "nodes": nodes,
        "edges": edge_items,
        "highlights": highlights,
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

    total_duration_sec = _safe_float(result.get("total_duration_sec"), 0.0)
    if total_duration_sec <= 0:
        total_duration_sec = sum(_safe_float(phase.get("duration_sec"), 0.0) for phase in phases)

    pipeline_metadata = _as_dict(result.get("pipeline_metadata"))
    protocol_inputs = _as_dict(pipeline_metadata.get("protocol_inputs"))

    analysis_results = _as_dict(result.get("analysis_results"))
    quality_metrics = _as_dict(analysis_results.get("quality_metrics"))
    evidence_protocol = _as_dict(analysis_results.get("evidence_protocol"))
    data_mining_result = _as_dict(analysis_results.get("data_mining_result"))
    knowledge_graph_board = _build_knowledge_graph_board(result)

    evidence_records = _as_list(evidence_protocol.get("evidence_records"))
    claims = _as_list(evidence_protocol.get("claims"))
    association_rules = _as_list(_as_dict(data_mining_result.get("association_rules")).get("rules"))
    cluster_summary = _as_list(_as_dict(data_mining_result.get("clustering")).get("cluster_summary"))

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

    quality_score = _quality_score(quality_metrics)
    health_score = max(
        0.0,
        min(1.0, 0.55 * _status_score(status) + 0.25 * phase_completion_rate + 0.2 * quality_score),
    )

    return {
        "job_id": job_id,
        "topic": topic,
        "cycle_id": str(result.get("cycle_id") or "").strip(),
        "overview": {
            "status": status,
            "status_label": format_status(status),
            "progress": round(progress, 3),
            "current_phase": current_phase,
            "current_phase_label": format_phase_name(current_phase),
            "total_duration_sec": round(total_duration_sec, 3),
            "started_at": result.get("started_at") or snapshot.get("started_at") or "",
            "completed_at": result.get("completed_at") or snapshot.get("completed_at") or "",
            "health_score": round(health_score, 3),
        },
        "phase_board": {
            "total": total_phase_count,
            "completed": completed_phase_count,
            "failed": phase_status_counts.get("failed", 0),
            "partial": phase_status_counts.get("partial", 0),
            "skipped": phase_status_counts.get("skipped", 0),
            "running": phase_status_counts.get("running", 0),
            "completion_rate": round(phase_completion_rate, 3),
            "items": phase_items,
        },
        "quality_board": {
            "confidence_score": _safe_float(quality_metrics.get("confidence_score"), 0.0),
            "completeness": _safe_float(quality_metrics.get("completeness"), 0.0),
            "quality_score": round(quality_score, 3),
        },
        "evidence_board": {
            "evidence_count": len(evidence_records),
            "claim_count": len(claims),
            "association_rule_count": len(association_rules),
            "cluster_count": len(cluster_summary),
        },
        "knowledge_graph_board": knowledge_graph_board,
        "protocol_inputs": {
            "study_type": protocol_inputs.get("study_type"),
            "primary_outcome": protocol_inputs.get("primary_outcome"),
            "intervention": protocol_inputs.get("intervention"),
            "comparison": protocol_inputs.get("comparison"),
        },
        "metadata": {
            "pipeline_cycle_name": pipeline_metadata.get("cycle_name"),
            "summary_generated": True,
        },
    }
