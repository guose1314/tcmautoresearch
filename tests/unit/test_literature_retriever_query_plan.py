import unittest

from src.research.literature_retriever import LiteratureRetriever


class TestLiteratureRetrieverQueryPlan(unittest.TestCase):
    def setUp(self):
        self.retriever = LiteratureRetriever({})

    def tearDown(self):
        self.retriever.close()

    def test_build_query_plan_known_source_with_fallback(self):
        plan = self.retriever._build_query_plan("pubmed", "huang qi", fallback=True)

        self.assertEqual(plan["source"], "pubmed")
        self.assertIn("term=huang+qi", plan["query_url"])
        self.assertTrue(plan["note"].endswith("（API 回退）"))

    def test_build_query_plan_unknown_source(self):
        plan = self.retriever._build_query_plan("unknown_source", "x", fallback=False)

        self.assertEqual(plan["source"], "unknown_source")
        self.assertEqual(plan["query_url"], "")
        self.assertEqual(plan["note"], "暂无检索 URL 模板。")


if __name__ == "__main__":
    unittest.main()
