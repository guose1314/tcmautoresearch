# src/ai_assistant/assistant_service.py
"""
AssistantService — 统一 AI 科研助手服务

架构位置
--------
应用层的 AI 对话入口。合并原有的:
- ``src/ai_assistant/engine.py`` (占位实现)
- ``src/ai_assistant/assistant_engine.py`` (意图识别 + LLM 调用)

新增 KG-RAG 增强：对话前自动从 Neo4j 知识图谱检索相关子图，
注入 prompt context，让 AI 回答有领域知识支撑。

用法
----
::

    from src.ai_assistant.assistant_service import AssistantService

    svc = AssistantService(llm_gateway=gateway, kg_service=kg)
    result = svc.chat("柴胡疏肝散治疗抑郁症的机制是什么？")
    print(result["reply"])
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent definitions
# ---------------------------------------------------------------------------

INTENT_LITERATURE = "literature_search"
INTENT_HYPOTHESIS = "hypothesis_generation"
INTENT_EXPERIMENT = "experiment_design"
INTENT_WRITING = "paper_writing"
INTENT_KG_QUERY = "knowledge_graph_query"
INTENT_GENERAL = "general_qa"

_INTENT_KEYWORDS: Dict[str, List[str]] = {
    INTENT_LITERATURE: [
        "文献", "论文", "检索", "搜索", "查找", "参考", "引用",
        "PubMed", "CNKI", "知网", "文章", "综述", "meta",
    ],
    INTENT_HYPOTHESIS: [
        "假说", "假设", "推测", "猜想", "机制", "可能",
        "为什么", "原因", "联系", "关联", "通路",
    ],
    INTENT_EXPERIMENT: [
        "实验", "设计", "方案", "对照", "样本", "统计",
        "随机", "盲法", "指标", "方法学", "protocol",
    ],
    INTENT_WRITING: [
        "论文", "撰写", "写作", "摘要", "引言", "讨论",
        "结论", "投稿", "期刊", "格式", "abstract",
    ],
    INTENT_KG_QUERY: [
        "知识图谱", "图谱", "归经", "组成", "配伍", "方剂",
        "包含", "治疗什么", "有什么功效", "靶点", "通路",
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
    INTENT_KG_QUERY: (
        "你是中医知识图谱查询助手。基于知识图谱中的实体和关系数据，"
        "准确回答用户关于方剂、中药、证候、靶点、通路等问题。"
    ),
    INTENT_GENERAL: (
        "你是中医智慧科研平台的 AI 助手，精通中医药理论与现代研究方法。"
        "用简洁专业的语言回答用户问题。"
    ),
}

# ---------------------------------------------------------------------------
# Suggestion templates
# ---------------------------------------------------------------------------

_SUGGESTIONS: Dict[str, List[str]] = {
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
    INTENT_KG_QUERY: [
        "查看相关方剂",
        "探索靶点-通路关系",
        "发现知识缺口",
    ],
    INTENT_GENERAL: [
        "深入了解相关概念",
        "查看知识图谱",
        "开始新的研究课题",
    ],
}


class AssistantService:
    """统一 AI 科研助手服务。

    Parameters
    ----------
    llm_gateway : object | None
        LLM 统一网关，需具备 ``generate(prompt, system_prompt=...)`` 方法。
        为 ``None`` 时尝试自动创建。
    kg_service : KnowledgeGraphService | None
        知识图谱服务，用于 KG-RAG 增强。
    max_history_turns : int
        每个 session 保留的最大对话轮数。
    kg_rag_enabled : bool
        是否启用 KG-RAG 增强。
    """

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        kg_service: Optional[Any] = None,
        max_history_turns: int = _MAX_HISTORY_TURNS,
        kg_rag_enabled: bool = True,
    ) -> None:
        self._llm = llm_gateway
        self._kg = kg_service
        self._max_turns = max_history_turns
        self._kg_rag_enabled = kg_rag_enabled
        self._history: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        logger.info(
            "AssistantService 初始化完成 (max_turns=%d, kg_rag=%s)",
            max_history_turns,
            kg_rag_enabled,
        )

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
            会话标识。
        context : dict | None
            附加上下文（当前研究项目信息、选中实体等）。

        Returns
        -------
        dict
            ``{"reply": str, "suggestions": list[str], "references": list[str],
               "intent": str, "session_id": str, "kg_context": dict | None}``
        """
        start_time = time.monotonic()
        context = context or {}
        intent = self._detect_intent(message)

        # KG-RAG 增强：提取相关知识图谱上下文
        kg_context = None
        if self._kg_rag_enabled and self._kg is not None:
            kg_context = self._retrieve_kg_context(message, intent)

        # 构建提示词
        prompt = self._build_prompt(intent, message, context, session_id, kg_context)
        system_prompt = _SYSTEM_PROMPTS.get(intent, _SYSTEM_PROMPTS[INTENT_GENERAL])

        # 调用 LLM
        reply = self._call_llm(prompt, system_prompt)

        # 生成后续建议
        suggestions = _SUGGESTIONS.get(intent, _SUGGESTIONS[INTENT_GENERAL])

        # 提取参考信息
        references = self._extract_references(reply, context)

        # 更新对话历史
        self._append_history(session_id, "user", message)
        self._append_history(session_id, "assistant", reply)

        elapsed = time.monotonic() - start_time
        logger.info("AssistantService.chat 完成 (intent=%s, %.2fs)", intent, elapsed)

        return {
            "reply": reply,
            "suggestions": suggestions,
            "references": references,
            "intent": intent,
            "session_id": session_id,
            "kg_context": kg_context,
        }

    def answer_with_evidence(self, question: str) -> Dict[str, Any]:
        """基于知识图谱证据回答问题。

        直接查询知识图谱，将结果注入 LLM 上下文后生成回答。

        Returns
        -------
        dict
            ``{"answer": str, "evidence": list[dict], "cypher": str}``
        """
        evidence: List[Dict[str, Any]] = []
        cypher = ""

        if self._kg is not None:
            try:
                kg_result = self._kg.query_natural_language(question)
                if kg_result.success:
                    evidence = kg_result.records
                    cypher = kg_result.cypher
            except Exception as exc:
                logger.warning("KG 查询失败: %s", exc)

        # 构建带证据的提示词
        evidence_text = ""
        if evidence:
            evidence_text = "\n\n【知识图谱查询结果】\n"
            for i, rec in enumerate(evidence[:10], 1):
                evidence_text += f"{i}. {rec}\n"

        prompt = f"请根据以下知识图谱数据回答问题。\n\n问题：{question}{evidence_text}"
        system_prompt = _SYSTEM_PROMPTS[INTENT_KG_QUERY]

        answer = self._call_llm(prompt, system_prompt)

        return {
            "answer": answer,
            "evidence": evidence,
            "cypher": cypher,
        }

    def suggest_next_step(self, session_id: str = "default") -> str:
        """基于对话历史建议下一步研究行动。"""
        history = self._history.get(session_id, [])
        if not history:
            return "请先提出一个研究问题，我将协助您规划下一步。"

        recent = history[-6:]
        summary = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:150]}"
            for m in recent
        )

        prompt = (
            f"以下是最近的对话记录：\n{summary}\n\n"
            "请基于以上对话，建议研究者下一步最应该做什么（简洁、可执行）。"
        )
        return self._call_llm(prompt, _SYSTEM_PROMPTS[INTENT_GENERAL])

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
        """基于关键词匹配的意图识别。"""
        scores: Dict[str, int] = {k: 0 for k in _INTENT_KEYWORDS}
        msg_lower = message.lower()
        for intent, keywords in _INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in msg_lower:
                    scores[intent] += 1

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return INTENT_GENERAL
        return best

    # ------------------------------------------------------------------
    # KG-RAG context retrieval
    # ------------------------------------------------------------------

    def _retrieve_kg_context(
        self, message: str, intent: str
    ) -> Optional[Dict[str, Any]]:
        """从知识图谱检索与用户问题相关的上下文。"""
        if self._kg is None:
            return None

        try:
            # 提取潜在的实体名称（简单启发式：中文名词短语）
            entities = self._extract_entity_mentions(message)

            context: Dict[str, Any] = {"entities": entities, "subgraphs": [], "gaps": []}

            for entity in entities[:3]:  # 限制子图查询数量
                subgraph = self._kg.get_subgraph(entity, depth=1)
                if subgraph.nodes:
                    context["subgraphs"].append({
                        "center": entity,
                        "nodes": len(subgraph.nodes),
                        "edges": len(subgraph.edges),
                        "data": {
                            "nodes": subgraph.nodes[:20],
                            "edges": subgraph.edges[:30],
                        },
                    })

                # 对假说意图额外查找知识缺口
                if intent == INTENT_HYPOTHESIS:
                    gaps = self._kg.find_gaps(entity)
                    context["gaps"].extend(
                        {"entity": g.entity, "type": g.gap_type, "desc": g.description}
                        for g in gaps[:5]
                    )

            return context if (context["subgraphs"] or context["gaps"]) else None
        except Exception as exc:
            logger.warning("KG-RAG 上下文检索失败: %s", exc)
            return None

    @staticmethod
    def _extract_entity_mentions(text: str) -> List[str]:
        """从文本中提取可能的实体名称（启发式）。

        识别常见中医实体模式：
        - 中药名（2-4 字）
        - 方剂名（含 "汤"/"散"/"丸"/"丹"/"膏" 后缀）
        - 证候名（含 "证"/"症" 后缀）
        """
        entities: List[str] = []

        # 方剂名：X汤/X散/X丸/X丹/X膏
        formulas = re.findall(r'[\u4e00-\u9fff]{2,8}[汤散丸丹膏]', text)
        entities.extend(formulas)

        # 证候名：X证/X症
        syndromes = re.findall(r'[\u4e00-\u9fff]{2,6}[证症]', text)
        entities.extend(syndromes)

        # 去重保持顺序
        seen = set()
        unique: List[str] = []
        for e in entities:
            if e not in seen:
                seen.add(e)
                unique.append(e)

        return unique

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        intent: str,
        message: str,
        context: Dict[str, Any],
        session_id: str,
        kg_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建发送给 LLM 的提示词。"""
        parts: List[str] = []

        # KG-RAG 上下文
        if kg_context:
            kg_text_parts: List[str] = []
            for sg in kg_context.get("subgraphs", []):
                kg_text_parts.append(f"· 实体 '{sg['center']}' 的知识子图：{sg['nodes']} 个节点、{sg['edges']} 条边")
                # 加入部分节点和边信息
                if sg.get("data", {}).get("edges"):
                    for edge in sg["data"]["edges"][:10]:
                        kg_text_parts.append(
                            f"  - {edge.get('source', '?')} --[{edge.get('type', '?')}]--> {edge.get('target', '?')}"
                        )
            for gap in kg_context.get("gaps", []):
                kg_text_parts.append(f"· 知识缺口：{gap['desc']}")
            if kg_text_parts:
                parts.append("【知识图谱上下文】\n" + "\n".join(kg_text_parts))

        # 研究上下文
        if context:
            ctx_lines = []
            if context.get("project_name"):
                ctx_lines.append(f"当前项目：{context['project_name']}")
            if context.get("entities"):
                ctx_lines.append(f"相关实体：{', '.join(str(e) for e in context['entities'][:10])}")
            if context.get("research_phase"):
                ctx_lines.append(f"研究阶段：{context['research_phase']}")
            if context.get("extra"):
                ctx_lines.append(f"补充信息：{context['extra']}")
            if ctx_lines:
                parts.append("【研究上下文】\n" + "\n".join(ctx_lines))

        # 对话历史摘要（最近 6 轮）
        history = self._history.get(session_id, [])
        recent = history[-12:]
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
            INTENT_KG_QUERY: "请基于知识图谱上下文回答以下问题。",
            INTENT_GENERAL: "请回答以下问题。",
        }
        parts.append(f"【任务】{intent_hint.get(intent, intent_hint[INTENT_GENERAL])}")
        parts.append(f"【用户提问】{message}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        """调用 LLM 生成回复。"""
        engine = self._get_llm()
        if engine is None:
            return f"[AI 助手] 已收到您的问题，但 LLM 引擎尚未加载。\n提示词摘要：{prompt[:200]}…"
        try:
            return engine.generate(prompt, system_prompt=system_prompt)
        except Exception as exc:
            logger.exception("LLM 生成失败")
            return f"[AI 助手] 抱歉，生成回复时出现错误：{exc}"

    def _get_llm(self) -> Optional[Any]:
        """惰性获取 LLM 网关。"""
        if self._llm is not None:
            return self._llm
        try:
            from src.infrastructure.llm_gateway import LLMGateway
            self._llm = LLMGateway()
            self._llm.load()
            return self._llm
        except Exception as exc:
            logger.warning("无法加载 LLM 网关: %s", exc)
            return None

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _append_history(self, session_id: str, role: str, content: str) -> None:
        """追加对话记录，超过限制时截断。"""
        self._history[session_id].append({"role": role, "content": content})
        max_items = self._max_turns * 2
        if len(self._history[session_id]) > max_items:
            self._history[session_id] = self._history[session_id][-max_items:]

    # ------------------------------------------------------------------
    # References extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_references(reply: str, context: Dict[str, Any]) -> List[str]:
        """从回复和上下文中提取参考信息。"""
        refs: List[str] = []
        if context.get("references"):
            refs.extend(str(r) for r in context["references"][:5])
        numbered = re.findall(r'\[(\d+)\]', reply)
        if numbered:
            refs.append(f"引用编号: {', '.join(numbered[:10])}")
        return refs
