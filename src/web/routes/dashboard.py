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
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from src.web.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATA_DIR = Path("data")
_OUTPUT_DIR = Path("output")


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


# ---------------------------------------------------------------------------
# Helpers – research output scanning
# ---------------------------------------------------------------------------


def _scan_research_sessions() -> List[Dict[str, Any]]:
    """扫描 output/ 下的 research_session_*.json，返回各会话摘要（按时间倒序）。"""
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
    sessions = _scan_research_sessions()

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
        {_card("🔬 研究课题", str(total_sessions), "blue-600")}
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
    sessions = _scan_research_sessions()
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
                <p>研究课题完成 <span class="text-gray-700 font-medium">{completed_sessions}</span> / {len(sessions)}</p>
            </div>
        </div>
        <p class="text-xs text-gray-400 mt-4">
            动态评估 · 基于知识实体、关系、论文产出、课题完成度综合加权
        </p>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Dashboard: Research Workflow — 科研论文书写流程
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/research-workflow", response_class=HTMLResponse)
async def dashboard_research_workflow(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    """科研论文生成管线流程可视化面板。"""
    sessions = _scan_research_sessions()
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
        ("experiment", "🧪 实验验证", "方剂分析、实体抽取、关系验证", "purple"),
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
                <span>课题 <strong class="text-blue-600">{total}</strong></span>
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
                    <div class="flex justify-between"><span class="text-gray-500">总研究课题</span><span class="font-medium text-gray-800">{total}</span></div>
                    <div class="flex justify-between"><span class="text-gray-500">已完成课题</span><span class="font-medium text-emerald-600">{completed}</span></div>
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
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    sessions = _scan_research_sessions()[:8]  # 最近 8 条
    if not sessions:
        return HTMLResponse(
            '<div class="px-5 py-8 text-center text-sm text-gray-400">'
            '暂无研究记录 — 通过 API 或 AI 助手启动研究课题</div>'
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
        rows += f"""
        <div class="px-5 py-3 hover:bg-gray-50 transition">
            <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-gray-800 truncate">{title}{paper_badge}</p>
                    <div class="mt-1 flex flex-wrap gap-1">{phases_tags}</div>
                </div>
                <span class="text-xs {cls} whitespace-nowrap">{icon} {label}</span>
            </div>
        </div>"""

    return HTMLResponse(rows)


@router.get("/api/projects", response_class=HTMLResponse)
async def projects_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    sessions = _scan_research_sessions()
    imrd = _count_imrd_reports()
    total = len(sessions)
    completed = sum(1 for s in sessions if s["status"] == "completed")

    _STATUS_MAP = {
        "completed": ("✅", "已完成", "bg-emerald-50 text-emerald-700"),
        "active": ("🔄", "进行中", "bg-blue-50 text-blue-700"),
        "running": ("🔄", "运行中", "bg-blue-50 text-blue-700"),
        "failed": ("❌", "失败", "bg-red-50 text-red-600"),
        "pending": ("⏳", "待执行", "bg-amber-50 text-amber-700"),
    }

    project_cards = ""
    for s in sessions:
        icon, label, cls = _STATUS_MAP.get(s["status"], ("❓", s["status"], "bg-gray-50 text-gray-500"))
        phases_html = " ".join(
            f'<span class="inline-block px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-100 text-gray-600">{p}</span>'
            for p in s["phases"]
        ) or '<span class="text-xs text-gray-300">无阶段</span>'
        paper_badge = '<span class="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded ml-1">📝 论文</span>' if s["has_reports"] else ""
        title = s["title"][:70]
        project_cards += f"""
        <div class="bg-white rounded-xl border border-gray-100 p-4 hover:shadow-md transition">
            <div class="flex items-start justify-between mb-2">
                <h3 class="text-sm font-semibold text-gray-800 flex-1 truncate">{title}{paper_badge}</h3>
                <span class="text-[10px] font-medium px-2 py-0.5 rounded-full {cls} ml-2 whitespace-nowrap">{icon} {label}</span>
            </div>
            <div class="flex flex-wrap gap-1 mb-2">{phases_html}</div>
            <p class="text-[10px] text-gray-400 truncate">cycle: {s['cycle_id'][:30]}</p>
        </div>"""

    if not project_cards:
        project_cards = _empty_state("🔬", "暂无研究课题",
            "使用 AI 助手或 POST /api/research/create 接口创建研究课题")

    html = f"""
    {_section_header("科研项目", f"共 {total} 个研究课题 · 已完成 {completed} · 论文产出 {imrd['total']} 份")}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {_card("🔬 研究课题", str(total), "blue-600")}
        {_card("✅ 已完成", str(completed), "emerald-600")}
        {_card("📝 论文输出", str(imrd["total"]), "purple-600")}
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">{project_cards}</div>
    """
    return HTMLResponse(html)


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
