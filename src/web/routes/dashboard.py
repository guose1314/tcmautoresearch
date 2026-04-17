# -*- coding: utf-8 -*-
"""仪表盘 API 路由 — 为 dashboard.html 的 HTMX 请求提供 HTML 片段。

端点清单（均返回 text/html 片段供 HTMX 局部替换）：
  GET /api/dashboard/stats     — 统计卡片
  GET /api/dashboard/quality   — 质量评分
  GET /api/projects/recent     — 近期项目列表
  GET /api/projects            — 科研项目页
  GET /api/ai/assistant        — AI 助手面板
  GET /api/literature          — 文献库
  GET /api/knowledge-graph     — 知识图谱
  GET /api/analysis/tools      — 分析工具
  GET /api/output              — 输出中心
  GET /api/settings            — 系统设置
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime
from html import escape
from math import ceil
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from src.api.research_utils import build_research_dashboard_payload
from src.research.observe_philology import (
    build_observe_philology_filter_contract,
    filter_observe_philology_assets,
)
from src.web.auth import get_current_user
from src.web.ops.research_session_contract import resolve_phase_result
from src.web.ops.research_session_service import (
    apply_catalog_review,
    apply_catalog_review_batch,
    apply_philology_review,
    apply_philology_review_batch,
    get_research_session,
    list_research_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path("data")
_OUTPUT_DIR = Path("output")
_PHILOLOGY_TERMINOLOGY_PAGE_SIZE = 8
_PHILOLOGY_COLLATION_PAGE_SIZE = 6


def _count_corpus_files() -> int:
    """统计 data/ 目录下的古籍文件数。"""
    try:
        return sum(1 for f in _DATA_DIR.glob("*.txt") if f.is_file())
    except Exception:
        return 0


def _count_output_files() -> int:
    """统计 output/ 目录下的结果文件数。"""
    try:
        if not _OUTPUT_DIR.exists():
            return 0
        return sum(1 for f in _OUTPUT_DIR.rglob("*") if f.is_file())
    except Exception:
        return 0


def _card(label: str, value: str, color: str = "gray-800") -> str:
    return (
        f'<div class="bg-white rounded-xl shadow-sm p-5 border border-gray-100">'
        f'<p class="text-xs text-gray-500 uppercase tracking-wide">{label}</p>'
        f'<p class="text-2xl font-bold text-{color} mt-1">{value}</p>'
        f"</div>"
    )


def _empty_state(icon: str, title: str, desc: str) -> str:
    return (
        f'<div class="flex flex-col items-center justify-center py-12 text-center">'
        f'<span class="text-5xl mb-4">{icon}</span>'
        f'<h3 class="text-lg font-semibold text-gray-700 mb-2">{title}</h3>'
        f'<p class="text-sm text-gray-400 max-w-md">{desc}</p>'
        f"</div>"
    )


def _section_header(title: str, subtitle: str = "") -> str:
    sub = f'<p class="text-sm text-gray-400 mt-1">{subtitle}</p>' if subtitle else ""
    return (
        f'<h2 class="font-semibold text-gray-800 text-lg mb-4">{title}</h2>{sub}'
    )


def _session_mtime(session: Dict[str, Any]) -> float:
    for key in ("updated_at", "created_at", "completed_at", "started_at"):
        raw_value = session.get(key)
        if not raw_value:
            continue
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
    return 0.0


def _session_phases(session: Dict[str, Any]) -> List[str]:
    phase_executions = session.get("phase_executions") or {}
    if isinstance(phase_executions, dict):
        phases = [str(name).strip() for name in phase_executions.keys() if str(name).strip()]
        if phases:
            return phases
    if isinstance(phase_executions, list):
        phases = [
            str(item.get("phase") or "").strip()
            for item in phase_executions
            if isinstance(item, dict) and str(item.get("phase") or "").strip()
        ]
        if phases:
            return phases

    analysis_summary = session.get("analysis_summary") or (session.get("metadata") or {}).get("analysis_summary") or {}
    completed = analysis_summary.get("completed_phases") if isinstance(analysis_summary, dict) else []
    if isinstance(completed, list):
        return [str(phase).strip() for phase in completed if str(phase).strip()]
    return []


def _build_session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    deliverables = session.get("deliverables") or []
    artifacts = session.get("artifacts") or []
    has_reports = bool(deliverables) or any(
        isinstance(item, dict)
        and str(item.get("artifact_type") or "").strip().lower() in {"paper", "report"}
        for item in artifacts
    )
    title = str(
        session.get("cycle_name")
        or session.get("title")
        or session.get("description")
        or session.get("research_objective")
        or session.get("question")
        or "无标题"
    ).strip() or "无标题"
    question = str(
        session.get("research_objective")
        or session.get("question")
        or session.get("description")
        or ""
    ).strip()
    return {
        "file": str(session.get("file") or ""),
        "title": title[:80],
        "question": question,
        "status": str(session.get("status") or "unknown"),
        "cycle_id": str(session.get("cycle_id") or ""),
        "phases": _session_phases(session),
        "has_reports": has_reports,
        "mtime": _session_mtime(session),
    }


def _safe_html(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _safe_join(values: Any, sep: str = "、") -> str:
    if not isinstance(values, list):
        return "—"
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        return "—"
    return _safe_html(sep.join(items))


def _normalize_page(value: Any, default: int = 1) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return default
    return page if page > 0 else default


def _parse_urlencoded_body(raw_body: bytes) -> Dict[str, str]:
    parsed = parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return {
        str(key): str(values[-1] if values else "")
        for key, values in parsed.items()
    }


def _paginate_items(items: List[Dict[str, Any]], page: int, page_size: int) -> Dict[str, Any]:
    total_count = len(items)
    total_pages = max(1, ceil(total_count / page_size)) if total_count else 1
    current_page = min(max(_normalize_page(page), 1), total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": current_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_count": total_count,
    }


def _project_detail_url(
    cycle_id: str,
    *,
    terminology_page: int = 1,
    collation_page: int = 1,
    drawer: bool = False,
    document_title: str = "",
    work_title: str = "",
    version_lineage_key: str = "",
    witness_key: str = "",
) -> str:
    query = [
        f"terminology_page={max(1, terminology_page)}",
        f"collation_page={max(1, collation_page)}",
    ]
    for key, value in (
        ("document_title", document_title),
        ("work_title", work_title),
        ("version_lineage_key", version_lineage_key),
        ("witness_key", witness_key),
    ):
        normalized_value = str(value or "").strip()
        if normalized_value:
            query.append(f"{key}={quote(normalized_value, safe='')}")
    if drawer:
        query.append("drawer=1")
    return f"/api/projects/{quote(str(cycle_id or '').strip(), safe='')}/detail?{'&'.join(query)}"


def _project_fragment_url(
    cycle_id: str,
    *,
    document_urn: str = "",
    document_title: str = "",
    highlight: str = "",
    context: str = "",
    role: str = "base",
) -> str:
    query: List[str] = []
    for key, value in (
        ("document_urn", document_urn),
        ("document_title", document_title),
        ("highlight", highlight),
        ("context", context),
        ("role", role),
    ):
        normalized = str(value or "").strip()
        if normalized:
            query.append(f"{key}={quote(normalized, safe='')}")
    return f"/api/projects/{quote(str(cycle_id or '').strip(), safe='')}/fragment-preview?{'&'.join(query)}"


def _render_session_status_badge(status: str) -> str:
    status_map = {
        "completed": ("✅", "已完成", "bg-emerald-50 text-emerald-700"),
        "active": ("🔄", "进行中", "bg-blue-50 text-blue-700"),
        "running": ("🔄", "运行中", "bg-blue-50 text-blue-700"),
        "failed": ("❌", "失败", "bg-red-50 text-red-600"),
        "pending": ("⏳", "待执行", "bg-amber-50 text-amber-700"),
    }
    icon, label, cls = status_map.get(status, ("❓", status or "未知", "bg-gray-50 text-gray-500"))
    return (
        f'<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium {cls}">'
        f"{icon} {_safe_html(label)}</span>"
    )


def _render_phase_tags(phases: List[str]) -> str:
    if not phases:
        return '<span class="text-xs text-gray-300">暂无阶段记录</span>'
    return " ".join(
        f'<span class="inline-block px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-50 text-emerald-700">{_safe_html(phase)}</span>'
        for phase in phases
    )


def _render_detail_pagination(
    cycle_id: str,
    *,
    section: str,
    page: int,
    total_pages: int,
    total_count: int,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    if total_count <= 0:
        return ""

    target_id = "#session-detail-drawer-content" if drawer else "#project-detail-panel"
    prev_term_page = page - 1 if section == "terminology" else terminology_page
    next_term_page = page + 1 if section == "terminology" else terminology_page
    prev_collation_page = page - 1 if section == "collation" else collation_page
    next_collation_page = page + 1 if section == "collation" else collation_page

    def _button(label: str, url: str, disabled: bool) -> str:
        if disabled:
            return (
                '<span class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 '
                'text-gray-300 bg-gray-50 cursor-not-allowed">'
                f"{_safe_html(label)}</span>"
            )
        return (
            f'<button type="button" class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 '
            f'text-gray-600 hover:text-gray-900 hover:border-gray-300 hover:bg-gray-50 transition" '
            f'hx-get="{_safe_html(url)}" hx-target="{target_id}" hx-swap="outerHTML">{_safe_html(label)}</button>'
        )

    prev_url = _project_detail_url(
        cycle_id,
        terminology_page=prev_term_page,
        collation_page=prev_collation_page,
        drawer=drawer,
        document_title=document_title,
        work_title=work_title,
        version_lineage_key=version_lineage_key,
        witness_key=witness_key,
    )
    next_url = _project_detail_url(
        cycle_id,
        terminology_page=next_term_page,
        collation_page=next_collation_page,
        drawer=drawer,
        document_title=document_title,
        work_title=work_title,
        version_lineage_key=version_lineage_key,
        witness_key=witness_key,
    )
    return f"""
    <div class="mt-3 flex items-center justify-between gap-3 text-xs text-gray-500">
        <span>第 {page} / {total_pages} 页 · 共 {total_count} 条</span>
        <div class="flex items-center gap-2">
            {_button("上一页", prev_url, page <= 1)}
            {_button("下一页", next_url, page >= total_pages)}
        </div>
    </div>
    """


def _render_catalog_review_badge(status: str) -> str:
    mapping = {
        "pending": ("待核", "bg-amber-50 text-amber-700"),
        "accepted": ("已核", "bg-emerald-50 text-emerald-700"),
        "rejected": ("驳回", "bg-rose-50 text-rose-700"),
        "needs_source": ("待补据", "bg-slate-100 text-slate-700"),
    }
    label, cls = mapping.get(str(status or "").strip().lower(), (str(status or "待核").strip() or "待核", "bg-amber-50 text-amber-700"))
    return f'<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium {cls}">{_safe_html(label)}</span>'


def _resolve_dashboard_reviewer(current_user: Any) -> str:
    if isinstance(current_user, dict):
        for field_name in ("display_name", "username", "principal", "user_id"):
            value = str(current_user.get(field_name) or "").strip()
            if value:
                return value
    return "工作台用户"


def _render_catalog_review_meta(record: Dict[str, Any]) -> str:
    reviewer = str(record.get("reviewer") or "").strip()
    reviewed_at = str(record.get("reviewed_at") or "").strip()
    decision_basis = str(record.get("decision_basis") or "").strip()
    parts = [part for part in (reviewer, reviewed_at, decision_basis) if part]
    if not parts:
        return '<p class="text-[11px] text-gray-400">尚未写回人工校核记录</p>'
    return f'<p class="text-[11px] text-gray-400">{" · ".join(_safe_html(part) for part in parts)}</p>'


def _render_catalog_review_actions(
    cycle_id: str,
    lineage: Dict[str, Any],
    *,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    target_id = "#session-detail-drawer-content" if drawer else "#project-detail-panel"
    target_version_lineage_key = str(lineage.get("version_lineage_key") or lineage.get("work_fragment_key") or "").strip()
    if not target_version_lineage_key:
        return ""

    hidden_fields = "".join(
        f'<input type="hidden" name="{_safe_html(name)}" value="{_safe_html(value)}">'
        for name, value in (
            ("scope", "version_lineage"),
            ("target_version_lineage_key", target_version_lineage_key),
            ("terminology_page", str(max(1, terminology_page))),
            ("collation_page", str(max(1, collation_page))),
            ("drawer", "1" if drawer else "0"),
            ("document_title", document_title),
            ("work_title", work_title),
            ("version_lineage_key", version_lineage_key),
            ("witness_key", witness_key),
        )
    )
    buttons = (
        ("accepted", "标记已核", "bg-emerald-600 text-white hover:bg-emerald-700"),
        ("rejected", "标记驳回", "bg-rose-600 text-white hover:bg-rose-700"),
        ("needs_source", "待补据", "bg-slate-800 text-white hover:bg-slate-900"),
        ("pending", "退回待核", "bg-amber-100 text-amber-800 hover:bg-amber-200"),
    )
    buttons_html = "".join(
        f'<button type="submit" name="review_status" value="{_safe_html(status)}" '
        f'class="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition {cls}">{_safe_html(label)}</button>'
        for status, label, cls in buttons
    )
    decision_basis = str(lineage.get("decision_basis") or "").strip()
    basis_field = (
        '<label class="block text-[11px] text-gray-500">'
        '审核依据 / 备注'
        f'<textarea name="decision_basis" rows="2" '
        'class="mt-1 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 '
        'placeholder:text-gray-400 focus:border-emerald-300 focus:bg-white focus:outline-none" '
        'placeholder="填写审核依据、缺失来源说明或人工备注">'
        f'{_safe_html(decision_basis)}</textarea>'
        '</label>'
    )
    return (
        f'<form class="space-y-2 pt-1" '
        f'hx-post="/api/projects/{quote(str(cycle_id or "").strip(), safe="")}/catalog-review" '
        f'hx-target="{target_id}" hx-swap="outerHTML">'
        f'{hidden_fields}{basis_field}<div class="flex flex-wrap items-center gap-2">{buttons_html}</div></form>'
    )


def _format_active_catalog_filter_summary(filter_contract: Dict[str, Any]) -> str:
    active_filters = filter_contract.get("active_filters") if isinstance(filter_contract.get("active_filters"), dict) else {}
    options = filter_contract.get("options") if isinstance(filter_contract.get("options"), dict) else {}
    option_labels = {
        field_name: {
            str(item.get("value") or ""): str(item.get("label") or item.get("value") or "")
            for item in value
            if isinstance(item, dict)
        }
        for field_name, value in options.items()
        if isinstance(value, list)
    }
    active_items = []
    for field_name, field_label in (
        ("work_title", "作品"),
        ("version_lineage_key", "版本谱系"),
        ("witness_key", "见证本"),
        ("document_title", "文献标题"),
    ):
        value = str(active_filters.get(field_name) or "").strip()
        if not value:
            continue
        label = option_labels.get(field_name, {}).get(value, value)
        active_items.append((field_label, label))
    if not active_items:
        return "按作品、版本谱系、见证本与文献标题同步筛选 Observe 文献学资产"
    if len(active_items) == 1:
        return f"当前筛选：{active_items[0][1]}"
    return "当前筛选：" + " / ".join(f"{field_label}={label}" for field_label, label in active_items)


def _render_catalog_filter_chips(
    cycle_id: str,
    *,
    filter_contract: Dict[str, Any],
    drawer: bool,
) -> str:
    options = filter_contract.get("options") if isinstance(filter_contract.get("options"), dict) else {}
    active_filters = filter_contract.get("active_filters") if isinstance(filter_contract.get("active_filters"), dict) else {}
    if not options:
        return ""

    target_id = "#session-detail-drawer-content" if drawer else "#project-detail-panel"

    def _build_chip_url(next_filters: Dict[str, str]) -> str:
        return _project_detail_url(
            cycle_id,
            terminology_page=1,
            collation_page=1,
            drawer=drawer,
            document_title=str(next_filters.get("document_title") or ""),
            work_title=str(next_filters.get("work_title") or ""),
            version_lineage_key=str(next_filters.get("version_lineage_key") or ""),
            witness_key=str(next_filters.get("witness_key") or ""),
        )

    def _chip(label: str, *, active: bool, next_filters: Dict[str, str]) -> str:
        base_class = "inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium border transition"
        cls = (
            "bg-emerald-600 border-emerald-600 text-white"
            if active
            else "bg-white border-gray-200 text-gray-600 hover:text-gray-900 hover:border-gray-300"
        )
        return (
            f'<button type="button" class="{base_class} {cls}" '
            f'hx-get="{_safe_html(_build_chip_url(next_filters))}" '
            f'hx-target="{target_id}" hx-swap="outerHTML">{_safe_html(label)}</button>'
        )

    sections_html = []
    for field_name, heading in (
        ("work_title", "作品"),
        ("version_lineage_key", "版本谱系"),
        ("witness_key", "见证本"),
        ("document_title", "文献标题"),
    ):
        field_options = [item for item in options.get(field_name, []) if isinstance(item, dict)]
        if not field_options:
            continue
        current_value = str(active_filters.get(field_name) or "").strip()
        chips = [
            _chip(
                f"全部{heading}",
                active=not current_value,
                next_filters={**active_filters, field_name: ""},
            )
        ]
        chips.extend(
            _chip(
                str(option.get("label") or option.get("value") or ""),
                active=str(option.get("value") or "") == current_value,
                next_filters={**active_filters, field_name: str(option.get("value") or "")},
            )
            for option in field_options
        )
        sections_html.append(
            f'<div class="space-y-2"><h5 class="text-xs font-semibold uppercase tracking-wide text-gray-500">{_safe_html(heading)}</h5><div class="flex flex-wrap gap-2">{"".join(chips)}</div></div>'
        )

    if not sections_html:
        return ""

    summary = _format_active_catalog_filter_summary(filter_contract)
    return f"""
    <div class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
                <h4 class="text-sm font-semibold text-gray-800">目录学筛选</h4>
                <p class="text-sm text-gray-400 mt-1">作品、版本谱系、见证本与文献标题共用同一套过滤条件</p>
            </div>
            <span class="text-xs text-emerald-700">{_safe_html(summary)}</span>
        </div>
        {''.join(sections_html)}
    </div>
    """


def _render_exegesis_summary_card(catalog_metrics: Dict[str, Any]) -> str:
    """训诂摘要卡片 — 展示释义覆盖度、来源分布、义项判别情况。"""
    entry_count = int(catalog_metrics.get("exegesis_entry_count") or 0)
    if entry_count == 0:
        return ""
    coverage = catalog_metrics.get("exegesis_definition_coverage")
    coverage_text = f"{coverage:.0%}" if coverage is not None else "—"
    source_dist = catalog_metrics.get("exegesis_source_distribution") or {}
    category_dist = catalog_metrics.get("exegesis_category_distribution") or {}
    disambiguation_count = int(catalog_metrics.get("exegesis_disambiguation_count") or 0)
    needs_disambiguation = int(catalog_metrics.get("exegesis_needs_disambiguation") or 0)
    dynasty_counts = catalog_metrics.get("exegesis_dynasty_term_counts") or {}

    source_labels = {
        "config_terminology_standard": "配置标准",
        "structured_tcm_knowledge": "结构化知识",
        "terminology_note": "附注推导",
        "canonical_fallback": "机器归并",
    }
    source_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs">'
        f'{_safe_html(source_labels.get(src, src))} {count}</span>'
        for src, count in sorted(source_dist.items())
    ) or '<span class="text-xs text-gray-400">暂无来源分布</span>'

    category_labels = {
        "herb": "药名", "formula": "方剂", "syndrome": "证候",
        "theory": "理论", "efficacy": "功效", "common": "通用",
    }
    category_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-blue-50 text-blue-700 text-xs">'
        f'{_safe_html(category_labels.get(cat, cat))} {count}</span>'
        for cat, count in sorted(category_dist.items())
    ) or '<span class="text-xs text-gray-400">暂无类别分布</span>'

    dynasty_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-amber-50 text-amber-700 text-xs">'
        f'{_safe_html(d)} {count}</span>'
        for d, count in sorted(dynasty_counts.items())
    )

    return f"""
    <div class="rounded-2xl border border-indigo-100 bg-indigo-50/30 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 class="text-sm font-semibold text-gray-800">训诂摘要</h4>
            <span class="text-xs text-indigo-600">释义覆盖 {_safe_html(coverage_text)}</span>
        </div>
        <div class="grid grid-cols-3 gap-3">
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">义项总数</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{entry_count}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">已判别</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{disambiguation_count}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">待判别</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{needs_disambiguation}</p>
            </div>
        </div>
        <div class="space-y-1">
            <p class="text-[11px] uppercase tracking-wide text-gray-400">释义来源</p>
            <div class="flex flex-wrap gap-2">{source_badges}</div>
        </div>
        <div class="space-y-1">
            <p class="text-[11px] uppercase tracking-wide text-gray-400">义项类别</p>
            <div class="flex flex-wrap gap-2">{category_badges}</div>
        </div>
        {'<div class="space-y-1"><p class="text-[11px] uppercase tracking-wide text-gray-400">时代表达</p><div class="flex flex-wrap gap-2">' + dynasty_badges + '</div></div>' if dynasty_badges else ''}
    </div>
    """


def _render_fragment_summary_card(catalog_metrics: Dict[str, Any]) -> str:
    """辑佚摘要卡片 — 展示候选项分类计数、评分、复核状态。"""
    total = int(catalog_metrics.get("fragment_total_count") or 0)
    if total == 0:
        return ""
    fragment_count = int(catalog_metrics.get("fragment_candidate_count") or 0)
    lost_text_count = int(catalog_metrics.get("lost_text_candidate_count") or 0)
    citation_source_count = int(catalog_metrics.get("citation_source_candidate_count") or 0)
    needs_review = int(catalog_metrics.get("fragment_needs_review_count") or 0)
    high_confidence = int(catalog_metrics.get("fragment_high_confidence_count") or 0)
    avg_score = catalog_metrics.get("fragment_avg_score")
    avg_score_text = f"{avg_score:.2f}" if avg_score is not None else "—"
    review_dist = catalog_metrics.get("fragment_review_status_distribution") or {}

    review_labels = {"pending": "待复核", "accepted": "已采纳", "rejected": "已驳回"}
    review_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-orange-50 text-orange-700 text-xs">'
        f'{_safe_html(review_labels.get(status, status))} {count}</span>'
        for status, count in sorted(review_dist.items())
    ) or '<span class="text-xs text-gray-400">暂无复核记录</span>'

    return f"""
    <div class="rounded-2xl border border-amber-100 bg-amber-50/30 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 class="text-sm font-semibold text-gray-800">辑佚摘要</h4>
            <span class="text-xs text-amber-600">平均置信 {_safe_html(avg_score_text)}</span>
        </div>
        <div class="grid grid-cols-3 gap-3">
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">疑似佚文</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{fragment_count}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">疑似佚失</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{lost_text_count}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">引文来源</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{citation_source_count}</p>
            </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">高置信</p>
                <p class="text-lg font-semibold text-emerald-700 mt-1">{high_confidence}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">待复核</p>
                <p class="text-lg font-semibold text-amber-700 mt-1">{needs_review}</p>
            </div>
        </div>
        <div class="space-y-1">
            <p class="text-[11px] uppercase tracking-wide text-gray-400">复核状态</p>
            <div class="flex flex-wrap gap-2">{review_badges}</div>
        </div>
    </div>
    """


def _render_evidence_chain_summary_card(catalog_metrics: Dict[str, Any]) -> str:
    """考据证据链摘要卡片 — 展示 claim 类型分布、置信度、冲突与复核状态。"""
    total = int(catalog_metrics.get("evidence_chain_count") or 0)
    if total == 0:
        return ""
    conflict_count = int(catalog_metrics.get("evidence_conflict_count") or 0)
    needs_review = int(catalog_metrics.get("evidence_needs_review_count") or 0)
    confidence_avg = catalog_metrics.get("evidence_confidence_avg")
    confidence_avg_text = f"{confidence_avg:.2f}" if confidence_avg is not None else "—"
    claim_dist = catalog_metrics.get("evidence_claim_type_distribution") or {}
    judgment_dist = catalog_metrics.get("evidence_judgment_distribution") or {}

    claim_labels = {"authorship_attribution": "作者归属", "version_chronology": "版本先后", "citation_source": "引文来源"}
    claim_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-teal-50 text-teal-700 text-xs">'
        f'{_safe_html(claim_labels.get(ct, ct))} {count}</span>'
        for ct, count in sorted(claim_dist.items())
    ) or '<span class="text-xs text-gray-400">暂无 claim</span>'

    judgment_labels = {"rule_based": "规则判定", "needs_review": "待人工复核"}
    judgment_badges = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-cyan-50 text-cyan-700 text-xs">'
        f'{_safe_html(judgment_labels.get(jt, jt))} {count}</span>'
        for jt, count in sorted(judgment_dist.items())
    ) or '<span class="text-xs text-gray-400">暂无判定</span>'

    return f"""
    <div class="rounded-2xl border border-teal-100 bg-teal-50/30 p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 class="text-sm font-semibold text-gray-800">考据证据链</h4>
            <span class="text-xs text-teal-600">平均置信 {_safe_html(confidence_avg_text)}</span>
        </div>
        <div class="grid grid-cols-3 gap-3">
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">证据链</p>
                <p class="text-lg font-semibold text-gray-800 mt-1">{total}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">冲突</p>
                <p class="text-lg font-semibold text-red-600 mt-1">{conflict_count}</p>
            </div>
            <div class="rounded-xl bg-white border border-slate-100 p-3">
                <p class="text-[11px] uppercase tracking-wide text-gray-400">待复核</p>
                <p class="text-lg font-semibold text-amber-700 mt-1">{needs_review}</p>
            </div>
        </div>
        <div class="space-y-1">
            <p class="text-[11px] uppercase tracking-wide text-gray-400">claim 类型</p>
            <div class="flex flex-wrap gap-2">{claim_badges}</div>
        </div>
        <div class="space-y-1">
            <p class="text-[11px] uppercase tracking-wide text-gray-400">判定类型</p>
            <div class="flex flex-wrap gap-2">{judgment_badges}</div>
        </div>
    </div>
    """


def _build_session_dashboard_snapshot(session: Dict[str, Any]) -> Dict[str, Any]:
    phase_executions = session.get("phase_executions") if isinstance(session.get("phase_executions"), dict) else {}
    phase_items: List[Dict[str, Any]] = []
    phase_results: Dict[str, Dict[str, Any]] = {}
    for phase_name, execution in phase_executions.items():
        if not isinstance(execution, dict):
            continue
        normalized_phase = str(execution.get("phase") or phase_name or "").strip().lower() or str(phase_name)
        result = resolve_phase_result(execution)
        phase_items.append(
            {
                "phase": normalized_phase,
                "status": str(execution.get("status") or result.get("status") or "completed").strip() or "completed",
                "duration_sec": float(execution.get("duration") or result.get("duration_sec") or 0.0),
                "summary": result.get("summary") if isinstance(result.get("summary"), dict) else {},
            }
        )
        if result:
            phase_results[normalized_phase] = result

    status = str(session.get("status") or "completed").strip().lower() or "completed"
    progress = 100.0 if status == "completed" else 0.0
    return {
        "job_id": str(session.get("cycle_id") or "").strip(),
        "topic": str(
            session.get("research_objective")
            or session.get("description")
            or session.get("cycle_name")
            or session.get("cycle_id")
            or ""
        ).strip(),
        "status": status,
        "progress": progress,
        "current_phase": str(session.get("current_phase") or "observe").strip().lower() or "observe",
        "result": {
            "cycle_id": str(session.get("cycle_id") or "").strip(),
            "pipeline_metadata": {
                "cycle_name": str(session.get("cycle_name") or "").strip(),
                "description": str(session.get("description") or "").strip(),
            },
            "phases": phase_items,
            "phase_results": phase_results,
            "learning_feedback_library": (
                session.get("learning_feedback_library")
                if isinstance(session.get("learning_feedback_library"), dict)
                else {}
            ),
            "observe_philology": session.get("observe_philology") if isinstance(session.get("observe_philology"), dict) else {},
        },
    }


def _render_workbench_review_actions(
    cycle_id: str,
    item: Dict[str, Any],
    *,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    asset_type = str(item.get("asset_type") or "").strip()
    asset_key = str(item.get("asset_key") or "").strip()
    if not asset_type or not asset_key:
        return ""

    target_id = "#session-detail-drawer-content" if drawer else "#project-detail-panel"
    hidden_fields = "".join(
        f'<input type="hidden" name="{_safe_html(name)}" value="{_safe_html(value)}">'
        for name, value in (
            ("asset_type", asset_type),
            ("asset_key", asset_key),
            ("candidate_kind", str(item.get("candidate_kind") or "")),
            ("document_title", str(item.get("document_title") or "")),
            ("document_urn", str(item.get("document_urn") or "")),
            ("work_title", str(item.get("work_title") or "")),
            ("fragment_title", str(item.get("fragment_title") or "")),
            ("version_lineage_key", str(item.get("version_lineage_key") or "")),
            ("witness_key", str(item.get("witness_key") or "")),
            ("canonical", str(item.get("canonical") or "")),
            ("label", str(item.get("label") or "")),
            ("difference_type", str(item.get("difference_type") or "")),
            ("base_text", str(item.get("base_text") or "")),
            ("witness_text", str(item.get("witness_text") or "")),
            ("claim_id", str(item.get("claim_id") or "")),
            ("source_entity", str(item.get("source_entity") or "")),
            ("target_entity", str(item.get("target_entity") or "")),
            ("relation_type", str(item.get("relation_type") or "")),
            ("fragment_candidate_id", str(item.get("fragment_candidate_id") or "")),
            ("evidence_chain_id", str(item.get("evidence_chain_id") or "")),
            ("claim_type", str(item.get("claim_type") or "")),
            ("claim_statement", str(item.get("claim_statement") or "")),
            ("judgment_type", str(item.get("judgment_type") or "")),
            ("terminology_page", str(max(1, terminology_page))),
            ("collation_page", str(max(1, collation_page))),
            ("drawer", "1" if drawer else "0"),
            ("document_title_filter", document_title),
            ("work_title_filter", work_title),
            ("version_lineage_key_filter", version_lineage_key),
            ("witness_key_filter", witness_key),
        )
    )
    buttons = (
        ("accepted", "标记已核", "bg-emerald-600 text-white hover:bg-emerald-700"),
        ("rejected", "标记驳回", "bg-rose-600 text-white hover:bg-rose-700"),
        ("needs_source", "待补据", "bg-slate-800 text-white hover:bg-slate-900"),
        ("pending", "退回待核", "bg-amber-100 text-amber-800 hover:bg-amber-200"),
    )
    buttons_html = "".join(
        f'<button type="submit" name="review_status" value="{_safe_html(status)}" '
        f'class="inline-flex items-center px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition {cls}">{_safe_html(label)}</button>'
        for status, label, cls in buttons
    )
    decision_basis = str(item.get("decision_basis") or "").strip()
    return (
        f'<form class="space-y-2 pt-1" '
        f'hx-post="/api/projects/{quote(str(cycle_id or "").strip(), safe="")}/philology-review" '
        f'hx-target="{target_id}" hx-swap="outerHTML">'
        f'{hidden_fields}'
        '<label class="block text-[11px] text-gray-500">审核依据 / 备注'
        f'<textarea name="decision_basis" rows="2" '
        'class="mt-1 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 '
        'placeholder:text-gray-400 focus:border-emerald-300 focus:bg-white focus:outline-none" '
        'placeholder="填写审核依据、补据说明或人工备注">'
        f'{_safe_html(decision_basis)}</textarea></label>'
        f'<div class="flex flex-wrap items-center gap-2">{buttons_html}</div></form>'
    )


def _render_workbench_review_card(
    cycle_id: str,
    item: Dict[str, Any],
    *,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    summary_lines = [str(line).strip() for line in item.get("summary_lines") or [] if str(line).strip()]
    summary_html = "".join(
        f'<p class="text-xs text-gray-500 leading-5">{_safe_html(line)}</p>'
        for line in summary_lines
    ) or '<p class="text-xs text-gray-400">暂无摘要说明</p>'
    subtitle = str(item.get("subtitle") or "").strip()
    card_review_status = str(item.get("review_status") or "pending").strip()
    return f"""
    <article class="rounded-xl border border-gray-100 bg-white p-4 shadow-sm space-y-3" data-review-status="{_safe_html(card_review_status)}">
        <div class="flex flex-wrap items-start justify-between gap-2">
            <div>
                <h5 class="text-sm font-semibold text-gray-800">{_safe_html(item.get('title') or '未命名条目')}</h5>
                <p class="text-xs text-gray-500 mt-1">{_safe_html(subtitle or '文献学工作台条目')}</p>
            </div>
            {_render_catalog_review_badge(str(item.get('review_status') or 'pending'))}
        </div>
        <div class="space-y-1">{summary_html}</div>
        {_render_catalog_review_meta(item)}
        {_render_workbench_review_actions(
            cycle_id,
            item,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=drawer,
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
        )}
    </article>
    """


def _render_workbench_review_section(
    cycle_id: str,
    section: Dict[str, Any],
    *,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    items = [dict(item) for item in section.get("items") or [] if isinstance(item, dict)]
    if not items:
        return ""
    cards_html = "".join(
        _render_workbench_review_card(
            cycle_id,
            item,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=drawer,
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
        )
        for item in items
    )
    return f"""
    <section class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
                <h4 class="text-base font-semibold text-gray-800">{_safe_html(section.get('title') or '文献学校核分组')}</h4>
                <p class="text-sm text-gray-400 mt-1">{_safe_html(section.get('description') or '按当前目录学筛选展示可审核条目')}</p>
            </div>
            <span class="text-xs text-gray-500">卡片 {len(items)}</span>
        </div>
        <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">{cards_html}</div>
    </section>
    """


def _render_philology_review_workbench(
    cycle_id: str,
    review_workbench: Dict[str, Any],
    filter_summary: str,
    *,
    terminology_page: int,
    collation_page: int,
    drawer: bool,
    document_title: str,
    work_title: str,
    version_lineage_key: str,
    witness_key: str,
) -> str:
    sections = [
        dict(section)
        for section in (review_workbench.get("sections") or [])
        if isinstance(section, dict) and str(section.get("asset_type") or "") != "catalog_version_lineage"
    ]
    visible_sections = [section for section in sections if any(isinstance(item, dict) for item in (section.get("items") or []))]
    if not visible_sections:
        return f"""
        <section class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4 space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h4 class="text-base font-semibold text-gray-800">文献学校核工作台</h4>
                    <p class="text-sm text-gray-400 mt-1">目录谱系仍在上方目录学基线复核，其余术语、校勘、辑佚、考据证据链条目统一在此处理</p>
                </div>
                <span class="text-xs text-emerald-700">{_safe_html(filter_summary)}</span>
            </div>
            {_empty_state('🧾', '暂无可审核条目', '当前筛选结果下还没有可在详情页直接写回的文献学工作台卡片。')}
        </section>
        """
    sections_html = "".join(
        _render_workbench_review_section(
            cycle_id,
            section,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=drawer,
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
        )
        for section in visible_sections
    )
    total_cards = sum(len(section.get("items") or []) for section in visible_sections)
    # collect unique review_status values across all visible items for filter chips
    all_review_statuses: set[str] = set()
    for section in visible_sections:
        for item in section.get("items") or []:
            if isinstance(item, dict):
                rs = str(item.get("review_status") or "").strip()
                if rs:
                    all_review_statuses.add(rs)
    status_labels = {
        "pending": "待审核",
        "accepted": "已通过",
        "rejected": "已驳回",
        "needs_source": "待补据",
    }
    review_status_chips = "".join(
        f'<button type="button" data-status="{_safe_html(status)}" '
        f'class="wb-status-chip inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium border transition '
        f'bg-white border-gray-200 text-gray-600 hover:text-gray-900 hover:border-gray-300" '
        f'onclick="toggleWorkbenchStatusFilter(this)">{_safe_html(status_labels.get(status, status))}</button>'
        for status in ("pending", "accepted", "rejected", "needs_source")
        if status in all_review_statuses
    )
    review_filter_html = ""
    if review_status_chips:
        review_filter_html = (
            '<div class="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-100 mt-2">'
            '<span class="text-xs text-gray-500 mr-1">复核状态：</span>'
            f'<button type="button" class="wb-status-chip wb-status-active inline-flex items-center px-3 py-1.5 '
            f'rounded-full text-xs font-medium border transition '
            f'bg-emerald-600 border-emerald-600 text-white" '
            f'data-status="" onclick="toggleWorkbenchStatusFilter(this)">全部</button>'
            f'{review_status_chips}</div>'
        )
    filter_script = """
    <script>
    function toggleWorkbenchStatusFilter(btn) {
      var status = btn.getAttribute("data-status") || "";
      document.querySelectorAll(".wb-status-chip").forEach(function(c) {
        c.classList.remove("wb-status-active", "bg-emerald-600", "border-emerald-600", "text-white");
        c.classList.add("bg-white", "border-gray-200", "text-gray-600");
      });
      btn.classList.add("wb-status-active", "bg-emerald-600", "border-emerald-600", "text-white");
      btn.classList.remove("bg-white", "border-gray-200", "text-gray-600");
      document.querySelectorAll("[data-review-status]").forEach(function(card) {
        card.style.display = (!status || card.getAttribute("data-review-status") === status) ? "" : "none";
      });
    }
    </script>
    """
    return f"""
    <section class="space-y-4">
        <div class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h4 class="text-base font-semibold text-gray-800">文献学校核工作台</h4>
                    <p class="text-sm text-gray-400 mt-1">目录谱系仍在上方目录学基线复核，其余术语、校勘、辑佚、考据证据链条目统一在此处理</p>
                </div>
                <div class="text-right text-xs text-gray-500">
                    <p>可见卡片 {total_cards}</p>
                    <p class="mt-1 text-emerald-700">{_safe_html(filter_summary)}</p>
                </div>
            </div>
            {review_filter_html}
        </div>
        {sections_html}
    </section>
    {filter_script}
    """


def _resolve_observe_document(
    session: Dict[str, Any],
    *,
    document_urn: str = "",
    document_title: str = "",
) -> Dict[str, Any]:
    documents = session.get("observe_documents") if isinstance(session.get("observe_documents"), list) else []
    normalized_urn = str(document_urn or "").strip()
    normalized_title = str(document_title or "").strip()
    for document in documents:
        if not isinstance(document, dict):
            continue
        urn = str(document.get("urn") or document.get("document_urn") or "").strip()
        title = str(document.get("title") or document.get("document_title") or "").strip()
        if normalized_urn and urn == normalized_urn:
            return dict(document)
        if normalized_title and title == normalized_title:
            return dict(document)
    return {}


def _candidate_document_paths(document: Dict[str, Any]) -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    def _append(raw_path: Any) -> None:
        text = str(raw_path or "").strip()
        if not text:
            return
        normalized = os.path.normcase(os.path.abspath(text)) if os.path.isabs(text) else os.path.normcase(str(Path(text)))
        if normalized in seen:
            return
        seen.add(normalized)
        candidates.append(Path(text))

    _append(document.get("source_file"))
    _append(document.get("urn") or document.get("document_urn"))

    title = str(document.get("title") or document.get("document_title") or "").strip()
    if title and _DATA_DIR.exists():
        for path in _DATA_DIR.glob("*.txt"):
            stem = str(path.stem or "").strip()
            if title in stem or stem in title:
                _append(path)
    return candidates


def _read_document_source_text(document: Dict[str, Any]) -> tuple[str, str]:
    for candidate in _candidate_document_paths(document):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="ignore"), str(candidate)
        except Exception:
            continue
    return "", ""


def _extract_fragment_window(source_text: str, *, highlight: str, context: str, window: int = 96) -> tuple[str, str, bool]:
    text = str(source_text or "")
    highlight_text = str(highlight or "").strip()
    context_text = str(context or "").strip()
    anchor = ""
    if context_text and context_text in text:
        anchor = context_text
    elif highlight_text and highlight_text in text:
        anchor = highlight_text

    if anchor:
        start = max(text.find(anchor) - window, 0)
        end = min(text.find(anchor) + len(anchor) + window, len(text))
        fragment = text[start:end]
        if start > 0:
            fragment = "..." + fragment
        if end < len(text):
            fragment = fragment + "..."
        mark_term = highlight_text if highlight_text and highlight_text in fragment else anchor
        return fragment, mark_term, True

    fallback = context_text or highlight_text or text[: window * 2] or "未能生成原始文档片段预览。"
    if text and len(text) > window * 2 and not context_text and not highlight_text:
        fallback = text[: window * 2] + "..."
    mark_term = highlight_text if highlight_text and highlight_text in fallback else ""
    return fallback, mark_term, False


def _highlight_fragment_html(fragment: str, mark_term: str) -> str:
    escaped_fragment = _safe_html(fragment)
    escaped_mark = _safe_html(mark_term)
    if not escaped_mark or escaped_mark not in escaped_fragment:
        return escaped_fragment
    return escaped_fragment.replace(
        escaped_mark,
        f'<mark class="bg-amber-200 text-amber-950 px-0.5 rounded">{escaped_mark}</mark>',
    )


def _render_fragment_preview_modal(
    session: Dict[str, Any] | None,
    *,
    document_urn: str = "",
    document_title: str = "",
    highlight: str = "",
    context: str = "",
    role: str = "base",
    error_message: str = "",
) -> str:
    if not isinstance(session, dict):
        message = error_message or "未找到可预览的原始文档片段。"
        return f"""
        <div id="document-fragment-modal-content" class="bg-white rounded-2xl border border-gray-100 shadow-2xl max-w-3xl w-full overflow-hidden">
            <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-3">
                <div>
                    <h3 class="text-base font-semibold text-gray-800">原始文档片段</h3>
                    <p class="text-sm text-gray-400 mt-1">校勘上下文定位预览</p>
                </div>
                <button type="button" class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 text-sm text-gray-500 hover:text-gray-800 hover:border-gray-300 transition" onclick="closeDocumentFragmentModal()">关闭</button>
            </div>
            <div class="p-6">{_empty_state("📖", "暂无片段", message)}</div>
        </div>
        """

    document = _resolve_observe_document(session, document_urn=document_urn, document_title=document_title)
    resolved_title = str(document.get("title") or document_title or document.get("document_title") or document_urn or "未标注文献").strip()
    source_text, source_path = _read_document_source_text(document)
    fragment, mark_term, located = _extract_fragment_window(
        source_text,
        highlight=highlight,
        context=context,
    ) if source_text else _extract_fragment_window("", highlight=highlight, context=context)
    source_type = str(document.get("source_type") or document.get("metadata", {}).get("source_type") or "unknown").strip() or "unknown"
    role_label = "Base 原文" if str(role or "").strip().lower() == "base" else "Witness 对校文"
    status_badge = (
        '<span class="inline-flex items-center px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium">已定位本地源文献片段</span>'
        if located and source_text
        else '<span class="inline-flex items-center px-2 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium">未定位到本地全文，展示校勘上下文预览</span>'
    )
    source_label = source_path or str(document.get("source_file") or document.get("urn") or document_urn or "未记录源路径").strip() or "未记录源路径"
    return f"""
    <div id="document-fragment-modal-content" class="bg-white rounded-2xl border border-gray-100 shadow-2xl max-w-3xl w-full overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-3">
            <div>
                <div class="flex flex-wrap items-center gap-2">{status_badge}</div>
                <h3 class="text-base font-semibold text-gray-800 mt-2">原始文档片段</h3>
                <p class="text-sm text-gray-400 mt-1">{_safe_html(resolved_title)} · {role_label}</p>
            </div>
            <button type="button" class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 text-sm text-gray-500 hover:text-gray-800 hover:border-gray-300 transition" onclick="closeDocumentFragmentModal()">关闭</button>
        </div>
        <div class="p-5 space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-gray-500">
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p>文献标题：<span class="text-gray-700">{_safe_html(resolved_title)}</span></p>
                    <p class="mt-1">来源类型：<span class="text-gray-700">{_safe_html(source_type)}</span></p>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p>高亮词：<span class="text-gray-700">{_safe_html(highlight or '—')}</span></p>
                    <p class="mt-1 break-all">源路径 / URN：<span class="text-gray-700">{_safe_html(source_label)}</span></p>
                </div>
            </div>
            <div class="rounded-2xl border border-gray-100 bg-gray-50 p-4">
                <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">片段预览</p>
                <div class="rounded-xl bg-white border border-gray-100 p-4 text-sm leading-7 text-gray-700 whitespace-pre-wrap font-serif">{_highlight_fragment_html(fragment, mark_term)}</div>
            </div>
        </div>
    </div>
    """


def _render_session_detail_panel(
    session: Dict[str, Any] | None,
    *,
    terminology_page: int = 1,
    collation_page: int = 1,
    drawer: bool = False,
    document_title: str = "",
    work_title: str = "",
    version_lineage_key: str = "",
    witness_key: str = "",
    error_message: str = "",
) -> str:
    panel_id = "session-detail-drawer-content" if drawer else "project-detail-panel"
    panel_class = "bg-white rounded-2xl border border-gray-100 shadow-sm"
    close_button = (
        '<button type="button" class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 '
        'text-sm text-gray-500 hover:text-gray-800 hover:border-gray-300 transition" '
        'onclick="closeSessionDetailDrawer()">关闭</button>'
        if drawer
        else ""
    )

    if not isinstance(session, dict):
        message = error_message or "选择一条研究任务后，可在这里查看 Observe 阶段的术语标准表、校勘条目与文献学校核工作台。"
        return f"""
        <div id="{panel_id}" class="{panel_class}">
            <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-3">
                <div>
                    <h3 class="text-base font-semibold text-gray-800">研究任务详情</h3>
                    <p class="text-sm text-gray-400 mt-1">分页展开 Observe 文献学结构化资产</p>
                </div>
                {close_button}
            </div>
            <div class="p-6">{_empty_state("📚", "暂无详情", message)}</div>
        </div>
        """

    notice_banner = ""
    if error_message:
        notice_banner = (
            '<div class="mx-5 mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">'
            f'{_safe_html(error_message)}</div>'
        )

    title = str(
        session.get("cycle_name")
        or session.get("title")
        or session.get("research_objective")
        or session.get("description")
        or session.get("cycle_id")
        or "未命名研究任务"
    ).strip() or "未命名研究任务"
    objective = str(session.get("research_objective") or session.get("description") or "").strip()
    cycle_id = str(session.get("cycle_id") or "").strip()
    phases = _session_phases(session)
    observe = session.get("observe_philology") if isinstance(session.get("observe_philology"), dict) else {}
    selected_document_title = str(document_title or "").strip()
    selected_work_title = str(work_title or "").strip()
    selected_version_lineage_key = str(version_lineage_key or "").strip()
    selected_witness_key = str(witness_key or "").strip()
    observe_filter_contract = build_observe_philology_filter_contract(
        observe,
        {
            "document_title": selected_document_title,
            "work_title": selected_work_title,
            "version_lineage_key": selected_version_lineage_key,
            "witness_key": selected_witness_key,
        },
    )
    dashboard_payload = build_research_dashboard_payload(
        _build_session_dashboard_snapshot(session),
        philology_filters={
            "document_title": selected_document_title,
            "work_title": selected_work_title,
            "version_lineage_key": selected_version_lineage_key,
            "witness_key": selected_witness_key,
        },
    )
    evidence_board = dashboard_payload.get("evidence_board") if isinstance(dashboard_payload.get("evidence_board"), dict) else {}
    review_workbench = evidence_board.get("review_workbench") if isinstance(evidence_board.get("review_workbench"), dict) else {}
    observe = filter_observe_philology_assets(
        observe,
        {
            "document_title": selected_document_title,
            "work_title": selected_work_title,
            "version_lineage_key": selected_version_lineage_key,
            "witness_key": selected_witness_key,
        },
    )
    annotation_report = observe.get("annotation_report") if isinstance(observe.get("annotation_report"), dict) else {}
    summary = annotation_report.get("summary") if isinstance(annotation_report.get("summary"), dict) else {}
    catalog_summary = observe.get("catalog_summary") if isinstance(observe.get("catalog_summary"), dict) else {}
    catalog_metrics = catalog_summary.get("summary") if isinstance(catalog_summary.get("summary"), dict) else {}
    catalog_version_lineages = sorted(
        [dict(item) for item in catalog_summary.get("version_lineages") or [] if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("work_title") or ""),
            str(item.get("fragment_title") or ""),
            str(item.get("edition") or ""),
            str(item.get("version_lineage_key") or ""),
        ),
    )
    catalog_source_type_counts = {
        str(key): int(value)
        for key, value in (catalog_metrics.get("source_type_counts") or {}).items()
        if str(key).strip()
    }
    catalog_review_status_counts = {
        str(key): int(value)
        for key, value in (catalog_metrics.get("review_status_counts") or {}).items()
        if str(key).strip()
    }
    notes = summary.get("philology_notes") if isinstance(summary.get("philology_notes"), list) else []

    terminology_rows_all = sorted(
        [dict(item) for item in observe.get("terminology_standard_table") or [] if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("document_title") or item.get("document_urn") or ""),
            str(item.get("canonical") or ""),
        ),
    )
    collation_entries_all = sorted(
        [dict(item) for item in observe.get("collation_entries") or [] if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("document_title") or item.get("document_urn") or ""),
            str(item.get("witness_title") or item.get("witness_urn") or ""),
            str(item.get("base_text") or ""),
        ),
    )
    terminology_rows = terminology_rows_all
    collation_entries = collation_entries_all

    term_page = _paginate_items(terminology_rows, terminology_page, _PHILOLOGY_TERMINOLOGY_PAGE_SIZE)
    collation_page_data = _paginate_items(collation_entries, collation_page, _PHILOLOGY_COLLATION_PAGE_SIZE)

    status = _render_session_status_badge(str(session.get("status") or "pending").strip().lower())
    duration = float(session.get("duration") or 0.0)
    source = str(observe.get("source") or "unavailable").strip() or "unavailable"
    catalog_document_count = int(observe.get("catalog_document_count") or catalog_metrics.get("catalog_document_count") or 0)
    version_lineage_count = int(observe.get("version_lineage_count") or catalog_metrics.get("version_lineage_count") or len(catalog_version_lineages))
    witness_count = int(observe.get("witness_count") or catalog_metrics.get("witness_count") or 0)
    missing_catalog_metadata_count = int(
        observe.get("missing_catalog_metadata_count") or catalog_metrics.get("missing_core_metadata_count") or 0
    )
    document_count = max(int(summary.get("processed_document_count") or observe.get("document_count") or 0), catalog_document_count)
    terminology_count = int(observe.get("terminology_standard_table_count") or len(terminology_rows))
    collation_count = int(observe.get("collation_entry_count") or len(collation_entries))
    notes_html = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-amber-50 text-amber-700 text-xs">{_safe_html(note)}</span>'
        for note in notes[:8]
    ) or '<span class="text-xs text-gray-400">暂无文献学说明</span>'
    filter_chips_html = _render_catalog_filter_chips(
        cycle_id,
        filter_contract=observe_filter_contract,
        drawer=drawer,
    )
    workbench_section_html = _render_philology_review_workbench(
        cycle_id,
        review_workbench,
        _format_active_catalog_filter_summary(observe_filter_contract),
        terminology_page=term_page["page"],
        collation_page=collation_page_data["page"],
        drawer=drawer,
        document_title=selected_document_title,
        work_title=selected_work_title,
        version_lineage_key=selected_version_lineage_key,
        witness_key=selected_witness_key,
    )
    catalog_semantic_badges_html = "".join(
        badge
        for badge in (
            f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-blue-50 text-blue-700 text-xs">义项 {int(catalog_metrics.get("exegesis_entry_count") or 0)}</span>'
            if int(catalog_metrics.get("exegesis_entry_count") or 0) > 0
            else "",
            f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-indigo-50 text-indigo-700 text-xs">时代语义 {int(catalog_metrics.get("temporal_semantic_count") or 0)}</span>'
            if int(catalog_metrics.get("temporal_semantic_count") or 0) > 0
            else "",
            f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-amber-50 text-amber-700 text-xs">待核 {int(catalog_metrics.get("pending_review_count") or 0)}</span>'
            if int(catalog_metrics.get("pending_review_count") or 0) > 0
            else "",
        )
        if badge
    )
    catalog_review_badges_html = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-slate-100 text-slate-700 text-xs">{_safe_html(review_status)} x {count}</span>'
        for review_status, count in sorted(catalog_review_status_counts.items())
    )
    catalog_source_badges_html = "".join(
        f'<span class="inline-flex items-center px-2 py-1 rounded-full bg-slate-100 text-slate-700 text-xs">{_safe_html(source_type)} x {count}</span>'
        for source_type, count in sorted(catalog_source_type_counts.items())
    ) or '<span class="text-xs text-gray-400">暂无来源分布</span>'
    catalog_lineage_cards_html = ""
    for lineage in catalog_version_lineages[:6]:
        lineage_witness_count = int(lineage.get("witness_count") or len(lineage.get("witnesses") or []))
        lineage_temporal_semantics = lineage.get("temporal_semantics") if isinstance(lineage.get("temporal_semantics"), dict) else {}
        lineage_semantic_hint = str(lineage_temporal_semantics.get("semantic_hint") or "").strip()
        if not lineage_semantic_hint:
            lineage_semantic_hint = " · ".join(
                part
                for part in (
                    str(lineage.get("dynasty") or "").strip(),
                    str(lineage.get("author") or "").strip(),
                    str(lineage.get("edition") or "").strip(),
                )
                if part
            ) or "目录学元数据待补充"
        lineage_exegesis_preview = "、".join(
            str(entry.get("canonical") or "").strip()
            for entry in (lineage.get("exegesis_entries") or [])[:3]
            if isinstance(entry, dict) and str(entry.get("canonical") or "").strip()
        )
        lineage_meta = " · ".join(
            part
            for part in (
                str(lineage.get("dynasty") or "").strip(),
                str(lineage.get("author") or "").strip(),
                str(lineage.get("edition") or "").strip(),
            )
            if part
        ) or "目录学元数据待补充"
        catalog_lineage_cards_html += f"""
        <article class="rounded-xl border border-gray-100 bg-white p-4 shadow-sm space-y-2">
            <div class="flex flex-wrap items-start justify-between gap-2">
                <div>
                    <h5 class="text-sm font-semibold text-gray-800">{_safe_html(lineage.get("work_title") or '未标注作品')}</h5>
                    <p class="text-xs text-gray-500 mt-1">{_safe_html(lineage.get("fragment_title") or '未标注章节')}</p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                    <span class="inline-flex items-center px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs">见证 {lineage_witness_count}</span>
                    {_render_catalog_review_badge(str(lineage.get("review_status") or "pending"))}
                </div>
            </div>
            <p class="text-xs text-gray-500">{_safe_html(lineage_meta)}</p>
            <p class="text-xs text-gray-500">时代语义：{_safe_html(lineage_semantic_hint)}</p>
            <p class="text-xs text-gray-500">训诂义项：{_safe_html(lineage_exegesis_preview or '待补充')}</p>
            {_render_catalog_review_meta(lineage)}
            <p class="text-[11px] text-gray-400 break-all">{_safe_html(lineage.get("version_lineage_key") or lineage.get("work_fragment_key") or '未生成谱系键')}</p>
            {_render_catalog_review_actions(
                cycle_id,
                lineage,
                terminology_page=term_page["page"],
                collation_page=collation_page_data["page"],
                drawer=drawer,
                document_title=selected_document_title,
                work_title=selected_work_title,
                version_lineage_key=selected_version_lineage_key,
                witness_key=selected_witness_key,
            )}
        </article>
        """
    if not catalog_lineage_cards_html:
        catalog_lineage_cards_html = _empty_state("📚", "暂无目录学谱系", "当前会话尚未汇总可复用的版本谱系。")
    catalog_section_html = ""
    if catalog_summary or catalog_document_count or version_lineage_count or witness_count:
        catalog_section_html = f"""
        <section class="rounded-2xl border border-slate-100 bg-slate-50/70 p-4 space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h4 class="text-base font-semibold text-gray-800">目录学基线</h4>
                    <p class="text-sm text-gray-400 mt-1">汇总作品-章节-版本谱系-见证，作为后续训诂、辑佚、考据的公共底座</p>
                </div>
                <span class="text-xs text-gray-500">缺失核心字段 {missing_catalog_metadata_count}</span>
            </div>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-2 text-center">
                <div class="rounded-xl bg-white border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">目录文献</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{catalog_document_count}</p>
                </div>
                <div class="rounded-xl bg-white border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">版本谱系</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{version_lineage_count}</p>
                </div>
                <div class="rounded-xl bg-white border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">版本见证</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{witness_count}</p>
                </div>
                <div class="rounded-xl bg-white border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">作品数</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{int(catalog_metrics.get('work_count') or 0)}</p>
                </div>
            </div>
            <div class="flex flex-wrap gap-2">{catalog_source_badges_html}</div>
            <div class="flex flex-wrap gap-2">{catalog_semantic_badges_html}{catalog_review_badges_html}</div>
            {_render_exegesis_summary_card(catalog_metrics)}
            {_render_fragment_summary_card(catalog_metrics)}
            {_render_evidence_chain_summary_card(catalog_metrics)}
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">{catalog_lineage_cards_html}</div>
        </section>
        """

    terminology_rows_html = ""
    status_labels = {"standardized": "已规范化", "configured": "仅配置", "recognized": "已识别"}
    for row in term_page["items"]:
        terminology_rows_html += f"""
        <tr class="border-b border-gray-100 last:border-0 align-top">
            <td class="px-3 py-3 text-sm text-gray-700 min-w-[140px]">
                <div class="font-medium text-gray-800">{_safe_html(row.get("document_title") or "—")}</div>
                <div class="text-[11px] text-gray-400 mt-1 break-all">{_safe_html(row.get("document_urn") or row.get("source_type") or "")}</div>
            </td>
            <td class="px-3 py-3 text-sm text-gray-800 min-w-[120px]">{_safe_html(row.get("canonical") or "—")}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[96px]">{_safe_html(row.get("label") or row.get("category") or "—")}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[88px]">{_safe_html(status_labels.get(str(row.get("status") or "").strip().lower(), row.get("status") or "—"))}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[180px]">{_safe_join(row.get("observed_forms"))}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[160px]">{_safe_join(row.get("configured_variants"))}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[140px]">{_safe_join(row.get("sources"))}</td>
            <td class="px-3 py-3 text-sm text-gray-600 min-w-[220px]">{_safe_join(row.get("notes"))}</td>
        </tr>
        """

    if not terminology_rows_html:
        terminology_rows_html = (
            '<tr><td colspan="8" class="px-3 py-8 text-center text-sm text-gray-400">'
            f'{_safe_html(selected_document_title or "全部文献")} 下暂无术语标准表记录</td></tr>'
        )

    difference_labels = {"replace": "异文替换", "insert": "疑似衍文", "delete": "疑似脱文"}
    severity_classes = {
        "info": "bg-slate-50 text-slate-600",
        "warning": "bg-amber-50 text-amber-700",
        "high": "bg-red-50 text-red-600",
    }
    collation_cards_html = ""
    for entry in collation_page_data["items"]:
        severity = str(entry.get("severity") or "info").strip().lower() or "info"
        severity_class = severity_classes.get(severity, "bg-slate-50 text-slate-600")
        judgement = str(entry.get("judgement") or difference_labels.get(str(entry.get("difference_type") or ""), "异文")).strip()
        difference_label = difference_labels.get(str(entry.get("difference_type") or "").strip(), str(entry.get("difference_type") or "异文").strip() or "异文")
        canonical_reading = str(entry.get("canonical_reading") or "").strip()
        matched_rule = str(entry.get("matched_rule") or "").strip()
        base_fragment_url = _project_fragment_url(
            cycle_id,
            document_urn=str(entry.get("document_urn") or "").strip(),
            document_title=str(entry.get("document_title") or "").strip(),
            highlight=str(entry.get("base_text") or "").strip(),
            context=str(entry.get("base_context") or "").strip(),
            role="base",
        )
        witness_fragment_url = _project_fragment_url(
            cycle_id,
            document_urn=str(entry.get("witness_urn") or entry.get("document_urn") or "").strip(),
            document_title=str(entry.get("witness_title") or entry.get("document_title") or "").strip(),
            highlight=str(entry.get("witness_text") or "").strip(),
            context=str(entry.get("witness_context") or "").strip(),
            role="witness",
        )
        collation_cards_html += f"""
        <article class="rounded-xl border border-gray-100 bg-white p-4 shadow-sm space-y-3">
            <div class="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                <div>
                    <h4 class="text-sm font-semibold text-gray-800">{_safe_html(entry.get("document_title") or entry.get("document_urn") or "未标注文献")}</h4>
                    <p class="text-xs text-gray-400 mt-1">对校版本：{_safe_html(entry.get("witness_title") or entry.get("witness_urn") or "平行版本")}</p>
                </div>
                <div class="flex flex-wrap items-center gap-2 text-xs">
                    <span class="inline-flex items-center px-2 py-1 rounded-full bg-blue-50 text-blue-700">{_safe_html(difference_label)}</span>
                    <span class="inline-flex items-center px-2 py-1 rounded-full {severity_class}">{_safe_html(judgement)}</span>
                </div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <div class="rounded-lg bg-rose-50 border border-rose-100 p-3">
                    <p class="text-[11px] font-semibold text-rose-600 uppercase tracking-wide">Base</p>
                    <p class="text-sm font-medium text-gray-800 mt-1 break-all">{_safe_html(entry.get("base_text") or "—")}</p>
                    <p class="text-xs text-gray-500 mt-2 leading-5">{_safe_html(entry.get("base_context") or "无上下文")}</p>
                    <button type="button" class="mt-3 inline-flex items-center px-2.5 py-1 rounded-lg border border-rose-200 text-xs text-rose-700 hover:bg-rose-100 transition" onclick="openDocumentFragmentModal()" hx-get="{_safe_html(base_fragment_url)}" hx-target="#document-fragment-modal-content" hx-swap="outerHTML">跳到原始片段</button>
                </div>
                <div class="rounded-lg bg-emerald-50 border border-emerald-100 p-3">
                    <p class="text-[11px] font-semibold text-emerald-600 uppercase tracking-wide">Witness</p>
                    <p class="text-sm font-medium text-gray-800 mt-1 break-all">{_safe_html(entry.get("witness_text") or "—")}</p>
                    <p class="text-xs text-gray-500 mt-2 leading-5">{_safe_html(entry.get("witness_context") or "无上下文")}</p>
                    <button type="button" class="mt-3 inline-flex items-center px-2.5 py-1 rounded-lg border border-emerald-200 text-xs text-emerald-700 hover:bg-emerald-100 transition" onclick="openDocumentFragmentModal()" hx-get="{_safe_html(witness_fragment_url)}" hx-target="#document-fragment-modal-content" hx-swap="outerHTML">跳到原始片段</button>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-gray-500">
                <p>选择策略：<span class="text-gray-700">{_safe_html(entry.get("selection_strategy") or "—")}</span></p>
                <p>来源：<span class="text-gray-700">{_safe_html(entry.get("source") or "—")}</span></p>
                <p>规范读法：<span class="text-gray-700">{_safe_html(canonical_reading or "—")}</span></p>
                <p>匹配规则：<span class="text-gray-700">{_safe_html(matched_rule or "—")}</span></p>
            </div>
            <div class="rounded-lg bg-gray-50 p-3 text-sm text-gray-600 leading-6">{_safe_html(entry.get("note") or "暂无校勘说明")}</div>
        </article>
        """

    if not collation_cards_html:
        collation_cards_html = _empty_state("🧾", "暂无校勘条目", f"{selected_document_title or '全部文献'} 下尚未输出可复用的版本对勘条目。")

    detail_body = f"""
    <div class="p-5 space-y-6">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">{status}</div>
                <h3 class="text-xl font-semibold text-gray-900 mt-3 break-words">{_safe_html(title)}</h3>
                <p class="text-sm text-gray-500 mt-2 leading-6">{_safe_html(objective or '暂无研究目标说明')}</p>
                <div class="mt-3 flex flex-wrap gap-1.5">{_render_phase_tags(phases)}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 min-w-[220px] text-center">
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">文献</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{document_count}</p>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">术语</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{terminology_count}</p>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">校勘</p>
                    <p class="text-lg font-semibold text-gray-800 mt-1">{collation_count}</p>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3">
                    <p class="text-[11px] uppercase tracking-wide text-gray-400">来源</p>
                    <p class="text-sm font-semibold text-gray-800 mt-1 break-all">{_safe_html(source)}</p>
                </div>
            </div>
        </div>

        <div class="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <h4 class="text-sm font-semibold text-amber-900">Observe 文献学摘要</h4>
                <span class="text-xs text-amber-700">cycle: {_safe_html(cycle_id or '—')} · 用时 {duration:.1f}s</span>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">{notes_html}</div>
        </div>

        {catalog_section_html}

        {filter_chips_html}

        {workbench_section_html}

        <section class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h4 class="text-base font-semibold text-gray-800">术语标准表</h4>
                    <p class="text-sm text-gray-400 mt-1">分页查看规范术语、观测写法、来源与注记</p>
                </div>
                <span class="text-xs text-gray-500">每页 {_PHILOLOGY_TERMINOLOGY_PAGE_SIZE} 条</span>
            </div>
            <div class="mt-4 overflow-x-auto rounded-xl border border-gray-100 bg-white">
                <table class="min-w-full divide-y divide-gray-100">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">文献</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">规范术语</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">类别</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">状态</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">观测写法</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">配置异写</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">来源</th>
                            <th class="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">注记</th>
                        </tr>
                    </thead>
                    <tbody>{terminology_rows_html}</tbody>
                </table>
            </div>
            {_render_detail_pagination(
                cycle_id,
                section="terminology",
                page=term_page["page"],
                total_pages=term_page["total_pages"],
                total_count=term_page["total_count"],
                terminology_page=term_page["page"],
                collation_page=collation_page_data["page"],
                drawer=drawer,
                document_title=selected_document_title,
                work_title=selected_work_title,
                version_lineage_key=selected_version_lineage_key,
                witness_key=selected_witness_key,
            )}
        </section>

        <section class="rounded-2xl border border-gray-100 bg-gray-50/60 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h4 class="text-base font-semibold text-gray-800">校勘条目明细</h4>
                    <p class="text-sm text-gray-400 mt-1">分页查看 base / witness 异文、上下文、判断与校勘说明</p>
                </div>
                <span class="text-xs text-gray-500">每页 {_PHILOLOGY_COLLATION_PAGE_SIZE} 条</span>
            </div>
            <div class="mt-4 space-y-3">{collation_cards_html}</div>
            {_render_detail_pagination(
                cycle_id,
                section="collation",
                page=collation_page_data["page"],
                total_pages=collation_page_data["total_pages"],
                total_count=collation_page_data["total_count"],
                terminology_page=term_page["page"],
                collation_page=collation_page_data["page"],
                drawer=drawer,
                document_title=selected_document_title,
                work_title=selected_work_title,
                version_lineage_key=selected_version_lineage_key,
                witness_key=selected_witness_key,
            )}
        </section>
    </div>
    """

    return f"""
    <div id="{panel_id}" class="{panel_class}">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-3">
            <div>
                <h3 class="text-base font-semibold text-gray-800">研究任务详情</h3>
                <p class="text-sm text-gray-400 mt-1">聚合展示 Observe 阶段术语标准表、校勘条目与文献学校核工作台</p>
            </div>
            {close_button}
        </div>
        {notice_banner}
        {detail_body}
    </div>
    """


# ---------------------------------------------------------------------------
# Helpers – research output scanning
# ---------------------------------------------------------------------------


def _scan_research_sessions(request: Request | None = None) -> List[Dict[str, Any]]:
    """优先从结构化存储读取研究会话，失败时回退扫描 output/ 导出文件。"""
    if request is not None:
        try:
            summaries = list_research_sessions(request.app)
            if summaries:
                results: List[Dict[str, Any]] = []
                for item in summaries[:50]:
                    cycle_id = str(item.get("cycle_id") or "").strip()
                    session = get_research_session(request.app, cycle_id) if cycle_id else None
                    source = session if isinstance(session, dict) else item
                    if isinstance(source, dict):
                        results.append(_build_session_summary(source))
                results.sort(key=lambda item: item["mtime"], reverse=True)
                return results
        except Exception as exc:
            logger.warning("dashboard structured session read failed, falling back to output scan: %s", exc)

    files = sorted(
        glob.glob(str(_OUTPUT_DIR / "research_session_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    results: List[Dict[str, Any]] = []
    for fp in files[:50]:  # 最多取最近 50 条
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
            results.append({
                "file": os.path.basename(fp),
                "title": d.get("title", "")[:80] or d.get("question", "")[:80] or "无标题",
                "question": d.get("question") or d.get("research_question") or "",
                "status": d.get("status", "unknown"),
                "cycle_id": d.get("cycle_id", ""),
                "phases": d.get("executed_phases") or [],
                "has_reports": bool(d.get("reports") or d.get("report_outputs")),
                "mtime": os.path.getmtime(fp),
            })
        except Exception:
            continue
    return results


def _count_imrd_reports() -> Dict[str, int]:
    """统计 output/ 下的 IMRD 报告文件数。"""
    md = len(glob.glob(str(_OUTPUT_DIR / "cycle_*_imrd_report.md")))
    docx = len(glob.glob(str(_OUTPUT_DIR / "cycle_*_imrd_report.docx")))
    return {"md": md, "docx": docx, "total": md + docx}


# ---------------------------------------------------------------------------
# Dashboard: Stats  – 系统全景仪表盘
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/stats", response_class=HTMLResponse)
async def dashboard_stats(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    corpus = _count_corpus_files()
    outputs = _count_output_files()
    imrd = _count_imrd_reports()
    sessions = _scan_research_sessions(request)

    # 知识实体 (ORM)
    orm_entities = 0
    orm_relations = 0
    orm_documents = 0
    db_mgr = getattr(getattr(request, "app", None), "state", None)
    db_mgr = getattr(db_mgr, "db_manager", None) if db_mgr else None
    if db_mgr is not None:
        try:
            from sqlalchemy import func as sa_func

            from src.infrastructure.persistence import (
                Document,
                Entity,
                EntityRelationship,
            )
            with db_mgr.session_scope() as sess:
                orm_entities = sess.query(sa_func.count(Entity.id)).scalar() or 0
                orm_relations = sess.query(sa_func.count(EntityRelationship.id)).scalar() or 0
                orm_documents = sess.query(sa_func.count(Document.id)).scalar() or 0
        except Exception:
            pass

    # 研究会话统计
    total_sessions = len(sessions)

    # KG 统计
    kg_entities = 0
    kg_relations = 0
    try:
        from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph
        kg = TCMKnowledgeGraph()
        kg_entities = kg.entity_count
        kg_relations = kg.relation_count
    except Exception:
        pass

    html = f"""
    <!-- 第一行: 核心指标 -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {_card("📚 古籍文献", str(corpus), "gray-800")}
        {_card("🔬 研究任务", str(total_sessions), "blue-600")}
        {_card("📝 已生成论文", str(imrd["total"]), "purple-600")}
        {_card("✅ 系统状态", "运行中", "emerald-600")}
    </div>
    <!-- 第二行: 知识沉淀指标 -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {_card("🧬 知识实体 (ORM)", f"{orm_entities:,}", "indigo-600")}
        {_card("🔗 知识关系 (ORM)", f"{orm_relations:,}", "teal-600")}
        {_card("🕸️ KG 节点", f"{kg_entities:,}", "emerald-700")}
        {_card("📎 KG 关系", f"{kg_relations:,}", "cyan-600")}
    </div>
    <!-- 第三行: 产出概览 -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {_card("📃 IMRD 报告 (MD)", str(imrd["md"]), "orange-600")}
        {_card("📄 IMRD 报告 (DOCX)", str(imrd["docx"]), "orange-600")}
        {_card("📊 分析文档", str(orm_documents), "gray-700")}
        {_card("📦 全部输出", str(outputs), "gray-700")}
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Dashboard: Quality
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/quality", response_class=HTMLResponse)
async def dashboard_quality(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    # 从 ORM 获取真实质量指标
    orm_entities = 0
    orm_relations = 0
    db_mgr = getattr(getattr(request, "app", None), "state", None)
    db_mgr = getattr(db_mgr, "db_manager", None) if db_mgr else None
    if db_mgr is not None:
        try:
            from sqlalchemy import func as sa_func

            from src.infrastructure.persistence import (
                Entity,
                EntityRelationship,
            )
            with db_mgr.session_scope() as sess:
                orm_entities = sess.query(sa_func.count(Entity.id)).scalar() or 0
                orm_relations = sess.query(sa_func.count(EntityRelationship.id)).scalar() or 0
        except Exception:
            pass

    # 根据实际数据计算质量分
    corpus = _count_corpus_files()
    sessions = _scan_research_sessions(request)
    completed_sessions = sum(1 for s in sessions if s["status"] == "completed")
    imrd = _count_imrd_reports()

    # 综合评分 (简易加权)
    corpus_score = min(1.0, corpus / 50) if corpus else 0
    entity_score = min(1.0, orm_entities / 500) if orm_entities else 0
    rel_score = min(1.0, orm_relations / 200) if orm_relations else 0
    paper_score = min(1.0, imrd["total"] / 20) if imrd["total"] else 0
    session_score = min(1.0, completed_sessions / 10) if completed_sessions else 0
    overall = int((corpus_score * 20 + entity_score * 25 + rel_score * 20 + paper_score * 20 + session_score * 15))

    # 知识覆盖度
    coverage = f"{entity_score:.0%}"
    # 关系密度
    density = f"{rel_score:.0%}"
    # 论文产出率
    paper_rate = f"{paper_score:.0%}"

    html = f"""
    <div class="px-5 py-4 border-b border-gray-100">
        <h2 class="font-semibold text-gray-800">质量评分概览</h2>
    </div>
    <div class="px-5 py-6">
        <div class="flex items-center gap-6">
            <div class="w-20 h-20 rounded-full border-4 {'border-emerald-500' if overall >= 60 else 'border-amber-500' if overall >= 30 else 'border-red-400'}
                        flex items-center justify-center">
                <span class="text-xl font-bold {'text-emerald-700' if overall >= 60 else 'text-amber-700' if overall >= 30 else 'text-red-600'}">{overall}</span>
            </div>
            <div class="text-sm text-gray-500 space-y-1.5 flex-1">
                <p>知识实体覆盖 <span class="text-gray-700 font-medium">{orm_entities:,}</span>
                   <span class="text-xs ml-1 text-emerald-600">({coverage})</span></p>
                <p>知识关系密度 <span class="text-gray-700 font-medium">{orm_relations:,}</span>
                   <span class="text-xs ml-1 text-teal-600">({density})</span></p>
                <p>论文产出 <span class="text-gray-700 font-medium">{imrd["total"]}</span> 份
                   <span class="text-xs ml-1 text-purple-600">({paper_rate})</span></p>
                <p>研究任务完成 <span class="text-gray-700 font-medium">{completed_sessions}</span> / {len(sessions)}</p>
            </div>
        </div>
        <p class="text-xs text-gray-400 mt-4">
            动态评估 · 基于知识实体、关系、论文产出、任务完成度综合加权
        </p>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Dashboard: Smoke Test Health — real_observe_smoke 即时摘要
# ---------------------------------------------------------------------------

_SMOKE_LATEST = _OUTPUT_DIR / "real_observe_smoke" / "latest.json"


def _load_smoke_latest() -> Dict[str, Any] | None:
    """Load the latest real_observe_smoke result; return *None* if absent."""
    try:
        if _SMOKE_LATEST.is_file():
            with open(_SMOKE_LATEST, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _smoke_metric(label: str, value: str, ok: bool) -> str:
    color = "emerald" if ok else "red"
    icon = "✓" if ok else "✗"
    return (
        f'<div class="flex justify-between items-center py-1">'
        f'<span class="text-sm text-gray-500">{label}</span>'
        f'<span class="text-sm font-medium text-{color}-600">{icon} {value}</span>'
        f'</div>'
    )


@router.get("/api/dashboard/smoke-health", response_class=HTMLResponse)
async def dashboard_smoke_health(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    data = _load_smoke_latest()
    if data is None:
        html = _empty_state("🔬", "暂无 Smoke 测试数据", "运行质量门后自动生成")
        return HTMLResponse(html)

    status = data.get("validation_status", "unknown")
    passed = status == "passed"
    violations = data.get("violations") or []
    p_val = data.get("p_value")
    es = data.get("effect_size")
    docs = data.get("processed_document_count", 0)
    records = data.get("record_count", 0)
    kg = data.get("kg_path_count", 0)
    assoc = data.get("association_rule_count", 0)
    freq = data.get("frequency_signal_count", 0)
    primary = data.get("primary_association") or {}

    # status badge
    badge_color = "emerald" if passed else "red"
    badge_text = "PASSED" if passed else "FAILED"

    # primary association summary
    primary_html = ""
    if primary:
        herb = primary.get("herb", "—")
        synd = primary.get("syndrome", "—")
        primary_html = (
            f'<div class="mt-3 p-3 bg-indigo-50 rounded-lg text-sm">'
            f'<p class="text-indigo-700 font-medium mb-1">🏷️ 主关联</p>'
            f'<p class="text-indigo-600">{herb} → {synd}'
            f' <span class="text-xs text-indigo-400">(χ²={primary.get("chi2", 0):.2f}, p={primary.get("p_value", 0):.4f})</span></p>'
            f'</div>'
        )

    # violation list
    violation_html = ""
    if violations:
        items = "".join(f'<li class="text-red-600 text-xs">{v}</li>' for v in violations[:5])
        violation_html = (
            f'<div class="mt-3 p-3 bg-red-50 rounded-lg">'
            f'<p class="text-red-700 font-medium text-sm mb-1">⚠ 违规项 ({len(violations)})</p>'
            f'<ul class="list-disc list-inside space-y-0.5">{items}</ul>'
            f'</div>'
        )

    html = f"""
    <div class="flex items-center justify-between mb-3">
        <span class="px-2.5 py-1 rounded-full text-xs font-bold bg-{badge_color}-100 text-{badge_color}-700">{badge_text}</span>
        <span class="text-xs text-gray-400">{data.get("generated_at", "")[:19]}</span>
    </div>
    <div class="space-y-0.5">
        {_smoke_metric("文档处理", str(docs), docs > 0)}
        {_smoke_metric("分析记录", str(records), records > 0)}
        {_smoke_metric("p 值", f"{p_val:.4f}" if p_val is not None else "—", p_val is not None and p_val < 0.05)}
        {_smoke_metric("效应量", f"{es:.4f}" if es is not None else "—", es is not None and es >= 0.3)}
        {_smoke_metric("KG 路径", str(kg), kg > 0)}
        {_smoke_metric("关联规则", str(assoc), assoc > 0)}
        {_smoke_metric("频次信号", str(freq), freq > 0)}
    </div>
    {primary_html}
    {violation_html}
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Dashboard: Research Workflow — 科研论文书写流程
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/research-workflow", response_class=HTMLResponse)
async def dashboard_research_workflow(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    """科研论文生成管线流程可视化面板。"""
    sessions = _scan_research_sessions(request)
    imrd = _count_imrd_reports()
    total = len(sessions)
    completed = sum(1 for s in sessions if s["status"] == "completed")
    with_papers = sum(1 for s in sessions if s["has_reports"])

    # 统计各阶段被执行的次数
    phase_counts: Dict[str, int] = {}
    for s in sessions:
        for p in s["phases"]:
            phase_counts[p] = phase_counts.get(p, 0) + 1

    PHASES = [
        ("observe", "📖 文献观察", "采集古籍语料，预处理规范化", "emerald"),
        ("hypothesis", "💡 假设生成", "基于知识图谱生成研究假设", "blue"),
        ("experiment", "🧪 实验方案", "研究协议设计、验证计划生成", "purple"),
        ("experiment_execution", "📥 结果导入", "外部实验执行结果接收与导入", "indigo"),
        ("analyze", "📊 数据分析", "语义建模、统计分析、可视化", "orange"),
        ("publish", "📝 论文生成", "IMRD 格式论文、引文格式化", "red"),
        ("reflect", "🔍 反思总结", "质量评审、研究空白分析", "gray"),
    ]

    # 流程图阶段卡片
    flow_cards = ""
    for i, (phase_id, label, desc, color) in enumerate(PHASES):
        cnt = phase_counts.get(phase_id, 0)
        active = cnt > 0
        opacity = "" if active else "opacity-50"
        ring = f"ring-2 ring-{color}-400" if active else ""
        badge = f'<span class="text-[10px] font-bold text-{color}-600 bg-{color}-50 px-1.5 py-0.5 rounded-full">{cnt}</span>' if cnt else '<span class="text-[10px] text-gray-300">0</span>'
        arrow = f'<div class="hidden md:flex items-center text-gray-300 text-lg px-1">→</div>' if i < len(PHASES) - 1 else ""
        flow_cards += f"""
        <div class="flex items-center">
            <div class="bg-white rounded-lg border border-gray-100 p-3 text-center min-w-[110px] {opacity} {ring} hover:shadow-md transition">
                <p class="text-lg mb-1">{label.split()[0]}</p>
                <p class="text-xs font-semibold text-gray-700">{label.split(maxsplit=1)[1] if ' ' in label else label}</p>
                <p class="text-[10px] text-gray-400 mt-0.5 leading-tight">{desc}</p>
                <div class="mt-1.5">{badge}</div>
            </div>
            {arrow}
        </div>"""

    # 最近产出的论文
    recent_papers = ""
    imrd_files = sorted(
        glob.glob(str(_OUTPUT_DIR / "cycle_*_imrd_report.md")),
        key=os.path.getmtime,
        reverse=True,
    )[:5]
    for fp in imrd_files:
        fname = os.path.basename(fp)
        try:
            with open(fp, encoding="utf-8") as f:
                first_line = f.readline().strip().lstrip("# ").strip()[:60] or fname
        except Exception:
            first_line = fname
        recent_papers += f"""
        <div class="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0">
            <span class="text-lg">📄</span>
            <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-700 truncate">{first_line}</p>
                <p class="text-[10px] text-gray-400">{fname}</p>
            </div>
        </div>"""

    if not recent_papers:
        recent_papers = '<p class="text-sm text-gray-400 text-center py-3">暂无生成的论文</p>'

    html = f"""
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <div class="flex items-center justify-between mb-4">
            <h2 class="font-semibold text-gray-800">🔬 科研论文书写流程</h2>
            <div class="flex gap-3 text-xs text-gray-500">
                <span>任务 <strong class="text-blue-600">{total}</strong></span>
                <span>完成 <strong class="text-emerald-600">{completed}</strong></span>
                <span>论文 <strong class="text-purple-600">{imrd['total']}</strong></span>
            </div>
        </div>

        <!-- 六阶段流水线 -->
        <div class="flex flex-wrap md:flex-nowrap items-start justify-center gap-1 mb-5 overflow-x-auto pb-2">
            {flow_cards}
        </div>

        <!-- 下方: 最近论文 + 统计 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <h3 class="text-sm font-semibold text-gray-600 mb-2">📝 最近生成论文</h3>
                {recent_papers}
            </div>
            <div>
                <h3 class="text-sm font-semibold text-gray-600 mb-2">📈 流程统计</h3>
                <div class="space-y-2 text-sm">
                    <div class="flex justify-between"><span class="text-gray-500">总研究任务</span><span class="font-medium text-gray-800">{total}</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">已完成任务</span><span class="font-medium text-emerald-600">{completed}</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">已生成论文</span><span class="font-medium text-purple-600">{with_papers}</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">IMRD 报告 (MD)</span><span class="font-medium">{imrd['md']}</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">IMRD 报告 (DOCX)</span><span class="font-medium">{imrd['docx']}</span></div>
                </div>
            </div>
        </div>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/api/projects/recent", response_class=HTMLResponse)
async def projects_recent(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    sessions = _scan_research_sessions(request)[:8]  # 最近 8 条
    if not sessions:
        return HTMLResponse(
            '<div class="px-5 py-8 text-center text-sm text-gray-400">'
            '暂无研究记录 — 可通过 POST /api/research/run 直接运行，或 POST /api/research/jobs 创建异步任务</div>'
        )

    _STATUS_MAP = {
        "completed": ("✅", "已完成", "text-emerald-600"),
        "active": ("🔄", "进行中", "text-blue-600"),
        "running": ("🔄", "运行中", "text-blue-600"),
        "failed": ("❌", "失败", "text-red-500"),
        "pending": ("⏳", "待执行", "text-amber-500"),
    }
    rows = ""
    for s in sessions:
        icon, label, cls = _STATUS_MAP.get(s["status"], ("❓", s["status"], "text-gray-500"))
        phases_tags = " ".join(
            f'<span class="inline-block px-1.5 py-0.5 text-[10px] font-medium rounded '
            f'bg-emerald-50 text-emerald-700">{p}</span>'
            for p in s["phases"]
        ) or '<span class="text-xs text-gray-300">—</span>'
        title = s["title"][:60]
        paper_badge = ' <span class="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded">📝 论文</span>' if s["has_reports"] else ""
        detail_button = ""
        if s["cycle_id"]:
            detail_url = _project_detail_url(s["cycle_id"], drawer=True)
            detail_button = (
                f'<button type="button" class="inline-flex items-center px-2.5 py-1 rounded-lg border border-gray-200 '
                f'text-xs text-gray-500 hover:text-gray-800 hover:border-gray-300 transition" '
                f'onclick="openSessionDetailDrawer()" hx-get="{_safe_html(detail_url)}" '
                f'hx-target="#session-detail-drawer-content" hx-swap="outerHTML">查看详情</button>'
            )
        rows += f"""
        <div class="px-5 py-3 hover:bg-gray-50 transition">
            <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-800 truncate">{title}{paper_badge}</p>
                    <div class="mt-1 flex flex-wrap gap-1">{phases_tags}</div>
                    <p class="mt-1 text-[10px] text-gray-400 truncate">cycle: {_safe_html(s['cycle_id'][:40]) or '—'}</p>
                </div>
                <div class="flex flex-col items-end gap-2">
                    <span class="text-xs {cls} whitespace-nowrap">{icon} {label}</span>
                    {detail_button}
                </div>
            </div>
        </div>"""

    return HTMLResponse(rows)


@router.get("/api/projects", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    sessions = _scan_research_sessions(request)
    imrd = _count_imrd_reports()
    total = len(sessions)
    completed = sum(1 for s in sessions if s["status"] == "completed")

    status_map = {
        "completed": ("✅", "已完成", "bg-emerald-50 text-emerald-700"),
        "active": ("🔄", "进行中", "bg-blue-50 text-blue-700"),
        "running": ("🔄", "运行中", "bg-blue-50 text-blue-700"),
        "failed": ("❌", "失败", "bg-red-50 text-red-600"),
        "pending": ("⏳", "待执行", "bg-amber-50 text-amber-700"),
    }

    initial_session: Dict[str, Any] | None = None
    if sessions:
        initial_cycle_id = str(sessions[0].get("cycle_id") or "").strip()
        if initial_cycle_id:
            try:
                initial_session = get_research_session(request.app, initial_cycle_id)
            except Exception:
                logger.exception("dashboard project detail preload failed: %s", initial_cycle_id)

    project_cards = ""
    for s in sessions:
        icon, label, cls = status_map.get(s["status"], ("❓", s["status"], "bg-gray-50 text-gray-500"))
        phases_html = " ".join(
            f'<span class="inline-block px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-100 text-gray-600">{p}</span>'
            for p in s["phases"]
        ) or '<span class="text-xs text-gray-300">无阶段</span>'
        paper_badge = '<span class="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded ml-1">📝 论文</span>' if s["has_reports"] else ""
        title = s["title"][:70]
        question = str(s.get("question") or "").strip()
        detail_button = ""
        if s["cycle_id"]:
            detail_button = (
                f'<button type="button" class="inline-flex items-center px-3 py-1.5 rounded-lg border border-gray-200 '
                f'text-sm text-gray-600 hover:text-gray-900 hover:border-gray-300 hover:bg-gray-50 transition" '
                f'hx-get="{_safe_html(_project_detail_url(s["cycle_id"]))}" '
                f'hx-target="#project-detail-panel" hx-swap="outerHTML">查看详情</button>'
            )
        project_cards += f"""
        <article class="bg-white rounded-2xl border border-gray-100 p-4 hover:shadow-md transition">
            <div class="flex items-start justify-between gap-3 mb-2">
                <div class="min-w-0 flex-1">
                    <h3 class="text-sm font-semibold text-gray-800 truncate">{title}{paper_badge}</h3>
                    <p class="text-xs text-gray-500 mt-1 line-clamp-2">{_safe_html(question or '暂无问题摘要')}</p>
                </div>
                <span class="text-[10px] font-medium px-2 py-0.5 rounded-full {cls} whitespace-nowrap">{icon} {label}</span>
            </div>
            <div class="flex flex-wrap gap-1 mb-3">{phases_html}</div>
            <div class="flex items-center justify-between gap-3">
                <p class="text-[10px] text-gray-400 truncate">cycle: {_safe_html(s['cycle_id'][:40]) or '—'}</p>
                {detail_button}
            </div>
        </article>"""

    if not project_cards:
        project_cards = _empty_state(
            "🔬",
            "暂无研究任务",
            "使用 AI 助手，或 POST /api/research/run 直接运行研究；如需异步跟踪，请 POST /api/research/jobs",
        )

    detail_panel = _render_session_detail_panel(initial_session)

    html = f"""
    {_section_header("研究任务", f"共 {total} 个研究任务 · 已完成 {completed} · 论文产出 {imrd['total']} 份")}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {_card("🔬 研究任务", str(total), "blue-600")}
        {_card("✅ 已完成", str(completed), "emerald-600")}
        {_card("📝 论文输出", str(imrd["total"]), "purple-600")}
    </div>
    <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-4 items-start">
        <div class="space-y-4">{project_cards}</div>
        {detail_panel}
    </div>
    """
    return HTMLResponse(html)


@router.get("/api/projects/{cycle_id}/detail", response_class=HTMLResponse)
async def project_detail_panel(
    request: Request,
    cycle_id: str,
    terminology_page: int = 1,
    collation_page: int = 1,
    document_title: str = "",
    work_title: str = "",
    version_lineage_key: str = "",
    witness_key: str = "",
    drawer: int = 0,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    try:
        session = get_research_session(request.app, cycle_id)
    except Exception as exc:
        logger.exception("dashboard project detail load failed: %s", cycle_id)
        return HTMLResponse(
            _render_session_detail_panel(
                None,
                terminology_page=terminology_page,
                collation_page=collation_page,
                drawer=bool(drawer),
                document_title=document_title,
                work_title=work_title,
                version_lineage_key=version_lineage_key,
                witness_key=witness_key,
                error_message=f"加载研究任务详情失败: {exc}",
            )
        )

    return HTMLResponse(
        _render_session_detail_panel(
            session,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=bool(drawer),
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
            error_message=f"未找到研究任务: {cycle_id}",
        )
    )


@router.post("/api/projects/{cycle_id}/catalog-review", response_class=HTMLResponse)
async def update_project_catalog_review(
    request: Request,
    cycle_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    form_payload = _parse_urlencoded_body(await request.body())
    scope = str(form_payload.get("scope") or "version_lineage").strip() or "version_lineage"
    target_version_lineage_key = str(form_payload.get("target_version_lineage_key") or "").strip()
    review_status = str(form_payload.get("review_status") or "pending").strip() or "pending"
    terminology_page = _normalize_page(form_payload.get("terminology_page"), 1)
    collation_page = _normalize_page(form_payload.get("collation_page"), 1)
    document_title = str(form_payload.get("document_title") or "").strip()
    work_title = str(form_payload.get("work_title") or "").strip()
    version_lineage_key = str(form_payload.get("version_lineage_key") or "").strip()
    witness_key = str(form_payload.get("witness_key") or "").strip()
    decision_basis = str(form_payload.get("decision_basis") or "").strip()
    drawer = 1 if str(form_payload.get("drawer") or "0").strip() in {"1", "true", "True"} else 0

    try:
        updated_session = apply_catalog_review(
            request.app,
            cycle_id,
            {
                "scope": scope,
                "version_lineage_key": str(target_version_lineage_key or "").strip(),
                "review_status": review_status,
                "reviewer": _resolve_dashboard_reviewer(user),
                "decision_basis": decision_basis or "目录学工作台快速审核",
            },
        )
        if updated_session is None:
            raise ValueError("Observe 阶段未持久化或研究任务不存在，无法写回目录学 review")
        session = updated_session
        error_message = ""
    except Exception as exc:
        logger.exception("dashboard catalog review writeback failed: %s", cycle_id)
        try:
            session = get_research_session(request.app, cycle_id)
        except Exception:
            session = None
        error_message = f"目录学 review 写回失败: {exc}"

    return HTMLResponse(
        _render_session_detail_panel(
            session,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=bool(drawer),
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
            error_message=error_message,
        )
    )


@router.post("/api/projects/{cycle_id}/philology-review", response_class=HTMLResponse)
async def update_project_philology_review(
    request: Request,
    cycle_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    form_payload = _parse_urlencoded_body(await request.body())
    review_status = str(form_payload.get("review_status") or "pending").strip() or "pending"
    terminology_page = _normalize_page(form_payload.get("terminology_page"), 1)
    collation_page = _normalize_page(form_payload.get("collation_page"), 1)
    document_title = str(form_payload.get("document_title_filter") or "").strip()
    work_title = str(form_payload.get("work_title_filter") or "").strip()
    version_lineage_key = str(form_payload.get("version_lineage_key_filter") or "").strip()
    witness_key = str(form_payload.get("witness_key_filter") or "").strip()
    decision_basis = str(form_payload.get("decision_basis") or "").strip()
    drawer = 1 if str(form_payload.get("drawer") or "0").strip() in {"1", "true", "True"} else 0

    review_payload = {
        "asset_type": str(form_payload.get("asset_type") or "").strip(),
        "asset_key": str(form_payload.get("asset_key") or "").strip(),
        "review_status": review_status,
        "reviewer": _resolve_dashboard_reviewer(user),
        "decision_basis": decision_basis or "项目详情文献学工作台快速审核",
        "candidate_kind": str(form_payload.get("candidate_kind") or "").strip(),
        "document_title": str(form_payload.get("document_title") or "").strip(),
        "document_urn": str(form_payload.get("document_urn") or "").strip(),
        "work_title": str(form_payload.get("work_title") or "").strip(),
        "fragment_title": str(form_payload.get("fragment_title") or "").strip(),
        "version_lineage_key": str(form_payload.get("version_lineage_key") or "").strip(),
        "witness_key": str(form_payload.get("witness_key") or "").strip(),
        "canonical": str(form_payload.get("canonical") or "").strip(),
        "label": str(form_payload.get("label") or "").strip(),
        "difference_type": str(form_payload.get("difference_type") or "").strip(),
        "base_text": str(form_payload.get("base_text") or "").strip(),
        "witness_text": str(form_payload.get("witness_text") or "").strip(),
        "claim_id": str(form_payload.get("claim_id") or "").strip(),
        "source_entity": str(form_payload.get("source_entity") or "").strip(),
        "target_entity": str(form_payload.get("target_entity") or "").strip(),
        "relation_type": str(form_payload.get("relation_type") or "").strip(),
        "fragment_candidate_id": str(form_payload.get("fragment_candidate_id") or "").strip(),
    }

    try:
        updated_session = apply_philology_review(request.app, cycle_id, review_payload)
        if updated_session is None:
            raise ValueError("Observe 阶段未持久化或研究任务不存在，无法写回文献学 review")
        session = updated_session
        error_message = ""
    except Exception as exc:
        logger.exception("dashboard philology review writeback failed: %s", cycle_id)
        try:
            session = get_research_session(request.app, cycle_id)
        except Exception:
            session = None
        error_message = f"文献学 review 写回失败: {exc}"

    return HTMLResponse(
        _render_session_detail_panel(
            session,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=bool(drawer),
            document_title=document_title,
            work_title=work_title,
            version_lineage_key=version_lineage_key,
            witness_key=witness_key,
            error_message=error_message,
        )
    )


@router.post("/api/projects/{cycle_id}/batch-catalog-review", response_class=HTMLResponse)
async def batch_project_catalog_review(
    request: Request,
    cycle_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    import json as _json

    try:
        raw_body = await request.body()
        body = _json.loads(raw_body) if raw_body else {}
    except Exception:
        body = {}

    decisions_raw: List[Dict[str, Any]] = body.get("decisions") or []
    reviewer = _resolve_dashboard_reviewer(user)
    terminology_page = int(body.get("terminology_page") or 1)
    collation_page = int(body.get("collation_page") or 1)
    drawer = 1 if body.get("drawer") else 0

    decisions = []
    for d in decisions_raw:
        d["reviewer"] = reviewer
        if not str(d.get("decision_basis") or "").strip():
            d["decision_basis"] = "仪表盘批量目录学审核"
        decisions.append(d)

    try:
        updated_session = apply_catalog_review_batch(request.app, cycle_id, decisions)
        if updated_session is None:
            raise ValueError("Observe 阶段未持久化或研究任务不存在")
        session = updated_session
        error_message = ""
    except Exception as exc:
        logger.exception("dashboard batch catalog review failed: %s", cycle_id)
        try:
            session = get_research_session(request.app, cycle_id)
        except Exception:
            session = None
        error_message = f"批量目录学 review 写回失败: {exc}"

    return HTMLResponse(
        _render_session_detail_panel(
            session,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=bool(drawer),
            error_message=error_message,
        )
    )


@router.post("/api/projects/{cycle_id}/batch-philology-review", response_class=HTMLResponse)
async def batch_project_philology_review(
    request: Request,
    cycle_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    import json as _json

    try:
        raw_body = await request.body()
        body = _json.loads(raw_body) if raw_body else {}
    except Exception:
        body = {}

    decisions_raw: List[Dict[str, Any]] = body.get("decisions") or []
    reviewer = _resolve_dashboard_reviewer(user)
    terminology_page = int(body.get("terminology_page") or 1)
    collation_page = int(body.get("collation_page") or 1)
    drawer = 1 if body.get("drawer") else 0

    decisions = []
    for d in decisions_raw:
        d["reviewer"] = reviewer
        if not str(d.get("decision_basis") or "").strip():
            d["decision_basis"] = "仪表盘批量文献学工作台审核"
        decisions.append(d)

    try:
        updated_session = apply_philology_review_batch(request.app, cycle_id, decisions)
        if updated_session is None:
            raise ValueError("Observe 阶段未持久化或研究任务不存在")
        session = updated_session
        error_message = ""
    except Exception as exc:
        logger.exception("dashboard batch philology review failed: %s", cycle_id)
        try:
            session = get_research_session(request.app, cycle_id)
        except Exception:
            session = None
        error_message = f"批量文献学 review 写回失败: {exc}"

    return HTMLResponse(
        _render_session_detail_panel(
            session,
            terminology_page=terminology_page,
            collation_page=collation_page,
            drawer=bool(drawer),
            error_message=error_message,
        )
    )


@router.get("/api/projects/{cycle_id}/fragment-preview", response_class=HTMLResponse)
async def project_fragment_preview(
    request: Request,
    cycle_id: str,
    document_urn: str = "",
    document_title: str = "",
    highlight: str = "",
    context: str = "",
    role: str = "base",
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    try:
        session = get_research_session(request.app, cycle_id)
    except Exception as exc:
        logger.exception("dashboard project fragment preview failed: %s", cycle_id)
        return HTMLResponse(
            _render_fragment_preview_modal(
                None,
                document_urn=document_urn,
                document_title=document_title,
                highlight=highlight,
                context=context,
                role=role,
                error_message=f"加载原始文档片段失败: {exc}",
            )
        )

    return HTMLResponse(
        _render_fragment_preview_modal(
            session,
            document_urn=document_urn,
            document_title=document_title,
            highlight=highlight,
            context=context,
            role=role,
            error_message=f"未找到研究任务: {cycle_id}",
        )
    )


# ---------------------------------------------------------------------------
# AI Assistant panel
# ---------------------------------------------------------------------------


@router.get("/api/ai/assistant", response_class=HTMLResponse)
async def ai_assistant_panel(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    html = """
    <h2 class="font-semibold text-gray-800 text-lg mb-4">AI 助手</h2>
    <div class="border border-gray-200 rounded-lg overflow-hidden">
        <!-- Chat history -->
        <div id="chat-history"
             class="h-80 overflow-y-auto p-4 bg-gray-50 space-y-3">
            <div class="flex gap-3">
                <span class="text-2xl">🤖</span>
                <div class="bg-white rounded-lg px-4 py-3 shadow-sm text-sm text-gray-700 max-w-lg">
                    您好！我是中医智慧科研助手。可以为您提供：
                    <ul class="list-disc ml-5 mt-2 space-y-1 text-gray-500">
                        <li>文献检索与综述</li>
                        <li>实验设计建议</li>
                        <li>新颖性评估</li>
                        <li>论文写作辅助</li>
                        <li>中医理论问答</li>
                    </ul>
                    <p class="mt-3 text-xs text-emerald-600">
                        研究执行入口已统一为 POST /api/research/run；如需异步跟踪，请使用 POST /api/research/jobs。
                    </p>
                </div>
            </div>
        </div>
        <!-- Input -->
        <form class="flex border-t border-gray-200"
              onsubmit="event.preventDefault(); sendChat();">
            <input id="chat-input" type="text"
                   placeholder="输入您的问题…（如：黄芪补气的古籍记载有哪些？）"
                   class="flex-1 px-4 py-3 text-sm focus:outline-none" />
            <button type="submit"
                    class="px-5 py-3 bg-emerald-600 text-white text-sm font-medium
                           hover:bg-emerald-700 transition">
                发送
            </button>
        </form>
    </div>
    <script>
    async function sendChat() {
        var input = document.getElementById('chat-input');
        var msg = input.value.trim();
        if (!msg) return;
        var history = document.getElementById('chat-history');

        // 显示用户消息
        history.innerHTML += '<div class="flex gap-3 justify-end">'
            + '<div class="bg-emerald-600 text-white rounded-lg px-4 py-3 shadow-sm text-sm max-w-lg">'
            + msg + '</div><span class="text-2xl">👤</span></div>';
        input.value = '';
        history.scrollTop = history.scrollHeight;

        // 调用后端
        try {
            var token = localStorage.getItem('access_token');
            var resp = await fetch('/api/assistant/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify({message: msg, session_id: 'web-default'})
            });
            var data = await resp.json();
            var reply = data.reply || data.detail || '抱歉，无法处理您的请求。';
            history.innerHTML += '<div class="flex gap-3">'
                + '<span class="text-2xl">🤖</span>'
                + '<div class="bg-white rounded-lg px-4 py-3 shadow-sm text-sm text-gray-700 max-w-lg">'
                + reply + '</div></div>';
        } catch(e) {
            history.innerHTML += '<div class="flex gap-3">'
                + '<span class="text-2xl">🤖</span>'
                + '<div class="bg-red-50 rounded-lg px-4 py-3 text-sm text-red-600 max-w-lg">'
                + '网络错误，请稍后重试</div></div>';
        }
        history.scrollTop = history.scrollHeight;
    }
    </script>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Literature
# ---------------------------------------------------------------------------


@router.get("/api/literature", response_class=HTMLResponse)
async def literature_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    # 列出 data/ 目录下的古籍文件
    items_html = ""
    try:
        files = sorted(_DATA_DIR.glob("*.txt"))
        for f in files[:20]:  # 展示前 20 个
            name = f.stem
            size_kb = f.stat().st_size / 1024
            items_html += (
                f'<tr class="hover:bg-gray-50">'
                f'<td class="px-4 py-3 text-sm text-gray-700">{name}</td>'
                f'<td class="px-4 py-3 text-sm text-gray-500">{size_kb:.1f} KB</td>'
                f'<td class="px-4 py-3 text-sm text-gray-500">TXT</td>'
                f"</tr>"
            )
        remaining = len(files) - 20
        if remaining > 0:
            items_html += (
                f'<tr><td colspan="3" class="px-4 py-3 text-sm text-gray-400 text-center">'
                f"… 还有 {remaining} 个文件</td></tr>"
            )
    except Exception as exc:
        items_html = (
            f'<tr><td colspan="3" class="px-4 py-3 text-sm text-red-500">'
            f"加载失败: {exc}</td></tr>"
        )

    corpus_count = _count_corpus_files()

    html = f"""
    {_section_header("文献库", f"共 {corpus_count} 部古籍文献")}
    <div class="overflow-x-auto">
        <table class="min-w-full">
            <thead>
                <tr class="border-b border-gray-200">
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">文献名</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">大小</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">格式</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">{items_html}</tbody>
        </table>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------


@router.get("/api/knowledge-graph", response_class=HTMLResponse)
async def knowledge_graph_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    html = f"""
    {_section_header("知识图谱", "可视化中医知识关系网络 · 知识蒸馏沉淀")}

    <!-- 累积统计条 -->
    <div id="kg-accumulated" class="mb-4 p-3 bg-emerald-50 rounded-lg border border-emerald-200">
        <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-emerald-700">📊 知识库累积</h3>
            <div class="flex items-center gap-3">
                <span id="kg-refresh-ts" class="text-xs text-emerald-400"></span>
                <button type="button" onclick="refreshKgStats()"
                        class="text-xs text-emerald-600 hover:underline">刷新</button>
            </div>
        </div>
        <div class="grid grid-cols-3 lg:grid-cols-6 gap-2 mt-2 text-sm">
            <div class="text-center"><span class="text-gray-500">主库实体</span>
                 <span id="kg-orm-ent" class="block font-bold text-emerald-700">—</span></div>
            <div class="text-center"><span class="text-gray-500">主库关系</span>
                 <span id="kg-orm-rel" class="block font-bold text-emerald-700">—</span></div>
            <div class="text-center"><span class="text-gray-500">文档数</span>
                 <span id="kg-orm-doc" class="block font-bold text-emerald-700">—</span></div>
            <div class="text-center"><span class="text-gray-500">图谱实体</span>
                 <span id="kg-total-ent" class="block font-bold text-gray-800">—</span></div>
            <div class="text-center"><span class="text-gray-500">图谱关系</span>
                 <span id="kg-total-rel" class="block font-bold text-gray-800">—</span></div>
            <div class="text-center"><span class="text-gray-500">实体类型</span>
                 <span id="kg-total-types" class="block font-bold text-gray-800">—</span></div>
        </div>
        <div id="kg-orm-types" class="mt-2 flex flex-wrap gap-1"></div>
    </div>

    <!-- 输入区 -->
    <div class="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h3 class="text-sm font-semibold text-gray-600 mb-2">输入古籍/方剂文本</h3>
        <textarea id="kg-input" rows="5"
                  placeholder="示例：桂枝汤由桂枝、芍药、甘草、生姜、大枣组成，主治太阳中风证，症见发热、汗出、恶风、脉浮缓。麻黄汤由麻黄、桂枝、杏仁、甘草组成，主治太阳伤寒证。"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                         focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-y"></textarea>
        <div class="mt-3 flex items-center gap-3">
            <button type="button" onclick="runKnowledgeGraph()"
                    id="kg-run-btn"
                    class="px-5 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg
                           hover:bg-emerald-700 transition disabled:opacity-50 disabled:cursor-wait">
                生成知识图谱
            </button>
            <button type="button" onclick="runLLMDistill()"
                    id="kg-distill-btn"
                    class="px-5 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg
                           hover:bg-purple-700 transition disabled:opacity-50 disabled:cursor-wait">
                🧠 LLM 知识蒸馏
            </button>
            <span id="kg-status" class="text-xs text-gray-400"></span>
        </div>
    </div>

    <!-- 结果区 -->
    <div id="kg-result" class="hidden">
        <!-- 本次统计卡片 -->
        <div id="kg-stats" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4"></div>

        <!-- SVG 图谱 -->
        <div class="border border-gray-200 rounded-lg overflow-hidden bg-white mb-4">
            <svg id="kg-svg" width="100%" height="480" class="block"></svg>
        </div>

        <!-- 实体列表 -->
        <div id="kg-entities" class="p-4 bg-gray-50 rounded-lg"></div>
    </div>

    <!-- 空状态（初始） -->
    <div id="kg-empty">
    """ + _empty_state("🕸️", "等待输入",
                   "在上方输入包含中药、方剂、证候的文本，"
                   "点击「生成知识图谱」或「LLM 知识蒸馏」即可看到可视化结果。") + f"""
    </div>

    <!-- 图谱类型选项卡 -->
    <div class="mt-6 p-4 bg-gray-50 rounded-lg">
        <h3 class="text-sm font-semibold text-gray-600 mb-2">知识图谱分类浏览（点击查看累积知识）</h3>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <div onclick="loadSubgraph('herb_relations')"
                 class="bg-white rounded-lg p-3 border border-gray-100 text-center cursor-pointer
                        hover:border-emerald-400 hover:bg-emerald-50 hover:shadow-sm transition"
                 id="kg-tab-herb_relations">
                <span class="text-2xl block mb-1">🌿</span>药物关系图
            </div>
            <div onclick="loadSubgraph('formula_composition')"
                 class="bg-white rounded-lg p-3 border border-gray-100 text-center cursor-pointer
                        hover:border-orange-400 hover:bg-orange-50 hover:shadow-sm transition"
                 id="kg-tab-formula_composition">
                <span class="text-2xl block mb-1">📋</span>方剂组成图
            </div>
            <div onclick="loadSubgraph('syndrome_treatment')"
                 class="bg-white rounded-lg p-3 border border-gray-100 text-center cursor-pointer
                        hover:border-purple-400 hover:bg-purple-50 hover:shadow-sm transition"
                 id="kg-tab-syndrome_treatment">
                <span class="text-2xl block mb-1">🔄</span>证治关系图
            </div>
            <div onclick="loadSubgraph('literature_citation')"
                 class="bg-white rounded-lg p-3 border border-gray-100 text-center cursor-pointer
                        hover:border-blue-400 hover:bg-blue-50 hover:shadow-sm transition"
                 id="kg-tab-literature_citation">
                <span class="text-2xl block mb-1">📖</span>文献引用图
            </div>
        </div>
    </div>

    <script>
    /* ---- 页面加载时获取累积统计 ---- */
    (function() {{ refreshKgStats(); }})();

    async function _authHeaders() {{
        const token = localStorage.getItem('access_token') || '';
        return {{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token,
        }};
    }}

    async function refreshKgStats() {{
        try {{
            const resp = await fetch('/api/analysis/kg/stats', {{
                headers: await _authHeaders(),
            }});
            if (!resp.ok) return;
            const d = await resp.json();
            /* ORM 主库 */
            document.getElementById('kg-orm-ent').textContent = (d.orm_entities || 0).toLocaleString();
            document.getElementById('kg-orm-rel').textContent = (d.orm_relations || 0).toLocaleString();
            document.getElementById('kg-orm-doc').textContent = (d.orm_documents || 0).toLocaleString();
            /* 图谱 */
            document.getElementById('kg-total-ent').textContent = d.total_entities;
            document.getElementById('kg-total-rel').textContent = d.total_relations;
            document.getElementById('kg-total-types').textContent =
                Object.keys(d.entity_types || {{}}).length;
            /* ORM 实体类型标签 */
            const ormTypes = d.orm_entity_types || {{}};
            const typesEl = document.getElementById('kg-orm-types');
            if (typesEl) {{
                typesEl.innerHTML = Object.entries(ormTypes).map(
                    ([k,v]) => '<span class="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">' + k + ' ' + v + '</span>'
                ).join('');
            }}
            /* 刷新时间 */
            const ts = document.getElementById('kg-refresh-ts');
            if (ts) ts.textContent = new Date().toLocaleTimeString();
        }} catch(e) {{}}
    }}

    /* 每 30 秒自动刷新累积统计 */
    setInterval(refreshKgStats, 30000);

    /* ---- 文本分析（规则管线 + 知识沉淀） ---- */
    async function runKnowledgeGraph() {{
        const input = document.getElementById('kg-input');
        const text = (input.value || '').trim();
        if (!text) {{ alert('请输入文本'); return; }}

        const btn = document.getElementById('kg-run-btn');
        const statusEl = document.getElementById('kg-status');
        btn.disabled = true;
        statusEl.textContent = '正在分析…';

        try {{
            const resp = await fetch('/api/analysis/text', {{
                method: 'POST',
                headers: await _authHeaders(),
                body: JSON.stringify({{ raw_text: text }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            renderKG(data);
            const acc = data.knowledge_accumulation || {{}};
            statusEl.textContent = '分析完成 — 新增 ' + (acc.new_entities || 0) + ' 实体, '
                + (acc.new_relations || 0) + ' 关系 (累计 ' + (acc.total_entities || '?') + ' / ' + (acc.total_relations || '?') + ')';
            refreshKgStats();
        }} catch (e) {{
            statusEl.textContent = '分析失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    /* ---- LLM 知识蒸馏 ---- */
    async function runLLMDistill() {{
        const input = document.getElementById('kg-input');
        const text = (input.value || '').trim();
        if (!text) {{ alert('请输入文本'); return; }}

        const btn = document.getElementById('kg-distill-btn');
        const statusEl = document.getElementById('kg-status');
        btn.disabled = true;
        statusEl.textContent = '🧠 LLM 知识蒸馏中（可能需30-60秒）…';

        try {{
            const resp = await fetch('/api/analysis/distill', {{
                method: 'POST',
                headers: await _authHeaders(),
                body: JSON.stringify({{ raw_text: text }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            renderKG(data);
            const acc = data.knowledge_accumulation || {{}};
            const llm = data.llm_extracted || {{}};
            statusEl.textContent = '蒸馏完成 — LLM 提取 ' + (llm.entities || 0) + ' 实体 + '
                + (llm.relations || 0) + ' 关系 · 新增 ' + (acc.new_entities || 0)
                + ' 实体, ' + (acc.new_relations || 0) + ' 关系 (累计 ' + (acc.total_entities || '?') + ')';
            refreshKgStats();
        }} catch (e) {{
            statusEl.textContent = '蒸馏失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    /* ---- 子图加载（四种图谱类型） ---- */
    var _activeTab = '';
    async function loadSubgraph(graphType) {{
        // 高亮选中 tab
        ['herb_relations','formula_composition','syndrome_treatment','literature_citation'].forEach(function(t) {{
            var el = document.getElementById('kg-tab-' + t);
            if (el) el.classList.toggle('ring-2', t === graphType);
            if (el) el.classList.toggle('ring-emerald-500', t === graphType);
        }});
        _activeTab = graphType;

        const statusEl = document.getElementById('kg-status');
        statusEl.textContent = '加载 ' + graphType + ' 子图…';

        try {{
            const resp = await fetch('/api/analysis/kg/subgraph?graph_type=' + graphType, {{
                headers: await _authHeaders(),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            const nodes = data.nodes || [];
            const edges = data.edges || [];

            document.getElementById('kg-empty').classList.add('hidden');
            document.getElementById('kg-result').classList.remove('hidden');

            const statsEl = document.getElementById('kg-stats');
            statsEl.innerHTML = [
                kgCard('图谱类型', data.label || graphType),
                kgCard('节点数', (data.statistics || {{}}).nodes_count || nodes.length),
                kgCard('关系数', (data.statistics || {{}}).edges_count || edges.length),
                kgCard('显示', Math.min(nodes.length, 500) + ' 节点'),
            ].join('');

            renderKGSvg(nodes, edges);

            // 实体列表
            const entEl = document.getElementById('kg-entities');
            if (nodes.length === 0) {{
                entEl.innerHTML = '<p class="text-sm text-gray-400">该图谱类型暂无知识数据，请先进行文本分析或 LLM 蒸馏</p>';
            }} else {{
                const grouped = {{}};
                nodes.forEach(function(n) {{
                    const t = n.type || '其他';
                    if (!grouped[t]) grouped[t] = [];
                    grouped[t].push(n.name || n.id);
                }});
                let html = '<h3 class="text-sm font-semibold text-gray-600 mb-2">' + (data.label || '') + ' 实体</h3>';
                for (const [type, names] of Object.entries(grouped)) {{
                    html += '<div class="mb-2"><span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">' + type + '</span> ';
                    html += '<span class="text-sm text-gray-600">' + names.slice(0, 30).join('、') + (names.length > 30 ? ' …' : '') + '</span></div>';
                }}
                entEl.innerHTML = html;
            }}
            statusEl.textContent = (data.label || '') + ' — ' + nodes.length + ' 节点, ' + edges.length + ' 关系';
        }} catch (e) {{
            statusEl.textContent = '加载子图失败: ' + e.message;
        }}
    }}

    /* ---- 渲染函数（共用） ---- */
    function renderKG(data) {{
        const entities = (data.entities || {{}}).items || [];
        const graph = (data.semantic_graph || {{}}).graph || {{}};
        const nodes = graph.nodes || [];
        const edges = graph.edges || [];

        document.getElementById('kg-empty').classList.add('hidden');
        document.getElementById('kg-result').classList.remove('hidden');

        const statsEl = document.getElementById('kg-stats');
        statsEl.innerHTML = [
            kgCard('实体数', entities.length),
            kgCard('节点数', nodes.length),
            kgCard('关系数', edges.length),
            kgCard('实体类型', countTypes(entities)),
        ].join('');

        renderKGSvg(nodes, edges);

        const entEl = document.getElementById('kg-entities');
        if (entities.length === 0) {{
            entEl.innerHTML = '<p class="text-sm text-gray-400">无识别实体</p>';
        }} else {{
            const grouped = {{}};
            entities.forEach(function(e) {{
                const t = e.type || e.entity_type || '其他';
                if (!grouped[t]) grouped[t] = [];
                grouped[t].push(e.name || e.text || e.value || JSON.stringify(e));
            }});
            let html = '<h3 class="text-sm font-semibold text-gray-600 mb-2">识别实体</h3>';
            for (const [type, names] of Object.entries(grouped)) {{
                html += '<div class="mb-2"><span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">' + type + '</span> ';
                html += '<span class="text-sm text-gray-600">' + names.slice(0, 20).join('、') + (names.length > 20 ? ' …' : '') + '</span></div>';
            }}
            entEl.innerHTML = html;
        }}
    }}

    function kgCard(label, val) {{
        return '<div class="bg-white rounded-xl shadow-sm p-4 border border-gray-100 text-center">'
            + '<p class="text-xs text-gray-500 uppercase tracking-wide">' + label + '</p>'
            + '<p class="text-xl font-bold text-gray-800 mt-1">' + val + '</p></div>';
    }}

    function countTypes(entities) {{
        const s = new Set();
        entities.forEach(function(e) {{ s.add(e.type || e.entity_type || '其他'); }});
        return s.size;
    }}

    const KG_TYPE_COLORS = {{
        '中药': '#059669', '方剂': '#d97706', '证候': '#7c3aed',
        '症状': '#dc2626', '治法': '#2563eb', '穴位': '#0891b2',
        'herb': '#059669', 'formula': '#d97706', 'syndrome': '#7c3aed',
        'symptom': '#dc2626', 'method': '#2563eb', 'efficacy': '#10b981',
        'default': '#6b7280',
    }};

    function nodeColor(node) {{
        const t = (node.type || node.entity_type || '').toLowerCase();
        return KG_TYPE_COLORS[t] || KG_TYPE_COLORS['default'];
    }}

    function renderKGSvg(nodes, edges) {{
        const svg = document.getElementById('kg-svg');
        const W = svg.clientWidth || 800;
        const H = 480;
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        svg.innerHTML = '';

        if (nodes.length === 0) {{
            svg.innerHTML = '<text x="' + W/2 + '" y="' + H/2 + '" text-anchor="middle" fill="#9ca3af" font-size="14">暂无图谱节点</text>';
            return;
        }}

        // 简单环形布局
        const cx = W / 2, cy = H / 2;
        const r = Math.min(W, H) * 0.38;
        const nodeMap = {{}};
        nodes.forEach(function(n, i) {{
            const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
            n._x = cx + r * Math.cos(angle);
            n._y = cy + r * Math.sin(angle);
            nodeMap[n.id || n.name || i] = n;
        }});

        // 画边
        edges.forEach(function(e) {{
            const src = nodeMap[e.source] || nodeMap[e.from];
            const tgt = nodeMap[e.target] || nodeMap[e.to];
            if (!src || !tgt) return;
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', src._x);
            line.setAttribute('y1', src._y);
            line.setAttribute('x2', tgt._x);
            line.setAttribute('y2', tgt._y);
            line.setAttribute('stroke', '#d1d5db');
            line.setAttribute('stroke-width', 1.5);
            svg.appendChild(line);
            const label = e.relation || e.label || '';
            if (label) {{
                const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                txt.setAttribute('x', (src._x + tgt._x) / 2);
                txt.setAttribute('y', (src._y + tgt._y) / 2 - 4);
                txt.setAttribute('text-anchor', 'middle');
                txt.setAttribute('fill', '#9ca3af');
                txt.setAttribute('font-size', '10');
                txt.textContent = label;
                svg.appendChild(txt);
            }}
        }});

        // 画节点
        nodes.forEach(function(n) {{
            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', n._x);
            circle.setAttribute('cy', n._y);
            circle.setAttribute('r', 18);
            circle.setAttribute('fill', nodeColor(n));
            circle.setAttribute('opacity', '0.85');
            g.appendChild(circle);
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', n._x);
            text.setAttribute('y', n._y + 30);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#374151');
            text.setAttribute('font-size', '11');
            text.textContent = (n.name || n.label || n.id || '').slice(0, 8);
            g.appendChild(text);

            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = (n.name || n.label || '') + ' (' + (n.type || n.entity_type || '') + ')';
            g.appendChild(title);

            svg.appendChild(g);
        }});
    }}
    </script>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Analysis Tools
# ---------------------------------------------------------------------------


@router.get("/api/analysis/tools", response_class=HTMLResponse)
async def analysis_tools_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    html = f"""
    {_section_header("分析工具", "中医古籍智能分析工具箱")}

    <!-- ===== 知识增长总览面板 ===== -->
    <div id="kg-growth-bar" class="mb-6 bg-gradient-to-r from-emerald-50 to-teal-50 rounded-xl border border-emerald-100 p-5">
        <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-emerald-800 text-sm">📊 知识库增长总览</h3>
            <button type="button" onclick="refreshKgGrowth()" id="kg-refresh-btn"
                    class="text-xs text-emerald-600 hover:text-emerald-800 transition">🔄 刷新</button>
        </div>
        <div id="kg-growth-cards" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div class="bg-white/80 rounded-lg p-3 text-center animate-pulse">
                <p class="text-xs text-gray-400">加载中…</p>
            </div>
        </div>
        <div id="kg-growth-types" class="mt-3 flex flex-wrap gap-2"></div>
    </div>
    <!-- 工具卡片入口 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <button type="button" onclick="openTool('text')"
                id="tool-btn-text"
                class="bg-white rounded-xl border border-gray-100 p-5 text-left hover:shadow-md
                       hover:border-emerald-200 transition cursor-pointer">
            <span class="text-3xl block mb-3">📝</span>
            <h3 class="font-semibold text-gray-800 mb-1">文本处理链</h3>
            <p class="text-sm text-gray-500">古籍预处理 → 实体抽取 → 语义建模</p>
        </button>
        <button type="button" onclick="openTool('formula')"
                id="tool-btn-formula"
                class="bg-white rounded-xl border border-gray-100 p-5 text-left hover:shadow-md
                       hover:border-emerald-200 transition cursor-pointer">
            <span class="text-3xl block mb-3">💊</span>
            <h3 class="font-semibold text-gray-800 mb-1">方剂综合分析</h3>
            <p class="text-sm text-gray-500">方剂配伍分析与综合评分</p>
        </button>
        <button type="button" onclick="openTool('kg')"
                id="tool-btn-kg"
                class="bg-white rounded-xl border border-gray-100 p-5 text-left hover:shadow-md
                       hover:border-emerald-200 transition cursor-pointer">
            <span class="text-3xl block mb-3">🕸️</span>
            <h3 class="font-semibold text-gray-800 mb-1">知识图谱生成</h3>
            <p class="text-sm text-gray-500">从文本生成知识图谱并可视化</p>
        </button>
    </div>

    <!-- ==================== 文本处理链面板 ==================== -->
    <div id="panel-text" class="hidden mb-6">
        <div class="bg-white rounded-xl border border-gray-100 p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-gray-800">📝 文本处理链</h3>
                <button type="button" onclick="closeTool('text')"
                        class="text-sm text-gray-400 hover:text-gray-600">✕ 关闭</button>
            </div>
            <textarea id="at-text-input" rows="6"
                      placeholder="粘贴古籍原文或中医方剂文本…&#10;示例：麻黄汤由麻黄、桂枝、杏仁、甘草组成，主治太阳伤寒表实证。"
                      class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                             focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-y"></textarea>
            <div class="mt-3 flex items-center gap-3">
                <button type="button" onclick="runTextPipeline()"
                        id="at-text-btn"
                        class="px-5 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg
                               hover:bg-emerald-700 transition disabled:opacity-50 disabled:cursor-wait">
                    开始分析
                </button>
                <span id="at-text-status" class="text-xs text-gray-400"></span>
            </div>
            <div id="at-text-result" class="mt-4 hidden">
                <div id="at-text-stats" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3"></div>
                <div id="at-text-entities" class="p-4 bg-gray-50 rounded-lg text-sm"></div>
            </div>
        </div>
    </div>

    <!-- ==================== 方剂综合分析面板 ==================== -->
    <div id="panel-formula" class="hidden mb-6">
        <div class="bg-white rounded-xl border border-gray-100 p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-gray-800">💊 方剂综合分析</h3>
                <button type="button" onclick="closeTool('formula')"
                        class="text-sm text-gray-400 hover:text-gray-600">✕ 关闭</button>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                    <label class="block text-sm font-medium text-gray-600 mb-1">方剂名称</label>
                    <input id="at-fm-name" type="text" placeholder="如：桂枝汤"
                           class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                                  focus:outline-none focus:ring-2 focus:ring-emerald-400" />
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-600 mb-1">组成药味（逗号分隔）</label>
                    <input id="at-fm-herbs" type="text" placeholder="桂枝, 芍药, 甘草, 生姜, 大枣"
                           class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                                  focus:outline-none focus:ring-2 focus:ring-emerald-400" />
                </div>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-600 mb-1">主治 / 功效描述</label>
                <textarea id="at-fm-desc" rows="3"
                          placeholder="调和营卫，解肌发表。治太阳中风，头痛发热，汗出恶风…"
                          class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                                 focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-y"></textarea>
            </div>
            <div class="flex items-center gap-3">
                <button type="button" onclick="runFormulaAnalysis()"
                        id="at-fm-btn"
                        class="px-5 py-2 bg-orange-600 text-white text-sm font-medium rounded-lg
                               hover:bg-orange-700 transition disabled:opacity-50 disabled:cursor-wait">
                    开始分析
                </button>
                <span id="at-fm-status" class="text-xs text-gray-400"></span>
            </div>
            <div id="at-fm-result" class="mt-4 hidden">
                <pre id="at-fm-output"
                     class="p-4 bg-gray-50 rounded-lg text-sm text-gray-700 overflow-x-auto whitespace-pre-wrap"></pre>
            </div>
        </div>
    </div>

    <!-- ==================== 知识图谱生成面板 ==================== -->
    <div id="panel-kg" class="hidden mb-6">
        <div class="bg-white rounded-xl border border-gray-100 p-6">
            <div class="flex items-center justify-between mb-4">
                <h3 class="font-semibold text-gray-800">🕸️ 知识图谱生成</h3>
                <button type="button" onclick="closeTool('kg')"
                        class="text-sm text-gray-400 hover:text-gray-600">✕ 关闭</button>
            </div>
            <textarea id="at-kg-input" rows="6"
                      placeholder="输入古籍/方剂文本，系统将提取实体与关系并生成可视化图谱…"
                      class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg
                             focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-y"></textarea>
            <div class="mt-3 flex items-center gap-3">
                <button type="button" onclick="runKgGenerate()"
                        id="at-kg-btn"
                        class="px-5 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg
                               hover:bg-purple-700 transition disabled:opacity-50 disabled:cursor-wait">
                    生成图谱
                </button>
                <button type="button" onclick="runKgDistill()"
                        id="at-kg-distill-btn"
                        class="px-5 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg
                               hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-wait">
                    🧠 LLM 蒸馏
                </button>
                <span id="at-kg-status" class="text-xs text-gray-400"></span>
            </div>
            <div id="at-kg-result" class="mt-4 hidden">
                <div id="at-kg-stats" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3"></div>
                <div class="border border-gray-200 rounded-lg overflow-hidden bg-white mb-3">
                    <svg id="at-kg-svg" width="100%" height="400" class="block"></svg>
                </div>
                <div id="at-kg-entities" class="p-4 bg-gray-50 rounded-lg text-sm"></div>
            </div>
        </div>
    </div>

    <script>
    /* ---- 知识增长总览 ---- */
    async function refreshKgGrowth() {{
        try {{
            const token = localStorage.getItem('access_token') || '';
            const resp = await fetch('/api/analysis/kg/stats', {{
                headers: {{ 'Authorization': 'Bearer ' + token }}
            }});
            if (!resp.ok) return;
            const d = await resp.json();
            const cards = document.getElementById('kg-growth-cards');
            const typesEl = document.getElementById('kg-growth-types');
            if (!cards) return;
            cards.innerHTML = [
                _growCard('🗂️ KG 实体', d.total_entities || 0, 'text-emerald-700'),
                _growCard('🔗 KG 关系', d.total_relations || 0, 'text-teal-700'),
                _growCard('📋 ORM 实体', d.orm_entities || 0, 'text-blue-700'),
                _growCard('📎 ORM 关系', d.orm_relations || 0, 'text-indigo-700'),
                _growCard('📄 文档数', d.orm_documents || 0, 'text-purple-700'),
                _growCard('🏷️ 实体类型', Object.keys(d.entity_types || {{}}).length, 'text-orange-700'),
            ].join('');

            // 实体类型标签
            let tags = '';
            const mapping = {{'herb':'🌿 中药','formula':'📜 方剂','syndrome':'🔬 证候',
                             'efficacy':'💊 功效','property':'🏷️ 药性','meridian':'📍 归经',
                             'generic':'📦 通用','other':'📎 其他'}};
            const allTypes = Object.assign({{}}, d.entity_types || {{}}, d.orm_entity_types || {{}});
            for (const [t, cnt] of Object.entries(allTypes)) {{
                const label = mapping[t] || t;
                tags += '<span class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-white border border-gray-200 text-gray-600">'
                    + label + ' <span class="ml-1 font-bold">' + cnt + '</span></span>';
            }}
            typesEl.innerHTML = tags;
        }} catch(e) {{
            console.warn('refreshKgGrowth failed', e);
        }}
    }}

    function _growCard(label, val, cls) {{
        return '<div class="bg-white/80 rounded-lg p-3 text-center shadow-sm">'
            + '<p class="text-xs text-gray-500">' + label + '</p>'
            + '<p class="text-xl font-bold mt-1 ' + (cls || '') + '">' + val + '</p></div>';
    }}

    // 页面加载时自动获取
    refreshKgGrowth();

    /* ---- 通用 helpers ---- */
    async function _atAuthHeaders() {{
        const token = localStorage.getItem('access_token') || '';
        return {{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token,
        }};
    }}

    function _atCard(label, val) {{
        return '<div class="bg-white rounded-xl shadow-sm p-3 border border-gray-100 text-center">'
            + '<p class="text-xs text-gray-500 uppercase tracking-wide">' + label + '</p>'
            + '<p class="text-lg font-bold text-gray-800 mt-1">' + val + '</p></div>';
    }}

    /* ---- 面板切换 ---- */
    function openTool(toolId) {{
        ['text','formula','kg'].forEach(function(t) {{
            var panel = document.getElementById('panel-' + t);
            var btn = document.getElementById('tool-btn-' + t);
            if (t === toolId) {{
                panel.classList.remove('hidden');
                btn.classList.add('ring-2', 'ring-emerald-500', 'border-emerald-400');
            }} else {{
                panel.classList.add('hidden');
                btn.classList.remove('ring-2', 'ring-emerald-500', 'border-emerald-400');
            }}
        }});
    }}

    function closeTool(toolId) {{
        document.getElementById('panel-' + toolId).classList.add('hidden');
        var btn = document.getElementById('tool-btn-' + toolId);
        btn.classList.remove('ring-2', 'ring-emerald-500', 'border-emerald-400');
    }}

    /* ---- 文本处理链 ---- */
    async function runTextPipeline() {{
        const text = (document.getElementById('at-text-input').value || '').trim();
        if (!text) {{ alert('请输入文本'); return; }}
        const btn = document.getElementById('at-text-btn');
        const status = document.getElementById('at-text-status');
        btn.disabled = true;
        status.textContent = '正在分析…';

        try {{
            const resp = await fetch('/api/analysis/text', {{
                method: 'POST',
                headers: await _atAuthHeaders(),
                body: JSON.stringify({{ raw_text: text }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            document.getElementById('at-text-result').classList.remove('hidden');

            const entities = (data.entities || {{}}).items || [];
            const stats = (data.entities || {{}}).statistics || {{}};
            const graph = (data.semantic_graph || {{}}).graph || {{}};
            const acc = data.knowledge_accumulation || {{}};

            document.getElementById('at-text-stats').innerHTML = [
                _atCard('实体数', entities.length),
                _atCard('关系数', (graph.edges || []).length),
                _atCard('新增实体', acc.new_entities || 0),
                _atCard('累计实体', acc.total_entities || '—'),
            ].join('');

            // 实体列表
            const grouped = {{}};
            entities.forEach(function(e) {{
                const t = e.type || e.entity_type || '其他';
                if (!grouped[t]) grouped[t] = [];
                grouped[t].push(e.name || e.text || '');
            }});
            let html = '<h4 class="font-semibold text-gray-600 mb-2">识别实体</h4>';
            for (const [type, names] of Object.entries(grouped)) {{
                html += '<div class="mb-1"><span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">' + type + '</span> ';
                html += '<span class="text-gray-600">' + names.slice(0, 30).join('、') + '</span></div>';
            }}
            document.getElementById('at-text-entities').innerHTML = html;
            status.textContent = '分析完成 — ' + entities.length + ' 实体, ' + (graph.edges || []).length + ' 关系';
            refreshKgGrowth();
        }} catch (e) {{
            status.textContent = '分析失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    /* ---- 方剂综合分析 ---- */
    async function runFormulaAnalysis() {{
        const name = (document.getElementById('at-fm-name').value || '').trim();
        const herbs = (document.getElementById('at-fm-herbs').value || '').trim();
        const desc = (document.getElementById('at-fm-desc').value || '').trim();
        if (!name && !herbs) {{ alert('请至少输入方剂名称或组成药味'); return; }}

        const btn = document.getElementById('at-fm-btn');
        const status = document.getElementById('at-fm-status');
        btn.disabled = true;
        status.textContent = '正在分析…';

        const perspective = {{
            formula_name: name,
            herbs: herbs ? herbs.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
            description: desc,
        }};

        try {{
            const resp = await fetch('/api/analysis/formula', {{
                method: 'POST',
                headers: await _atAuthHeaders(),
                body: JSON.stringify({{ perspective: perspective }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            document.getElementById('at-fm-result').classList.remove('hidden');
            document.getElementById('at-fm-output').textContent = JSON.stringify(data.result || data, null, 2);
            status.textContent = '分析完成';
            refreshKgGrowth();
        }} catch (e) {{
            status.textContent = '分析失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    /* ---- 知识图谱生成 ---- */
    async function runKgGenerate() {{
        const text = (document.getElementById('at-kg-input').value || '').trim();
        if (!text) {{ alert('请输入文本'); return; }}
        const btn = document.getElementById('at-kg-btn');
        const status = document.getElementById('at-kg-status');
        btn.disabled = true;
        status.textContent = '正在生成图谱…';

        try {{
            const resp = await fetch('/api/analysis/text', {{
                method: 'POST',
                headers: await _atAuthHeaders(),
                body: JSON.stringify({{ raw_text: text }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            _renderAtKg(data);
            const acc = data.knowledge_accumulation || {{}};
            status.textContent = '图谱生成完成 — 新增 ' + (acc.new_entities || 0) + ' 实体';
            refreshKgGrowth();
        }} catch (e) {{
            status.textContent = '生成失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    async function runKgDistill() {{
        const text = (document.getElementById('at-kg-input').value || '').trim();
        if (!text) {{ alert('请输入文本'); return; }}
        const btn = document.getElementById('at-kg-distill-btn');
        const status = document.getElementById('at-kg-status');
        btn.disabled = true;
        status.textContent = '🧠 LLM 知识蒸馏中…';

        try {{
            const resp = await fetch('/api/analysis/distill', {{
                method: 'POST',
                headers: await _atAuthHeaders(),
                body: JSON.stringify({{ raw_text: text }}),
            }});
            if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || resp.statusText);
            }}
            const data = await resp.json();
            _renderAtKg(data);
            const acc = data.knowledge_accumulation || {{}};
            const llm = data.llm_extracted || {{}};
            status.textContent = '蒸馏完成 — LLM ' + (llm.entities || 0) + ' 实体 + '
                + (llm.relations || 0) + ' 关系';
            refreshKgGrowth();
        }} catch (e) {{
            status.textContent = '蒸馏失败: ' + e.message;
        }} finally {{
            btn.disabled = false;
        }}
    }}

    /* ---- 知识图谱渲染 ---- */
    function _renderAtKg(data) {{
        document.getElementById('at-kg-result').classList.remove('hidden');
        const entities = (data.entities || {{}}).items || [];
        const graph = (data.semantic_graph || {{}}).graph || {{}};
        const nodes = graph.nodes || [];
        const edges = graph.edges || [];

        document.getElementById('at-kg-stats').innerHTML = [
            _atCard('实体数', entities.length),
            _atCard('节点数', nodes.length),
            _atCard('关系数', edges.length),
            _atCard('实体类型', new Set(entities.map(e => e.type || e.entity_type || '其他')).size),
        ].join('');

        // SVG 渲染
        const svg = document.getElementById('at-kg-svg');
        const W = svg.clientWidth || 800, H = 400;
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        svg.innerHTML = '';
        if (nodes.length === 0) {{
            svg.innerHTML = '<text x="' + W/2 + '" y="' + H/2 + '" text-anchor="middle" fill="#9ca3af" font-size="14">暂无图谱节点</text>';
        }} else {{
            const cx = W/2, cy = H/2, r = Math.min(W,H)*0.38;
            const nMap = {{}};
            nodes.forEach(function(n,i) {{
                const a = (2*Math.PI*i)/nodes.length - Math.PI/2;
                n._x = cx + r*Math.cos(a); n._y = cy + r*Math.sin(a);
                nMap[n.id || n.name || i] = n;
            }});
            edges.forEach(function(e) {{
                const s = nMap[e.source]||nMap[e.from], t = nMap[e.target]||nMap[e.to];
                if (!s||!t) return;
                const line = document.createElementNS('http://www.w3.org/2000/svg','line');
                line.setAttribute('x1',s._x); line.setAttribute('y1',s._y);
                line.setAttribute('x2',t._x); line.setAttribute('y2',t._y);
                line.setAttribute('stroke','#d1d5db'); line.setAttribute('stroke-width',1.5);
                svg.appendChild(line);
            }});
            nodes.forEach(function(n) {{
                const g = document.createElementNS('http://www.w3.org/2000/svg','g');
                const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
                c.setAttribute('cx',n._x); c.setAttribute('cy',n._y);
                c.setAttribute('r',16); c.setAttribute('fill','#059669'); c.setAttribute('opacity','0.85');
                g.appendChild(c);
                const t = document.createElementNS('http://www.w3.org/2000/svg','text');
                t.setAttribute('x',n._x); t.setAttribute('y',n._y+28);
                t.setAttribute('text-anchor','middle'); t.setAttribute('fill','#374151'); t.setAttribute('font-size','11');
                t.textContent = (n.name||n.label||'').slice(0,8);
                g.appendChild(t);
                svg.appendChild(g);
            }});
        }}

        // 实体列表
        const entEl = document.getElementById('at-kg-entities');
        if (entities.length === 0) {{
            entEl.innerHTML = '<p class="text-gray-400">无识别实体</p>';
        }} else {{
            const grouped = {{}};
            entities.forEach(function(e) {{
                const t = e.type || e.entity_type || '其他';
                if (!grouped[t]) grouped[t] = [];
                grouped[t].push(e.name || e.text || '');
            }});
            let html = '<h4 class="font-semibold text-gray-600 mb-2">识别实体</h4>';
            for (const [type, names] of Object.entries(grouped)) {{
                html += '<div class="mb-1"><span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">' + type + '</span> ';
                html += '<span class="text-gray-600">' + names.slice(0, 30).join('、') + '</span></div>';
            }}
            entEl.innerHTML = html;
        }}
    }}
    </script>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@router.get("/api/output", response_class=HTMLResponse)
async def output_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    items_html = ""
    try:
        if _OUTPUT_DIR.exists():
            files = sorted(_OUTPUT_DIR.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.is_file()][:15]
            for f in files:
                rel = f.relative_to(_OUTPUT_DIR)
                size_kb = f.stat().st_size / 1024
                items_html += (
                    f'<tr class="hover:bg-gray-50">'
                    f'<td class="px-4 py-3 text-sm text-gray-700">{rel}</td>'
                    f'<td class="px-4 py-3 text-sm text-gray-500">{size_kb:.1f} KB</td>'
                    f'<td class="px-4 py-3 text-sm text-gray-500">{f.suffix or "—"}</td>'
                    f"</tr>"
                )
    except Exception:
        pass

    if not items_html:
        return HTMLResponse(
            f'{_section_header("输出中心", "查看和管理研究输出")}'
            + _empty_state("📤", "暂无输出文件", "运行研究流程后，结果文件将在此展示")
        )

    count = _count_output_files()
    html = f"""
    {_section_header("输出中心", f"共 {count} 个输出文件")}
    <div class="overflow-x-auto">
        <table class="min-w-full">
            <thead>
                <tr class="border-b border-gray-200">
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">文件名</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">大小</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">类型</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">{items_html}</tbody>
        </table>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/api/settings", response_class=HTMLResponse)
async def settings_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    # 读取配置 (通过统一配置中心)
    sys_info = {}
    try:
        from src.infrastructure.config_loader import load_settings

        _st = load_settings()
        sys_info = _st.get_section("system", default={})
    except Exception:
        pass
    except Exception:
        pass

    name = sys_info.get("name", "TCM Auto Research")
    version = sys_info.get("version", "—")

    html = f"""
    {_section_header("系统设置")}
    <div class="space-y-4">
        <div class="bg-white rounded-xl border border-gray-100 p-5">
            <h3 class="font-semibold text-gray-700 mb-3">系统信息</h3>
            <dl class="grid grid-cols-2 gap-3 text-sm">
                <dt class="text-gray-500">系统名称</dt>
                <dd class="text-gray-800 font-medium">{name}</dd>
                <dt class="text-gray-500">版本</dt>
                <dd class="text-gray-800 font-medium">{version}</dd>
                <dt class="text-gray-500">运行环境</dt>
                <dd class="text-gray-800 font-medium">development</dd>
                <dt class="text-gray-500">Python</dt>
                <dd class="text-gray-800 font-medium">3.10</dd>
            </dl>
        </div>
        <div class="bg-white rounded-xl border border-gray-100 p-5">
            <h3 class="font-semibold text-gray-700 mb-3">配置文件</h3>
            <ul class="text-sm text-gray-600 space-y-1.5">
                <li>📄 config.yml — 主配置</li>
                <li>🔒 secrets.yml — 密钥与凭据</li>
                <li>📁 config/development.yml — 开发环境覆盖</li>
                <li>📁 config/production.yml — 生产环境覆盖</li>
            </ul>
        </div>
    </div>
    """
    return HTMLResponse(html)
