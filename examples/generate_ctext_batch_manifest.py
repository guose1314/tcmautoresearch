"""
生成 ctext 白名单批量采集清单
"""

import json

from src.research.ctext_corpus_collector import CTextCorpusCollector


def main() -> None:
    collector = CTextCorpusCollector()
    collector.initialize()
    try:
        manifest = collector.generate_batch_collection_manifest(
            selected_groups=["four_books", "five_classics", "tcm_classics"],
            whitelist_path="data/ctext_whitelist.json",
            output_file="output/ctext_batch_manifest.json"
        )
        print(json.dumps(
            {
                "count": manifest.get("count", 0),
                "selected_groups": manifest.get("selected_groups", []),
                "output_file": "output/ctext_batch_manifest.json"
            },
            ensure_ascii=False,
            indent=2
        ))
    finally:
        collector.cleanup()


if __name__ == "__main__":
    main()
