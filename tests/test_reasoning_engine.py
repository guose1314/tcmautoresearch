"""
tests/test_reasoning_engine.py
ReasoningEngine 单元测试 — 覆盖真实 KG 路径推理的各个模块
"""
import unittest

from src.reasoning.reasoning_engine import _ROLE_WEIGHTS, ReasoningEngine

# ---------------------------------------------------------------------------
# 测试用 KG 数据（模拟 SemanticGraphBuilder 输出）
# ---------------------------------------------------------------------------

# 方剂: 四君子汤
# 君药: 人参、党参  臣药: 白术  佐药: 茯苓  使药: 甘草
# 药物功效: 人参→补气, 白术→健脾
# 方证: 四君子汤→治疗→脾气虚证

_SAMPLE_ENTITIES = [
    {"name": "四君子汤", "type": "formula",   "confidence": 0.95},
    {"name": "补中益气汤", "type": "formula",  "confidence": 0.90},
    {"name": "人参",    "type": "herb",      "confidence": 0.90},
    {"name": "党参",    "type": "herb",      "confidence": 0.85},
    {"name": "白术",    "type": "herb",      "confidence": 0.88},
    {"name": "茯苓",    "type": "herb",      "confidence": 0.87},
    {"name": "甘草",    "type": "herb",      "confidence": 0.92},
    {"name": "黄芪",    "type": "herb",      "confidence": 0.91},
    {"name": "补气",    "type": "efficacy",  "confidence": 0.80},
    {"name": "健脾",    "type": "efficacy",  "confidence": 0.78},
    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.70},
]

_SAMPLE_GRAPH = {
    "nodes": [
        {"id": "formula:四君子汤",  "data": {"type": "formula",  "name": "四君子汤",  "confidence": 0.95}},
        {"id": "formula:补中益气汤","data": {"type": "formula",  "name": "补中益气汤","confidence": 0.90}},
        {"id": "herb:人参",         "data": {"type": "herb",     "name": "人参",      "confidence": 0.90}},
        {"id": "herb:党参",         "data": {"type": "herb",     "name": "党参",      "confidence": 0.85}},
        {"id": "herb:白术",         "data": {"type": "herb",     "name": "白术",      "confidence": 0.88}},
        {"id": "herb:茯苓",         "data": {"type": "herb",     "name": "茯苓",      "confidence": 0.87}},
        {"id": "herb:甘草",         "data": {"type": "herb",     "name": "甘草",      "confidence": 0.92}},
        {"id": "herb:黄芪",         "data": {"type": "herb",     "name": "黄芪",      "confidence": 0.91}},
        {"id": "efficacy:补气",     "data": {"type": "efficacy", "name": "补气",      "confidence": 0.80}},
        {"id": "efficacy:健脾",     "data": {"type": "efficacy", "name": "健脾",      "confidence": 0.78}},
        {"id": "syndrome:脾气虚证", "data": {"type": "syndrome", "name": "脾气虚证",  "confidence": 0.70}},
    ],
    "edges": [
        # 四君子汤 君臣佐使
        {"source": "formula:四君子汤",  "target": "herb:人参",     "attributes": {"relationship_type": "sovereign", "confidence": 0.95}},
        {"source": "formula:四君子汤",  "target": "herb:党参",     "attributes": {"relationship_type": "sovereign", "confidence": 0.92}},
        {"source": "formula:四君子汤",  "target": "herb:白术",     "attributes": {"relationship_type": "minister",  "confidence": 0.93}},
        {"source": "formula:四君子汤",  "target": "herb:茯苓",     "attributes": {"relationship_type": "assistant", "confidence": 0.91}},
        {"source": "formula:四君子汤",  "target": "herb:甘草",     "attributes": {"relationship_type": "envoy",     "confidence": 0.90}},
        # 补中益气汤 君臣
        {"source": "formula:补中益气汤","target": "herb:黄芪",     "attributes": {"relationship_type": "sovereign", "confidence": 0.95}},
        {"source": "formula:补中益气汤","target": "herb:人参",     "attributes": {"relationship_type": "minister",  "confidence": 0.90}},
        {"source": "formula:补中益气汤","target": "herb:白术",     "attributes": {"relationship_type": "assistant", "confidence": 0.88}},
        {"source": "formula:补中益气汤","target": "herb:甘草",     "attributes": {"relationship_type": "envoy",     "confidence": 0.88}},
        # 药物 → 功效
        {"source": "herb:人参",  "target": "efficacy:补气",  "attributes": {"relationship_type": "efficacy", "confidence": 0.90}},
        {"source": "herb:白术",  "target": "efficacy:健脾",  "attributes": {"relationship_type": "efficacy", "confidence": 0.88}},
        {"source": "herb:党参",  "target": "efficacy:补气",  "attributes": {"relationship_type": "efficacy", "confidence": 0.85}},
        # 方剂 → 证候
        {"source": "formula:四君子汤",  "target": "syndrome:脾气虚证", "attributes": {"relationship_type": "treats", "confidence": 0.85}},
        {"source": "formula:补中益气汤","target": "syndrome:脾气虚证", "attributes": {"relationship_type": "treats", "confidence": 0.80}},
    ],
}

