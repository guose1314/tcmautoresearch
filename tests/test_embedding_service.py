"""tests/test_embedding_service.py — 3.3 向量检索服务单元测试"""

import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from src.knowledge.embedding_service import (
    EmbeddingItem,
    EmbeddingService,
    SearchResult,
)


class FakeEncoder:
    def __init__(self, mapping):
        self.mapping = mapping

    def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True):
        vectors = []
        for text in texts:
            if text not in self.mapping:
                raise KeyError(f"missing fake vector for: {text}")
            vectors.append(self.mapping[text])
        return np.asarray(vectors, dtype=np.float32)


class TestEmbeddingModels(unittest.TestCase):
    def test_search_result_to_dict(self):
        result = SearchResult(
            item_id="formula-1",
            text="四君子汤；药物:人参 白术 茯苓 甘草",
            item_type="formula",
            score=0.95,
            rank=1,
            metadata={"name": "四君子汤"},
        )
        payload = result.to_dict()
        self.assertEqual(payload["item_id"], "formula-1")
        self.assertEqual(payload["rank"], 1)
        self.assertEqual(payload["metadata"]["name"], "四君子汤")


class TestEmbeddingService(unittest.TestCase):
    def setUp(self):
        self.formula_a = "四君子汤；药物:人参 白术 茯苓 甘草；证候:脾虚 气虚；补气健脾"
        self.formula_b = "六君子汤；药物:人参 白术 茯苓 甘草 陈皮 半夏；证候:脾虚 痰湿；补气化痰"
        self.formula_c = "麻黄汤；药物:麻黄 桂枝 杏仁 甘草；证候:风寒表实；发汗解表"
        self.syndrome_a = "脾虚证；表现:乏力 纳呆 便溏；中焦虚弱"
        self.syndrome_b = "痰湿证；表现:胸闷 痰多 倦怠；湿浊内阻"
        self.query_formula = "补气健脾方"
        self.query_syndrome = "脾虚乏力便溏"

        encoder = FakeEncoder(
            {
                self.formula_a: [1.0, 0.0, 0.0],
                self.formula_b: [0.9, 0.1, 0.0],
                self.formula_c: [0.0, 1.0, 0.0],
                self.syndrome_a: [1.0, 0.0, 0.2],
                self.syndrome_b: [0.1, 0.9, 0.0],
                self.query_formula: [1.0, 0.0, 0.0],
                self.query_syndrome: [1.0, 0.0, 0.1],
                "自定义方剂文本": [0.5, 0.5, 0.0],
                "检索自定义方剂": [0.45, 0.55, 0.0],
            }
        )
        self.service = EmbeddingService(encoder=encoder, use_faiss=False)

    def test_add_items_and_build_index(self):
        added = self.service.add_items(
            [
                EmbeddingItem(item_id="f1", text="自定义方剂文本", item_type="formula"),
            ]
        )
        self.assertEqual(added, 1)
        self.assertEqual(self.service.size, 1)
        self.assertEqual(self.service.dimension, 3)
        self.assertFalse(self.service.faiss_enabled)

    def test_build_formula_index_and_search(self):
        count = self.service.build_formula_index(
            [
                {
                    "formula_id": "f1",
                    "name": "四君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草"],
                    "indications": ["脾虚", "气虚"],
                    "description": "补气健脾",
                },
                {
                    "formula_id": "f2",
                    "name": "六君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草", "陈皮", "半夏"],
                    "indications": ["脾虚", "痰湿"],
                    "description": "补气化痰",
                },
                {
                    "formula_id": "f3",
                    "name": "麻黄汤",
                    "herbs": ["麻黄", "桂枝", "杏仁", "甘草"],
                    "indications": ["风寒表实"],
                    "description": "发汗解表",
                },
            ]
        )
        self.assertEqual(count, 3)

        results = self.service.search_similar_formulas(self.query_formula, top_k=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].item_id, "f1")
        self.assertEqual(results[0].item_type, "formula")
        self.assertGreaterEqual(results[0].score, results[1].score)

    def test_build_syndrome_index_and_search(self):
        self.service.build_syndrome_index(
            [
                {
                    "syndrome_id": "s1",
                    "name": "脾虚证",
                    "manifestations": ["乏力", "纳呆", "便溏"],
                    "description": "中焦虚弱",
                },
                {
                    "syndrome_id": "s2",
                    "name": "痰湿证",
                    "manifestations": ["胸闷", "痰多", "倦怠"],
                    "description": "湿浊内阻",
                },
            ]
        )
        results = self.service.search_similar_syndromes(self.query_syndrome, top_k=2)
        self.assertEqual(results[0].item_id, "s1")
        self.assertEqual(results[0].item_type, "syndrome")

    def test_combined_indexes_filter_by_type(self):
        self.service.build_formula_index(
            [
                {
                    "formula_id": "f1",
                    "name": "四君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草"],
                    "indications": ["脾虚", "气虚"],
                    "description": "补气健脾",
                }
            ]
        )
        self.service.build_syndrome_index(
            [
                {
                    "syndrome_id": "s1",
                    "name": "脾虚证",
                    "manifestations": ["乏力", "纳呆", "便溏"],
                    "description": "中焦虚弱",
                }
            ]
        )
        formula_results = self.service.search(self.query_formula, item_type="formula", top_k=5)
        syndrome_results = self.service.search(self.query_formula, item_type="syndrome", top_k=5)
        self.assertTrue(all(item.item_type == "formula" for item in formula_results))
        self.assertTrue(all(item.item_type == "syndrome" for item in syndrome_results))

    def test_exclude_item_id(self):
        self.service.build_formula_index(
            [
                {
                    "formula_id": "f1",
                    "name": "四君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草"],
                    "indications": ["脾虚", "气虚"],
                    "description": "补气健脾",
                },
                {
                    "formula_id": "f2",
                    "name": "六君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草", "陈皮", "半夏"],
                    "indications": ["脾虚", "痰湿"],
                    "description": "补气化痰",
                },
            ]
        )
        results = self.service.search_similar_formulas(self.query_formula, top_k=2, exclude_formula_id="f1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].item_id, "f2")

    def test_min_score_filters_results(self):
        self.service.build_formula_index(
            [
                {
                    "formula_id": "f1",
                    "name": "四君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草"],
                    "indications": ["脾虚", "气虚"],
                    "description": "补气健脾",
                },
                {
                    "formula_id": "f3",
                    "name": "麻黄汤",
                    "herbs": ["麻黄", "桂枝", "杏仁", "甘草"],
                    "indications": ["风寒表实"],
                    "description": "发汗解表",
                },
            ]
        )
        results = self.service.search_similar_formulas(self.query_formula, top_k=5, min_score=0.8)
        self.assertEqual([item.item_id for item in results], ["f1"])

    def test_stats(self):
        self.service.build_formula_index(
            [
                {
                    "formula_id": "f1",
                    "name": "四君子汤",
                    "herbs": ["人参", "白术", "茯苓", "甘草"],
                    "indications": ["脾虚", "气虚"],
                    "description": "补气健脾",
                }
            ]
        )
        self.service.build_syndrome_index(
            [
                {
                    "syndrome_id": "s1",
                    "name": "脾虚证",
                    "manifestations": ["乏力", "纳呆", "便溏"],
                    "description": "中焦虚弱",
                }
            ]
        )
        stats = self.service.stats()
        self.assertEqual(stats["size"], 2)
        self.assertEqual(stats["types"]["formula"], 1)
        self.assertEqual(stats["types"]["syndrome"], 1)

    def test_clear(self):
        self.service.add_items([EmbeddingItem(item_id="f1", text="自定义方剂文本", item_type="formula")])
        self.service.clear()
        self.assertEqual(self.service.size, 0)
        self.assertIsNone(self.service.dimension)

    def test_invalid_query_raises(self):
        with self.assertRaises(ValueError):
            self.service.search("", top_k=3)

    def test_invalid_top_k_raises(self):
        with self.assertRaises(ValueError):
            self.service.search("检索自定义方剂", top_k=0)

    def test_invalid_item_type_raises(self):
        with self.assertRaises(ValueError):
            self.service.add_items([EmbeddingItem(item_id="x", text="bad", item_type="unsupported")])

    def test_formula_item_uses_syndromes_fallback_when_indications_missing(self):
        item = {
            "formula_id": "f9",
            "name": "测试方",
            "herbs": ["黄芪"],
            "syndromes": ["气虚"],
        }
        coerced = self.service._coerce_formula_item(item)
        self.assertEqual(coerced.item_id, "f9")
        self.assertIn("药物:黄芪", coerced.text)
        self.assertIn("证候:气虚", coerced.text)

    def test_persisted_index_can_be_loaded_without_reencoding(self):
        formulas = [
            {
                "formula_id": "f1",
                "name": "四君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草"],
                "indications": ["脾虚", "气虚"],
                "description": "补气健脾",
            },
            {
                "formula_id": "f2",
                "name": "六君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草", "陈皮", "半夏"],
                "indications": ["脾虚", "痰湿"],
                "description": "补气化痰",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            service = EmbeddingService(encoder=self.service._encoder, use_faiss=False, persist_directory=tmp)
            service.build_formula_index(formulas)

            reloaded = EmbeddingService(encoder=self.service._encoder, use_faiss=False, persist_directory=tmp)
            self.assertEqual(reloaded.size, 2)
            results = reloaded.search_similar_formulas(self.query_formula, top_k=2)

        self.assertEqual(results[0].item_id, "f1")
        self.assertEqual(results[1].item_id, "f2")

    def test_build_formula_index_reuses_persisted_signature_without_encoder_call(self):
        class _CountingEncoder(FakeEncoder):
            def __init__(self, mapping):
                super().__init__(mapping)
                self.calls = 0

            def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True):
                self.calls += 1
                return super().encode(texts, normalize_embeddings=normalize_embeddings, convert_to_numpy=convert_to_numpy)

        formulas = [
            {
                "formula_id": "f1",
                "name": "四君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草"],
                "indications": ["脾虚", "气虚"],
                "description": "补气健脾",
            }
        ]
        counting_encoder = _CountingEncoder(
            {
                self.formula_a: [1.0, 0.0, 0.0],
                self.query_formula: [1.0, 0.0, 0.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            service = EmbeddingService(encoder=counting_encoder, use_faiss=False, persist_directory=tmp)
            service.build_formula_index(formulas)
            self.assertEqual(counting_encoder.calls, 1)

            reloaded = EmbeddingService(encoder=counting_encoder, use_faiss=False, persist_directory=tmp)
            reloaded.build_formula_index(formulas)

        self.assertEqual(counting_encoder.calls, 1)

    def test_persisted_index_invalidates_when_corpus_version_changes(self):
        formulas = [
            {
                "formula_id": "f1",
                "name": "四君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草"],
                "indications": ["脾虚", "气虚"],
                "description": "补气健脾",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            service = EmbeddingService(
                encoder=self.service._encoder,
                use_faiss=False,
                persist_directory=tmp,
                corpus_version="formula-corpus-v1",
            )
            service.build_formula_index(formulas)

            reloaded = EmbeddingService(
                encoder=self.service._encoder,
                use_faiss=False,
                persist_directory=tmp,
                corpus_version="formula-corpus-v2",
            )

            self.assertEqual(reloaded.size, 0)
            reloaded.build_formula_index(formulas)
            self.assertEqual(reloaded.size, 1)
            self.assertEqual(reloaded.stats()["corpus_version"], "formula-corpus-v2")


class TestEmbeddingServiceSentenceTransformersIntegration(unittest.TestCase):
    @patch("src.knowledge.embedding_service.SentenceTransformer")
    def test_uses_sentence_transformers_when_encoder_not_provided(self, mock_sentence_transformer):
        class _StubEncoder:
            def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True):
                return np.asarray([[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32)

        mock_sentence_transformer.return_value = _StubEncoder()

        service = EmbeddingService(encoder=None, use_faiss=False, model_name="demo-model")
        service.add_items([EmbeddingItem(item_id="f1", text="四君子汤", item_type="formula")])

        mock_sentence_transformer.assert_called_once_with("demo-model")
        self.assertEqual(service.size, 1)

    @patch("src.knowledge.embedding_service.SentenceTransformer", None)
    def test_missing_sentence_transformers_raises_runtime_error(self):
        service = EmbeddingService(encoder=None, use_faiss=False)
        with self.assertRaises(RuntimeError):
            service.add_items([EmbeddingItem(item_id="f1", text="四君子汤", item_type="formula")])


if __name__ == "__main__":
    unittest.main()