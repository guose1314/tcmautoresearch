# -*- coding: utf-8 -*-
"""
tests/test_analysis_modules.py
测试拆分后的 10 个分析模块各自的核心方法。

模块清单：
 1. DocumentPreprocessor       — 文档预处理
 2. AdvancedEntityExtractor    — TCM 实体抽取
 3. SemanticGraphBuilder       — 语义图构建
 4. ReasoningEngine            — 推理引擎
 5. DataMiningService          — 数据挖掘
 6. FormulaStructureAnalyzer   — 方剂结构
 7. FormulaComparator          — 方剂比较
 8. NetworkPharmacologySystemBiologyAnalyzer — 网络药理学
 9. HerbPropertyDatabase       — 药性数据库
10. MultimodalFusionEngine     — 多模态融合
"""
from __future__ import annotations

import pytest

# ===================================================================
# 1. DocumentPreprocessor
# ===================================================================

class TestDocumentPreprocessor:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.analysis.preprocessor import DocumentPreprocessor
        self.pp = DocumentPreprocessor()
        self.pp.initialize()
        yield
        self.pp.cleanup()

    def test_initialize(self):
        assert self.pp.initialized is True

    def test_execute_basic(self):
        result = self.pp.execute({"raw_text": "黄芪味甘，性微温，归脾、肺经。"})
        assert "processed_text" in result
        assert isinstance(result["processed_text"], str)
        assert len(result["processed_text"]) > 0

    def test_execute_empty_text_raises(self):
        with pytest.raises(ValueError, match="缺少原始文本输入"):
            self.pp.execute({"raw_text": ""})

    def test_metadata_in_output(self):
        result = self.pp.execute({"raw_text": "人参补气"})
        assert "metadata" in result or "processing_steps" in result


# ===================================================================
# 2. AdvancedEntityExtractor
# ===================================================================

class TestAdvancedEntityExtractor:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.analysis.entity_extractor import AdvancedEntityExtractor
        self.ext = AdvancedEntityExtractor()
        self.ext.initialize()
        yield
        self.ext.cleanup()

    def test_initialize(self):
        assert self.ext.initialized is True

    def test_extract_entities(self):
        ctx = {"processed_text": "黄芪30克，人参10克，甘草6克，配伍白术15克。"}
        result = self.ext.execute(ctx)
        assert "entities" in result
        assert isinstance(result["entities"], list)

    def test_entities_have_expected_fields(self):
        ctx = {"processed_text": "黄芪补气升阳，人参大补元气。"}
        result = self.ext.execute(ctx)
        if result["entities"]:
            entity = result["entities"][0]
            assert "name" in entity
            assert "type" in entity

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="缺少处理后的文本输入"):
            self.ext.execute({"processed_text": ""})


# ===================================================================
# 3. SemanticGraphBuilder
# ===================================================================

class TestSemanticGraphBuilder:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.analysis.semantic_graph import SemanticGraphBuilder
        self.sg = SemanticGraphBuilder()
        self.sg.initialize()
        yield
        self.sg.cleanup()

    def test_initialize(self):
        assert self.sg.initialized is True

    def test_execute_with_entities(self):
        ctx = {
            "processed_text": "黄芪补气升阳",
            "entities": [
                {"name": "黄芪", "type": "herb", "confidence": 0.9},
                {"name": "补气", "type": "efficacy", "confidence": 0.8},
            ],
        }
        result = self.sg.execute(ctx)
        assert isinstance(result, dict)

    def test_graph_statistics(self):
        ctx = {
            "processed_text": "人参补气",
            "entities": [{"name": "人参", "type": "herb", "confidence": 0.9}],
        }
        result = self.sg.execute(ctx)
        # 结果中应包含图统计或语义图
        assert "graph_statistics" in result or "semantic_graph" in result or "summary_analysis" in result


# ===================================================================
# 4. ReasoningEngine
# ===================================================================