_EMPTY_GRAPH = {"nodes": [], "edges": []}


def _make_engine(**kw) -> ReasoningEngine:
    return ReasoningEngine(kw or {})


class TestRebuildGraph(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_node_count(self):
        kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)
        self.assertEqual(kg.number_of_nodes(), 11)

    def test_edge_count(self):
        kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)
        self.assertGreater(kg.number_of_edges(), 0)

    def test_node_attributes_preserved(self):
        kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)
        data = kg.nodes["herb:人参"]
        self.assertEqual(data["name"], "人参")
        self.assertEqual(data["type"], "herb")

    def test_edge_attributes_preserved(self):
        kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)
        data = kg.get_edge_data("formula:四君子汤", "herb:人参")
        self.assertIsNotNone(data)
        self.assertEqual(data["relationship_type"], "sovereign")
        self.assertAlmostEqual(data["confidence"], 0.95)

    def test_duplicate_edge_keeps_highest_confidence(self):
        graph_data = {
            "nodes": [
                {"id": "formula:A", "data": {}},
                {"id": "herb:B",    "data": {}},
            ],
            "edges": [
                {"source": "formula:A", "target": "herb:B", "attributes": {"relationship_type": "sovereign", "confidence": 0.70}},
                {"source": "formula:A", "target": "herb:B", "attributes": {"relationship_type": "sovereign", "confidence": 0.95}},
            ],
        }
        kg = self.engine._rebuild_graph(graph_data)
        edge = kg.get_edge_data("formula:A", "herb:B")
        self.assertAlmostEqual(edge["confidence"], 0.95)

    def test_empty_graph(self):
        kg = self.engine._rebuild_graph(_EMPTY_GRAPH)
        self.assertEqual(kg.number_of_nodes(), 0)
        self.assertEqual(kg.number_of_edges(), 0)

    def test_missing_source_or_target_skipped(self):
        graph_data = {
            "nodes": [{"id": "formula:A", "data": {}}],
            "edges": [
                {"source": "",          "target": "formula:A", "attributes": {}},
                {"source": "formula:A", "target": "",          "attributes": {}},
            ],
        }
        kg = self.engine._rebuild_graph(graph_data)
        self.assertEqual(kg.number_of_edges(), 0)


