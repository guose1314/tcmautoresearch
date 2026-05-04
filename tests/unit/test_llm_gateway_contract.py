from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.contexts.llm_reasoning import (
    LLMGateway,
    LLMGatewayRequest,
    LLMGatewayResult,
    LLMReasoningMode,
    LLMRetrievalPolicy,
)
from src.infra.prompt_registry import reset_prompt_registry_settings_cache
from src.infra.token_budget_policy import reset_token_budget_policy_settings_cache
from src.llm.llm_gateway import LLMGateway as CanonicalLLMGateway
from src.llm.llm_gateway import generate_with_gateway


class _SchemaFakeService:
    n_ctx = 4096
    max_tokens = 128

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        return self.response


class LLMGatewayContractTest(unittest.TestCase):
    def test_request_minimal_defaults_are_json_serializable(self) -> None:
        request = LLMGatewayRequest(prompt="Summarize the evidence.")

        payload = request.to_dict()

        self.assertEqual(payload["phase"], "unknown")
        self.assertEqual(payload["purpose"], "default")
        self.assertEqual(payload["task_type"], "general")
        self.assertEqual(payload["schema_name"], "")
        self.assertEqual(payload["reasoning_mode"], "direct")
        self.assertIsNone(payload["max_input_tokens"])
        self.assertEqual(payload["prompt_version"], "unknown")
        self.assertIsNone(payload["token_budget"])
        self.assertEqual(payload["json_output"], False)
        self.assertFalse(payload["graph_rag"]["enabled"])
        json.dumps(payload, ensure_ascii=False)

    def test_canonical_llm_module_exports_gateway(self) -> None:
        self.assertIs(CanonicalLLMGateway, LLMGateway)

    def test_generate_with_gateway_facade_records_telemetry(self) -> None:
        service = _SchemaFakeService('{"ok": true}')

        result = generate_with_gateway(
            service,
            "输出 JSON。",
            prompt_version="facade.prompt@v1",
            phase="analysis",
            purpose="facade_test",
            task_type="contract_test",
            token_budget=123,
            json_output=True,
        )

        payload = result.to_dict()
        self.assertEqual(payload["prompt_version"], "facade.prompt@v1")
        self.assertEqual(payload["token_budget"], 123)
        self.assertEqual(payload["json_repair_status"], "valid_json")
        self.assertIn("model_id", payload)
        self.assertIn("latency_s", payload)
        self.assertEqual(payload["structured"], {"ok": True})

    def test_request_accepts_graph_rag_policy_mapping(self) -> None:
        request = LLMGatewayRequest(
            prompt="Build a grounded answer.",
            phase="Analyze",
            purpose="paper_plugin",
            task_type="citation_synthesis",
            schema_name="citation_grounding_v1",
            graph_rag={
                "enabled": True,
                "question_type": "LOCAL",
                "query": "siwutang",
                "entity_ids": ["ev-1"],
                "asset_type": "Evidence",
                "cycle_id": "cycle-1",
            },
            reasoning_mode="graph_rag",
            max_input_tokens="1024",
        )

        payload = request.to_dict()

        self.assertEqual(request.reasoning_mode, LLMReasoningMode.GRAPH_RAG)
        self.assertEqual(payload["phase"], "analyze")
        self.assertEqual(payload["purpose"], "paper_plugin")
        self.assertEqual(payload["task_type"], "citation_synthesis")
        self.assertEqual(payload["schema_name"], "citation_grounding_v1")
        self.assertEqual(payload["max_input_tokens"], 1024)
        self.assertTrue(payload["graph_rag"]["enabled"])
        self.assertEqual(payload["graph_rag"]["question_type"], "local")
        self.assertEqual(payload["graph_rag"]["asset_type"], "evidence")
        json.dumps(payload, ensure_ascii=False)

    def test_result_contains_required_fields_and_is_json_serializable(self) -> None:
        result = LLMGatewayResult(
            text="grounded answer",
            structured={"claim": "ok"},
            citations=[{"id": "citation-1"}],
            retrieval_trace={"node_ids": ["n1"]},
            llm_cost_report={"estimated_tokens": 12},
            warnings=["schema_not_applied"],
            reasoning_mode=LLMReasoningMode.SCHEMA_VALIDATED,
            schema_name="claim_schema",
        )

        payload = result.to_dict()

        for key in (
            "text",
            "structured",
            "citations",
            "retrieval_trace",
            "llm_cost_report",
            "warnings",
            "prompt_version",
            "model_id",
            "latency_s",
            "token_budget",
            "json_repair_status",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["text"], "grounded answer")
        self.assertEqual(payload["structured"], {"claim": "ok"})
        self.assertEqual(payload["reasoning_mode"], "schema_validated")
        json.dumps(payload, ensure_ascii=False)

    def test_retrieval_policy_bool_shorthand(self) -> None:
        request = LLMGatewayRequest(prompt="x", graph_rag=True)

        self.assertIsInstance(request.graph_rag, LLMRetrievalPolicy)
        self.assertTrue(request.graph_rag.enabled)
        json.dumps(request.to_dict(), ensure_ascii=False)

    def test_gateway_missing_service_returns_degraded_result(self) -> None:
        result = LLMGateway().generate(LLMGatewayRequest(prompt="x"))

        payload = result.to_dict()
        self.assertEqual(payload["text"], "")
        self.assertIn("llm_service_missing", payload["warnings"])
        self.assertEqual(payload["metadata"]["purpose"], "default")
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_uses_injected_service(self) -> None:
        class _FakeService:
            def __init__(self) -> None:
                self.calls = []
                self.n_ctx = 512
                self.max_tokens = 64

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls.append((prompt, system_prompt))
                return "fake response"

            def get_cost_report(self):
                return {"calls": 1}

        service = _FakeService()
        request = LLMGatewayRequest(
            prompt="hello",
            system_prompt="system",
            graph_rag={"enabled": True, "query": "hello"},
        )

        result = LLMGateway(service).generate(request)

        self.assertEqual(service.calls, [("hello", "system")])
        payload = result.to_dict()
        self.assertEqual(payload["text"], "fake response")
        self.assertEqual(payload["llm_cost_report"]["service"], {"calls": 1})
        self.assertEqual(payload["metadata"]["planned_call"]["phase"], "unknown")
        self.assertIn("prompt_version", payload)
        self.assertIn("model_id", payload)
        self.assertIn("latency_s", payload)
        self.assertIn("token_budget", payload)
        self.assertIn("json_repair_status", payload)
        self.assertTrue(payload["retrieval_trace"]["graph_rag"]["enabled"])
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_records_production_observability_fields(self) -> None:
        class _LocalGGUFService:
            def __init__(self) -> None:
                self.calls = []
                self.model_path = "models/local-qwen.gguf"
                self.n_gpu_layers = 28
                self.n_ctx = 4096
                self.max_tokens = 256
                self.temperature = 0.2

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls.append((prompt, system_prompt))
                return '{"ok": true}'

        service = _LocalGGUFService()
        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt="输出 JSON。",
                prompt_version="analysis.distill@v1",
                phase="analysis",
                task_type="distill",
                token_budget=2048,
                json_output=True,
            )
        )

        payload = result.to_dict()
        self.assertEqual(payload["prompt_version"], "analysis.distill@v1")
        self.assertEqual(payload["model_id"], "models/local-qwen.gguf")
        self.assertGreaterEqual(payload["latency_s"], 0.0)
        self.assertEqual(payload["token_budget"], 2048)
        self.assertEqual(payload["json_repair_status"], "valid_json")
        self.assertEqual(payload["structured"], {"ok": True})
        self.assertEqual(payload["metadata"]["gpu_params"]["n_gpu_layers"], 28)
        self.assertEqual(payload["metadata"]["gpu_params"]["n_ctx"], 4096)
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_repairs_json_when_requested(self) -> None:
        service = _SchemaFakeService("```json\n{'answer': '可采纳',}\n```")

        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt="输出 JSON。",
                prompt_version="test.prompt@v1",
                json_output=True,
            )
        )

        payload = result.to_dict()
        self.assertEqual(payload["json_repair_status"], "repaired")
        self.assertEqual(payload["structured"], {"answer": "可采纳"})
        self.assertTrue(
            any("json_repair_applied" in item for item in payload["warnings"])
        )
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_retries_failed_generation_once(self) -> None:
        class _FlakyService:
            n_ctx = 512
            max_tokens = 64

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary outage")
                return "retry ok"

        service = _FlakyService()
        result = LLMGateway(service).generate(
            LLMGatewayRequest(prompt="x", retry_count=1)
        )

        payload = result.to_dict()
        self.assertEqual(service.calls, 2)
        self.assertEqual(payload["text"], "retry ok")
        self.assertEqual(payload["metadata"]["attempts_used"], 2)
        self.assertTrue(
            any("llm_generate_retry" in item for item in payload["warnings"])
        )

    def test_gateway_applies_planner_token_budget_before_service_call(self) -> None:
        class _FakeService:
            def __init__(self) -> None:
                self.calls = []
                self.n_ctx = 4096
                self.max_tokens = 128

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                self.calls.append((prompt, system_prompt))
                return "budgeted response"

            def cache_stats(self):
                return {"session_hits": 0, "session_misses": 1}

        raw_prompt = "证据片段：" + ("黄芪补气改善疲劳。" * 500)
        service = _FakeService()

        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt=raw_prompt,
                phase="hypothesis",
                purpose="hypothesis",
                task_type="hypothesis_generation",
                max_input_tokens=160,
                context={
                    "dossier_sections": {
                        "objective": "黄芪补气研究",
                        "evidence": "本草与现代观察均提示补气相关证据",
                    }
                },
            )
        )

        self.assertEqual(result.text, "budgeted response")
        self.assertEqual(len(service.calls), 1)
        budgeted_prompt, _system_prompt = service.calls[0]
        self.assertLess(len(budgeted_prompt), len(raw_prompt))
        self.assertIn("截断上下文", budgeted_prompt)

        payload = result.to_dict()
        planned = payload["metadata"]["planned_call"]
        self.assertEqual(planned["phase"], "hypothesis")
        self.assertEqual(planned["task_type"], "hypothesis_generation")
        self.assertEqual(planned["max_input_tokens"], 160)
        self.assertTrue(planned["prompt_application"]["trimmed"])
        self.assertEqual(
            payload["llm_cost_report"]["cache"],
            {"session_hits": 0, "session_misses": 1},
        )
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_generate_exception_returns_degraded_result(self) -> None:
        class _FailingService:
            n_ctx = 512
            max_tokens = 64

            def generate(self, prompt: str, system_prompt: str = "") -> str:
                raise RuntimeError("local model unavailable")

        result = LLMGateway(_FailingService()).generate(
            LLMGatewayRequest(prompt="x", phase="analyze", task_type="graph_reasoning")
        )

        payload = result.to_dict()
        self.assertEqual(payload["text"], "")
        self.assertEqual(payload["structured"], {})
        self.assertTrue(payload["warnings"])
        self.assertIn("llm_generate_failed", payload["warnings"][0])
        self.assertEqual(payload["metadata"]["planned_call"]["phase"], "analyze")
        json.dumps(payload, ensure_ascii=False)


class LLMGatewaySchemaValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def tearDown(self) -> None:
        reset_prompt_registry_settings_cache()
        reset_token_budget_policy_settings_cache()

    def test_gateway_schema_valid_json_populates_structured_result(self) -> None:
        service = _SchemaFakeService('{"answer": "可采纳", "confidence": 0.82}')

        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt="判断该文献结论是否可采纳。",
                schema_name="answer_schema",
                context={"schemas": {"answer_schema": self._answer_schema()}},
            )
        )

        self.assertEqual(result.structured, {"answer": "可采纳", "confidence": 0.82})
        self.assertFalse(result.warnings)
        self.assertEqual(len(service.calls), 1)
        self.assertIn("JSON Schema", service.calls[0][0])
        self.assertIn('"answer"', service.calls[0][0])
        payload = result.to_dict()
        self.assertTrue(payload["metadata"]["schema_validation"]["schema_valid"])
        self.assertEqual(
            payload["metadata"]["schema_validation"]["schema_source"],
            "request.context",
        )
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_schema_invalid_json_returns_text_and_warning(self) -> None:
        service = _SchemaFakeService("这不是 JSON，但主链不能中断。")

        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt="输出结构化结论。",
                schema_name="answer_schema",
                context={"schemas": {"answer_schema": self._answer_schema()}},
            )
        )

        payload = result.to_dict()
        self.assertEqual(payload["text"], "这不是 JSON，但主链不能中断。")
        self.assertEqual(payload["structured"], {})
        self.assertTrue(
            any("schema_invalid_json" in item for item in payload["warnings"])
        )
        self.assertFalse(payload["metadata"]["schema_validation"]["schema_valid"])
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_schema_missing_returns_text_and_warning(self) -> None:
        service = _SchemaFakeService('{"answer": "ok", "confidence": 0.7}')

        result = LLMGateway(service).generate(
            LLMGatewayRequest(
                prompt="输出结构化结论。",
                schema_name="missing_schema",
            )
        )

        payload = result.to_dict()
        self.assertEqual(payload["text"], '{"answer": "ok", "confidence": 0.7}')
        self.assertEqual(payload["structured"], {})
        self.assertIn("schema_missing:missing_schema", payload["warnings"])
        self.assertFalse(payload["metadata"]["schema_validation"]["schema_found"])
        self.assertFalse(
            payload["metadata"]["schema_validation"]["prompt_schema_included"]
        )
        self.assertNotIn("JSON Schema", service.calls[0][0])
        json.dumps(payload, ensure_ascii=False)

    def test_gateway_schema_validation_failure_fail_open_degrades(self) -> None:
        def _load_settings(path, default=None):
            if path == "models.llm.prompt_registry":
                return {
                    "enabled": True,
                    "include_schema_in_prompt": True,
                    "fail_on_schema_validation": False,
                    "max_schema_chars": 4000,
                }
            return default or {}

        service = _SchemaFakeService('{"answer": "可采纳"}')
        schema = self._answer_schema(required=("answer", "confidence"))

        with patch(
            "src.infrastructure.config_loader.load_settings_section",
            side_effect=_load_settings,
        ):
            reset_prompt_registry_settings_cache()
            result = LLMGateway(service).generate(
                LLMGatewayRequest(
                    prompt="输出结构化结论。",
                    schema_name="answer_schema",
                    context={"schemas": {"answer_schema": schema}},
                )
            )

        payload = result.to_dict()
        self.assertEqual(payload["text"], '{"answer": "可采纳"}')
        self.assertEqual(payload["structured"], {})
        self.assertTrue(
            any("schema_validation_failed" in item for item in payload["warnings"])
        )
        self.assertFalse(
            payload["metadata"]["schema_validation"]["fail_on_schema_validation"]
        )
        self.assertFalse(payload["metadata"]["schema_validation"]["schema_valid"])
        json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _answer_schema(required=("answer",)) -> dict:
        return {
            "type": "object",
            "required": list(required),
            "properties": {
                "answer": {"type": "string", "minLength": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        }


if __name__ == "__main__":
    unittest.main()
