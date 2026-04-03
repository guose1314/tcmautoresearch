"""literature_retriever.py 覆盖率补齐测试 — 目标 ≥ 90%。

覆盖 PubMed / Semantic Scholar / PLOS / arXiv 解析链、重试机制、查询计划生成。
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.collector.literature_retriever import (
    QUERY_PLAN_TEMPLATES,
    LiteratureRecord,
    LiteratureRetriever,
)


class TestLiteratureRetrieverInit(unittest.TestCase):
    def test_default_config(self):
        lr = LiteratureRetriever()
        self.assertEqual(lr.timeout_sec, 20.0)
        self.assertEqual(lr.retry_count, 2)
        self.assertIn("User-Agent", lr.headers)

    def test_custom_config(self):
        lr = LiteratureRetriever({"timeout_sec": 5, "retry_count": 0, "request_interval_sec": 0})
        self.assertEqual(lr.timeout_sec, 5.0)
        self.assertEqual(lr.retry_count, 0)

    def test_close_is_noop(self):
        lr = LiteratureRetriever()
        self.assertIsNone(lr.close())


class TestBuildQueryPlan(unittest.TestCase):
    def setUp(self):
        self.lr = LiteratureRetriever()

    def test_known_source(self):
        plan = self.lr._build_query_plan("pubmed", "黄芪")
        self.assertEqual(plan["source"], "pubmed")
        self.assertIn("pubmed.ncbi.nlm.nih.gov", plan["query_url"])

    def test_fallback_source(self):
        plan = self.lr._build_query_plan("pubmed", "黄芪", fallback=True)
        self.assertIn("API 回退", plan["note"])

    def test_unknown_source(self):
        plan = self.lr._build_query_plan("unknown_db", "test")
        self.assertEqual(plan["query_url"], "")
        self.assertIn("暂无", plan["note"])


class TestBuildPubmedRecords(unittest.TestCase):
    def setUp(self):
        self.lr = LiteratureRetriever()

    def test_normal_records(self):
        result_obj = {
            "12345": {
                "title": "黄芪药理研究",
                "authors": [{"name": "张三"}, {"name": "李四"}],
                "pubdate": "2024 Jan",
                "articleids": [{"idtype": "doi", "value": "10.1234/test"}],
            }
        }
        records = self.lr._build_pubmed_records(["12345"], result_obj)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "黄芪药理研究")
        self.assertEqual(records[0].authors, ["张三", "李四"])
        self.assertEqual(records[0].year, 2024)
        self.assertEqual(records[0].doi, "10.1234/test")

    def test_empty_item(self):
        records = self.lr._build_pubmed_records(["99999"], {"99999": {}})
        self.assertEqual(len(records), 0)

    def test_missing_id(self):
        records = self.lr._build_pubmed_records(["11111"], {})
        self.assertEqual(len(records), 0)

    def test_no_authors(self):
        result_obj = {"1": {"title": "T", "authors": [], "pubdate": "2020"}}
        records = self.lr._build_pubmed_records(["1"], result_obj)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].authors, [])

    def test_no_doi(self):
        result_obj = {"1": {"title": "T", "articleids": []}}
        r = self.lr._build_pubmed_records(["1"], result_obj)
        self.assertEqual(r[0].doi, "")

    def test_year_invalid(self):
        result_obj = {"1": {"title": "T", "pubdate": "unknown"}}
        r = self.lr._build_pubmed_records(["1"], result_obj)
        self.assertIsNone(r[0].year)

    def test_author_missing_name(self):
        result_obj = {"1": {"title": "T", "authors": [{"affiliation": "A"}, {"name": "B"}]}}
        r = self.lr._build_pubmed_records(["1"], result_obj)
        self.assertEqual(r[0].authors, ["B"])


class TestBuildPubmedParams(unittest.TestCase):
    def test_with_email_and_api_key(self):
        lr = LiteratureRetriever()
        params = lr._build_pubmed_params({"term": "q"}, "a@b.com", "key123")
        self.assertEqual(params["email"], "a@b.com")
        self.assertEqual(params["api_key"], "key123")
        self.assertEqual(params["db"], "pubmed")

    def test_without_email(self):
        lr = LiteratureRetriever()
        params = lr._build_pubmed_params({"term": "q"}, "", "")
        self.assertNotIn("email", params)
        self.assertNotIn("api_key", params)


class TestSearchAsync(unittest.TestCase):
    """异步搜索全流程测试。"""

    def test_search_offline_plan_only(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        result = lr.search("黄芪", sources=["pubmed", "google_scholar"], offline_plan_only=True)
        self.assertTrue(result["offline_plan_only"])
        self.assertEqual(len(result["records"]), 0)
        self.assertTrue(len(result["query_plans"]) >= 2)

    def test_search_unsupported_source(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        result = lr.search("test", sources=["nonexistent_db"], offline_plan_only=True)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["error"], "unsupported_source")

    def test_search_restricted_sources(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        result = lr.search("test", sources=["cochrane", "embase"], offline_plan_only=False)
        self.assertEqual(len(result["query_plans"]), 2)

    def test_search_default_sources(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        result = lr.search("test", sources=None, offline_plan_only=True)
        self.assertIn("pubmed", result["sources"])
        self.assertIn("google_scholar", result["sources"])

    def test_search_api_exception_generates_fallback(self):
        lr = LiteratureRetriever({"request_interval_sec": 0, "retry_count": 0, "timeout_sec": 1})

        async def _mock_search(*args, **kwargs):
            raise httpx.ConnectError("fail")

        with patch.object(lr, "_search_open_api_async", side_effect=_mock_search):
            result = lr.search("黄芪", sources=["pubmed"])
            self.assertEqual(len(result["errors"]), 1)
            # Should generate a fallback query plan
            fallback_plans = [p for p in result["query_plans"] if "API 回退" in p.get("note", "")]
            self.assertTrue(len(fallback_plans) >= 1)


class TestPubmedAsyncSearch(unittest.TestCase):
    def test_pubmed_empty_idlist(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"esearchresult": {"idlist": []}}
            mock_response.raise_for_status = MagicMock()
            mock_response.text = ""
            mock_client.get.return_value = mock_response
            records = await lr._search_pubmed_async(mock_client, "nothing", 10, "", "")
            return records

        records = asyncio.run(_run())
        self.assertEqual(len(records), 0)

    def test_pubmed_with_results(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            call_count = [0]

            async def _get(url, params=None):
                call_count[0] += 1
                mock_resp = MagicMock()
                mock_resp.raise_for_status = MagicMock()
                if call_count[0] == 1:  # esearch
                    mock_resp.json.return_value = {"esearchresult": {"idlist": ["100"]}}
                else:  # esummary
                    mock_resp.json.return_value = {"result": {"100": {"title": "Test", "pubdate": "2024"}}}
                return mock_resp

            mock_client.get = _get
            return await lr._search_pubmed_async(mock_client, "test", 10, "", "")

        records = asyncio.run(_run())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Test")


class TestSemanticScholarAsync(unittest.TestCase):
    def test_parse_semantic_scholar_response(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "data": [
                    {
                        "title": "TCM Review",
                        "authors": [{"name": "Author A"}],
                        "year": 2023,
                        "abstract": "A review.",
                        "url": "http://example.com",
                        "citationCount": 42,
                        "externalIds": {"DOI": "10.1/a", "CorpusId": "123"},
                    }
                ]
            }
            mock_client.get.return_value = mock_resp
            return await lr._search_semantic_scholar_async(mock_client, "tcm", 10)

        records = asyncio.run(_run())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "semantic_scholar")
        self.assertEqual(records[0].doi, "10.1/a")
        self.assertEqual(records[0].citation_count, 42)

    def test_empty_response(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {}
            mock_client.get.return_value = mock_resp
            return await lr._search_semantic_scholar_async(mock_client, "nothing", 10)

        records = asyncio.run(_run())
        self.assertEqual(len(records), 0)


class TestPlosOneAsync(unittest.TestCase):
    def test_parse_plos_response(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "response": {
                    "docs": [
                        {
                            "id": "10.1371/test",
                            "title": ["PLOS Title"],
                            "author": ["Auth1", "Auth2"],
                            "abstract": ["Abstract text"],
                            "publication_date": "2022-05-01T00:00:00Z",
                        }
                    ]
                }
            }
            mock_client.get.return_value = mock_resp
            return await lr._search_plos_one_async(mock_client, "test", 10)

        records = asyncio.run(_run())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "plos_one")
        self.assertEqual(records[0].title, "PLOS Title")
        self.assertEqual(records[0].year, 2022)
        self.assertEqual(records[0].abstract, "Abstract text")

    def test_plos_title_as_string(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "response": {
                    "docs": [{"id": "x", "title": "String Title", "abstract": "Abs"}]
                }
            }
            mock_client.get.return_value = mock_resp
            return await lr._search_plos_one_async(mock_client, "test", 10)

        records = asyncio.run(_run())
        self.assertEqual(records[0].title, "String Title")
        self.assertEqual(records[0].abstract, "Abs")


class TestArxivAsync(unittest.TestCase):
    def test_parse_arxiv_xml(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>中医方剂 AI 分析</title>
    <summary>Method study</summary>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Author X</name></author>
    <author><name>Author Y</name></author>
  </entry>
</feed>"""

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = xml_response
            mock_client.get.return_value = mock_resp
            return await lr._search_arxiv_async(mock_client, "test", 10)

        records = asyncio.run(_run())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "arxiv")
        self.assertEqual(records[0].title, "中医方剂 AI 分析")
        self.assertEqual(records[0].year, 2024)
        self.assertEqual(records[0].authors, ["Author X", "Author Y"])
        self.assertEqual(records[0].external_id, "2401.12345v1")

    def test_arxiv_missing_fields(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})
        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Title Only</title>
  </entry>