class TestAnalyzeCompositionRoles(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_returns_formula_compositions_key(self):
        result = self.engine._analyze_composition_roles(self.kg, _SAMPLE_ENTITIES)
        self.assertIn("formula_compositions", result)

    def test_four_gentlemen_roles(self):
        result = self.engine._analyze_composition_roles(self.kg, _SAMPLE_ENTITIES)
        comp = result["formula_compositions"].get("四君子汤", {})
        self.assertGreater(comp.get("sovereign_count", 0), 0)
        self.assertEqual(comp.get("minister_count", 0), 1)
        self.assertEqual(comp.get("assistant_count", 0), 1)
        self.assertEqual(comp.get("envoy_count", 0), 1)

    def test_total_formulas_analyzed(self):
        result = self.engine._analyze_composition_roles(self.kg, _SAMPLE_ENTITIES)
        self.assertEqual(result["total_formulas_analyzed"], 2)

    def test_formula_not_in_kg_skipped(self):
        entities = [{"name": "不存在方剂", "type": "formula"}]
        kg = self.engine._rebuild_graph(_EMPTY_GRAPH)
        result = self.engine._analyze_composition_roles(kg, entities)
        self.assertEqual(result["total_formulas_analyzed"], 0)

    def test_role_herb_names_are_strings(self):
        result = self.engine._analyze_composition_roles(self.kg, _SAMPLE_ENTITIES)
        for formula, comp in result["formula_compositions"].items():
            for role_herbs in comp["roles"].values():
                for h in role_herbs:
                    self.assertIsInstance(h, str)


class TestFindKgPaths(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_returns_list(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        self.assertIsInstance(paths, list)

    def test_paths_have_required_keys(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        required = {"path", "length", "relationship_sequence", "confidence"}
        for p in paths:
            self.assertEqual(required, required & set(p.keys()))

    def test_paths_sorted_by_confidence_desc(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        confs = [p["confidence"] for p in paths]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_path_length_matches_sequence_length(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        for p in paths:
            self.assertEqual(p["length"], len(p["relationship_sequence"]))
            self.assertEqual(p["length"], len(p["path"]) - 1)

    def test_formula_to_syndrome_path_found(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        # 应该找到 四君子汤 → 脾气虚证 的直接 treats 路径
        direct = [
            p for p in paths
            if "formula:四君子汤" in p["path"] and "syndrome:脾气虚证" in p["path"]
        ]
        self.assertTrue(len(direct) > 0)

    def test_empty_kg_returns_empty(self):
        kg = self.engine._rebuild_graph(_EMPTY_GRAPH)
        paths = self.engine._find_kg_paths(kg, _SAMPLE_ENTITIES)
        self.assertEqual(paths, [])

    def test_confidence_in_0_1_range(self):
        paths = self.engine._find_kg_paths(self.kg, _SAMPLE_ENTITIES)
        for p in paths:
            self.assertGreaterEqual(p["confidence"], 0.0)
            self.assertLessEqual(p["confidence"],    1.0)


class TestBuildInferenceChains(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_returns_list(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        self.assertIsInstance(chains, list)

    def test_chain_has_required_keys(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        required = {"formula", "path", "relationship_sequence", "pattern", "confidence",
                    "terminal_node", "terminal_label"}
        for c in chains:
            self.assertEqual(required, required & set(c.keys()))

    def test_chains_include_sovereign_efficacy(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        # 四君子汤 -sovereign→ 人参 -efficacy→ 补气  应该被找到
        matching = [
            c for c in chains
            if c["formula"] == "四君子汤" and "sovereign" in c["relationship_sequence"]
            and c["relationship_sequence"][-1] == "efficacy"
        ]
        self.assertTrue(len(matching) > 0)

    def test_chains_no_cycles(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        for c in chains:
            self.assertEqual(len(c["path"]), len(set(c["path"])))

    def test_unique_paths(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        keys = ["→".join(c["path"]) for c in chains]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sorted_by_confidence_desc(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        confs = [c["confidence"] for c in chains]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_terminal_label_is_name_part(self):
        chains = self.engine._build_inference_chains(self.kg, _SAMPLE_ENTITIES)
        for c in chains:
            # terminal_label should not contain the type prefix
            self.assertNotIn(":", c.get("terminal_label", ""))


class TestFindHubNodes(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(top_k_hubs=5)
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_returns_list(self):
        hubs = self.engine._find_hub_nodes(self.kg)
        self.assertIsInstance(hubs, list)

    def test_respects_top_k(self):
        hubs = self.engine._find_hub_nodes(self.kg)
        self.assertLessEqual(len(hubs), 5)

    def test_hub_keys_present(self):
        hubs = self.engine._find_hub_nodes(self.kg)
        required = {"node_id", "name", "entity_type", "degree_centrality", "out_degree", "in_degree", "confidence"}
        for h in hubs:
            self.assertEqual(required, required & set(h.keys()))

    def test_sorted_by_centrality_desc(self):
        hubs = self.engine._find_hub_nodes(self.kg)
        cents = [h["degree_centrality"] for h in hubs]
        self.assertEqual(cents, sorted(cents, reverse=True))

    def test_empty_graph_returns_empty(self):
        kg = self.engine._rebuild_graph(_EMPTY_GRAPH)
        hubs = self.engine._find_hub_nodes(kg)
        self.assertEqual(hubs, [])


class TestCoverageStats(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_keys_present(self):
        stats = self.engine._coverage_stats(self.kg, _SAMPLE_ENTITIES)
        required = {"total_entities", "entities_in_kg", "overall_coverage_rate",
                    "kg_nodes", "kg_edges", "coverage_by_type"}
        self.assertEqual(required, required & set(stats.keys()))

    def test_total_entities_matches(self):
        stats = self.engine._coverage_stats(self.kg, _SAMPLE_ENTITIES)
        self.assertEqual(stats["total_entities"], len(_SAMPLE_ENTITIES))

    def test_coverage_rate_in_range(self):
        stats = self.engine._coverage_stats(self.kg, _SAMPLE_ENTITIES)
        self.assertGreaterEqual(stats["overall_coverage_rate"], 0.0)
        self.assertLessEqual(stats["overall_coverage_rate"],    1.0)

    def test_coverage_by_type_contains_formula(self):
        stats = self.engine._coverage_stats(self.kg, _SAMPLE_ENTITIES)
        self.assertIn("formula", stats["coverage_by_type"])

    def test_empty_entities(self):
        stats = self.engine._coverage_stats(self.kg, [])
        self.assertEqual(stats["total_entities"], 0)
        self.assertEqual(stats["overall_coverage_rate"], 0.0)


class TestDoExecuteOutputStructure(unittest.TestCase):
    """_do_execute() 应产生所有预期字段（向后兼容 + 新增）。"""

    def setUp(self):
        self.engine = _make_engine()
        self.engine.initialize()

    def _run(self):
        return self.engine._do_execute({
            "entities": _SAMPLE_ENTITIES,
            "semantic_graph": _SAMPLE_GRAPH,
        })

    # 向后兼容字段
    def test_has_reasoning_results(self):
        out = self._run()
        self.assertIn("reasoning_results", out)

    def test_reasoning_results_entity_relationships(self):
        out = self._run()
        self.assertIn("entity_relationships", out["reasoning_results"])
        self.assertIsInstance(out["reasoning_results"]["entity_relationships"], list)

    def test_reasoning_results_knowledge_patterns(self):
        out = self._run()
        patterns = out["reasoning_results"]["knowledge_patterns"]
        self.assertIn("common_entities", patterns)
        self.assertIn("entity_groups", patterns)

    def test_reasoning_results_inference_confidence(self):
        out = self._run()
        conf = out["reasoning_results"]["inference_confidence"]
        self.assertIsInstance(conf, float)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf,    1.0)

    def test_has_temporal_analysis(self):
        out = self._run()
        self.assertIn("temporal_analysis", out)

    def test_temporal_analysis_time_periods(self):
        out = self._run()
        self.assertIn("time_periods", out["temporal_analysis"])
        self.assertIsInstance(out["temporal_analysis"]["time_periods"], list)

    def test_temporal_analysis_temporal_patterns(self):
        out = self._run()
        self.assertIn("temporal_patterns", out["temporal_analysis"])
        self.assertIsInstance(out["temporal_analysis"]["temporal_patterns"], list)

    def test_has_pattern_recognition(self):
        out = self._run()
        self.assertIn("pattern_recognition", out)

    def test_pattern_recognition_common_patterns(self):
        out = self._run()
        self.assertIn("common_patterns", out["pattern_recognition"])
        self.assertIsInstance(out["pattern_recognition"]["common_patterns"], list)

    def test_pattern_recognition_prediction(self):
        out = self._run()
        self.assertIn("prediction", out["pattern_recognition"])
        self.assertIsInstance(out["pattern_recognition"]["prediction"], str)

    # 新增字段
    def test_has_kg_paths(self):
        out = self._run()
        self.assertIn("kg_paths", out)
        self.assertIsInstance(out["kg_paths"], list)

    def test_has_inference_chains(self):
        out = self._run()
        self.assertIn("inference_chains", out)
        self.assertIsInstance(out["inference_chains"], list)

    def test_has_composition_analysis(self):
        out = self._run()
        self.assertIn("composition_analysis", out)
        self.assertIn("formula_compositions", out["composition_analysis"])

    def test_has_hub_nodes(self):
        out = self._run()
        self.assertIn("hub_nodes", out)
        self.assertIsInstance(out["hub_nodes"], list)

    def test_has_coverage_stats(self):
        out = self._run()
        self.assertIn("coverage_stats", out)
        self.assertIn("overall_coverage_rate", out["coverage_stats"])

    def test_no_cross_product_relationships(self):
        """entity_relationships 应为 KG 边数，不是 O(n²) 笛卡尔积。"""
        out = self._run()
        n = len(_SAMPLE_ENTITIES)
        edge_count = len(out["reasoning_results"]["entity_relationships"])
        self.assertLess(edge_count, n * n)


class TestDoExecuteEmptyInput(unittest.TestCase):
    """空输入不应崩溃。"""

    def setUp(self):
        self.engine = _make_engine()
        self.engine.initialize()

    def test_empty_entities_and_graph(self):
        out = self.engine._do_execute({"entities": [], "semantic_graph": {}})
        self.assertIn("reasoning_results", out)
        self.assertIn("kg_paths", out)

    def test_entities_no_graph(self):
        out = self.engine._do_execute({"entities": _SAMPLE_ENTITIES})
        self.assertIn("reasoning_results", out)
        self.assertEqual(out["coverage_stats"]["kg_nodes"], 0)


class TestPathConfidence(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.kg = self.engine._rebuild_graph(_SAMPLE_GRAPH)

    def test_single_edge_confidence(self):
        # 单跳路径
        path = ["formula:四君子汤", "herb:人参"]
        conf = self.engine._path_confidence(self.kg, path)
        self.assertGreater(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_empty_path_returns_zero(self):
        conf = self.engine._path_confidence(self.kg, ["sole_node"])
        self.assertEqual(conf, 0.0)

    def test_longer_path_lowers_confidence(self):
        short = ["formula:四君子汤", "herb:人参"]
        long_ = ["formula:四君子汤", "herb:人参", "efficacy:补气"]
        conf_short = self.engine._path_confidence(self.kg, short)
        conf_long  = self.engine._path_confidence(self.kg, long_)
        # 长路径置信度 ≤ 短路径 (几何均值特性)
        self.assertLessEqual(conf_long, conf_short + 0.01)  # slight tolerance


class TestRoleWeights(unittest.TestCase):
    def test_sovereign_highest(self):
        self.assertGreaterEqual(_ROLE_WEIGHTS["sovereign"], _ROLE_WEIGHTS["minister"])
        self.assertGreaterEqual(_ROLE_WEIGHTS["minister"],  _ROLE_WEIGHTS["assistant"])
        self.assertGreaterEqual(_ROLE_WEIGHTS["assistant"], _ROLE_WEIGHTS["envoy"])

    def test_all_weights_in_range(self):
        for rel, w in _ROLE_WEIGHTS.items():
            self.assertGreater(w, 0.0, msg=rel)
            self.assertLessEqual(w, 1.0, msg=rel)


if __name__ == "__main__":
    unittest.main()
