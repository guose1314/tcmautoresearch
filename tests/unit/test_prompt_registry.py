"""Prompt Registry 与 JSON Schema 结构化输出回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.ai_assistant.research_advisor import ResearchAdvisor
from src.infra.layered_cache import LayeredTaskCache
from src.infra.llm_service import LLMService
from src.infra.prompt_registry import (
    PROMPT_REGISTRY,
    call_registered_prompt,
    get_registry_summary,
    parse_registered_output,
    render_prompt,
    reset_prompt_registry_settings_cache,
)
from src.infra.token_budget_policy import reset_token_budget_policy_settings_cache
from src.research.gap_analyzer import GapAnalyzer
from src.research.hypothesis_engine import HypothesisEngine


class _CaptureLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.response


class TestPromptRegistryCatalog(unittest.TestCase):
    def setUp(self):
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_registry_contains_expected_entries(self):
        for name in (
            "research_advisor.hypothesis_suggestion",
            "research_advisor.experiment_design",
            "research_advisor.novelty_evaluation",
            "gap_analyzer.structured_report",
            "hypothesis_engine.default_hypothesis",
            "hypothesis_engine.kg_enhanced",
        ):
            self.assertIn(name, PROMPT_REGISTRY)

    def test_registry_summary_exposes_prompt_counts(self):
        summary = get_registry_summary()
        self.assertGreaterEqual(summary["total_prompts"], 6)
        self.assertIn("json_array", summary["output_kinds"])
        self.assertIn("json_object", summary["output_kinds"])


class TestRenderPrompt(unittest.TestCase):
    def setUp(self):
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_render_prompt_appends_schema_instruction(self):
        rendered = render_prompt(
            "research_advisor.hypothesis_suggestion",
            topic="补中益气汤与脾气虚证",
            literature_section="",
        )
        self.assertIn("JSON Schema", rendered.user_prompt)
        self.assertIn("只输出单个 JSON 数组", rendered.user_prompt)
        self.assertIn('"hypothesis"', rendered.user_prompt)

    def test_render_prompt_supports_template_override(self):
        rendered = render_prompt(
            "hypothesis_engine.default_hypothesis",
            system_prompt_override="自定义系统提示",
            user_template_override="任务：{gap_type}",
            gap_type="custom_gap",
        )
        self.assertEqual(rendered.system_prompt, "自定义系统提示")
        self.assertIn("任务：custom_gap", rendered.user_prompt)
        self.assertIn("JSON Schema", rendered.user_prompt)

    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_render_prompt_applies_budget_and_preserves_schema_suffix(self, mock_load):
        def _side_effect(path, default=None):
            if path == "models.llm.prompt_registry":
                return {
                    "enabled": True,
                    "include_schema_in_prompt": True,
                    "fail_on_schema_validation": False,
                    "max_schema_chars": 4000,
                }
            if path == "models.llm.token_budget_policy":
                return {
                    "enabled": True,
                    "default_input_tokens": 384,
                    "min_input_tokens": 128,
                    "max_context_tokens": 512,
                    "reserve_output_tokens": 64,
                    "trim_notice": "\n\n[..trimmed..]\n\n",
                    "task_input_budgets": {
                        "hypothesis_generation": 320,
                    },
                }
            return default or {}

        mock_load.side_effect = _side_effect
        rendered = render_prompt(
            "research_advisor.hypothesis_suggestion",
            topic="补中益气汤与脾气虚证",
            literature_section="文献摘要：" + ("黄芪补气研究。" * 600),
        )

        self.assertIn("[..trimmed..]", rendered.user_prompt)
        self.assertIn("JSON Schema", rendered.user_prompt)
        self.assertIn('"hypothesis"', rendered.user_prompt)


class TestParseRegisteredOutput(unittest.TestCase):
    def test_parse_registered_output_accepts_fenced_json(self):
        raw = """```json
        [{
          "hypothesis": "黄芪可能通过补气机制改善脾气虚证",
          "confidence": 0.82,
          "rationale": "已有文献与方证线索支持",
          "suggested_methods": ["文献回顾", "网络药理学"]
        }]
        ```"""
        result = parse_registered_output("research_advisor.hypothesis_suggestion", raw)
        self.assertTrue(result.schema_valid)
        self.assertEqual(len(result.parsed), 1)

    def test_parse_registered_output_marks_missing_required_fields(self):
        raw = '{"study_type": "RCT"}'
        result = parse_registered_output("research_advisor.experiment_design", raw)
        self.assertFalse(result.schema_valid)
        self.assertTrue(any("sample_size" in item for item in result.errors))


class TestLLMServiceRegisteredPrompt(unittest.TestCase):
    def setUp(self):
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_generate_registered_uses_registry_rendering(self):
        class EchoService(LLMService):
            def __init__(self):
                self.calls = []

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
                return "ok"

        svc = EchoService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {"enabled": False},
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    result = svc.generate_registered(
                        "research_advisor.novelty_evaluation",
                        hypothesis="补中益气汤可能存在新机制",
                        literature_section="",
                    )
            finally:
                cache.close()

        self.assertEqual(result, "ok")
        self.assertEqual(len(svc.calls), 1)
        self.assertIn("JSON Schema", svc.calls[0]["prompt"])
        self.assertTrue(svc.calls[0]["system_prompt"])

    def test_generate_registered_uses_prompt_cache(self):
        class EchoService(LLMService):
            def __init__(self):
                self.calls = []

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
                return "cached-ok"

        svc = EchoService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {
                        "enabled": True,
                        "namespace": "prompt",
                        "ttl_seconds": None,
                    },
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    first = svc.generate_registered(
                        "research_advisor.experiment_design",
                        hypothesis="黄芪补气可能改善疲劳",
                    )
                    second = svc.generate_registered(
                        "research_advisor.experiment_design",
                        hypothesis="黄芪补气可能改善疲劳",
                    )
            finally:
                cache.close()

        self.assertEqual(first, "cached-ok")
        self.assertEqual(second, "cached-ok")
        self.assertEqual(len(svc.calls), 1)


class TestCallRegisteredPromptCache(unittest.TestCase):
    def setUp(self):
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_call_registered_prompt_reuses_cached_response(self):
        llm = _CaptureLLM(
            '[{"hypothesis":"A","confidence":0.9,"rationale":"B","suggested_methods":["C"]}]'
        )
        rendered = render_prompt(
            "research_advisor.hypothesis_suggestion",
            topic="黄芪补气",
            literature_section="",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {
                        "enabled": True,
                        "namespace": "prompt",
                        "ttl_seconds": None,
                    },
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    first = call_registered_prompt(
                        llm, rendered.name, rendered=rendered
                    )
                    second = call_registered_prompt(
                        llm, rendered.name, rendered=rendered
                    )
            finally:
                cache.close()

        self.assertEqual(first, second)
        self.assertEqual(len(llm.calls), 1)

    def test_call_registered_prompt_uses_gateway_json_repair(self):
        llm = _CaptureLLM(
            "```json\n{'novelty_score': 7, 'novelty_level': '显著', 'overlapping_studies': [], 'unique_aspects': ['方证线索'], 'improvement_suggestions': [],}\n```"
        )
        rendered = render_prompt(
            "research_advisor.novelty_evaluation",
            hypothesis="桂枝汤可能存在方证新线索",
            literature_section="",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {"enabled": False},
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    raw = call_registered_prompt(llm, rendered.name, rendered=rendered)
            finally:
                cache.close()

        parsed = parse_registered_output(rendered.name, raw)
        self.assertTrue(parsed.schema_valid)
        self.assertEqual(parsed.parsed["novelty_score"], 7)
        self.assertEqual(len(llm.calls), 1)


class TestModulePromptIntegration(unittest.TestCase):
    def setUp(self):
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_gap_analyzer_prompt_contains_schema(self):
        analyzer = GapAnalyzer({"max_summaries": 1}, llm_service=None)
        analyzer.initialize()
        self.addCleanup(analyzer.cleanup)

        payload = analyzer.build_prompt_payload(
            clinical_question="中医干预证据缺口是什么？",
            evidence_matrix={},
            literature_summaries=[{"title": "A", "summary_text": "B"}],
            output_language="zh",
        )
        self.assertIn("JSON Schema", payload["user_prompt"])
        self.assertIn('"clinical_question"', payload["user_prompt"])

    def test_hypothesis_engine_prompt_contains_schema(self):
        llm = _CaptureLLM(
            """[
            {
              "title": "黄芪与脾气虚证存在直接作用",
              "statement": "假设黄芪与脾气虚证之间存在直接关联。",
              "rationale": "已有证据提示稳定共现。",
              "novelty": 0.8,
              "feasibility": 0.7,
              "evidence_support": 0.75,
              "validation_plan": "做文献回顾与图谱补边。",
              "keywords": ["黄芪", "脾气虚证"]
            }
            ]"""
        )
        graph = MagicMock()
        graph.find_gaps.return_value = []
        engine = HypothesisEngine(
            {"max_hypotheses": 5}, llm_engine=llm, knowledge_graph=graph
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {"enabled": False},
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    hypotheses = engine.generate_hypotheses(
                        {
                            "gap_type": "missing_direct_relation",
                            "entity": "黄芪",
                            "entity_type": "herb",
                            "description": "存在间接路径但缺少直接关系。",
                            "entities": ["黄芪", "脾气虚证"],
                            "severity": "high",
                        },
                        {},
                    )
            finally:
                cache.close()

        self.assertEqual(len(llm.calls), 1)
        self.assertIn("JSON Schema", llm.calls[0]["prompt"])
        self.assertEqual(hypotheses[0].generation_mode, "llm")

    def test_research_advisor_prompt_contains_schema(self):
        llm = _CaptureLLM(
            """[
            {
              "hypothesis": "补中益气汤可能通过调节免疫炎症改善疲劳",
              "confidence": 0.76,
              "rationale": "古籍功效与现代机制有交叉证据。",
              "suggested_methods": ["综述", "细胞实验"]
            }
            ]"""
        )
        advisor = ResearchAdvisor(llm_engine=llm)
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {"enabled": False},
                    "evidence": {"enabled": False},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch(
                    "src.infra.prompt_registry.get_layered_task_cache",
                    return_value=cache,
                ):
                    result = advisor.suggest_hypothesis("补中益气汤的现代机制")
            finally:
                cache.close()

        self.assertEqual(len(llm.calls), 1)
        self.assertIn("JSON Schema", llm.calls[0]["prompt"])
        self.assertEqual(result[0]["confidence"], 0.76)


if __name__ == "__main__":
    unittest.main()
