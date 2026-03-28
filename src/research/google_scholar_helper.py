"""
Google Scholar Integration Helper - 给定 Scholar 搜索页 URL，生成 related works

功能：
- 解析 Google Scholar 搜索结果页
- 提取论文条目（题目、作者信息、摘要、引用数、链接）
- 基于提取结果生成 related works（LLM，可选）
- 输出 Markdown + JSON 结果文件
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


@dataclass
class ScholarPaperItem:
    title: str = ""
    authors_venue: str = ""
    snippet: str = ""
    citations: int = 0
    year: str = ""
    url: str = ""
    author_year_citation: str = ""


@dataclass
class GoogleScholarHelperResult:
    status: str = "pending"  # pending | success | error
    query_url: str = ""
    total_papers: int = 0
    papers: List[Dict[str, Any]] = field(default_factory=list)
    related_works_md: str = ""
    output_markdown: str = ""
    output_json: str = ""
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        }
    )

    # 复用系统代理，兼容国内网络环境
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if http_proxy or https_proxy:
        proxies: Dict[str, str] = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        session.proxies.update(proxies)

    return session


def _extract_year(text: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", text or "")
    return match.group(0) if match else ""


def _extract_citations(item_soup) -> int:
    cites = 0
    for a in item_soup.select(".gs_fl a"):
        txt = a.get_text(" ", strip=True).lower()
        m = re.search(r"cited by\s+(\d+)", txt)
        if m:
            cites = int(m.group(1))
            break
    return cites


def _extract_primary_author(authors_venue: str) -> str:
    """从 Scholar 的 authors/venue 文本提取第一作者姓氏或姓名。"""
    if not authors_venue:
        return "Unknown"

    # 常见格式: "A. Vaswani, N. Shazeer, ... - NeurIPS, 2017"
    author_segment = authors_venue.split(" - ", 1)[0].strip()
    if not author_segment:
        return "Unknown"

    first_author = author_segment.split(",", 1)[0].strip()
    if not first_author:
        return "Unknown"

    tokens = [t for t in re.split(r"\s+", first_author) if t]
    if not tokens:
        return "Unknown"

    surname = tokens[-1].strip(".")
    surname = re.sub(r"[^A-Za-z\u4e00-\u9fff\-]", "", surname)
    return surname or "Unknown"


def _format_author_year_citation(authors_venue: str, year: str, index: int) -> str:
    """生成作者-年份引用键，如 (Vaswani, 2017)。"""
    author = _extract_primary_author(authors_venue)
    safe_year = year or "n.d."
    if author == "Unknown" and safe_year == "n.d.":
        return f"Ref{index}"
    return f"({author}, {safe_year})"


def _parse_google_scholar_html(html: str, max_papers: int) -> List[ScholarPaperItem]:
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup 未安装，请先安装: pip install beautifulsoup4")

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".gs_ri")

    papers: List[ScholarPaperItem] = []
    for row in rows[:max_papers]:
        title_el = row.select_one(".gs_rt")
        link_el = title_el.find("a") if title_el else None
        title = title_el.get_text(" ", strip=True) if title_el else ""
        title = re.sub(r"\[[^\]]+\]\s*", "", title).strip()

        authors_venue_el = row.select_one(".gs_a")
        authors_venue = authors_venue_el.get_text(" ", strip=True) if authors_venue_el else ""

        snippet_el = row.select_one(".gs_rs")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        href = ""
        if link_el:
            href_raw = link_el.get("href", "")
            href = href_raw if isinstance(href_raw, str) else ""

        paper = ScholarPaperItem(
            title=title,
            authors_venue=authors_venue,
            snippet=snippet,
            citations=_extract_citations(row),
            year=_extract_year(authors_venue),
            url=href,
            author_year_citation=_format_author_year_citation(
                authors_venue,
                _extract_year(authors_venue),
                len(papers) + 1,
            ),
        )
        papers.append(paper)

    return papers


def _run_llm_prompt(llm_engine, prompt: str) -> str:
    if llm_engine is None:
        return ""

    if hasattr(llm_engine, "generate"):
        try:
            return llm_engine.generate(prompt)
        except Exception:
            pass

    if hasattr(llm_engine, "query"):
        try:
            return llm_engine.query(prompt)
        except Exception:
            pass

    return ""


def _build_related_works_prompt(
    topic_hint: str,
    papers: List[ScholarPaperItem],
    target_lang: str,
    additional_prompt: str,
) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        lines.append(
            f"[{i}] Title: {p.title}\n"
            f"Authors/Venue: {p.authors_venue}\n"
            f"Year: {p.year}\n"
            f"Author-Year Citation: {p.author_year_citation}\n"
            f"Citations: {p.citations}\n"
            f"Abstract Snippet: {p.snippet}\n"
            f"URL: {p.url}\n"
        )

    topic_text = topic_hint.strip() or "(未提供主题，按论文共性自动归纳)"
    extra = f"\nAdditional requirements: {additional_prompt}\n" if additional_prompt else ""

    return (
        f"You are an expert academic writer. Based on the papers below, write a high-quality Related Works section in {target_lang}.\n"
        "Requirements:\n"
        "1) Group prior work into clear themes.\n"
        "2) Compare methods, assumptions, strengths, and limitations.\n"
        "3) Use author-year citations in text, e.g., (Vaswani, 2017).\n"
        "4) Keep the provided Author-Year Citation keys aligned with each paper.\n"
        "5) End with a gap statement motivating current work.\n"
        f"Research topic: {topic_text}\n"
        f"{extra}\n"
        "Paper list:\n"
        + "\n".join(lines)
    )


def _fallback_related_works(papers: List[ScholarPaperItem], target_lang: str) -> str:
    header = "## Related Works\n\n" if target_lang.lower().startswith("en") else "## 相关工作\n\n"
    if not papers:
        return header + "未提取到可用文献条目。\n"

    lines = [header]
    for i, p in enumerate(papers, 1):
        lines.append(
            f"{p.author_year_citation} {p.title} 提出了相关方法；"
            f"其摘要片段显示研究重点为：{p.snippet or 'N/A'}。"
        )
    lines.append("\n上述工作覆盖了该方向的主要基线和变体，但在任务设定与泛化能力方面仍有改进空间。")
    return "\n".join(lines)


def run_google_scholar_related_works(
    scholar_url: str,
    output_dir: str = "./output/google_scholar_helper",
    max_papers: int = 20,
    topic_hint: str = "",
    target_lang: str = "Chinese",
    use_llm: bool = True,
    llm_engine=None,
    additional_prompt: str = "",
) -> GoogleScholarHelperResult:
    """运行 Google Scholar related-works 辅助流程。"""
    result = GoogleScholarHelperResult(query_url=scholar_url)

    if not scholar_url or "scholar.google" not in scholar_url:
        result.status = "error"
        result.error = "请输入有效的 Google Scholar 搜索页 URL"
        return result

    try:
        session = _build_session()
        response = session.get(scholar_url, timeout=30)
        response.raise_for_status()

        papers = _parse_google_scholar_html(response.text, max_papers=max_papers)
        result.total_papers = len(papers)
        result.papers = [asdict(p) for p in papers]

        if not papers:
            result.status = "error"
            result.error = "未在页面中解析到论文条目（可能触发反爬或页面结构变化）"
            return result

        related_works = ""
        if use_llm:
            prompt = _build_related_works_prompt(
                topic_hint=topic_hint,
                papers=papers,
                target_lang=target_lang,
                additional_prompt=additional_prompt,
            )
            related_works = _run_llm_prompt(llm_engine, prompt).strip()

        if not related_works:
            related_works = _fallback_related_works(papers, target_lang=target_lang)

        result.related_works_md = related_works

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = out / f"scholar_related_works_{stamp}.md"
        json_path = out / f"scholar_related_works_{stamp}.json"

        md_text = (
            "# Google Scholar Related Works\n\n"
            f"- URL: {scholar_url}\n"
            f"- Papers Parsed: {len(papers)}\n"
            f"- Generated At: {result.timestamp}\n\n"
            "## Parsed Papers\n\n"
        )
        for i, p in enumerate(papers, 1):
            md_text += (
                f"### [{i}] {p.title}\n"
                f"- Citation Key: {p.author_year_citation}\n"
                f"- Authors/Venue: {p.authors_venue}\n"
                f"- Year: {p.year or 'N/A'}\n"
                f"- Citations: {p.citations}\n"
                f"- URL: {p.url or 'N/A'}\n"
                f"- Snippet: {p.snippet or 'N/A'}\n\n"
            )

        md_text += "## Generated Related Works\n\n" + related_works + "\n"

        result.output_markdown = str(md_path)
        result.output_json = str(json_path)
        result.status = "success"
        md_path.write_text(md_text, encoding="utf-8")
        json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        return result

    except Exception as exc:
        result.status = "error"
        result.error = str(exc)
        return result
