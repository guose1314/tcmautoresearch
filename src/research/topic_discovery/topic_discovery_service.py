"""topic_discovery 子阶段服务实现。

主入口:
  propose_topics(seed, *, catalog_entries=None, kg=None, llm_caller=None,
                 max_proposals=5, min_proposals=3) -> list[TopicProposal]

实现策略（J-1 范围，纯规则可测）:
  1. 角度展开: 在 CANDIDATE_ANGLES 中按"中医文献研究法"优先级挑选
     min..max 个研究角度。
  2. 子问题模板化: 对每个角度生成对应中文 sub_question。
  3. 证据来源招募:
       - catalog_entries: 来自 observe / catalog_contract 的本地条目
       - kg: 任何实现 entity_count / entities_by_type 的图对象
       - 兜底: 至少 1 个 catalog 类候选，保证 source_candidates 非空
  4. 优先级评分: 角度基础分 + 证据数量加权
  5. 可选 LLM 精修: llm_caller(prompt) -> str 返回结构化文本，仅做 hint 改写

故意不依赖:
  - 真实 LLMEngine（避免单测加载 GGUF）
  - Neo4j 驱动（KG 接口面向 src.knowledge.tcm_knowledge_graph 内存图）
"""

from __future__ import annotations

from typing import Any, Callable, List, Mapping, Optional, Sequence

from src.research.topic_discovery.contract import (
    ANGLE_CATALOG_VERSION,
    ANGLE_EXEGESIS,
    ANGLE_FANGZHENG,
    ANGLE_SANYIN_ZHIYI,
    ANGLE_SCHOOL_LINEAGE,
    ANGLE_TEXTUAL_CRITICISM,
    ANGLE_TONGBING_YIZHI,
    ANGLE_YIBING_TONGZHI,
    CANDIDATE_ANGLES,
    TOPIC_PROPOSAL_MAX,
    TOPIC_PROPOSAL_MIN,
    TopicProposal,
    TopicSourceCandidate,
)

LLMCaller = Callable[[str], str]

# 角度 → (sub_question 模板, 假说提示模板, 基础优先级)
_ANGLE_TEMPLATES: dict[str, tuple[str, str, float]] = {
    ANGLE_FANGZHENG: (
        "围绕 {seed} 梳理代表方剂—证候配伍规律及其历代演变",
        "若 {seed} 的核心方证组合在不同朝代保持稳定，则其疗效机制具有方剂学一致性",
        0.85,
    ),
    ANGLE_TONGBING_YIZHI: (
        "针对 {seed} 提取同病异治范式并对比不同医家治法差异",
        "若不同医家对 {seed} 的治法在病机分型上可分类聚簇，则同病异治存在可解释规律",
        0.78,
    ),
    ANGLE_YIBING_TONGZHI: (
        "针对 {seed} 检索异病同治的方剂与证型共性",
        "若 {seed} 涉及的多病可被同一方剂有效覆盖，则异病同治存在共性病机",
        0.72,
    ),
    ANGLE_SANYIN_ZHIYI: (
        "考察 {seed} 在因时/因地/因人三维度下的治法差异",
        "若 {seed} 的治法在三因维度上存在显著差异，则三因制宜对其有可计算约束",
        0.68,
    ),
    ANGLE_TEXTUAL_CRITICISM: (
        "对 {seed} 涉及的核心古籍进行真伪/年代/作者考据",
        "若 {seed} 关键证据所依据的古籍存在伪托或断代争议，则其结论需附带版本风险声明",
        0.66,
    ),
    ANGLE_EXEGESIS: (
        "对 {seed} 涉及的关键术语进行训诂注释与古今义辨",
        "若 {seed} 的关键术语古今义存在显著漂移，则现代研究结论存在术语错置风险",
        0.62,
    ),
    ANGLE_SCHOOL_LINEAGE: (
        "梳理 {seed} 的学派流派与师承演化脉络",
        "若 {seed} 的学说可被归入若干学派且学派内部一致性高，则学派变量对结论具有解释力",
        0.58,
    ),
    ANGLE_CATALOG_VERSION: (
        "建立 {seed} 的文献目录与版本谱系并标注佚文风险",
        "若 {seed} 的核心文献版本谱系存在断裂或佚文，则需先完成辑佚再下结论",
        0.55,
    ),
}


