"""
文献检索聚合模块。

支持：
- 开放 API 直连：PubMed/MEDLINE API, Semantic Scholar, PLOS ONE, arXiv
- 检索入口生成：bioRxiv(ioRxiv), Google Scholar, Cochrane, Embase, Scopus,
  Web of Science, Lexicomp, ClinicalKey
"""

from __future__ import annotations

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
PLOS_SEARCH_API = "https://api.plos.org/search"
ARXIV_API = "http://export.arxiv.org/api/query"

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
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.get(
                    "user_agent",
                    "TCM-AutoResearch-LiteratureRetriever/1.0 (mailto:research@example.com)",
                )
            }
        )

    def close(self) -> None:
        self.session.close()

    def search(
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

        for source in normalized_sources:
            info = self.SUPPORTED_SOURCES.get(source)
            if not info:
                errors.append({"source": source, "error": "unsupported_source"})
                continue

            mode = info["mode"]
            if mode == "open_api" and not offline_plan_only:
                try:
                    records = self._search_open_api(
                        source=source,
                        query=query,
                        max_results=max_results_per_source,
                        pubmed_email=pubmed_email,
                        pubmed_api_key=pubmed_api_key,
                    )
                    open_api_results[source] = records
                except Exception as exc:
                    # API 不可用时回退为可执行检索入口，避免流程中断
                    errors.append({"source": source, "error": str(exc)})
                    query_plans.append(self._build_query_plan(source=source, query=query, fallback=True))
            else:
                query_plans.append(self._build_query_plan(source=source, query=query, fallback=False))

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

    def _search_open_api(
        self,
        source: str,
        query: str,
        max_results: int,
        pubmed_email: str,
        pubmed_api_key: str,
    ) -> List[LiteratureRecord]:
        if source in ("pubmed", "medline_api"):
            return self._search_pubmed(query, max_results, pubmed_email, pubmed_api_key)
        if source == "semantic_scholar":
            return self._search_semantic_scholar(query, max_results)
        if source == "plos_one":
            return self._search_plos_one(query, max_results)
        if source == "arxiv":
            return self._search_arxiv(query, max_results)
        return []

    def _search_pubmed(
        self,
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

        esearch_data = self._request_json(f"{PUBMED_EUTILS_BASE}/esearch.fcgi", esearch_params)
        ids = (esearch_data.get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []

        esummary_params = self._build_pubmed_params(
            {"id": ",".join(ids)},
            email,
            api_key,
        )

        summary_data = self._request_json(f"{PUBMED_EUTILS_BASE}/esummary.fcgi", esummary_params)
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

    def _search_semantic_scholar(self, query: str, max_results: int) -> List[LiteratureRecord]:
        params = {
            "query": query,
            "limit": str(max_results),
            "fields": "title,authors,year,abstract,url,citationCount,externalIds",
        }
        data = self._request_json(SEMANTIC_SCHOLAR_SEARCH, params)
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

    def _search_plos_one(self, query: str, max_results: int) -> List[LiteratureRecord]:
        params = {
            "q": f"title:{query} OR abstract:{query}",
            "fq": 'journal_key:"PLoSONE"',
            "fl": "id,title,author,abstract,publication_date",
            "rows": str(max_results),
            "wt": "json",
        }
        data = self._request_json(PLOS_SEARCH_API, params)
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

    def _search_arxiv(self, query: str, max_results: int) -> List[LiteratureRecord]:
        params = {
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(max_results),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        response = self._request_text(ARXIV_API, params)

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
        last_exc: Optional[Exception] = None
        for attempt in range(self.retry_count + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_sec)
                response.raise_for_status()
                data = response.json()
                if self.request_interval_sec > 0:
                    time.sleep(self.request_interval_sec)
                return data
            except Exception as exc:
                last_exc = exc
                if attempt < self.retry_count:
                    time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"request failed: {url}, params={params}, error={last_exc}")

    def _request_text(self, url: str, params: Dict[str, Any]) -> str:
        last_exc: Optional[Exception] = None
        for attempt in range(self.retry_count + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_sec)
                response.raise_for_status()
                if self.request_interval_sec > 0:
                    time.sleep(self.request_interval_sec)
                return response.text
            except Exception as exc:
                last_exc = exc
                if attempt < self.retry_count:
                    time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"request failed: {url}, params={params}, error={last_exc}")
