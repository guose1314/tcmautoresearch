import unittest

from src.collector import Normalizer
from src.collector.corpus_bundle import CorpusBundle, CorpusDocument


class TestNormalizerTextPayload(unittest.TestCase):
    def setUp(self):
        self.normalizer = Normalizer({"convert_mode": ""})
        self.assertTrue(self.normalizer.initialize())

    def tearDown(self):
        self.normalizer.cleanup()

    def test_normalize_raw_text_and_metadata_aliases(self):
        result = self.normalizer.execute(
            {
                "raw_text": "黃芪\x00  主治氣虛\n\n\nformulas",
                "metadata": {
                    "author": "張三, 李四",
                    "file_path": "./data/huangqi.txt",
                    "format": "TXT",
                    "published": "2024-03-01",
                },
                "title": "黃芪論",
            }
        )

        self.assertTrue(result["success"])
        self.assertNotIn("\x00", result["normalized_text"])
        self.assertIn("黄芪", result["normalized_text"])
        self.assertIn("formula", result["normalized_text"])
        self.assertEqual(result["metadata"]["authors"], ["張三", "李四"])
        self.assertEqual(result["metadata"]["source_file"], "./data/huangqi.txt")
        self.assertEqual(result["metadata"]["source_type"], "local")
        self.assertEqual(result["metadata"]["year"], "2024")
        self.assertIn("黃芪", result["term_mappings"])

    def test_normalize_bytes_uses_encoding_unification(self):
        payload = "當歸補血湯".encode("gb18030")

        result = self.normalizer.execute({"raw_text": payload})

        self.assertTrue(result["success"])
        self.assertIn("当归补血汤", result["normalized_text"])
        self.assertIn(result["metadata"]["encoding"], {"gb18030", "gb2312", "gbk", "utf-8", "utf-8-sig"})


class TestNormalizerDocumentAndBundle(unittest.TestCase):
    def setUp(self):
        self.normalizer = Normalizer({"convert_mode": ""})
        self.assertTrue(self.normalizer.initialize())

    def tearDown(self):
        self.normalizer.cleanup()

    def test_normalize_single_document(self):
        document = {
            "doc_id": "doc-1",
            "title": "金匱要略",
            "text": "金匱要略\n\n證候辨析",
            "source_type": "TXT",
            "source_ref": "./data/jinkui.txt",
            "language": "zh",
            "metadata": {"author": "佚名", "tags": "傷寒論, 方證"},
            "collected_at": "2026-03-31T00:00:00",
            "children": [],
        }

        result = self.normalizer.execute({"document": document})
        normalized_document = result["document"]

        self.assertTrue(result["success"])
        self.assertEqual(normalized_document["source_type"], "local")
        self.assertEqual(normalized_document["title"], "金匮要略")
        self.assertIn("证候辨析", normalized_document["text"])
        self.assertEqual(normalized_document["metadata"]["authors"], ["佚名"])
        self.assertEqual(normalized_document["metadata"]["keywords"], ["伤寒论", "方证"])
        self.assertIn("normalization", normalized_document["metadata"])

    def test_normalize_bundle_updates_stats_and_documents(self):
        bundle = CorpusBundle(
            bundle_id="bundle-1",
            sources=["pdf"],
            documents=[
                CorpusDocument(
                    doc_id="pdf_001",
                    title="傷寒論",
                    text="黃芪主治\n\n\n氣虛。",
                    source_type="pdf",
                    source_ref="./output/a.pdf",
                    language="zh",
                    metadata={"creator": "張仲景", "format": "pdf"},
                    collected_at="2026-03-31T00:00:00",
                )
            ],
            collected_at="2026-03-31T00:00:00",
            stats={"total_documents": 1, "total_chars": 9},
            errors=[],
        )

        result = self.normalizer.execute(bundle.to_dict())

        self.assertEqual(result["stats"]["normalized_documents"], 1)
        self.assertGreaterEqual(result["stats"]["term_mapping_count"], 1)
        self.assertEqual(result["documents"][0]["title"], "伤寒论")
        self.assertEqual(result["documents"][0]["metadata"]["authors"], ["张仲景"])
        self.assertEqual(result["documents"][0]["metadata"]["source_type"], "pdf")


if __name__ == "__main__":
    unittest.main()