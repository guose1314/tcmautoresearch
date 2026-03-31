"""
统一文献检索演示：
- 开放 API：PubMed/MEDLINE API, Semantic Scholar, PLOS ONE, arXiv
- 检索计划：bioRxiv(ioRxiv), Google Scholar, Cochrane, Embase, Scopus,
  Web of Science, Lexicomp, ClinicalKey

示例：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/demo_literature_retrieval.py \
    --query "traditional chinese medicine AND shanghan" \
    --max-results 5 \
    --output-file output/literature_retrieval_result.json
"""

import argparse
import json
from pathlib import Path

from src.collector.literature_retriever import LiteratureRetriever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一医学文献检索")
    parser.add_argument("--query", required=True, help="检索关键词")
    parser.add_argument("--source", action="append", dest="sources", help="指定来源，可重复传入")
    parser.add_argument("--max-results", type=int, default=5, help="每个开放 API 来源最多返回条数")
    parser.add_argument("--output-file", default="output/literature_retrieval_result.json", help="结果输出路径")
    parser.add_argument("--pubmed-email", default="", help="PubMed E-utilities 邮箱（推荐）")
    parser.add_argument("--pubmed-api-key", default="", help="PubMed API key（可选）")
    parser.add_argument(
        "--offline-plan-only",
        action="store_true",
        help="仅生成检索计划，不请求任何在线 API",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    retriever = LiteratureRetriever(
        {
            "timeout_sec": 20,
            "retry_count": 2,
            "request_interval_sec": 0.2,
        }
    )

    try:
        result = retriever.search(
            query=args.query,
            sources=args.sources,
            max_results_per_source=args.max_results,
            pubmed_email=args.pubmed_email,
            pubmed_api_key=args.pubmed_api_key,
            offline_plan_only=args.offline_plan_only,
        )
    finally:
        retriever.close()

    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "query": args.query,
        "sources": args.sources or list(LiteratureRetriever.SUPPORTED_SOURCES.keys()),
        "record_count": len(result.get("records", [])),
        "query_plan_count": len(result.get("query_plans", [])),
        "error_count": len(result.get("errors", [])),
        "output_file": output_file.as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
