import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.research.ctext_corpus_collector import CTextCorpusCollector


class TestCTextCorpusCollector(unittest.TestCase):
    def setUp(self):
        self.collector = CTextCorpusCollector(
            {
                "request_interval_sec": 0,
                "retry_count": 0,
            }
        )
        self.assertTrue(self.collector.initialize())

    def tearDown(self):
        self.collector.cleanup()

    @patch("src.research.ctext_corpus_collector.requests.Session.get")
    def test_collect_urn_recursive(self, mock_get):
        def side_effect(url, params=None, timeout=None):
            endpoint = url.split("/")[-1]
            response = MagicMock()
            response.raise_for_status.return_value = None

            if endpoint == "gettext":
                urn = params.get("urn")
                if urn == "ctp:analects":
                    payload = {
                        "title": "论语",
                        "subsections": ["ctp:analects/xue-er"]
                    }
                elif urn == "ctp:analects/xue-er":
                    payload = {
                        "title": "学而",
                        "fulltext": ["学而时习之，不亦说乎。"]
                    }
                else:
                    payload = {"title": "unknown", "fulltext": []}
            elif endpoint == "readlink":
                payload = {"urn": "ctp:analects"}
            elif endpoint == "getstatus":
                payload = {"loggedin": False, "subscriber": False}
            else:
                payload = {}

            response.json.return_value = payload
            return response

        mock_get.side_effect = side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.collector.execute(
                {
                    "ctext_urls": ["https://ctext.org/analects"],
                    "recurse": True,
                    "output_dir": tmpdir,
                    "save_to_disk": True
                }
            )

            self.assertEqual(result["source"], "ctext")
            self.assertEqual(result["seed_urns"], ["ctp:analects"])
            self.assertEqual(result["stats"]["document_count"], 1)
            self.assertEqual(result["stats"]["chapter_count"], 2)
            self.assertGreater(result["stats"]["char_count"], 0)

            root = result["documents"][0]
            self.assertEqual(root["urn"], "ctp:analects")
            self.assertEqual(root["title"], "论语")
            self.assertEqual(root["subsections"], ["ctp:analects/xue-er"])
            self.assertEqual(len(root["children"]), 1)
            self.assertEqual(root["children"][0]["title"], "学而")

            output_file = result.get("output_file")
            self.assertTrue(output_file)
            self.assertTrue(os.path.exists(output_file))
            with open(output_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self.assertIn("documents", payload)


if __name__ == "__main__":
    unittest.main()
