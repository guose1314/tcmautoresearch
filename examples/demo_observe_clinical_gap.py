"""
observe 阶段临床关联 Gap Analysis 演示。

示例：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/demo_observe_clinical_gap.py \
    --query "traditional chinese medicine covid randomized" \
    --clinical-question "TCM 对 COVID-19 的有效性与安全性证据缺口是什么？" \
    --output-file output/observe_clinical_gap_result.json
"""

import argparse
import json
from pathlib import Path

from src.orchestration.research_runtime_service import ResearchRuntimeService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="observe 临床关联 Gap Analysis")
    parser.add_argument("--query", required=True, help="文献检索词")
    parser.add_argument("--clinical-question", required=True, help="临床问题（建议 PICO 形式）")
    parser.add_argument("--output-file", default="output/observe_clinical_gap_result.json", help="输出文件")
    parser.add_argument("--offline-plan-only", action="store_true", help="仅检索计划，不触网")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    runtime_service = ResearchRuntimeService({
        "phases": ["observe"],
        "pipeline_config": {
            "literature_retrieval": {
                "enabled": True,
                "default_sources": ["pubmed", "semantic_scholar", "plos_one", "arxiv"],
                "max_results_per_source": 3,
                "offline_plan_only": args.offline_plan_only,
            },
            "clinical_gap_analysis": {
                "enabled": True,
                "n_ctx": 4096,
                "temperature": 0.15,
                "max_tokens": 1024,
            },
        },
    })

    runtime_result = runtime_service.run(
        args.clinical_question,
        cycle_name="observe_clinical_gap_demo",
        description="observe 文献检索与临床缺口分析",
        scope="observe",
        phase_contexts={
            "observe": {
                "run_literature_retrieval": True,
                "run_clinical_gap_analysis": True,
                "run_preprocess_and_extract": False,
                "literature_query": args.query,
                "clinical_question": args.clinical_question,
                "literature_offline_plan_only": args.offline_plan_only,
            },
        },
    )

    result = runtime_result.session_result
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    phase_results = result.get("phase_results") or {}
    observe_result = phase_results.get("observe") or {}
    clinical_gap = (observe_result.get("literature_pipeline") or {}).get("clinical_gap_analysis") or {}
    summary = {
        "status": runtime_result.orchestration_result.status,
        "literature_records": (observe_result.get("literature_pipeline") or {}).get("record_count", 0),
        "evidence_matrix_rows": ((observe_result.get("literature_pipeline") or {}).get("evidence_matrix") or {}).get("record_count", 0),
        "has_gap_report": bool(clinical_gap.get("report")),
        "output_file": output_file.as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
