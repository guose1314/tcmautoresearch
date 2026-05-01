"""
古方脉络差异追溯与 Graph-RAG 分析引擎 (Graph-RAG Traceability Engine)

追踪“同类药方在不同文献分布”的差异，强制 Qwen 输出带有具体溯源的分析结论。
自动将大模型生成的引文 (Citations) 映射回 Neo4j 图谱的对应节点 (如文献版本原文 ID)。
"""

import copy
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.infra.llm_service import CachedLLMService
from src.storage.neo4j_driver import Neo4jDriver

logger = logging.getLogger(__name__)


class PulseDifferenceAnalysisResult(BaseModel):
    formula_name: str
    differences_summary: str
    visual_chain_nodes: List[str]
    citations: List[Dict[str, str]] = Field(default_factory=list)


class GraphEvolutionTracer:
    def __init__(
        self, neo4j_driver: Neo4jDriver, llm_engine: Optional[CachedLLMService] = None
    ):
        self.neo4j = neo4j_driver
        self.llm = llm_engine or CachedLLMService()

    def trace_formula_evolution(
        self, formula_name: str
    ) -> PulseDifferenceAnalysisResult:
        """
        根据方名检索该药方在不同文献 (Literature) 中用药 (Herb) 的流变情况
        输出脉络差异报告和带引文的完整验证链。
        """
        # 1. 抓取 Graph Context
        graph_data = self._pull_graph_context(formula_name)
        if not graph_data:
            return PulseDifferenceAnalysisResult(
                formula_name=formula_name,
                differences_summary="图谱中尚未找到该方剂的相关文献记录。",
                visual_chain_nodes=[],
            )

        # 2. 让 LLM 做带有严格溯源限制的分析
        analysis_payload, used_task_ids = self._invoke_llm_for_analysis(
            formula_name, graph_data
        )

        # 3. 产出验证与溯源链条可视化
        visual_nodes = []
        for gd in graph_data:
            lit_title = gd.get("literature", "未知文献")
            herbs_str = "、".join(gd.get("herbs", []))
            # 形式如: 文献A版本 -> 药方X -> 药味组合1
            visual_nodes.append(f"{lit_title} -> {formula_name} -> {herbs_str}")

        # 4. Evaluation Loop - Evaluate output and feedback to SelfLearningEngine
        try:
            from src.core.architecture import ModuleRegistry
            from src.learning.quality_assessor import QualityAssessor

            assessor = QualityAssessor()
            context = {"graph_data": graph_data}
            quality_score = assessor.evaluate(analysis_payload, context)

            engine_info = ModuleRegistry.get_instance().get_module(
                "self_learning_engine"
            )
            if engine_info and getattr(engine_info, "instance", None):
                engine_info.instance.apply_few_shot_feedback(
                    used_task_ids, quality_score
                )
        except Exception as e:
            logger.warning(f"Quality feedback loop failed: {e}")

        return PulseDifferenceAnalysisResult(
            formula_name=formula_name,
            differences_summary=analysis_payload.get("differences_summary", ""),
            visual_chain_nodes=visual_nodes,
            citations=self._map_citations(
                analysis_payload.get("citations", []), graph_data
            ),
        )

    def _pull_graph_context(self, formula_name: str) -> List[Dict[str, Any]]:
        # 从命中的实体节点出发，抓取该节点关联的“文献来源”、“包含的药组变化”
        cypher = (
            "MATCH (p:Prescription {name: $formula}) "
            "OPTIONAL MATCH (p)-[:APPEARS_IN]->(l:Literature) "
            "OPTIONAL MATCH (p)-[c:CONTAINS]->(h:Herb) "
            "RETURN coalesce(l.title, '未知出处') AS literature, "
            "       l.id AS lit_id, "
            "       collect(DISTINCT h.name) AS herbs"
        )

        results = []
        try:
            with self.neo4j.driver.session(database=self.neo4j.database) as session:
                records = session.run(cypher, formula=formula_name)
                for rec in records:
                    lit = rec.get("literature")
                    # 防止由于 OPTIONAL MATCH 导致没有药材却产生空条目的情况
                    herbs = rec.get("herbs", [])
                    if not herbs:
                        continue
                    results.append(
                        {
                            "literature": lit,
                            "lit_id": rec.get("lit_id") or f"lit-{lit}",
                            "herbs": herbs,
                        }
                    )
        except Exception as e:
            logger.warning(f"Neo4j 图谱游走失败: {e}")

        return results

    def _invoke_llm_for_analysis(
        self, formula_name: str, graph_data: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Any], list[str]]:
        """
        利用大模型融合 Graph Context 进行分析。
        要求大模型在输出结论必须带文献标题。
        """
        graph_text = "\n".join(
            [
                f"- 出处: 《{d['literature']}》 | 药味组合: {','.join(d['herbs'])}"
                for d in graph_data
            ]
        )

        dynamic_few_shot = ""
        task_ids = []
        try:
            from src.core.architecture import ModuleRegistry

            engine_info = ModuleRegistry.get_instance().get_module(
                "self_learning_engine"
            )
            if engine_info and getattr(engine_info, "instance", None):
                # Request dynamic few shot context AND task ids
                dynamic_few_shot, task_ids = (
                    engine_info.instance.get_dynamic_few_shot_context(limit=2)
                )
        except Exception as e:
            logger.warning(f"获取动态 Few-Shot 失败: {e}")

        prompt = f"""你是一名精通文献溯源的中医专家。现在我们需要追踪古方“{formula_name}”在不同朝代/文献中的流变差异。
图谱召回知识范围如下：
{graph_text}
{dynamic_few_shot}
请你输出 JSON 格式的结论，字段如下：
1. "differences_summary": 对方剂的药味变化与脉络差异的综合分析结论。如果提取规律有冲突，请显式说明（例如：“虽然《X》未提及某药，但《Y》加入了某药”）。
2. "citations": 列出分析中引用到的文献列表，如 ["文献标题A", "文献标题B"]。该字段必须严格出自你引用的依据。
"""
        # Fallback payload
        fallback_res = {
            "differences_summary": "测试环境或 LLM 服务未就绪，使用占位符分析结论。脉络：发现图谱存在明显药物差异或沿袭关系。",
            "citations": [d["literature"] for d in graph_data],
        }

        try:
            raw_response = self.llm._request_completion(
                "gpt-3.5-turbo", [{"role": "user", "content": prompt}], temperature=0.1
            )
            # 简单剥离 JSON block (容错性)
            cleaned = raw_response.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned), task_ids
        except Exception as e:
            logger.warning(f"LLM 调用异常，启用降级占位: {e}")
            return fallback_res, []

    def _map_citations(
        self, citations: List[str], graph_data: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        mapped = []
        lit_dict = {d["literature"]: d["lit_id"] for d in graph_data}
        for cit in citations:
            matched_id = lit_dict.get(cit)
            if matched_id:
                mapped.append({"citation_text": cit, "neo4j_node_id": matched_id})
        return mapped
