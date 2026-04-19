# -*- coding: utf-8 -*-
"""科研建议模块 — 假说生成、实验设计与创新性评估。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.infra.prompt_registry import (
    call_registered_prompt,
    parse_registered_output,
    render_prompt,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_HYPOTHESIS_SYSTEM = (
    "你是一位中医药科研方法学专家。请根据给定主题和已有文献摘要，"
    "生成 2–3 条可检验的科研假说。每条假说须包含：\n"
    "1. hypothesis — 简明假说陈述\n"
    "2. confidence — 置信度(0–1)\n"
    "3. rationale — 理论依据\n"
    "4. suggested_methods — 建议验证方法列表\n"
    "请以严格 JSON 数组格式输出，不要添加其他文字。"
)

_EXPERIMENT_SYSTEM = (
    "你是一位中医药临床与实验研究设计专家。请根据给定的研究假说，"
    "设计一份完整的实验方案，返回严格 JSON 对象，包含以下字段：\n"
    "study_type — 研究类型(RCT/队列/病例对照/体外实验/动物实验等)\n"
    "sample_size — 建议样本量及估算依据\n"
    "methods — 实验方法步骤(数组)\n"
    "controls — 对照组设计\n"
    "variables — 自变量与因变量\n"
    "expected_outcomes — 预期结果\n"
    "statistical_analysis — 统计分析方法\n"
    "ethical_considerations — 伦理考量\n"
    "不要添加 JSON 以外的文字。"
)

_NOVELTY_SYSTEM = (
    "你是一位中医药学术评审专家。请评估给定假说相对于已有文献的创新性。"
    "返回严格 JSON 对象，包含：\n"
    "novelty_score — 创新性评分(0–10)\n"
    "novelty_level — 创新等级(突破性/显著/中等/增量/低)\n"
    "overlapping_studies — 已有相似研究摘要(数组)\n"
    "unique_aspects — 本假说的独特之处(数组)\n"
    "improvement_suggestions — 提升创新性的建议(数组)\n"
    "不要添加 JSON 以外的文字。"
)


class ResearchAdvisor:
    """科研建议引擎 — 假说生成、实验设计与创新性评估。

    Parameters
    ----------
    llm_engine : object | None
        LLM 推理引擎，需具备 ``generate(prompt, system_prompt)`` 方法。
        为 ``None`` 时惰性加载 ``src.llm.llm_engine.LLMEngine``。
    """

    def __init__(self, llm_engine: Optional[Any] = None) -> None:
        self._llm = llm_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest_hypothesis(
        self,
        topic: str,
        literature: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """基于 LLM 生成 2–3 条研究假说。

        Parameters
        ----------
        topic : str
            研究主题。
        literature : list[dict] | None
            已有文献列表，每项可含 ``title``, ``abstract``, ``authors`` 等。

        Returns
        -------
        list[dict]
            每条含 ``hypothesis``, ``confidence``, ``rationale``, ``suggested_methods``。
        """
        lit_summary = self._summarize_literature(literature)
        rendered = render_prompt(
            "research_advisor.hypothesis_suggestion",
            topic=topic,
            literature_section=(f"【已有文献摘要】\n{lit_summary}\n" if lit_summary else ""),
        )

        raw = self._call_registered_llm("research_advisor.hypothesis_suggestion", rendered)
        validation = parse_registered_output("research_advisor.hypothesis_suggestion", raw)
        hypotheses = validation.parsed if isinstance(validation.parsed, list) else self._parse_json_list(raw)

        # 确保每条都有必需字段
        result: List[Dict[str, Any]] = []
        for idx, h in enumerate(hypotheses[:3]):
            result.append({
                "hypothesis": h.get("hypothesis", f"假说 {idx + 1}"),
                "confidence": self._clamp(h.get("confidence", 0.5), 0.0, 1.0),
                "rationale": h.get("rationale", ""),
                "suggested_methods": h.get("suggested_methods", []),
            })

        if not result:
            result = self._fallback_hypotheses(topic)
        return result

    def design_experiment(self, hypothesis: str) -> Dict[str, Any]:
        """为给定假说设计实验方案。

        Parameters
        ----------
        hypothesis : str
            研究假说陈述。

        Returns
        -------
        dict
            含 ``study_type``, ``sample_size``, ``methods``, ``controls``,
            ``expected_outcomes`` 等。
        """
        rendered = render_prompt(
            "research_advisor.experiment_design",
            hypothesis=hypothesis,
        )
        raw = self._call_registered_llm("research_advisor.experiment_design", rendered)
        validation = parse_registered_output("research_advisor.experiment_design", raw)
        design = validation.parsed if isinstance(validation.parsed, dict) else self._parse_json_dict(raw)

        # 确保核心字段存在
        defaults = {
            "study_type": "待定",
            "sample_size": "待估算",
            "methods": [],
            "controls": "待设计",
            "variables": {},
            "expected_outcomes": "待定",
            "statistical_analysis": "待定",
            "ethical_considerations": "待评估",
        }
        for key, default in defaults.items():
            design.setdefault(key, default)

        if not design.get("methods"):
            design = self._fallback_experiment(hypothesis)
        return design

    def evaluate_novelty(
        self,
        hypothesis: str,
        existing_literature: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """评估假说相对于已有文献的创新性。

        Parameters
        ----------
        hypothesis : str
            研究假说。
        existing_literature : list[dict] | None
            已有文献列表。

        Returns
        -------
        dict
            含 ``novelty_score``, ``novelty_level``, ``overlapping_studies``,
            ``unique_aspects``, ``improvement_suggestions``。
        """
        lit_summary = self._summarize_literature(existing_literature)
        rendered = render_prompt(
            "research_advisor.novelty_evaluation",
            hypothesis=hypothesis,
            literature_section=(f"【已有文献】\n{lit_summary}\n" if lit_summary else ""),
        )

        raw = self._call_registered_llm("research_advisor.novelty_evaluation", rendered)
        validation = parse_registered_output("research_advisor.novelty_evaluation", raw)
        result = validation.parsed if isinstance(validation.parsed, dict) else self._parse_json_dict(raw)

        defaults: Dict[str, Any] = {
            "novelty_score": 5,
            "novelty_level": "中等",
            "overlapping_studies": [],
            "unique_aspects": [],
            "improvement_suggestions": [],
        }
        for key, default in defaults.items():
            result.setdefault(key, default)

        result["novelty_score"] = self._clamp(result["novelty_score"], 0, 10)
        return result

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str, system_prompt: str) -> str:
        engine = self._get_llm()
        if engine is None:
            logger.warning("LLM 引擎不可用，返回空字符串")
            return ""
        try:
            return engine.generate(prompt, system_prompt=system_prompt)
        except Exception:
            logger.exception("LLM 生成失败")
            return ""

    def _call_registered_llm(self, prompt_name: str, rendered) -> str:
        engine = self._get_llm()
        if engine is None:
            logger.warning("LLM 引擎不可用，返回空字符串")
            return ""
        try:
            return call_registered_prompt(engine, prompt_name, rendered=rendered)
        except Exception:
            logger.exception("LLM 结构化生成失败")
            return ""

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        try:
            from src.infra.llm_service import get_llm_service
            svc = get_llm_service("assistant")
            svc.load()
            self._llm = svc
            return svc
        except Exception as exc:
            self._llm = None
            logger.warning("无法加载 LLM 引擎: %s", exc)
            return None

    # ------------------------------------------------------------------
    # JSON parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_list(text: str) -> List[Dict[str, Any]]:
        """尝试从 LLM 输出中提取 JSON 数组。"""
        if not text:
            return []
        # 尝试直接解析
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*(\[.*?])\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试找到第一个 [ ... ]
        m = re.search(r'\[.*]', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def _parse_json_dict(text: str) -> Dict[str, Any]:
        """尝试从 LLM 输出中提取 JSON 对象。"""
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        m = re.search(r'```(?:json)?\s*(\{.*?})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r'\{.*}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_literature(literature: Optional[List[Dict[str, Any]]]) -> str:
        if not literature:
            return ""
        lines: List[str] = []
        for idx, item in enumerate(literature[:10], 1):
            title = item.get("title", "无标题")
            abstract = item.get("abstract", "")
            if abstract and len(abstract) > 200:
                abstract = abstract[:200] + "…"
            line = f"{idx}. {title}"
            if abstract:
                line += f" — {abstract}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _clamp(value, lo, hi):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return lo
        return max(lo, min(hi, v))

    # ------------------------------------------------------------------
    # Fallback outputs (when LLM unavailable)
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_hypotheses(topic: str) -> List[Dict[str, Any]]:
        return [
            {
                "hypothesis": f"针对「{topic}」，中药复方可能通过多靶点协同机制发挥治疗作用",
                "confidence": 0.6,
                "rationale": "中医方剂的君臣佐使配伍体现多组分多靶点特征",
                "suggested_methods": ["网络药理学分析", "分子对接验证", "体外细胞实验"],
            },
            {
                "hypothesis": f"「{topic}」相关经典方剂的核心药对存在剂量依赖性协同效应",
                "confidence": 0.5,
                "rationale": "基于经典文献记载的配伍规律推测量效关系",
                "suggested_methods": ["等效线分析", "Chou-Talalay 联合指数法", "动物模型验证"],
            },
        ]

    @staticmethod
    def _fallback_experiment(hypothesis: str) -> Dict[str, Any]:
        return {
            "study_type": "随机对照实验 (RCT)",
            "sample_size": "根据效应量和检验效能计算（建议 ≥30/组）",
            "methods": [
                "文献回顾与研究方案制定",
                "样本筛选与随机分组",
                "干预措施实施",
                "数据采集与质量控制",
                "统计分析与结果报告",
            ],
            "controls": "安慰剂对照 + 阳性药物对照",
            "variables": {
                "independent": "干预措施（中药/对照）",
                "dependent": "主要疗效指标",
            },
            "expected_outcomes": f"验证假说: {hypothesis[:100]}",
            "statistical_analysis": "意向性分析 (ITT)，双侧检验 α=0.05",
            "ethical_considerations": "需通过伦理委员会审批，签署知情同意书",
        }
