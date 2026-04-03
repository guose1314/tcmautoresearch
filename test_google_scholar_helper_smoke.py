"""
Google Scholar 端到端 smoke test（真实页面抓取 + 产物断言）

说明：
- 默认使用真实 Scholar URL。
- 如网络受限/触发验证码，测试会 skip（不是 fail）。
- 运行方式：
  c:/Users/hgk/tcmautoresearch/venv/Scripts/python.exe test_google_scholar_helper_smoke.py
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.research.google_scholar_helper import run_google_scholar_related_works


class TestGoogleScholarHelperSmoke(unittest.TestCase):
    def test_live_scholar_fetch_and_artifacts(self):
        url = os.getenv(
            "SCHOLAR_SMOKE_URL",
            "https://scholar.google.com/scholar?q=large+language+model+reasoning",
        )

        with tempfile.TemporaryDirectory(prefix="scholar_smoke_") as tmp:
            out_dir = Path(tmp) / "output"
            result = run_google_scholar_related_works(
                scholar_url=url,
                output_dir=str(out_dir),
                max_papers=5,
                topic_hint="Large language model reasoning",
                target_lang="English",
                use_llm=False,
                additional_prompt="Prefer concise related works.",
            )

            if result.status != "success":
                # 真实网页抓取受网络与反爬策略影响，失败时跳过避免 CI 假阴性。
                self.skipTest(f"Live Scholar fetch unavailable: {result.error}")

            self.assertGreater(result.total_papers, 0)
            self.assertTrue(result.output_markdown)
            self.assertTrue(result.output_json)
            self.assertTrue(Path(result.output_markdown).exists())
            self.assertTrue(Path(result.output_json).exists())

            md_text = Path(result.output_markdown).read_text(encoding="utf-8")
            self.assertIn("Generated Related Works", md_text)
            self.assertIn("Citation Key:", md_text)

            payload = json.loads(Path(result.output_json).read_text(encoding="utf-8"))
            self.assertEqual(payload.get("status"), "success")
            self.assertGreater(payload.get("total_papers", 0), 0)
            papers = payload.get("papers", [])
            self.assertTrue(isinstance(papers, list) and len(papers) > 0)
            self.assertIn("author_year_citation", papers[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
