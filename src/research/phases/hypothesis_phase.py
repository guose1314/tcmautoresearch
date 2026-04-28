from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

from src.research.evidence_contract import build_phase_evidence_protocol
from src.research.graph_assets import (
    build_graph_assets_payload,
    build_hypothesis_subgraph,
)
from src.research.hypothesis_engine import (
    DEFAULT_HYPOTHESIS_EVIDENCE_GRADE,
    HYPOTHESIS_EVIDENCE_GRADES,
    METHODOLOGY_TAGS,
)
from src.research.learning_strategy import (
    StrategyApplicationTracker,
    resolve_learning_strategy,
)
from src.research.phase_result import build_phase_result, get_phase_value
from src.research.reasoning_template_selector import select_reasoning_framework
from src.storage.graph_interface import IKnowledgeGraph
from src.storage.neo4j_driver import create_knowledge_graph

try:
    from src.research.theoretical_framework import (
        HypothesisStatus,
        ResearchDomain,
        ResearchHypothesis,
        TheoreticalFramework,
    )
except Exception:
    HypothesisStatus = None
    ResearchDomain = None
    ResearchHypothesis = None
    TheoreticalFramework = None


def _validate_hypothesis_methodology_contract(hypotheses: List[Dict[str, Any]]) -> None:
    """T2.4 契约校验：每条 hypothesis 必须带合法的 methodology_tag 与 evidence_grade。

    methodology_tag 为必填且必须落在 ``METHODOLOGY_TAGS`` 中。
    evidence_grade 允许 None（视作 ``DEFAULT_HYPOTHESIS_EVIDENCE_GRADE``），
    但若提供则必须落在 ``HYPOTHESIS_EVIDENCE_GRADES`` 中。
    任何违规都会抛 ValueError 让 phase 退出码非 0。
    """

    for index, item in enumerate(hypotheses or []):
        if not isinstance(item, dict):
            raise ValueError(
                f"hypothesis[{index}] must be a dict for methodology validation, got {type(item).__name__}"
            )
        tag = item.get("methodology_tag")
        if tag is None or tag == "":
            raise ValueError(
                f"hypothesis[{index}] missing required methodology_tag; "
                f"allowed values: {METHODOLOGY_TAGS}"
            )
        if tag not in METHODOLOGY_TAGS:
            raise ValueError(
                f"hypothesis[{index}] invalid methodology_tag={tag!r}; "
                f"allowed values: {METHODOLOGY_TAGS}"
            )
        grade = item.get("evidence_grade", DEFAULT_HYPOTHESIS_EVIDENCE_GRADE)
        if grade is None or grade == "":
            continue
        if grade not in HYPOTHESIS_EVIDENCE_GRADES:
            raise ValueError(
                f"hypothesis[{index}] invalid evidence_grade={grade!r}; "
                f"allowed values: {HYPOTHESIS_EVIDENCE_GRADES}"
            )


