# src/research/handlers/observe_handler.py
"""观察阶段处理器：文献采集、预处理、实体抽取、语义建模与 LLM 文献考证（I-02）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase

logger = logging.getLogger(__name__)


class ObservePhaseHandler(BasePhaseHandler):
    """
    观察阶段处理器（指令 I-02 重构版）。

    负责：
    1. 从 CText / 本地语料库 / 文献数据库采集原始数据
    2. 文档预处理（分词、标准化）
    3. 实体抽取与语义图构建
    4. 推理引擎运行
    5. 临床 Gap Analysis（可选）
    6. 【I-02 新增】LLMResearchAdvisor 文献考证分析
    7. 【I-02 新增】将高质量观察写入 StorageGateway
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行观察阶段，返回 observations / findings / corpus_collection 等字段。"""
        # 1. 执行基础采集、预处理与实体抽取
        result = self.pipeline.phase_handlers.execute_observe_phase(cycle, context or {})

        # 2. LLMResearchAdvisor 文献考证分析（I-02）
        llm_advisory = self._run_llm_analysis(result, cycle, context or {})
        if llm_advisory:
            result["llm_advisory"] = llm_advisory

        # 3. 将观察结果持久化到 StorageGateway（I-03）
        self._persist_result(result, cycle)

        return result

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _run_llm_analysis(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """调用 LLMResearchAdvisor 对采集到的文献进行考证分析（I-02）。"""
        try:
            from src.research.llm_research_advisor import LLMResearchAdvisor

            # 尝试从 pipeline 获取 LLM + RAG 服务
            llm = getattr(self.pipeline, "_llm_engine", None)
            rag = getattr(self.pipeline, "_rag_service", None)

            if llm is None:
                logger.debug("ObserveHandler: LLM 未配置，跳过文献考证分析")
                return {}

            advisor = LLMResearchAdvisor(llm_engine=llm, rag_service=rag)

            # 提取观察阶段的文本内容供 LLM 分析
            corpus_text = self._extract_corpus_text(result)
            if not corpus_text:
                return {}

            advisory = advisor.advise(
                phase="observe",
                context={"text": corpus_text},
                use_rag=True,
                use_hyde=True,
            )

            advisory_dict = advisory.to_dict()
            # 将 LLM 发现追加到 findings
            if advisory.conclusion:
                result.setdefault("findings", [])
                result["findings"].append(f"[LLM考证] {advisory.conclusion[:200]}")
            if advisory.evidence:
                result.setdefault("observations", [])
                for ev in advisory.evidence[:3]:
                    result["observations"].append(f"[文献证据] {ev}")

            logger.debug(
                "ObserveHandler: LLM 文献考证完成，confidence=%.2f, grounded=%s",
                advisory.confidence,
                advisory.is_grounded,
            )
            return advisory_dict
        except Exception as exc:
            logger.warning("ObserveHandler: LLM 分析失败（跳过）: %s", exc)
            return {}

    def _extract_corpus_text(self, result: Dict[str, Any]) -> str:
        """从观察阶段结果中提取可供 LLM 分析的文本。"""
        parts: List[str] = []

        # 优先提取 CorpusBundle 中的文本
        corpus = result.get("corpus_collection")
        if isinstance(corpus, dict):
            docs = corpus.get("documents") or []
            for doc in docs[:3]:
                if isinstance(doc, dict):
                    text = doc.get("content") or doc.get("text") or ""
                    if text:
                        parts.append(str(text)[:400])

        # 其次提取 ingestion_pipeline 摘要
        ingestion = result.get("ingestion_pipeline")
        if isinstance(ingestion, dict):
            summary = ingestion.get("summary") or ingestion.get("description") or ""
            if summary:
                parts.append(str(summary)[:200])

        # 最后使用 observations 列表
        for obs in result.get("observations", [])[:3]:
            parts.append(str(obs)[:150])

        return "\n".join(parts)[:800] if parts else ""

    def _persist_result(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> None:
        """将观察结果写入 StorageGateway（I-03）。"""
        try:
            gateway = getattr(self.pipeline, "_storage_gateway", None)
            if gateway is None:
                from src.storage.storage_gateway import StorageGateway
                gateway = StorageGateway.from_config(self.pipeline.config)
            if gateway is not None:
                gateway.save_research_result(cycle.cycle_id, result)
        except Exception as exc:
            logger.debug("ObserveHandler: 结果持久化失败（跳过）: %s", exc)
