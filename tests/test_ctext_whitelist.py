import json
import os
import tempfile
import unittest

from src.collector.ctext_corpus_collector import CTextCorpusCollector
from src.collector.ctext_whitelist import build_batch_manifest, load_whitelist


class TestCTextWhitelist(unittest.TestCase):
    def test_load_whitelist_from_config_file(self):
        whitelist = load_whitelist("data/ctext_whitelist.json")

        self.assertEqual(whitelist.get("version"), "1.2.0")
        self.assertIn("groups", whitelist)
        self.assertIn("four_books", whitelist["groups"])
        self.assertIn("tcm_classics", whitelist["groups"])
        first_item = whitelist["groups"]["tcm_classics"]["items"][0]
        self.assertEqual(first_item["catalog_id"], "ctp:huangdi-neijing/shang-gu-tian-zhen-lun")
        self.assertEqual(first_item["edition"], "Chinese Text Project 数字整理本")
        self.assertEqual(first_item["work_title"], "黄帝内经")
        self.assertEqual(first_item["fragment_title"], "上古天真论")

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
        tcm_entry = next(entry for entry in manifest["entries"] if entry["urn"] == "ctp:shang-han-lun/bian-mai-fa")
        self.assertEqual(tcm_entry["catalog_id"], "ctp:shang-han-lun/bian-mai-fa")
        self.assertEqual(tcm_entry["author"], "张仲景")
        self.assertEqual(tcm_entry["dynasty"], "东汉")
        self.assertEqual(tcm_entry["version_metadata"]["work_title"], "伤寒论")

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
        self.assertEqual(manifest["entries"][0]["catalog_id"], "ctp:a")

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
                self.assertIn("catalog_id", saved_manifest["entries"][0])
        finally:
            collector.cleanup()


if __name__ == "__main__":
    unittest.main()