class HypothesisPhaseMixin:
    """Mixin: hypothesis 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_hypothesis_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        self._hypothesis_tracker = StrategyApplicationTracker("hypothesis", context, self.pipeline.config)
        hypothesis_context = self._build_hypothesis_context(cycle, context)
        result = self.pipeline.hypothesis_engine.execute(hypothesis_context)
        hypotheses = result.get("hypotheses") or []
        # T2.4: methodology_tag 必填 + evidence_grade 校验，失败立即抛错（phase 退出码非 0）
        _validate_hypothesis_methodology_contract(hypotheses)
        metadata = result.setdefault("metadata", {})
        result["phase"] = "hypothesis"
        result.setdefault("validation_iterations", [])
        result.setdefault("domain", hypothesis_context.get("research_domain") or "integrative_research")
        metadata.setdefault("hypothesis_count", len(hypotheses))
        metadata.setdefault("validation_iteration_count", len(result.get("validation_iterations") or []))
        metadata.setdefault(
            "selected_hypothesis_id",
            str((hypotheses[0] or {}).get("hypothesis_id") if hypotheses else ""),
        )
        metadata.setdefault("used_llm_generation", any(item.get("generation_mode") == "llm" for item in hypotheses))
        metadata.setdefault("used_llm_closed_loop", False)
        metadata.setdefault("llm_iteration_count", 0)
        # Phase I-4: 若没有任何 LLM 生成的假设（rules-only 或全部 fallback），写入 fallback 质量元数据
        if not metadata.get("used_llm_generation"):
            from src.quality.quality_assessor import build_phase_fallback_metadata

            hypothesis_count = len(hypotheses)
            # 经验阈值：3 条及以上规则推导假设视为质量充足
            fallback_quality = round(min(1.0, hypothesis_count / 3.0), 4)
            action_label = "skip" if hypothesis_count == 0 else "retry_simplified"
            reason_extra = "rules_only_generation"
            fallback_meta = build_phase_fallback_metadata(
                action=action_label,
                baseline_score=1.0,
                optimized_score=fallback_quality,
                reason_extra=reason_extra,
            )
            metadata.setdefault("fallback_path", "rules_engine")
            metadata.update(
                {
                    "fallback_quality_score": fallback_meta["fallback_quality_score"],
                    "fallback_acceptance": fallback_meta["fallback_acceptance"],
                    "fallback_reason": fallback_meta["fallback_reason"],
                    "fallback_quality_matrix": fallback_meta["fallback_quality_matrix"],
                }
            )
        # 记录推理框架选择
        reasoning_fw = hypothesis_context.get("reasoning_framework")
        if reasoning_fw is not None:
            metadata["reasoning_framework"] = reasoning_fw.to_dict() if hasattr(reasoning_fw, "to_dict") else str(reasoning_fw)
        # Phase J-4: 对 top hypothesis 文本执行 self-refine，写入 quality delta 元数据
        try:
            from src.research.self_refine import (
                build_self_refine_metadata,
                run_self_refine,
            )

            top = next(
                (h for h in hypotheses if isinstance(h, dict)),
                None,
            )
            top_text = ""
            if top is not None:
                top_text = str(
                    top.get("statement")
                    or top.get("description")
                    or top.get("hypothesis_text")
                    or top.get("title")
                    or ""
                ).strip()
            if top_text:
                refine_result = run_self_refine(top_text)
                metadata.update(build_self_refine_metadata(refine_result))
        except Exception:
            # self-refine 任何故障都不能阻断 hypothesis 阶段
            pass
        if hasattr(self, "_hypothesis_tracker"):
            metadata["learning"] = self._hypothesis_tracker.to_metadata()
            self.pipeline.register_phase_learning_manifest(
                {"phase": "hypothesis", **self._hypothesis_tracker.to_metadata()}
            )
        phase_payload = dict(result)
        hypothesis_subgraph = build_hypothesis_subgraph(cycle.cycle_id, hypotheses)
        graph_assets = build_graph_assets_payload(hypothesis_subgraph=hypothesis_subgraph)
        metadata.setdefault("graph_asset_subgraphs", sorted(key for key in graph_assets.keys() if key != "summary"))
        metadata.setdefault("graph_asset_node_count", int(hypothesis_subgraph.get("node_count") or 0))
        metadata.setdefault("graph_asset_edge_count", int(hypothesis_subgraph.get("edge_count") or 0))
        evidence_protocol = build_phase_evidence_protocol(
            "hypothesis",
            claims=[
                {
                    "claim_id": h.get("hypothesis_id") or "",
                    "claim_text": h.get("statement") or h.get("description") or h.get("hypothesis_text") or "",
                    "claim_type": "hypothesis",
                    "source_entity": (h.get("source_entities") or [""])[0] if isinstance(h, dict) else "",
                    "target_entity": h.get("title") or h.get("statement") or "",
                    "relation_type": "proposes",
                }
                for h in hypotheses if isinstance(h, dict)
            ],
            evidence_grade="hypothesis",
            evidence_summary={"phase": "hypothesis", "hypothesis_count": len(hypotheses)},
        )
        return build_phase_result(
            "hypothesis",
            status=str(result.get("status") or ("completed" if hypotheses else "degraded")),
            results={
                "hypotheses": hypotheses,
                "validation_iterations": result.get("validation_iterations") or [],
                "domain": result.get("domain") or hypothesis_context.get("research_domain") or "integrative_research",
                "selected_hypothesis_id": metadata.get("selected_hypothesis_id", ""),
                "evidence_protocol": evidence_protocol,
                "graph_assets": graph_assets,
            },
            artifacts=result.get("artifacts"),
            metadata=metadata,
            error=result.get("error"),
            extra_fields=phase_payload,
        )

    def _build_hypothesis_context(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        existing_hypotheses = get_phase_value(
            cycle.phase_executions.get(self.pipeline.ResearchPhase.HYPOTHESIS, {}).get("result", {}),
            "hypotheses",
            [],
        )
        learning_strategy = resolve_learning_strategy(context, self.pipeline.config)

        observations = get_phase_value(observe_result, "observations", [])
        findings = get_phase_value(observe_result, "findings", [])
        literature_pipeline = get_phase_value(observe_result, "literature_pipeline", {}) or {}
        corpus_collection = get_phase_value(observe_result, "corpus_collection", {}) or {}
        ingestion_pipeline = get_phase_value(observe_result, "ingestion_pipeline", {}) or {}

        entities = context.get("entities") or ingestion_pipeline.get("entities") or corpus_collection.get("entities") or []
        contradictions = context.get("contradictions") or observe_result.get("contradictions") or []
        literature_titles = self._extract_hypothesis_literature_titles(literature_pipeline, context)
        semantic_relationships = self._extract_hypothesis_relationships(ingestion_pipeline, context)
        reasoning_summary = self._extract_hypothesis_reasoning_summary(ingestion_pipeline, context)
        knowledge_graph = self._build_hypothesis_knowledge_graph(
            entities,
            {
                **context,
                "relationships": semantic_relationships,
            },
        )
        knowledge_gap = context.get("knowledge_gap") or self._derive_hypothesis_knowledge_gap(knowledge_graph, entities)

        # ---- 推理结构自发现：选择最匹配的推理框架 ----
        reasoning_framework = select_reasoning_framework(
            getattr(cycle, "research_objective", "") or context.get("research_objective") or "",
            {
                "entities": entities,
                "knowledge_gap": knowledge_gap,
                "research_domain": context.get("research_domain") or self._infer_hypothesis_domain(cycle, observations, findings),
                "research_scope": getattr(cycle, "research_scope", "") or context.get("research_scope") or "",
                "learning_strategy": learning_strategy,
                "reasoning_framework": context.get("reasoning_framework"),
            },
            force_framework=context.get("force_reasoning_framework"),
        )
        
        dynamic_few_shot = ""
        if hasattr(self.pipeline, "self_learning_engine") and self.pipeline.self_learning_engine:
            dynamic_few_shot = self.pipeline.self_learning_engine.get_dynamic_few_shot_examples(limit=3)

        return {
            "research_objective": cycle.research_objective or context.get("research_objective") or cycle.description,
            "research_scope": cycle.research_scope or context.get("research_scope") or "",
            "research_domain": context.get("research_domain") or self._infer_hypothesis_domain(cycle, observations, findings),
            "observations": observations,
            "findings": findings,
            "entities": entities,
            "literature_titles": literature_titles,
            "literature_pipeline": literature_pipeline,
            "contradictions": contradictions,
            "relationships": semantic_relationships,
            "reasoning_summary": reasoning_summary,
            "knowledge_patterns": (reasoning_summary.get("knowledge_patterns") or {}),
            "inference_confidence": float(reasoning_summary.get("inference_confidence") or 0.0),
            "existing_hypotheses": existing_hypotheses,
            "use_llm_generation": self._resolve_hypothesis_use_llm_generation(context, learning_strategy),
            "llm_service": context.get("llm_service"),
            "knowledge_graph": knowledge_graph,
            "knowledge_gap": knowledge_gap,
            "learning_strategy": learning_strategy,
            "reasoning_framework": reasoning_framework,
            "reasoning_guidance": reasoning_framework.hypothesis_guidance,
            "dynamic_few_shot": dynamic_few_shot,
        }

    def _resolve_hypothesis_use_llm_generation(
        self,
        context: Dict[str, Any],
        learning_strategy: Dict[str, Any],
    ) -> bool:
        if "use_llm_generation" in context:
            adjusted = bool(context.get("use_llm_generation"))
            reason = "explicit_context"
        elif "hypothesis_use_llm_generation" in learning_strategy:
            adjusted = bool(learning_strategy.get("hypothesis_use_llm_generation"))
            reason = "hypothesis_use_llm_generation_in_strategy"
        elif "use_llm_generation" in learning_strategy:
            adjusted = bool(learning_strategy.get("use_llm_generation"))
            reason = "use_llm_generation_in_strategy"
        else:
            adjusted = False
            reason = "default_false"
        if hasattr(self, "_hypothesis_tracker"):
            self._hypothesis_tracker.record(
                "use_llm_generation", False, adjusted, reason,
            )
        return adjusted

    def _extract_hypothesis_reasoning_summary(
        self,
        ingestion_pipeline: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        explicit_summary = context.get("reasoning_summary")
        if isinstance(explicit_summary, dict) and explicit_summary:
            return explicit_summary
        aggregate_summary = (ingestion_pipeline.get("aggregate") or {}).get("reasoning_summary") or {}
        if isinstance(aggregate_summary, dict) and aggregate_summary:
            return aggregate_summary
        document_summaries = [
            item.get("reasoning_summary")
            for item in (ingestion_pipeline.get("documents") or [])
            if isinstance(item, dict) and isinstance(item.get("reasoning_summary"), dict)
        ]
        return self._merge_reasoning_summaries([item for item in document_summaries if item])

    def _extract_hypothesis_relationships(
        self,
        ingestion_pipeline: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        explicit_relationships = context.get("relationships") or context.get("relations")
        if isinstance(explicit_relationships, list) and explicit_relationships:
            return self._deduplicate_relationships([item for item in explicit_relationships if isinstance(item, dict)])

        aggregate_relationships = (ingestion_pipeline.get("aggregate") or {}).get("semantic_relationships") or []
        if isinstance(aggregate_relationships, list) and aggregate_relationships:
            return self._deduplicate_relationships([item for item in aggregate_relationships if isinstance(item, dict)])

        document_relationships: List[Dict[str, Any]] = []
        for document in ingestion_pipeline.get("documents") or []:
            if not isinstance(document, dict):
                continue
            document_relationships.extend(
                item for item in (document.get("semantic_relationships") or []) if isinstance(item, dict)
            )
        return self._deduplicate_relationships(document_relationships)

    def _extract_hypothesis_literature_titles(
        self,
        literature_pipeline: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[str]:
        titles = context.get("literature_titles")
        if isinstance(titles, list) and titles:
            return [str(item) for item in titles if str(item).strip()]
        records = literature_pipeline.get("records") or []
        return [str(item.get("title")) for item in records if isinstance(item, dict) and item.get("title")]

    def _build_hypothesis_knowledge_graph(
        self,
        entities: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> IKnowledgeGraph:
        graph = create_knowledge_graph(preload_formulas=False)
        normalized_entities: List[Dict[str, Any]] = []
        for item in entities:
            if isinstance(item, dict) and item.get("name"):
                normalized_entities.append(item)
                graph.add_entity(item)
            elif item:
                entity_payload = {"name": str(item), "type": "generic"}
                normalized_entities.append(entity_payload)
                graph.add_entity(entity_payload)

        for relation in context.get("relationships") or context.get("relations") or []:
            self._add_hypothesis_relation(graph, relation)

        type_map: Dict[str, List[str]] = {}
        for item in normalized_entities:
            entity_type = str(item.get("type") or "generic").lower()
            type_map.setdefault(entity_type, []).append(str(item.get("name")))

        self._add_first_pair_relation(graph, type_map, "formula", "herb", "contains")
        self._add_first_pair_relation(graph, type_map, "formula", "syndrome", "treats")
        self._add_first_pair_relation(graph, type_map, "herb", "efficacy", "efficacy")
        self._add_first_pair_relation(graph, type_map, "syndrome", "target", "associated_target")
        self._add_first_pair_relation(graph, type_map, "target", "pathway", "participates_in")
        self._add_first_pair_relation(graph, type_map, "herb", "pathway", "participates_in")
        return graph

    def _add_hypothesis_relation(self, graph: IKnowledgeGraph, relation: Any) -> None:
        if isinstance(relation, dict):
            src = relation.get("source") or relation.get("src")
            dst = relation.get("target") or relation.get("dst")
            rel_type = relation.get("type") or relation.get("rel_type")
            if src and dst and rel_type:
                source_type = str(relation.get("source_type") or "").strip()
                target_type = str(relation.get("target_type") or "").strip()
                if source_type:
                    graph.add_entity({"name": str(src), "type": source_type})
                if target_type:
                    graph.add_entity({"name": str(dst), "type": target_type})
                graph.add_relation(str(src), str(rel_type), str(dst), relation.get("metadata") or {})
            return
        if isinstance(relation, (list, tuple)) and len(relation) >= 3:
            src, rel_type, dst = relation[:3]
            metadata = relation[3] if len(relation) >= 4 and isinstance(relation[3], dict) else {}
            graph.add_relation(str(src), str(rel_type), str(dst), metadata)

    def _add_first_pair_relation(
        self,
        graph: IKnowledgeGraph,
        type_map: Dict[str, List[str]],
        source_type: str,
        target_type: str,
        relation_type: str,
    ) -> None:
        sources = type_map.get(source_type) or []
        targets = type_map.get(target_type) or []
        if not sources or not targets:
            return
        source = sources[0]
        target = targets[0]
        if hasattr(graph, 'neighbors') and target in graph.neighbors(source, relation_type):
            return
        graph.add_relation(source, relation_type, target, {"inferred": True, "source": "pipeline_hypothesis_context"})

    def _derive_hypothesis_knowledge_gap(
        self,
        graph: IKnowledgeGraph,
        entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        type_map: Dict[str, List[str]] = {}
        for item in entities:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            type_map.setdefault(str(item.get("type") or "generic").lower(), []).append(str(item.get("name")))

        candidate_pairs = [
            ("formula", "efficacy"),
            ("formula", "pathway"),
            ("herb", "syndrome"),
            ("syndrome", "pathway"),
        ]
        for source_type, target_type in candidate_pairs:
            sources = type_map.get(source_type) or []
            targets = type_map.get(target_type) or []
            if not sources or not targets:
                continue
            source = sources[0]
            target = targets[0]
            if graph.query_path(source, target) and target not in graph.neighbors(source):
                return {
                    "gap_type": "missing_direct_relation",
                    "entity": source,
                    "entity_type": source_type,
                    "description": f"存在 {source} 到 {target} 的图谱路径，但缺少直接关系。",
                    "entities": [source, target],
                    "severity": "high",
                }

        gaps = graph.find_gaps()
        if gaps:
            first_gap = gaps[0]
            return {
                "gap_type": first_gap.gap_type,
                "entity": first_gap.entity,
                "entity_type": first_gap.entity_type,
                "description": first_gap.description,
                "entities": [first_gap.entity],
                "severity": first_gap.severity,
            }

        if entities:
            first_entity = entities[0]
            name = str(first_entity.get("name") or "研究对象") if isinstance(first_entity, dict) else str(first_entity)
            entity_type = str(first_entity.get("type") or "generic") if isinstance(first_entity, dict) else "generic"
            return {
                "gap_type": "insufficient_graph_relation",
                "entity": name,
                "entity_type": entity_type,
                "description": f"围绕 {name} 缺少足够图谱关系，需生成探索性假设。",
                "entities": [name],
                "severity": "medium",
            }

        return {
            "gap_type": "insufficient_graph_relation",
            "entity": "研究对象",
            "entity_type": "generic",
            "description": "当前上下文缺少足够图谱关系，需生成探索性假设。",
            "entities": ["研究对象"],
            "severity": "medium",
        }

    def _infer_hypothesis_domain(
        self,
        cycle: "ResearchCycle",
        observations: list[str],
        findings: list[str],
    ) -> str:
        text_blob = " ".join(
            [
                cycle.research_scope or "",
                cycle.research_objective or "",
                cycle.description or "",
                *observations,
                *findings,
            ]
        )
        if any(token in text_blob for token in ["历史", "古籍", "朝代", "演变"]):
            return "historical_research"
        if any(token in text_blob for token in ["方剂", "配伍", "处方"]):
            return "formula_research"
        if any(token in text_blob for token in ["药物", "药材", "本草"]):
            return "herb_research"
        return "integrative_research"

    def _resolve_selected_hypothesis(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
        hypothesis_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.HYPOTHESIS, {}).get("result", {})
        hypotheses = get_phase_value(hypothesis_result, "hypotheses", []) or []
        explicit_id = str(context.get("selected_hypothesis_id") or "").strip()
        selected_id = explicit_id or str((hypothesis_result.get("metadata") or {}).get("selected_hypothesis_id") or "").strip()
        selected = None
        if selected_id:
            selected = next((item for item in hypotheses if item.get("hypothesis_id") == selected_id), None)
        if selected is None and hypotheses:
            selected = hypotheses[0]
            selected_id = str(selected.get("hypothesis_id") or "").strip()
        return selected, {
            "selected_hypothesis_id": selected_id,
            "hypothesis_count": len(hypotheses),
            "selection_source": "context" if explicit_id else "hypothesis_phase",
        }
