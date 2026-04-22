"""J-1 测试: topic_discovery 子阶段与 TopicProposal contract。"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List

from src.research.topic_discovery import (
    TOPIC_PROPOSAL_CONTRACT_VERSION,
    TOPIC_PROPOSAL_MAX,
    TOPIC_PROPOSAL_MIN,
    TopicDiscoveryService,
    TopicProposal,
    TopicSourceCandidate,
    build_topic_discovery_summary,
    normalize_topic_proposals,
    propose_topics,
)
from src.research.topic_discovery.contract import (
    ANGLE_EXEGESIS,
    ANGLE_TEXTUAL_CRITICISM,
    CANDIDATE_ANGLES,
)


class _StubKG:
    """模拟 TCMKnowledgeGraph.entities_by_type 接口（无 sqlite/neo4j 依赖）。"""

    def __init__(self, mapping: Dict[str, List[str]]) -> None:
        self._mapping = mapping

    def entities_by_type(self, etype: str) -> List[str]:
        return list(self._mapping.get(etype, []))


class TopicProposalContractTests(unittest.TestCase):
    def test_contract_version_constant(self) -> None:
        self.assertEqual(TOPIC_PROPOSAL_CONTRACT_VERSION, "topic-proposal-v1")

    def test_proposal_round_trip(self) -> None:
        original = TopicProposal(
            seed="脾胃湿热证",
            sub_question="拆解",
            angle="方证规律",
            source_candidates=[
                TopicSourceCandidate(
                    source_kind="catalog",
                    source_ref="catalog::abc",
                    title="伤寒论",
                ),
            ],
            falsifiable_hypothesis_hint="若...则...",
            priority=0.83,
            rationale="reason",
        )
        serialized = original.to_dict()
        self.assertEqual(serialized["contract_version"], "topic-proposal-v1")
        self.assertEqual(serialized["source_candidates"][0]["source_kind"], "catalog")
        rebuilt = TopicProposal.from_dict(serialized)
        self.assertEqual(rebuilt.seed, original.seed)
        self.assertEqual(rebuilt.angle, original.angle)
        self.assertAlmostEqual(rebuilt.priority, original.priority, places=4)
        self.assertEqual(len(rebuilt.source_candidates), 1)
        self.assertEqual(rebuilt.source_candidates[0].source_ref, "catalog::abc")

    def test_priority_clamped_in_from_dict(self) -> None:
        rebuilt = TopicProposal.from_dict({"priority": 9.9})
        self.assertEqual(rebuilt.priority, 1.0)
        rebuilt2 = TopicProposal.from_dict({"priority": -3})
        self.assertEqual(rebuilt2.priority, 0.0)
        rebuilt3 = TopicProposal.from_dict({"priority": "abc"})
        self.assertEqual(rebuilt3.priority, 0.0)

    def test_normalize_accepts_dataclass_and_dict(self) -> None:
        proposals = [
            TopicProposal(seed="A", sub_question="q1", angle="方证规律"),
            {"seed": "A", "sub_question": "q2", "angle": "考据辨伪", "priority": 0.5},
        ]
        out = normalize_topic_proposals(proposals)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["sub_question"], "q1")
        self.assertEqual(out[1]["angle"], "考据辨伪")

    def test_summary_reports_contract_compliance(self) -> None:
        proposals = propose_topics("小柴胡汤现代研究综述")
        summary = build_topic_discovery_summary("小柴胡汤现代研究综述", proposals)
        self.assertEqual(summary["seed"], "小柴胡汤现代研究综述")
        self.assertEqual(summary["proposal_count"], len(proposals))
        self.assertTrue(summary["meets_count_contract"])
        self.assertTrue(summary["all_have_evidence"])
        self.assertGreater(summary["avg_priority"], 0.0)


class TopicDiscoveryServiceTests(unittest.TestCase):
    def test_propose_returns_count_within_contract(self) -> None:
        proposals = propose_topics("脾胃湿热证")
        self.assertGreaterEqual(len(proposals), TOPIC_PROPOSAL_MIN)
        self.assertLessEqual(len(proposals), TOPIC_PROPOSAL_MAX)

    def test_propose_yields_unique_angles(self) -> None:
        proposals = propose_topics("湿温病的辨证治法")
        angles = [p.angle for p in proposals]
        self.assertEqual(len(angles), len(set(angles)), "候选课题角度不应重复")
        for angle in angles:
            self.assertIn(angle, CANDIDATE_ANGLES)

    def test_each_proposal_has_evidence_and_hint(self) -> None:
        proposals = propose_topics("温病学派演化")
        for p in proposals:
            self.assertTrue(p.sub_question, "sub_question 必须存在")
            self.assertTrue(p.falsifiable_hypothesis_hint, "假说提示必须存在")
            self.assertGreater(
                len(p.source_candidates), 0, "证据来源至少 1 条"
            )

    def test_priority_sorted_descending(self) -> None:
        proposals = propose_topics("六经辨证临床转化")
        priorities = [p.priority for p in proposals]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_catalog_entries_become_evidence_sources(self) -> None:
        catalog = [
            {"catalog_id": "catalog::shanghan", "work_title": "伤寒论"},
            {"document_id": "catalog::jingui", "document_title": "金匮要略"},
        ]
        proposals = propose_topics("少阳证治", catalog_entries=catalog)
        # 任一非考据/训诂/目录角度均应吸纳 catalog 来源
        non_textual = [p for p in proposals if p.angle not in (
            ANGLE_TEXTUAL_CRITICISM, ANGLE_EXEGESIS,
        )]
        self.assertTrue(non_textual)
        for p in non_textual:
            refs = {s.source_ref for s in p.source_candidates}
            self.assertTrue(
                refs & {"catalog::shanghan", "catalog::jingui"},
                f"角度 {p.angle} 的来源未包含 catalog 条目: {refs}",
            )

    def test_kg_entities_become_evidence_sources(self) -> None:
        kg = _StubKG({
            "formula": ["小柴胡汤", "桂枝汤"],
            "syndrome": ["少阳证"],
            "school": ["伤寒学派"],
        })
        proposals = propose_topics("和解少阳", kg=kg)
        any_kg = False
        for p in proposals:
            for s in p.source_candidates:
                if s.source_kind == "kg":
                    any_kg = True
                    self.assertIn(
                        s.source_ref,
                        {"小柴胡汤", "桂枝汤", "少阳证", "伤寒学派"},
                    )
        self.assertTrue(any_kg, "应至少有一条课题吸纳 KG 来源")

    def test_textual_angle_excludes_kg_sources(self) -> None:
        kg = _StubKG({"formula": ["小柴胡汤"]})
        proposals = propose_topics("仲景版本考据", kg=kg, catalog_entries=[
            {"catalog_id": "catalog::sk", "work_title": "宋本伤寒论"},
        ])
        textual = [p for p in proposals if p.angle == ANGLE_TEXTUAL_CRITICISM]
        self.assertTrue(textual)
        for p in textual:
            kinds = {s.source_kind for s in p.source_candidates}
            self.assertNotIn("kg", kinds, "考据角度的来源不应混入 KG 节点")

    def test_empty_seed_raises(self) -> None:
        with self.assertRaises(ValueError):
            propose_topics("")
        with self.assertRaises(ValueError):
            propose_topics("   ")

    def test_llm_caller_refines_hint(self) -> None:
        captured: list[str] = []

        def fake_llm(prompt: str) -> str:
            captured.append(prompt)
            return "若仲景方证规律可归纳，则其在不同朝代保持稳定。"

        proposals = propose_topics("仲景方证", llm_caller=fake_llm)
        self.assertTrue(captured, "LLM caller 必须被调用")
        for p in proposals:
            self.assertEqual(
                p.falsifiable_hypothesis_hint,
                "若仲景方证规律可归纳，则其在不同朝代保持稳定。",
            )

    def test_llm_caller_failure_falls_back(self) -> None:
        def broken_llm(_prompt: str) -> str:
            raise RuntimeError("oom")

        proposals = propose_topics("脾虚湿盛", llm_caller=broken_llm)
        for p in proposals:
            self.assertTrue(p.falsifiable_hypothesis_hint)
            self.assertIn("脾虚湿盛", p.falsifiable_hypothesis_hint)

    def test_service_proposals_serializable_as_json(self) -> None:
        proposals = propose_topics("阴阳五行的临床应用")
        payload = [p.to_dict() for p in proposals]
        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("topic-proposal-v1", text)


if __name__ == "__main__":
    unittest.main()
