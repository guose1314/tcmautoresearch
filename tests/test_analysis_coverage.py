# tests/test_analysis_coverage.py
"""
分析层覆盖率补齐测试：
- entity_extractor.py (82% → ≥90%)
- data_mining.py (82% → ≥90%)
- preprocessor.py (87% → ≥90%)
- multimodal_fusion.py (89% → ≥90%)
"""
import unittest
from unittest.mock import MagicMock, patch

from src.analysis.data_mining import DataMiningService
from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.multimodal_fusion import (
    FusionResult,
    FusionStrategy,
    ModalityData,
    MultimodalFusionEngine,
)
from src.analysis.preprocessor import DocumentPreprocessor


# ============================================================
# AdvancedEntityExtractor
# ============================================================
class TestEntityExtractorInit(unittest.TestCase):
    def test_default_init(self):
        ext = AdvancedEntityExtractor()
        self.assertIsNotNone(ext.lexicon)
        self.assertEqual(ext.external_dict_paths, [])

    def test_init_with_external_dicts(self):
        ext = AdvancedEntityExtractor(config={"external_dicts": ["/fake/dict.txt"]})
        self.assertEqual(ext.external_dict_paths, ["/fake/dict.txt"])

    def test_dosage_patterns_exist(self):
        ext = AdvancedEntityExtractor()
        self.assertGreater(len(ext.dosage_patterns), 0)


class TestEntityExtractorInitialize(unittest.TestCase):
    def test_initialize_success(self):
        ext = AdvancedEntityExtractor()
        self.assertTrue(ext.initialize())

    def test_initialize_with_missing_external_dict(self):
        ext = AdvancedEntityExtractor(config={"external_dicts": ["/nonexistent/dict.txt"]})
        # Should still succeed, just log warning
        self.assertTrue(ext.initialize())


class TestEntityExtractorExecute(unittest.TestCase):
    def setUp(self):
        self.ext = AdvancedEntityExtractor()
        self.ext.initialize()

    def test_execute_basic(self):
        ctx = {"processed_text": "黄芪当归甘草白术茯苓"}
        result = self.ext._do_execute(ctx)
        self.assertIn("entities", result)
        self.assertIn("statistics", result)
        self.assertIn("confidence_scores", result)

    def test_execute_missing_text_raises(self):
        with self.assertRaises(ValueError):
            self.ext._do_execute({})

    def test_execute_non_string_text_raises(self):
        with self.assertRaises(ValueError):
            self.ext._do_execute({"processed_text": 123})

    def test_execute_empty_text_raises(self):
        with self.assertRaises(ValueError):
            self.ext._do_execute({"processed_text": ""})


class TestEntityExtraction(unittest.TestCase):
    def setUp(self):
        self.ext = AdvancedEntityExtractor()
        self.ext.initialize()

    def test_extract_entities(self):
        entities = self.ext._extract_entities("黄芪白术茯苓")
        self.assertIsInstance(entities, list)

    def test_extract_dosages_numeric(self):
        dosages = self.ext._extract_dosages("黄芪30克")
        self.assertTrue(any(d["type"] == "dosage" for d in dosages))

    def test_extract_dosages_chinese_number(self):
        dosages = self.ext._extract_dosages("黄芪三两")
        self.assertTrue(any(d["type"] == "dosage" for d in dosages))

    def test_no_overlap(self):
        """长词应优先于短词，不应有位置重叠"""
        entities = self.ext._extract_entities("四君子汤")
        # 检查无重叠位置
        positions = set()
        for e in entities:
            if e["type"] != "dosage":
                rng = range(e["position"], e["end_position"])
                overlap = positions & set(rng)
                self.assertEqual(len(overlap), 0, f"Overlap at {overlap}")
                positions.update(rng)


