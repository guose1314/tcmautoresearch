# -*- coding: utf-8 -*-
"""AI 助手对话引擎 — 意图识别、提示词构建与多轮会话管理。"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.llm.llm_gateway import generate_with_gateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 意图定义
# ---------------------------------------------------------------------------

INTENT_LITERATURE = "literature_search"
INTENT_HYPOTHESIS = "hypothesis_generation"
INTENT_EXPERIMENT = "experiment_design"
INTENT_WRITING = "paper_writing"
INTENT_GENERAL = "general_qa"

_INTENT_KEYWORDS: Dict[str, List[str]] = {
    INTENT_LITERATURE: [
        "文献",
        "论文",
        "检索",
        "搜索",
        "查找",
        "参考",
        "引用",
        "PubMed",
        "CNKI",
        "知网",
        "文章",
        "综述",
        "meta",
    ],
    INTENT_HYPOTHESIS: [
        "假说",
        "假设",
        "推测",
        "猜想",
        "机制",
        "可能",
        "为什么",
        "原因",
        "联系",
        "关联",
        "通路",
    ],
    INTENT_EXPERIMENT: [
        "实验",
        "设计",
        "方案",
        "对照",
        "样本",
        "统计",
        "随机",
        "盲法",
        "指标",
        "方法学",
        "protocol",
    ],
    INTENT_WRITING: [
        "论文",
        "撰写",
        "写作",
        "摘要",
        "引言",
        "讨论",
        "结论",
        "投稿",
        "期刊",
        "格式",
        "abstract",
    ],
}

_MAX_HISTORY_TURNS = 20

# ---------------------------------------------------------------------------
# System prompts per intent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: Dict[str, str] = {
    INTENT_LITERATURE: (
        "你是一位中医药文献检索专家。根据用户需求，给出检索策略建议、"
        "推荐关键词组合，并指出可能的高质量文献来源。"
    ),
    INTENT_HYPOTHESIS: (
        "你是一位中医药研究假说生成专家。基于用户提供的背景信息，"
        "运用中医理论与现代药理学知识，提出可检验的科研假说。"
    ),
    INTENT_EXPERIMENT: (
        "你是一位中医药实验设计顾问。根据研究假说，设计合理的实验方案，"
        "包括实验分组、样本量、观测指标和统计方法。"
    ),
    INTENT_WRITING: (
        "你是一位中医药学术论文写作助手。协助用户完善论文结构、"
        "润色学术语言、规范引用格式。"
    ),
    INTENT_GENERAL: (
        "你是中医智慧科研平台的 AI 助手，精通中医药理论与现代研究方法。"
        "用简洁专业的语言回答用户问题。"
    ),
}


class AssistantEngine:
    """AI 科研助手对话引擎。

    Parameters
    ----------
    llm_engine : object | None
        LLM 推理引擎，需具备 ``generate(prompt, system_prompt)`` 方法。
        为 ``None`` 时惰性加载 ``src.llm.llm_engine.LLMEngine``。
    research_pipeline : object | None
        研究管线实例，用于辅助文献检索和假说扩展。
    max_history_turns : int
        每个 session 保留的最大对话轮数。
    kg_rag : KGRAGService | None
        知识图谱增强检索服务，对话前自动注入图谱上下文。
    """

    def __init__(
        self,
        llm_engine: Optional[Any] = None,
        research_pipeline: Optional[Any] = None,
        max_history_turns: int = _MAX_HISTORY_TURNS,
        kg_rag: Optional[Any] = None,
    ) -> None:
        self._llm = llm_engine
        self._pipeline = research_pipeline
        self._max_turns = max_history_turns
        self._kg_rag = kg_rag
        self._history: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        # 记录最近一次 LLM 加载失败原因，便于上层（如 /api/analysis/distill）
        # 在返回 503 时把根因透出，避免被静默吞掉。
        self._last_llm_load_error: str = ""
        logger.info("AssistantEngine 初始化完成 (max_turns=%d)", max_history_turns)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        message: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """主对话方法。

        Parameters
        ----------
        message : str
            用户输入。
        session_id : str
            会话标识，用于维护独立的对话历史。
        context : dict | None
            附加上下文（当前研究项目信息、选中实体等）。

        Returns
        -------
        dict
            ``{"reply": str, "suggestions": list[str], "references": list[str],
               "intent": str, "session_id": str}``
        """
        context = context or {}
        intent = self._detect_intent(message)

        # 构建提示词
        prompt = self._build_prompt(intent, message, context, session_id)
        system_prompt = _SYSTEM_PROMPTS.get(intent, _SYSTEM_PROMPTS[INTENT_GENERAL])

        # 调用 LLM
        reply = self._call_llm(prompt, system_prompt)

        # 生成后续建议
        suggestions = self._generate_suggestions(intent, message, reply)

        # 提取参考信息
        references = self._extract_references(reply, context)

        # 更新对话历史
        self._append_history(session_id, "user", message)
        self._append_history(session_id, "assistant", reply)

        return {
            "reply": reply,
            "suggestions": suggestions,
            "references": references,
            "intent": intent,
            "session_id": session_id,
        }

    def get_history(self, session_id: str = "default") -> List[Dict[str, str]]:
        """返回指定会话的对话历史副本。"""
        return list(self._history.get(session_id, []))

    def clear_history(self, session_id: str = "default") -> None:
        """清空指定会话的对话历史。"""
        self._history.pop(session_id, None)

    # ------------------------------------------------------------------
    # Intent detection
    # ------------------------------------------------------------------

    def _detect_intent(self, message: str) -> str:
        """基于关键词匹配的意图识别。

        对每个意图统计命中关键词数，取得分最高者；
        若所有意图得分均为 0，返回 ``INTENT_GENERAL``。
        """
        scores: Dict[str, int] = {k: 0 for k in _INTENT_KEYWORDS}
        msg_lower = message.lower()
        for intent, keywords in _INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in msg_lower:
                    scores[intent] += 1

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] == 0:
            return INTENT_GENERAL
        return best

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        intent: str,
        message: str,
        context: Dict[str, Any],
        session_id: str,
    ) -> str:
        """构建发送给 LLM 的提示词（含历史摘要与上下文）。"""
        parts: List[str] = []

        # KG-RAG：自动检索知识图谱上下文
        if self._kg_rag is not None:
            try:
                rag_ctx = self._kg_rag.retrieve(message)
                rag_text = rag_ctx.format()
                if rag_text:
                    parts.append(f"【知识图谱参考】\n{rag_text}")
            except Exception as exc:
                logger.debug("KG-RAG 检索失败: %s", exc)

        # 上下文信息
        if context:
            ctx_lines = []
            if context.get("project_name"):
                ctx_lines.append(f"当前项目：{context['project_name']}")
            if context.get("entities"):
                ctx_lines.append(
                    f"相关实体：{', '.join(str(e) for e in context['entities'][:10])}"
                )
            if context.get("research_phase"):
                ctx_lines.append(f"研究阶段：{context['research_phase']}")
            if context.get("extra"):
                ctx_lines.append(f"补充信息：{context['extra']}")
            if ctx_lines:
                parts.append("【研究上下文】\n" + "\n".join(ctx_lines))

        # 对话历史摘要（最近 6 轮）
        history = self._history.get(session_id, [])
        recent = history[-12:]  # 6 轮 × 2 条
        if recent:
            hist_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}"
                for m in recent
            )
            parts.append(f"【对话历史】\n{hist_text}")

        # 意图提示
        intent_hint = {
            INTENT_LITERATURE: "请针对以下问题提供文献检索策略和建议。",
            INTENT_HYPOTHESIS: "请基于以下信息生成可检验的科研假说。",
            INTENT_EXPERIMENT: "请为以下研究需求设计实验方案。",
            INTENT_WRITING: "请协助完成以下学术写作任务。",
            INTENT_GENERAL: "请回答以下问题。",
        }
        parts.append(f"【任务】{intent_hint.get(intent, intent_hint[INTENT_GENERAL])}")
        parts.append(f"【用户提问】{message}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        """调用 LLM 引擎生成回复。"""
        engine = self._get_llm()
        if engine is None:
            return f"[AI 助手] 已收到您的问题，但 LLM 引擎尚未加载。\n提示词摘要：{prompt[:200]}…"
        try:
            result = generate_with_gateway(
                engine,
                prompt,
                system_prompt,
                prompt_version="assistant_engine.chat@v1",
                phase="assistant",
                purpose="assistant_chat",
                task_type="assistant_response",
                metadata={"prompt_name": "assistant_engine.chat"},
            )
            failure = next(
                (
                    warning
                    for warning in result.warnings
                    if warning.startswith("llm_generate_failed")
                ),
                "",
            )
            if failure:
                return f"[AI 助手] 抱歉，生成回复时出现错误：{failure}"
            return str(result.text or "")
        except Exception as exc:
            logger.exception("LLM 生成失败")
            return f"[AI 助手] 抱歉，生成回复时出现错误：{exc}"

    def _get_llm(self):
        """惰性获取 LLM 引擎。"""
        if self._llm is not None:
            return self._llm
        try:
            from src.infra.llm_service import get_llm_service

            svc = get_llm_service("assistant")
            svc.load()
            self._llm = svc
            self._last_llm_load_error = ""
            return svc
        except Exception as exc:
            # 加载失败时显式回滚，避免缓存未初始化引擎对象。
            self._llm = None
            self._last_llm_load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("无法加载 LLM 引擎: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Suggestions & references
    # ------------------------------------------------------------------

    def _generate_suggestions(self, intent: str, message: str, reply: str) -> List[str]:
        """根据意图和回复内容生成后续操作建议。"""
        suggestions_map: Dict[str, List[str]] = {
            INTENT_LITERATURE: [
                "查看检索结果详情",
                "扩展检索关键词",
                "导出文献列表",
            ],
            INTENT_HYPOTHESIS: [
                "进一步验证该假说",
                "设计实验方案",
                "查找相关文献支持",
            ],
            INTENT_EXPERIMENT: [
                "评估实验可行性",
                "调整样本量",
                "生成实验 Protocol",
            ],
            INTENT_WRITING: [
                "生成参考文献列表",
                "润色学术语言",
                "检查论文格式",
            ],
            INTENT_GENERAL: [
                "深入了解相关概念",
                "查看知识图谱",
                "开始新的研究课题",
            ],
        }
        return suggestions_map.get(intent, suggestions_map[INTENT_GENERAL])

    @staticmethod
    def _extract_references(reply: str, context: Dict[str, Any]) -> List[str]:
        """从回复和上下文中提取参考信息。"""
        refs: List[str] = []

        # 从上下文中获取已有引用
        if context.get("references"):
            refs.extend(str(r) for r in context["references"][:5])

        # 简单正则匹配回复中的引用标记
        # 匹配 [1], [2] 等编号引用
        numbered = re.findall(r"\[(\d+)\]", reply)
        if numbered:
            refs.append(f"回复中引用了 {len(set(numbered))} 篇文献")

        return refs

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _append_history(self, session_id: str, role: str, content: str) -> None:
        """向会话历史追加一条记录，超出上限时移除最早的一轮。"""
        self._history[session_id].append({"role": role, "content": content})
        # 每轮 2 条（user + assistant）
        max_messages = self._max_turns * 2
        while len(self._history[session_id]) > max_messages:
            # 移除最早的一轮（2 条）
            self._history[session_id].pop(0)
            self._history[session_id].pop(0)
