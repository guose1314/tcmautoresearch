from __future__ import annotations

import re
from math import erfc, sqrt
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from src.research.data_miner import StatisticalDataMiner
from src.research.evidence_contract import build_evidence_protocol
from src.research.graph_assets import (
    build_evidence_subgraph,
    build_graph_assets_payload,
)
from src.research.hypothesis_engine import (
    DEFAULT_HYPOTHESIS_EVIDENCE_GRADE,
    HYPOTHESIS_EVIDENCE_GRADES,
    METHODOLOGY_TAGS,
)
from src.research.learning_strategy import (
    StrategyApplicationTracker,
    has_learning_strategy,
    resolve_learning_flag,
    resolve_learning_strategy,
    resolve_numeric_learning_parameter,
)
from src.research.phase_result import build_phase_result, get_phase_value
from src.research.reasoning_template_selector import select_reasoning_framework
from src.research.tcm_reasoning import (
    TCM_REASONING_CONTRACT_VERSION,
    TCMReasoningPremise,
    build_tcm_reasoning_metadata,
    run_tcm_reasoning,
)
from src.research.textual_criticism import (
    VERDICT_CONTRACT_VERSION,
    build_textual_criticism_summary,
    normalize_authenticity_verdicts,
)

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

try:
    from src.quality import EvidenceGrader
except Exception:
    EvidenceGrader = None


_HERB_DRIVEN_SYNDROME_PREFERENCES: tuple[tuple[str, str], ...] = (("火麻仁", "中风"),)


def _resolve_analyze_methodology(
    context: Dict[str, Any],
    cycle: "ResearchCycle",
) -> Dict[str, str]:
    """T2.4: 推断 analyze 阶段的 methodology_tag 与 evidence_grade。

    优先取 context 显式覆盖；缺省按研究目标启发式选择 methodology_tag，
    evidence_grade 默认 ``DEFAULT_HYPOTHESIS_EVIDENCE_GRADE``。
    """

    explicit_tag = (context.get("methodology_tag") or "").strip().lower()
    if explicit_tag in METHODOLOGY_TAGS:
        tag = explicit_tag
    else:
        objective = str(
            getattr(cycle, "research_objective", "")
            or context.get("research_objective")
            or ""
        ).lower()
        if any(
            token in objective
            for token in ("校勘", "训诂", "philolog", "version", "异文")
        ):
            tag = "philology"
        elif any(
            token in objective
            for token in ("分类", "本草", "classification", "taxonomy", "category")
        ):
            tag = "classification"
        else:
            tag = "evidence_based"

    explicit_grade = context.get("methodology_evidence_grade") or context.get(
        "hypothesis_evidence_grade"
    )
    if explicit_grade in HYPOTHESIS_EVIDENCE_GRADES:
        grade = explicit_grade
    else:
        grade = DEFAULT_HYPOTHESIS_EVIDENCE_GRADE
    return {"methodology_tag": tag, "evidence_grade": grade}


def _validate_analyze_methodology_contract(methodology: Dict[str, Any]) -> None:
    """T2.4 契约校验：analyze 输出的 methodology 块必须合法。失败时让 phase 退出码非 0。"""

    if not isinstance(methodology, dict):
        raise ValueError(
            f"analyze.methodology must be a dict, got {type(methodology).__name__}"
        )
    tag = methodology.get("methodology_tag")
    if tag not in METHODOLOGY_TAGS:
        raise ValueError(
            f"analyze.methodology.methodology_tag invalid={tag!r}; allowed={METHODOLOGY_TAGS}"
        )
    grade = methodology.get("evidence_grade")
    if grade is None or grade == "":
        return
    if grade not in HYPOTHESIS_EVIDENCE_GRADES:
        raise ValueError(
            f"analyze.methodology.evidence_grade invalid={grade!r}; allowed={HYPOTHESIS_EVIDENCE_GRADES}"
        )


