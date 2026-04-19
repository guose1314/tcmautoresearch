"""ResearchDossierBuilder — 将多源研究素材压缩为 LLM 可消费的研究 dossier。

架构位置
--------
本模块位于 ``src/research``，在 *Phase Orchestrator* 与 *LLM 生成层* 之间，
负责把散布在多个阶段结果、图谱查询、证据记录和术语表中的长文本
压缩成一份结构化、可复用的 **研究 dossier**——
确保 7B / 14B 本地模型在有限上下文窗口内获得最大信息密度。

设计目标
--------
* 面向 ``ResearchCycle`` 和 ``Dict[str, PhaseResult]`` 的聚合入口。
* 按 *section* 组织（objective / evidence / entities / graph / terminology / corpus_digest）。
* 每个 section 带独立 ``token_budget``，总预算可由调用方指定。
* 返回 ``ResearchDossier`` dataclass（可序列化为 JSON / Markdown / 纯文本）。
* 通过 ``get_llm_service`` 获取 LLM（用于摘要压缩），不直接实例化 LLMEngine。

快速上手
--------
::

    from src.research.dossier_builder import ResearchDossierBuilder

    builder = ResearchDossierBuilder(max_context_tokens=3072)
    dossier = builder.build(cycle, phase_records)
    prompt_text = dossier.to_text()
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.research.observe_philology import (
    extract_observe_philology_assets_from_phase_result,
)
from src.research.phase_result import get_phase_results, is_phase_result_payload

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────────

# 粗略 token 估算：中文 ~1.5 字/token，英文 ~4 char/token；
# 此处取折中值用于预算控制。
_CHARS_PER_TOKEN_CN = 1.5
_CHARS_PER_TOKEN_EN = 4.0

# Section 默认 token 预算分配比例 (总和 = 1.0)
_DEFAULT_BUDGET_RATIOS: Dict[str, float] = {
    "objective": 0.06,
    "evidence": 0.22,
    "entities": 0.12,
    "graph": 0.12,
    "terminology": 0.08,
    "version_info": 0.08,
    "controversies": 0.10,
    "hypothesis_history": 0.10,
    "corpus_digest": 0.12,
}

_PHASE_DOSSIER_DEFAULT_MAX_TOKENS: Dict[str, int] = {
    "observe": 1280,
    "analyze": 1536,
    "publish": 1792,
}

_PHASE_DOSSIER_BUDGET_RATIOS: Dict[str, Dict[str, float]] = {
    "observe": {
        "objective": 0.10,
        "observe_summary": 0.22,
        "philology": 0.24,
        "entities": 0.12,
        "terminology": 0.16,
        "corpus_digest": 0.16,
    },
    "analyze": {
        "objective": 0.08,
        "analysis_summary": 0.20,
        "evidence_protocol": 0.26,
        "evidence_grade": 0.14,
        "textual_evidence": 0.18,
        "entities": 0.14,
    },
    "publish": {
        "objective": 0.08,
        "publish_summary": 0.14,
        "paper_digest": 0.28,
        "reference_digest": 0.18,
        "artifact_digest": 0.18,
        "output_digest": 0.14,
    },
}

_SUPPORTED_PHASE_DOSSIERS: tuple[str, ...] = ("observe", "analyze", "publish")


# ── 数据结构 ─────────────────────────────────────────────────────────────────


@dataclass
class DossierSection:
    """Dossier 中的一个 section。"""

    name: str
    content: str
    item_count: int = 0
    truncated: bool = False
    token_budget: int = 0
    estimated_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content,
            "item_count": self.item_count,
            "truncated": self.truncated,
            "token_budget": self.token_budget,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class ResearchDossier:
    """已压缩的研究 dossier——可直接注入 LLM prompt。"""

    cycle_id: str
    research_objective: str
    sections: List[DossierSection] = field(default_factory=list)
    max_context_tokens: int = 3072
    total_estimated_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── 序列化 ────────────────────────────────────────────────

    def to_text(self, separator: str = "\n\n") -> str:
        """渲染为纯文本格式（直接拼入 prompt）。"""
        parts: list[str] = []
        for sec in self.sections:
            if not sec.content.strip():
                continue
            parts.append(f"## {sec.name}\n{sec.content}")
        return separator.join(parts)

    def to_markdown(self) -> str:
        """渲染为 Markdown 格式。"""
        lines = [f"# 研究 Dossier: {self.research_objective}\n"]
        for sec in self.sections:
            if not sec.content.strip():
                continue
            lines.append(f"## {sec.name}")
            lines.append(sec.content)
            if sec.truncated:
                lines.append(f"_（已截断，原始条目 {sec.item_count} 条）_")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "research_objective": self.research_objective,
            "sections": [s.to_dict() for s in self.sections],
            "max_context_tokens": self.max_context_tokens,
            "total_estimated_tokens": self.total_estimated_tokens,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ── Builder ──────────────────────────────────────────────────────────────────


class ResearchDossierBuilder:
    """将 ResearchCycle + 阶段结果压缩为 ``ResearchDossier``。

    Parameters
    ----------
    max_context_tokens :
        输出 dossier 的总 token 预算（默认 3072，适合 4096 ctx 模型留 1024 给输出）。
    budget_ratios :
        各 section 的预算分配比例，键名见 ``_DEFAULT_BUDGET_RATIOS``。
    enable_llm_summarization :
        为 ``True`` 时，对超长 section 调用 LLM 做摘要压缩（需要可用模型）；
        为 ``False`` 时仅做截断。
    llm_purpose :
        传给 ``get_llm_service`` 的 purpose 标识。
    """

    def __init__(
        self,
        max_context_tokens: int = 3072,
        budget_ratios: Optional[Dict[str, float]] = None,
        enable_llm_summarization: bool = False,
        llm_purpose: str = "default",
        phase_max_context_tokens: Optional[Dict[str, int]] = None,
    ) -> None:
        self.max_context_tokens = max(256, int(max_context_tokens))
        self.budget_ratios = dict(budget_ratios or _DEFAULT_BUDGET_RATIOS)
        self.enable_llm_summarization = enable_llm_summarization
        self.llm_purpose = llm_purpose
        self._llm_service: Any = None
        self.phase_max_context_tokens = {
            phase_name: max(256, int(value))
            for phase_name, value in {
                **_PHASE_DOSSIER_DEFAULT_MAX_TOKENS,
                **dict(phase_max_context_tokens or {}),
            }.items()
        }

    # ── 公开 API ──────────────────────────────────────────────

    def build(
        self,
        cycle: Any,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        graph_data: Optional[Dict[str, Any]] = None,
        terminology: Optional[List[Dict[str, Any]]] = None,
        corpus_excerpts: Optional[List[str]] = None,
        version_info: Optional[List[Dict[str, Any]]] = None,
    ) -> ResearchDossier:
        """从研究周期构建 dossier。

        Parameters
        ----------
        cycle :
            ``ResearchCycle`` 实例（或任何拥有 ``cycle_id``,
            ``research_objective``, ``phase_executions``, ``outcomes`` 属性的对象）。
        phase_records :
            ``{phase_name: phase_record_dict}``，如不提供则从
            ``cycle.phase_executions`` 提取。
        graph_data :
            图谱查询结果 ``{"nodes": [...], "edges": [...]}"``。
        terminology :
            术语条目列表 ``[{"term": "...", "definition": "..."}, ...]``。
        corpus_excerpts :
            语料摘录文本列表。
        version_info :
            文献版本信息 ``[{"title": "...", "dynasty": "...", "author": "...", ...}]``。
        """
        cycle_id = getattr(cycle, "cycle_id", "") or ""
        objective = getattr(cycle, "research_objective", "") or ""
        records = phase_records or self._extract_phase_records(cycle)

        dossier = ResearchDossier(
            cycle_id=cycle_id,
            research_objective=objective,
            max_context_tokens=self.max_context_tokens,
        )

        # 按 section 逐个构建
        dossier.sections.append(
            self._build_objective_section(objective, cycle)
        )
        dossier.sections.append(
            self._build_evidence_section(records)
        )
        dossier.sections.append(
            self._build_entities_section(records)
        )
        dossier.sections.append(
            self._build_graph_section(graph_data)
        )
        dossier.sections.append(
            self._build_terminology_section(terminology)
        )
        dossier.sections.append(
            self._build_version_info_section(records, version_info)
        )
        dossier.sections.append(
            self._build_controversies_section(records)
        )
        dossier.sections.append(
            self._build_hypothesis_history_section(records, cycle)
        )
        dossier.sections.append(
            self._build_corpus_digest_section(records, corpus_excerpts)
        )

        return self._finalize_dossier(
            dossier,
            dossier_kind="global",
            source_phases=sorted(records.keys()),
        )

    def build_phase_dossier(
        self,
        cycle: Any,
        phase_name: str,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResearchDossier:
        normalized_phase_name = str(phase_name or "").strip().lower()
        if normalized_phase_name == "observe":
            return self.build_observe_dossier(cycle, phase_records)
        if normalized_phase_name == "analyze":
            return self.build_analyze_dossier(cycle, phase_records)
        if normalized_phase_name == "publish":
            return self.build_publish_dossier(cycle, phase_records)
        raise ValueError(f"不支持的 phase dossier: {phase_name}")

    def build_phase_dossiers(
        self,
        cycle: Any,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, ResearchDossier]:
        records = phase_records or self._extract_phase_records(cycle)
        dossiers: Dict[str, ResearchDossier] = {}
        for phase_name in _SUPPORTED_PHASE_DOSSIERS:
            if phase_name not in records:
                continue
            dossiers[phase_name] = self.build_phase_dossier(cycle, phase_name, records)
        return dossiers

    def build_observe_dossier(
        self,
        cycle: Any,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResearchDossier:
        records = phase_records or self._extract_phase_records(cycle)
        observe_record = records.get("observe") or {}
        observe_results = self._resolve_phase_results_payload(observe_record)
        observe_phase_result = self._resolve_phase_result_payload(observe_record)
        philology_assets = extract_observe_philology_assets_from_phase_result(observe_phase_result)
        terminology_rows = self._as_dict_list(philology_assets.get("terminology_standard_table"))

        dossier = ResearchDossier(
            cycle_id=getattr(cycle, "cycle_id", "") or "",
            research_objective=getattr(cycle, "research_objective", "") or "",
            max_context_tokens=self._resolve_phase_max_context_tokens("observe"),
        )
        dossier.sections = [
            self._build_phase_objective_section(cycle, "observe"),
            self._build_observe_summary_section(observe_results),
            self._build_observe_philology_section(philology_assets),
            self._build_phase_entities_section({"observe": observe_record}, "observe"),
            self._build_phase_terminology_section(terminology_rows, "observe"),
            self._build_observe_corpus_digest_section(observe_results),
        ]
        return self._finalize_dossier(dossier, dossier_kind="observe", source_phases=["observe"])

    def build_analyze_dossier(
        self,
        cycle: Any,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResearchDossier:
        records = phase_records or self._extract_phase_records(cycle)
        analyze_record = records.get("analyze") or {}
        analyze_results = self._resolve_phase_results_payload(analyze_record)

        dossier = ResearchDossier(
            cycle_id=getattr(cycle, "cycle_id", "") or "",
            research_objective=getattr(cycle, "research_objective", "") or "",
            max_context_tokens=self._resolve_phase_max_context_tokens("analyze"),
        )
        dossier.sections = [
            self._build_phase_objective_section(cycle, "analyze"),
            self._build_analyze_summary_section(analyze_results),
            self._build_analyze_evidence_protocol_section(analyze_results),
            self._build_analyze_evidence_grade_section(analyze_results),
            self._build_analyze_textual_evidence_section(analyze_results),
            self._build_phase_entities_section({"analyze": analyze_record}, "analyze"),
        ]
        return self._finalize_dossier(dossier, dossier_kind="analyze", source_phases=["analyze"])

    def build_publish_dossier(
        self,
        cycle: Any,
        phase_records: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ResearchDossier:
        records = phase_records or self._extract_phase_records(cycle)
        publish_record = records.get("publish") or {}
        publish_results = self._resolve_phase_results_payload(publish_record)
        publish_metadata = self._resolve_phase_metadata_payload(publish_record)
        publish_source = self._resolve_cycle_phase_dossier_source(cycle, "publish")

        dossier = ResearchDossier(
            cycle_id=getattr(cycle, "cycle_id", "") or "",
            research_objective=getattr(cycle, "research_objective", "") or "",
            max_context_tokens=self._resolve_phase_max_context_tokens("publish"),
        )
        dossier.sections = [
            self._build_phase_objective_section(cycle, "publish"),
            self._build_publish_summary_section(publish_results, publish_metadata, publish_source),
            self._build_publish_paper_digest_section(publish_results, publish_source),
            self._build_publish_reference_digest_section(publish_results, publish_metadata),
            self._build_publish_artifact_digest_section(publish_results),
            self._build_publish_output_digest_section(publish_results),
        ]
        return self._finalize_dossier(dossier, dossier_kind="publish", source_phases=["publish"])

    # ── Section 构建器 ────────────────────────────────────────

    def _build_objective_section(
        self, objective: str, cycle: Any,
    ) -> DossierSection:
        budget = self._section_budget("objective")
        parts: list[str] = []
        if objective:
            parts.append(f"研究目标：{objective}")
        scope = getattr(cycle, "research_scope", "") or ""
        if scope:
            parts.append(f"研究范围：{scope}")
        content = "\n".join(parts)
        content, truncated = self._fit_budget(content, budget)
        return DossierSection(
            name="研究目标",
            content=content,
            item_count=1,
            truncated=truncated,
            token_budget=budget,
        )

    def _build_evidence_section(
        self, records: Dict[str, Dict[str, Any]],
    ) -> DossierSection:
        budget = self._section_budget("evidence")
        evidence_items = self._collect_evidence_lines(records)
        return self._build_text_section("证据摘要", "\n".join(evidence_items), len(evidence_items), budget)

    def _build_entities_section(
        self, records: Dict[str, Dict[str, Any]],
    ) -> DossierSection:
        budget = self._section_budget("entities")
        entity_items = self._collect_entity_items(records)
        lines = [f"- {name} ({etype})" for name, etype in entity_items]
        return self._build_text_section("实体列表", "\n".join(lines), len(entity_items), budget)

    def _build_graph_section(
        self, graph_data: Optional[Dict[str, Any]],
    ) -> DossierSection:
        budget = self._section_budget("graph")
        if not graph_data:
            return DossierSection(
                name="知识图谱", content="", item_count=0, token_budget=budget,
            )

        lines: list[str] = []
        nodes = graph_data.get("nodes") or []
        edges = graph_data.get("edges") or graph_data.get("relationships") or []

        if nodes:
            node_summary = ", ".join(
                f"{n.get('name', '?')}({n.get('type', n.get('label', '?'))})"
                for n in nodes[:50]
            )
            lines.append(f"节点 ({len(nodes)}): {node_summary}")

        if edges:
            for e in edges[:30]:
                src = e.get("source") or e.get("start", "?")
                rel = e.get("type") or e.get("relation", "?")
                tgt = e.get("target") or e.get("end", "?")
                lines.append(f"  {src} -[{rel}]-> {tgt}")

        content = "\n".join(lines)
        content, truncated = self._fit_budget(content, budget)
        return DossierSection(
            name="知识图谱",
            content=content,
            item_count=len(nodes) + len(edges),
            truncated=truncated,
            token_budget=budget,
        )

    def _build_terminology_section(
        self, terminology: Optional[List[Dict[str, Any]]],
    ) -> DossierSection:
        budget = self._section_budget("terminology")
        if not terminology:
            return DossierSection(
                name="术语表", content="", item_count=0, token_budget=budget,
            )

        lines = self._collect_terminology_lines(terminology)
        return self._build_text_section("术语表", "\n".join(lines), len(lines), budget)

    def _build_version_info_section(
        self,
        records: Dict[str, Dict[str, Any]],
        version_info: Optional[List[Dict[str, Any]]],
    ) -> DossierSection:
        """构建版本信息 section：文献来源、朝代、作者、版本谱系。"""
        budget = self._section_budget("version_info")
        lines: list[str] = []

        # 从显式传入的 version_info 提取
        if version_info:
            for item in version_info[:20]:
                title = str(item.get("title") or item.get("document_title") or "").strip()
                dynasty = str(item.get("dynasty") or "").strip()
                author = str(item.get("author") or "").strip()
                lineage = str(item.get("version_lineage") or item.get("version_lineage_key") or "").strip()
                parts: list[str] = []
                if title:
                    parts.append(title)
                if dynasty:
                    parts.append(f"[{dynasty}]")
                if author:
                    parts.append(author)
                if lineage:
                    parts.append(f"（谱系：{lineage}）")
                if parts:
                    lines.append("- " + " ".join(parts))

        # 从 observe 阶段的 philology 提取版本谱系
        if not lines:
            observe_record = records.get("observe") or {}
            observe_payload = self._resolve_phase_result_payload(observe_record)
            philology_assets = extract_observe_philology_assets_from_phase_result(observe_payload)
            if isinstance(philology_assets, dict) and philology_assets.get("available"):
                collation_entries = self._as_dict_list(philology_assets.get("collation_entries"))
                for entry in collation_entries[:15]:
                    doc_title = str(entry.get("document_title") or "").strip()
                    witness = str(entry.get("witness_key") or "").strip()
                    lineage_key = str(entry.get("version_lineage_key") or "").strip()
                    note = str(entry.get("note") or entry.get("collation_note") or "").strip()
                    desc = doc_title or witness or lineage_key
                    if desc:
                        line = f"- {desc}"
                        if note:
                            line += f"：{note[:80]}"
                        lines.append(line)

        if not lines:
            return DossierSection(name="版本信息", content="", item_count=0, token_budget=budget)

        return self._build_text_section("版本信息", "\n".join(lines), len(lines), budget)

    def _build_controversies_section(
        self,
        records: Dict[str, Dict[str, Any]],
    ) -> DossierSection:
        """构建争议点 section：冲突论断、证据矛盾、学术争议。"""
        budget = self._section_budget("controversies")
        lines: list[str] = []

        # 从 observe 阶段的 philology conflict_claims 提取
        observe_record = records.get("observe") or {}
        observe_payload = self._resolve_phase_result_payload(observe_record)
        philology_assets = extract_observe_philology_assets_from_phase_result(observe_payload)
        if isinstance(philology_assets, dict) and philology_assets.get("available"):
            conflict_claims = self._as_dict_list(philology_assets.get("conflict_claims"))
            for claim in conflict_claims[:10]:
                subject = str(claim.get("subject") or claim.get("term") or claim.get("entity") or "").strip()
                claim_a = str(claim.get("claim_a") or claim.get("position_a") or "").strip()
                claim_b = str(claim.get("claim_b") or claim.get("position_b") or "").strip()
                source_a = str(claim.get("source_a") or "").strip()
                source_b = str(claim.get("source_b") or "").strip()
                if subject and (claim_a or claim_b):
                    line = f"- 【{subject}】"
                    if claim_a:
                        line += f" 观点A：{claim_a[:60]}"
                        if source_a:
                            line += f"（{source_a}）"
                    if claim_b:
                        line += f" vs 观点B：{claim_b[:60]}"
                        if source_b:
                            line += f"（{source_b}）"
                    lines.append(line)

        # 从 analyze 阶段的 evidence 中提取相互矛盾的证据
        analyze_record = records.get("analyze") or {}
        analyze_results = self._resolve_phase_results_payload(analyze_record)
        evidence_protocol = self._resolve_nested_dict(analyze_results, "evidence_protocol")
        contradictions = self._as_dict_list(
            evidence_protocol.get("contradictions")
            or evidence_protocol.get("conflicting_evidence")
            or analyze_results.get("contradictions")
        )
        for contra in contradictions[:8]:
            topic = str(contra.get("topic") or contra.get("claim") or "").strip()
            detail = str(contra.get("detail") or contra.get("description") or "").strip()
            if topic:
                line = f"- 证据矛盾：{topic}"
                if detail:
                    line += f" — {detail[:80]}"
                lines.append(line)

        if not lines:
            return DossierSection(name="争议点", content="", item_count=0, token_budget=budget)

        return self._build_text_section("争议点", "\n".join(lines), len(lines), budget)

    def _build_hypothesis_history_section(
        self,
        records: Dict[str, Dict[str, Any]],
        cycle: Any,
    ) -> DossierSection:
        """构建假说历史 section：各阶段生成的假说及其演变。"""
        budget = self._section_budget("hypothesis_history")
        lines: list[str] = []

        # 从各阶段记录中收集假说
        for phase_name in ("observe", "analyze", "hypothesis", "publish"):
            record = records.get(phase_name)
            if not record:
                continue
            results = self._resolve_phase_results_payload(record)
            hypotheses = self._as_dict_list(
                results.get("hypotheses")
                or self._resolve_nested_dict(results, "hypothesis_result").get("hypotheses")
                or self._resolve_nested_dict(results, "reasoning_results").get("hypotheses")
            )
            if not hypotheses:
                continue
            lines.append(f"[{phase_name}阶段] 生成 {len(hypotheses)} 条假说：")
            for i, h in enumerate(hypotheses[:5], 1):
                statement = str(
                    h.get("statement") or h.get("hypothesis") or h.get("title") or ""
                ).strip()
                if not statement:
                    continue
                novelty = h.get("novelty")
                feasibility = h.get("feasibility")
                scores = ""
                if novelty is not None or feasibility is not None:
                    parts = []
                    if novelty is not None:
                        parts.append(f"新颖度={novelty}")
                    if feasibility is not None:
                        parts.append(f"可行性={feasibility}")
                    scores = f" ({', '.join(parts)})"
                lines.append(f"  {i}. {statement[:100]}{scores}")

        # 从 cycle.outcomes 补充最终选定假说
        outcomes = getattr(cycle, "outcomes", None) or []
        if isinstance(outcomes, list):
            selected = [
                o for o in outcomes
                if isinstance(o, dict) and (
                    o.get("type") == "hypothesis" or "hypothesis" in str(o.get("category") or "")
                )
            ]
            if selected:
                lines.append("[最终选定假说]")
                for s in selected[:3]:
                    text = str(s.get("statement") or s.get("content") or s.get("title") or "").strip()
                    if text:
                        lines.append(f"  ★ {text[:120]}")

        if not lines:
            return DossierSection(name="假说历史", content="", item_count=0, token_budget=budget)

        return self._build_text_section("假说历史", "\n".join(lines), len(lines), budget)

    def _build_corpus_digest_section(
        self,
        records: Dict[str, Dict[str, Any]],
        corpus_excerpts: Optional[List[str]],
    ) -> DossierSection:
        budget = self._section_budget("corpus_digest")
        parts = self._collect_corpus_parts(records, corpus_excerpts)
        return self._build_text_section("语料摘要", "\n".join(parts), len(parts), budget)

    def _build_phase_objective_section(self, cycle: Any, phase_name: str) -> DossierSection:
        parts: list[str] = []
        objective = str(getattr(cycle, "research_objective", "") or "").strip()
        scope = str(getattr(cycle, "research_scope", "") or "").strip()
        if objective:
            parts.append(f"研究目标：{objective}")
        if scope:
            parts.append(f"研究范围：{scope}")
        parts.append(f"当前压缩阶段：{phase_name}")
        return self._build_phase_text_section(
            phase_name,
            "objective",
            "研究目标",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_phase_entities_section(
        self,
        records: Dict[str, Dict[str, Any]],
        phase_name: str,
    ) -> DossierSection:
        entity_items = self._collect_entity_items(records)
        lines = [f"- {name} ({etype})" for name, etype in entity_items]
        return self._build_phase_text_section(
            phase_name,
            "entities",
            "实体列表",
            "\n".join(lines),
            item_count=len(entity_items),
        )

    def _build_phase_terminology_section(
        self,
        terminology: Optional[List[Dict[str, Any]]],
        phase_name: str,
    ) -> DossierSection:
        lines = self._collect_terminology_lines(terminology)
        return self._build_phase_text_section(
            phase_name,
            "terminology",
            "术语表",
            "\n".join(lines),
            item_count=len(lines),
        )

    def _build_observe_summary_section(self, observe_results: Dict[str, Any]) -> DossierSection:
        summary = self._first_non_empty_text(
            observe_results.get("summary"),
            observe_results.get("analysis_summary"),
            observe_results.get("description"),
        )
        observations = self._extract_text_items(observe_results.get("observations"))
        findings = self._extract_text_items(observe_results.get("findings"))
        corpus_collection = observe_results.get("corpus_collection") if isinstance(observe_results.get("corpus_collection"), dict) else {}
        literature_pipeline = observe_results.get("literature_pipeline") if isinstance(observe_results.get("literature_pipeline"), dict) else {}

        parts: list[str] = []
        if summary:
            parts.append(f"阶段摘要：{summary}")
        if observations:
            parts.append("关键观察：")
            parts.extend(f"- {item}" for item in observations[:6])
        if findings:
            parts.append("关键发现：")
            parts.extend(f"- {item}" for item in findings[:6])

        corpus_stats: list[str] = []
        document_count = self._coerce_int(
            corpus_collection.get("document_count"),
            corpus_collection.get("source_count"),
            literature_pipeline.get("record_count"),
            default=0,
        )
        text_entry_count = self._coerce_int(
            corpus_collection.get("text_entry_count"),
            corpus_collection.get("entry_count"),
            default=0,
        )
        if document_count:
            corpus_stats.append(f"文档数 {document_count}")
        if text_entry_count:
            corpus_stats.append(f"语料条目 {text_entry_count}")
        if corpus_stats:
            parts.append(f"语料规模：{'，'.join(corpus_stats)}。")

        return self._build_phase_text_section(
            "observe",
            "observe_summary",
            "观察摘要",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_observe_philology_section(self, philology_assets: Dict[str, Any]) -> DossierSection:
        if not isinstance(philology_assets, dict) or not philology_assets.get("available"):
            return self._build_phase_text_section("observe", "philology", "文献考据", "", item_count=0)

        terminology_rows = self._as_dict_list(philology_assets.get("terminology_standard_table"))
        collation_entries = self._as_dict_list(philology_assets.get("collation_entries"))
        evidence_chains = self._as_dict_list(philology_assets.get("evidence_chains"))
        conflict_claims = self._as_dict_list(philology_assets.get("conflict_claims"))

        parts = [
            (
                "考据概览："
                f"术语规范 {self._coerce_int(philology_assets.get('terminology_standard_table_count'), len(terminology_rows))} 条，"
                f"校勘条目 {self._coerce_int(philology_assets.get('collation_entry_count'), len(collation_entries))} 条，"
                f"证据链 {self._coerce_int(philology_assets.get('evidence_chain_count'), len(evidence_chains))} 条，"
                f"冲突论断 {self._coerce_int(philology_assets.get('conflict_count'), len(conflict_claims))} 条。"
            )
        ]

        if terminology_rows:
            parts.append("核心术语规范：")
            for row in terminology_rows[:5]:
                source_term = self._first_non_empty_text(
                    row.get("source_term"),
                    row.get("term"),
                    row.get("surface_form"),
                    row.get("name"),
                )
                canonical_term = self._first_non_empty_text(
                    row.get("canonical_term"),
                    row.get("canonical"),
                    row.get("normalized_term"),
                    row.get("normalized"),
                )
                notes = self._first_non_empty_text(row.get("definition"), row.get("notes"), row.get("label"))
                line = f"- {source_term}"
                if canonical_term and canonical_term != source_term:
                    line += f" → {canonical_term}"
                if notes:
                    line += f" | {_truncate(notes, 90)}"
                parts.append(line)

        if collation_entries:
            parts.append("关键校勘：")
            for entry in collation_entries[:4]:
                lemma = self._first_non_empty_text(entry.get("lemma"), entry.get("canonical_text"), entry.get("source_text"), entry.get("term"))
                variant = self._first_non_empty_text(entry.get("variant"), entry.get("variant_text"), entry.get("reading"), entry.get("target_text"))
                witness = self._first_non_empty_text(entry.get("witness"), entry.get("witnesses"), entry.get("source_document"), entry.get("document_title"))
                line = f"- {lemma or '未命名条目'}"
                if variant:
                    line += f" vs {variant}"
                if witness:
                    line += f" | 见于 {witness}"
                parts.append(line)

        if evidence_chains:
            parts.append("考据证据链：")
            for chain in evidence_chains[:4]:
                claim = self._first_non_empty_text(chain.get("claim"), chain.get("statement"), chain.get("summary"), chain.get("conclusion"))
                support = self._first_non_empty_text(chain.get("supporting_evidence"), chain.get("evidence"), chain.get("excerpt"))
                line = f"- {claim or '未命名证据链'}"
                if support:
                    line += f" | {_truncate(support, 100)}"
                parts.append(line)

        return self._build_phase_text_section(
            "observe",
            "philology",
            "文献考据",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_observe_corpus_digest_section(self, observe_results: Dict[str, Any]) -> DossierSection:
        parts: list[str] = []
        corpus_collection = observe_results.get("corpus_collection") if isinstance(observe_results.get("corpus_collection"), dict) else {}
        documents = observe_results.get("documents")
        if not isinstance(documents, list):
            documents = corpus_collection.get("documents") if isinstance(corpus_collection.get("documents"), list) else []

        collection_summary = self._first_non_empty_text(
            corpus_collection.get("summary"),
            observe_results.get("summary"),
        )
        if collection_summary:
            parts.append(f"语料总述：{collection_summary}")

        for document in documents[:5]:
            if not isinstance(document, dict):
                continue
            title = self._first_non_empty_text(document.get("title"), document.get("name"), document.get("source"), document.get("document_id"))
            snippet = self._first_non_empty_text(document.get("summary"), document.get("excerpt"), document.get("description"), document.get("text"))
            if title or snippet:
                line = f"- {title or '未命名语料'}"
                if snippet:
                    line += f": {_truncate(snippet, 120)}"
                parts.append(line)

        return self._build_phase_text_section(
            "observe",
            "corpus_digest",
            "语料摘要",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_analyze_summary_section(self, analyze_results: Dict[str, Any]) -> DossierSection:
        analysis_summary = self._first_non_empty_text(
            analyze_results.get("analysis_summary"),
            analyze_results.get("summary"),
            analyze_results.get("description"),
        )
        statistical_analysis = self._resolve_nested_dict(analyze_results, "statistical_analysis")
        reasoning_results = self._resolve_nested_dict(analyze_results, "reasoning_results")

        parts: list[str] = []
        if analysis_summary:
            parts.append(f"阶段摘要：{analysis_summary}")
        parts.extend(self._summarize_mapping(
            statistical_analysis,
            preferred_keys=("method", "sample_size", "test_count", "significant_result_count", "significant_findings"),
            heading="统计分析摘要",
        ))
        if reasoning_results:
            evidence_count = len(self._as_dict_list(reasoning_results.get("evidence_records")))
            claim_count = len(self._as_dict_list(reasoning_results.get("claims")))
            parts.append(f"推理链路：证据记录 {evidence_count} 条，候选论断 {claim_count} 条。")

        return self._build_phase_text_section(
            "analyze",
            "analysis_summary",
            "分析摘要",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_analyze_evidence_protocol_section(self, analyze_results: Dict[str, Any]) -> DossierSection:
        evidence_protocol = self._resolve_nested_dict(analyze_results, "evidence_protocol")
        claims = self._as_dict_list(evidence_protocol.get("claims"))
        evidence_records = self._collect_dict_list(
            evidence_protocol.get("evidence_records"),
            self._resolve_nested_dict(analyze_results, "reasoning_results").get("evidence_records"),
        )

        parts = self._summarize_mapping(
            evidence_protocol,
            preferred_keys=("summary", "protocol_summary", "claim_count", "evidence_record_count", "coverage_notes"),
            heading="证据协议",
        )
        if claims:
            parts.append("候选论断：")
            for claim in claims[:5]:
                claim_text = self._first_non_empty_text(claim.get("claim"), claim.get("statement"), claim.get("text"), claim.get("description"))
                grade = self._first_non_empty_text(claim.get("evidence_grade"), claim.get("grade"))
                line = f"- {claim_text or '未命名论断'}"
                if grade:
                    line += f" [{grade}]"
                parts.append(line)
        if evidence_records:
            parts.append("代表性证据：")
            parts.extend(self._collect_evidence_lines({"analyze": {"results": {"evidence_records": evidence_records}}})[:5])

        return self._build_phase_text_section(
            "analyze",
            "evidence_protocol",
            "证据协议",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_analyze_evidence_grade_section(self, analyze_results: Dict[str, Any]) -> DossierSection:
        evidence_grade_summary = self._resolve_nested_dict(analyze_results, "evidence_grade_summary")
        parts = self._summarize_mapping(
            evidence_grade_summary,
            preferred_keys=(
                "summary",
                "high_count",
                "moderate_count",
                "low_count",
                "very_low_count",
                "risk_of_bias",
                "consistency",
            ),
            heading="证据分级",
        )
        return self._build_phase_text_section(
            "analyze",
            "evidence_grade",
            "证据分级",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_analyze_textual_evidence_section(self, analyze_results: Dict[str, Any]) -> DossierSection:
        textual_evidence_summary = self._resolve_nested_dict(analyze_results, "textual_evidence_summary")
        graph_evidence_summary = self._resolve_nested_dict(analyze_results, "similar_formula_graph_evidence_summary")
        parts = self._summarize_mapping(
            textual_evidence_summary,
            preferred_keys=("summary", "key_findings", "evidence_chain_count", "document_count"),
            heading="文本证据",
        )
        parts.extend(self._summarize_mapping(
            graph_evidence_summary,
            preferred_keys=("summary", "match_count", "top_match", "overall_score"),
            heading="图谱证据",
        ))
        return self._build_phase_text_section(
            "analyze",
            "textual_evidence",
            "文本证据链",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_publish_summary_section(
        self,
        publish_results: Dict[str, Any],
        publish_metadata: Dict[str, Any],
        publish_source: Dict[str, Any],
    ) -> DossierSection:
        deliverables = self._extract_text_items(publish_results.get("deliverables"))
        parts = [
            (
                "交付概览："
                f"论文 {self._coerce_int(publish_metadata.get('publication_count'), len(self._as_dict_list(publish_results.get('publications'))))} 篇，"
                f"交付物 {self._coerce_int(publish_metadata.get('deliverable_count'), len(deliverables))} 项，"
                f"引用 {self._coerce_int(publish_metadata.get('citation_count'), len(self._as_dict_list(publish_results.get('citations'))))} 条。"
            )
        ]
        review_summary = publish_results.get("paper_review_summary")
        if not isinstance(review_summary, dict):
            review_summary = publish_metadata.get("paper_review_summary") if isinstance(publish_metadata.get("paper_review_summary"), dict) else {}
        if not review_summary:
            review_summary = publish_source.get("paper_review_summary") if isinstance(publish_source.get("paper_review_summary"), dict) else {}
        parts.extend(self._summarize_mapping(
            review_summary,
            preferred_keys=("final_score", "rounds_completed", "accepted"),
            heading="论文评审摘要",
        ))
        if deliverables:
            parts.append("关键交付物：")
            parts.extend(f"- {item}" for item in deliverables[:6])

        return self._build_phase_text_section(
            "publish",
            "publish_summary",
            "投稿摘要",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_publish_paper_digest_section(
        self,
        publish_results: Dict[str, Any],
        publish_source: Dict[str, Any],
    ) -> DossierSection:
        paper_draft = publish_results.get("paper_draft") if isinstance(publish_results.get("paper_draft"), dict) else {}
        if not paper_draft:
            paper_draft = publish_source.get("paper_draft") if isinstance(publish_source.get("paper_draft"), dict) else {}
        sections = paper_draft.get("sections") if isinstance(paper_draft.get("sections"), list) else []
        parts: list[str] = []
        title = self._first_non_empty_text(paper_draft.get("title"), publish_results.get("title"))
        abstract = self._first_non_empty_text(paper_draft.get("abstract"))
        if title:
            parts.append(f"标题：{title}")
        if abstract:
            parts.append(f"摘要：{_truncate(abstract, 260)}")
        if sections:
            parts.append("章节压缩：")
            for section in sections[:5]:
                if not isinstance(section, dict):
                    continue
                section_title = self._first_non_empty_text(section.get("title"), section.get("section_type"), section.get("type"))
                content = self._first_non_empty_text(section.get("content"))
                if section_title or content:
                    parts.append(f"- {section_title or '未命名章节'}: {_truncate(content, 120)}")

        return self._build_phase_text_section(
            "publish",
            "paper_digest",
            "论文初稿",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_publish_reference_digest_section(
        self,
        publish_results: Dict[str, Any],
        publish_metadata: Dict[str, Any],
    ) -> DossierSection:
        parts: list[str] = []
        formatted_references = self._first_non_empty_text(
            publish_results.get("formatted_references"),
            publish_results.get("gbt7714"),
        )
        if formatted_references:
            parts.append("参考文献摘录：")
            parts.extend(f"- {line.strip()}" for line in formatted_references.splitlines()[:8] if line.strip())
        citation_count = self._coerce_int(publish_metadata.get("citation_count"), len(self._as_dict_list(publish_results.get("citations"))), default=0)
        if citation_count:
            parts.append(f"引用记录数：{citation_count}")

        return self._build_phase_text_section(
            "publish",
            "reference_digest",
            "证据与引用",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_publish_artifact_digest_section(self, publish_results: Dict[str, Any]) -> DossierSection:
        research_artifact = publish_results.get("research_artifact") if isinstance(publish_results.get("research_artifact"), dict) else {}
        analysis_results = publish_results.get("analysis_results") if isinstance(publish_results.get("analysis_results"), dict) else {}
        llm_analysis_context = analysis_results.get("llm_analysis_context") if isinstance(analysis_results.get("llm_analysis_context"), dict) else {}

        parts = self._summarize_mapping(
            research_artifact,
            preferred_keys=("summary", "hypothesis_audit_summary", "similar_formula_graph_evidence_summary"),
            heading="研究产物摘要",
        )
        parts.extend(self._summarize_mapping(
            analysis_results,
            preferred_keys=("summary", "analysis_summary", "limitations"),
            heading="分析结果摘要",
        ))
        module_presence = llm_analysis_context.get("module_presence") if isinstance(llm_analysis_context.get("module_presence"), dict) else {}
        if module_presence:
            populated_modules = [name for name, present in module_presence.items() if present]
            parts.append(f"LLM 分析模块：{', '.join(populated_modules[:8])}" if populated_modules else "LLM 分析模块：无")

        return self._build_phase_text_section(
            "publish",
            "artifact_digest",
            "结构化产物",
            "\n".join(parts),
            item_count=len(parts),
        )

    def _build_publish_output_digest_section(self, publish_results: Dict[str, Any]) -> DossierSection:
        output_files = publish_results.get("output_files") if isinstance(publish_results.get("output_files"), dict) else {}
        lines = [f"- {name}: {path}" for name, path in output_files.items() if str(path or "").strip()]
        return self._build_phase_text_section(
            "publish",
            "output_digest",
            "输出文件",
            "\n".join(lines),
            item_count=len(lines),
        )

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    def _extract_phase_records(cycle: Any) -> Dict[str, Dict[str, Any]]:
        """从 ResearchCycle 提取阶段记录。"""
        executions = getattr(cycle, "phase_executions", None) or {}
        records: Dict[str, Dict[str, Any]] = {}
        for key, value in executions.items():
            phase_name = key.value if hasattr(key, "value") else str(key)
            records[phase_name] = value if isinstance(value, dict) else {}
        return records

    def _section_budget(self, section_name: str) -> int:
        ratio = self.budget_ratios.get(section_name, 0.1)
        return max(32, int(self.max_context_tokens * ratio))

    def _resolve_phase_max_context_tokens(self, phase_name: str) -> int:
        return self.phase_max_context_tokens.get(phase_name, self.max_context_tokens)

    def _phase_section_budget(self, phase_name: str, section_name: str) -> int:
        phase_budget = self._resolve_phase_max_context_tokens(phase_name)
        phase_ratios = _PHASE_DOSSIER_BUDGET_RATIOS.get(phase_name, {})
        ratio = phase_ratios.get(section_name, 0.15)
        return max(32, int(phase_budget * ratio))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 token 数（中英混合启发式）。"""
        if not text:
            return 0
        cn_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        en_chars = len(text) - cn_chars
        return int(
            math.ceil(cn_chars / _CHARS_PER_TOKEN_CN)
            + math.ceil(en_chars / _CHARS_PER_TOKEN_EN)
        )

    def _fit_budget(self, text: str, budget_tokens: int) -> tuple[str, bool]:
        """将文本截断到 token 预算以内。返回 (截断后文本, 是否被截断)。"""
        est = self._estimate_tokens(text)
        if est <= budget_tokens:
            return text, False

        # 按比例截断字符
        ratio = budget_tokens / max(est, 1)
        target_chars = int(len(text) * ratio * 0.95)  # 留 5% 余量
        truncated_text = text[:target_chars].rsplit("\n", 1)[0]
        return truncated_text + "\n…（已截断）", True

    def _llm_compress(self, text: str, budget_tokens: int) -> Optional[str]:
        """调用 LLM 对超长文本做摘要压缩。"""
        try:
            if self._llm_service is None:
                from src.infra.llm_service import get_llm_service
                self._llm_service = get_llm_service(self.llm_purpose)
                self._llm_service.load()

            target_chars = int(budget_tokens * _CHARS_PER_TOKEN_CN)
            prompt = (
                f"请将以下研究材料压缩为不超过 {target_chars} 字的摘要，"
                "保留关键实体、证据和结论，不要遗漏重要关系：\n\n"
                f"{text[:6000]}"
            )
            result = self._llm_service.generate(
                prompt,
                system_prompt="你是中医药研究文献压缩专家。输出纯文本摘要，不要添加格式标记。",
            )
            return result.strip() if result else None
        except Exception as exc:
            logger.warning("LLM 摘要压缩失败，回退到截断: %s", exc)
            return None

    def _build_text_section(
        self,
        name: str,
        content: str,
        item_count: int,
        token_budget: int,
    ) -> DossierSection:
        if self.enable_llm_summarization and self._estimate_tokens(content) > token_budget:
            compressed = self._llm_compress(content, token_budget)
            if compressed:
                return DossierSection(
                    name=name,
                    content=compressed,
                    item_count=item_count,
                    truncated=True,
                    token_budget=token_budget,
                )

        content, truncated = self._fit_budget(content, token_budget)
        return DossierSection(
            name=name,
            content=content,
            item_count=item_count,
            truncated=truncated,
            token_budget=token_budget,
        )

    def _build_phase_text_section(
        self,
        phase_name: str,
        section_name: str,
        display_name: str,
        content: str,
        *,
        item_count: int,
    ) -> DossierSection:
        return self._build_text_section(
            display_name,
            content,
            item_count,
            self._phase_section_budget(phase_name, section_name),
        )

    def _finalize_dossier(
        self,
        dossier: ResearchDossier,
        *,
        dossier_kind: str,
        source_phases: Sequence[str],
    ) -> ResearchDossier:
        total = 0
        for sec in dossier.sections:
            sec.estimated_tokens = self._estimate_tokens(sec.content)
            total += sec.estimated_tokens
        dossier.total_estimated_tokens = total
        dossier.metadata = {
            "builder_version": "1.2",
            "dossier_kind": dossier_kind,
            "source_phases": list(source_phases),
            "max_context_tokens": dossier.max_context_tokens,
            "enable_llm_summarization": self.enable_llm_summarization,
            "section_count": len(dossier.sections),
            "non_empty_section_count": sum(1 for s in dossier.sections if s.content.strip()),
        }
        logger.info(
            "ResearchDossier 构建完成: cycle=%s, kind=%s, sections=%d, estimated_tokens=%d / budget=%d",
            dossier.cycle_id,
            dossier_kind,
            len(dossier.sections),
            total,
            dossier.max_context_tokens,
        )
        return dossier

    @staticmethod
    def _resolve_phase_result_payload(record: Any) -> Dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        if is_phase_result_payload(record):
            return record

        nested = record.get("result")
        if isinstance(nested, dict):
            if is_phase_result_payload(nested):
                return nested
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            return {
                "phase": str(record.get("phase") or "").strip(),
                "status": str(record.get("status") or "completed").strip() or "completed",
                "results": nested,
                "metadata": metadata,
                "error": record.get("error"),
            }

        results = record.get("results")
        if isinstance(results, dict):
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            return {
                "phase": str(record.get("phase") or "").strip(),
                "status": str(record.get("status") or "completed").strip() or "completed",
                "results": results,
                "metadata": metadata,
                "error": record.get("error"),
            }
        return {}

    def _resolve_phase_results_payload(self, record: Any) -> Dict[str, Any]:
        payload = self._resolve_phase_result_payload(record)
        results = get_phase_results(payload)
        if isinstance(results, dict) and results:
            return results
        if isinstance(payload.get("results"), dict):
            return payload.get("results")
        return {}

    def _resolve_phase_metadata_payload(self, record: Any) -> Dict[str, Any]:
        payload = self._resolve_phase_result_payload(record)
        metadata = payload.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _resolve_cycle_phase_dossier_source(cycle: Any, phase_name: str) -> Dict[str, Any]:
        metadata = getattr(cycle, "metadata", None) or {}
        if not isinstance(metadata, dict):
            return {}
        phase_sources = metadata.get("phase_dossier_sources")
        if not isinstance(phase_sources, dict):
            return {}
        payload = phase_sources.get(phase_name)
        return payload if isinstance(payload, dict) else {}

    def _collect_evidence_lines(self, records: Dict[str, Dict[str, Any]]) -> List[str]:
        evidence_items: list[str] = []
        for record in records.values():
            results = self._resolve_phase_results_payload(record)
            for ev in self._collect_dict_list(
                results.get("evidence_records"),
                self._resolve_nested_dict(results, "evidence_protocol").get("evidence_records"),
                self._resolve_nested_dict(results, "reasoning_results").get("evidence_records"),
                self._resolve_nested_dict(results, "analysis_results").get("evidence_protocol", {}).get("evidence_records") if isinstance(self._resolve_nested_dict(results, "analysis_results").get("evidence_protocol"), dict) else [],
                self._resolve_nested_dict(results, "research_artifact").get("evidence"),
            ):
                grade = self._first_non_empty_text(ev.get("evidence_grade"), ev.get("grade"))
                excerpt = self._first_non_empty_text(ev.get("excerpt"), ev.get("text"), ev.get("summary"))
                source = self._first_non_empty_text(ev.get("source_entity"), ev.get("source"), ev.get("subject"))
                target = self._first_non_empty_text(ev.get("target_entity"), ev.get("target"), ev.get("object"))
                rel = self._first_non_empty_text(ev.get("relation_type"), ev.get("relation"), ev.get("predicate"))
                line = f"[{grade}] {source} → {rel} → {target}" if any((source, rel, target)) else f"[{grade}] {_truncate(excerpt, 120)}"
                if excerpt and excerpt not in line:
                    line += f" | {_truncate(excerpt, 120)}"
                evidence_items.append(line.strip())
        return evidence_items

    def _collect_entity_items(self, records: Dict[str, Dict[str, Any]]) -> List[tuple[str, str]]:
        entity_set: dict[str, str] = {}
        for record in records.values():
            results = self._resolve_phase_results_payload(record)
            entities = self._collect_dict_list(
                results.get("entities"),
                results.get("extracted_entities"),
                self._resolve_nested_dict(results, "analysis_results").get("entities"),
                self._resolve_nested_dict(results, "research_artifact").get("entities"),
            )
            for ent in entities:
                name = self._first_non_empty_text(ent.get("text"), ent.get("name"), ent.get("entity"))
                etype = self._first_non_empty_text(ent.get("type"), ent.get("entity_type"), "unknown")
                if name:
                    entity_set[name] = etype
        return sorted(entity_set.items())

    def _collect_terminology_lines(self, terminology: Optional[List[Dict[str, Any]]]) -> List[str]:
        lines: list[str] = []
        for term_entry in terminology or []:
            if not isinstance(term_entry, dict):
                continue
            term = self._first_non_empty_text(
                term_entry.get("term"),
                term_entry.get("canonical_term"),
                term_entry.get("canonical"),
                term_entry.get("name"),
            )
            definition = self._first_non_empty_text(
                term_entry.get("definition"),
                term_entry.get("label"),
                term_entry.get("notes"),
            )
            if term:
                lines.append(f"- **{term}**: {definition}" if definition else f"- **{term}**")
        return lines

    def _collect_corpus_parts(
        self,
        records: Dict[str, Dict[str, Any]],
        corpus_excerpts: Optional[List[str]],
    ) -> List[str]:
        parts: list[str] = []
        for phase_name, record in records.items():
            results = self._resolve_phase_results_payload(record)
            summary = self._first_non_empty_text(
                results.get("summary"),
                results.get("analysis_summary"),
                results.get("description"),
            )
            if summary:
                parts.append(f"[{phase_name}] {_truncate(summary, 300)}")

        for idx, excerpt in enumerate(corpus_excerpts or []):
            if isinstance(excerpt, str) and excerpt.strip():
                parts.append(f"[语料 {idx + 1}] {_truncate(excerpt, 300)}")
        return parts

    @staticmethod
    def _resolve_nested_dict(results: Dict[str, Any], key: str) -> Dict[str, Any]:
        direct = results.get(key)
        if isinstance(direct, dict):
            return direct
        nested = results.get("analysis_results")
        if isinstance(nested, dict):
            value = nested.get(key)
            if isinstance(value, dict):
                return value
        nested = results.get("research_artifact")
        if isinstance(nested, dict):
            value = nested.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _collect_dict_list(*candidates: Any) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            for item in candidate:
                if isinstance(item, dict):
                    collected.append(item)
        return collected

    @staticmethod
    def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _extract_text_items(value: Any) -> List[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if not isinstance(value, list):
            return []

        items: List[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            elif isinstance(item, dict):
                text = ResearchDossierBuilder._first_non_empty_text(
                    item.get("summary"),
                    item.get("description"),
                    item.get("text"),
                    item.get("name"),
                    item.get("title"),
                )
                if text:
                    items.append(text)
        return items

    @staticmethod
    def _summarize_mapping(
        payload: Mapping[str, Any] | None,
        *,
        preferred_keys: Sequence[str]=(),
        heading: str="",
        max_items: int=6,
    ) -> List[str]:
        if not isinstance(payload, Mapping) or not payload:
            return []

        lines: List[str] = []
        if heading:
            lines.append(f"{heading}：")

        emitted_keys: set[str] = set()
        for key in [*preferred_keys, *payload.keys()]:
            if key in emitted_keys or key not in payload:
                continue
            emitted_keys.add(key)
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    continue
            elif isinstance(value, (int, float, bool)):
                text = str(value)
            else:
                continue
            lines.append(f"- {key}: {_truncate(text, 100)}")
            if len(lines) >= max_items + (1 if heading else 0):
                break
        return lines

    @staticmethod
    def _first_non_empty_text(*values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float)):
                return str(value)
        return ""

    @staticmethod
    def _coerce_int(*values: Any, default: int = 0) -> int:
        for value in values:
            try:
                coerced = int(value)
            except (TypeError, ValueError):
                continue
            return coerced
        return default


# ── 工具函数 ─────────────────────────────────────────────────────────────────


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
