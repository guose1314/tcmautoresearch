"""tests/test_data_miner.py — DataMiner 独立模块单元测试 (2.2)"""

import numpy as np
import pytest

from src.research.data_miner import (
    DataMiner,
    NetworkPharmacologySystemBiologyAnalyzer,
    StatisticalDataMiner,
)

# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

HERBS = ["黄芪", "党参", "白术", "茯苓", "甘草"]

RECORDS = [
    {"formula": "补中益气汤", "herbs": ["黄芪", "党参", "白术", "甘草"]},
    {"formula": "四君子汤",   "herbs": ["党参", "白术", "茯苓", "甘草"]},
    {"formula": "参苓白术散", "herbs": ["党参", "白术", "茯苓", "甘草"]},
    {"formula": "六君子汤",   "herbs": ["党参", "白术", "茯苓", "甘草", "黄芪"]},
    {"formula": "归脾汤",     "herbs": ["黄芪", "党参", "白术", "茯苓"]},
]


# ===========================================================================
# cluster() 公共接口
# ===========================================================================

class TestCluster:
    def test_returns_clusters_and_factors_keys(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        assert "clusters" in result
        assert "factors" in result

    def test_clusters_count_equals_record_count(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        assert len(result["clusters"]) == len(RECORDS)

    def test_cluster_labels_are_ints(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        for item in result["clusters"]:
            assert isinstance(item["cluster"], int)

    def test_cluster_formula_preserved(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        formulas = [item["formula"] for item in result["clusters"]]
        expected = [r["formula"] for r in RECORDS]
        assert formulas == expected

    def test_factors_are_list(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        assert isinstance(result["factors"], list)

    def test_factor_top_herbs_structure(self):
        result = DataMiner.cluster(RECORDS, HERBS)
        for factor in result["factors"]:
            assert "factor" in factor
            assert "top_herbs" in factor
            for item in factor["top_herbs"]:
                assert "herb" in item
                assert "loading" in item

    def test_empty_records_returns_empty(self):
        result = DataMiner.cluster([], HERBS)
        assert result == {"clusters": [], "factors": []}

    def test_empty_herbs_returns_empty(self):
        result = DataMiner.cluster(RECORDS, [])
        assert result == {"clusters": [], "factors": []}

    def test_single_record(self):
        result = DataMiner.cluster(RECORDS[:1], HERBS)
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["cluster"] == 0

    def test_two_records(self):
        result = DataMiner.cluster(RECORDS[:2], HERBS)
        assert len(result["clusters"]) == 2


# ===========================================================================
# latent_topics() 公共接口
# ===========================================================================

class TestLatentTopics:
    def test_returns_topics_key(self):
        result = DataMiner.latent_topics(RECORDS, HERBS)
        assert "topics" in result

    def test_topics_is_list(self):
        result = DataMiner.latent_topics(RECORDS, HERBS)
        assert isinstance(result["topics"], list)

    def test_topics_not_empty(self):
        result = DataMiner.latent_topics(RECORDS, HERBS)
        assert len(result["topics"]) >= 1

    def test_topic_structure(self):
        result = DataMiner.latent_topics(RECORDS, HERBS)
        for topic in result["topics"]:
            assert "topic" in topic
            assert "top_herbs" in topic
            for item in topic["top_herbs"]:
                assert "herb" in item
                assert "weight" in item

    def test_empty_records_returns_empty(self):
        result = DataMiner.latent_topics([], HERBS)
        assert result == {"topics": []}

    def test_empty_herbs_returns_empty(self):
        result = DataMiner.latent_topics(RECORDS, [])
        assert result == {"topics": []}


# ===========================================================================
# _numpy_kmeans() 内部方法
# ===========================================================================

class TestNumpyKmeans:
    def test_returns_list_of_ints(self):
        X = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.0, 0.0]])
        labels = DataMiner._numpy_kmeans(X, k=2)
        assert isinstance(labels, list)
        assert len(labels) == 4
        assert all(isinstance(label, int) for label in labels)

    def test_k_equals_n_returns_sequential(self):
        X = np.ones((3, 2))
        labels = DataMiner._numpy_kmeans(X, k=3)
        assert labels == [0, 1, 2]

    def test_k_greater_than_n_returns_sequential(self):
        X = np.ones((2, 2))
        labels = DataMiner._numpy_kmeans(X, k=5)
        assert labels == [0, 1]

    def test_single_cluster(self):
        X = np.array([[1.0, 0.0], [1.0, 0.1], [0.9, 0.0]])
        labels = DataMiner._numpy_kmeans(X, k=1)
        assert all(label == 0 for label in labels)
        assert len(labels) == 3

    def test_deterministic(self):
        X = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.0, 0.0]])
        labels_a = DataMiner._numpy_kmeans(X, k=2)
        labels_b = DataMiner._numpy_kmeans(X, k=2)
        assert labels_a == labels_b

    def test_label_count_matches_rows(self):
        X = np.random.default_rng(0).random((10, 5))
        labels = DataMiner._numpy_kmeans(X, k=3)
        assert len(labels) == 10

    def test_labels_within_range(self):
        X = np.random.default_rng(1).random((8, 4))
        labels = DataMiner._numpy_kmeans(X, k=3)
        assert all(0 <= label < 3 for label in labels)


