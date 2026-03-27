"""
ResearchPipeline observe 阶段端到端演示：采集 -> 清洗 -> 抽取 -> 建模
"""

import argparse
import json
import logging
from typing import Any, Dict, List, Optional

from src.research.ctext_whitelist import load_whitelist
from src.research.multi_source_corpus import build_source_collection_plan
from src.research.research_pipeline import ResearchPhase, ResearchPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 ResearchPipeline 的 observe 首段主流程演示")
    parser.add_argument("--group", action="append", dest="groups", help="白名单分组，可重复指定")
    parser.add_argument("--whitelist-path", default="data/ctext_whitelist.json", help="白名单配置文件")
    parser.add_argument("--output-dir", default="data/ctext", help="ctext 采集输出目录")
    parser.add_argument("--max-depth", type=int, default=2, help="ctext 递归深度")
    parser.add_argument("--max-texts", type=int, default=2, help="最多处理多少篇已采集文本")
    parser.add_argument("--max-chars-per-text", type=int, default=800, help="每篇文本进入下游链路的最大字符数")
    return parser.parse_args()


def resolve_groups(whitelist_path: str, groups: Optional[List[str]]) -> List[str]:
    whitelist = load_whitelist(whitelist_path)
    available_groups = list((whitelist.get("groups") or {}).keys())
    if not groups:
        return ["tcm_classics"]

    unknown = [group for group in groups if group not in available_groups]
    if unknown:
        raise ValueError(f"未知白名单分组: {unknown}，可用分组: {available_groups}")
    return groups


def build_pipeline_config(whitelist_path: str) -> Dict[str, Any]:
    return {
        "ctext_corpus": {
            "enabled": True,
            "api_base": "https://api.ctext.org",
            "request_interval_sec": 0.2,
            "retry_count": 2,
            "timeout_sec": 20,
            "whitelist": {
                "enabled": True,
                "path": whitelist_path,
                "default_groups": ["tcm_classics"]
            }
        },
        "observe_pipeline": {
            "enabled": True
        }
    }


def run_demo(
    groups: Optional[List[str]] = None,
    whitelist_path: str = "data/ctext_whitelist.json",
    output_dir: str = "data/ctext",
    max_depth: int = 2,
    max_texts: int = 2,
    max_chars_per_text: int = 800
) -> Dict[str, Any]:
    selected_groups = resolve_groups(whitelist_path, groups)

    def execute_observe(selected_demo_groups: List[str]) -> Dict[str, Any]:
        pipeline = ResearchPipeline(build_pipeline_config(whitelist_path))

        cycle = pipeline.create_research_cycle(
            cycle_name="observe_ingestion_demo",
            description="ctext 标准语料观察阶段首段主流程演示",
            objective="验证采集、清洗、实体抽取、语义建模的串联能力",
            scope="observe_ingestion_demo",
            researchers=["demo_runner"]
        )
        if not pipeline.start_research_cycle(cycle.cycle_id):
            raise RuntimeError("研究循环启动失败")

        return pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "use_ctext_whitelist": True,
                "whitelist_path": whitelist_path,
                "whitelist_groups": selected_demo_groups,
                "output_dir": output_dir,
                "recurse": True,
                "max_depth": max_depth,
                "max_texts": max_texts,
                "max_chars_per_text": max_chars_per_text,
                "save_to_disk": True,
                "run_preprocess_and_extract": True
            }
        )

    result = execute_observe(selected_groups)

    fallback_result = None
    fallback_triggered = False
    initial_errors = result.get("corpus_collection", {}).get("errors", [])
    if (
        "tcm_classics" in selected_groups
        and result.get("ingestion_pipeline", {}).get("processed_document_count", 0) == 0
        and initial_errors
        and "four_books" not in selected_groups
    ):
        fallback_triggered = True
        fallback_result = execute_observe(["four_books"])

    source_plan = build_source_collection_plan("黄帝内经")

    summary = {
        "phase": result.get("phase"),
        "data_source": result.get("metadata", {}).get("data_source"),
        "ctext_groups": result.get("metadata", {}).get("ctext_groups", []),
        "corpus_stats": result.get("corpus_collection", {}).get("stats", {}),
        "corpus_errors": result.get("corpus_collection", {}).get("errors", []),
        "ingestion_aggregate": result.get("ingestion_pipeline", {}).get("aggregate", {}),
        "processed_document_count": result.get("ingestion_pipeline", {}).get("processed_document_count", 0),
        "sample_documents": result.get("ingestion_pipeline", {}).get("documents", []),
        "semantic_modeling": result.get("metadata", {}).get("semantic_modeling", False),
        "output_file": result.get("corpus_collection", {}).get("output_file", ""),
        "fallback_triggered": fallback_triggered,
        "fallback_result": {
            "ctext_groups": fallback_result.get("metadata", {}).get("ctext_groups", []),
            "corpus_stats": fallback_result.get("corpus_collection", {}).get("stats", {}),
            "corpus_errors": fallback_result.get("corpus_collection", {}).get("errors", []),
            "processed_document_count": fallback_result.get("ingestion_pipeline", {}).get("processed_document_count", 0),
            "ingestion_aggregate": fallback_result.get("ingestion_pipeline", {}).get("aggregate", {}),
            "semantic_modeling": fallback_result.get("metadata", {}).get("semantic_modeling", False),
            "output_file": fallback_result.get("corpus_collection", {}).get("output_file", "")
        } if fallback_result else None,
        "multi_source_routes": {
            "route_count": source_plan.get("route_count", 0),
            "source_ids": [route.get("source_id", "") for route in source_plan.get("routes", [])]
        }
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    args = parse_args()
    run_demo(
        groups=args.groups,
        whitelist_path=args.whitelist_path,
        output_dir=args.output_dir,
        max_depth=args.max_depth,
        max_texts=args.max_texts,
        max_chars_per_text=args.max_chars_per_text
    )
