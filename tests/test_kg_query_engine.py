# -*- coding: utf-8 -*-
"""tests/test_kg_query_engine.py — KGQueryEngine 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.kg_query_engine import (
    INTENT_COMPOSITION,
    INTENT_EFFICACY,
    INTENT_HERB_FORMULAS,
    INTENT_PATH,
    INTENT_SIMILAR,
    INTENT_STATISTICS,
    INTENT_TREATING,
    INTENT_UNKNOWN,
    KGQueryEngine,
    QueryResult,
    _is_safe_cypher,
)

# ===================================================================
# Cypher 安全校验
# ===================================================================


class TestCypherSafety:
    def test_safe_match_return(self):
        assert _is_safe_cypher("MATCH (n) RETURN n")

    def test_safe_with_where(self):
        assert _is_safe_cypher("MATCH (n) WHERE n.name = 'x' RETURN n")

    def test_unsafe_create(self):
        assert not _is_safe_cypher("CREATE (n:Node {name: 'x'})")

    def test_unsafe_delete(self):
        assert not _is_safe_cypher("MATCH (n) DELETE n")

    def test_unsafe_set(self):
        assert not _is_safe_cypher("MATCH (n) SET n.x = 1 RETURN n")

    def test_unsafe_merge(self):
        assert not _is_safe_cypher("MERGE (n:Node {name: 'x'})")

    def test_unsafe_drop(self):
        assert not _is_safe_cypher("DROP INDEX my_index")

    def test_unsafe_detach_delete(self):
        assert not _is_safe_cypher("MATCH (n) DETACH DELETE n")

    def test_safe_string_containing_create(self):
        # CREATE inside a string literal should be ignored
        assert _is_safe_cypher("MATCH (n) WHERE n.desc = 'CREATE something' RETURN n")

    def test_unsafe_remove(self):
        assert not _is_safe_cypher("MATCH (n) REMOVE n.prop RETURN n")


# ===================================================================
# 意图识别
# ===================================================================


class TestDetectIntent:
    @pytest.fixture()
    def engine(self):
        return KGQueryEngine()

    def test_composition_intent(self, engine):
        assert engine.detect_intent("四君子汤的组成是什么") == INTENT_COMPOSITION

    def test_composition_intent_junshen(self, engine):
        assert engine.detect_intent("四君子汤的君臣佐使") == INTENT_COMPOSITION

    def test_efficacy_intent(self, engine):
        assert engine.detect_intent("黄芪有什么功效") == INTENT_EFFICACY

    def test_treating_intent(self, engine):
        assert engine.detect_intent("治疗脾虚的方剂") == INTENT_TREATING

    def test_similar_intent(self, engine):
        assert engine.detect_intent("四君子汤的类似方剂") == INTENT_SIMILAR

    def test_path_intent(self, engine):
        assert engine.detect_intent("人参和黄芪之间的关系") == INTENT_PATH

    def test_herb_formulas_intent(self, engine):
        assert engine.detect_intent("哪些方剂含有黄芪") == INTENT_HERB_FORMULAS

    def test_statistics_intent(self, engine):
        assert engine.detect_intent("图谱中有多少个节点") == INTENT_STATISTICS

    def test_unknown_intent(self, engine):
        assert engine.detect_intent("今天天气怎么样") == INTENT_UNKNOWN

    def test_entity_fallback_formula(self, engine):
        """无关键词但有方剂名 → 默认 COMPOSITION。"""
        assert engine.detect_intent("四君子汤") == INTENT_COMPOSITION

    def test_entity_fallback_herb(self, engine):
        """无关键词但有中药名 → 默认 EFFICACY。"""
        assert engine.detect_intent("黄芪") == INTENT_EFFICACY


# ===================================================================
# 模板翻译（translate）
# ===================================================================


class TestTranslate:
    @pytest.fixture()
    def engine(self):
        return KGQueryEngine()

    def test_translate_composition(self, engine):
        cypher, params = engine.translate("四君子汤的组成")
        assert cypher is not None
        assert "formula_name" in params
        assert params["formula_name"] == "四君子汤"
        assert "MATCH" in cypher

    def test_translate_efficacy(self, engine):
        cypher, params = engine.translate("黄芪有什么功效")
        assert cypher is not None
        assert params["herb_name"] == "黄芪"

    def test_translate_treating(self, engine):
        cypher, params = engine.translate("治疗脾虚的方剂")
        assert cypher is not None
        assert params["syndrome_name"] == "脾虚"

    def test_translate_similar(self, engine):
        cypher, params = engine.translate("四君子汤的类似方剂")
        assert cypher is not None
        assert params["formula_name"] == "四君子汤"

    def test_translate_path(self, engine):
        cypher, params = engine.translate("人参和黄芪之间的关系")
        assert cypher is not None
        assert "src" in params
        assert "dst" in params

    def test_translate_herb_formulas(self, engine):
        cypher, params = engine.translate("哪些方剂含有黄芪")
        assert cypher is not None
        assert params["herb_name"] == "黄芪"

    def test_translate_statistics(self, engine):
        cypher, params = engine.translate("图谱统计")
        assert cypher is not None
        assert params == {}

    def test_translate_empty(self, engine):
        cypher, params = engine.translate("")
        assert cypher is None

    def test_translate_unknown_no_entity(self, engine):
        cypher, _ = engine.translate("今天天气如何")
        assert cypher is None


# ===================================================================
# query() — 无驱动（翻译模式）
# ===================================================================


class TestQueryTranslateOnly:
    def test_query_no_driver_returns_cypher(self):
        engine = KGQueryEngine(neo4j_driver=None)
        result = engine.query("四君子汤的组成")
        assert result.success
        assert result.intent == INTENT_COMPOSITION
        assert "MATCH" in result.cypher
        assert "翻译成功" in result.summary

    def test_query_empty_input(self):
        engine = KGQueryEngine()
        result = engine.query("")
        assert not result.success
        assert "空" in result.error

    def test_query_unknown_no_llm(self):
        engine = KGQueryEngine()
        result = engine.query("今天天气怎么样")
        assert not result.success


# ===================================================================
# query() — 有驱动
# ===================================================================


class TestQueryWithDriver:
    @pytest.fixture()
    def mock_driver(self):
        driver = MagicMock()
        driver.database = "neo4j"
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        driver.driver.session.return_value = session

        # execute_read returns list of mock records
        record1 = MagicMock()
        record1.__iter__ = MagicMock(return_value=iter([("herb", "人参"), ("role", "SOVEREIGN")]))
        record1.keys.return_value = ["herb", "role"]
        record1.__getitem__ = lambda self, k: {"herb": "人参", "role": "SOVEREIGN"}[k]

        def fake_execute_read(fn):
            # Give fn a mock tx
            tx = MagicMock()
            mock_result = [{"herb": "人参", "role": "SOVEREIGN"}, {"herb": "白术", "role": "MINISTER"}]
            tx.run.return_value = mock_result
            return fn(tx)

        session.execute_read = fake_execute_read
        return driver

    def test_query_with_driver_success(self, mock_driver):
        engine = KGQueryEngine(neo4j_driver=mock_driver)
        result = engine.query("四君子汤的组成")
        assert result.success
        assert result.intent == INTENT_COMPOSITION
        assert len(result.records) == 2

    def test_query_driver_exception(self):
        driver = MagicMock()
        driver.database = "neo4j"
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        driver.driver.session.return_value = session
        session.execute_read.side_effect = RuntimeError("connection lost")

        engine = KGQueryEngine(neo4j_driver=driver)
        result = engine.query("四君子汤的组成")
        assert not result.success
        assert "connection lost" in result.error


# ===================================================================
# LLM 辅助
# ===================================================================


class TestLLMAssisted:
    def test_llm_generates_cypher(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "MATCH (n:Herb) RETURN n.name LIMIT 5"
        engine = KGQueryEngine(llm_service=mock_llm)
        result = engine.query("列出前5个中药")
        assert result.success
        assert "MATCH" in result.cypher

    def test_llm_returns_code_block(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "```cypher\nMATCH (n:Herb) RETURN n.name\n```"
        engine = KGQueryEngine(llm_service=mock_llm)
        cypher, _ = engine.translate("列出所有中药")
        # Template won't match, fallback to LLM
        assert cypher is not None
        assert cypher == "MATCH (n:Herb) RETURN n.name"

    def test_llm_unsafe_rejected(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "CREATE (n:Herb {name: 'test'})"
        engine = KGQueryEngine(llm_service=mock_llm)
        result = engine.query("创建一个中药节点")
        assert not result.success

    def test_llm_exception_handled(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("LLM down")
        engine = KGQueryEngine(llm_service=mock_llm)
        result = engine.query("列出所有中药")
        assert not result.success

    def test_llm_empty_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = ""
        engine = KGQueryEngine(llm_service=mock_llm)
        result = engine.query("列出所有中药")
        assert not result.success


# ===================================================================
# _extract_cypher_from_llm
# ===================================================================


class TestExtractCypherFromLLM:
    def test_plain_match(self):
        raw = "MATCH (n) RETURN n"
        assert KGQueryEngine._extract_cypher_from_llm(raw) == "MATCH (n) RETURN n"

    def test_code_block(self):
        raw = "这是查询：\n```cypher\nMATCH (n) RETURN n\n```\n说明..."
        assert KGQueryEngine._extract_cypher_from_llm(raw) == "MATCH (n) RETURN n"

    def test_multiline_code_block(self):
        raw = "```\nMATCH (n)\nRETURN n\n```"
        result = KGQueryEngine._extract_cypher_from_llm(raw)
        assert result is not None
        assert "MATCH" in result

    def test_none_input(self):
        assert KGQueryEngine._extract_cypher_from_llm("") is None
        assert KGQueryEngine._extract_cypher_from_llm(None) is None

    def test_no_cypher_content(self):
        assert KGQueryEngine._extract_cypher_from_llm("这只是普通文本") is None


# ===================================================================
# _extract_syndrome
# ===================================================================


class TestExtractSyndrome:
    def test_zhiliao_pattern(self):
        assert KGQueryEngine._extract_syndrome("治疗脾虚的方剂") == "脾虚"

    def test_zhi_pattern(self):
        assert KGQueryEngine._extract_syndrome("治气虚怎么办") == "气虚"

    def test_zhuzhi_pattern(self):
        assert KGQueryEngine._extract_syndrome("主治血瘀的方剂") == "血瘀"

    def test_yongyu_pattern(self):
        assert KGQueryEngine._extract_syndrome("用于肝郁的方子") == "肝郁"

    def test_no_match(self):
        assert KGQueryEngine._extract_syndrome("今天天气好") is None


# ===================================================================
# Summarize
# ===================================================================


class TestSummarize:
    def test_empty_records(self):
        assert "未找到" in KGQueryEngine._summarize(INTENT_COMPOSITION, [])

    def test_composition_summary(self):
        records = [{"herb": "人参", "role": "SOVEREIGN"}, {"herb": "白术", "role": "MINISTER"}]
        s = KGQueryEngine._summarize(INTENT_COMPOSITION, records)
        assert "2 味药材" in s
        assert "人参" in s

    def test_efficacy_summary(self):
        records = [{"efficacy": "补气"}, {"efficacy": "固表"}]
        s = KGQueryEngine._summarize(INTENT_EFFICACY, records)
        assert "补气" in s

    def test_treating_summary(self):
        records = [{"formula": "四君子汤"}]
        s = KGQueryEngine._summarize(INTENT_TREATING, records)
        assert "四君子汤" in s

    def test_statistics_summary(self):
        records = [{"label": "Formula", "count": 100}]
        s = KGQueryEngine._summarize(INTENT_STATISTICS, records)
        assert "Formula" in s
