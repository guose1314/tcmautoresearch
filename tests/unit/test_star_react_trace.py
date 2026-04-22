"""Phase M-1: STaR / ReAct trace 契约测试。"""

from __future__ import annotations

import unittest

from src.research.star_react_trace import (
    STAR_REACT_TRACE_CONTRACT_VERSION,
    ReasoningTrace,
    TraceStep,
    VALID_STEP_KINDS,
    build_reasoning_trace,
    export_traces_for_offline_eval,
)


class TestStarReactTraceContract(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(STAR_REACT_TRACE_CONTRACT_VERSION, "star-react-trace-v1")

    def test_valid_step_kinds(self):
        self.assertEqual(
            VALID_STEP_KINDS,
            frozenset({"thought", "action", "observation", "answer"}),
        )

    def test_thought_step(self):
        step = TraceStep(kind="thought", content="先看《伤寒论》序")
        self.assertEqual(step.kind, "thought")

    def test_action_requires_tool_name(self):
        with self.assertRaises(ValueError):
            TraceStep(kind="action", content="查图谱")

    def test_action_with_tool(self):
        step = TraceStep(
            kind="action",
            content="查询桂枝汤组成",
            tool_name="query_neo4j",
            tool_args={"cypher": "MATCH (f:Formula {name:'桂枝汤'})"},
        )
        self.assertEqual(step.tool_name, "query_neo4j")

    def test_invalid_kind(self):
        with self.assertRaises(ValueError):
            TraceStep(kind="meditation", content="x")

    def test_step_roundtrip(self):
        step = TraceStep(
            kind="action",
            content="x",
            tool_name="query_catalog",
            tool_args={"title": "伤寒论"},
            tool_result={"hits": 3},
            score=0.9,
            metadata={"k": "v"},
        )
        restored = TraceStep.from_dict(step.to_dict())
        self.assertEqual(restored.tool_name, "query_catalog")
        self.assertEqual(restored.tool_args, {"title": "伤寒论"})
        self.assertEqual(restored.metadata, {"k": "v"})

    def test_build_trace_requires_id_and_phase(self):
        with self.assertRaises(ValueError):
            build_reasoning_trace(trace_id="", phase="hypothesis", question="q")
        with self.assertRaises(ValueError):
            build_reasoning_trace(trace_id="t1", phase="", question="q")

    def test_build_trace_default_steps_empty(self):
        trace = build_reasoning_trace(trace_id="t1", phase="hypothesis", question="q")
        self.assertEqual(trace.steps, [])
        self.assertEqual(trace.contract_version, STAR_REACT_TRACE_CONTRACT_VERSION)

    def test_add_step_and_serialize(self):
        trace = build_reasoning_trace(trace_id="t1", phase="hypothesis", question="桂枝汤主治")
        trace.add_step(TraceStep(kind="thought", content="先回忆条文"))
        trace.add_step(
            TraceStep(
                kind="action",
                content="查图谱",
                tool_name="query_neo4j",
                tool_args={"cypher": "MATCH ..."},
            )
        )
        trace.add_step(TraceStep(kind="observation", content="得到 3 条记录"))
        trace.add_step(TraceStep(kind="answer", content="桂枝汤治太阳中风"))
        trace.final_answer = "桂枝汤治太阳中风"
        trace.overall_score = 0.85
        d = trace.to_dict()
        self.assertEqual(len(d["steps"]), 4)
        self.assertEqual(d["overall_score"], 0.85)
        restored = ReasoningTrace.from_dict(d)
        self.assertEqual(len(restored.steps), 4)
        self.assertEqual(restored.final_answer, "桂枝汤治太阳中风")

    def test_export_for_offline_eval(self):
        t1 = build_reasoning_trace(trace_id="t1", phase="hypothesis", question="q1")
        t2 = build_reasoning_trace(trace_id="t2", phase="hypothesis", question="q2")
        payload = export_traces_for_offline_eval([t1, t2])
        self.assertEqual(payload["contract_version"], STAR_REACT_TRACE_CONTRACT_VERSION)
        self.assertEqual(payload["trace_count"], 2)
        self.assertEqual(len(payload["traces"]), 2)


if __name__ == "__main__":
    unittest.main()
