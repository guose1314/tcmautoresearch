import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.collector.literature_retriever import LiteratureRecord, LiteratureRetriever


class TestLiteratureRetrieverAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.retriever = LiteratureRetriever({"request_interval_sec": 0, "retry_count": 0})

    async def asyncTearDown(self):
        self.retriever.close()

    async def test_search_async_falls_back_to_query_plan_on_api_error(self):
        async def fake_search_open_api_async(*args, **kwargs):
            source = kwargs["source"]
            if source == "pubmed":
                return [
                    LiteratureRecord(
                        source="pubmed",
                        title="Test Title",
                        authors=["A"],
                        year=2024,
                        doi="10.1000/test",
                        url="https://pubmed.ncbi.nlm.nih.gov/1/",
                        abstract="abstract",
                        citation_count=5,
                        external_id="1",
                    )
                ]
            raise RuntimeError("429 rate limited")

        with patch.object(
            self.retriever,
            "_search_open_api_async",
            new=AsyncMock(side_effect=fake_search_open_api_async),
        ):
            result = await self.retriever.search_async(
                query="huang qi",
                sources=["pubmed", "semantic_scholar", "google_scholar"],
                max_results_per_source=3,
            )

        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["source"], "pubmed")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["source"], "semantic_scholar")
        self.assertEqual(len(result["query_plans"]), 2)
        plan_sources = {item["source"] for item in result["query_plans"]}
        self.assertIn("semantic_scholar", plan_sources)
        self.assertIn("google_scholar", plan_sources)

    async def test_request_json_async_retries_then_succeeds(self):
        self.retriever.retry_count = 1

        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True}

        client = AsyncMock()
        client.get = AsyncMock(side_effect=[RuntimeError("boom"), response])

        result = await self.retriever._request_json_async(client, "https://example.com", {"q": "x"})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(client.get.await_count, 2)


class TestLiteratureRetrieverSyncWrapper(unittest.TestCase):
    def test_sync_search_delegates_to_async(self):
        retriever = LiteratureRetriever({})
        expected = {"query": "q", "records": [], "query_plans": [], "source_stats": {}, "errors": []}

        with patch.object(retriever, "search_async", new=AsyncMock(return_value=expected)) as mock_search_async:
            result = retriever.search("q")

        self.assertEqual(result, expected)
        mock_search_async.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()