class TestEntityExtractionStatistics(unittest.TestCase):
    def setUp(self):
        self.ext = AdvancedEntityExtractor()
        self.ext.initialize()

    def test_calculate_statistics(self):
        entities = [
            {"type": "herb", "name": "黄芪"},
            {"type": "herb", "name": "白术"},
            {"type": "formula", "name": "四君子汤"},
        ]
        stats = self.ext._calculate_statistics(entities)
        self.assertEqual(stats["total_count"], 3)
        self.assertEqual(stats["by_type"]["herb"], 2)
        self.assertEqual(stats["by_type"]["formula"], 1)

    def test_calculate_confidence_empty(self):
        result = self.ext._calculate_confidence([])
        self.assertEqual(result["average_confidence"], 0.0)

    def test_calculate_confidence_non_empty(self):
        entities = [
            {"confidence": 0.9},
            {"confidence": 0.8},
        ]
        result = self.ext._calculate_confidence(entities)
        self.assertAlmostEqual(result["average_confidence"], 0.85)
        self.assertAlmostEqual(result["min_confidence"], 0.8)
        self.assertAlmostEqual(result["max_confidence"], 0.9)


class TestEntityExtractorCleanup(unittest.TestCase):
    def test_cleanup(self):
        ext = AdvancedEntityExtractor()
        ext.initialize()
        self.assertTrue(ext.cleanup())


# ============================================================
# DataMiningService
# ============================================================
class TestDataMiningInit(unittest.TestCase):
    def test_default_config(self):
        dm = DataMiningService()
        self.assertAlmostEqual(dm.min_support, 0.3)
        self.assertAlmostEqual(dm.min_confidence, 0.6)

    def test_custom_config(self):
        dm = DataMiningService(config={"min_support": "0.5", "min_confidence": "0.8"})
        self.assertAlmostEqual(dm.min_support, 0.5)
        self.assertAlmostEqual(dm.min_confidence, 0.8)


class TestDataMiningNormalizeMethods(unittest.TestCase):
    def test_alias_resolution(self):
        dm = DataMiningService()
        self.assertEqual(dm._normalize_methods("association"), ["association_rules"])
        self.assertEqual(dm._normalize_methods("frequent"), ["frequent_itemsets"])
        self.assertEqual(dm._normalize_methods("cluster"), ["clustering"])

    def test_list_input(self):
        dm = DataMiningService()
        result = dm._normalize_methods(["association", "cluster"])
        self.assertEqual(result, ["association_rules", "clustering"])

    def test_dedup(self):
        dm = DataMiningService()
        result = dm._normalize_methods(["association", "association_rules"])
        self.assertEqual(result, ["association_rules"])

    def test_empty(self):
        dm = DataMiningService()
        self.assertEqual(dm._normalize_methods(None), [])
        self.assertEqual(dm._normalize_methods([]), [])


class TestDataMiningResolve(unittest.TestCase):
    def setUp(self):
        self.dm = DataMiningService()
        self.dm.initialize()

    def test_resolve_records_from_context(self):
        ctx = {"records": [{"herbs": ["甘草", "黄芪"], "formula": "方一"}]}
        records = self.dm._resolve_records(ctx)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["formula"], "方一")

    def test_resolve_records_formula_records(self):
        ctx = {"formula_records": [{"herbs": ["白术"]}]}
        records = self.dm._resolve_records(ctx)
        self.assertEqual(len(records), 1)

    def test_resolve_transactions_explicit(self):
        ctx = {"transactions": [["甘草", "黄芪"], ["白术", "茯苓"]]}
        tx = self.dm._resolve_transactions(ctx, [])
        self.assertEqual(len(tx), 2)

    def test_derive_transactions_from_records(self):
        records = [
            {"herbs": ["甘草", "黄芪"]},
            {"herbs": ["白术", "茯苓"]},
        ]
        tx = self.dm._derive_transactions_from_records(records)
        self.assertEqual(len(tx), 2)

    def test_build_records_from_transactions(self):
        tx = [["甘草", "黄芪"], ["白术"]]
        records = self.dm._build_records_from_transactions(tx)
        self.assertEqual(len(records), 2)
        self.assertIn("formula", records[0])

    def test_resolve_items_explicit(self):
        ctx = {"herbs": ["甘草", "黄芪", "甘草"]}
        items = self.dm._resolve_items(ctx, [], [])
        self.assertEqual(len(items), 2)  # deduped

    def test_resolve_items_from_transactions(self):
        ctx = {}
        items = self.dm._resolve_items(ctx, [], [["甘草", "黄芪"]])
        self.assertIn("甘草", items)

    def test_normalize_transaction_dict(self):
        tx = {"herbs": ["甘草", "黄芪"]}
        result = self.dm._normalize_transaction(tx)
        self.assertEqual(len(result), 2)

    def test_normalize_transaction_string(self):
        result = self.dm._normalize_transaction("甘草")
        self.assertEqual(result, ["甘草"])