def _normalize_seed(seed: Any) -> str:
    return str(seed or "").strip()


def _select_angles(min_count: int, max_count: int) -> list[str]:
    """按 CANDIDATE_ANGLES 顺序选出 [min..max] 个角度。"""
    bounded_min = max(1, min(min_count, len(CANDIDATE_ANGLES)))
    bounded_max = max(bounded_min, min(max_count, len(CANDIDATE_ANGLES)))
    # J-1 阶段固定取 max（在 min..max 内偏多更利于研究者挑选）
    return list(CANDIDATE_ANGLES[:bounded_max])


def _catalog_to_source(entry: Mapping[str, Any]) -> Optional[TopicSourceCandidate]:
    if not isinstance(entry, Mapping):
        return None
    catalog_id = str(
        entry.get("catalog_id") or entry.get("document_id") or entry.get("id") or ""
    ).strip()
    title = str(
        entry.get("work_title")
        or entry.get("document_title")
        or entry.get("title")
        or ""
    ).strip()
    if not catalog_id and not title:
        return None
    return TopicSourceCandidate(
        source_kind="catalog",
        source_ref=catalog_id or title,
        title=title or catalog_id,
        note="from observe catalog",
    )


def _kg_to_sources(kg: Any, *, limit: int = 3) -> list[TopicSourceCandidate]:
    if kg is None:
        return []
    sources: list[TopicSourceCandidate] = []
    # 优先方剂/证候/学派；接口对齐 TCMKnowledgeGraph.entities_by_type
    for etype in ("formula", "syndrome", "school"):
        try:
            names = list(getattr(kg, "entities_by_type", lambda *_: [])(etype) or [])
        except Exception:
            names = []
        for name in names[:limit]:
            sources.append(
                TopicSourceCandidate(
                    source_kind="kg",
                    source_ref=str(name),
                    title=str(name),
                    note=f"kg/{etype}",
                )
            )
    return sources


def _ensure_min_sources(
    sources: list[TopicSourceCandidate],
    *,
    seed: str,
) -> list[TopicSourceCandidate]:
    if sources:
        return sources
    # 兜底：用 seed 自身建一条 catalog 候选，保证下游不空集
    return [
        TopicSourceCandidate(
            source_kind="catalog",
            source_ref=f"seed::{seed}",
            title=seed,
            note="fallback seed-derived catalog stub",
        )
    ]


def _score_priority(angle: str, source_count: int) -> float:
    base = _ANGLE_TEMPLATES[angle][2]
    # 证据加权：每条证据 +0.02，封顶 +0.10
    bonus = min(0.10, 0.02 * source_count)
    return round(min(1.0, base + bonus), 4)


def _refine_hint_with_llm(
    hint: str,
    *,
    llm_caller: Optional[LLMCaller],
    seed: str,
    angle: str,
) -> str:
    if llm_caller is None:
        return hint
    prompt = (
        f"你是一位中医文献研究方法学顾问，请基于以下信息将『假说提示』改写为一句"
        f"中文的可证伪科学假设：\n"
        f"研究方向: {seed}\n"
        f"研究角度: {angle}\n"
        f"原始提示: {hint}\n"
        f"输出只给出一句，不要前后缀。"
    )
    try:
        result = llm_caller(prompt)
    except Exception:
        return hint
    refined = str(result or "").strip()
    return refined or hint