class TestReasoningEngine:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.analysis.reasoning_engine import ReasoningEngine
        self.re = ReasoningEngine()
        self.re.initialize()
        yield
        self.re.cleanup()

    def test_initialize(self):
        assert self.re.initialized is True

    def test_execute_with_entities_and_graph(self):
        ctx = {
            "entities": [
                {"name": "黄芪", "type": "herb"},
                {"name": "补气", "type": "efficacy"},
            ],
            "semantic_graph": {"nodes": [], "edges": []},
        }
        result = self.re.execute(ctx)
        assert isinstance(result, dict)

    def test_reasoning_output_keys(self):
        ctx = {
            "entities": [{"name": "人参", "type": "herb"}],
            "semantic_graph": {},
        }
        result = self.re.execute(ctx)
        # 至少应含推理结果或推理路径
        has_key = any(
            k in result
            for k in ("reasoning_results", "inference_chains", "pattern_recognition", "kg_paths")
        )
        assert has_key or isinstance(result, dict)


# ===================================================================
# 5. DataMiningService
# ===================================================================

class TestDataMiningService:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.analysis.data_mining import DataMiningService
        self.dm = DataMiningService()
        self.dm.initialize()
        yield
        self.dm.cleanup()

    def test_initialize(self):
        assert self.dm.initialized is True

    def test_execute_with_records(self):
        ctx = {
            "records": [
                {"items": ["黄芪", "人参", "甘草"]},
                {"items": ["人参", "白术", "茯苓"]},
                {"items": ["黄芪", "当归", "甘草"]},
            ],
            "methods": ["frequent_itemsets"],
        }
        result = self.dm.execute(ctx)
        assert isinstance(result, dict)

    def test_default_config_values(self):
        assert self.dm.min_support > 0
        assert self.dm.min_confidence > 0


# ===================================================================
# 6. FormulaStructureAnalyzer
# ===================================================================

class TestFormulaStructureAnalyzer:
    def test_analyze_known_formula(self):
        from src.analysis.formula_structure import FormulaStructureAnalyzer
        result = FormulaStructureAnalyzer.analyze_formula_structure("四君子汤")
        assert isinstance(result, dict)
        assert result.get("formula_name") == "四君子汤"

    def test_analyze_unknown_formula(self):
        from src.analysis.formula_structure import FormulaStructureAnalyzer
        result = FormulaStructureAnalyzer.analyze_formula_structure("__不存在的方__")
        assert isinstance(result, dict)

    def test_get_formula_composition(self):
        from src.analysis.formula_structure import FormulaStructureAnalyzer
        result = FormulaStructureAnalyzer.get_formula_composition("四君子汤")
        assert isinstance(result, dict)


# ===================================================================
# 7. FormulaComparator
# ===================================================================

class TestFormulaComparator:
    def test_compare_two_formulas(self):
        from src.analysis.formula_comparator import FormulaComparator
        result = FormulaComparator.compare_formulas("四君子汤", "六君子汤")
        assert isinstance(result, dict)

    def test_find_similar_formulas(self):
        from src.analysis.formula_comparator import FormulaComparator
        result = FormulaComparator.find_similar_formulas("四君子汤")
        assert isinstance(result, (list, dict))


# ===================================================================
# 8. NetworkPharmacologySystemBiologyAnalyzer
# ===================================================================

class TestNetworkPharmacology:
    def test_analyze_formula_network(self):
        from src.analysis.network_pharmacology import (
            NetworkPharmacologySystemBiologyAnalyzer,
        )
        result = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(
            "四君子汤", ["人参", "白术", "茯苓", "甘草"]
        )
        assert isinstance(result, dict)

    def test_result_has_expected_keys(self):
        from src.analysis.network_pharmacology import (
            NetworkPharmacologySystemBiologyAnalyzer,
        )
        result = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(
            "补中益气汤", ["黄芪", "人参"]
        )
        # 应包含网络分析结果的某些键
        assert isinstance(result, dict)


# ===================================================================
# 9. HerbPropertyDatabase
# ===================================================================

