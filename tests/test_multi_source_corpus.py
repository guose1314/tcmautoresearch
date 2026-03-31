import unittest

from src.collector.multi_source_corpus import (
    build_source_collection_plan,
    build_witnesses_from_records,
    cross_validate_witnesses,
    load_source_registry,
    recognize_classical_format,
)


class TestMultiSourceCorpus(unittest.TestCase):
    def test_load_registry_has_ten_sources(self):
        registry = load_source_registry("data/corpus_source_registry.json")
        self.assertEqual(len(registry.get("sources", [])), 10)

    def test_format_recognition(self):
        self.assertEqual(recognize_classical_format(file_name="chapter.tei.xml"), "tei_xml")
        self.assertEqual(recognize_classical_format(file_name="scan.djvu"), "djvu")
        self.assertEqual(
            recognize_classical_format(content_type="application/pdf", file_name="ancient-book"),
            "pdf"
        )

    def test_format_recognition_by_sample_and_media_type(self):
        self.assertEqual(
            recognize_classical_format(content_type="application/xml", sample_text="<TEI><teiHeader>...</teiHeader></TEI>"),
            "tei_xml",
        )
        self.assertEqual(
            recognize_classical_format(content_type="application/xml", sample_text="<root>plain xml</root>"),
            "xml",
        )
        self.assertEqual(recognize_classical_format(sample_text="{"), "json")

    def test_cross_validation(self):
        witnesses = build_witnesses_from_records(
            [
                {
                    "source_id": "ctext",
                    "title": "伤寒论·辨脉法",
                    "text": "伤寒三日，阳明脉大。"
                },
                {
                    "source_id": "kanripo",
                    "title": "伤寒论·辨脉法",
                    "text": "伤寒三日，阳明脉大。"
                },
                {
                    "source_id": "wikisource_zh",
                    "title": "伤寒论·辨脉法",
                    "text": "伤寒三日，阳明脉浮。"
                }
            ]
        )
        result = cross_validate_witnesses(witnesses, similarity_threshold=0.8)
        self.assertEqual(result["witness_count"], 3)
        self.assertGreaterEqual(result["consistency_score"], 0.8)
        self.assertTrue(result["high_consistency_pairs"])

    def test_collection_plan(self):
        plan = build_source_collection_plan("黄帝内经", "data/corpus_source_registry.json")
        self.assertEqual(plan["route_count"], 10)
        self.assertEqual(plan["title"], "黄帝内经")


if __name__ == "__main__":
    unittest.main()
