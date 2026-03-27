"""
ctext 标准语料自动采集演示
"""

import argparse
import json
import logging
from typing import Any, Dict, List, Optional

from src.research.ctext_corpus_collector import CTextCorpusCollector
from src.research.ctext_whitelist import load_whitelist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按白名单分组抓取 ctext 标准语料")
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        help="指定白名单分组，可重复传入，例如 --group four_books --group tcm_classics"
    )
    parser.add_argument(
        "--whitelist-path",
        default="data/ctext_whitelist.json",
        help="白名单配置文件路径"
    )
    parser.add_argument(
        "--output-dir",
        default="data/ctext",
        help="采集结果输出目录"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="章节递归最大深度"
    )
    return parser.parse_args()


def resolve_groups(whitelist_path: str, groups: Optional[List[str]]) -> List[str]:
    whitelist = load_whitelist(whitelist_path)
    available_groups = list((whitelist.get("groups") or {}).keys())
    if not groups:
        return available_groups

    unknown_groups = [group for group in groups if group not in available_groups]
    if unknown_groups:
        raise ValueError(f"未知白名单分组: {unknown_groups}，可用分组: {available_groups}")

    return groups


def run_demo(
    groups: Optional[List[str]] = None,
    whitelist_path: str = "data/ctext_whitelist.json",
    output_dir: str = "data/ctext",
    max_depth: int = 3
) -> Dict[str, Any]:
    selected_groups = resolve_groups(whitelist_path, groups)

    collector = CTextCorpusCollector(
        {
            "output_dir": output_dir,
            "request_interval_sec": 0.2,
            "retry_count": 2,
            "timeout_sec": 20
        }
    )

    if not collector.initialize():
        raise RuntimeError("CText 采集器初始化失败")

    try:
        status = collector.check_api_status()
        print("API Status:")
        print(json.dumps(status, ensure_ascii=False, indent=2))

        manifest = collector.generate_batch_collection_manifest(
            selected_groups=selected_groups,
            whitelist_path=whitelist_path,
            output_file=""
        )

        print("Batch Manifest Summary:")
        print(json.dumps(
            {
                "selected_groups": manifest.get("selected_groups", []),
                "count": manifest.get("count", 0),
                "seed_urns": [entry.get("urn", "") for entry in manifest.get("entries", [])]
            },
            ensure_ascii=False,
            indent=2
        ))

        result = collector.execute(
            {
                "use_whitelist": True,
                "whitelist_path": whitelist_path,
                "whitelist_groups": selected_groups,
                "recurse": True,
                "max_depth": max_depth,
                "save_to_disk": True
            }
        )

        summary = {
            "seed_urns": result.get("seed_urns", []),
            "stats": result.get("stats", {}),
            "errors": result.get("errors", []),
            "output_file": result.get("output_file", "")
        }

        print("Collection Summary:")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return result
    finally:
        collector.cleanup()


if __name__ == "__main__":
    args = parse_args()
    run_demo(
        groups=args.groups,
        whitelist_path=args.whitelist_path,
        output_dir=args.output_dir,
        max_depth=args.max_depth
    )