</feed>"""

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = xml_response
            mock_client.get.return_value = mock_resp
            return await lr._search_arxiv_async(mock_client, "test", 10)

        records = asyncio.run(_run())
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].year)
        self.assertEqual(records[0].authors, [])


class TestRequestRetry(unittest.TestCase):
    def test_retry_exhaustion_raises(self):
        lr = LiteratureRetriever({"retry_count": 1, "request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("fail")
            with self.assertRaises(RuntimeError) as ctx:
                await lr._request_json_async(mock_client, "http://example.com", {})
            self.assertIn("request failed", str(ctx.exception))

        asyncio.run(_run())

    def test_request_text_retry_exhaustion(self):
        lr = LiteratureRetriever({"retry_count": 1, "request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("fail")
            with self.assertRaises(RuntimeError):
                await lr._request_text_async(mock_client, "http://example.com", {})

        asyncio.run(_run())

    def test_request_interval_sleep(self):
        lr = LiteratureRetriever({"retry_count": 0, "request_interval_sec": 0.01})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"data": "ok"}
            mock_client.get.return_value = mock_resp
            result = await lr._request_json_async(mock_client, "http://example.com", {})
            self.assertEqual(result["data"], "ok")

        asyncio.run(_run())


class TestRunCoroutine(unittest.TestCase):
    def test_run_coroutine_no_running_loop(self):
        lr = LiteratureRetriever()

        async def _coro():
            return 42

        result = lr._run_coroutine(_coro())
        self.assertEqual(result, 42)

    def test_search_open_api_router(self):
        lr = LiteratureRetriever({"request_interval_sec": 0})

        async def _run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {"esearchresult": {"idlist": []}}
            mock_client.get.return_value = mock_resp
            # pubmed path
            r = await lr._search_open_api_async(mock_client, "pubmed", "q", 5, "", "")
            self.assertEqual(r, [])
            # unsupported path
            r = await lr._search_open_api_async(mock_client, "unknown_source", "q", 5, "", "")
            self.assertEqual(r, [])

        asyncio.run(_run())


class TestLiteratureRecord(unittest.TestCase):
    def test_dataclass_fields(self):
        rec = LiteratureRecord(
            source="pubmed", title="T", authors=["A"], year=2024,
            doi="10.1/a", url="http://example.com", abstract="abs",
            citation_count=5, external_id="123"
        )
        self.assertEqual(rec.source, "pubmed")
        self.assertEqual(rec.citation_count, 5)


if __name__ == "__main__":
    unittest.main()
