import unittest
from unittest.mock import patch

from src.analysis.philology_service import PhilologyService


class _FakeLexicon:
    def __init__(self):
        self._mapping = {
            "黄芪": ("黄芪", "herb"),
            "黄耆": ("黄芪", "herb"),
            "当归": ("当归", "herb"),
            "补血汤": ("补血汤", "formula"),
        }

    def resolve_synonym(self, word):
        return self._mapping.get(word, (word, None))

    def get_all_words(self):
        return set(self._mapping.keys())


class TestPhilologyService(unittest.TestCase):
    @patch("src.analysis.philology_service.get_lexicon", return_value=_FakeLexicon())
    def test_standardizes_terms_and_builds_collation_notes(self, _mock_lexicon):
        service = PhilologyService(
            {
                "max_recognized_terms": 6,
                "max_collation_diffs": 4,
                "terminology_standards": [
                    {
                        "canonical": "黄芪",
                        "variants": ["黃芪", "黃耆"],
                        "category": "herb",
                        "note": "药名统一按通行简体处理",
                    }
                ],
                "collation_entry_rules": [
                    {
                        "name": "huangqi_variant",
                        "match_terms": ["黃芪", "黃耆"],
                        "judgement": "异体字通用",
                        "note": "此处属字形异写，不改义项。",
                    }
                ],
            }
        )

        self.assertTrue(service.initialize())
        try:
            result = service.execute(
                {
                    "raw_text": "黃芪當歸補血湯主治血虛。",
                    "metadata": {"title": "补血汤"},
                    "parallel_versions": [
                        {
                            "title": "补血汤宋本",
                            "urn": "doc:2",
                            "text": "黃耆當歸補血湯主治血虚。",
                        }
                    ],
                }
            )
        finally:
            service.cleanup()

        self.assertIn("黄芪", result["raw_text"])
        self.assertIn("当归", result["raw_text"])
        self.assertIn("补血汤", result["raw_text"])

        philology = result["philology"]
        term_standardization = philology["term_standardization"]
        self.assertGreaterEqual(term_standardization["recognized_term_count"], 2)
        self.assertGreaterEqual(term_standardization["orthographic_variant_count"], 1)

        glossary_terms = {item["term"] for item in term_standardization["glossary_notes"]}
        self.assertIn("黄芪", glossary_terms)
        self.assertIn("当归", glossary_terms)
        self.assertIn("补血汤", glossary_terms)

        terminology_table = term_standardization["terminology_standard_table"]
        self.assertGreaterEqual(term_standardization["terminology_standard_table_count"], 2)
        huangqi_row = next(item for item in terminology_table if item["canonical"] == "黄芪")
        self.assertIn("黃芪", huangqi_row["observed_forms"])
        self.assertIn("黃耆", huangqi_row["configured_variants"])
        self.assertTrue(any("药名统一按通行简体处理" in note for note in huangqi_row["notes"]))

        version_collation = philology["version_collation"]
        self.assertEqual(version_collation["witness_count"], 1)
        self.assertGreaterEqual(version_collation["difference_count"], 1)
        self.assertGreaterEqual(version_collation["collation_entry_count"], 1)
        self.assertEqual(version_collation["collation_entries"][0]["judgement"], "异体字通用")
        self.assertIn("不改义项", version_collation["collation_entries"][0]["note"])

        fragment_reconstruction = philology["fragment_reconstruction"]
        self.assertGreaterEqual(fragment_reconstruction["fragment_candidate_count"], 1)
        self.assertEqual(fragment_reconstruction["lost_text_candidate_count"], 0)
        self.assertEqual(fragment_reconstruction["citation_source_candidate_count"], 0)
        self.assertIn("fragment_candidate_id", fragment_reconstruction["fragment_candidates"][0])
        self.assertIn("reconstruction_basis", fragment_reconstruction["fragment_candidates"][0])

        assets = philology["philology_assets"]
        self.assertEqual(assets["asset_count"], 4)
        self.assertEqual(assets["annotation_report"]["terminology_standard_table_count"], term_standardization["terminology_standard_table_count"])
        self.assertEqual(len(assets["terminology_standard_table"]), term_standardization["terminology_standard_table_count"])
        self.assertEqual(len(assets["collation_entries"]), version_collation["collation_entry_count"])
        self.assertEqual(len(assets["fragment_candidates"]), fragment_reconstruction["fragment_candidate_count"])
        self.assertEqual(assets["annotation_report"]["fragment_candidate_count"], fragment_reconstruction["fragment_candidate_count"])
        self.assertTrue(any("版本对勘" in note for note in result["philology_notes"]))
        self.assertTrue(any("辑佚候选" in note for note in result["philology_notes"]))
