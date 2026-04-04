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
        self.assertTrue(all(item.generation_mode in ("llm", "kg_enhanced") for item in hypotheses))
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


# ---------------------------------------------------------------------------
# P3.2  KG 增强假设生成测试
# ---------------------------------------------------------------------------


class KGEnhancedFakeLLM:
    """返回包含 source_gap_type / source_entities 的 KG 增强格式响应。"""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return """[
  {
    "title": "PI3K-Akt 通路缺少证候关联",
    "statement": "假设 PI3K-Akt 通路与脾气虚证之间存在尚未编码的靶点-证候关联。",
    "rationale": "图谱中 PI3K-Akt 为孤立节点，但文献支持其参与补气机制。",
    "novelty": 0.90,
    "feasibility": 0.80,
    "evidence_support": 0.75,
    "validation_plan": "检索通路靶点数据库与证候文献交叉验证。",
    "keywords": ["PI3K-Akt", "脾气虚证", "靶点"],
    "source_gap_type": "orphan_entity",
    "source_entities": ["PI3K-Akt", "脾气虚证"]
  },
  {
    "title": "补中益气汤组成角色遗漏",
    "statement": "假设补中益气汤的佐使药物尚未被系统标注。",
    "rationale": "图谱显示方剂配伍角色不完整。",
    "novelty": 0.72,
    "feasibility": 0.88,
    "evidence_support": 0.82,
    "validation_plan": "古籍比对验证缺失药物角色。",
    "keywords": ["补中益气汤", "佐使", "配伍"],
    "source_gap_type": "incomplete_composition",
    "source_entities": ["补中益气汤"]
  }
]"""


