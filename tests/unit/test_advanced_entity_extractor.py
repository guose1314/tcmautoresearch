import unittest
from unittest.mock import patch

from src.analysis.entity_extractor import AdvancedEntityExtractor


class _FakeLexicon:
    def __init__(self):
        self._word_types = {
            "小柴胡汤": "formula",
            "柴胡": "herb",
            "黄芩": "herb",
        }

    def get_all_words(self):
        return list(self._word_types.keys())

    def get_word_type(self, word):
        return self._word_types.get(word)

    def resolve_synonym(self, word):
        return word, self._word_types.get(word)

    def get_vocab_size(self):
        return len(self._word_types)

    def load_from_file(self, _path, _word_type="common"):
        return 0

    def export_to_jieba_format(self, _filepath, word_type="common"):
        return None


class TestAdvancedEntityExtractor(unittest.TestCase):
    def _build_module(self):
        with patch("src.analysis.entity_extractor.get_lexicon", return_value=_FakeLexicon()):
            module = AdvancedEntityExtractor()
        self.assertTrue(module.initialize())
        return module

    def test_execute_validates_processed_text(self):
        module = self._build_module()

        with self.assertRaises(ValueError):
            module.execute({})

        with self.assertRaises(ValueError):
            module.execute({"processed_text": 123})

    def test_extract_entities_prefers_longest_non_overlap(self):
        module = self._build_module()
        entities = module._extract_entities("小柴胡汤与柴胡黄芩")
        names = [item["name"] for item in entities if item["type"] != "dosage"]

        self.assertIn("小柴胡汤", names)
        self.assertIn("柴胡", names)
        self.assertIn("黄芩", names)

        # 第一处“小柴胡汤”命中后，不应在其内部重复标注“柴胡”
        first_formula = next(item for item in entities if item["name"] == "小柴胡汤")
        overlapped_herb = [
            item
            for item in entities
            if item["name"] == "柴胡"
            and first_formula["position"] <= item["position"] < first_formula["end_position"]
        ]
        self.assertEqual(overlapped_herb, [])

    def test_extract_dosages(self):
        module = self._build_module()
        dosages = module._extract_dosages("柴胡10克，黄芩三两")

        self.assertGreaterEqual(len(dosages), 2)
        self.assertTrue(any(item["name"] == "10克" for item in dosages))
        self.assertTrue(any(item["name"] == "三两" for item in dosages))

    def test_execute_output_contract(self):
        module = self._build_module()
        result = module.execute({"processed_text": "小柴胡汤10克"})

        self.assertIn("entities", result)
        self.assertIn("statistics", result)
        self.assertIn("confidence_scores", result)
        self.assertIn("average_confidence", result["confidence_scores"])


if __name__ == "__main__":
    unittest.main()
