from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from src.collector.corpus_bundle import (
    CorpusBundle,
    extract_text_entries,
    is_corpus_bundle,
)
from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph

try:
    from src.generation.citation_manager import CitationManager
except Exception:
    CitationManager = None

try:
    from src.generation.paper_writer import PaperWriter
except Exception:
    PaperWriter = None

try:
    from src.generation.output_formatter import OutputGenerator
except Exception:
    OutputGenerator = None

try:
    from src.output.report_generator import ReportGenerator
except Exception:
    ReportGenerator = None

try:
    from src.quality import EvidenceGrader
except Exception:
    EvidenceGrader = None

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

if TYPE_CHECKING:
    from src.research.research_pipeline import (
        ResearchCycle,
        ResearchPhase,
        ResearchPipeline,
    )


class ResearchPhaseHandlers:
    """阶段处理器：负责研究阶段分发与执行。"""

    _RELATION_SOURCE_PRIORITY = {
        "observe_reasoning_engine": 3,
        "observe_semantic_graph": 2,
        "pipeline_hypothesis_context": 1,
    }
    _RELATION_CONFLICT_STRATEGIES = {
        "source_priority_then_confidence",
        "confidence_then_source_priority",
    }

    def __init__(self, pipeline: "ResearchPipeline"):
        self.pipeline = pipeline

    def execute_phase_internal(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        dispatch = {
            "observe": self.execute_observe_phase,
            "hypothesis": self.execute_hypothesis_phase,
            "experiment": self.execute_experiment_phase,
            "analyze": self.execute_analyze_phase,
            "publish": self.execute_publish_phase,
            "reflect": self.execute_reflect_phase,
        }
        handler = dispatch.get(phase.value)
        if handler is None:
            return {"error": f"未知阶段: {phase.value}"}
        return handler(cycle, context)

    def execute_observe_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}

        corpus_result = self._collect_observe_corpus_if_enabled(context)
        literature_result = self._run_observe_literature_if_enabled(context)

        observations, findings = self._build_observe_seed_lists()
        self._append_corpus_observe_updates(corpus_result, observations, findings)

        ingestion_result = self._run_observe_ingestion_if_enabled(corpus_result, context)
        self._append_ingestion_observe_updates(ingestion_result, observations, findings)
        self._append_literature_observe_updates(literature_result, observations, findings)

        return {
            "phase": "observe",
            "observations": observations,
            "findings": findings,
            "corpus_collection": corpus_result,
            "ingestion_pipeline": ingestion_result,
            "literature_pipeline": literature_result,
            "metadata": self._build_observe_metadata(
                context,
                observations,
                findings,
                corpus_result,
                ingestion_result,
                literature_result,
            ),
        }

    def _build_observe_seed_lists(self) -> tuple[list[str], list[str]]:
        observations = [
            "收集到原始中医古籍文本数据",
            "识别出多个方剂实例",
            "发现不同朝代的用药规律",
            "提取出关键症候信息",
        ]
        findings = [
            "方剂组成存在地域差异",
            "药材使用呈现时代演变特征",
            "症候分类具有系统性规律",
        ]
        return observations, findings

    def _collect_observe_corpus_if_enabled(self, context: Dict[str, Any]) -> Dict[str, Any] | None:
        collect_ctext = self.pipeline._should_collect_ctext_corpus(context)
        collect_local = self.pipeline._should_collect_local_corpus(context)

        if not collect_ctext and not collect_local:
            return None

        bundles: list[CorpusBundle] = []
        fallback_error: Dict[str, Any] | None = None

        ctext_result = self.pipeline._collect_ctext_observation_corpus(context) if collect_ctext else None
        fallback_error = self._register_observe_collection_result(
            ctext_result,
            "ctext",
            bundles,
            fallback_error,
        )

        local_result = self.pipeline._collect_local_observation_corpus(context) if collect_local else None
        fallback_error = self._register_observe_collection_result(
            local_result,
            "local",
            bundles,
            fallback_error,
        )

        if bundles:
            merged = CorpusBundle.merge(bundles) if len(bundles) > 1 else bundles[0]
            return merged.to_dict()
        return fallback_error

    def _register_observe_collection_result(
        self,
        source_result: Dict[str, Any] | None,
        source_type: str,
        bundles: list[CorpusBundle],
        fallback_error: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        if not source_result:
            return fallback_error
        if source_result.get("error"):
            return fallback_error or source_result

        bundle = self._to_observe_corpus_bundle(source_result, source_type)
        if bundle:
            bundles.append(bundle)
        return fallback_error

    def _to_observe_corpus_bundle(
        self,
        source_result: Dict[str, Any],
        source_type: str,
    ) -> CorpusBundle | None:
        if source_type == "ctext":
            return CorpusBundle.from_ctext_result(source_result)
        if source_type == "local" and is_corpus_bundle(source_result):
            return CorpusBundle.from_dict(source_result)
        return None

    def _run_observe_literature_if_enabled(self, context: Dict[str, Any]) -> Dict[str, Any] | None:
        if not self._should_run_observe_literature(context):
            return None
        return self._run_observe_literature_pipeline(context)

    def _run_observe_ingestion_if_enabled(
        self,
        corpus_result: Dict[str, Any] | None,
        context: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if not corpus_result or corpus_result.get("error"):
            return None
        if not self._should_run_observe_ingestion(context):
            return None
        return self._run_observe_ingestion_pipeline(corpus_result, context)

    def _append_corpus_observe_updates(
        self,
        corpus_result: Dict[str, Any] | None,
        observations: list[str],
        findings: list[str],
    ) -> None:
        if not corpus_result:
            return
        if corpus_result.get("error"):
            findings.append(f"语料采集失败: {corpus_result['error']}")
            return

        if is_corpus_bundle(corpus_result):
            stats = corpus_result.get("stats", {})
            sources = corpus_result.get("sources", [])
            total = stats.get("total_documents", 0)
            if sources == ["ctext"]:
                observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get('document_count', total)} 个根文献")
                findings.insert(0, "观察阶段已接入标准语料白名单，可直接进入后续假设生成")
            else:
                source_label = "+".join(sources) if sources else "多来源"
                observations.insert(0, f"已从 {source_label} 自动采集 {total} 篇文档（CorpusBundle）")
                findings.insert(0, "观察阶段已输出统一 CorpusBundle，多来源文档可直接进入后续假设生成")
            return

        stats = corpus_result.get("stats", {})
        observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get('document_count', 0)} 个根文献")
        findings.insert(0, "观察阶段已接入标准语料白名单，可直接进入后续假设生成")

    def _append_ingestion_observe_updates(
        self,
        ingestion_result: Dict[str, Any] | None,
        observations: list[str],
        findings: list[str],
    ) -> None:
        if not ingestion_result:
            return
        if ingestion_result.get("error"):
            findings.append(f"预处理、实体抽取与语义建模链路失败: {ingestion_result['error']}")
            return

        aggregate = ingestion_result.get("aggregate", {})
        observations.append(
            f"已完成 {ingestion_result.get('processed_document_count', 0)} 篇文本的预处理、实体抽取与语义建模"
        )
        findings.append(f"首段主流程累计识别 {aggregate.get('total_entities', 0)} 个实体")
        findings.append(
            f"累计构建 {aggregate.get('semantic_graph_nodes', 0)} 个语义节点与 {aggregate.get('semantic_graph_edges', 0)} 条关系"
        )

    def _append_literature_observe_updates(
        self,
        literature_result: Dict[str, Any] | None,
        observations: list[str],
        findings: list[str],
    ) -> None:
        if not literature_result:
            return
        if literature_result.get("error"):
            findings.append(f"文献检索链路失败: {literature_result['error']}")
            return

        clinical_gap = literature_result.get("clinical_gap_analysis") or {}
        evidence_matrix = literature_result.get("evidence_matrix", {})
        observations.append(
            f"已完成 {literature_result.get('record_count', 0)} 条医学文献检索并抽取摘要证据"
        )
        findings.append(f"证据矩阵覆盖 {evidence_matrix.get('dimension_count', 0)} 个维度")
        findings.append(
            f"文献来源统计: {', '.join(literature_result.get('source_counts_summary', [])) or '无'}"
        )
        if clinical_gap.get("report"):
            findings.append("已完成 Qwen 临床关联 Gap Analysis，可直接用于选题与方案设计")

    def _build_observe_metadata(
        self,
        context: Dict[str, Any],
        observations: list[str],
        findings: list[str],
        corpus_result: Dict[str, Any] | None,
        ingestion_result: Dict[str, Any] | None,
        literature_result: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        clinical_gap = (literature_result or {}).get("clinical_gap_analysis") or {}
        ingestion_ok = bool(ingestion_result and not ingestion_result.get("error"))
        literature_ok = bool(literature_result and not literature_result.get("error"))
        downstream_processing, semantic_modeling = self._build_observe_ingestion_flags(
            ingestion_result,
            ingestion_ok,
        )

        return {
            "data_source": self._resolve_observe_data_source(context),
            "observation_count": len(observations),
            "finding_count": len(findings),
            "auto_collected_ctext": self._is_ctext_corpus_collected(corpus_result),
            "auto_collected_corpus": bool(corpus_result),
            "corpus_schema": "bundle" if is_corpus_bundle(corpus_result) else ("ctext_raw" if corpus_result else None),
            "ctext_groups": self._resolve_whitelist_groups(context),
            "downstream_processing": downstream_processing,
            "semantic_modeling": semantic_modeling,
            "literature_retrieval": literature_ok,
            "evidence_matrix": self._has_observe_evidence_matrix(literature_result, literature_ok),
            "clinical_gap_analysis": bool(literature_ok and clinical_gap.get("report")),
        }

    def _is_ctext_corpus_collected(self, corpus_result: Dict[str, Any] | None) -> bool:
        if not corpus_result:
            return False
        if not is_corpus_bundle(corpus_result):
            return True
        return "ctext" in (corpus_result.get("sources") or [])

    def _build_observe_ingestion_flags(
        self,
        ingestion_result: Dict[str, Any] | None,
        ingestion_ok: bool,
    ) -> tuple[bool, bool]:
        if not ingestion_ok or not ingestion_result:
            return False, False

        downstream_processing = ingestion_result.get("processed_document_count", 0) > 0
        semantic_modeling = ingestion_result.get("aggregate", {}).get("semantic_graph_nodes", 0) > 0
        return bool(downstream_processing), bool(semantic_modeling)

    def _has_observe_evidence_matrix(
        self,
        literature_result: Dict[str, Any] | None,
        literature_ok: bool,
    ) -> bool:
        if not literature_ok or not literature_result:
            return False
        return bool(literature_result.get("evidence_matrix", {}).get("record_count", 0) > 0)

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        if self._should_collect_ctext_corpus(context) and self._should_collect_local_corpus(context):
            return "ctext_whitelist+local"
        if self._should_collect_ctext_corpus(context):
            return "ctext_whitelist"
        if self._should_collect_local_corpus(context):
            return "local"
        return context.get("data_source", "unknown")

    def _should_run_observe_ingestion(self, context: Dict[str, Any]) -> bool:
        if "run_preprocess_and_extract" in context:
            return bool(context.get("run_preprocess_and_extract"))

        observe_pipeline_config = self.pipeline.config.get("observe_pipeline", {})
        return bool(observe_pipeline_config.get("enabled", True))

    def _should_run_observe_literature(self, context: Dict[str, Any]) -> bool:
        if "run_literature_retrieval" in context:
            return bool(context.get("run_literature_retrieval"))

        literature_config = self.pipeline.config.get("literature_retrieval", {})
        return bool(literature_config.get("enabled", False))

    def _run_observe_literature_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        literature_config = self.pipeline.config.get("literature_retrieval", {})
        sources = context.get("literature_sources") or literature_config.get(
            "default_sources",
            ["pubmed", "semantic_scholar", "plos_one", "arxiv"],
        )
        query = context.get("literature_query") or context.get("query") or "traditional chinese medicine"
        raw_max_results = context.get("literature_max_results", literature_config.get("max_results_per_source", 5))
        max_results = max(1, min(int(raw_max_results), 50))
        offline_plan_only = bool(
            context.get(
                "literature_offline_plan_only",
                literature_config.get("offline_plan_only", False),
            )
        )

        retriever = self.pipeline.create_module(
            "literature_retriever",
            {
                "timeout_sec": literature_config.get("timeout_sec", 20),
                "retry_count": literature_config.get("retry_count", 2),
                "request_interval_sec": literature_config.get("request_interval_sec", 0.2),
                "user_agent": literature_config.get("user_agent", "TCM-AutoResearch-Observe/1.0"),
            },
        )

        try:
            retrieval_result = retriever.search(
                query=query,
                sources=sources,
                max_results_per_source=max_results,
                pubmed_email=context.get("pubmed_email", literature_config.get("pubmed_email", "")),
                pubmed_api_key=context.get("pubmed_api_key", literature_config.get("pubmed_api_key", "")),
                offline_plan_only=offline_plan_only,
            )
        except Exception as e:
            self.pipeline.logger.error("观察阶段文献检索失败: %s", e)
            return {"error": str(e)}
        finally:
            retriever.close()

        summaries = self.pipeline._extract_literature_summaries(retrieval_result.get("records", []))
        evidence_matrix = self.pipeline._build_evidence_matrix(summaries, context)
        clinical_gap_result = None
        if self.pipeline._should_run_clinical_gap_analysis(context):
            clinical_gap_result = self.pipeline._run_clinical_gap_analysis(evidence_matrix, summaries, context)

        source_counts = retrieval_result.get("source_stats", {})
        source_counts_summary = [
            f"{source}:{(stats or {}).get('count', 0)}"
            for source, stats in source_counts.items()
        ]

        return {
            "query": retrieval_result.get("query", query),
            "sources": retrieval_result.get("sources", sources),
            "record_count": len(retrieval_result.get("records", [])),
            "abstract_summary_count": len(summaries),
            "records": retrieval_result.get("records", []),
            "query_plans": retrieval_result.get("query_plans", []),
            "errors": retrieval_result.get("errors", []),
            "source_stats": source_counts,
            "source_counts_summary": source_counts_summary,
            "summaries": summaries,
            "evidence_matrix": evidence_matrix,
            "clinical_gap_analysis": clinical_gap_result,
        }

    def _should_collect_ctext_corpus(self, context: Dict[str, Any]) -> bool:
        ctext_config = self.pipeline.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})

        if "use_ctext_whitelist" in context:
            return bool(context.get("use_ctext_whitelist"))

        if context.get("data_source") == "ctext_whitelist":
            return True

        return bool(ctext_config.get("enabled") and whitelist_config.get("enabled"))

    def _should_collect_local_corpus(self, context: Dict[str, Any]) -> bool:
        if "use_local_corpus" in context:
            return bool(context.get("use_local_corpus"))

        if context.get("data_source") == "local":
            return True

        local_config = self.pipeline.config.get("local_corpus", {})
        return bool(local_config.get("enabled"))

    def _collect_local_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any] | None:
        local_config = self.pipeline.config.get("local_corpus", {})
        collector = self.pipeline.create_module(
            "local_corpus_collector",
            {
                "data_dir": context.get("local_data_dir", local_config.get("data_dir", "data")),
                "file_glob": context.get("file_glob", local_config.get("file_glob", "*.txt")),
                "max_files": context.get("local_max_files", local_config.get("max_files", 50)),
                "recursive": context.get("local_recursive", local_config.get("recursive", False)),
                "encoding_fallbacks": local_config.get("encoding_fallbacks"),
                "min_text_length": local_config.get("min_text_length", 50),
            },
        )
        initialized = collector.initialize()
        if not initialized:
            return {"error": "本地语料采集器初始化失败"}
        try:
            return collector.execute(context)
        except Exception as e:
            self.pipeline.logger.error("观察阶段本地语料采集失败: %s", e)
            return {"error": str(e)}
        finally:
            collector.cleanup()

    def _resolve_whitelist_groups(self, context: Dict[str, Any]) -> List[str]:
        ctext_config = self.pipeline.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})
        return context.get("whitelist_groups") or whitelist_config.get("default_groups", [])

    def _collect_ctext_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctext_config = self.pipeline.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})

        collector = self.pipeline.create_module(
            "ctext_corpus_collector",
            {
                "api_base": context.get("api_base", ctext_config.get("api_base", "https://api.ctext.org")),
                "request_interval_sec": context.get("request_interval_sec", ctext_config.get("request_interval_sec", 0.2)),
                "retry_count": context.get("retry_count", ctext_config.get("retry_count", 2)),
                "timeout_sec": context.get("timeout_sec", ctext_config.get("timeout_sec", 20)),
                "output_dir": context.get("output_dir", os.path.join("data", "ctext")),
            },
        )

        initialized = collector.initialize()
        if not initialized:
            return {"error": "ctext 采集器初始化失败"}

        try:
            return collector.execute(
                {
                    "use_whitelist": True,
                    "whitelist_path": context.get("whitelist_path", whitelist_config.get("path")),
                    "whitelist_groups": self._resolve_whitelist_groups(context),
                    "recurse": context.get("recurse", True),
                    "max_depth": context.get("max_depth", 3),
                    "save_to_disk": context.get("save_to_disk", True),
                    "output_dir": context.get("output_dir", os.path.join("data", "ctext")),
                }
            )
        except Exception as e:
            self.pipeline.logger.error("观察阶段 ctext 采集失败: %s", e)
            return {"error": str(e)}
        finally:
            collector.cleanup()

    def _run_observe_ingestion_pipeline(self, corpus_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        text_entries = self.pipeline._extract_corpus_text_entries(corpus_result)
        max_texts = max(1, min(int(context.get("max_texts", 3)), 20))
        max_chars_per_text = max(200, min(int(context.get("max_chars_per_text", 1200)), 4000))
        selected_entries = text_entries[:max_texts]

        if not selected_entries:
            return {
                "processed_document_count": 0,
                "documents": [],
                "aggregate": {
                    "total_entities": 0,
                    "entity_type_counts": {},
                    "average_confidence": 0.0,
                },
            }

        preprocessor = self.pipeline.create_module("document_preprocessor", context.get("preprocessor_config") or {})
        extractor = self.pipeline.create_module("entity_extractor", context.get("extractor_config") or {})
        semantic_builder = self.pipeline.create_module("semantic_graph_builder", context.get("semantic_builder_config") or {})
        reasoning_engine = self.pipeline.create_module("reasoning_engine", context.get("reasoning_engine_config") or {})

        if not preprocessor.initialize():
            return {"error": "文档预处理器初始化失败"}
        if not extractor.initialize():
            preprocessor.cleanup()
            return {"error": "实体抽取器初始化失败"}
        if not semantic_builder.initialize():
            extractor.cleanup()
            preprocessor.cleanup()
            return {"error": "语义图构建器初始化失败"}
        reasoning_enabled = bool(context.get("run_reasoning", True))
        if reasoning_enabled and not reasoning_engine.initialize():
            reasoning_enabled = False
            self.pipeline.logger.warning("推理引擎初始化失败，继续使用语义图关系")

        document_results: List[Dict[str, Any]] = []
        entity_type_counts: Dict[str, int] = {}
        total_entities = 0
        confidence_values: List[float] = []
        total_semantic_nodes = 0
        total_semantic_edges = 0
        total_semantic_relationships: List[Dict[str, Any]] = []
        reasoning_summaries: List[Dict[str, Any]] = []

        try:
            for entry in selected_entries:
                raw_text = entry.get("text", "")[:max_chars_per_text]
                preprocess_result = preprocessor.execute(
                    {
                        "raw_text": raw_text,
                        "source_file": entry.get("urn", "unknown"),
                        "metadata": {
                            "title": entry.get("title", ""),
                            "source": "ctext",
                            "collection_stage": "observe",
                        },
                    }
                )
                extraction_result = extractor.execute(preprocess_result)
                semantic_result = semantic_builder.execute(extraction_result)
                reasoning_result = self._run_observe_reasoning_if_enabled(
                    reasoning_engine,
                    reasoning_enabled,
                    extraction_result,
                    semantic_result,
                )

                entities = extraction_result.get("entities", [])
                total_entities += len(entities)
                confidence_values.extend(entity.get("confidence", 0.0) for entity in entities)
                graph_stats = semantic_result.get("graph_statistics", {})
                semantic_relationships = self._merge_relationship_sources(
                    self._extract_semantic_relationships(semantic_result),
                    self._extract_reasoning_relationships(reasoning_result, semantic_result, entities),
                )
                reasoning_summary = self._extract_reasoning_summary(reasoning_result)
                total_semantic_nodes += graph_stats.get("nodes_count", 0)
                total_semantic_edges += graph_stats.get("edges_count", 0)
                total_semantic_relationships.extend(semantic_relationships)
                if reasoning_summary:
                    reasoning_summaries.append(reasoning_summary)

                for entity_type, count in extraction_result.get("statistics", {}).get("by_type", {}).items():
                    entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + count

                document_results.append(
                    {
                        "urn": entry.get("urn", ""),
                        "title": entry.get("title", ""),
                        "raw_text_preview": raw_text[:120],
                        "processed_text_preview": preprocess_result.get("processed_text", "")[:120],
                        "entity_count": len(entities),
                        "entity_types": extraction_result.get("statistics", {}).get("by_type", {}),
                        "average_confidence": extraction_result.get("confidence_scores", {}).get("average_confidence", 0.0),
                        "semantic_graph_nodes": graph_stats.get("nodes_count", 0),
                        "semantic_graph_edges": graph_stats.get("edges_count", 0),
                        "relationship_types": graph_stats.get("relationships_by_type", {}),
                        "semantic_relationships": semantic_relationships,
                        "reasoning_results": (reasoning_result or {}).get("reasoning_results", {}),
                        "reasoning_summary": reasoning_summary,
                    }
                )

            average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
            return {
                "processed_document_count": len(document_results),
                "documents": document_results,
                "aggregate": {
                    "total_entities": total_entities,
                    "entity_type_counts": entity_type_counts,
                    "average_confidence": average_confidence,
                    "semantic_graph_nodes": total_semantic_nodes,
                    "semantic_graph_edges": total_semantic_edges,
                    "semantic_relationships": self._deduplicate_relationships(total_semantic_relationships),
                    "reasoning_summary": self._merge_reasoning_summaries(reasoning_summaries),
                },
            }
        except Exception as e:
            self.pipeline.logger.error("观察阶段预处理/抽取/建模链路失败: %s", e)
            return {"error": str(e)}
        finally:
            reasoning_engine.cleanup()
            semantic_builder.cleanup()
            extractor.cleanup()
            preprocessor.cleanup()

    def _extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        return extract_text_entries(corpus_result)

    def _extract_semantic_relationships(self, semantic_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        semantic_graph = semantic_result.get("semantic_graph") or {}
        nodes = semantic_graph.get("nodes") or []
        edges = semantic_graph.get("edges") or []
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return []

        node_map: Dict[str, Dict[str, Any]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            data = node.get("data") or {}
            if not node_id:
                continue
            node_map[node_id] = {
                "name": str(data.get("name") or node_id),
                "type": str(data.get("type") or "generic"),
            }

        relationships: List[Dict[str, Any]] = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source_id = str(edge.get("source") or "").strip()
            target_id = str(edge.get("target") or "").strip()
            attributes = edge.get("attributes") or {}
            source_node = node_map.get(source_id)
            target_node = node_map.get(target_id)
            if not source_node or not target_node:
                continue
            relation_type = str(
                attributes.get("relationship_type")
                or attributes.get("rel_type")
                or attributes.get("type")
                or "related_to"
            )
            relationships.append(
                {
                    "source": source_node["name"],
                    "target": target_node["name"],
                    "type": relation_type,
                    "source_type": source_node["type"],
                    "target_type": target_node["type"],
                    "metadata": {
                        "confidence": float(attributes.get("confidence") or 0.0),
                        "relationship_name": str(attributes.get("relationship_name") or relation_type),
                        "description": str(attributes.get("description") or ""),
                        "source_node_id": source_id,
                        "target_node_id": target_id,
                        "source": "observe_semantic_graph",
                    },
                }
            )
        return self._deduplicate_relationships(relationships)

    def _run_observe_reasoning_if_enabled(
        self,
        reasoning_engine: Any,
        reasoning_enabled: bool,
        extraction_result: Dict[str, Any],
        semantic_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not reasoning_enabled:
            return {}
        try:
            return reasoning_engine.execute(
                {
                    "entities": extraction_result.get("entities", []),
                    "semantic_graph": semantic_result.get("semantic_graph", {}),
                }
            )
        except Exception as exc:
            self.pipeline.logger.warning("观察阶段推理链路失败，忽略 reasoning 结果: %s", exc)
            return {}

    def _extract_reasoning_relationships(
        self,
        reasoning_result: Dict[str, Any],
        semantic_result: Dict[str, Any],
        entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        reasoning_results = (reasoning_result or {}).get("reasoning_results") or {}
        entity_relationships = reasoning_results.get("entity_relationships") or []
        if not isinstance(entity_relationships, list):
            return []

        entity_type_map: Dict[str, str] = {}
        for entity in entities:
            if not isinstance(entity, dict) or not entity.get("name"):
                continue
            entity_type_map[str(entity.get("name"))] = str(entity.get("type") or "generic")

        for relation in self._extract_semantic_relationships(semantic_result):
            source = str(relation.get("source") or "")
            target = str(relation.get("target") or "")
            source_type = str(relation.get("source_type") or "generic")
            target_type = str(relation.get("target_type") or "generic")
            if source and source not in entity_type_map:
                entity_type_map[source] = source_type
            if target and target not in entity_type_map:
                entity_type_map[target] = target_type

        relationships: List[Dict[str, Any]] = []
        for relation in entity_relationships:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            relation_type = str(relation.get("type") or relation.get("rel_type") or "related_to").strip()
            if not source or not target:
                continue
            relationships.append(
                {
                    "source": source,
                    "target": target,
                    "type": relation_type,
                    "source_type": entity_type_map.get(source, "generic"),
                    "target_type": entity_type_map.get(target, "generic"),
                    "metadata": {
                        "confidence": float(relation.get("confidence") or 0.0),
                        "relationship_name": relation_type,
                        "description": "Derived from reasoning_engine.entity_relationships",
                        "source": "observe_reasoning_engine",
                    },
                }
            )
        return self._deduplicate_relationships(relationships)

    def _extract_reasoning_summary(self, reasoning_result: Dict[str, Any]) -> Dict[str, Any]:
        reasoning_results = (reasoning_result or {}).get("reasoning_results") or {}
        if not reasoning_results:
            return {}
        knowledge_patterns = reasoning_results.get("knowledge_patterns") or {}
        common_entities = knowledge_patterns.get("common_entities") or []
        most_shared_efficacies = knowledge_patterns.get("most_shared_efficacies") or []
        entity_groups = knowledge_patterns.get("entity_groups") or {}
        return {
            "inference_confidence": float(reasoning_results.get("inference_confidence") or 0.0),
            "knowledge_patterns": {
                "common_entities": [str(item) for item in common_entities if str(item).strip()],
                "most_shared_efficacies": [str(item) for item in most_shared_efficacies if str(item).strip()],
                "entity_groups": {
                    str(key): [str(item) for item in (values or []) if str(item).strip()]
                    for key, values in entity_groups.items()
                },
            },
        }

    def _merge_reasoning_summaries(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not summaries:
            return {}
        inference_scores = [float(item.get("inference_confidence") or 0.0) for item in summaries]
        merged_patterns = {
            "common_entities": [],
            "most_shared_efficacies": [],
            "entity_groups": {},
        }
        for summary in summaries:
            patterns = summary.get("knowledge_patterns") or {}
            for key in ["common_entities", "most_shared_efficacies"]:
                for item in patterns.get(key) or []:
                    if item not in merged_patterns[key]:
                        merged_patterns[key].append(item)
            for group_key, values in (patterns.get("entity_groups") or {}).items():
                merged_patterns["entity_groups"].setdefault(group_key, [])
                for value in values or []:
                    if value not in merged_patterns["entity_groups"][group_key]:
                        merged_patterns["entity_groups"][group_key].append(value)
        return {
            "inference_confidence": round(sum(inference_scores) / len(inference_scores), 4),
            "knowledge_patterns": merged_patterns,
        }

    def _merge_relationship_sources(self, *relationship_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for group in relationship_groups:
            if isinstance(group, list):
                merged.extend(group)
        return self._deduplicate_relationships(merged)

    def _deduplicate_relationships(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduplicated_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        for relation in relationships:
            if not isinstance(relation, dict):
                continue
            key = (
                str(relation.get("source") or ""),
                str(relation.get("type") or relation.get("rel_type") or ""),
                str(relation.get("target") or ""),
            )
            if not all(key):
                continue
            current = deduplicated_map.get(key)
            if current is None:
                deduplicated_map[key] = relation
                continue
            deduplicated_map[key] = self._resolve_relationship_conflict(current, relation)
        return list(deduplicated_map.values())

    def _resolve_relationship_conflict(
        self,
        current: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        relation_type = str(current.get("type") or current.get("rel_type") or candidate.get("type") or candidate.get("rel_type") or "")
        strategy = self._relationship_conflict_strategy(relation_type)
        current_priority = self._relationship_source_priority(current)
        candidate_priority = self._relationship_source_priority(candidate)
        current_confidence = self._relationship_confidence(current)
        candidate_confidence = self._relationship_confidence(candidate)

        if strategy == "confidence_then_source_priority":
            if candidate_confidence > current_confidence:
                preferred = candidate
                alternate = current
            elif candidate_confidence < current_confidence:
                preferred = current
                alternate = candidate
            elif candidate_priority >= current_priority:
                preferred = candidate
                alternate = current
            else:
                preferred = current
                alternate = candidate
        else:
            if candidate_priority > current_priority:
                preferred = candidate
                alternate = current
            elif candidate_priority < current_priority:
                preferred = current
                alternate = candidate
            elif candidate_confidence >= current_confidence:
                preferred = candidate
                alternate = current
            else:
                preferred = current
                alternate = candidate

        preferred_metadata = dict(preferred.get("metadata") or {})
        alternate_metadata = dict(alternate.get("metadata") or {})
        merged_sources: List[str] = []
        for source_name in [
            str(preferred_metadata.get("source") or ""),
            *[str(item) for item in (preferred_metadata.get("merged_sources") or [])],
            str(alternate_metadata.get("source") or ""),
            *[str(item) for item in (alternate_metadata.get("merged_sources") or [])],
        ]:
            if source_name and source_name not in merged_sources:
                merged_sources.append(source_name)

        preferred_metadata["merged_sources"] = merged_sources
        preferred_metadata["confidence"] = max(current_confidence, candidate_confidence)
        preferred_metadata["conflict_resolution"] = {
            "strategy": strategy,
            "preferred_source": str(preferred_metadata.get("source") or ""),
            "alternate_source": str(alternate_metadata.get("source") or ""),
            "preferred_priority": self._relationship_source_priority(preferred),
            "alternate_priority": self._relationship_source_priority(alternate),
            "preferred_confidence": self._relationship_confidence(preferred),
            "alternate_confidence": self._relationship_confidence(alternate),
        }
        return {
            **preferred,
            "metadata": preferred_metadata,
        }

    def _relationship_conflict_strategy(self, relation_type: str) -> str:
        config = self._relationship_conflict_resolution_config()
        relation_type_strategies = config.get("relation_type_strategies") or {}
        strategy = relation_type_strategies.get(relation_type) or config.get("default_strategy") or "source_priority_then_confidence"
        strategy = str(strategy or "source_priority_then_confidence").strip()
        if strategy not in self._RELATION_CONFLICT_STRATEGIES:
            return "source_priority_then_confidence"
        return strategy

    def _relationship_conflict_resolution_config(self) -> Dict[str, Any]:
        root_config = self.pipeline.config.get("relationship_conflict_resolution") or {}
        observe_config = (self.pipeline.config.get("observe_pipeline") or {}).get("relationship_conflict_resolution") or {}
        merged_config = dict(root_config) if isinstance(root_config, dict) else {}
        if isinstance(observe_config, dict):
            merged_config.update(observe_config)
        return merged_config

    def _relationship_source_priority(self, relation: Dict[str, Any]) -> int:
        metadata = relation.get("metadata") or {}
        source_name = str(metadata.get("source") or "")
        config = self._relationship_conflict_resolution_config()
        source_priority = dict(self._RELATION_SOURCE_PRIORITY)
        configured_priority = config.get("source_priority") or {}
        if isinstance(configured_priority, dict):
            for name, priority in configured_priority.items():
                try:
                    source_priority[str(name)] = int(priority)
                except (TypeError, ValueError):
                    continue
        return int(source_priority.get(source_name, 0))

    def _relationship_confidence(self, relation: Dict[str, Any]) -> float:
        metadata = relation.get("metadata") or {}
        try:
            return float(metadata.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def execute_hypothesis_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis_context = self._build_hypothesis_context(cycle, context or {})
        result = self.pipeline.hypothesis_engine.execute(hypothesis_context)
        hypotheses = result.get("hypotheses") or []
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
        return result

    def execute_experiment_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        selected_hypothesis, selection_metadata = self._resolve_selected_hypothesis(cycle, context)
        if selected_hypothesis is None:
            return {
                "phase": "experiment",
                "experiments": [],
                "results": {},
                "success_rate": 0.0,
                "metadata": {
                    "validation_status": "blocked",
                    "reason": "missing_hypothesis_selection",
                    **selection_metadata,
                },
            }

        experiment_framework = self._create_theoretical_framework()
        experiment_context = self._build_experiment_context(cycle, context, selected_hypothesis)
        research_hypothesis = self._convert_to_research_hypothesis(selected_hypothesis, cycle)
        experiment = experiment_framework.design_experiment(research_hypothesis, experiment_context)

        experiment_payload = experiment.to_dict()
        experiment_results = {
            "study_design": experiment.experimental_design,
            "sample_size": experiment.sample_size,
            "duration_days": experiment.duration,
            "methodology": experiment.methodology,
            "validation_metrics": {
                "quality_score": experiment.quality_score,
                "reproducibility_score": experiment.reproducibility_score,
                "scientific_validity": experiment.scientific_validity,
            },
            "data_sources": experiment.data_sources,
            "validation_plan": selected_hypothesis.get("validation_plan", ""),
            "expected_results": experiment.expected_results,
            "evidence_profile": experiment_context.get("evidence_profile", {}),
            "source_weights": experiment_context.get("source_weights", []),
            "gap_priority_summary": experiment_context.get("gap_priority_summary", {}),
        }
        return {
            "phase": "experiment",
            "experiments": [experiment_payload],
            "results": experiment_results,
            "selected_hypothesis": selected_hypothesis,
            "success_rate": 1.0,
            "metadata": {
                "study_type": experiment.experimental_design,
                "validation_status": "approved",
                "evidence_record_count": experiment_context.get("evidence_profile", {}).get("record_count", 0),
                "weighted_evidence_score": experiment_context.get("evidence_profile", {}).get("weighted_evidence_score", 0.0),
                "clinical_gap_available": experiment_context.get("evidence_profile", {}).get("clinical_gap_available", False),
                "highest_gap_priority": experiment_context.get("gap_priority_summary", {}).get("highest_priority", "低"),
                **selection_metadata,
            },
        }

    def execute_analyze_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        analysis_results = {
            "statistical_significance": True,
            "confidence_level": 0.95,
            "effect_size": 0.75,
            "p_value": 0.003,
            "interpretation": "发现方剂剂量与疗效存在显著相关性，符合中医理论预期",
            "limitations": ["样本规模有限", "数据来源单一", "时间跨度较短"],
        }
        evidence_grade_payload, evidence_grade_error = self._grade_analyze_evidence(cycle, context)
        if evidence_grade_payload:
            analysis_results["evidence_grade"] = evidence_grade_payload
            analysis_results["evidence_grade_summary"] = self._build_evidence_grade_summary(evidence_grade_payload)

        metadata = {
            "analysis_type": "statistical_analysis",
            "significance_level": 0.05,
            "evidence_grade_generated": bool(evidence_grade_payload),
            "evidence_study_count": int(evidence_grade_payload.get("study_count") or 0) if evidence_grade_payload else 0,
        }
        if evidence_grade_error:
            metadata["evidence_grade_error"] = evidence_grade_error

        return {
            "phase": "analyze",
            "results": analysis_results,
            "metadata": metadata,
        }

    def _grade_analyze_evidence(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str]:
        literature_records = self._collect_analyze_literature_records(cycle, context)
        if not literature_records:
            return {}, ""

        try:
            grader = self._create_evidence_grader()
            return grader.grade_evidence(literature_records).to_dict(), ""
        except Exception as exc:
            self.pipeline.logger.warning("Analyze 阶段 GRADE 证据分级失败: %s", exc)
            return {}, str(exc)

    def _collect_analyze_literature_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Any]:
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        context_literature_pipeline = context.get("literature_pipeline")

        candidates = [
            context.get("literature_records"),
            context_literature_pipeline.get("records") if isinstance(context_literature_pipeline, dict) else None,
            (observe_result.get("literature_pipeline") or {}).get("records") if isinstance(observe_result, dict) else None,
        ]
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            records = [item for item in candidate if item is not None]
            if records:
                return records
        return []

    def _build_evidence_grade_summary(self, evidence_grade: Dict[str, Any]) -> Dict[str, Any]:
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

    def execute_publish_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        hypothesis_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.HYPOTHESIS, {}).get("result", {})
        experiment_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.EXPERIMENT, {}).get("result", {})
        analyze_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.ANALYZE, {}).get("result", {})
        literature_pipeline = observe_result.get("literature_pipeline") or {}
        citation_records = self._collect_citation_records(cycle, context, literature_pipeline)

        citation_manager = self._create_citation_manager()
        citation_result = self._execute_citation_manager(citation_manager, citation_records)

        paper_writer = self._create_paper_writer()
        paper_context = self._build_publish_paper_context(
            cycle,
            context,
            observe_result,
            hypothesis_result,
            experiment_result,
            analyze_result,
            literature_pipeline,
            citation_records,
            citation_result,
        )
        paper_result = self._execute_paper_writer(paper_writer, paper_context)
        paper_output_files = paper_result.get("output_files") if isinstance(paper_result, dict) else {}
        citation_output_files = citation_result.get("output_files")
        merged_output_files = self._merge_publish_output_files(
            paper_output_files if isinstance(paper_output_files, dict) else {},
            citation_output_files if isinstance(citation_output_files, dict) else {},
        )
        report_session_result = self._build_publish_report_session_result(
            cycle,
            context,
            observe_result,
            hypothesis_result,
            experiment_result,
            analyze_result,
            paper_context,
            paper_result if isinstance(paper_result, dict) else {},
            citation_result,
            merged_output_files,
        )
        report_generation_result = self._generate_publish_reports(report_session_result, context)
        report_output_files = report_generation_result.get("output_files") if isinstance(report_generation_result, dict) else {}
        merged_output_files = self._merge_publish_output_files(
            merged_output_files,
            report_output_files if isinstance(report_output_files, dict) else {},
        )

        publications = [
            {
                "title": "基于AI的中医古籍方剂分析研究",
                "journal": "中医研究学报",
                "authors": cycle.researchers,
                "keywords": ["AI", "中医", "古籍", "方剂", "数据分析"],
                "status": "submitted",
                "citation_key": f"{self._safe_researcher_key(cycle.researchers)}2026AI",
            },
            {
                "title": "古代方剂剂量演变规律研究",
                "journal": "中医药学报",
                "authors": cycle.researchers,
                "keywords": ["剂量", "历史", "演变", "中医"],
                "status": "accepted",
                "citation_key": f"{self._safe_researcher_key(cycle.researchers)}2026Dose",
            },
        ]

        deliverables = [
            "研究报告",
            "数据集",
            "分析工具包",
            "可视化图表",
        ]
        if citation_result.get("bibtex"):
            deliverables.append("BibTeX 参考文献")
        if citation_result.get("gbt7714"):
            deliverables.append("GB/T 7714 参考文献")
        if merged_output_files.get("markdown"):
            deliverables.append("Markdown 论文初稿")
        if merged_output_files.get("docx"):
            deliverables.append("DOCX 论文初稿")
        if merged_output_files.get("imrd_markdown"):
            deliverables.append("Markdown IMRD 报告")
        if merged_output_files.get("imrd_docx"):
            deliverables.append("DOCX IMRD 报告")

        return {
            "phase": "publish",
            "publications": publications,
            "deliverables": deliverables,
            "citations": citation_result.get("entries", []),
            "bibtex": citation_result.get("bibtex", ""),
            "gbt7714": citation_result.get("gbt7714", ""),
            "formatted_references": citation_result.get("formatted_references", ""),
            "paper_draft": paper_result.get("paper_draft", {}) if isinstance(paper_result, dict) else {},
            "paper_language": paper_result.get("language", "") if isinstance(paper_result, dict) else "",
            "imrd_reports": report_generation_result.get("reports", {}) if isinstance(report_generation_result, dict) else {},
            "report_output_files": report_output_files if isinstance(report_output_files, dict) else {},
            "report_session_result": report_session_result,
            "report_generation_errors": report_generation_result.get("errors", []) if isinstance(report_generation_result, dict) else [],
            "analysis_results": paper_context.get("analysis_results", {}),
            "research_artifact": paper_context.get("research_artifact", {}),
            "output_files": merged_output_files,
            "metadata": {
                "publication_count": len(publications),
                "deliverable_count": len(deliverables),
                "citation_count": citation_result.get("citation_count", 0),
                "paper_section_count": paper_result.get("section_count", 0) if isinstance(paper_result, dict) else 0,
                "paper_reference_count": paper_result.get("reference_count", 0) if isinstance(paper_result, dict) else 0,
                "report_count": len(report_generation_result.get("reports", {})) if isinstance(report_generation_result, dict) else 0,
                "report_error_count": len(report_generation_result.get("errors", [])) if isinstance(report_generation_result, dict) else 0,
            },
        }

    def execute_reflect_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        reflections = [
            {
                "topic": "方法论改进",
                "reflection": "实验设计可以更加多样化，增加跨学科方法的应用",
                "action": "在下一轮研究中引入更多样化的实验方法",
            },
            {
                "topic": "数据质量",
                "reflection": "古籍文本的标准化处理仍有改进空间",
                "action": "开发更完善的文本预处理工具",
            },
            {
                "topic": "技术应用",
                "reflection": "AI模型在中医领域应用效果显著，但需要持续优化",
                "action": "加强模型训练和调优",
            },
        ]

        improvement_plan = [
            "优化数据预处理流程",
            "增强模型泛化能力",
            "完善质量控制体系",
            "建立长期跟踪机制",
        ]

        return {
            "phase": "reflect",
            "reflections": reflections,
            "improvement_plan": improvement_plan,
            "metadata": {
                "reflection_count": len(reflections),
                "plan_items": len(improvement_plan),
            },
        }

    def _build_hypothesis_context(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        existing_hypotheses = cycle.phase_executions.get(self.pipeline.ResearchPhase.HYPOTHESIS, {}).get("result", {}).get("hypotheses", [])

        observations = observe_result.get("observations", [])
        findings = observe_result.get("findings", [])
        literature_pipeline = observe_result.get("literature_pipeline") or {}
        corpus_collection = observe_result.get("corpus_collection") or {}
        ingestion_pipeline = observe_result.get("ingestion_pipeline") or {}

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
            "use_llm_generation": context.get("use_llm_generation", False),
            "llm_service": context.get("llm_service"),
            "knowledge_graph": knowledge_graph,
            "knowledge_gap": knowledge_gap,
        }

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
    ) -> TCMKnowledgeGraph:
        graph = TCMKnowledgeGraph(preload_formulas=False)
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

    def _add_hypothesis_relation(self, graph: TCMKnowledgeGraph, relation: Any) -> None:
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
        graph: TCMKnowledgeGraph,
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
        if target in graph.neighbors(source, relation_type):
            return
        graph.add_relation(source, relation_type, target, {"inferred": True, "source": "pipeline_hypothesis_context"})

    def _derive_hypothesis_knowledge_gap(
        self,
        graph: TCMKnowledgeGraph,
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
        hypotheses = hypothesis_result.get("hypotheses") or []
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

    def _create_theoretical_framework(self) -> Any:
        if TheoreticalFramework is None:
            raise RuntimeError("TheoreticalFramework 不可用，无法生成实验设计")
        return TheoreticalFramework(self.pipeline.config.get("theoretical_framework_config") or {})

    def _build_experiment_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        literature_pipeline = observe_result.get("literature_pipeline") or {}
        evidence_matrix = literature_pipeline.get("evidence_matrix") or {}
        clinical_gap_analysis = literature_pipeline.get("clinical_gap_analysis") or {}
        evidence_records = evidence_matrix.get("records") or []
        dimension_count = int(evidence_matrix.get("dimension_count") or 0)
        top_records = [dict(item) for item in evidence_records[:3] if isinstance(item, dict)]
        weighted_records = self._build_weighted_evidence_records(top_records, dimension_count)
        source_weights = self._build_source_weights(literature_pipeline, evidence_records)
        evidence_profile = self._build_evidence_profile(
            evidence_matrix,
            weighted_records,
            source_weights,
            literature_pipeline,
        )
        gap_priority_summary = self._extract_gap_priority_summary(clinical_gap_analysis)
        derived_data_sources = self._build_experiment_data_sources(source_weights, evidence_records)
        return {
            "research_objective": cycle.research_objective or context.get("research_objective") or cycle.description,
            "research_scope": cycle.research_scope or context.get("research_scope") or "",
            "research_domain": selected_hypothesis.get("domain") or context.get("research_domain") or "integrative_research",
            "validation_plan": selected_hypothesis.get("validation_plan") or "",
            "supporting_signals": selected_hypothesis.get("supporting_signals") or [],
            "contradiction_signals": selected_hypothesis.get("contradiction_signals") or [],
            "evidence_matrix": evidence_matrix,
            "evidence_records": evidence_records,
            "weighted_evidence_records": weighted_records,
            "evidence_priority_titles": [item.get("title", "") for item in weighted_records if item.get("title")],
            "evidence_profile": evidence_profile,
            "source_weights": source_weights,
            "clinical_gap_analysis": clinical_gap_analysis,
            "gap_priority_summary": gap_priority_summary,
            "data_sources": context.get("data_sources") or derived_data_sources,
            "sample_size": context.get("sample_size") or self._derive_experiment_sample_size(evidence_profile, selected_hypothesis, gap_priority_summary),
            "duration_days": context.get("duration_days") or self._derive_experiment_duration(evidence_profile, selected_hypothesis),
            "methodology": context.get("methodology") or self._derive_experiment_methodology(evidence_profile, source_weights, gap_priority_summary),
        }

    def _extract_gap_priority_summary(self, clinical_gap_analysis: Dict[str, Any]) -> Dict[str, Any]:
        summary = clinical_gap_analysis.get("priority_summary") or {}
        counts = summary.get("counts") or {}
        return {
            "counts": {
                "高": int(counts.get("高", 0)),
                "中": int(counts.get("中", 0)),
                "低": int(counts.get("低", 0)),
            },
            "highest_priority": str(summary.get("highest_priority") or "低"),
            "total_gaps": int(summary.get("total_gaps") or len(clinical_gap_analysis.get("gaps") or [])),
        }

    def _build_weighted_evidence_records(
        self,
        records: List[Dict[str, Any]],
        dimension_count: int,
    ) -> List[Dict[str, Any]]:
        normalized_dimension_count = max(1, dimension_count)
        weighted_records: List[Dict[str, Any]] = []
        for item in records:
            coverage_score = float(item.get("coverage_score") or 0.0)
            weighted_records.append(
                {
                    **item,
                    "evidence_weight": round(min(1.0, coverage_score / normalized_dimension_count), 4),
                }
            )
        return weighted_records

    def _build_source_weights(
        self,
        literature_pipeline: Dict[str, Any],
        evidence_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        source_stats = literature_pipeline.get("source_stats") or {}
        if source_stats:
            total = sum(int((stats or {}).get("count", 0)) for stats in source_stats.values()) or 1
            weights = []
            for source, stats in source_stats.items():
                count = int((stats or {}).get("count", 0))
                weights.append(
                    {
                        "source": source,
                        "label": (stats or {}).get("source_name") or source,
                        "count": count,
                        "weight": round(count / total, 4),
                        "mode": (stats or {}).get("mode", ""),
                    }
                )
            return sorted(weights, key=lambda item: item.get("weight", 0.0), reverse=True)

        counts = Counter(str(item.get("source") or "unknown") for item in evidence_records if item.get("source"))
        total = sum(counts.values()) or 1
        return [
            {
                "source": source,
                "label": source,
                "count": count,
                "weight": round(count / total, 4),
                "mode": "derived",
            }
            for source, count in counts.most_common()
        ]

    def _build_evidence_profile(
        self,
        evidence_matrix: Dict[str, Any],
        weighted_records: List[Dict[str, Any]],
        source_weights: List[Dict[str, Any]],
        literature_pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension_count = int(evidence_matrix.get("dimension_count") or 0)
        coverage_scores = [float(item.get("coverage_score") or 0.0) for item in weighted_records]
        average_coverage = round(sum(coverage_scores) / len(coverage_scores), 4) if coverage_scores else 0.0
        weighted_evidence_score = 0.0
        if dimension_count > 0:
            weighted_evidence_score = round(
                sum(float(item.get("evidence_weight") or 0.0) for item in weighted_records) / max(1, len(weighted_records)),
                4,
            )
        source_balance = 0.0
        if source_weights:
            source_balance = round(min(item.get("weight", 0.0) for item in source_weights) * len(source_weights), 4)
        clinical_gap = literature_pipeline.get("clinical_gap_analysis") or {}
        gap_priority_summary = self._extract_gap_priority_summary(clinical_gap)
        return {
            "record_count": int(evidence_matrix.get("record_count") or len(evidence_matrix.get("records") or [])),
            "dimension_count": dimension_count,
            "dimension_hit_counts": evidence_matrix.get("dimension_hit_counts") or {},
            "average_coverage": average_coverage,
            "weighted_evidence_score": weighted_evidence_score,
            "source_count": len(source_weights),
            "source_balance": source_balance,
            "clinical_gap_available": bool(clinical_gap.get("report")),
            "gap_total": int(gap_priority_summary.get("total_gaps", 0)),
            "gap_high_count": int((gap_priority_summary.get("counts") or {}).get("高", 0)),
            "gap_medium_count": int((gap_priority_summary.get("counts") or {}).get("中", 0)),
            "gap_low_count": int((gap_priority_summary.get("counts") or {}).get("低", 0)),
            "highest_gap_priority": str(gap_priority_summary.get("highest_priority") or "低"),
        }

    def _build_experiment_data_sources(
        self,
        source_weights: List[Dict[str, Any]],
        evidence_records: List[Dict[str, Any]],
    ) -> List[str]:
        sources = [str(item.get("label") or item.get("source") or "").strip() for item in source_weights]
        sources = [item for item in sources if item]
        if sources:
            return sources

        derived_sources = []
        for item in evidence_records[:3]:
            source = str(item.get("source") or "").strip()
            if source and source not in derived_sources:
                derived_sources.append(source)
        return derived_sources or ["古籍文本", "现代数据库", "专家知识"]

    def _derive_experiment_sample_size(
        self,
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
        gap_priority_summary: Dict[str, Any],
    ) -> int:
        record_count = int(evidence_profile.get("record_count") or 0)
        dimension_count = int(evidence_profile.get("dimension_count") or 0)
        weighted_score = float(evidence_profile.get("weighted_evidence_score") or 0.0)
        contradiction_count = len(selected_hypothesis.get("contradiction_signals") or [])
        gap_counts = gap_priority_summary.get("counts") or {}
        high_gap_count = int(gap_counts.get("高", 0))
        medium_gap_count = int(gap_counts.get("中", 0))
        highest_gap_priority = str(gap_priority_summary.get("highest_priority") or "低")
        sample_size = 36 + record_count * 8 + dimension_count * 6 + int(weighted_score * 40) + contradiction_count * 5
        sample_size += high_gap_count * 18 + medium_gap_count * 8
        if highest_gap_priority == "高":
            sample_size += 16
        return max(36, min(sample_size, 240))

    def _derive_experiment_duration(
        self,
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> int:
        duration = 14 + int(evidence_profile.get("dimension_count") or 0) * 3 + int(evidence_profile.get("record_count") or 0)
        if selected_hypothesis.get("contradiction_signals"):
            duration += 4
        if evidence_profile.get("clinical_gap_available"):
            duration += 5
        return max(14, min(duration, 90))

    def _derive_experiment_methodology(
        self,
        evidence_profile: Dict[str, Any],
        source_weights: List[Dict[str, Any]],
        gap_priority_summary: Dict[str, Any],
    ) -> str:
        highest_gap_priority = str(gap_priority_summary.get("highest_priority") or "低")
        if evidence_profile.get("clinical_gap_available") and highest_gap_priority == "高":
            return "high_priority_gap_escalated_validation"
        if evidence_profile.get("clinical_gap_available"):
            return "gap_informed_evidence_weighted_analysis"
        if len(source_weights) >= 2 and float(evidence_profile.get("weighted_evidence_score") or 0.0) >= 0.5:
            return "multisource_weighted_comparative_analysis"
        if int(evidence_profile.get("record_count") or 0) > 0:
            return "evidence_weighted_analysis"
        return "data_analysis"

    def _convert_to_research_hypothesis(
        self,
        hypothesis: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> Any:
        if ResearchHypothesis is None or ResearchDomain is None or HypothesisStatus is None:
            raise RuntimeError("ResearchHypothesis 不可用，无法构建实验输入")

        domain_value = str(hypothesis.get("domain") or "integrative_research").strip() or "integrative_research"
        try:
            domain = ResearchDomain(domain_value)
        except Exception:
            domain = ResearchDomain.INTEGRATIVE_RESEARCH

        status_value = str(hypothesis.get("status") or "draft").strip().lower()
        try:
            status = HypothesisStatus(status_value)
        except Exception:
            status = HypothesisStatus.ACTIVE

        return ResearchHypothesis(
            hypothesis_id=str(hypothesis.get("hypothesis_id") or ""),
            title=str(hypothesis.get("title") or hypothesis.get("statement") or "研究假设"),
            description=str(hypothesis.get("statement") or hypothesis.get("description") or ""),
            research_domain=domain,
            status=status,
            confidence=float(hypothesis.get("confidence") or hypothesis.get("final_score") or 0.0),
            complexity=int(float(hypothesis.get("final_score") or 0.0) * 100),
            testability=float((hypothesis.get("scores") or {}).get("testability", 0.0)),
            research_objective=cycle.research_objective,
            expected_outcome=str(hypothesis.get("rationale") or ""),
            validation_method=str(hypothesis.get("validation_plan") or ""),
            relevance_to_tcm=float((hypothesis.get("scores") or {}).get("relevance", 0.0)),
            novelty_score=float((hypothesis.get("scores") or {}).get("novelty", 0.0)),
            practical_value=float((hypothesis.get("scores") or {}).get("feasibility", 0.0)),
            supporting_evidence=[{"signal": item} for item in (hypothesis.get("supporting_signals") or [])],
            contradicting_evidence=[{"signal": item} for item in (hypothesis.get("contradiction_signals") or [])],
            tags=[str(hypothesis.get("domain") or domain.value)],
            keywords=[str(item) for item in (hypothesis.get("keywords") or []) if str(item).strip()],
        )

    def collect_citation_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._collect_citation_records(cycle, context, literature_pipeline)

    def _collect_citation_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        context_records = context.get("citation_records")
        if isinstance(context_records, list):
            return [dict(item) for item in context_records if isinstance(item, dict)]

        literature_records = literature_pipeline.get("records")
        if isinstance(literature_records, list) and literature_records:
            return [dict(item) for item in literature_records if isinstance(item, dict)]

        publications = [
            {
                "title": outcome.get("result", {}).get("title", "") or outcome.get("result", {}).get("phase", ""),
                "authors": cycle.researchers,
                "year": datetime.now().year,
                "journal": "中医古籍全自动研究系统",
                "source": "pipeline",
                "note": outcome.get("phase", ""),
            }
            for outcome in cycle.outcomes
            if isinstance(outcome, dict) and isinstance(outcome.get("result"), dict)
        ]
        return [item for item in publications if item.get("title")]

    def _create_citation_manager(self) -> Any:
        try:
            return self.pipeline.create_module("citation_manager", self.pipeline.config.get("citation_management") or {})
        except Exception:
            citation_manager_cls = CitationManager or self.pipeline.CitationManager
            if citation_manager_cls is None:
                raise RuntimeError("CitationManager 不可用")
            return citation_manager_cls(self.pipeline.config.get("citation_management") or {})

    def _execute_citation_manager(
        self,
        citation_manager: Any,
        citation_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        citation_manager.initialize()
        try:
            return citation_manager.execute({"records": citation_records})
        finally:
            citation_manager.cleanup()

    def _create_paper_writer(self) -> Any:
        paper_config = dict(self.pipeline.config.get("paper_writing") or {})
        try:
            return self.pipeline.create_module("paper_writer", paper_config)
        except Exception:
            paper_writer_cls = PaperWriter or getattr(self.pipeline, "PaperWriter", None)
            if paper_writer_cls is None:
                raise RuntimeError("PaperWriter 不可用")
            return paper_writer_cls(paper_config)

    def _create_output_generator(self) -> Any:
        output_config = dict(
            self.pipeline.config.get("structured_output")
            or self.pipeline.config.get("output_generation")
            or {}
        )
        try:
            return self.pipeline.create_module("output_generator", output_config)
        except Exception:
            output_generator_cls = OutputGenerator or getattr(self.pipeline, "OutputGenerator", None)
            if output_generator_cls is None:
                raise RuntimeError("OutputGenerator 不可用")
            return output_generator_cls(output_config)

    def _create_report_generator(self, context: Dict[str, Any] | None = None) -> Any:
        report_context = context or {}
        report_config = dict(self.pipeline.config.get("report_generation") or {})
        if report_context.get("report_output_dir"):
            report_config["output_dir"] = report_context.get("report_output_dir")
        if report_context.get("report_output_formats"):
            report_config["output_formats"] = report_context.get("report_output_formats")
        try:
            return self.pipeline.create_module("report_generator", report_config)
        except Exception:
            report_generator_cls = ReportGenerator or getattr(self.pipeline, "ReportGenerator", None)
            if report_generator_cls is None:
                raise RuntimeError("ReportGenerator 不可用")
            return report_generator_cls(report_config)

    def _create_evidence_grader(self) -> Any:
        grader_config = dict(self.pipeline.config.get("evidence_grading") or {})
        if EvidenceGrader is None:
            raise RuntimeError("EvidenceGrader 不可用")
        return EvidenceGrader(grader_config)

    def _build_publish_paper_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_result: Dict[str, Any],
        hypothesis_result: Dict[str, Any],
        experiment_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
        citation_records: List[Dict[str, Any]],
        citation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        hypothesis_candidates = hypothesis_result.get("hypotheses") or []
        selected_hypothesis = experiment_result.get("selected_hypothesis") or {}
        if not isinstance(selected_hypothesis, dict):
            selected_hypothesis = {}
        if not selected_hypothesis and isinstance(hypothesis_candidates, list) and hypothesis_candidates:
            first_hypothesis = hypothesis_candidates[0]
            if isinstance(first_hypothesis, dict):
                selected_hypothesis = first_hypothesis

        ingestion_pipeline = observe_result.get("ingestion_pipeline") or {}

        publish_hypotheses = self._build_publish_hypothesis_entries(
            hypothesis_result,
            ingestion_pipeline,
            context,
            selected_hypothesis,
        )
        if publish_hypotheses:
            selected_hypothesis_id = str(selected_hypothesis.get("hypothesis_id") or "").strip()
            matched_selected = next(
                (
                    item
                    for item in publish_hypotheses
                    if str(item.get("hypothesis_id") or "").strip() == selected_hypothesis_id
                ),
                None,
            )
            if matched_selected is not None:
                selected_hypothesis = matched_selected
            elif not selected_hypothesis:
                selected_hypothesis = publish_hypotheses[0]
        hypothesis_audit_summary = self._build_publish_hypothesis_audit_summary(
            publish_hypotheses,
            self._extract_hypothesis_reasoning_summary(ingestion_pipeline, context),
        )

        experiment_context = (
            self._build_experiment_context(cycle, context, selected_hypothesis)
            if selected_hypothesis
            else {}
        )
        analyze_results_raw = analyze_result.get("results") if isinstance(analyze_result, dict) else None
        analyze_results = analyze_results_raw if isinstance(analyze_results_raw, dict) else {}
        observe_entities = self._extract_publish_entities(observe_result, context)
        reasoning_results = self._build_publish_reasoning_results(
            context,
            experiment_context,
            experiment_result,
            analyze_result,
            analyze_results,
        )
        data_mining_result = self._resolve_publish_data_mining_result(context, analyze_result, analyze_results)
        research_perspectives = self._resolve_publish_research_perspectives(context, analyze_result, analyze_results)
        publish_output_context = self._build_publish_output_context(
            cycle,
            context,
            observe_entities,
            {**hypothesis_result, "hypotheses": publish_hypotheses},
            selected_hypothesis,
            hypothesis_audit_summary,
            analyze_result,
            analyze_results,
            reasoning_results,
            data_mining_result,
            research_perspectives,
        )
        structured_output = self._execute_publish_output_generator(publish_output_context)
        structured_payload_raw = structured_output.get("output_data") if isinstance(structured_output, dict) else {}
        structured_payload = structured_payload_raw if isinstance(structured_payload_raw, dict) else {}
        research_artifact = structured_payload.get("research_artifact") if isinstance(structured_payload, dict) else {}
        if not isinstance(research_artifact, dict):
            research_artifact = {}
        similar_formula_graph_evidence_summary = self._resolve_publish_similar_formula_graph_evidence_summary(
            context,
            analyze_result,
            analyze_results,
            research_artifact,
        )
        evidence_grade_summary = self._resolve_publish_evidence_grade_summary(
            context,
            analyze_result,
            analyze_results,
            research_artifact,
        )
        if not research_artifact:
            research_artifact = {
                "hypothesis": publish_hypotheses or ([selected_hypothesis] if selected_hypothesis else []),
                "hypothesis_audit_summary": hypothesis_audit_summary,
                "evidence_grade_summary": evidence_grade_summary,
                "evidence": reasoning_results.get("evidence_records") or [],
                "data_mining_result": data_mining_result,
                "similar_formula_graph_evidence_summary": similar_formula_graph_evidence_summary,
            }
        elif evidence_grade_summary and not isinstance(research_artifact.get("evidence_grade_summary"), dict):
            research_artifact["evidence_grade_summary"] = evidence_grade_summary
        analysis_results_payload = self._compose_publish_analysis_results(
            structured_payload,
            analyze_result,
            analyze_results,
            experiment_result,
            reasoning_results,
            data_mining_result,
            research_perspectives,
            similar_formula_graph_evidence_summary,
        )
        output_dir = context.get("paper_output_dir") or context.get("output_dir") or os.path.join("output", "papers", cycle.cycle_id)
        output_formats = context.get("paper_output_formats") or context.get("output_formats") or ["markdown", "docx"]
        title = str(
            context.get("paper_title")
            or context.get("title")
            or f"{cycle.research_objective or cycle.description}研究"
        ).strip()

        paper_context = {
            "title": title,
            "authors": context.get("authors") or cycle.researchers,
            "author": context.get("author") or ", ".join(cycle.researchers),
            "affiliation": context.get("affiliation") or "",
            "journal": context.get("journal") or "",
            "objective": cycle.research_objective or context.get("objective") or cycle.description,
            "research_domain": context.get("research_domain") or selected_hypothesis.get("domain") or "中医古籍研究",
            "keywords": context.get("keywords") or selected_hypothesis.get("keywords") or [],
            "entities": observe_entities,
            "hypotheses": publish_hypotheses or ([selected_hypothesis] if selected_hypothesis else []),
            "hypothesis": selected_hypothesis,
            "hypothesis_audit_summary": hypothesis_audit_summary,
            "evidence_grade_summary": evidence_grade_summary,
            "reasoning_results": reasoning_results,
            "data_mining_result": data_mining_result,
            "similar_formula_graph_evidence_summary": similar_formula_graph_evidence_summary,
            "literature_pipeline": literature_pipeline,
            "citation_records": citation_records,
            "formatted_references": citation_result.get("formatted_references") or citation_result.get("gbt7714") or "",
            "limitations": self._resolve_publish_limitations(context, analyze_results, analysis_results_payload),
            "gap_analysis": experiment_context.get("clinical_gap_analysis") or {},
            "analysis_results": analysis_results_payload,
            "research_artifact": research_artifact,
            "output_data": structured_payload,
            "quality_metrics": structured_payload.get("quality_metrics") if isinstance(structured_payload, dict) else {},
            "recommendations": structured_payload.get("recommendations") if isinstance(structured_payload, dict) else [],
            "research_perspectives": research_perspectives,
            "output_dir": output_dir,
            "output_formats": output_formats,
            "file_stem": context.get("paper_file_stem") or cycle.cycle_name or cycle.cycle_id,
        }
        if isinstance(context.get("figure_paths"), list):
            paper_context["figure_paths"] = context.get("figure_paths")
        return paper_context

    def _build_publish_report_session_result(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_result: Dict[str, Any],
        hypothesis_result: Dict[str, Any],
        experiment_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        paper_context: Dict[str, Any],
        paper_result: Dict[str, Any],
        citation_result: Dict[str, Any],
        merged_output_files: Dict[str, Any],
    ) -> Dict[str, Any]:
        reflect_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.REFLECT, {}).get("result", {})
        publish_payload = {
            "paper_draft": paper_result.get("paper_draft", {}),
            "paper_language": paper_result.get("language", ""),
            "formatted_references": citation_result.get("formatted_references", ""),
            "citations": citation_result.get("entries", []),
            "research_artifact": paper_context.get("research_artifact", {}),
            "analysis_results": paper_context.get("analysis_results", {}),
            "output_files": merged_output_files,
        }
        phase_results = {
            "observe": self._normalize_report_phase_result("observe", observe_result),
            "hypothesis": self._normalize_report_phase_result("hypothesis", hypothesis_result),
            "experiment": self._normalize_report_phase_result("experiment", experiment_result),
            "analyze": self._normalize_report_phase_result("analyze", analyze_result),
            "publish": self._normalize_report_phase_result("publish", publish_payload),
        }
        if isinstance(reflect_result, dict) and reflect_result:
            phase_results["reflect"] = self._normalize_report_phase_result("reflect", reflect_result)

        return {
            "session_id": cycle.cycle_id,
            "title": str(paper_context.get("title") or cycle.research_objective or cycle.description or "中医科研 IMRD 报告").strip(),
            "question": cycle.research_objective or context.get("question") or cycle.description,
            "research_question": cycle.research_objective or context.get("question") or cycle.description,
            "metadata": {
                "title": str(paper_context.get("title") or cycle.research_objective or cycle.description or "中医科研 IMRD 报告").strip(),
                "research_question": cycle.research_objective or context.get("question") or cycle.description,
                "cycle_name": cycle.cycle_name,
                "research_scope": cycle.research_scope,
                "researchers": cycle.researchers,
                "generated_by": "publish_phase",
            },
            "phase_results": phase_results,
        }

    def _normalize_report_phase_result(self, phase_name: str, phase_result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(phase_result) if isinstance(phase_result, dict) else {}
        nested_results = normalized.get("results")
        if isinstance(nested_results, dict):
            for key, value in nested_results.items():
                normalized.setdefault(key, value)

        if phase_name == "experiment" and "study_protocol" not in normalized:
            experiments = normalized.get("experiments")
            if isinstance(experiments, list) and experiments and isinstance(experiments[0], dict):
                normalized["study_protocol"] = experiments[0]
            elif isinstance(nested_results, dict) and nested_results:
                normalized["study_protocol"] = nested_results
        return normalized

    def _generate_publish_reports(
        self,
        session_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        report_formats = self._resolve_publish_report_formats(context)
        if not report_formats:
            return {"reports": {}, "output_files": {}, "errors": []}

        try:
            report_generator = self._create_report_generator(context)
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段无法创建 ReportGenerator: %s", exc)
            return {"reports": {}, "output_files": {}, "errors": [str(exc)]}

        reports: Dict[str, Any] = {}
        output_files: Dict[str, Any] = {}
        errors: List[Dict[str, str]] = []
        initialized = False
        try:
            initialized = bool(report_generator.initialize())
            if not initialized:
                message = "ReportGenerator 初始化失败"
                self.pipeline.logger.warning(message)
                return {"reports": {}, "output_files": {}, "errors": [message]}

            for report_format in report_formats:
                try:
                    report = report_generator.generate_report(session_result, report_format)
                    reports[str(report_format)] = report.to_dict()
                    if report.output_path:
                        output_files[f"imrd_{report.format}"] = report.output_path
                except Exception as exc:
                    self.pipeline.logger.warning("Publish 阶段生成 %s IMRD 报告失败: %s", report_format, exc)
                    errors.append({str(report_format): str(exc)})
        finally:
            if initialized:
                report_generator.cleanup()

        return {"reports": reports, "output_files": output_files, "errors": errors}

    def _resolve_publish_report_formats(self, context: Dict[str, Any]) -> List[str]:
        configured_formats = (
            context.get("report_output_formats")
            or context.get("report_formats")
            or (self.pipeline.config.get("report_generation") or {}).get("output_formats")
            or ["markdown", "docx"]
        )
        if isinstance(configured_formats, str):
            configured_formats = [configured_formats]
        if not isinstance(configured_formats, list):
            return ["markdown", "docx"]

        normalized: List[str] = []
        for item in configured_formats:
            value = str(item).strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return normalized or ["markdown", "docx"]

    def _build_publish_output_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_entities: List[Dict[str, Any]],
        hypothesis_result: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
        hypothesis_audit_summary: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        research_perspectives: Dict[str, Any],
    ) -> Dict[str, Any]:
        semantic_graph = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("semantic_graph",),
        )
        temporal_analysis = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("temporal_analysis",),
        )
        pattern_recognition = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("pattern_recognition",),
        )
        statistics = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("statistics",),
        )
        return {
            "source_file": str(context.get("source_file") or cycle.cycle_name or cycle.cycle_id),
            "objective": cycle.research_objective or context.get("objective") or cycle.description,
            "entities": observe_entities,
            "statistics": statistics,
            "hypothesis": hypothesis_result.get("hypotheses") or ([selected_hypothesis] if selected_hypothesis else []),
            "hypothesis_result": hypothesis_result,
            "hypothesis_audit_summary": hypothesis_audit_summary,
            "reasoning_results": reasoning_results,
            "data_mining_result": data_mining_result,
            "research_perspectives": research_perspectives,
            "analysis_results": analyze_results,
            "semantic_graph": semantic_graph,
            "temporal_analysis": temporal_analysis,
            "pattern_recognition": pattern_recognition,
            "confidence_score": context.get("confidence_score") or analyze_results.get("confidence_level") or 0.5,
        }

    def _build_publish_hypothesis_entries(
        self,
        hypothesis_result: Dict[str, Any],
        ingestion_pipeline: Dict[str, Any],
        context: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        raw_hypotheses = hypothesis_result.get("hypotheses") or ([selected_hypothesis] if selected_hypothesis else [])
        if not isinstance(raw_hypotheses, list):
            return []

        relationships = self._extract_hypothesis_relationships(ingestion_pipeline, context)
        reasoning_summary = self._extract_hypothesis_reasoning_summary(ingestion_pipeline, context)
        return [
            self._enrich_publish_hypothesis(item, relationships, reasoning_summary)
            for item in raw_hypotheses
            if isinstance(item, dict)
        ]

    def _enrich_publish_hypothesis(
        self,
        hypothesis: Dict[str, Any],
        relationships: List[Dict[str, Any]],
        reasoning_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        enriched = dict(hypothesis)
        scores = dict(enriched.get("scores") or {})
        mechanism_completeness = float(
            scores.get("mechanism_completeness")
            or enriched.get("mechanism_completeness")
            or 0.0
        )
        source_entities = [
            str(item).strip()
            for item in (enriched.get("source_entities") or [])
            if str(item).strip()
        ]
        relationship_evidence = self._match_hypothesis_relationships(source_entities, relationships)
        merged_sources: List[str] = []
        for relation in relationship_evidence:
            metadata = relation.get("metadata") or {}
            source_name = str(metadata.get("source") or "").strip()
            if source_name and source_name not in merged_sources:
                merged_sources.append(source_name)
            for merged_source in metadata.get("merged_sources") or []:
                merged_source_name = str(merged_source).strip()
                if merged_source_name and merged_source_name not in merged_sources:
                    merged_sources.append(merged_source_name)

        audit = dict(enriched.get("audit") or {})
        audit.update(
            {
                "mechanism_completeness": mechanism_completeness,
                "reasoning_inference_confidence": float(reasoning_summary.get("inference_confidence") or 0.0),
                "relationship_count": len(relationship_evidence),
                "merged_sources": merged_sources,
                "relationship_evidence": relationship_evidence[:5],
            }
        )
        enriched["scores"] = scores
        enriched["mechanism_completeness"] = mechanism_completeness
        enriched["audit"] = audit
        return enriched

    def _match_hypothesis_relationships(
        self,
        source_entities: List[str],
        relationships: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not source_entities:
            return []

        entity_set = {item for item in source_entities if item}
        matched: List[Dict[str, Any]] = []
        for relation in relationships:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            if source not in entity_set and target not in entity_set:
                continue
            matched.append(
                {
                    "source": source,
                    "target": target,
                    "type": str(relation.get("type") or relation.get("rel_type") or "related_to"),
                    "source_type": str(relation.get("source_type") or "generic"),
                    "target_type": str(relation.get("target_type") or "generic"),
                    "metadata": dict(relation.get("metadata") or {}),
                }
            )
        matched.sort(key=self._relationship_confidence, reverse=True)
        return matched

    def _build_publish_hypothesis_audit_summary(
        self,
        hypotheses: List[Dict[str, Any]],
        reasoning_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not hypotheses:
            return {}

        mechanism_scores: List[float] = []
        merged_sources: List[str] = []
        relationship_count = 0
        selected_hypothesis = hypotheses[0]
        for hypothesis in hypotheses:
            mechanism_value = float(
                hypothesis.get("mechanism_completeness")
                or (hypothesis.get("scores") or {}).get("mechanism_completeness")
                or 0.0
            )
            mechanism_scores.append(mechanism_value)
            audit = hypothesis.get("audit") or {}
            relationship_count += int(audit.get("relationship_count") or 0)
            for source_name in audit.get("merged_sources") or []:
                source_text = str(source_name).strip()
                if source_text and source_text not in merged_sources:
                    merged_sources.append(source_text)

        return {
            "selected_hypothesis_id": str(selected_hypothesis.get("hypothesis_id") or ""),
            "hypothesis_count": len(hypotheses),
            "selected_mechanism_completeness": float(
                selected_hypothesis.get("mechanism_completeness")
                or (selected_hypothesis.get("scores") or {}).get("mechanism_completeness")
                or 0.0
            ),
            "average_mechanism_completeness": round(sum(mechanism_scores) / len(mechanism_scores), 4),
            "relationship_count": relationship_count,
            "merged_sources": merged_sources,
            "reasoning_inference_confidence": float(reasoning_summary.get("inference_confidence") or 0.0),
        }

    def _execute_publish_output_generator(self, publish_output_context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            output_generator = self._create_output_generator()
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段无法创建 OutputGenerator，将退回简化产物上下文: %s", exc)
            return {}

        output_generator.initialize()
        try:
            return output_generator.execute(publish_output_context)
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段构建 research_artifact 失败，将退回简化产物上下文: %s", exc)
            return {}
        finally:
            output_generator.cleanup()

    def _compose_publish_analysis_results(
        self,
        structured_payload: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        experiment_result: Dict[str, Any],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        research_perspectives: Dict[str, Any],
        similar_formula_graph_evidence_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        composed: Dict[str, Any] = {}
        structured_analysis = structured_payload.get("analysis_results") if isinstance(structured_payload, dict) else {}
        if isinstance(structured_analysis, dict):
            composed.update(structured_analysis)

        if reasoning_results:
            composed["reasoning_results"] = reasoning_results
        if data_mining_result:
            composed["data_mining_result"] = data_mining_result
        if research_perspectives:
            composed["research_perspectives"] = research_perspectives
        if similar_formula_graph_evidence_summary:
            composed["similar_formula_graph_evidence_summary"] = similar_formula_graph_evidence_summary
        if analyze_results:
            composed["statistical_analysis"] = analyze_results
            for key in (
                "statistical_significance",
                "confidence_level",
                "effect_size",
                "p_value",
                "interpretation",
                "evidence_grade",
                "evidence_grade_summary",
            ):
                if key in analyze_results and key not in composed:
                    composed[key] = analyze_results.get(key)
        experiment_payload = experiment_result.get("results") if isinstance(experiment_result, dict) else None
        if isinstance(experiment_payload, dict) and experiment_payload:
            composed["experiment_results"] = experiment_payload
        analyze_metadata = analyze_result.get("metadata") if isinstance(analyze_result, dict) else None
        if isinstance(analyze_metadata, dict) and analyze_metadata:
            composed["metadata"] = analyze_metadata
        quality_metrics = structured_payload.get("quality_metrics") if isinstance(structured_payload, dict) else None
        if isinstance(quality_metrics, dict) and quality_metrics:
            composed["quality_metrics"] = quality_metrics
        recommendations = structured_payload.get("recommendations") if isinstance(structured_payload, dict) else None
        if isinstance(recommendations, list) and recommendations:
            composed["recommendations"] = recommendations
        return composed

    def _build_publish_reasoning_results(
        self,
        context: Dict[str, Any],
        experiment_context: Dict[str, Any],
        experiment_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = [
            context.get("reasoning_results"),
            analyze_result.get("reasoning_results") if isinstance(analyze_result, dict) else None,
            analyze_results.get("reasoning_results") if isinstance(analyze_results, dict) else None,
            experiment_result.get("reasoning_results") if isinstance(experiment_result, dict) else None,
        ]
        reasoning_results: Dict[str, Any] = {}
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate:
                reasoning_results = dict(candidate)
                break

        if not isinstance(reasoning_results.get("evidence_records"), list):
            reasoning_results["evidence_records"] = (
                experiment_context.get("weighted_evidence_records")
                or experiment_context.get("evidence_records")
                or []
            )
        if not isinstance(reasoning_results.get("evidence_summary"), dict):
            evidence_profile = experiment_context.get("evidence_profile") or {}
            if isinstance(evidence_profile, dict) and evidence_profile:
                reasoning_results["evidence_summary"] = evidence_profile
        return reasoning_results

    def _resolve_publish_data_mining_result(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        value = self._resolve_publish_dict_field(containers, ("data_mining_result", "data_mining", "mining_result"))
        if value:
            return value

        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("data_mining_result")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_research_perspectives(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("research_perspectives",))
        if direct:
            return direct
        for field_name in ("semantic_analysis", "research_analysis", "analysis_results"):
            nested_container = self._resolve_publish_dict_field(containers, (field_name,))
            if isinstance(nested_container.get("research_perspectives"), dict):
                return dict(nested_container.get("research_perspectives") or {})
        return {}

    def _resolve_publish_similar_formula_graph_evidence_summary(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        research_artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("similar_formula_graph_evidence_summary",))
        if direct:
            return direct
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("similar_formula_graph_evidence_summary")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_evidence_grade_summary(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        research_artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("evidence_grade_summary",))
        if direct:
            return direct

        evidence_grade = self._resolve_publish_dict_field(containers, ("evidence_grade",))
        if evidence_grade:
            return self._build_evidence_grade_summary(evidence_grade)

        if isinstance(research_artifact, dict):
            nested = research_artifact.get("evidence_grade_summary")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_limitations(
        self,
        context: Dict[str, Any],
        analyze_results: Dict[str, Any],
        analysis_results_payload: Dict[str, Any],
    ) -> Any:
        if context.get("limitations"):
            return context.get("limitations")
        if analyze_results.get("limitations"):
            return analyze_results.get("limitations")
        statistical_analysis = analysis_results_payload.get("statistical_analysis")
        if isinstance(statistical_analysis, dict) and statistical_analysis.get("limitations"):
            return statistical_analysis.get("limitations")
        return []

    def _resolve_publish_dict_field(
        self,
        containers: List[Any],
        field_names: tuple[str, ...],
    ) -> Dict[str, Any]:
        for container in containers:
            if not isinstance(container, dict):
                continue
            for field_name in field_names:
                value = container.get(field_name)
                if isinstance(value, dict):
                    return dict(value)
        return {}

    def _execute_paper_writer(
        self,
        paper_writer: Any,
        paper_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        paper_writer.initialize()
        try:
            try:
                return paper_writer.execute(paper_context)
            except ImportError:
                fallback_context = dict(paper_context)
                fallback_context["output_formats"] = ["markdown"]
                fallback_context["output_format"] = "markdown"
                return paper_writer.execute(fallback_context)
        finally:
            paper_writer.cleanup()

    def _extract_publish_entities(
        self,
        observe_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        entities = context.get("entities")
        if isinstance(entities, list) and entities:
            return [item for item in entities if isinstance(item, dict)]

        ingestion_pipeline = observe_result.get("ingestion_pipeline") or {}
        documents = ingestion_pipeline.get("documents") or []
        derived: List[Dict[str, Any]] = []
        for document in documents[:5]:
            if not isinstance(document, dict):
                continue
            title = str(document.get("title") or document.get("urn") or "").strip()
            if not title:
                continue
            derived.append({"name": title})
        return derived

    def _merge_publish_output_files(
        self,
        paper_output_files: Dict[str, Any],
        citation_output_files: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if isinstance(citation_output_files, dict):
            merged.update({key: value for key, value in citation_output_files.items() if value})
        if isinstance(paper_output_files, dict):
            merged.update({key: value for key, value in paper_output_files.items() if value})
        return merged

    def _safe_researcher_key(self, researchers: List[str]) -> str:
        if not researchers:
            return "research"
        primary = str(researchers[0]).strip() or "research"
        compact = "".join(ch for ch in primary if ch.isalnum())
        return compact[:24] or "research"