class TestDataMiningExecute(unittest.TestCase):
    def setUp(self):
        self.dm = DataMiningService()
        self.dm.initialize()

    def test_execute_frequent_itemsets(self):
        ctx = {
            "methods": ["frequent_itemsets"],
            "transactions": [
                ["甘草", "黄芪", "白术"],
                ["甘草", "黄芪"],
                ["甘草", "白术"],
                ["黄芪", "白术"],
            ],
        }
        result = self.dm._do_execute(ctx)
        self.assertIn("frequent_itemsets", result)
        self.assertIn("frequent_itemsets", result["methods_executed"])

    def test_execute_association_rules(self):
        ctx = {
            "methods": ["association_rules"],
            "transactions": [
                ["甘草", "黄芪", "白术"],
                ["甘草", "黄芪"],
                ["甘草", "白术"],
            ],
        }
        result = self.dm._do_execute(ctx)
        self.assertIn("association_rules", result)

    def test_execute_clustering(self):
        ctx = {
            "methods": ["clustering"],
            "records": [
                {"herbs": ["甘草", "黄芪"]},
                {"herbs": ["白术", "茯苓"]},
            ],
        }
        result = self.dm._do_execute(ctx)
        self.assertIn("clustering", result)

    def test_execute_no_data_raises(self):
        with self.assertRaises(ValueError):
            self.dm._do_execute({"methods": ["frequent_itemsets"]})

    def test_execute_records_only(self):
        """只提供 records，应自动推导 transactions"""
        ctx = {
            "methods": ["frequent_itemsets"],
            "records": [
                {"herbs": ["甘草", "黄芪"]},
                {"herbs": ["白术", "茯苓"]},
            ],
        }
        result = self.dm._do_execute(ctx)
        self.assertIn("frequent_itemsets", result)

    def test_execute_transactions_only(self):
        """只提供 transactions，应自动推导 records"""
        ctx = {
            "methods": ["frequent_itemsets"],
            "transactions": [["甘草", "黄芪"]],
        }
        result = self.dm._do_execute(ctx)
        self.assertGreater(result["record_count"], 0)


class TestDataMiningCleanup(unittest.TestCase):
    def test_cleanup(self):
        dm = DataMiningService()
        dm.initialize()
        self.assertTrue(dm.cleanup())


# ============================================================
# DocumentPreprocessor
# ============================================================
class TestPreprocessorInit(unittest.TestCase):
    def test_default_config(self):
        pp = DocumentPreprocessor()
        self.assertEqual(pp.convert_mode, "t2s")
        self.assertEqual(pp.max_input_chars, 2_000_000)

    def test_custom_config(self):
        pp = DocumentPreprocessor(config={"convert_mode": "", "max_input_chars": "100"})
        self.assertEqual(pp.convert_mode, "")
        self.assertEqual(pp.max_input_chars, 100)


class TestPreprocessorInitialize(unittest.TestCase):
    def test_initialize_success(self):
        pp = DocumentPreprocessor(config={"convert_mode": ""})
        self.assertTrue(pp.initialize())


