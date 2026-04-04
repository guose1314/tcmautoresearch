#!/usr/bin/env python3
"""Rebuild observe_phase.py from the original pipeline_phase_handlers content.

Run: python tools/_rebuild_observe_phase.py
"""
import pathlib
import textwrap

TARGET = pathlib.Path("src/research/phases/observe_phase.py")

CONTENT = '''\
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
from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph


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
        collect_ctext = self._should_collect_ctext_corpus(context)
        collect_local = self._should_collect_local_corpus(context)

        if not collect_ctext and not collect_local:
            return None

        bundles: list[CorpusBundle] = []
        fallback_error: Dict[str, Any] | None = None

        ctext_result = self._collect_ctext_observation_corpus(context) if collect_ctext else None
        fallback_error = self._register_observe_collection_result(
            ctext_result,
            "ctext",
            bundles,
            fallback_error,
        )

        local_result = self._collect_local_observation_corpus(context) if collect_local else None
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
            findings.append(f"语料采集失败: {corpus_result[\'error\']}")
            return

        if is_corpus_bundle(corpus_result):
            stats = corpus_result.get("stats", {})
            sources = corpus_result.get("sources", [])
            total = stats.get("total_documents", 0)
            if sources == ["ctext"]:
                observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get(\'document_count\', total)} 个根文献")
                findings.insert(0, "观察阶段已接入标准语料白名单，可直接进入后续假设生成")
            else:
                source_label = "+".join(sources) if sources else "多来源"
                observations.insert(0, f"已从 {source_label} 自动采集 {total} 篇文档（CorpusBundle）")
                findings.insert(0, "观察阶段已输出统一 CorpusBundle，多来源文档可直接进入后续假设生成")
            return

        stats = corpus_result.get("stats", {})
        observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get(\'document_count\', 0)} 个根文献")
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
            findings.append(f"预处理、实体抽取与语义建模链路失败: {ingestion_result[\'error\']}")
            return

        aggregate = ingestion_result.get("aggregate", {})
        observations.append(
            f"已完成 {ingestion_result.get(\'processed_document_count\', 0)} 篇文本的预处理、实体抽取与语义建模"
        )
        findings.append(f"首段主流程累计识别 {aggregate.get(\'total_entities\', 0)} 个实体")
        findings.append(
            f"累计构建 {aggregate.get(\'semantic_graph_nodes\', 0)} 个语义节点与 {aggregate.get(\'semantic_graph_edges\', 0)} 条关系"
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
            findings.append(f"文献检索链路失败: {literature_result[\'error\']}")
            return

        clinical_gap = literature_result.get("clinical_gap_analysis") or {}
        evidence_matrix = literature_result.get("evidence_matrix", {})
        observations.append(
            f"已完成 {literature_result.get(\'record_count\', 0)} 条医学文献检索并抽取摘要证据"
        )
        findings.append(f"证据矩阵覆盖 {evidence_matrix.get(\'dimension_count\', 0)} 个维度")
        findings.append(
            f"文献来源统计: {\', \'.join(literature_result.get(\'source_counts_summary\', [])) or \'无\'}"
        )
        if clinical_gap.get("report"):
            findings.append("已完成 Qwen 临床关联 Gap Analysis，可直接用于选题与方案设计")
'''

print(f"Content length: {len(CONTENT)}")
# This approach is going to be complex with escaping. Better approach below.
print("ABORTED - will use direct file write instead")
