import json
import os
import tempfile
import unittest

from src.research.ctext_corpus_collector import CTextCorpusCollector
from src.research.ctext_whitelist import build_batch_manifest, load_whitelist


class TestCTextWhitelist(unittest.TestCase):
    def test_load_whitelist_from_config_file(self):
        whitelist = load_whitelist("data/ctext_whitelist.json")

        self.assertEqual(whitelist.get("version"), "1.1.0")
        self.assertIn("groups", whitelist)
        self.assertIn("four_books", whitelist["groups"])
        self.assertIn("tcm_classics", whitelist["groups"])

    def test_build_batch_manifest_from_config_file(self):
        whitelist = load_whitelist("data/ctext_whitelist.json")
        manifest = build_batch_manifest(whitelist, ["four_books", "tcm_classics"])

        self.assertEqual(manifest["count"], 8)
        self.assertEqual(manifest["selected_groups"], ["four_books", "tcm_classics"])

        urns = [entry["urn"] for entry in manifest["entries"]]
        urls = [entry.get("url", "") for entry in manifest["entries"] if entry.get("url")]
        self.assertIn("ctp:analects", urns)
        self.assertIn("ctp:shang-han-lun/bian-mai-fa", urns)
        self.assertIn("https://ctext.org/shang-han-lun/bian-mai-fa", urls)

    def test_build_batch_manifest_skips_duplicates_and_invalid_items(self):
        whitelist = {
            "version": "test",
            "groups": {
                "g1": {
                    "name": "G1",
                    "items": [
                        {"title": "A", "urn": "ctp:a", "url": "", "priority": "high"},
                        {"title": "A-dup", "urn": "ctp:a", "url": "", "priority": "low"},
                        {"title": "B", "urn": "", "url": "https://x/b", "priority": "medium"},
                        {"title": "B-dup", "urn": "", "url": "https://x/b", "priority": "low"},
                        {"title": "empty"},
                        "invalid",
                    ],
                }
            },
        }

        manifest = build_batch_manifest(whitelist, ["g1"])

        self.assertEqual(manifest["count"], 2)
        self.assertEqual([item["title"] for item in manifest["entries"]], ["A", "B"])

    def test_generate_manifest_and_write_output_file(self):
        collector = CTextCorpusCollector({"request_interval_sec": 0, "retry_count": 0})
        self.assertTrue(collector.initialize())

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_file = os.path.join(tmpdir, "manifest.json")
                manifest = collector.generate_batch_collection_manifest(
                    selected_groups=["five_classics"],
                    whitelist_path="data/ctext_whitelist.json",
                    output_file=output_file
                )

                self.assertEqual(manifest["count"], 5)
                self.assertTrue(os.path.exists(output_file))

                with open(output_file, "r", encoding="utf-8") as f:
                    saved_manifest = json.load(f)

                self.assertEqual(saved_manifest["selected_groups"], ["five_classics"])
                self.assertEqual(saved_manifest["count"], 5)
        finally:
            collector.cleanup()


if __name__ == "__main__":
    unittest.main()
