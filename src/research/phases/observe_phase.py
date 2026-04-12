from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

from src.collector.corpus_bundle import (
    CorpusBundle,
    extract_text_entries,
    is_corpus_bundle,
)
from src.cycle.cycle_runner import execute_real_module_pipeline
from src.research.phase_result import build_phase_result


class ObservePhaseMixin:
    """Mixin: observe 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_observe_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}

        corpus_result = self._collect_observe_corpus_if_enabled(context)
        literature_result = self._run_observe_literature_if_enabled(context)

        observations, findings = self._build_observe_seed_lists()
        self._append_corpus_observe_updates(corpus_result, observations, findings)

        ingestion_result = self._run_observe_ingestion_if_enabled(corpus_result, context)
        self._append_ingestion_observe_updates(ingestion_result, observations, findings)
        self._append_literature_observe_updates(literature_result, observations, findings)

        metadata = self._build_observe_metadata(
            context,
            observations,
            findings,
            corpus_result,
            ingestion_result,
            literature_result,
        )
        status = "degraded" if any(
            isinstance(item, dict) and item.get("error")
            for item in (corpus_result, ingestion_result, literature_result)
        ) else "completed"
        return build_phase_result(
            "observe",
            status=status,
            results={
                "observations": observations,
                "findings": findings,
                "corpus_collection": corpus_result,
                "ingestion_pipeline": ingestion_result,
                "literature_pipeline": literature_result,
            },
            metadata=metadata,
            extra_fields={
                "observations": observations,
                "findings": findings,
                "corpus_collection": corpus_result,
                "ingestion_pipeline": ingestion_result,
                "literature_pipeline": literature_result,
            },
        )

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
            "output_generation": self._has_observe_output_generation(ingestion_result, ingestion_ok),
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

    def _has_observe_output_generation(
        self,
        ingestion_result: Dict[str, Any] | None,
        ingestion_ok: bool,
    ) -> bool:
        if not ingestion_ok or not ingestion_result:
            return False
        aggregate = ingestion_result.get("aggregate") or {}
        return bool(aggregate.get("output_quality_metrics"))

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        if self.pipeline._should_collect_ctext_corpus(context) and self.pipeline._should_collect_local_corpus(context):
            return "ctext_whitelist+local"
        if self.pipeline._should_collect_ctext_corpus(context):
            return "ctext_whitelist"
        if self.pipeline._should_collect_local_corpus(context):
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
            self.pipeline.logger.error(f"观察阶段文献检索失败: {e}")
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

        # Backward-compatible alias used by run_cycle_demo research mode.
        if "collect_local_corpus" in context:
            return bool(context.get("collect_local_corpus"))

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
            self.pipeline.logger.error(f"观察阶段 ctext 采集失败: {e}")
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

        try:
            module_chain, cleanup_modules = self._build_observe_subpipeline_modules(context)
        except Exception as e:
            self.pipeline.logger.error("观察阶段子流程初始化失败: %s", e)
            return {"error": str(e)}

        document_results: List[Dict[str, Any]] = []
        entity_type_counts: Dict[str, int] = {}
        total_entities = 0
        confidence_values: List[float] = []
        total_semantic_nodes = 0
        total_semantic_edges = 0
        total_semantic_relationships: List[Dict[str, Any]] = []
        reasoning_summaries: List[Dict[str, Any]] = []
        output_quality_metrics: List[Dict[str, Any]] = []
        output_recommendations: List[str] = []

        try:
            for entry in selected_entries:
                raw_text = entry.get("text", "")[:max_chars_per_text]
                module_results = execute_real_module_pipeline(
                    {
                        "raw_text": raw_text,
                        "source_file": entry.get("urn", "unknown"),
                        "metadata": {
                            "title": entry.get("title", ""),
                            "source": "ctext",
                            "collection_stage": "observe",
                        },
                    },
                    modules=module_chain,
                    manage_module_lifecycle=False,
                    optional_modules={"ReasoningEngine", "OutputGenerator"},
                )

                preprocess_result = self._extract_module_output(module_results, "DocumentPreprocessor")
                extraction_result = self._extract_module_output(module_results, "EntityExtractor")
                semantic_result = self._extract_module_output(module_results, "SemanticModeler")
                reasoning_result = self._extract_module_output(module_results, "ReasoningEngine")
                output_result = self._extract_module_output(module_results, "OutputGenerator")

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
                if output_result:
                    quality_metrics = (output_result.get("output_data") or {}).get("quality_metrics")
                    if isinstance(quality_metrics, dict):
                        output_quality_metrics.append(quality_metrics)
                    recommendations = (output_result.get("output_data") or {}).get("recommendations")
                    if isinstance(recommendations, list):
                        for rec in recommendations:
                            rec_str = str(rec).strip() if rec else ""
                            if rec_str and rec_str not in output_recommendations:
                                output_recommendations.append(rec_str)

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
                        "output_generation": (output_result or {}).get("output_data"),
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
                    "output_quality_metrics": output_quality_metrics,
                    "output_recommendations": output_recommendations,
                },
            }
        except Exception as e:
            self.pipeline.logger.error("观察阶段预处理/抽取/建模链路失败: %s", e)
            return {"error": str(e)}
        finally:
            self._cleanup_observe_subpipeline_modules(cleanup_modules)

    def _build_observe_subpipeline_modules(
        self,
        context: Dict[str, Any],
    ) -> tuple[List[tuple[str, Any]], List[Any]]:
        preprocessor = self.pipeline.analysis_port.create_preprocessor(context.get("preprocessor_config") or {})
        extractor = self.pipeline.analysis_port.create_extractor(context.get("extractor_config") or {})
        semantic_builder = self.pipeline.analysis_port.create_semantic_builder(context.get("semantic_builder_config") or {})
        reasoning_engine = self.pipeline.analysis_port.create_reasoning_engine(context.get("reasoning_engine_config") or {})
        output_generator = self.pipeline.output_port.create_output_generator(context.get("output_generator_config") or {})

        cleanup_modules = [output_generator, reasoning_engine, semantic_builder, extractor, preprocessor]
        module_chain: List[tuple[str, Any]] = []

        if not preprocessor.initialize():
            raise RuntimeError("文档预处理器初始化失败")
        module_chain.append(("DocumentPreprocessor", preprocessor))

        if not extractor.initialize():
            raise RuntimeError("实体抽取器初始化失败")
        module_chain.append(("EntityExtractor", extractor))

        if not semantic_builder.initialize():
            raise RuntimeError("语义图构建器初始化失败")
        module_chain.append(("SemanticModeler", semantic_builder))

        if bool(context.get("run_reasoning", True)):
            if reasoning_engine.initialize():
                module_chain.append(("ReasoningEngine", reasoning_engine))
            else:
                self.pipeline.logger.warning("推理引擎初始化失败，继续使用语义图关系")

        if bool(context.get("run_output_generation", True)):
            if output_generator.initialize():
                module_chain.append(("OutputGenerator", output_generator))
            else:
                self.pipeline.logger.warning("输出生成器初始化失败，跳过结构化输出生成")

        return module_chain, cleanup_modules

    def _cleanup_observe_subpipeline_modules(self, modules: List[Any]) -> None:
        for module in reversed(modules):
            try:
                module.cleanup()
            except Exception as exc:
                self.pipeline.logger.warning("观察阶段子流程模块清理失败: %s", exc)

    def _extract_module_output(
        self,
        module_results: List[Dict[str, Any]],
        module_name: str,
    ) -> Dict[str, Any]:
        for module_result in module_results:
            if module_result.get("module") == module_name:
                if module_result.get("status") != "completed":
                    return {}
                output_data = module_result.get("output_data")
                return output_data if isinstance(output_data, dict) else {}
        return {}

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

