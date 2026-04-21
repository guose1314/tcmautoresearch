# src/research/handlers/analyze_handler.py
"""分析阶段处理器：统计分析、证据分级与研究方法路由。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline

logger = logging.getLogger(__name__)


class AnalyzePhaseHandler(BasePhaseHandler):
    """
    分析阶段处理器。

    负责：
    1. 统计分析（置信区间、效应量、P 值）
    2. GRADE 证据分级
    3. 通过 ResearchMethodRouter 调用对应研究方法分析器
       （FormulaStructure / NetworkPharmacology / ClassicalLiterature 等）
    4. 将分析结果写入 Neo4j（通过 StorageGateway）
    5. 记录 SelfLearningEngine 学习记录

    指令05 新增：ResearchMethodRouter 接入。
    指令06 新增：Neo4j 真实写入。
    指令09 新增：向 SelfLearningEngine 记录分析结果。
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行分析阶段，返回 results / metadata / method_results 等字段。"""
        # 1. 执行基础统计分析与证据分级
        result = self.pipeline.phase_handlers.execute_analyze_phase(cycle, context or {})

        # 2. 通过 ResearchMethodRouter 执行专属研究方法分析（指令05）
        method_results = self._run_method_router(cycle, context or {})
        if method_results:
            result["method_results"] = method_results

        # 3. 将分析结果写入 Neo4j（指令06）
        self._write_to_neo4j(result, cycle)

        # 4. 向 SelfLearningEngine 记录分析结果（指令09）
        self._record_to_learning_engine(result, cycle)

        return result

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _run_method_router(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """通过 ResearchMethodRouter 路由研究方法分析。"""
        try:
            from src.research.method_router import ResearchMethodRouter

            router = ResearchMethodRouter()
            # 从上下文或观察阶段提取语料
            observe_result = cycle.phase_executions.get(
                self.pipeline.ResearchPhase.OBSERVE, {}
            ).get("result", {})
            corpus = (
                context.get("corpus")
                or observe_result.get("corpus_collection")
                or observe_result.get("ingestion_pipeline")
                or {}
            )
            analysis_types: List[str] = context.get(
                "analysis_types",
                ["formula_structure", "classical_literature"],
            )
            results: Dict[str, Any] = {}
            for analysis_type in analysis_types:
                try:
                    results[analysis_type] = router.route(analysis_type, corpus)
                except Exception as exc:
                    logger.warning("研究方法 %s 分析失败: %s", analysis_type, exc)
                    results[analysis_type] = {"status": "error", "error": str(exc)}
            return results
        except Exception as exc:
            logger.warning("ResearchMethodRouter 初始化失败，跳过方法路由: %s", exc)
            return {}

    def _write_to_neo4j(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> None:
        """将分析结果写入 Neo4j 图谱（指令06）。"""
        try:
            from src.storage.storage_gateway import StorageGateway

            gateway = StorageGateway.from_config(self.pipeline.config)
            if gateway is not None:
                gateway.save_research_result(cycle.cycle_id, result)
        except Exception as exc:
            logger.warning("分析结果写入 Neo4j 失败（跳过）: %s", exc)

    def _record_to_learning_engine(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> None:
        """向 SelfLearningEngine 记录分析结果（指令08/09）。"""
        try:
            if hasattr(self.pipeline, "learning_engine") and self.pipeline.learning_engine:
                quality = float(
                    result.get("results", {}).get("confidence_level", 0.5)
                )
                self.pipeline.learning_engine.record_outcome(result, quality)
        except Exception as exc:
            logger.warning("SelfLearningEngine 记录失败（跳过）: %s", exc)
