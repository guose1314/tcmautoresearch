# -*- coding: utf-8 -*-
"""tests/test_kg_rag.py — KGRAGService 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.kg_rag import KGRAGContext, KGRAGService

# ===================================================================
# KGRAGContext
# ===================================================================


class TestKGRAGContext:
    def test_empty_by_default(self):
        ctx = KGRAGContext()
        assert ctx.empty
        assert ctx.format() == ""

    def test_format_with_facts(self):
        ctx = KGRAGContext()
        ctx.entities_found = [{"name": "黄芪", "type": "herb"}]
        ctx.graph_facts = ["黄芪 功效: 补气, 固表, 利水"]
        text = ctx.format()
        assert "黄芪" in text
        assert "补气" in text
        assert not ctx.empty

    def test_format_with_similar_items(self):
        ctx = KGRAGContext()
        ctx.similar_items = [{"name": "人参", "text": "人参-补气健脾", "score": 0.85}]
        text = ctx.format()
        assert "人参" in text
        assert "0.85" in text

    def test_format_combined(self):
        ctx = KGRAGContext()
        ctx.entities_found = [{"name": "四君子汤", "type": "formula"}]
        ctx.graph_facts = ["四君子汤 组成 — 君药: 人参"]
        ctx.similar_items = [{"name": "六君子汤", "text": "六君子汤", "score": 0.9}]
        text = ctx.format()
        assert "识别到的实体" in text
        assert "知识图谱事实" in text
        assert "语义相似项" in text


# ===================================================================
# Entity extraction
# ===================================================================


class TestExtractEntities:
    def test_extract_formula(self):
        svc = KGRAGService()
        entities = svc.extract_entities("四君子汤的组成是什么？")
        names = {e["name"] for e in entities}
        assert "四君子汤" in names

    def test_extract_herb(self):
        svc = KGRAGService()
        entities = svc.extract_entities("黄芪有什么功效？")
        names = {e["name"] for e in entities}
        assert "黄芪" in names

    def test_extract_efficacy(self):
        svc = KGRAGService()
        entities = svc.extract_entities("哪些药物可以补气？")
        types = {e["type"] for e in entities}
        assert "efficacy" in types

    def test_extract_multiple(self):
        svc = KGRAGService()
        entities = svc.extract_entities("四君子汤中黄芪的补气作用")
        names = {e["name"] for e in entities}
        assert "四君子汤" in names
        assert "黄芪" in names

    def test_empty_query(self):
        svc = KGRAGService()
        assert svc.extract_entities("") == []

    def test_no_match(self):
        svc = KGRAGService()
        assert svc.extract_entities("今天天气怎么样") == []

    def test_no_duplicate(self):
        svc = KGRAGService()
        entities = svc.extract_entities("人参人参人参")
        assert len([e for e in entities if e["name"] == "人参"]) == 1


# ===================================================================
# Retrieve — graph facts
# ===================================================================


class TestRetrieveGraph:
    @pytest.fixture()
    def mock_kg(self):
        kg = MagicMock()
        # get_subgraph returns a mock DiGraph
        mock_graph = MagicMock()
        mock_graph.edges.return_value = [
            ("四君子汤", "人参", {"rel_type": "SOVEREIGN"}),
            ("四君子汤", "白术", {"rel_type": "MINISTER"}),
        ]
        kg.get_subgraph.return_value = mock_graph
        kg.neighbors.return_value = []
        return kg

    def test_retrieve_with_kg(self, mock_kg):
        svc = KGRAGService(knowledge_graph=mock_kg)
        ctx = svc.retrieve("四君子汤的组成")
        assert not ctx.empty
        assert len(ctx.graph_facts) > 0
        # Subgraph queried
        mock_kg.get_subgraph.assert_called()

    def test_retrieve_no_kg(self):
        svc = KGRAGService(knowledge_graph=None)
        ctx = svc.retrieve("四君子汤")
        # Should still extract entities but no graph facts
        assert len(ctx.entities_found) > 0
        assert len(ctx.graph_facts) == 0

    def test_retrieve_empty_query(self):
        svc = KGRAGService()
        ctx = svc.retrieve("")
        assert ctx.empty

    def test_retrieve_formula_details(self, mock_kg):
        """formula类型实体应补充组成事实。"""
        svc = KGRAGService(knowledge_graph=mock_kg)
        ctx = svc.retrieve("四君子汤的功效")
        # Should have subgraph facts + composition facts
        facts_text = "\n".join(ctx.graph_facts)
        assert "四君子汤" in facts_text

    def test_retrieve_herb_efficacies(self, mock_kg):
        """herb类型实体应补充功效事实。"""
        mock_kg.get_subgraph.return_value = MagicMock(edges=MagicMock(return_value=[]))
        svc = KGRAGService(knowledge_graph=mock_kg)
        ctx = svc.retrieve("黄芪的作用")
        facts_text = "\n".join(ctx.graph_facts)
        assert "黄芪" in facts_text
        assert "补气" in facts_text

    def test_max_facts_limit(self, mock_kg):
        """事实数应受 max_facts 限制。"""
        mock_graph = MagicMock()
        mock_graph.edges.return_value = [
            (f"A{i}", f"B{i}", {"rel_type": "REL"}) for i in range(50)
        ]
        mock_kg.get_subgraph.return_value = mock_graph
        svc = KGRAGService(knowledge_graph=mock_kg, max_facts=5)
        ctx = svc.retrieve("四君子汤")
        assert len(ctx.graph_facts) <= 5

    def test_kg_exception_handled(self, mock_kg):
        """KG 查询异常应被捕获，不中断。"""
        mock_kg.get_subgraph.side_effect = RuntimeError("DB down")
        svc = KGRAGService(knowledge_graph=mock_kg)
        ctx = svc.retrieve("四君子汤")
        # No crash, just empty graph facts (composition may still come from static data)
        assert isinstance(ctx, KGRAGContext)


# ===================================================================
# Retrieve — embedding search
# ===================================================================


class TestRetrieveEmbedding:
    @pytest.fixture()
    def mock_emb(self):
        emb = MagicMock()
        result = MagicMock()
        result.item_id = "六味地黄丸"
        result.text = "六味地黄丸-滋阴补肾"
        result.item_type = "formula"
        result.score = 0.82
        emb.search.return_value = [result]
        return emb

    def test_retrieve_with_embedding(self, mock_emb):
        svc = KGRAGService(embedding_service=mock_emb)
        ctx = svc.retrieve("补肾方剂")
        assert len(ctx.similar_items) == 1
        assert ctx.similar_items[0]["name"] == "六味地黄丸"
        mock_emb.search.assert_called_once()

    def test_embedding_exception_handled(self, mock_emb):
        mock_emb.search.side_effect = RuntimeError("model not loaded")
        svc = KGRAGService(embedding_service=mock_emb)
        ctx = svc.retrieve("补肾方剂")
        assert len(ctx.similar_items) == 0  # graceful degradation


# ===================================================================
# AssistantEngine integration
# ===================================================================


class TestAssistantEngineKGRAG:
    def test_chat_with_kg_rag(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "AI 回复"

        mock_rag = MagicMock()
        rag_ctx = KGRAGContext()
        rag_ctx.graph_facts = ["四君子汤 组成 — 君药: 人参"]
        mock_rag.retrieve.return_value = rag_ctx

        from src.ai_assistant.assistant_engine import AssistantEngine
        engine = AssistantEngine(llm_engine=mock_llm, kg_rag=mock_rag)
        result = engine.chat("四君子汤的组成")

        assert result["reply"] == "AI 回复"
        # KG-RAG should have been called
        mock_rag.retrieve.assert_called_once_with("四君子汤的组成")
        # The prompt sent to LLM should contain KG context
        prompt_arg = mock_llm.generate.call_args[0][0]
        assert "知识图谱参考" in prompt_arg

    def test_chat_without_kg_rag(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "回复"

        from src.ai_assistant.assistant_engine import AssistantEngine
        engine = AssistantEngine(llm_engine=mock_llm, kg_rag=None)
        result = engine.chat("你好")

        assert result["reply"] == "回复"
        # No KG-RAG injection
        prompt_arg = mock_llm.generate.call_args[0][0]
        assert "知识图谱参考" not in prompt_arg

    def test_chat_kg_rag_error_handled(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "回复"

        mock_rag = MagicMock()
        mock_rag.retrieve.side_effect = RuntimeError("KG down")

        from src.ai_assistant.assistant_engine import AssistantEngine
        engine = AssistantEngine(llm_engine=mock_llm, kg_rag=mock_rag)
        result = engine.chat("四君子汤")

        # Should not crash, returns normal reply
        assert result["reply"] == "回复"