class TestPreprocessorExecute(unittest.TestCase):
    def setUp(self):
        self.pp = DocumentPreprocessor(config={"convert_mode": ""})
        self.pp.initialize()

    def test_execute_basic(self):
        result = self.pp._do_execute({"raw_text": "测试文本内容"})
        self.assertIn("processed_text", result)
        self.assertIn("metadata", result)
        self.assertIn("processing_steps", result)

    def test_execute_missing_text_raises(self):
        with self.assertRaises(ValueError):
            self.pp._do_execute({})

    def test_execute_non_string_raises(self):
        with self.assertRaises(ValueError):
            self.pp._do_execute({"raw_text": 123})

    def test_execute_empty_raises(self):
        with self.assertRaises(ValueError):
            self.pp._do_execute({"raw_text": ""})

    def test_execute_too_large_raises(self):
        pp = DocumentPreprocessor(config={"convert_mode": "", "max_input_chars": 10})
        pp.initialize()
        with self.assertRaises(ValueError):
            pp._do_execute({"raw_text": "a" * 20})


class TestPreprocessorTextProcessing(unittest.TestCase):
    def setUp(self):
        self.pp = DocumentPreprocessor(config={"convert_mode": ""})
        self.pp.initialize()

    def test_sanitize_control_chars(self):
        result = self.pp._sanitize_text("abc\x00\x01\x02def")
        self.assertEqual(result, "abcdef")

    def test_clean_line_breaks(self):
        result = self.pp._clean_line_breaks("中\n文")
        self.assertEqual(result, "中文")

    def test_normalize_whitespace(self):
        result = self.pp._normalize_whitespace("多   个   空格")
        self.assertEqual(result, "多 个 空格")

    def test_convert_text_no_opencc(self):
        result = self.pp._convert_text("繁體字")
        self.assertEqual(result, "繁體字")  # no opencc configured

    def test_process_text_pipeline(self):
        result = self.pp._process_text("  \x00内容\x01  \n\n\n\n  测试  ")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\n\n\n", result)


class TestPreprocessorSegment(unittest.TestCase):
    def setUp(self):
        self.pp = DocumentPreprocessor(config={"convert_mode": ""})
        self.pp.initialize()

    def test_segment_basic(self):
        result = self.pp.segment_text("中医药学是伟大的")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_segment_with_pos(self):
        result = self.pp.segment_text("中医药学", use_pos=True)
        self.assertIsInstance(result, list)

    def test_segment_ancient_punctuation(self):
        result = self.pp.segment_with_ancient_punctuation("主治头痛。功效清热。")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_augment_ancient_punctuation(self):
        text = "黄芪主治气虚"
        result = self.pp._augment_ancient_punctuation(text)
        self.assertIn("。", result)


class TestPreprocessorCleanup(unittest.TestCase):
    def test_cleanup(self):
        pp = DocumentPreprocessor(config={"convert_mode": ""})
        pp.initialize()
        # preprocessor doesn't define _do_cleanup, uses BaseModule default
        # just verify full cycle works


# ============================================================
# MultimodalFusionEngine
# ============================================================
class TestModalityData(unittest.TestCase):
    def test_to_vector_fills_missing(self):
        md = ModalityData(name="text", features={"a": 0.5, "b": 0.8})
        vec = md.to_vector(["a", "c", "b"])
        self.assertEqual(vec, [0.5, 0.0, 0.8])


class TestFusionResult(unittest.TestCase):
    def test_to_dict(self):
        fr = FusionResult(
            strategy=FusionStrategy.ATTENTION,
            fused_features={"a": 0.12345},
            confidence=0.87654,
            modality_weights={"text": 0.6},
            modality_contributions={"text": 1.0},
            evidence_score=0.5,
        )
        d = fr.to_dict()
        self.assertEqual(d["strategy"], "attention")
        self.assertEqual(d["fused_features"]["a"], 0.1235)