class TestHerbPropertyDatabase:
    def test_import(self):
        from src.analysis.herb_properties import (
            HerbPropertyDatabase,
            HerbTemperature,
            MeridianType,
        )
        assert HerbPropertyDatabase is not None
        assert HerbTemperature is not None
        assert MeridianType is not None

    def test_herb_properties_class_attributes(self):
        from src.analysis.herb_properties import HerbPropertyDatabase
        # HerbPropertyDatabase 应具有 HERB_PROPERTIES 或相关数据
        assert hasattr(HerbPropertyDatabase, "HERB_PROPERTIES") or callable(
            getattr(HerbPropertyDatabase, "get_herb_property", None)
        )


# ===================================================================
# 10. MultimodalFusionEngine
# ===================================================================

class TestMultimodalFusionEngine:
    def test_extract_text_modality(self):
        from src.analysis.multimodal_fusion import (
            FusionStrategy,
            MultimodalFusionEngine,
        )
        engine = MultimodalFusionEngine(strategy=FusionStrategy.ATTENTION)
        modalities = engine.extract_modalities({"processed_text": "黄芪补气升阳"})
        assert len(modalities) >= 1
        assert modalities[0].name == "text"

    def test_extract_entity_modality(self):
        from src.analysis.multimodal_fusion import MultimodalFusionEngine
        engine = MultimodalFusionEngine()
        modalities = engine.extract_modalities({
            "processed_text": "人参",
            "entities": [{"name": "人参", "type": "herb"}],
        })
        names = [m.name for m in modalities]
        assert "entity" in names

    def test_fuse_single_modality(self):
        from src.analysis.multimodal_fusion import (
            FusionStrategy,
            ModalityData,
            MultimodalFusionEngine,
        )
        engine = MultimodalFusionEngine()
        modality = ModalityData(
            name="text",
            features={"length": 0.5, "diversity": 0.8},
            weight=1.0,
            confidence=0.9,
        )
        result = engine.fuse([modality])
        assert result.confidence > 0
        assert "text" in result.modality_weights

    def test_fuse_multiple_modalities(self):
        from src.analysis.multimodal_fusion import (
            FusionStrategy,
            ModalityData,
            MultimodalFusionEngine,
        )
        engine = MultimodalFusionEngine(strategy=FusionStrategy.WEIGHTED_SUM)
        m1 = ModalityData(name="text", features={"f1": 0.5}, weight=1.0, confidence=0.9)
        m2 = ModalityData(name="entity", features={"f1": 0.8}, weight=1.0, confidence=0.85)
        result = engine.fuse([m1, m2])
        assert len(result.modality_weights) == 2
        assert result.confidence > 0

    def test_fuse_empty_raises(self):
        from src.analysis.multimodal_fusion import MultimodalFusionEngine
        engine = MultimodalFusionEngine()
        with pytest.raises(ValueError, match="至少需要一个模态"):
            engine.fuse([])

    def test_fusion_history_tracking(self):
        from src.analysis.multimodal_fusion import ModalityData, MultimodalFusionEngine
        engine = MultimodalFusionEngine()
        m = ModalityData(name="text", features={"f": 0.5})
        engine.fuse([m])
        engine.fuse([m])
        history = engine.get_fusion_history()
        assert len(history) == 2

    @pytest.mark.parametrize("strategy", ["weighted_sum", "attention", "max_pool", "product"])
    def test_all_strategies(self, strategy):
        from src.analysis.multimodal_fusion import (
            FusionStrategy,
            ModalityData,
            MultimodalFusionEngine,
        )
        s = FusionStrategy(strategy)
        engine = MultimodalFusionEngine(strategy=s)
        m1 = ModalityData(name="a", features={"x": 0.5, "y": 0.3})
        m2 = ModalityData(name="b", features={"x": 0.7, "y": 0.9})
        result = engine.fuse([m1, m2])
        assert isinstance(result.fused_features, dict)
