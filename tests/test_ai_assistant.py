# -*- coding: utf-8 -*-
"""
tests/test_ai_assistant.py
测试 AssistantEngine.chat()（使用 Mock LLM 引擎）。
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from src.ai_assistant.assistant_engine import (
    INTENT_EXPERIMENT,
    INTENT_GENERAL,
    INTENT_HYPOTHESIS,
    INTENT_LITERATURE,
    INTENT_WRITING,
    AssistantEngine,
)


@pytest.fixture
def mock_llm():
    """Mock LLM 引擎，generate() 返回固定文本。"""
    llm = MagicMock()
    llm.generate.return_value = "这是 Mock LLM 的回复。参考文献 [1] [2]。"
    return llm


@pytest.fixture
def engine(mock_llm):
    return AssistantEngine(llm_engine=mock_llm)


# ===================================================================
# 意图识别
# ===================================================================

class TestIntentDetection:
    def test_literature_intent(self, engine):
        assert engine._detect_intent("帮我检索黄芪的相关文献") == INTENT_LITERATURE

    def test_hypothesis_intent(self, engine):
        assert engine._detect_intent("补气的机制可能是什么") == INTENT_HYPOTHESIS

    def test_experiment_intent(self, engine):
        assert engine._detect_intent("设计一个随机对照实验方案") == INTENT_EXPERIMENT

    def test_writing_intent(self, engine):
        assert engine._detect_intent("帮我撰写论文摘要") == INTENT_WRITING

    def test_general_intent(self, engine):
        assert engine._detect_intent("你好，今天天气怎么样") == INTENT_GENERAL

    def test_mixed_keywords_highest_wins(self, engine):
        # 包含更多文献关键词
        intent = engine._detect_intent("检索文献论文，找到相关参考引用文章")
        assert intent == INTENT_LITERATURE

    def test_case_insensitive_english(self, engine):
        intent = engine._detect_intent("search PubMed articles")
        assert intent == INTENT_LITERATURE


# ===================================================================
# chat() 主方法
# ===================================================================

class TestChat:
    def test_chat_returns_expected_keys(self, engine):
        result = engine.chat("黄芪的文献有哪些？")
        assert "reply" in result
        assert "suggestions" in result
        assert "references" in result
        assert "intent" in result
        assert "session_id" in result

    def test_chat_reply_from_mock_llm(self, engine, mock_llm):
        result = engine.chat("测试问题")
        assert result["reply"] == mock_llm.generate.return_value
        mock_llm.generate.assert_called_once()

    def test_chat_detects_intent(self, engine):
        result = engine.chat("帮我检索黄芪文献")
        assert result["intent"] == INTENT_LITERATURE

    def test_chat_with_session_id(self, engine):
        result = engine.chat("你好", session_id="sess_42")
        assert result["session_id"] == "sess_42"

    def test_chat_with_context(self, engine):
        ctx = {"project_name": "补气药研究", "entities": ["黄芪", "人参"]}
        result = engine.chat("分析这些药物", context=ctx)
        assert isinstance(result["reply"], str)

    def test_suggestions_is_list(self, engine):
        result = engine.chat("设计实验")
        assert isinstance(result["suggestions"], list)
        assert len(result["suggestions"]) > 0

    def test_references_extraction(self, engine):
        result = engine.chat("问题")
        # Mock LLM 回复包含 [1] [2]，应被提取
        assert isinstance(result["references"], list)


# ===================================================================
# 对话历史管理
# ===================================================================

class TestHistoryManagement:
    def test_history_initially_empty(self, engine):
        assert engine.get_history("new_session") == []

    def test_history_grows_after_chat(self, engine):
        engine.chat("第一轮", session_id="s1")
        history = engine.get_history("s1")
        assert len(history) == 2  # user + assistant
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_history_multiple_turns(self, engine):
        engine.chat("Q1", session_id="s2")
        engine.chat("Q2", session_id="s2")
        history = engine.get_history("s2")
        assert len(history) == 4  # 2 turns × 2 messages

    def test_clear_history(self, engine):
        engine.chat("test", session_id="s3")
        assert len(engine.get_history("s3")) > 0
        engine.clear_history("s3")
        assert engine.get_history("s3") == []

    def test_sessions_are_independent(self, engine):
        engine.chat("A", session_id="sa")
        engine.chat("B", session_id="sb")
        assert len(engine.get_history("sa")) == 2
        assert len(engine.get_history("sb")) == 2
        engine.clear_history("sa")
        assert engine.get_history("sa") == []
        assert len(engine.get_history("sb")) == 2

    def test_history_truncation(self):
        """超过 max_history_turns 时旧历史被截断。"""
        llm = MagicMock()
        llm.generate.return_value = "reply"
        eng = AssistantEngine(llm_engine=llm, max_history_turns=2)
        for i in range(5):
            eng.chat(f"msg_{i}", session_id="trunc")
        history = eng.get_history("trunc")
        # max_turns=2 → 最多 4 条消息
        assert len(history) <= 4


# ===================================================================
# 无 LLM 引擎时的降级行为
# ===================================================================

class TestNoLLMFallback:
    def test_chat_without_llm(self):
        """LLM 为 None 且惰性加载失败时，应返回占位回复。"""
        eng = AssistantEngine(llm_engine=None)
        # 阻止惰性加载
        eng._get_llm = MagicMock(return_value=None)
        result = eng.chat("问题")
        assert "AI 助手" in result["reply"]
        assert result["intent"] is not None

    def test_llm_exception_returns_error_reply(self, mock_llm):
        """LLM 抛异常时，应返回错误提示而非崩溃。"""
        mock_llm.generate.side_effect = RuntimeError("GPU OOM")
        eng = AssistantEngine(llm_engine=mock_llm)
        result = eng.chat("问题")
        assert "错误" in result["reply"] or "Error" in result["reply"]

    def test_failed_lazy_load_does_not_cache_unloaded_engine(self, monkeypatch):
        """惰性加载失败后，不应缓存未初始化引擎对象。"""

        class _BrokenLLMEngine:
            def load(self):
                raise RuntimeError("load failed")

            def generate(self, prompt, system_prompt=""):
                raise RuntimeError("should not be called")

        fake_module = types.ModuleType("src.llm.llm_engine")
        fake_module.LLMEngine = _BrokenLLMEngine
        monkeypatch.setitem(sys.modules, "src.llm.llm_engine", fake_module)

        eng = AssistantEngine(llm_engine=None)
        first = eng._get_llm()
        assert first is None
        assert eng._llm is None

        result = eng.chat("问题")
        assert "尚未加载" in result["reply"]
