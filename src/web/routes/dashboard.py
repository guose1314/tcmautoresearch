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

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
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
# Dashboard: Stats
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/stats", response_class=HTMLResponse)
async def dashboard_stats(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    corpus = _count_corpus_files()
    outputs = _count_output_files()

    # 尝试获取词典规模
    entity_count = "—"
    try:
        from src.data.tcm_lexicon import get_lexicon_stats

        stats = get_lexicon_stats()
        entity_count = f"{stats.get('total', 0):,}"
    except Exception:
        pass

    html = (
        _card("古籍文献", str(corpus), "gray-800")
        + _card("知识实体", entity_count, "gray-800")
        + _card("输出文件", str(outputs), "gray-800")
        + _card("系统状态", "运行中", "emerald-600")
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Dashboard: Quality
# ---------------------------------------------------------------------------


@router.get("/api/dashboard/quality", response_class=HTMLResponse)
async def dashboard_quality(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    html = """
    <div class="px-5 py-4 border-b border-gray-100">
        <h2 class="font-semibold text-gray-800">质量评分概览</h2>
    </div>
    <div class="px-5 py-6">
        <div class="flex items-center gap-6">
            <div class="w-20 h-20 rounded-full border-4 border-emerald-500
                        flex items-center justify-center">
                <span class="text-xl font-bold text-emerald-700">95</span>
            </div>
            <div class="text-sm text-gray-500 space-y-1.5">
                <p>完整性：<span class="text-gray-700 font-medium">0.95</span></p>
                <p>准确性：<span class="text-gray-700 font-medium">0.92</span></p>
                <p>可追溯性：<span class="text-gray-700 font-medium">0.95</span></p>
                <p>标准符合度：<span class="text-gray-700 font-medium">0.98</span></p>
            </div>
        </div>
        <p class="text-xs text-gray-400 mt-4">
            基于 T/C IATCM 098-2023 标准评估 · 数据来源：config.yml academic 配置
        </p>
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
    html = """
    <div class="px-5 py-8 text-center text-sm text-gray-400">
        暂无进行中的项目，点击 "科研项目" 创建新项目
    </div>
    """
    return HTMLResponse(html)


@router.get("/api/projects", response_class=HTMLResponse)
async def projects_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    html = f"""
    {_section_header("科研项目", "管理和跟踪您的中医研究课题")}
    <div class="grid gap-4">
        <div class="border border-dashed border-gray-300 rounded-xl p-8
                    flex flex-col items-center justify-center cursor-pointer
                    hover:border-emerald-400 hover:bg-emerald-50/30 transition group">
            <span class="text-4xl mb-3 group-hover:scale-110 transition-transform">➕</span>
            <p class="text-sm font-medium text-gray-600 group-hover:text-emerald-700">
                创建新研究课题
            </p>
            <p class="text-xs text-gray-400 mt-1">
                使用 POST /api/research/create 接口
            </p>
        </div>
    </div>
    <div class="mt-6">
        {_empty_state("🔬", "暂无研究项目",
                       "创建第一个研究课题以开始系统化中医古籍研究")}
    </div>
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
    {_section_header("知识图谱", "可视化中医知识关系网络")}
    {_empty_state("🕸️", "知识图谱可视化",
                   "运行文本分析后，使用 GET /api/analysis/graph/{{research_id}} 获取图谱数据。"
                   "也可通过 AI 助手对话生成知识图谱。")}
    <div class="mt-6 p-4 bg-gray-50 rounded-lg">
        <h3 class="text-sm font-semibold text-gray-600 mb-2">支持的图谱类型</h3>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <div class="bg-white rounded-lg p-3 border border-gray-100 text-center">
                <span class="text-2xl block mb-1">🌿</span>药物关系图
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-100 text-center">
                <span class="text-2xl block mb-1">📋</span>方剂组成图
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-100 text-center">
                <span class="text-2xl block mb-1">🔄</span>证治关系图
            </div>
            <div class="bg-white rounded-lg p-3 border border-gray-100 text-center">
                <span class="text-2xl block mb-1">📖</span>文献引用图
            </div>
        </div>
    </div>
    """
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Analysis Tools
# ---------------------------------------------------------------------------


@router.get("/api/analysis/tools", response_class=HTMLResponse)
async def analysis_tools_page(
    user: Dict[str, Any] = Depends(get_current_user),
) -> HTMLResponse:
    tools = [
        ("📝", "文本处理链", "古籍预处理 → 实体抽取 → 语义建模", "POST /api/analysis/text"),
        ("💊", "方剂综合分析", "方剂配伍分析与综合评分", "POST /api/analysis/formula"),
        ("🕸️", "知识图谱生成", "从分析结果生成可视化图谱", "GET /api/analysis/graph/{id}"),
    ]
    cards = ""
    for icon, title, desc, endpoint in tools:
        cards += f"""
        <div class="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md
                    hover:border-emerald-200 transition">
            <span class="text-3xl block mb-3">{icon}</span>
            <h3 class="font-semibold text-gray-800 mb-1">{title}</h3>
            <p class="text-sm text-gray-500 mb-3">{desc}</p>
            <code class="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">{endpoint}</code>
        </div>
        """

    html = f"""
    {_section_header("分析工具", "中医古籍智能分析工具箱")}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">{cards}</div>
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
    # 读取 config.yml 的基本信息
    sys_info = {}
    try:
        import yaml

        with open("config.yml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sys_info = cfg.get("system", {})
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
