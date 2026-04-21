"""
文献检索聚合模块。

支持：
- 开放 API 直连：PubMed/MEDLINE API, Semantic Scholar, PLOS ONE, arXiv
- 检索入口生成：bioRxiv(ioRxiv), Google Scholar, Cochrane, Embase, Scopus,
  Web of Science, Lexicomp, ClinicalKey
"""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Awaitable, Dict, List, Optional

import httpx

from src.common.retry_utils import retry

PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
PLOS_SEARCH_API = "https://api.plos.org/search"
ARXIV_API = "https://export.arxiv.org/api/query"

QUERY_PLAN_TEMPLATES: Dict[str, Dict[str, str]] = {
    "pubmed": {
        "query_url": "https://pubmed.ncbi.nlm.nih.gov/?term={q}",
        "note": "PubMed 网页检索入口",
    },
    "medline_api": {
        "query_url": "https://pubmed.ncbi.nlm.nih.gov/?term={q}",
        "note": "PubMed 网页检索入口",
    },
    "semantic_scholar": {
        "query_url": "https://www.semanticscholar.org/search?q={q}",
        "note": "Semantic Scholar 网页检索入口，常见限流可改走网页查询",
    },
    "plos_one": {
        "query_url": "https://journals.plos.org/plosone/search?q={q}",
        "note": "PLOS ONE 网页检索入口",
    },
    "arxiv": {
        "query_url": "https://arxiv.org/search/?query={q}&searchtype=all",
        "note": "arXiv 网页检索入口",
    },
    "google_scholar": {
        "query_url": "https://scholar.google.com/scholar?q={q}",
        "note": "Google Scholar 无稳定官方开放 API，建议使用页面检索或合规代理服务。",
    },
    "iorxiv": {
        "query_url": "https://www.biorxiv.org/search/{q}%20numresults%3A50%20sort%3Arelevance-rank",
        "note": "bioRxiv/ioRxiv 推荐使用网页检索或机构提供的数据接口。",
    },
    "cochrane": {
        "query_url": "https://www.cochranelibrary.com/advanced-search?text={q}",
        "note": "Cochrane Library 多数内容需机构订阅。",
    },
    "embase": {
        "query_url": "https://www.embase.com/search/results?query={q}",
        "note": "Embase 属付费数据库，通常需机构账号。",
    },
    "scopus": {
        "query_url": "https://www.scopus.com/results/results.uri?query={q}",
        "note": "Scopus API 需 Elsevier 开发者密钥与订阅授权。",
    },
    "web_of_science": {
        "query_url": "https://www.webofscience.com/wos/woscc/basic-search?search_mode=GeneralSearch&q={q}",
        "note": "Web of Science 访问通常需要机构订阅。",
    },
    "lexicomp": {
        "query_url": "https://online.lexi.com/lco/action/search?query={q}",
        "note": "Lexicomp 是临床决策支持平台，需要授权账号。",
    },
    "clinicalkey": {
        "query_url": "https://www.clinicalkey.com/#!/search/{q}",
        "note": "ClinicalKey 通常需要机构订阅。",
    },
}


@dataclass
class LiteratureRecord:
    source: str
    title: str
    authors: List[str]
    year: Optional[int]
    doi: str
    url: str
    abstract: str
    citation_count: Optional[int]
    external_id: str