class TestFusionExtractModalities(unittest.TestCase):
    def test_extract_text_only(self):
        engine = MultimodalFusionEngine()
        modalities = engine.extract_modalities({"processed_text": "测试文本"})
        self.assertEqual(len(modalities), 1)
        self.assertEqual(modalities[0].name, "text")

    def test_extract_all_modalities(self):
        engine = MultimodalFusionEngine()
        ctx = {
            "processed_text": "测试文本",
            "entities": [{"type": "herb", "confidence": 0.9}],
            "semantic_graph": {"nodes": [1, 2], "edges": [1]},
            "performance_score": 0.8,
        }
        modalities = engine.extract_modalities(ctx)
        names = [m.name for m in modalities]
        self.assertIn("text", names)
        self.assertIn("entity", names)
        self.assertIn("graph", names)
        self.assertIn("stats", names)

    def test_extract_entity_dict_format(self):
        engine = MultimodalFusionEngine()
        ctx = {"entities": {"e1": {"type": "herb", "confidence": 0.9}}}
        modalities = engine.extract_modalities(ctx)
        self.assertEqual(len(modalities), 1)
        self.assertEqual(modalities[0].name, "entity")

    def test_extract_stats_modality(self):
        engine = MultimodalFusionEngine()
        ctx = {"performance_score": 0.7, "confidence_score": 0.8, "quality_score": 0.6}
        modalities = engine.extract_modalities(ctx)
        self.assertEqual(len(modalities), 1)
        self.assertEqual(modalities[0].name, "stats")

    def test_extract_empty_context(self):
        engine = MultimodalFusionEngine()
        modalities = engine.extract_modalities({})
        self.assertEqual(len(modalities), 0)


class TestFusionStrategies(unittest.TestCase):
    def setUp(self):
        self.modalities = [
            ModalityData(name="text", features={"a": 0.5, "b": 0.8}, confidence=0.9),
            ModalityData(name="entity", features={"a": 0.6, "c": 0.3}, confidence=0.85),
        ]

    def test_attention_strategy(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.ATTENTION)
        result = engine.fuse(self.modalities)
        self.assertIsInstance(result, FusionResult)
        self.assertGreater(result.confidence, 0)

    def test_weighted_sum_strategy(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.WEIGHTED_SUM)
        result = engine.fuse(self.modalities)
        self.assertIn("a", result.fused_features)

    def test_max_pool_strategy(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.MAX_POOL)
        result = engine.fuse(self.modalities)
        self.assertIn("a", result.fused_features)

    def test_product_strategy(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.PRODUCT)
        result = engine.fuse(self.modalities)
        self.assertIn("a", result.fused_features)

    def test_override_strategy(self):
        engine = MultimodalFusionEngine(strategy=FusionStrategy.ATTENTION)
        result = engine.fuse(self.modalities, strategy=FusionStrategy.MAX_POOL)
        self.assertEqual(result.strategy, FusionStrategy.MAX_POOL)


class TestFusionEdgeCases(unittest.TestCase):
    def test_empty_modalities_raises(self):
        engine = MultimodalFusionEngine()
        with self.assertRaises(ValueError):
            engine.fuse([])

    def test_single_modality(self):
        engine = MultimodalFusionEngine()
        modalities = [ModalityData(name="text", features={"a": 0.5}, confidence=0.9)]
        result = engine.fuse(modalities)
        self.assertEqual(result.evidence_score, 0.9)  # single modality → own confidence

    def test_fusion_history(self):
        engine = MultimodalFusionEngine()
        modalities = [ModalityData(name="text", features={"a": 0.5}, confidence=0.9)]
        engine.fuse(modalities)
        engine.fuse(modalities)
        history = engine.get_fusion_history()
        self.assertEqual(len(history), 2)

    def test_text_modality_features(self):
        md = MultimodalFusionEngine._extract_text_modality("测试文本123")
        self.assertIn("text_length_norm", md.features)
        self.assertIn("char_diversity", md.features)
        self.assertIn("digit_density", md.features)

    def test_graph_modality_features(self):
        md = MultimodalFusionEngine._extract_graph_modality({
            "nodes": list(range(10)),
            "edges": list(range(5)),
            "graph_statistics": {"connected_components": 2}
        })
        self.assertIn("graph_node_density", md.features)


if __name__ == "__main__":
    unittest.main()
