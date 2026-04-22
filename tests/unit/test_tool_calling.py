"""Phase M-2: Tool calling registry 测试。"""

from __future__ import annotations

import unittest

from src.research.tool_calling import (
    TOOL_CALLING_CONTRACT_VERSION,
    ToolCall,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    build_default_tool_registry,
    render_tool_catalog_for_prompt,
)


class TestToolCallingContract(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(TOOL_CALLING_CONTRACT_VERSION, "tool-calling-v1")

    def test_default_registry_specs(self):
        reg = build_default_tool_registry()
        names = {s.name for s in reg.list_specs()}
        self.assertEqual(
            names, {"query_neo4j", "query_catalog", "query_exegesis"}
        )
        self.assertEqual(reg.contract_version, TOOL_CALLING_CONTRACT_VERSION)

    def test_register_duplicate_raises(self):
        reg = ToolRegistry()
        spec = ToolSpec(name="x", description="d")
        reg.register(spec)
        with self.assertRaises(ValueError):
            reg.register(spec)

    def test_invoke_unknown_tool(self):
        reg = ToolRegistry()
        result = reg.invoke(ToolCall(tool_name="nope"))
        self.assertFalse(result.ok)
        self.assertIn("unknown", result.error)

    def test_invoke_unbound_handler(self):
        reg = build_default_tool_registry()
        result = reg.invoke(ToolCall(tool_name="query_neo4j", arguments={"cypher": "x"}))
        self.assertFalse(result.ok)
        self.assertIn("not bound", result.error)

    def test_bind_handler_unknown(self):
        reg = ToolRegistry()
        with self.assertRaises(KeyError):
            reg.bind_handler("missing", lambda args: None)

    def test_invoke_success(self):
        reg = build_default_tool_registry()
        reg.bind_handler("query_catalog", lambda args: [{"title": args.get("title")}])
        result = reg.invoke(
            ToolCall(tool_name="query_catalog", arguments={"title": "伤寒论"}, call_id="c1")
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.output, [{"title": "伤寒论"}])
        self.assertEqual(result.call_id, "c1")

    def test_invoke_handler_exception_caught(self):
        reg = ToolRegistry()
        reg.register(ToolSpec(name="boom", description="x"))

        def bad(_):
            raise RuntimeError("kaboom")

        reg.bind_handler("boom", bad)
        result = reg.invoke(ToolCall(tool_name="boom"))
        self.assertFalse(result.ok)
        self.assertIn("kaboom", result.error)
        self.assertIn("RuntimeError", result.error)

    def test_tool_spec_to_dict(self):
        spec = ToolSpec(name="x", description="d", parameters_schema={"type": "object"})
        d = spec.to_dict()
        self.assertEqual(d["name"], "x")
        self.assertEqual(d["parameters_schema"], {"type": "object"})

    def test_tool_call_to_dict(self):
        call = ToolCall(tool_name="x", arguments={"a": 1}, call_id="c")
        self.assertEqual(call.to_dict(), {"tool_name": "x", "arguments": {"a": 1}, "call_id": "c"})

    def test_tool_result_to_dict(self):
        r = ToolResult(tool_name="x", ok=True, output=42, call_id="c")
        self.assertEqual(r.to_dict()["output"], 42)

    def test_render_catalog(self):
        reg = build_default_tool_registry()
        text = render_tool_catalog_for_prompt(reg)
        self.assertIn("query_neo4j", text)
        self.assertIn("query_catalog", text)
        self.assertIn("query_exegesis", text)
        self.assertTrue(text.startswith("## Available Tools"))

    def test_has(self):
        reg = build_default_tool_registry()
        self.assertTrue(reg.has("query_neo4j"))
        self.assertFalse(reg.has("nope"))


if __name__ == "__main__":
    unittest.main()
