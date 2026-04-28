import unittest
from unittest.mock import MagicMock, patch

from src.analysis.evolution_tracer import GraphEvolutionTracer


class TestGraphRagTraceability(unittest.TestCase):
    """集成测试验证接口：输入“四物汤”，执行分析任务，强制要求 Qwen 附带引用并映射回 Neo4j 原文 ID"""

    @patch("src.storage.neo4j_driver.Neo4jDriver")
    @patch("src.infra.llm_service.CachedLLMService")
    def test_pulse_difference_analysis(self, mock_llm_service_cls, mock_neo4j_cls):
        # 1. 模拟 Neo4j 图谱召回数据：证明流转追溯的可视化链条节点
        mock_driver = mock_neo4j_cls.return_value
        mock_session = MagicMock()
        mock_driver.driver.session.return_value.__enter__.return_value = mock_session
        
        # 模拟执行 Cypher 时返回的 records
        fake_records = [
            {"literature": "局方", "lit_id": "lit-jf-1", "herbs": ["熟地", "当归", "白芍", "川芎"]},
            {"literature": "仙授理伤续断秘方", "lit_id": "lit-xs-2", "herbs": ["地黄", "当归", "白芍", "川芎", "白芷"]}
        ]
        mock_session.run.return_value = fake_records
        
        # 2. 模拟 LLM (Qwen) 的 GraphRAG 链条追溯接口产出
        mock_llm = mock_llm_service_cls.return_value
        # 返回 JSON 字符串确保 parser 能加载
        mock_llm._request_completion.return_value = '''
        {
            "differences_summary": "《局方》以熟地见长，追求补血调血；《仙授理伤续断秘方》中多了一味【白芷】，以治伤活血理气为主。",
            "citations": ["局方", "仙授理伤续断秘方"]
        }
        '''
        
        # 3. 实例化 tracer 并运行测试
        tracer = GraphEvolutionTracer(neo4j_driver=mock_driver, llm_engine=mock_llm)
        result = tracer.trace_formula_evolution("四物汤")
        
        # 4. 断言结构呈现
        # (1) Dashboard 呈现的完整的链条节点：文献A版本 -> 药方X -> 药味组合1 对比 ...
        self.assertEqual(len(result.visual_chain_nodes), 2)
        self.assertEqual(result.visual_chain_nodes[0], "局方 -> 四物汤 -> 熟地、当归、白芍、川芎")
        self.assertEqual(result.visual_chain_nodes[1], "仙授理伤续断秘方 -> 四物汤 -> 地黄、当归、白芍、川芎、白芷")
        
        # (2) Citations：强制解析引用并映射回 Neo4j 的原文 ID
        self.assertEqual(len(result.citations), 2)
        
        neo4j_ids = [c["neo4j_node_id"] for c in result.citations]
        self.assertIn("lit-jf-1", neo4j_ids)
        self.assertIn("lit-xs-2", neo4j_ids)
        
        print("===== 溯源追踪及 Graph-RAG 集成测试成功 (四物汤) =====")
        print("脉络差异:")
        print(result.differences_summary)
        print("\n链条可视化:")
        for node in result.visual_chain_nodes:
            print(f"- {node}")
        print("\nCitations mapped to Neo4j IDs:")
        for c in result.citations:
            print(f"- 引用了原典 {c['citation_text']}, DB_ID [{c['neo4j_node_id']}]")

if __name__ == "__main__":
    unittest.main()