class TestKGEnhancedHypothesis(unittest.TestCase):
    """P3.2 KG 增强假设生成功能测试。"""

    def setUp(self):
        # 构造一个有明确 gap 的图谱：PI3K-Akt 孤立（无出/入边）
        self.graph = TCMKnowledgeGraph(preload_formulas=False)
        self.graph.add_entity({"name": "补中益气汤", "type": "formula"})
        self.graph.add_entity({"name": "脾气虚证", "type": "syndrome"})
        self.graph.add_entity({"name": "黄芪", "type": "herb"})
        self.graph.add_entity({"name": "补气", "type": "efficacy"})
        self.graph.add_entity({"name": "PI3K-Akt", "type": "pathway"})
        self.graph.add_relation("补中益气汤", "contains", "黄芪")
        self.graph.add_relation("黄芪", "efficacy", "补气")
        self.graph.add_relation("补中益气汤", "treats", "脾气虚证")
        # 注意：PI3K-Akt 没有任何关系 → 孤立实体

        self.context = {
            "research_objective": "围绕补中益气汤展开知识图谱缺口分析",
            "research_scope": "中医方剂机制研究",
            "observations": ["黄芪为主要君药"],
            "findings": ["方剂配伍角色不完整"],
            "entities": [
                {"name": "补中益气汤", "type": "formula"},
                {"name": "黄芪", "type": "herb"},
            ],
        }

    # -- extract_kg_gaps -------------------------------------------------

    def test_extract_kg_gaps_returns_gaps(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)
        gaps = engine.extract_kg_gaps(self.context)
        self.assertIsInstance(gaps, list)
        self.assertGreaterEqual(len(gaps), 1)

    def test_extract_kg_gaps_sorted_by_severity(self):
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)
        gaps = engine.extract_kg_gaps(self.context)
        if len(gaps) >= 2:
            order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(gaps) - 1):
                self.assertLessEqual(
                    order.get(gaps[i].severity, 3),
                    order.get(gaps[i + 1].severity, 3),
                )

    def test_extract_kg_gaps_empty_graph(self):
        empty = TCMKnowledgeGraph(preload_formulas=False)
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=empty)
        engine.initialize()
        self.addCleanup(engine.cleanup)
        gaps = engine.extract_kg_gaps({})
        self.assertEqual(gaps, [])

    # -- _format_kg_gaps --------------------------------------------------

    def test_format_kg_gaps_text(self):
        from src.storage.graph_interface import KnowledgeGap

        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gaps = [
            KnowledgeGap("orphan_entity", "PI3K-Akt", "pathway", "孤立实体", "medium"),
            KnowledgeGap("missing_downstream", "黄芪", "herb", "缺少下游关系", "high"),
        ]
        text = engine._format_kg_gaps(gaps)
        self.assertIn("PI3K-Akt", text)
        self.assertIn("orphan_entity", text)
        self.assertIn("HIGH", text)
        # 格式为编号列表
        self.assertTrue(text.startswith("1."))

    def test_format_kg_gaps_truncates_to_10(self):
        from src.storage.graph_interface import KnowledgeGap

        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gaps = [
            KnowledgeGap("orphan_entity", f"E{i}", "herb", f"desc{i}", "low")
            for i in range(15)
        ]
        text = engine._format_kg_gaps(gaps)
        self.assertIn("10.", text)
        self.assertNotIn("11.", text)

    # -- _build_kg_structure_summary --------------------------------------

    def test_build_kg_structure_summary(self):
        from src.storage.graph_interface import KnowledgeGap

        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gaps = [
            KnowledgeGap("orphan_entity", "补中益气汤", "formula", "测试", "medium"),
        ]
        summary = engine._build_kg_structure_summary(gaps, {"knowledge_graph": self.graph})
        self.assertIsInstance(summary, str)
        self.assertTrue(len(summary) > 0)

    # -- generate_hypotheses: KG 增强路径 ---------------------------------

    def test_kg_enhanced_generation_mode(self):
        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=KGEnhancedFakeLLM(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)
        hypotheses = engine.generate_hypotheses(None, self.context)
        self.assertGreaterEqual(len(hypotheses), 2)
        self.assertTrue(all(h.generation_mode == "kg_enhanced" for h in hypotheses))

    def test_kg_enhanced_preserves_source_gap_type(self):
        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=KGEnhancedFakeLLM(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)
        hypotheses = engine.generate_hypotheses(None, self.context)
        gap_types = {h.source_gap_type for h in hypotheses}
        self.assertTrue(
            gap_types & {"orphan_entity", "incomplete_composition"},
            f"Expected KG gap types but got {gap_types}",
        )

    def test_kg_enhanced_preserves_source_entities(self):
        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=KGEnhancedFakeLLM(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)
        hypotheses = engine.generate_hypotheses(None, self.context)
        all_entities = []
        for h in hypotheses:
            all_entities.extend(h.source_entities)
        self.assertTrue(any("PI3K-Akt" in e for e in all_entities))

    # -- 回退路径 -----------------------------------------------------------

    def test_fallback_to_llm_when_no_kg_gaps(self):
        """KG 无缺口 → 回退到普通 LLM 路径。"""
        full_graph = TCMKnowledgeGraph(preload_formulas=False)
        full_graph.add_entity({"name": "A", "type": "herb"})
        full_graph.add_entity({"name": "B", "type": "efficacy"})
        full_graph.add_relation("A", "efficacy", "B")

        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=FakeLLMEngine(),
            knowledge_graph=full_graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gap = {
            "gap_type": "custom_gap",
            "entity": "A",
            "entity_type": "herb",
            "description": "自定义缺口",
            "entities": ["A", "B"],
            "severity": "medium",
        }
        hypotheses = engine.generate_hypotheses(gap, {"use_llm_generation": True})
        self.assertGreaterEqual(len(hypotheses), 2)
        self.assertTrue(all(h.generation_mode == "llm" for h in hypotheses))

    def test_llm_failure_falls_back_to_rules(self):
        """LLM 调用异常 → 回退到规则引擎。"""

        class FailingLLM:
            def generate(self, prompt: str, system_prompt: str = "") -> str:
                raise RuntimeError("LLM 服务不可用")

        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=FailingLLM(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)

        gap = {
            "gap_type": "orphan_entity",
            "entity": "PI3K-Akt",
            "entity_type": "pathway",
            "description": "孤立实体",
            "entities": ["PI3K-Akt"],
            "severity": "medium",
        }
        hypotheses = engine.generate_hypotheses(gap, self.context)
        self.assertGreaterEqual(len(hypotheses), 1)
        self.assertTrue(all(h.generation_mode == "rule" for h in hypotheses))

    def test_no_llm_skips_kg_enhanced_path(self):
        """无 LLM 引擎时不触发 KG 增强路径。"""
        engine = HypothesisEngine({"max_hypotheses": 5}, knowledge_graph=self.graph)
        engine.initialize()
        self.addCleanup(engine.cleanup)
        context_no_llm = {**self.context, "use_llm_generation": False}
        hypotheses = engine.generate_hypotheses(None, context_no_llm)
        self.assertGreaterEqual(len(hypotheses), 1)
        self.assertTrue(all(h.generation_mode == "rule" for h in hypotheses))

    # -- _do_execute metadata ---------------------------------------------

    def test_execute_metadata_used_kg_enhanced(self):
        engine = HypothesisEngine(
            {"max_hypotheses": 5},
            llm_engine=KGEnhancedFakeLLM(),
            knowledge_graph=self.graph,
        )
        engine.initialize()
        self.addCleanup(engine.cleanup)

        result = engine.execute({"knowledge_gap": None, **self.context})
        self.assertEqual(result["phase"], "hypothesis")
        meta = result["metadata"]
        self.assertIn("used_kg_enhanced", meta)
        self.assertTrue(meta["used_kg_enhanced"])
        self.assertEqual(meta["generation_mode"], "kg_enhanced")
        self.assertTrue(meta["used_llm_generation"])


if __name__ == "__main__":
    unittest.main()