class LiteratureRetriever:
    """跨来源文献检索器。"""

    # 用户请求覆盖的来源统一定义
    SUPPORTED_SOURCES: Dict[str, Dict[str, str]] = {
        "pubmed": {"mode": "open_api", "name": "PubMed"},
        "medline_api": {"mode": "open_api", "name": "PubMed/MEDLINE API"},
        "semantic_scholar": {"mode": "open_api", "name": "Semantic Scholar"},
        "plos_one": {"mode": "open_api", "name": "PLOS ONE"},
        "arxiv": {"mode": "open_api", "name": "arXiv"},
        "iorxiv": {"mode": "query_link", "name": "bioRxiv / ioRxiv"},
        "google_scholar": {"mode": "query_link", "name": "Google Scholar"},
        "cochrane": {"mode": "restricted", "name": "Cochrane Library"},
        "embase": {"mode": "restricted", "name": "Embase"},
        "scopus": {"mode": "restricted", "name": "Scopus"},
        "web_of_science": {"mode": "restricted", "name": "Web of Science"},
        "lexicomp": {"mode": "restricted", "name": "Lexicomp"},
        "clinicalkey": {"mode": "restricted", "name": "ClinicalKey"},
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.timeout_sec = float(self.config.get("timeout_sec", 20))
        self.retry_count = int(self.config.get("retry_count", 2))
        self.request_interval_sec = float(self.config.get("request_interval_sec", 0.2))
        self.max_concurrent_sources = int(self.config.get("max_concurrent_sources", 4))
        self.headers = {
            "User-Agent": self.config.get(
                "user_agent",
                "TCM-AutoResearch-LiteratureRetriever/1.0 (mailto:research@example.com)",
            )
        }

    def close(self) -> None:
        return None

    def search(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        max_results_per_source: int = 10,
        pubmed_email: str = "",
        pubmed_api_key: str = "",
        offline_plan_only: bool = False,
    ) -> Dict[str, Any]:
        return self._run_coroutine(
            self.search_async(
                query=query,
                sources=sources,
                max_results_per_source=max_results_per_source,
                pubmed_email=pubmed_email,
                pubmed_api_key=pubmed_api_key,
                offline_plan_only=offline_plan_only,
            )
        )

    async def search_async(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        max_results_per_source: int = 10,
        pubmed_email: str = "",
        pubmed_api_key: str = "",
        offline_plan_only: bool = False,
    ) -> Dict[str, Any]:
        source_list = sources or list(self.SUPPORTED_SOURCES.keys())
        normalized_sources = [s.strip().lower() for s in source_list if s and s.strip()]

        open_api_results: Dict[str, List[LiteratureRecord]] = {}
        query_plans: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        async with self._create_async_client() as client:
            pending_sources: List[str] = []
            tasks: Dict[str, asyncio.Task[List[LiteratureRecord]]] = {}
            semaphore = asyncio.Semaphore(max(1, self.max_concurrent_sources))

            for source in normalized_sources:
                info = self.SUPPORTED_SOURCES.get(source)
                if not info:
                    errors.append({"source": source, "error": "unsupported_source"})
                    continue

                mode = info["mode"]
                if mode == "open_api" and not offline_plan_only:
                    pending_sources.append(source)
                    tasks[source] = asyncio.create_task(
                        self._search_open_api_with_semaphore(
                            semaphore=semaphore,
                            client=client,
                            source=source,
                            query=query,
                            max_results=max_results_per_source,
                            pubmed_email=pubmed_email,
                            pubmed_api_key=pubmed_api_key,
                        )
                    )
                else:
                    query_plans.append(self._build_query_plan(source=source, query=query, fallback=False))

            for source in pending_sources:
                try:
                    open_api_results[source] = await tasks[source]
                except Exception as exc:
                    errors.append({"source": source, "error": str(exc)})
                    query_plans.append(self._build_query_plan(source=source, query=query, fallback=True))

        all_records: List[Dict[str, Any]] = []
        source_stats: Dict[str, Any] = {}
        for source, records in open_api_results.items():
            source_stats[source] = {
                "mode": "open_api",
                "count": len(records),
                "source_name": self.SUPPORTED_SOURCES[source]["name"],
            }
            all_records.extend(asdict(item) for item in records)

        for plan in query_plans:
            source = plan["source"]
            source_stats[source] = {
                "mode": self.SUPPORTED_SOURCES[source]["mode"],
                "count": 0,
                "source_name": self.SUPPORTED_SOURCES[source]["name"],
                "query_url": plan["query_url"],
                "note": plan["note"],
            }

        return {
            "query": query,
            "generated_at": datetime.now().isoformat(),
            "offline_plan_only": offline_plan_only,
            "max_results_per_source": max_results_per_source,
            "sources": normalized_sources,
            "records": all_records,
            "query_plans": query_plans,
            "source_stats": source_stats,
            "errors": errors,
        }

    def save_result(self, result: Dict[str, Any], output_file: str) -> str:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return output_file

    async def _search_open_api_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
        source: str,
        query: str,
        max_results: int,
        pubmed_email: str,
        pubmed_api_key: str,
    ) -> List[LiteratureRecord]:
        async with semaphore:
            return await self._search_open_api_async(
                client=client,
                source=source,
                query=query,
                max_results=max_results,
                pubmed_email=pubmed_email,
                pubmed_api_key=pubmed_api_key,
            )

    async def _search_open_api_async(
        self,
        client: httpx.AsyncClient,
        source: str,
        query: str,
        max_results: int,
        pubmed_email: str,
        pubmed_api_key: str,
    ) -> List[LiteratureRecord]:
        if source in ("pubmed", "medline_api"):
            return await self._search_pubmed_async(client, query, max_results, pubmed_email, pubmed_api_key)
        if source == "semantic_scholar":
            return await self._search_semantic_scholar_async(client, query, max_results)
        if source == "plos_one":
            return await self._search_plos_one_async(client, query, max_results)
        if source == "arxiv":
            return await self._search_arxiv_async(client, query, max_results)
        return []

    def _search_open_api(
        self,
        source: str,
        query: str,
        max_results: int,
        pubmed_email: str,
        pubmed_api_key: str,
    ) -> List[LiteratureRecord]:
        async def _runner() -> List[LiteratureRecord]:
            async with self._create_async_client() as client:
                return await self._search_open_api_async(
                    client=client,
                    source=source,
                    query=query,
                    max_results=max_results,
                    pubmed_email=pubmed_email,
                    pubmed_api_key=pubmed_api_key,
                )

        return self._run_coroutine(_runner())

    async def _search_pubmed_async(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
        email: str,
        api_key: str,
    ) -> List[LiteratureRecord]:
        esearch_params = self._build_pubmed_params(
            {"term": query, "retmax": str(max_results), "sort": "relevance"},
            email,
            api_key,
        )

        esearch_data = await self._request_json_async(client, f"{PUBMED_EUTILS_BASE}/esearch.fcgi", esearch_params)
        ids = (esearch_data.get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []

        esummary_params = self._build_pubmed_params(
            {"id": ",".join(ids)},
            email,
            api_key,
        )

        summary_data = await self._request_json_async(client, f"{PUBMED_EUTILS_BASE}/esummary.fcgi", esummary_params)
        result_obj = summary_data.get("result") or {}
        return self._build_pubmed_records(ids, result_obj)

    def _build_pubmed_params(
        self,
        base_params: Dict[str, str],
        email: str,
        api_key: str,
    ) -> Dict[str, str]:
        params: Dict[str, str] = {
            "db": "pubmed",
            "retmode": "json",
            **base_params,
        }
        if email:
            params["email"] = email
        if api_key:
            params["api_key"] = api_key
        return params

    def _build_pubmed_records(
        self,
        ids: List[str],
        result_obj: Dict[str, Any],
    ) -> List[LiteratureRecord]:
        records: List[LiteratureRecord] = []
        for pmid in ids:
            item = result_obj.get(pmid) or {}
            record = self._build_single_pubmed_record(pmid, item)
            if record:
                records.append(record)
        return records

    def _build_single_pubmed_record(
        self,
        pmid: str,
        item: Dict[str, Any],
    ) -> Optional[LiteratureRecord]:
        if not item:
            return None
        authors = [author.get("name", "") for author in item.get("authors", []) if author.get("name")]
        return LiteratureRecord(
            source="pubmed",
            title=item.get("title", ""),
            authors=authors,
            year=self._extract_pubmed_year(item),
            doi=self._extract_pubmed_doi(item),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            abstract="",
            citation_count=None,
            external_id=pmid,
        )

    def _extract_pubmed_year(self, item: Dict[str, Any]) -> Optional[int]:
        pubdate = str(item.get("pubdate", ""))
        if len(pubdate) >= 4 and pubdate[:4].isdigit():
            return int(pubdate[:4])
        return None

    def _extract_pubmed_doi(self, item: Dict[str, Any]) -> str:
        for article_id in item.get("articleids", []):
            if article_id.get("idtype") == "doi":
                return article_id.get("value", "")
        return ""

    async def _search_semantic_scholar_async(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
    ) -> List[LiteratureRecord]:
        params = {
            "query": query,
            "limit": str(max_results),
            "fields": "title,authors,year,abstract,url,citationCount,externalIds",
        }
        data = await self._request_json_async(client, SEMANTIC_SCHOLAR_SEARCH, params)
        rows = data.get("data") or []
        records: List[LiteratureRecord] = []
        for item in rows:
            authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
            ext_ids = item.get("externalIds") or {}
            records.append(
                LiteratureRecord(
                    source="semantic_scholar",
                    title=item.get("title", ""),
                    authors=authors,
                    year=item.get("year"),
                    doi=ext_ids.get("DOI", ""),
                    url=item.get("url", ""),
                    abstract=item.get("abstract", "") or "",
                    citation_count=item.get("citationCount"),
                    external_id=ext_ids.get("CorpusId", "") or "",
                )
            )
        return records

    async def _search_plos_one_async(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
    ) -> List[LiteratureRecord]:
        params = {
            "q": f"title:{query} OR abstract:{query}",
            "fq": 'journal_key:"PLoSONE"',
            "fl": "id,title,author,abstract,publication_date",
            "rows": str(max_results),
            "wt": "json",
        }
        data = await self._request_json_async(client, PLOS_SEARCH_API, params)
        docs = ((data.get("response") or {}).get("docs") or [])

        records: List[LiteratureRecord] = []
        for item in docs:
            pub_date = str(item.get("publication_date", ""))
            year = int(pub_date[:4]) if len(pub_date) >= 4 and pub_date[:4].isdigit() else None
            plos_id = item.get("id", "")
            records.append(
                LiteratureRecord(
                    source="plos_one",
                    title=(item.get("title") or [""])[0] if isinstance(item.get("title"), list) else item.get("title", ""),
                    authors=item.get("author") or [],
                    year=year,
                    doi=plos_id,
                    url=f"https://journals.plos.org/plosone/article?id={plos_id}" if plos_id else "",
                    abstract=(item.get("abstract") or [""])[0] if isinstance(item.get("abstract"), list) else item.get("abstract", ""),
                    citation_count=None,
                    external_id=plos_id,
                )
            )
        return records

    async def _search_arxiv_async(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
    ) -> List[LiteratureRecord]:
        params = {
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(max_results),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        response = await self._request_text_async(client, ARXIV_API, params)

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(response)
        records: List[LiteratureRecord] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
            year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
            authors = [
                (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
                for author in entry.findall("atom:author", ns)
            ]
            external_id = url.rsplit("/", 1)[-1] if url else ""

            records.append(
                LiteratureRecord(
                    source="arxiv",
                    title=title,
                    authors=[a for a in authors if a],
                    year=year,
                    doi="",
                    url=url,
                    abstract=summary,
                    citation_count=None,
                    external_id=external_id,
                )
            )
        return records

    def _build_query_plan(self, source: str, query: str, fallback: bool = False) -> Dict[str, Any]:
        q = urllib.parse.quote_plus(query)
        template = QUERY_PLAN_TEMPLATES.get(source)
        if not template:
            return {
                "source": source,
                "query_url": "",
                "note": "暂无检索 URL 模板。",
            }

        note = template["note"]
        if fallback:
            note = f"{note}（API 回退）"
        return {
            "source": source,
            "query_url": template["query_url"].format(q=q),
            "note": note,
        }

    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async def _runner() -> Dict[str, Any]:
            async with self._create_async_client() as client:
                return await self._request_json_async(client, url, params)

        return self._run_coroutine(_runner())

    async def _request_json_async(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        @retry(
            max_retries=self.retry_count,
            backoff="linear",
            base_delay=0.4,
            exceptions=(httpx.HTTPError, RuntimeError),
        )
        async def _do() -> Dict[str, Any]:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if self.request_interval_sec > 0:
                await asyncio.sleep(self.request_interval_sec)
            return data

        try:
            return await _do()
        except (httpx.HTTPError, RuntimeError) as exc:
            raise RuntimeError(f"request failed after retries: {url} — {exc}") from exc

    def _request_text(self, url: str, params: Dict[str, Any]) -> str:
        async def _runner() -> str:
            async with self._create_async_client() as client:
                return await self._request_text_async(client, url, params)

        return self._run_coroutine(_runner())

    async def _request_text_async(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Dict[str, Any],
    ) -> str:
        @retry(
            max_retries=self.retry_count,
            backoff="linear",
            base_delay=0.4,
            exceptions=(httpx.HTTPError, RuntimeError),
        )
        async def _do() -> str:
            response = await client.get(url, params=params)
            response.raise_for_status()
            if self.request_interval_sec > 0:
                await asyncio.sleep(self.request_interval_sec)
            return response.text

        try:
            return await _do()
        except (httpx.HTTPError, RuntimeError) as exc:
            raise RuntimeError(f"request failed after retries: {url} — {exc}") from exc

    def _create_async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=dict(self.headers), timeout=self.timeout_sec, follow_redirects=True)

    def _run_coroutine(self, coroutine: Awaitable[Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: Dict[str, Any] = {}
        error: Dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coroutine)
            except BaseException as exc:  # pragma: no cover
                error["value"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result.get("value")
