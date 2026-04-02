import unittest

from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph
from src.research.hypothesis_engine import Hypothesis, HypothesisEngine


class FakeLLMEngine:
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return """[
  {
    "title": "黄芪与脾气虚证存在直接作用",
    "statement": "假设黄芪与脾气虚证之间存在可验证的直接关联，可补全当前图谱缺边。",
    "rationale": "图谱中存在间接证据且文献多次共现。",
    "novelty": 0.88,
    "feasibility": 0.78,
    "evidence_support": 0.74,
    "validation_plan": "通过文献回顾和知识图谱补边验证。",
    "keywords": ["黄芪", "脾气虚证", "直接关联"]
  },
  {
    "title": "黄芪通过补气机制影响脾气虚证",
    "statement": "假设黄芪通过补气相关中介机制影响脾气虚证。",
    "rationale": "已有功效和证候线索支持中介机制存在。",
    "novelty": 0.82,
    "feasibility": 0.76,
    "evidence_support": 0.72,
    "validation_plan": "补充功效和证候关联证据。",
    "keywords": ["黄芪", "补气", "脾气虚证"]
  }
]"""


class TestHypothesisEngine(unittest.TestCase):
    def setUp(self):
        self.graph = TCMKnowledgeGraph(preload_formulas=False)
        self.graph.add_entity({"name": "补中益气汤", "type": "formula"})
        self.graph.add_entity({"name": "脾气虚证", "type": "syndrome"})
        self.graph.add_entity({"name": "黄芪", "type": "herb"})
        self.graph.add_entity({"name": "补气", "type": "efficacy"})
        self.graph.add_entity({"name": "PI3K-Akt", "type": "pathway"})
        self.graph.add_relation("补中益气汤", "contains", "黄芪")
        self.graph.add_relation("黄芪", "efficacy", "补气")
        self.graph.add_relation("补中益气汤", "treats", "脾气虚证")
        self.graph.add_relation("黄芪", "participates_in", "PI3K-Akt")

        self.context = {
            "research_objective": "围绕补中益气汤和脾气虚证建立新的机制假设",
            "research_scope": "中医方剂与证候关系研究",
            "observations": [
                "补中益气汤与脾气虚证在古籍和综述中多次共同出现",
                "黄芪的补气作用在多个研究摘要中重复出现",
            ],
            "findings": [
                "黄芪与补气功效之间存在稳定关系",
                "方剂层面已观察到治疗脾气虚证的间接证据链",
            ],
            "literature_titles": [
                "补中益气汤治疗脾气虚证的文献证据分析",
                "黄芪补气作用机制研究进展",
            ],
            "entities": [
                {"name": "补中益气汤", "type": "formula"},
                {"name": "黄芪", "type": "herb"},
                {"name": "脾气虚证", "type": "syndrome"},
            ],
        }

    def test_rule_mode_generates_at_least_three_hypotheses_from_gap(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gap = {
            "gap_type": "missing_direct_relation",
            "entity": "黄芪",
            "entity_type": "herb",
            "description": "存在 黄芪 -> 补中益气汤 -> 脾气虚证 的路径，但缺少 黄芪 -> 脾气虚证 的直接关系。",
            "entities": ["黄芪", "脾气虚证"],
            "severity": "high",
        }

        hypotheses = engine.generate_hypotheses(gap, self.context)

        self.assertGreaterEqual(len(hypotheses), 3)
        self.assertTrue(all(item.generation_mode == "rule" for item in hypotheses))
        self.assertTrue(any("直接关系" in item.statement for item in hypotheses))

    def test_rank_hypotheses_orders_by_weighted_score(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        low = Hypothesis(
            hypothesis_id="low",
            title="低分假设",
            statement="低分假设",
            rationale="",
            novelty=0.5,
            feasibility=0.5,
            evidence_support=0.5,
            confidence=0.0,
            source_gap_type="custom",
            source_entities=["A"],
        )
        high = Hypothesis(
            hypothesis_id="high",
            title="高分假设",
            statement="高分假设",
            rationale="",
            novelty=0.9,
            feasibility=0.8,
            evidence_support=0.7,
            confidence=0.0,
            source_gap_type="custom",
            source_entities=["B"],
        )

        ranked = engine.rank_hypotheses([low, high])

        self.assertEqual(ranked[0].hypothesis_id, "high")
        self.assertGreater(ranked[0].confidence, ranked[1].confidence)

    def test_reasoning_summary_increases_mechanism_completeness_score(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        hypothesis = Hypothesis(
            hypothesis_id="mech",
            title="机制链假设",
            statement="补中益气汤可能通过 IL6 相关机制影响 JAK-STAT 通路。",
            rationale="",
            novelty=0.7,
            feasibility=0.7,
            evidence_support=0.7,
            confidence=0.0,
            source_gap_type="missing_direct_relation",
            source_entities=["补中益气汤", "JAK-STAT"],
            keywords=["补中益气汤", "IL6", "JAK-STAT"],
        )

        low_context = {**self.context, "reasoning_summary": {}, "knowledge_patterns": {}, "inference_confidence": 0.0}
        high_context = {
            **self.context,
            "reasoning_summary": {
                "inference_confidence": 0.92,
                "knowledge_patterns": {
                    "common_entities": ["IL6", "JAK-STAT"],
                    "most_shared_efficacies": ["补气"],
                    "entity_groups": {"formula": ["补中益气汤"], "target": ["IL6"]},
                },
            },
            "knowledge_patterns": {
                "common_entities": ["IL6", "JAK-STAT"],
                "most_shared_efficacies": ["补气"],
                "entity_groups": {"formula": ["补中益气汤"], "target": ["IL6"]},
            },
            "inference_confidence": 0.92,
        }

        low_score = engine._enrich_hypotheses([hypothesis], low_context)[0].scores["mechanism_completeness"]
        hypothesis_high = Hypothesis(
            hypothesis_id="mech2",
            title="机制链假设",
            statement="补中益气汤可能通过 IL6 相关机制影响 JAK-STAT 通路。",
            rationale="",
            novelty=0.7,
            feasibility=0.7,
            evidence_support=0.7,
            confidence=0.0,
            source_gap_type="missing_direct_relation",
            source_entities=["补中益气汤", "JAK-STAT"],
            keywords=["补中益气汤", "IL6", "JAK-STAT"],
        )
        high_score = engine._enrich_hypotheses([hypothesis_high], high_context)[0].scores["mechanism_completeness"]

        self.assertGreater(high_score, low_score)
        self.assertGreaterEqual(high_score, 0.7)

    def test_llm_mode_prefers_llm_generation(self):
        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=FakeLLMEngine(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gap = {
            "gap_type": "missing_direct_relation",
            "entity": "黄芪",
            "entity_type": "herb",
            "description": "存在间接路径但缺少直接关系。",
            "entities": ["黄芪", "脾气虚证"],
            "severity": "high",
        }

        hypotheses = engine.generate_hypotheses(gap, self.context)

        self.assertGreaterEqual(len(hypotheses), 2)
        self.assertTrue(all(item.generation_mode == "llm" for item in hypotheses))
        self.assertEqual(hypotheses[0].source_entities, ["黄芪", "脾气虚证"])

    def test_execute_uses_context_gap_and_returns_metadata(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        result = engine.execute(
            {
                **self.context,
                "knowledge_gap": {
                    "gap_type": "missing_direct_relation",
                    "entity": "黄芪",
                    "entity_type": "herb",
                    "description": "存在间接路径但缺少直接关系。",
                    "entities": ["黄芪", "脾气虚证"],
                    "severity": "high",
                },
            }
        )

        self.assertEqual(result["phase"], "hypothesis")
        self.assertGreaterEqual(len(result["hypotheses"]), 3)
        self.assertIn("metadata", result)
        self.assertEqual(result["metadata"]["has_llm"], False)
        self.assertEqual(result["metadata"]["selected_hypothesis_id"], result["hypotheses"][0]["hypothesis_id"])


if __name__ == "__main__":
    unittest.main()