class AnalyzePhaseMixin:
    """Mixin: analyze 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_analyze_phase(
        self, cycle: "ResearchCycle", context: Dict[str, Any]
    ) -> Dict[str, Any]:
        context = context or {}
        self._analyze_tracker = StrategyApplicationTracker(
            "analyze", context, self.pipeline.config
        )

        # ---- 推理结构自发现 ----
        reasoning_framework = select_reasoning_framework(
            getattr(cycle, "research_objective", "")
            or context.get("research_objective")
            or "",
            context,
            force_framework=context.get("force_reasoning_framework"),
        )
        context.setdefault("reasoning_framework", reasoning_framework)
        context.setdefault(
            "analyze_evidence_priority", reasoning_framework.analyze_evidence_priority
        )

        significance_level = self._resolve_analyze_significance_level(context)
        analyze_records = self._collect_analyze_records(cycle, context)
        analyze_relationships = self._collect_analyze_relationships(cycle, context)
        reasoning_results = self._run_analyze_reasoning(context, analyze_relationships)
        data_mining_result = self._build_analyze_data_mining_result(analyze_records)
        analysis_results = self._build_analyze_results(
            analyze_records,
            reasoning_results,
            data_mining_result,
            context,
        )
        literature_records = self._collect_analyze_literature_records(cycle, context)

        evidence_grade_payload, evidence_grade_error = self._grade_analyze_evidence(
            cycle,
            context,
            literature_records=literature_records,
        )
        if evidence_grade_payload:
            analysis_results["evidence_grade"] = evidence_grade_payload
            analysis_results["evidence_grade_summary"] = (
                self._build_evidence_grade_summary(evidence_grade_payload)
            )
            analysis_results["statistical_analysis"]["evidence_grade"] = (
                evidence_grade_payload
            )
            analysis_results["statistical_analysis"]["evidence_grade_summary"] = (
                analysis_results["evidence_grade_summary"]
            )

        evidence_protocol = build_evidence_protocol(
            reasoning_results,
            evidence_records=literature_records,
            evidence_grade=evidence_grade_payload,
        )
        if evidence_protocol:
            evidence_protocol.setdefault("phase_origin", "analyze")
            analysis_results["evidence_protocol"] = evidence_protocol

        textual_evidence_summary = self._extract_textual_evidence_summary(cycle)
        if textual_evidence_summary:
            analysis_results["textual_evidence_summary"] = textual_evidence_summary
        textual_criticism = self._extract_textual_criticism(cycle, context)
        textual_criticism_summary = (
            textual_criticism.get("summary") if textual_criticism else {}
        )
        if textual_criticism:
            analysis_results["textual_criticism"] = textual_criticism
            analysis_results["textual_criticism_summary"] = textual_criticism_summary
        graph_rag = self._prepare_analyze_graph_rag_context(context, cycle)
        tcm_reasoning = self._run_analyze_tcm_reasoning(
            cycle,
            context,
            analyze_records,
            analyze_relationships,
        )
        if tcm_reasoning:
            analysis_results["tcm_reasoning"] = tcm_reasoning

        # T2.4: methodology contract — methodology_tag 必填 + evidence_grade 默认 'C'
        methodology = _resolve_analyze_methodology(context, cycle)
        _validate_analyze_methodology_contract(methodology)
        analysis_results["methodology"] = methodology

        cycle_id = str(getattr(cycle, "cycle_id", "") or "analyze-cycle")
        evidence_subgraph = (
            build_evidence_subgraph(
                cycle_id,
                evidence_protocol,
                phase="analyze",
            )
            if evidence_protocol
            else {}
        )
        if evidence_subgraph:
            analysis_results["graph_assets"] = build_graph_assets_payload(
                evidence_subgraph=evidence_subgraph
            )

        metadata = {
            "analysis_type": "statistical_analysis",
            "significance_level": significance_level,
            "analysis_modules": self._resolve_analyze_modules(
                reasoning_results, data_mining_result
            ),
            "record_count": len(analyze_records),
            "minimum_sample_size": self._resolve_analyze_min_sample_size(context),
            "syndrome_count": len(
                {
                    record.get("syndrome")
                    for record in analyze_records
                    if record.get("syndrome") and record.get("syndrome") != "unknown"
                }
            ),
            "reasoning_engine_used": bool(reasoning_results),
            "reasoning_relationship_count": len(
                (
                    (reasoning_results.get("reasoning_results") or {}).get(
                        "entity_relationships"
                    )
                    or []
                )
            ),
            "data_mining_methods": list(
                data_mining_result.get("methods_executed") or []
            ),
            "evidence_grade_generated": bool(evidence_grade_payload),
            "evidence_study_count": int(evidence_grade_payload.get("study_count") or 0)
            if evidence_grade_payload
            else 0,
            "evidence_protocol_generated": bool(evidence_protocol),
            "evidence_record_count": int(
                (
                    (evidence_protocol.get("summary") or {}).get(
                        "evidence_record_count"
                    )
                    or 0
                )
            )
            if evidence_protocol
            else 0,
            "evidence_claim_count": int(
                ((evidence_protocol.get("summary") or {}).get("claim_count") or 0)
            )
            if evidence_protocol
            else 0,
            "textual_evidence_chain_consumed": bool(textual_evidence_summary),
            "textual_evidence_chain_count": int(
                textual_evidence_summary.get("evidence_chain_count") or 0
            )
            if textual_evidence_summary
            else 0,
            "textual_criticism_consumed": bool(textual_criticism),
            "textual_criticism_verdict_count": int(
                textual_criticism_summary.get("verdict_count") or 0
            )
            if textual_criticism_summary
            else 0,
            "textual_criticism_needs_review_count": int(
                textual_criticism_summary.get("needs_review_count") or 0
            )
            if textual_criticism_summary
            else 0,
            "graph_asset_subgraphs": ["evidence_subgraph"] if evidence_subgraph else [],
            "graph_asset_node_count": int(evidence_subgraph.get("node_count") or 0)
            if evidence_subgraph
            else 0,
            "graph_asset_edge_count": int(evidence_subgraph.get("edge_count") or 0)
            if evidence_subgraph
            else 0,
            "learning_strategy_applied": has_learning_strategy(
                context, self.pipeline.config
            ),
            "reasoning_framework": reasoning_framework.to_dict(),
        }
        metadata.update(self._build_analyze_tcm_reasoning_metadata(tcm_reasoning))
        if textual_criticism:
            metadata["analysis_modules"].append("textual_criticism")
        if metadata.get("tcm_reasoning_generated"):
            metadata["analysis_modules"].append("tcm_reasoning")
        if evidence_grade_error:
            metadata["evidence_grade_error"] = evidence_grade_error
        if hasattr(self, "_analyze_tracker"):
            metadata["learning"] = self._analyze_tracker.to_metadata()
            self.pipeline.register_phase_learning_manifest(
                {"phase": "analyze", **self._analyze_tracker.to_metadata()}
            )

        metadata["graph_rag"] = graph_rag

        # T4.5: enable_self_refine=True 时，对 analyze 主结论文本调用 SelfRefineRunner
        try:
            from src.research._self_refine_t45 import (
                apply_self_refine_v2,
                resolve_enable_self_refine,
                resolve_self_refine_runner,
            )

            if resolve_enable_self_refine(context, self.pipeline.config):
                runner = resolve_self_refine_runner(context, self.pipeline)
                draft_segments: List[str] = []
                stat_summary = (
                    analysis_results.get("statistical_analysis", {}).get("summary")
                    if isinstance(analysis_results.get("statistical_analysis"), dict)
                    else None
                )
                if isinstance(stat_summary, str) and stat_summary.strip():
                    draft_segments.append(stat_summary.strip())
                evid_summary = analysis_results.get("evidence_grade_summary")
                if isinstance(evid_summary, str) and evid_summary.strip():
                    draft_segments.append(evid_summary.strip())
                if not draft_segments:
                    # fallback：把 reasoning_results 关键字段拼成短文
                    rr = (
                        reasoning_results.get("reasoning_results")
                        if isinstance(reasoning_results, dict)
                        else None
                    )
                    if isinstance(rr, dict):
                        rels = rr.get("entity_relationships") or []
                        if rels:
                            draft_segments.append(
                                f"识别 {len(rels)} 条实体关系，覆盖 {len(set((r or {}).get('source') for r in rels if isinstance(r, dict)))} 个源实体。"
                            )
                draft_text_v2 = "\n\n".join(draft_segments)
                metadata.update(
                    apply_self_refine_v2(
                        runner=runner,
                        purpose="analyze",
                        draft_text=draft_text_v2,
                        max_refine_rounds=int(
                            (context or {}).get("self_refine_max_rounds", 1)
                        ),
                    )
                )
        except Exception:
            pass

        return build_phase_result(
            "analyze",
            status="completed",
            results={
                **analysis_results,
                "reasoning_results": reasoning_results,
                "data_mining_result": data_mining_result,
            },
            metadata=metadata,
            error=evidence_grade_error,
        )

    def _apply_graph_rag(
        self,
        context: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> Dict[str, Any]:
        """T5.5: 在 SelfRefineRunner 之前先调 GraphRAG 三档检索。

                触发条件：默认遵循 ``graph_rag.default_enabled``；
                ``context["enable_graph_rag"]`` 显式为 ``False`` 时关闭。

        ``question_type`` 解析顺序：
          1. ``context["graph_rag_question_type"]`` 显式覆盖；
          2. 启发式：含 ``entity_ids`` → ``local``；含 ``topic_keys`` → ``community``；
             否则 ``global``。
        """
        if not self._resolve_analyze_graph_rag_enabled(context):
            return self._build_graph_rag_block(
                status="disabled",
                reason=self._resolve_graph_rag_disabled_reason(context),
            )
        try:
            from src.llm.graph_rag import VALID_QUESTION_TYPES, GraphRAG
        except Exception as exc:  # noqa: BLE001
            return self._build_graph_rag_block(
                status="degraded",
                reason="graph_rag_unavailable",
                error=str(exc),
            )

        rag: Any = context.get("graph_rag_runner")
        missing_driver = False
        if rag is None:
            driver = getattr(self.pipeline, "neo4j_driver", None) or context.get(
                "neo4j_driver"
            )
            missing_driver = driver is None
            token_budget = int(context.get("graph_rag_token_budget", 8000))
            rag = GraphRAG(neo4j_driver=driver, token_budget=token_budget)

        topic_keys = list(context.get("graph_rag_topic_keys") or [])
        entity_ids = list(context.get("graph_rag_entity_ids") or [])
        asset_type = str(context.get("graph_rag_asset_type") or "").strip().lower()
        question_type = (context.get("graph_rag_question_type") or "").strip().lower()
        if question_type not in VALID_QUESTION_TYPES:
            if asset_type:
                question_type = "local"
            elif entity_ids:
                question_type = "local"
            elif topic_keys:
                question_type = "community"
            else:
                question_type = "global"

        query = (
            context.get("graph_rag_query")
            or getattr(cycle, "research_objective", "")
            or context.get("research_objective", "")
        )
        try:
            result = rag.retrieve(
                question_type,
                query,
                topic_keys=topic_keys or None,
                entity_ids=entity_ids or None,
                asset_type=asset_type or None,
                cycle_id=str(
                    context.get("graph_rag_cycle_id")
                    or getattr(cycle, "cycle_id", "")
                    or ""
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return self._build_graph_rag_block(
                status="degraded",
                reason="retrieve_failed",
                scope=question_type,
                asset_type=asset_type,
                error=str(exc),
            )
        block = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if self._is_empty_graph_rag_block(block):
            block = self._build_graph_rag_block(
                status="degraded",
                reason="missing_neo4j_driver" if missing_driver else "empty_result",
                scope=question_type,
                asset_type=asset_type,
                block=block,
            )
        else:
            block = self._build_graph_rag_block(
                status="applied",
                reason="retrieved",
                scope=question_type,
                asset_type=asset_type,
                block=block,
            )
        # 写回 context 让 SelfRefineRunner 在 inputs 里看到
        context.setdefault("graph_rag_context", block)
        return block

    def _prepare_analyze_graph_rag_context(
        self,
        context: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> Dict[str, Any]:
        """Prepare GraphRAG early so Analyze substages can consume it."""
        if self._resolve_analyze_graph_rag_enabled(context):
            try:
                return self._apply_graph_rag(context, cycle)
            except Exception as exc:  # noqa: BLE001
                return self._build_graph_rag_block(
                    status="degraded",
                    reason="exception",
                    error=str(exc),
                )
        return self._build_graph_rag_block(
            status="disabled",
            reason=self._resolve_graph_rag_disabled_reason(context),
        )

    def _resolve_analyze_graph_rag_enabled(self, context: Dict[str, Any]) -> bool:
        if "enable_graph_rag" in context:
            return bool(context.get("enable_graph_rag"))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        for flag_name in ("analyze_enable_graph_rag", "enable_graph_rag"):
            if flag_name in strategy:
                return bool(strategy.get(flag_name))

        graph_rag_config = self._resolve_graph_rag_config()
        if "default_enabled" in graph_rag_config:
            return bool(graph_rag_config.get("default_enabled"))
        return True

    def _resolve_graph_rag_disabled_reason(self, context: Dict[str, Any]) -> str:
        if "enable_graph_rag" in context:
            return "explicit_context_disabled"
        strategy = resolve_learning_strategy(context, self.pipeline.config)
        if "analyze_enable_graph_rag" in strategy:
            return "strategy_analyze_disabled"
        if "enable_graph_rag" in strategy:
            return "strategy_disabled"
        return "config_default_disabled"

    def _resolve_graph_rag_config(self) -> Dict[str, Any]:
        config = getattr(self.pipeline, "config", {}) or {}
        graph_rag_config = config.get("graph_rag") if isinstance(config, dict) else {}
        return dict(graph_rag_config) if isinstance(graph_rag_config, dict) else {}

    @staticmethod
    def _build_graph_rag_block(
        *,
        status: str,
        reason: str,
        scope: str = "",
        asset_type: str = "",
        block: Dict[str, Any] | None = None,
        error: str = "",
    ) -> Dict[str, Any]:
        payload = dict(block or {})
        payload.setdefault("scope", scope or payload.get("scope") or "")
        payload.setdefault("asset_type", asset_type or payload.get("asset_type") or "")
        payload.setdefault("body", str(payload.get("body") or ""))
        payload.setdefault("token_count", int(payload.get("token_count") or 0))
        payload.setdefault("citations", list(payload.get("citations") or []))
        payload.setdefault("truncated", bool(payload.get("truncated", False)))
        payload.setdefault("traceability", dict(payload.get("traceability") or {}))
        payload["status"] = status
        payload["reason"] = reason
        if error:
            payload["error"] = error
        return payload

    @staticmethod
    def _is_empty_graph_rag_block(block: Dict[str, Any]) -> bool:
        traceability = block.get("traceability") if isinstance(block, dict) else {}
        has_traceability = AnalyzePhaseMixin._has_graph_rag_traceability(traceability)
        return not (
            str(block.get("body") or "").strip()
            or block.get("citations")
            or has_traceability
        )

    @staticmethod
    def _has_graph_rag_traceability(traceability: Any) -> bool:
        if not isinstance(traceability, dict):
            return False
        for key in ("node_ids", "relationship_ids", "source_phases", "cycle_ids"):
            values = traceability.get(key)
            if isinstance(values, list) and values:
                return True
        return bool(
            str(traceability.get("source_phase") or "").strip()
            or str(traceability.get("cycle_id") or "").strip()
        )

    def _resolve_analyze_modules(
        self,
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
    ) -> List[str]:
        modules: List[str] = []
        if reasoning_results:
            modules.append("reasoning_engine")
        if data_mining_result.get("methods_executed"):
            modules.append("statistical_data_miner")
        return modules

    def _resolve_analyze_flag(
        self,
        context: Dict[str, Any],
        flag_name: str,
        default: bool,
    ) -> bool:
        if flag_name in context:
            return bool(context.get(flag_name))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        analyze_flag_name = f"analyze_{flag_name}"
        if analyze_flag_name in strategy:
            return bool(strategy.get(analyze_flag_name))

        return resolve_learning_flag(flag_name, default, context, self.pipeline.config)

    def _resolve_analyze_significance_level(self, context: Dict[str, Any]) -> float:
        explicit_level = context.get("significance_level")
        if explicit_level is not None:
            try:
                return round(min(0.2, max(0.01, float(explicit_level))), 4)
            except (TypeError, ValueError):
                return 0.05

        if not has_learning_strategy(context, self.pipeline.config):
            return 0.05

        quality_threshold = resolve_numeric_learning_parameter(
            "quality_threshold",
            0.7,
            context,
            self.pipeline.config,
            min_value=0.3,
            max_value=0.95,
        )
        adjusted = round(min(0.1, max(0.01, 0.12 - quality_threshold * 0.1)), 4)
        if hasattr(self, "_analyze_tracker"):
            self._analyze_tracker.record(
                "significance_level",
                0.05,
                adjusted,
                f"quality_threshold={quality_threshold}",
                parameter="quality_threshold",
                parameter_value=quality_threshold,
            )
        return adjusted

    def _resolve_analyze_min_sample_size(self, context: Dict[str, Any]) -> int:
        explicit_value = context.get("minimum_sample_size")
        if explicit_value is None:
            explicit_value = context.get("min_sample_size")
        if explicit_value is not None:
            try:
                return max(1, min(int(explicit_value), 20))
            except (TypeError, ValueError):
                return 5

        if not has_learning_strategy(context, self.pipeline.config):
            return 5

        quality_threshold = resolve_numeric_learning_parameter(
            "quality_threshold",
            0.7,
            context,
            self.pipeline.config,
            min_value=0.3,
            max_value=0.95,
        )
        adjusted = max(3, min(8, int(round(2 + quality_threshold * 4))))
        if hasattr(self, "_analyze_tracker"):
            self._analyze_tracker.record(
                "min_sample_size",
                5,
                adjusted,
                f"quality_threshold={quality_threshold}",
                parameter="quality_threshold",
                parameter_value=quality_threshold,
            )
        return adjusted

    def _filter_analyze_relationships_by_confidence(
        self,
        relationships: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        explicit_threshold = context.get("analyze_confidence_threshold")
        if explicit_threshold is None and not has_learning_strategy(
            context, self.pipeline.config
        ):
            return relationships

        if explicit_threshold is None:
            confidence_threshold = resolve_numeric_learning_parameter(
                "confidence_threshold",
                0.7,
                context,
                self.pipeline.config,
                min_value=0.0,
                max_value=1.0,
            )
        else:
            try:
                confidence_threshold = min(1.0, max(0.0, float(explicit_threshold)))
            except (TypeError, ValueError):
                confidence_threshold = 0.0

        if confidence_threshold <= 0.0:
            return relationships

        filtered_relationships: List[Dict[str, Any]] = []
        for relationship in relationships:
            metadata = relationship.get("metadata") or {}
            has_explicit_confidence = (
                "confidence" in metadata or "confidence" in relationship
            )
            if not has_explicit_confidence:
                filtered_relationships.append(relationship)
                continue
            try:
                confidence = float(
                    metadata.get("confidence", relationship.get("confidence") or 0.0)
                )
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence >= confidence_threshold:
                filtered_relationships.append(relationship)
        return filtered_relationships

    def _collect_analyze_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        explicit_records = context.get("analysis_records") or context.get("records")
        if isinstance(explicit_records, list):
            normalized_records = self._normalize_analyze_records(explicit_records)
            if normalized_records:
                return normalized_records

        execution_records = self._collect_execution_stage_records(cycle)
        if execution_records:
            return execution_records

        documents = self._collect_analyze_documents(cycle, context)
        records: List[Dict[str, Any]] = []
        for index, document in enumerate(documents, start=1):
            record = self._build_analyze_record_from_document(document, index)
            if record:
                records.append(record)

        if records:
            return records

        # Fallback: 从 Hypothesis 阶段的 source_entities 合成分析记录
        return self._synthesize_records_from_hypotheses(cycle)

    def _normalize_analyze_records(self, records: List[Any]) -> List[Dict[str, Any]]:
        normalized_records: List[Dict[str, Any]] = []
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            herbs = self._unique_text_list(
                record.get("herbs") or record.get("items") or []
            )
            if not herbs:
                continue
            normalized_records.append(
                {
                    "formula": str(
                        record.get("formula")
                        or record.get("title")
                        or f"record_{index}"
                    ),
                    "syndrome": str(record.get("syndrome") or "unknown"),
                    "herbs": herbs,
                    "title": str(
                        record.get("title")
                        or record.get("formula")
                        or f"record_{index}"
                    ),
                }
            )
        return normalized_records

    def _collect_analyze_documents(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        context_documents = context.get("documents")
        if isinstance(context_documents, list):
            return [item for item in context_documents if isinstance(item, dict)]

        observe_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.OBSERVE, {}
        ).get("result", {})
        ingestion_pipeline = (
            context.get("ingestion_pipeline")
            or get_phase_value(observe_result, "ingestion_pipeline", {})
            or {}
        )
        documents = ingestion_pipeline.get("documents") or []
        return [item for item in documents if isinstance(item, dict)]

    def _build_analyze_record_from_document(
        self,
        document: Dict[str, Any],
        index: int,
    ) -> Dict[str, Any]:
        relationships = [
            item
            for item in (document.get("semantic_relationships") or [])
            if isinstance(item, dict)
        ]
        grouped_entities = self._group_relationship_entities(relationships)
        herbs = grouped_entities.get("herb") or []
        if not herbs:
            return {}

        formulas = grouped_entities.get("formula") or []
        syndromes = grouped_entities.get("syndrome") or []
        title = str(document.get("title") or document.get("urn") or f"document_{index}")
        return {
            "formula": formulas[0] if formulas else title,
            "title": title,
            "syndrome": self._select_analyze_record_syndrome(syndromes, herbs),
            "herbs": herbs,
        }

    def _select_analyze_record_syndrome(
        self, syndromes: List[str], herbs: List[str]
    ) -> str:
        if not syndromes:
            return "unknown"

        herb_set = {str(item).strip() for item in herbs if str(item).strip()}
        syndrome_set = {str(item).strip() for item in syndromes if str(item).strip()}
        for herb_name, preferred_syndrome in _HERB_DRIVEN_SYNDROME_PREFERENCES:
            if herb_name in herb_set and preferred_syndrome in syndrome_set:
                return preferred_syndrome
        return syndromes[0]

    def _group_relationship_entities(
        self, relationships: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = {}
        for relationship in relationships:
            for side in ("source", "target"):
                entity_name = str(relationship.get(side) or "").strip()
                entity_type = (
                    str(relationship.get(f"{side}_type") or "generic").strip().lower()
                )
                if not entity_name:
                    continue
                grouped.setdefault(entity_type, [])
                if entity_name not in grouped[entity_type]:
                    grouped[entity_type].append(entity_name)
        return grouped

    def _collect_analyze_relationships(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        explicit_relationships = (
            context.get("relationships")
            or context.get("semantic_relationships")
            or context.get("relations")
        )
        if isinstance(explicit_relationships, list) and explicit_relationships:
            return self._deduplicate_analyze_relationships(
                [item for item in explicit_relationships if isinstance(item, dict)]
            )

        execution_relationships = self._collect_execution_stage_relationships(cycle)
        if execution_relationships:
            return execution_relationships

        observe_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.OBSERVE, {}
        ).get("result", {})
        ingestion_pipeline = (
            context.get("ingestion_pipeline")
            or get_phase_value(observe_result, "ingestion_pipeline", {})
            or {}
        )
        aggregate_relationships = (ingestion_pipeline.get("aggregate") or {}).get(
            "semantic_relationships"
        ) or []
        if isinstance(aggregate_relationships, list) and aggregate_relationships:
            return self._deduplicate_analyze_relationships(
                [item for item in aggregate_relationships if isinstance(item, dict)]
            )

        relationships: List[Dict[str, Any]] = []
        for document in self._collect_analyze_documents(cycle, context):
            relationships.extend(
                item
                for item in (document.get("semantic_relationships") or [])
                if isinstance(item, dict)
            )

        if relationships:
            return self._deduplicate_analyze_relationships(relationships)

        # Fallback: 从 Hypothesis 阶段的 source_entities 合成关系
        return self._synthesize_relationships_from_hypotheses(cycle)

    def _collect_execution_stage_records(
        self, cycle: "ResearchCycle"
    ) -> List[Dict[str, Any]]:
        execution_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.EXPERIMENT_EXECUTION,
            {},
        ).get("result", {})
        if not isinstance(execution_result, dict):
            return []

        for key in (
            "analysis_records",
            "execution_records",
            "imported_records",
            "result_records",
            "records",
        ):
            candidate = get_phase_value(execution_result, key, []) or []
            if not isinstance(candidate, list):
                continue
            normalized_records = self._normalize_analyze_records(candidate)
            if normalized_records:
                return normalized_records

        documents = get_phase_value(execution_result, "documents", []) or []
        if not isinstance(documents, list):
            return []

        records: List[Dict[str, Any]] = []
        for index, document in enumerate(documents, start=1):
            if not isinstance(document, dict):
                continue
            record = self._build_analyze_record_from_document(document, index)
            if record:
                records.append(record)
        return records

    def _collect_execution_stage_relationships(
        self, cycle: "ResearchCycle"
    ) -> List[Dict[str, Any]]:
        execution_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.EXPERIMENT_EXECUTION,
            {},
        ).get("result", {})
        if not isinstance(execution_result, dict):
            return []

        for key in (
            "analysis_relationships",
            "execution_relationships",
            "imported_relationships",
            "semantic_relationships",
            "relationships",
        ):
            candidate = get_phase_value(execution_result, key, []) or []
            if isinstance(candidate, list) and candidate:
                return self._deduplicate_analyze_relationships(
                    [item for item in candidate if isinstance(item, dict)]
                )

        documents = get_phase_value(execution_result, "documents", []) or []
        if not isinstance(documents, list):
            return []

        relationships: List[Dict[str, Any]] = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            relationships.extend(
                item
                for item in (document.get("semantic_relationships") or [])
                if isinstance(item, dict)
            )
        if not relationships:
            return []
        return self._deduplicate_analyze_relationships(relationships)

    def _deduplicate_analyze_relationships(
        self, relationships: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        deduplicated: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for relationship in relationships:
            source = str(relationship.get("source") or "").strip()
            target = str(relationship.get("target") or "").strip()
            relation_type = str(
                relationship.get("type") or relationship.get("rel_type") or "related_to"
            ).strip()
            if not source or not target:
                continue

            key = (source, target, relation_type)
            metadata = relationship.get("metadata") or {}
            candidate_confidence = float(metadata.get("confidence") or 0.0)
            candidate_priority = int(
                self._RELATION_SOURCE_PRIORITY.get(str(metadata.get("source") or ""), 0)
            )
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = relationship
                continue

            existing_metadata = existing.get("metadata") or {}
            existing_confidence = float(existing_metadata.get("confidence") or 0.0)
            existing_priority = int(
                self._RELATION_SOURCE_PRIORITY.get(
                    str(existing_metadata.get("source") or ""), 0
                )
            )
            if (candidate_priority, candidate_confidence) >= (
                existing_priority,
                existing_confidence,
            ):
                deduplicated[key] = relationship

        return list(deduplicated.values())

    def _run_analyze_reasoning(
        self,
        context: Dict[str, Any],
        relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self._resolve_analyze_flag(context, "run_reasoning", True):
            return {}

        filtered_relationships = self._filter_analyze_relationships_by_confidence(
            relationships, context
        )
        explicit_graph = context.get("semantic_graph")
        semantic_graph = (
            explicit_graph
            if isinstance(explicit_graph, dict)
            else self._build_analyze_semantic_graph(filtered_relationships)
        )
        explicit_entities = self._normalize_analyze_entities(context.get("entities"))
        inferred_entities = self._build_entities_from_relationships(
            filtered_relationships
        )
        entities = self._merge_analyze_entities(explicit_entities, inferred_entities)

        if (
            not entities
            or not isinstance(semantic_graph, dict)
            or not (semantic_graph.get("edges") or [])
        ):
            raw_text = context.get("raw_text") or context.get("input_data", {}).get(
                "raw_text"
            )
            if raw_text and isinstance(raw_text, str):
                self.pipeline.logger.info(
                    "Analyze 阶段未获取到预处理实体与关系，启动内置 Fallback 抽取流程..."
                )
                try:
                    preprocessor = self.pipeline.analysis_port.create_preprocessor(
                        context.get("preprocessor_config")
                    )
                    extractor = self.pipeline.analysis_port.create_extractor(
                        context.get("extractor_config")
                    )
                    semantic_builder = (
                        self.pipeline.analysis_port.create_semantic_builder(
                            context.get("semantic_builder_config")
                        )
                    )

                    if (
                        preprocessor.initialize()
                        and extractor.initialize()
                        and semantic_builder.initialize()
                    ):
                        fallback_ctx = {"raw_text": raw_text}
                        fallback_ctx = preprocessor.execute(fallback_ctx)
                        fallback_ctx = extractor.execute(fallback_ctx)
                        fallback_ctx = semantic_builder.execute(fallback_ctx)

                        fb_entities = fallback_ctx.get("entities", [])
                        fb_graph = fallback_ctx.get("semantic_graph", {})
                        fb_rels = (
                            fb_graph.get("edges", [])
                            if isinstance(fb_graph, dict)
                            else []
                        )

                        if fb_entities and fb_rels:
                            entities = fb_entities
                            semantic_graph = fb_graph
                            self.pipeline.logger.info(
                                "Fallback 抽取成功：获取到 %d 个实体，%d 条关系",
                                len(entities),
                                len(fb_rels),
                            )
                except Exception as exc:
                    self.pipeline.logger.warning(
                        "Analyze 阶段 Fallback 降级抽取失败: %s", exc
                    )

        if (
            not entities
            or not isinstance(semantic_graph, dict)
            or not (semantic_graph.get("edges") or [])
        ):
            return {}

        try:
            reasoning_engine = self.pipeline.analysis_port.create_reasoning_engine(
                context.get("reasoning_engine_config") or {}
            )
        except Exception as exc:
            self.pipeline.logger.warning(
                "Analyze 阶段无法创建 ReasoningEngine: %s", exc
            )
            return {}

        try:
            if not reasoning_engine.initialize():
                self.pipeline.logger.warning(
                    "Analyze 阶段 ReasoningEngine 初始化失败，跳过推理分析"
                )
                return {}
            return reasoning_engine.execute(
                {
                    "entities": entities,
                    "semantic_graph": semantic_graph,
                }
            )
        except Exception as exc:
            self.pipeline.logger.warning(
                "Analyze 阶段 ReasoningEngine 执行失败: %s", exc
            )
            return {}
        finally:
            reasoning_engine.cleanup()

    def _normalize_analyze_entities(self, entities: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(entities, list):
            return normalized
        for item in entities:
            if isinstance(item, dict) and item.get("name"):
                normalized.append(
                    {
                        "name": str(item.get("name")),
                        "type": str(item.get("type") or "generic").lower(),
                        "confidence": float(item.get("confidence") or 0.0),
                    }
                )
            elif item:
                normalized.append(
                    {"name": str(item), "type": "generic", "confidence": 0.0}
                )
        return normalized

    def _build_entities_from_relationships(
        self, relationships: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        entity_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for relationship in relationships:
            metadata = relationship.get("metadata") or {}
            confidence = float(metadata.get("confidence") or 0.0)
            for side in ("source", "target"):
                entity_name = str(relationship.get(side) or "").strip()
                entity_type = (
                    str(relationship.get(f"{side}_type") or "generic").strip().lower()
                )
                if not entity_name:
                    continue
                key = (entity_name, entity_type)
                current = entity_map.get(key)
                if current is None or confidence > float(
                    current.get("confidence") or 0.0
                ):
                    entity_map[key] = {
                        "name": entity_name,
                        "type": entity_type,
                        "confidence": confidence,
                    }
        return list(entity_map.values())

    def _merge_analyze_entities(
        self,
        primary_entities: List[Dict[str, Any]],
        secondary_entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for entity in primary_entities + secondary_entities:
            entity_name = str(entity.get("name") or "").strip()
            entity_type = str(entity.get("type") or "generic").strip().lower()
            if not entity_name:
                continue
            key = entity_name
            current = merged.get(key)
            candidate_confidence = float(entity.get("confidence") or 0.0)
            candidate = {
                "name": entity_name,
                "type": entity_type,
                "confidence": candidate_confidence,
            }
            if current is None:
                merged[key] = candidate
                continue
            current_confidence = float(current.get("confidence") or 0.0)
            if current.get("type") == "generic" and entity_type != "generic":
                merged[key] = candidate
            elif candidate_confidence > current_confidence:
                merged[key] = candidate
        return list(merged.values())

    def _build_analyze_semantic_graph(
        self, relationships: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        node_map: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        for relationship in relationships:
            source_name = str(relationship.get("source") or "").strip()
            source_type = (
                str(relationship.get("source_type") or "generic").strip().lower()
            )
            target_name = str(relationship.get("target") or "").strip()
            target_type = (
                str(relationship.get("target_type") or "generic").strip().lower()
            )
            relation_type = str(
                relationship.get("type") or relationship.get("rel_type") or "related_to"
            ).strip()
            metadata = relationship.get("metadata") or {}
            if not source_name or not target_name:
                continue

            source_id = f"{source_type}:{source_name}"
            target_id = f"{target_type}:{target_name}"
            node_map[source_id] = {
                "id": source_id,
                "data": {"name": source_name, "type": source_type},
            }
            node_map[target_id] = {
                "id": target_id,
                "data": {"name": target_name, "type": target_type},
            }
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "attributes": {
                        "relationship_type": relation_type or "related_to",
                        "relationship_name": str(
                            metadata.get("relationship_name")
                            or relation_type
                            or "related_to"
                        ),
                        "description": str(metadata.get("description") or ""),
                        "confidence": float(metadata.get("confidence") or 0.0),
                    },
                }
            )

        return {"nodes": list(node_map.values()), "edges": edges}

    def _build_analyze_data_mining_result(
        self,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        herbs = sorted(
            {herb for record in records for herb in (record.get("herbs") or []) if herb}
        )
        transactions = [
            record.get("herbs") or [] for record in records if record.get("herbs")
        ]
        result: Dict[str, Any] = {
            "record_count": len(records),
            "transaction_count": len(transactions),
            "item_count": len(herbs),
            "methods_executed": [],
        }
        if not herbs or not records:
            result["frequency_chi_square"] = {
                "herb_frequency": [],
                "chi_square_top": [],
            }
            result["association_rules"] = {"rules": []}
            return result

        result["frequency_chi_square"] = StatisticalDataMiner.frequency_and_chi_square(
            records, herbs
        )
        result["association_rules"] = StatisticalDataMiner.association_rules(
            transactions
        )
        result["methods_executed"] = ["frequency_chi_square", "association_rules"]
        return result

    def _build_analyze_results(
        self,
        records: List[Dict[str, Any]],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        statistical_analysis = self._build_statistical_analysis(
            records, reasoning_results, data_mining_result, context
        )
        return {
            "statistical_analysis": dict(statistical_analysis),
        }

    def _build_statistical_analysis(
        self,
        records: List[Dict[str, Any]],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        chi_square_items = (data_mining_result.get("frequency_chi_square") or {}).get(
            "chi_square_top"
        ) or []
        primary_finding = self._select_primary_statistical_finding(
            records, chi_square_items
        )
        inference_confidence = float(
            (
                (reasoning_results.get("reasoning_results") or {}).get(
                    "inference_confidence"
                )
                or 0.0
            )
        )
        significance_level = self._resolve_analyze_significance_level(context)

        if not primary_finding:
            limitations = self._build_analyze_limitations(
                records,
                reasoning_results,
                has_statistical_finding=False,
                context=context,
            )
            return {
                "statistical_significance": False,
                "confidence_level": round(inference_confidence, 4),
                "effect_size": 0.0,
                "p_value": None,
                "interpretation": self._build_analyze_interpretation(
                    {}, reasoning_results, len(records)
                ),
                "limitations": limitations,
                "primary_association": {},
            }

        p_value = primary_finding.get("p_value")
        confidence_level = round(
            max(inference_confidence, 1.0 - float(p_value or 0.0)), 4
        )
        statistical_significance = bool(
            p_value is not None and float(p_value) <= significance_level
        )
        limitations = self._build_analyze_limitations(
            records, reasoning_results, has_statistical_finding=True, context=context
        )
        interpretation = self._build_analyze_interpretation(
            primary_finding, reasoning_results, len(records)
        )
        return {
            "statistical_significance": statistical_significance,
            "confidence_level": confidence_level,
            "effect_size": primary_finding.get("effect_size", 0.0),
            "p_value": p_value,
            "interpretation": interpretation,
            "limitations": limitations,
            "primary_association": primary_finding,
        }

    def _select_primary_statistical_finding(
        self,
        records: List[Dict[str, Any]],
        chi_square_items: List[Any],
    ) -> Dict[str, Any]:
        if (
            not records
            or not isinstance(chi_square_items, list)
            or not chi_square_items
        ):
            return {}

        selected = next(
            (
                item
                for item in chi_square_items
                if isinstance(item, dict)
                and self._is_positive_statistical_candidate(records, item)
            ),
            None,
        )
        if not isinstance(selected, dict):
            return {}

        herb = str(selected.get("herb") or "").strip()
        syndrome = str(selected.get("syndrome") or "").strip()
        if not herb or not syndrome:
            return {}

        a, b, c, d = StatisticalDataMiner._build_contingency_counts(
            records, herb, syndrome
        )
        chi2, p_value = StatisticalDataMiner._compute_chi_square(a, b, c, d)
        normalized_p_value = self._normalize_p_value(p_value, float(chi2))
        sample_size = a + b + c + d
        effect_size = self._compute_phi_effect_size(float(chi2), sample_size)
        return {
            "herb": herb,
            "syndrome": syndrome,
            "chi2": round(float(chi2), 4),
            "p_value": normalized_p_value,
            "effect_size": effect_size,
            "sample_size": sample_size,
            "contingency_table": {"a": a, "b": b, "c": c, "d": d},
        }

    def _is_positive_statistical_candidate(
        self,
        records: List[Dict[str, Any]],
        candidate: Dict[str, Any],
    ) -> bool:
        herb = str(candidate.get("herb") or "").strip()
        syndrome = str(candidate.get("syndrome") or "").strip()
        if not herb or not syndrome:
            return False

        a, _, _, _ = StatisticalDataMiner._build_contingency_counts(
            records, herb, syndrome
        )
        return a > 0

    def _normalize_p_value(self, raw_p_value: Any, chi2: float) -> float | None:
        if raw_p_value is not None:
            try:
                return round(float(raw_p_value), 6)
            except (TypeError, ValueError):
                return None
        if chi2 < 0:
            return None
        return round(float(erfc(sqrt(chi2 / 2.0))), 6)

    def _compute_phi_effect_size(self, chi2: float, sample_size: int) -> float:
        if sample_size <= 0 or chi2 <= 0:
            return 0.0
        return round(float(sqrt(chi2 / sample_size)), 4)

    def _build_analyze_interpretation(
        self,
        primary_finding: Dict[str, Any],
        reasoning_results: Dict[str, Any],
        record_count: int,
    ) -> str:
        reasoning_payload = (
            (reasoning_results.get("reasoning_results") or {})
            if isinstance(reasoning_results, dict)
            else {}
        )
        knowledge_patterns = reasoning_payload.get("knowledge_patterns") or {}
        common_entities = [
            str(item)
            for item in (knowledge_patterns.get("common_entities") or [])
            if str(item).strip()
        ]

        if not primary_finding:
            if common_entities:
                return f"当前样本不足以形成稳定统计显著性，但 ReasoningEngine 已识别出 {'、'.join(common_entities[:3])} 等高频核心实体，可作为下一轮实验验证线索。"
            if record_count <= 0:
                return "当前缺少可用的结构化观察记录，Analyze 阶段仅完成最小化结果汇总，尚不能给出可靠统计推断。"
            return "当前可用记录不足以支撑稳定的卡方检验结果，建议补充 Observe 阶段的结构化实体与关系数据。"

        herb = primary_finding.get("herb") or "目标药物"
        syndrome = primary_finding.get("syndrome") or "目标证候"
        p_value = primary_finding.get("p_value")
        effect_size = primary_finding.get("effect_size")
        interpretation = (
            f"基于 {record_count} 条结构化观察记录，{herb} 与 {syndrome} 的关联被识别为当前最强统计信号"
            f"（p={p_value}, 效应量={effect_size}）。"
        )
        if common_entities:
            interpretation += f" ReasoningEngine 同时在知识图谱中归纳出 {'、'.join(common_entities[:3])} 等关键实体共现模式，支持该关联具有结构性解释。"
        return interpretation

    def _build_analyze_limitations(
        self,
        records: List[Dict[str, Any]],
        reasoning_results: Dict[str, Any],
        has_statistical_finding: bool,
        context: Dict[str, Any],
    ) -> List[str]:
        limitations: List[str] = []
        minimum_sample_size = self._resolve_analyze_min_sample_size(context)
        if len(records) < minimum_sample_size:
            limitations.append(
                f"可用于统计检验的结构化记录数量偏少（当前 {len(records)}，建议至少 {minimum_sample_size}），显著性结论稳定性有限"
            )
        syndrome_count = len(
            {
                record.get("syndrome")
                for record in records
                if record.get("syndrome") and record.get("syndrome") != "unknown"
            }
        )
        if syndrome_count < 2:
            limitations.append("证候分层不足，当前只能进行有限的二分类统计比较")
        if not reasoning_results:
            limitations.append("缺少可复用的语义图关系或推理结果，结构性解释仍不充分")
        if not has_statistical_finding:
            limitations.append(
                "当前数据尚不足以产出稳定的主统计关联，建议先增强 Observe 阶段的实体与关系覆盖"
            )
        return limitations or [
            "当前分析基于自动抽取结果，仍需结合专家复核与外部证据验证"
        ]

    def _unique_text_list(self, values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        unique_values: List[str] = []
        for item in values:
            text = str(item).strip()
            if text and text not in unique_values:
                unique_values.append(text)
        return unique_values

    def _grade_analyze_evidence(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_records: List[Any] | None = None,
    ) -> tuple[Dict[str, Any], str]:
        if not self._resolve_analyze_flag(context, "grade_evidence", True):
            return {}, ""

        records = list(
            literature_records
            or self._collect_analyze_literature_records(cycle, context)
        )
        if not records:
            return {}, ""

        try:
            grader = self._create_evidence_grader()
            return grader.grade_evidence(records).to_dict(), ""
        except Exception as exc:
            self.pipeline.logger.warning("Analyze 阶段 GRADE 证据分级失败: %s", exc)
            return {}, str(exc)

    def _collect_analyze_literature_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Any]:
        observe_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.OBSERVE, {}
        ).get("result", {})
        context_literature_pipeline = context.get("literature_pipeline")

        candidates = [
            context.get("literature_records"),
            context_literature_pipeline.get("records")
            if isinstance(context_literature_pipeline, dict)
            else None,
            (get_phase_value(observe_result, "literature_pipeline", {}) or {}).get(
                "records"
            )
            if isinstance(observe_result, dict)
            else None,
        ]
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            records = [item for item in candidate if item is not None]
            if records:
                return records
        return []

    def _build_evidence_grade_summary(
        self, evidence_grade: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(evidence_grade, dict) or not evidence_grade:
            return {}

        bias_distribution: Dict[str, int] = {}
        for key, value in (evidence_grade.get("bias_risk_distribution") or {}).items():
            try:
                bias_distribution[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

        factor_averages: Dict[str, float] = {}
        for key, value in (evidence_grade.get("factor_averages") or {}).items():
            try:
                factor_averages[str(key)] = round(float(value), 4)
            except (TypeError, ValueError):
                continue

        summary_lines = [
            str(item).strip()
            for item in (evidence_grade.get("summary") or [])
            if str(item).strip()
        ]

        try:
            overall_score = round(float(evidence_grade.get("overall_score") or 0.0), 4)
        except (TypeError, ValueError):
            overall_score = 0.0

        study_results = evidence_grade.get("study_results") or []
        study_count = evidence_grade.get("study_count") or len(study_results)
        try:
            normalized_study_count = int(study_count)
        except (TypeError, ValueError):
            normalized_study_count = 0

        return {
            "overall_grade": str(evidence_grade.get("overall_grade") or ""),
            "overall_score": overall_score,
            "study_count": normalized_study_count,
            "factor_averages": factor_averages,
            "bias_risk_distribution": bias_distribution,
            "summary": summary_lines,
        }

    def _extract_textual_evidence_summary(
        self, cycle: "ResearchCycle"
    ) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.OBSERVE, {}
        ).get("result", {})
        if not isinstance(observe_result, dict):
            return {}
        philology_assets = get_phase_value(observe_result, "philology_assets", {})
        if not isinstance(philology_assets, dict):
            return {}
        evidence_chains = philology_assets.get("evidence_chains") or []
        if not evidence_chains:
            return {}
        conflict_claims = philology_assets.get("conflict_claims") or []
        evidence_chain_count = int(
            philology_assets.get("evidence_chain_count") or len(evidence_chains)
        )
        conflict_count = int(
            philology_assets.get("conflict_count") or len(conflict_claims)
        )
        needs_review_count = sum(
            1 for c in evidence_chains if c.get("needs_manual_review")
        )
        high_confidence_count = sum(
            1 for c in evidence_chains if (c.get("confidence") or 0) >= 0.60
        )
        return {
            "evidence_chain_count": evidence_chain_count,
            "conflict_count": conflict_count,
            "needs_review_count": needs_review_count,
            "high_confidence_count": high_confidence_count,
        }

    def _extract_textual_criticism(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.OBSERVE, {}
        ).get("result", {})
        candidates = [context.get("textual_criticism")]
        if isinstance(observe_result, dict):
            candidates.append(get_phase_value(observe_result, "textual_criticism", {}))

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            verdicts = candidate.get("verdicts") or candidate.get(
                "authenticity_verdicts"
            )
            normalized = normalize_authenticity_verdicts(verdicts or [])
            if not normalized:
                continue
            return {
                "verdicts": normalized,
                "summary": build_textual_criticism_summary(normalized),
                "contract_version": str(
                    candidate.get("contract_version") or VERDICT_CONTRACT_VERSION
                ),
                "source_phase": "observe",
            }
        return {}

    def _run_analyze_tcm_reasoning(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        analyze_records: List[Dict[str, Any]],
        analyze_relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self._resolve_analyze_flag(context, "run_tcm_reasoning", True):
            return {}

        premises = self._build_analyze_tcm_reasoning_premises(
            context,
            analyze_records,
            analyze_relationships,
        )
        if not premises:
            return {}

        seed = self._resolve_analyze_tcm_reasoning_seed(cycle, context)
        try:
            trace = run_tcm_reasoning(premises, seed=seed)
        except Exception as exc:  # noqa: BLE001 - TCM reasoning must not block analyze
            self.pipeline.logger.warning("Analyze 阶段 TCMReasoning 失败: %s", exc)
            summary = self._empty_analyze_tcm_reasoning_metadata()
            summary["tcm_reasoning_error"] = str(exc)
            return {
                "seed": seed,
                "premises": [premise.to_dict() for premise in premises],
                "steps": [],
                "overall_confidence": 0.0,
                "pattern_coverage": [],
                "notes": "TCMReasoning 执行失败，Analyze 主链已降级继续。",
                "contract_version": TCM_REASONING_CONTRACT_VERSION,
                "summary": summary,
                "degraded_reason": "tcm_reasoning_failed",
                "error": str(exc),
            }

        payload = trace.to_dict()
        payload["summary"] = build_tcm_reasoning_metadata(trace)
        return payload

    def _build_analyze_tcm_reasoning_premises(
        self,
        context: Dict[str, Any],
        analyze_records: List[Dict[str, Any]],
        analyze_relationships: List[Dict[str, Any]],
    ) -> List[TCMReasoningPremise]:
        premises: List[TCMReasoningPremise] = []
        seen: set[Tuple[str, str, str]] = set()

        def add_premise(
            premise_kind: Any,
            canonical: Any,
            *,
            label: Any = "",
            source_ref: Any = "",
            note: Any = "",
            claim_id: Any = "",
            source_phase: Any = "",
            confidence: Any = 0.0,
        ) -> None:
            kind = self._normalize_tcm_reasoning_premise_kind(premise_kind)
            text = str(canonical or "").strip()
            if not kind or not text or text == "unknown":
                return
            ref = str(source_ref or "analyze").strip() or "analyze"
            normalized_claim_id = str(claim_id or "").strip()
            key = (kind, text, normalized_claim_id or ref)
            if key in seen:
                return
            seen.add(key)
            premises.append(
                TCMReasoningPremise(
                    premise_kind=kind,
                    canonical=text,
                    label=str(label or text).strip() or text,
                    source_ref=ref,
                    note=str(note or "").strip(),
                    claim_id=normalized_claim_id,
                    source_phase=str(source_phase or "").strip(),
                    confidence=self._clamp_graph_rag_confidence(confidence),
                )
            )

        explicit_premises = (
            context.get("tcm_reasoning_premises") or context.get("tcm_premises") or []
        )
        for item in explicit_premises:
            if isinstance(item, TCMReasoningPremise):
                add_premise(
                    item.premise_kind,
                    item.canonical,
                    label=item.label,
                    source_ref=item.source_ref,
                    note=item.note,
                    claim_id=item.claim_id,
                    source_phase=item.source_phase,
                    confidence=item.confidence,
                )
            elif isinstance(item, dict):
                premise = TCMReasoningPremise.from_dict(item)
                add_premise(
                    premise.premise_kind,
                    premise.canonical,
                    label=premise.label,
                    source_ref=premise.source_ref,
                    note=premise.note,
                    claim_id=premise.claim_id,
                    source_phase=premise.source_phase,
                    confidence=premise.confidence,
                )

        for spec in self._iter_analyze_graph_rag_tcm_premise_specs(context):
            add_premise(
                spec.get("premise_kind"),
                spec.get("canonical"),
                label=spec.get("label"),
                source_ref=spec.get("source_ref"),
                note=spec.get("note"),
                claim_id=spec.get("claim_id"),
                source_phase=spec.get("source_phase"),
                confidence=spec.get("confidence"),
            )

        for index, record in enumerate(analyze_records, start=1):
            if not isinstance(record, dict):
                continue
            source_ref = str(
                record.get("title") or record.get("formula") or f"record_{index}"
            )
            add_premise("formula", record.get("formula"), source_ref=source_ref)
            add_premise("syndrome", record.get("syndrome"), source_ref=source_ref)
            for herb in record.get("herbs") or []:
                add_premise("herb", herb, source_ref=source_ref)
            for symptom in record.get("symptoms") or record.get("manifestations") or []:
                add_premise("symptom", symptom, source_ref=source_ref)

        for relationship in analyze_relationships or []:
            if not isinstance(relationship, dict):
                continue
            metadata = (
                relationship.get("metadata")
                if isinstance(relationship.get("metadata"), dict)
                else {}
            )
            source_ref = (
                relationship.get("source_ref")
                or metadata.get("source")
                or metadata.get("source_ref")
                or "analyze_relationship"
            )
            note = relationship.get("type") or relationship.get("rel_type") or ""
            for side in ("source", "target"):
                add_premise(
                    relationship.get(f"{side}_type"),
                    relationship.get(side),
                    source_ref=source_ref,
                    note=note,
                )

        for factor in self._iter_analyze_tcm_context_factors(context):
            if isinstance(factor, dict):
                add_premise(
                    factor.get("premise_kind") or "context",
                    factor.get("canonical")
                    or factor.get("value")
                    or factor.get("label"),
                    label=factor.get("label"),
                    source_ref=factor.get("source_ref") or "analyze_context",
                    note=factor.get("note") or "三因制宜上下文",
                )
            else:
                add_premise(
                    "context",
                    factor,
                    source_ref="analyze_context",
                    note="三因制宜上下文",
                )
        return premises

    def _iter_analyze_graph_rag_tcm_premise_specs(
        self,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        specs: List[Dict[str, Any]] = []
        for block in self._iter_analyze_graph_rag_blocks(context):
            asset_type = str(block.get("asset_type") or "").strip().lower()
            if asset_type not in {"claim", "evidence"}:
                continue
            traceability = block.get("traceability")
            if not isinstance(traceability, dict):
                traceability = {}
            source_phase = str(traceability.get("source_phase") or "").strip()
            if not source_phase:
                source_phases = traceability.get("source_phases") or []
                if isinstance(source_phases, list) and source_phases:
                    source_phase = str(source_phases[0] or "").strip()
            node_ids = [str(item) for item in traceability.get("node_ids") or []]
            citations = [
                item for item in block.get("citations") or [] if isinstance(item, dict)
            ]
            lines = [
                line.strip()
                for line in str(block.get("body") or "").splitlines()
                if line.strip()
            ]
            if not lines and citations:
                lines = [""] * len(citations)

            for index, line in enumerate(lines):
                parsed = self._parse_graph_rag_typed_asset_line(line)
                line_asset_type = str(parsed.get("asset_type") or asset_type).lower()
                if line_asset_type not in {"claim", "evidence"}:
                    continue
                citation = citations[index] if index < len(citations) else {}
                node_id = (
                    parsed.get("node_id")
                    or citation.get("id")
                    or (node_ids[index] if index < len(node_ids) else "")
                    or (node_ids[0] if node_ids else "")
                )
                fields = dict(parsed.get("fields") or {})
                claim_id = (
                    fields.get("claim_id")
                    or self._derive_graph_rag_claim_id(node_id)
                    or self._derive_graph_rag_claim_id(citation.get("id"))
                )
                confidence = self._clamp_graph_rag_confidence(fields.get("confidence"))
                if confidence == 0.0:
                    confidence = self._clamp_graph_rag_confidence(
                        fields.get("score") or fields.get("weight")
                    )
                source_ref = str(claim_id or node_id or "graph_rag").strip()
                for (
                    premise_kind,
                    canonical,
                ) in self._extract_tcm_specs_from_graph_rag_fields(
                    line_asset_type,
                    fields,
                    line,
                ):
                    specs.append(
                        {
                            "premise_kind": premise_kind,
                            "canonical": canonical,
                            "label": canonical,
                            "source_ref": source_ref,
                            "note": f"GraphRAG {line_asset_type} typed asset",
                            "claim_id": claim_id,
                            "source_phase": source_phase,
                            "confidence": confidence,
                        }
                    )
        return specs

    @staticmethod
    def _iter_analyze_graph_rag_blocks(context: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = context.get("graph_rag_context") or context.get("graph_rag") or {}
        if isinstance(raw, dict):
            nested = raw.get("blocks")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
            return [raw]
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        return []

    @staticmethod
    def _parse_graph_rag_typed_asset_line(line: str) -> Dict[str, Any]:
        text = str(line or "").strip()
        match = re.match(
            r"^\[(?P<asset>[^:\]]+):(?P<node>[^\]]+)\]\s*"
            r"(?:\([^)]+\))?\s*(?P<rest>.*)$",
            text,
        )
        asset_type = ""
        node_id = ""
        rest = text
        if match:
            asset_type = str(match.group("asset") or "").strip().lower()
            node_id = str(match.group("node") or "").strip()
            rest = str(match.group("rest") or "").strip()
        fields: Dict[str, str] = {}
        for part in re.split(r"[；;]", rest):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip()
            if normalized_key and normalized_value:
                fields[normalized_key] = normalized_value
        if rest and "claim_text" not in fields and "excerpt" not in fields:
            fields["body"] = rest
        return {"asset_type": asset_type, "node_id": node_id, "fields": fields}

    @classmethod
    def _extract_tcm_specs_from_graph_rag_fields(
        cls,
        asset_type: str,
        fields: Dict[str, str],
        line: str,
    ) -> List[Tuple[str, str]]:
        specs: List[Tuple[str, str]] = []

        def add(kind: str, value: Any) -> None:
            text = str(value or "").strip()
            if text and (kind, text) not in specs:
                specs.append((kind, text))

        for key in ("formula", "formula_name", "prescription"):
            add("formula", fields.get(key))
        for key in ("syndrome", "pattern"):
            add("syndrome", fields.get(key))
        for key in ("symptom", "manifestation"):
            add("symptom", fields.get(key))
        for key in ("herb", "medicine"):
            add("herb", fields.get(key))
        for key in ("herbs", "medicines"):
            for item in cls._split_graph_rag_list(fields.get(key)):
                add("herb", item)

        source_entity = fields.get("source_entity") or fields.get("source")
        target_entity = fields.get("target_entity") or fields.get("target")
        relation_type = str(fields.get("relation_type") or "").lower()
        if cls._looks_like_formula(source_entity):
            add("formula", source_entity)
        elif source_entity and any(token in relation_type for token in ("herb", "药")):
            add("herb", source_entity)
        if target_entity:
            add("syndrome", target_entity)

        claim_text = (
            fields.get("claim_text")
            or fields.get("excerpt")
            or fields.get("title")
            or fields.get("body")
            or line
        )
        for formula in re.findall(
            r"([\u4e00-\u9fa5A-Za-z0-9]{1,20}(?:汤|散|丸|方|颗粒|胶囊))",
            claim_text,
        ):
            add("formula", formula)
        syndrome_match = re.search(
            r"(?:治疗|主治|用于|适用于)([^，,。；;]+)", claim_text
        )
        if syndrome_match:
            syndrome = syndrome_match.group(1).strip()
            if syndrome:
                add("syndrome", syndrome)
        for herb in cls._extract_herbs_from_claim_text(claim_text):
            add("herb", herb)
        return specs

    @staticmethod
    def _derive_graph_rag_claim_id(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "::" in text:
            return text.split("::")[-1].strip()
        return text

    @staticmethod
    def _clamp_graph_rag_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        if 1.0 < confidence <= 100.0:
            confidence = confidence / 100.0
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _split_graph_rag_list(value: Any) -> List[str]:
        text = str(value or "").strip()
        if not text:
            return []
        return [item.strip() for item in re.split(r"[,，、/|]+", text) if item.strip()]

    @staticmethod
    def _looks_like_formula(value: Any) -> bool:
        text = str(value or "").strip()
        return bool(re.search(r"(?:汤|散|丸|方|颗粒|胶囊)$", text))

    @classmethod
    def _extract_herbs_from_claim_text(cls, claim_text: str) -> List[str]:
        match = re.search(
            r"(?:方含|含|由|组成[:：]?)([^。；;，,]+)", str(claim_text or "")
        )
        if not match:
            return []
        herbs: List[str] = []
        for token in cls._split_graph_rag_list(match.group(1)):
            cleaned = re.sub(r"等\d*味?$", "", token).strip()
            if not cleaned or cls._looks_like_formula(cleaned):
                continue
            if cleaned.endswith("证") or "治疗" in cleaned or len(cleaned) > 8:
                continue
            herbs.append(cleaned)
        return herbs

    def _normalize_tcm_reasoning_premise_kind(self, value: Any) -> str:
        kind = str(value or "").strip().lower()
        aliases = {
            "formula": "formula",
            "prescription": "formula",
            "方剂": "formula",
            "方": "formula",
            "herb": "herb",
            "medicine": "herb",
            "药材": "herb",
            "药物": "herb",
            "syndrome": "syndrome",
            "pattern": "syndrome",
            "证候": "syndrome",
            "证": "syndrome",
            "symptom": "symptom",
            "manifestation": "symptom",
            "症状": "symptom",
            "context": "context",
            "factor": "context",
            "上下文": "context",
        }
        return aliases.get(kind, "")

    def _iter_analyze_tcm_context_factors(self, context: Dict[str, Any]) -> List[Any]:
        factors: List[Any] = []
        for key in (
            "tcm_context_factors",
            "context_factors",
            "sanyin_context",
        ):
            value = context.get(key)
            if isinstance(value, list):
                factors.extend(value)
            elif value not in (None, "", [], {}):
                factors.append(value)

        for key in ("season", "region", "location", "population", "constitution"):
            value = context.get(key)
            if value not in (None, "", [], {}):
                factors.append({"canonical": value, "label": str(value), "note": key})
        return factors

    def _resolve_analyze_tcm_reasoning_seed(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> str:
        for key in (
            "tcm_reasoning_seed",
            "research_question",
            "research_objective",
            "topic",
        ):
            value = str(context.get(key) or "").strip()
            if value:
                return value
        return str(getattr(cycle, "research_objective", "") or "").strip()

    def _build_analyze_tcm_reasoning_metadata(
        self,
        tcm_reasoning: Dict[str, Any],
    ) -> Dict[str, Any]:
        summary = (
            tcm_reasoning.get("summary")
            if isinstance(tcm_reasoning, dict)
            and isinstance(tcm_reasoning.get("summary"), dict)
            else {}
        )
        metadata = self._empty_analyze_tcm_reasoning_metadata()
        metadata.update(
            {key: value for key, value in summary.items() if key in metadata}
        )
        metadata["tcm_reasoning_generated"] = (
            bool(
                not tcm_reasoning.get("degraded_reason")
                and int(metadata.get("tcm_reasoning_step_count") or 0) > 0
            )
            if isinstance(tcm_reasoning, dict)
            else False
        )
        if isinstance(tcm_reasoning, dict) and tcm_reasoning.get("error"):
            metadata["tcm_reasoning_error"] = tcm_reasoning["error"]
        return metadata

    def _empty_analyze_tcm_reasoning_metadata(self) -> Dict[str, Any]:
        return {
            "tcm_reasoning_generated": False,
            "tcm_reasoning_step_count": 0,
            "tcm_reasoning_pattern_coverage": [],
            "tcm_reasoning_pattern_count": 0,
            "tcm_reasoning_overall_confidence": 0.0,
            "tcm_reasoning_pattern_distribution": {},
            "tcm_reasoning_premise_count": 0,
            "tcm_reasoning_notes": "",
            "tcm_reasoning_contract_version": TCM_REASONING_CONTRACT_VERSION,
        }

    # ── Hypothesis fallback: 从先前阶段合成分析数据 ──────────────

    def _synthesize_records_from_hypotheses(
        self,
        cycle: "ResearchCycle",
    ) -> List[Dict[str, Any]]:
        """从 Hypothesis 阶段的 source_entities 合成分析记录。

        当 Observe 阶段未产出 ingestion_pipeline（无语料采集）时，
        利用假设中的实体列表构建最小化分析记录，避免 Analyze 阶段空转。
        """
        hypothesis_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.HYPOTHESIS, {}
        ).get("result", {})
        hypotheses = get_phase_value(hypothesis_result, "hypotheses", []) or []
        if not hypotheses:
            return []

        records: List[Dict[str, Any]] = []
        for index, hyp in enumerate(hypotheses, start=1):
            if not isinstance(hyp, dict):
                continue
            entities = hyp.get("source_entities") or hyp.get("keywords") or []
            if not entities:
                continue
            entity_list = [str(e).strip() for e in entities if str(e).strip()]
            if not entity_list:
                continue
            records.append(
                {
                    "formula": hyp.get("title") or f"hypothesis_{index}",
                    "title": hyp.get("title") or f"hypothesis_{index}",
                    "syndrome": hyp.get("source_gap_type") or "unknown",
                    "herbs": entity_list,
                }
            )
        return records

    def _synthesize_relationships_from_hypotheses(
        self,
        cycle: "ResearchCycle",
    ) -> List[Dict[str, Any]]:
        """从 Hypothesis 阶段的 source_entities 合成语义关系。

        利用假设中实体对生成 'hypothesis_association' 类型关系，
        使 ReasoningEngine 能在此基础上进行推理分析。
        """
        hypothesis_result = cycle.phase_executions.get(
            self.pipeline.ResearchPhase.HYPOTHESIS, {}
        ).get("result", {})
        hypotheses = get_phase_value(hypothesis_result, "hypotheses", []) or []
        if not hypotheses:
            return []

        relationships: List[Dict[str, Any]] = []
        for hyp in hypotheses:
            if not isinstance(hyp, dict):
                continue
            entities = [
                str(e).strip()
                for e in (hyp.get("source_entities") or [])
                if str(e).strip()
            ]
            confidence = float(
                hyp.get("confidence") or hyp.get("evidence_support") or 0.5
            )
            # 为每对实体生成一条关系
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    relationships.append(
                        {
                            "source": entities[i],
                            "source_type": "herb",
                            "target": entities[j],
                            "target_type": "herb",
                            "type": "hypothesis_association",
                            "metadata": {
                                "confidence": confidence,
                                "source": "hypothesis_engine",
                                "hypothesis_title": hyp.get("title") or "",
                            },
                        }
                    )
        return self._deduplicate_analyze_relationships(relationships)
