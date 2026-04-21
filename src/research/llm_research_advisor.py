# src/research/llm_research_advisor.py
"""
LLMResearchAdvisor — 让 Qwen1.5-7B 深度参与六大研究阶段的推理决策（指令 I-01）。

设计思路：
  - 每个研究阶段（observe/hypothesis/experiment/analyze/publish/reflect）
    均有专属 Prompt 模板，驱动 Qwen 输出结构化 JSON 结论。
  - 集成 HyDE（I-04）：先生成假设文档再检索，提升 RAG 精度。
  - 集成 Self-RAG（I-09）：对生成结果进行自我批评，过滤低质量输出。
  - 降级策略：LLM 或 RAG 不可用时返回空结论字典，主流程不中断。

参考：
  - HyDE: Gao et al. (2022) https://arxiv.org/abs/2212.10496
  - Self-RAG: Asai et al. (2023) https://arxiv.org/abs/2310.11511
  - RAPTOR: Sarthi et al. (2024) https://arxiv.org/abs/2401.18059
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.llm.llm_engine import LLMEngine
    from src.learning.rag_service import RAGService

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AdvisoryResult:
    """LLMResearchAdvisor 单次推理结果。"""

    phase: str
    conclusion: str = ""
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source_refs: List[str] = field(default_factory=list)
    llm_raw: str = ""
    retrieval_docs: List[Dict[str, Any]] = field(default_factory=list)
    is_grounded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "conclusion": self.conclusion,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "source_refs": self.source_refs,
            "llm_raw": self.llm_raw,
            "is_grounded": self.is_grounded,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 模板
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_ROLE = (
    "你是一位杰出的中医学教授兼资深文献研究专家，"
    "精通《伤寒论》《本草纲目》等经典著作，"
    "擅长方剂配伍分析、文献考证与中医科研设计。"
    "回答必须严谨、有据可查，不得编造文献。"
)

_PHASE_PROMPTS: Dict[str, str] = {
    "observe": (
        "【文献考证任务】\n"
        "请仔细阅读以下古籍/文献片段，完成以下分析：\n"
        "1. 核心处方名称及组成（药味、剂量）\n"
        "2. 主治病证（证型、症状）\n"
        "3. 学术渊源（最早出处、历代沿革）\n"
        "4. 用药特点与配伍规律\n\n"
        "文献片段：\n{text}\n\n"
        "请以 JSON 格式输出，字段：conclusion（总结）、evidence（证据列表）、"
        "confidence（0-1 可信度）、source_refs（参考文献列表）。\n"
        "JSON："
    ),
    "hypothesis": (
        "【假设生成任务】\n"
        "基于以下知识缺口分析，生成 3 条具体可验证的中医研究假设：\n\n"
        "知识缺口：\n{gaps}\n\n"
        "要求每条假设包含：\n"
        "- 假设陈述（可操作、可检验）\n"
        "- 理论依据（中医经典支撑）\n"
        "- 验证路径（实验/文献方法）\n"
        "- 预期意义（学术价值）\n\n"
        "请以 JSON 格式输出，字段：conclusion（核心假设）、evidence（理论依据）、"
        "confidence（0-1 可行性评分）、source_refs（参考方向）。\n"
        "JSON："
    ),
    "experiment": (
        "【实验设计任务】\n"
        "请为以下研究假设设计一个严谨的实验或文献研究方案：\n\n"
        "研究假设：\n{hypothesis}\n\n"
        "设计要求：\n"
        "1. 研究类型（RCT/观察性/文献系统评价）\n"
        "2. 主要评价指标\n"
        "3. 纳入/排除标准\n"
        "4. 统计分析方法\n"
        "5. 预期样本量\n\n"
        "请以 JSON 格式输出，字段：conclusion（方案概述）、evidence（设计依据）、"
        "confidence（0-1 科学性评分）、source_refs（参考标准）。\n"
        "JSON："
    ),
    "analyze": (
        "【文献分析考证任务】\n"
        "请对以下研究分析结果进行中医文献考证，指出历史源流与学术价值：\n\n"
        "分析数据：\n{results}\n\n"
        "考证维度：\n"
        "1. 历史文献溯源（最早记载、演变过程）\n"
        "2. 各家学说比较（不同医家观点）\n"
        "3. 现代研究印证（与现代药理的联系）\n"
        "4. 学术创新价值（是否填补研究空白）\n\n"
        "请以 JSON 格式输出，字段：conclusion（考证结论）、evidence（文献证据）、"
        "confidence（0-1 考证可信度）、source_refs（引用文献）。\n"
        "JSON："
    ),
    "publish": (
        "【论文撰写任务】\n"
        "请将以下研究数据整理为 IMRD 格式的论文摘要（中英文各一份）：\n\n"
        "研究数据：\n{data}\n\n"
        "摘要要求（每部分 2-3 句）：\n"
        "- Introduction：研究背景与目的\n"
        "- Methods：研究设计与方法\n"
        "- Results：主要发现\n"
        "- Discussion：结论与局限性\n"
        "- Innovation：创新点\n\n"
        "请以 JSON 格式输出，字段：conclusion（摘要正文）、evidence（主要数据支撑）、"
        "confidence（0-1 研究质量评分）、source_refs（关键参考文献）。\n"
        "JSON："
    ),
    "reflect": (
        "【研究反思任务】\n"
        "请对本次研究周期进行批判性反思与总结：\n\n"
        "研究摘要：\n{summary}\n\n"
        "反思维度：\n"
        "1. 主要发现与突破\n"
        "2. 研究局限与偏差\n"
        "3. 未解决的科学问题\n"
        "4. 后续研究方向建议\n"
        "5. 方法论改进建议\n\n"
        "请以 JSON 格式输出，字段：conclusion（核心反思）、evidence（具体问题列表）、"
        "confidence（0-1 反思深度评分）、source_refs（参考改进方向）。\n"
        "JSON："
    ),
}

# HyDE 假设文档生成 Prompt
_HYDE_PROMPT = (
    "你是中医文献专家。请为以下查询写一段简短的参考答案（约80字中文），"
    "即使不确定也请基于中医理论给出最可能的回答：\n\n"
    "查询：{query}\n\n"
    "参考答案（直接输出，不要解释）："
)


# ─────────────────────────────────────────────────────────────────────────────
# 主类
# ─────────────────────────────────────────────────────────────────────────────


class LLMResearchAdvisor:
    """
    基于 Qwen1.5-7B-Chat 的中医研究顾问。

    功能：
      - ``advise()``           — 针对指定研究阶段进行 LLM 推理，返回结构化结论
      - ``hyde_retrieve()``    — HyDE 增强检索（先生成假设文档再检索）
      - ``self_rag_critique()``— Self-RAG 自我批评（评估生成质量）

    用法::

        from src.research.llm_research_advisor import LLMResearchAdvisor
        advisor = LLMResearchAdvisor(llm_engine=engine, rag_service=rag)
        result = advisor.advise("observe", {"text": "黄芪性温，味甘…"})
        print(result.conclusion)
    """

    # LLM 生成参数
    _MAX_TOKENS = 512
    _TEMPERATURE = 0.3  # 低温度保证输出稳定性

    def __init__(
        self,
        llm_engine: Optional["LLMEngine"] = None,
        rag_service: Optional["RAGService"] = None,
    ) -> None:
        """
        Args:
            llm_engine: LLMEngine 实例（Qwen1.5-7B）；为 None 时降级返回空结论。
            rag_service: RAGService 实例；为 None 时跳过 RAG 检索。
        """
        self._llm = llm_engine
        self._rag = rag_service

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def advise(
        self,
        phase: str,
        context: Dict[str, Any],
        use_rag: bool = True,
        use_hyde: bool = True,
    ) -> AdvisoryResult:
        """
        针对指定研究阶段执行 LLM 推理（指令 I-01 核心方法）。

        Args:
            phase: 阶段名称（observe/hypothesis/experiment/analyze/publish/reflect）。
            context: 阶段上下文数据，具体 key 视阶段而定：
                     observe   → "text"
                     hypothesis→ "gaps"
                     experiment→ "hypothesis"
                     analyze   → "results"
                     publish   → "data"
                     reflect   → "summary"
            use_rag: 是否先检索相关古籍增强上下文。
            use_hyde: 是否使用 HyDE 增强检索。

        Returns:
            AdvisoryResult 包含结构化推理结论。
        """
        if self._llm is None:
            logger.debug("LLMResearchAdvisor: LLM 不可用，返回空结论（phase=%s）", phase)
            return AdvisoryResult(phase=phase)

        # 1. RAG 检索增强上下文
        retrieval_docs: List[Dict[str, Any]] = []
        if use_rag and self._rag is not None:
            query = self._build_rag_query(phase, context)
            if query:
                if use_hyde:
                    retrieval_docs = self.hyde_retrieve(query, k=3)
                else:
                    retrieval_docs = self._rag.retrieve(query, k=3)

        # 2. 构建最终 Prompt
        prompt = self._build_prompt(phase, context, retrieval_docs)
        if not prompt:
            logger.warning("LLMResearchAdvisor: 未知阶段 %s，返回空结论", phase)
            return AdvisoryResult(phase=phase)

        # 3. LLM 生成
        raw_output = self._safe_generate(prompt)

        # 4. 解析 JSON 结论
        result = self._parse_json_result(raw_output, phase)
        result.retrieval_docs = retrieval_docs
        result.llm_raw = raw_output

        # 5. Self-RAG 可信度评估
        if retrieval_docs and result.conclusion:
            critique = self.self_rag_critique(result.conclusion, retrieval_docs)
            result.is_grounded = critique.get("is_grounded", False)
            if not result.is_grounded:
                logger.debug("LLMResearchAdvisor: 结论未获文献支撑（phase=%s）", phase)

        return result

    def hyde_retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        HyDE 增强检索（指令 I-04 集成）。

        先让 LLM 生成"假设答案"，用假设答案的 embedding 做向量检索，
        比直接用 query embedding 精度更高。

        Args:
            query: 检索查询文本。
            k: 返回文档数量。

        Returns:
            相关文档列表（格式同 RAGService.retrieve()）。
        """
        if self._rag is None:
            return []

        # 若 RAGService 支持 HyDE，直接委托
        if hasattr(self._rag, "retrieve") and self._llm is not None:
            try:
                # 尝试调用支持 use_hyde 参数的 retrieve
                return self._rag.retrieve(query, k=k, use_hyde=True, llm=self._llm)
            except TypeError:
                pass  # 旧版 RAGService 不支持 use_hyde 参数，回退

        # 回退：手动生成假设文档
        if self._llm is not None:
            hyde_prompt = _HYDE_PROMPT.format(query=query)
            try:
                hypothetical_doc = self._llm.generate(
                    hyde_prompt,
                    max_tokens=100,
                    temperature=0.5,
                )
                if hypothetical_doc.strip():
                    return self._rag.retrieve(hypothetical_doc, k=k)
            except Exception as exc:
                logger.debug("HyDE 假设文档生成失败，回退普通检索: %s", exc)

        return self._rag.retrieve(query, k=k)

    def self_rag_critique(
        self,
        answer: str,
        source_docs: List[Dict[str, Any]],
    ) -> Dict[str, bool]:
        """
        Self-RAG 自我批评（指令 I-09 集成）。

        评估生成内容是否有文献支撑（[IsSUP] 令牌逻辑）。

        Args:
            answer: LLM 生成的回答文本。
            source_docs: RAG 检索到的参考文档列表。

        Returns:
            ``{"is_relevant": bool, "is_grounded": bool, "is_useful": bool}``
        """
        if not source_docs or not answer:
            return {"is_relevant": False, "is_grounded": False, "is_useful": bool(answer)}

        if self._llm is None:
            # 无 LLM 时用关键词匹配做简单判断
            combined_src = " ".join(d.get("text", "") for d in source_docs[:3])
            answer_words = set(answer[:200].replace("，", " ").replace("。", " ").split())
            src_words = set(combined_src[:500].replace("，", " ").replace("。", " ").split())
            overlap = len(answer_words & src_words)
            is_grounded = overlap >= 3
            return {
                "is_relevant": bool(source_docs),
                "is_grounded": is_grounded,
                "is_useful": bool(answer),
            }

        critique_prompt = (
            "请判断以下回答是否有文献支撑（只回答 YES 或 NO）：\n\n"
            f"回答：{answer[:200]}\n\n"
            f"参考文献：{source_docs[0].get('text', '')[:200]}\n\n"
            "是否有文献支撑（YES/NO）："
        )
        try:
            verdict = self._llm.generate(critique_prompt, max_tokens=5, temperature=0.0)
            is_grounded = "YES" in verdict.upper()
        except Exception:
            is_grounded = False

        return {
            "is_relevant": True,
            "is_grounded": is_grounded,
            "is_useful": bool(answer),
        }

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        phase: str,
        context: Dict[str, Any],
        retrieval_docs: List[Dict[str, Any]],
    ) -> str:
        """构建最终 Prompt（模板 + RAG 上下文 + 阶段数据）。"""
        template = _PHASE_PROMPTS.get(phase)
        if not template:
            return ""

        # 将上下文数据填充到模板（所有 key 均可选）
        safe_context: Dict[str, str] = {
            "text": str(context.get("text", context.get("corpus", "")))[:800],
            "gaps": str(context.get("gaps", context.get("knowledge_gaps", "")))[:600],
            "hypothesis": str(context.get("hypothesis", ""))[:600],
            "results": self._truncate_dict(context.get("results", context.get("analysis_results", {})))[:600],
            "data": self._truncate_dict(context.get("data", context))[:600],
            "summary": str(context.get("summary", ""))[:600],
        }

        try:
            phase_content = template.format(**safe_context)
        except KeyError:
            phase_content = template

        # 在 Prompt 头部追加 RAG 检索到的参考资料
        if retrieval_docs:
            rag_context = "\n".join(
                f"[参考{i + 1}] {d.get('text', '')[:200]}"
                for i, d in enumerate(retrieval_docs[:3])
            )
            phase_content = (
                f"【相关古籍参考资料】\n{rag_context}\n\n"
                f"【分析任务】\n{phase_content}"
            )

        return phase_content

    def _build_rag_query(self, phase: str, context: Dict[str, Any]) -> str:
        """提取当前阶段最适合检索的查询文本。"""
        mapping = {
            "observe": "text",
            "hypothesis": "gaps",
            "experiment": "hypothesis",
            "analyze": "results",
            "publish": "summary",
            "reflect": "summary",
        }
        key = mapping.get(phase, "text")
        raw = context.get(key, "")
        if isinstance(raw, dict):
            return str(raw)[:100]
        return str(raw)[:100]

    def _safe_generate(self, prompt: str) -> str:
        """调用 LLM 生成，失败返回空字符串。"""
        if self._llm is None:
            return ""
        try:
            return self._llm.generate(
                prompt,
                max_tokens=self._MAX_TOKENS,
                temperature=self._TEMPERATURE,
                system=_SYSTEM_ROLE,
            )
        except Exception as exc:
            logger.warning("LLMResearchAdvisor: LLM 生成失败: %s", exc)
            return ""

    @staticmethod
    def _parse_json_result(raw: str, phase: str) -> AdvisoryResult:
        """从 LLM 输出中解析 JSON 格式的结论。"""
        result = AdvisoryResult(phase=phase, llm_raw=raw)
        if not raw:
            return result

        # 尝试从输出中提取 JSON 块
        json_text = raw.strip()
        # 有时 LLM 会在 JSON 前后包裹 ```json ... ``` 代码块
        if "```" in json_text:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
            if m:
                json_text = m.group(1)
        # 提取第一个 { ... } 块
        if not json_text.startswith("{"):
            brace_start = json_text.find("{")
            if brace_start != -1:
                json_text = json_text[brace_start:]

        try:
            data = json.loads(json_text)
            result.conclusion = str(data.get("conclusion", ""))
            evidence_raw = data.get("evidence", [])
            if isinstance(evidence_raw, list):
                result.evidence = [str(e) for e in evidence_raw[:10]]
            elif isinstance(evidence_raw, str):
                result.evidence = [evidence_raw]
            result.confidence = float(data.get("confidence", 0.5))
            refs_raw = data.get("source_refs", [])
            if isinstance(refs_raw, list):
                result.source_refs = [str(r) for r in refs_raw[:5]]
            elif isinstance(refs_raw, str):
                result.source_refs = [refs_raw]
        except (json.JSONDecodeError, ValueError):
            # JSON 解析失败时将整个输出作为 conclusion
            result.conclusion = raw[:500].strip()
            result.confidence = 0.3

        return result

    @staticmethod
    def _truncate_dict(obj: Any, max_len: int = 500) -> str:
        """将任意对象转为截断字符串。"""
        if isinstance(obj, dict):
            try:
                text = json.dumps(obj, ensure_ascii=False, default=str)
            except Exception:
                text = str(obj)
        else:
            text = str(obj)
        return text[:max_len]
