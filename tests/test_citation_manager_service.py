import os
import tempfile
import unittest

from src.generation import CitationManager


class TestCitationManagerLibraryService(unittest.TestCase):
    def setUp(self):
        self.manager = CitationManager({"format": "GB/T 7714-2015", "merge_duplicates": True})
        self.assertTrue(self.manager.initialize())

    def tearDown(self):
        self.manager.cleanup()

    def test_duplicate_records_are_merged_into_library(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "title": "Large Language Models for TCM Research",
                        "authors": ["Alice Smith", "Bob Chen"],
                        "year": 2024,
                        "journal": "Journal of TCM Informatics",
                    },
                    {
                        "title": "Large Language Models for TCM Research",
                        "authors": ["Alice Smith", "Bob Chen"],
                        "year": 2024,
                        "doi": "10.1000/tcm.2024.1",
                        "url": "https://example.com/paper",
                    },
                ]
            }
        )

        self.assertEqual(result["citation_count"], 1)
        self.assertEqual(result["duplicates_merged"], 1)
        self.assertEqual(result["library"]["stats"]["entry_count"], 1)
        self.assertEqual(result["entries"][0]["doi"], "10.1000/tcm.2024.1")
        self.assertIn("article", result["library"]["stats"]["by_type"])

    def test_reference_library_input_is_supported(self):
        result = self.manager.execute(
            {
                "reference_library": {
                    "records": [
                        {
                            "title": "中医证据综合研究",
                            "authors": "张三, 李四",
                            "publish_date": "2023-08-01",
                            "source": "arxiv",
                            "url": "https://arxiv.org/abs/1234.5678",
                        }
                    ]
                }
            }
        )

        self.assertEqual(result["citation_count"], 1)
        self.assertEqual(result["library"]["stats"]["by_year"]["2023"], 1)
        self.assertEqual(result["library"]["stats"]["by_source"]["arxiv"], 1)

    def test_export_outputs_writes_library_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.manager.execute(
                {
                    "records": [
                        {
                            "title": "TCM Citation Export",
                            "authors": ["Grace Hopper"],
                            "year": 2026,
                            "journal": "Custom Journal",
                        }
                    ],
                    "output_dir": tmpdir,
                    "export_outputs": True,
                    "file_stem": "citation_bundle",
                }
            )

            self.assertIn("library_json", result["output_files"])
            self.assertIn("bibtex", result["output_files"])
            self.assertIn("gbt7714", result["output_files"])
            for path in result["output_files"].values():
                self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()