class TopicDiscoveryService:
    """topic_discovery 子阶段服务。

    使用方式:
      service = TopicDiscoveryService(catalog_entries=..., kg=..., llm_caller=...)
      proposals = service.propose("脾胃湿热证")
    """

    def __init__(
        self,
        *,
        catalog_entries: Optional[Sequence[Mapping[str, Any]]] = None,
        kg: Any = None,
        llm_caller: Optional[LLMCaller] = None,
        min_proposals: int = TOPIC_PROPOSAL_MIN,
        max_proposals: int = TOPIC_PROPOSAL_MAX,
    ) -> None:
        self._catalog_entries: list[Mapping[str, Any]] = list(catalog_entries or [])
        self._kg = kg
        self._llm_caller = llm_caller
        self._min = min_proposals
        self._max = max_proposals

    def propose(self, seed: Any) -> List[TopicProposal]:
        normalized_seed = _normalize_seed(seed)
        if not normalized_seed:
            raise ValueError("topic_discovery: seed 不能为空")

        catalog_sources: list[TopicSourceCandidate] = []
        for entry in self._catalog_entries:
            candidate = _catalog_to_source(entry)
            if candidate is not None:
                catalog_sources.append(candidate)

        kg_sources = _kg_to_sources(self._kg)

        proposals: list[TopicProposal] = []
        for angle in _select_angles(self._min, self._max):
            sub_q_tpl, hint_tpl, _base = _ANGLE_TEMPLATES[angle]
            sub_question = sub_q_tpl.format(seed=normalized_seed)
            hint = hint_tpl.format(seed=normalized_seed)
            hint = _refine_hint_with_llm(
                hint,
                llm_caller=self._llm_caller,
                seed=normalized_seed,
                angle=angle,
            )

            # 角度相关来源筛选：训诂/考据/目录类优先 catalog；其它角度兼并 KG
            if angle in (ANGLE_TEXTUAL_CRITICISM, ANGLE_EXEGESIS, ANGLE_CATALOG_VERSION):
                merged = list(catalog_sources)
            else:
                merged = list(catalog_sources) + list(kg_sources)
            merged = _ensure_min_sources(merged, seed=normalized_seed)
            # 限制每条课题最多 5 条来源，避免过载
            merged = merged[:5]

            priority = _score_priority(angle, len(merged))
            rationale = (
                f"角度『{angle}』基础分 {_ANGLE_TEMPLATES[angle][2]:.2f}，"
                f"证据数 {len(merged)} 条加权后 {priority:.2f}"
            )
            proposals.append(
                TopicProposal(
                    seed=normalized_seed,
                    sub_question=sub_question,
                    angle=angle,
                    source_candidates=merged,
                    falsifiable_hypothesis_hint=hint,
                    priority=priority,
                    rationale=rationale,
                )
            )

        # 按优先级降序，截到 max
        proposals.sort(key=lambda p: p.priority, reverse=True)
        capped = proposals[: self._max]
        if len(capped) < self._min:
            # 极端情况下兜底（CANDIDATE_ANGLES 始终 >= TOPIC_PROPOSAL_MAX，理论不会进入）
            raise RuntimeError(
                f"topic_discovery: 候选数量 {len(capped)} 少于最低 {self._min}"
            )
        return capped


def propose_topics(
    seed: Any,
    *,
    catalog_entries: Optional[Sequence[Mapping[str, Any]]] = None,
    kg: Any = None,
    llm_caller: Optional[LLMCaller] = None,
    min_proposals: int = TOPIC_PROPOSAL_MIN,
    max_proposals: int = TOPIC_PROPOSAL_MAX,
) -> List[TopicProposal]:
    """便捷函数：等价于 TopicDiscoveryService(...).propose(seed)。"""
    service = TopicDiscoveryService(
        catalog_entries=catalog_entries,
        kg=kg,
        llm_caller=llm_caller,
        min_proposals=min_proposals,
        max_proposals=max_proposals,
    )
    return service.propose(seed)


__all__ = ["TopicDiscoveryService", "propose_topics", "LLMCaller"]