# ===========================================================================
# _svd_fallback_factors()
# ===========================================================================

class TestSvdFallbackFactors:
    def _make_X(self):
        return np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])

    def test_returns_list(self):
        herbs = ["甘草", "黄芪", "党参"]
        result = DataMiner._svd_fallback_factors(self._make_X(), herbs)
        assert isinstance(result, list)

    def test_each_entry_has_factor_and_top_herbs(self):
        herbs = ["甘草", "黄芪", "党参"]
        result = DataMiner._svd_fallback_factors(self._make_X(), herbs)
        for entry in result:
            assert "factor" in entry
            assert "top_herbs" in entry

    def test_top_herbs_max_5(self):
        herbs = list("ABCDEFGHIJ")  # 10 herbs
        X = np.eye(10)
        result = DataMiner._svd_fallback_factors(X, herbs)
        for entry in result:
            assert len(entry["top_herbs"]) <= 5


# ===========================================================================
# _svd_latent_topics()
# ===========================================================================

class TestSvdLatentTopics:
    def _make_X(self):
        return np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])

    def test_returns_list(self):
        herbs = ["甘草", "黄芪", "党参"]
        result = DataMiner._svd_latent_topics(self._make_X(), herbs)
        assert isinstance(result, list)

    def test_topic_structure(self):
        herbs = ["甘草", "黄芪", "党参"]
        result = DataMiner._svd_latent_topics(self._make_X(), herbs)
        for entry in result:
            assert "topic" in entry
            assert "top_herbs" in entry
            for item in entry["top_herbs"]:
                assert "herb" in item
                assert "weight" in item

    def test_top_herbs_max_5(self):
        herbs = list("ABCDEFGHIJ")
        X = np.eye(10)
        result = DataMiner._svd_latent_topics(X, herbs)
        for entry in result:
            assert len(entry["top_herbs"]) <= 5


# ===========================================================================
# 渐进迁移：SummaryAnalysisEngine 仍可正常调用（委托验证）
# ===========================================================================

class TestDelegation:
    """验证 SummaryAnalysisEngine._clustering_and_factor_analysis / _latent_structure_model
    委托给 DataMiner 后输出结构不变。"""

    @pytest.fixture(autouse=True)
    def _import_engine(self):
        from src.semantic_modeling.research_methods import SummaryAnalysisEngine
        self.engine = SummaryAnalysisEngine

    def test_clustering_delegation_returns_clusters_and_factors(self):
        result = self.engine._clustering_and_factor_analysis(RECORDS, HERBS)
        assert "clusters" in result
        assert "factors" in result
        assert len(result["clusters"]) == len(RECORDS)

    def test_latent_delegation_returns_topics(self):
        result = self.engine._latent_structure_model(RECORDS, HERBS)
        assert "topics" in result
        assert isinstance(result["topics"], list)

    def test_svd_fallback_delegation(self):
        X = np.array([[1.0, 0.0], [0.0, 1.0]])
        result = self.engine._svd_fallback_factors(X, ["黄芪", "党参"])
        assert isinstance(result, list)

    def test_svd_latent_delegation(self):
        X = np.array([[1.0, 0.0], [0.0, 1.0]])
        result = self.engine._svd_latent_topics(X, ["黄芪", "党参"])
        assert isinstance(result, list)


class TestResearchDataMinerExtraction:
    def test_network_pharmacology_analysis(self):
        result = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(
            "四君子汤", ["人参", "甘草"]
        )
        assert result["formula_name"] == "四君子汤"
        assert result["target_count"] > 0
        assert isinstance(result["enriched_pathways"], list)

    def test_statistical_frequency_and_chi_square(self):
        result = StatisticalDataMiner.frequency_and_chi_square(RECORDS, HERBS)
        assert "herb_frequency" in result
        assert "chi_square_top" in result

    def test_statistical_association_rules(self):
        transactions = [r["herbs"] for r in RECORDS]
        result = StatisticalDataMiner.association_rules(transactions)
        assert "rules" in result
        assert isinstance(result["rules"], list)
