"""
课题设计演示：使用 llama-cpp-python 调用本地 Qwen 模型生成研究假设。

示例：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/demo_qwen_hypothesis_design.py \
    --domain "中医药防治呼吸系统感染" \
    --clinical-question "TCM 对 COVID-19 恢复期症状改善的证据缺口是什么？" \
    --evidence-json output/observe_literature_pipeline.json \
    --output-file output/qwen_research_hypothesis.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from src.llm.llm_engine import LLMEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="调用本地 Qwen 生成课题研究假设")
    parser.add_argument("--domain", required=True, help="研究领域")
    parser.add_argument("--clinical-question", default="", help="临床问题")
    parser.add_argument("--evidence-json", default="", help="observe 阶段输出 JSON（可选）")
    parser.add_argument("--output-file", default="output/qwen_research_hypothesis.md", help="输出文件")
    parser.add_argument("--max-tokens", type=int, default=768, help="模型最大生成 token")
    parser.add_argument("--n-ctx", type=int, default=4096, help="模型上下文窗口")
    parser.add_argument("--temperature", type=float, default=0.2, help="采样温度")
    return parser.parse_args()


def _safe_get_evidence_matrix(data: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(data.get("evidence_matrix"), dict):
        return data["evidence_matrix"]
    literature = data.get("literature_pipeline") or {}
    if isinstance(literature.get("evidence_matrix"), dict):
        return literature["evidence_matrix"]
    return {}


def _safe_get_source_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    literature = data.get("literature_pipeline") or {}
    if isinstance(literature.get("source_stats"), dict):
        return literature.get("source_stats") or {}
    return {}


def build_corpus_summary(evidence_json_path: str, clinical_question: str) -> str:
    if not evidence_json_path:
        return (
            "当前未提供结构化证据矩阵 JSON。"
            f"临床问题：{clinical_question or '未指定'}。"
            "请基于中医药文献研究常见证据层级提出可验证假设。"
        )

    path = Path(evidence_json_path)
    if not path.exists():
        return (
            f"指定证据文件不存在：{evidence_json_path}。"
            f"临床问题：{clinical_question or '未指定'}。"
            "请基于现有临床研究方法学给出假设。"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    matrix = _safe_get_evidence_matrix(payload)
    source_stats = _safe_get_source_stats(payload)

    dim_hit_counts = matrix.get("dimension_hit_counts", {}) or {}
    top_records = (matrix.get("records", []) or [])[:5]
    top_lines: List[str] = []
    for row in top_records:
        top_lines.append(
            f"- {row.get('source', 'unknown')} | {row.get('title', '')[:70]} | coverage={row.get('coverage_score', 0)}"
        )

    source_lines = []
    for source, stats in source_stats.items():
        source_lines.append(f"{source}:{(stats or {}).get('count', 0)}")

    summary_lines = [
        f"临床问题：{clinical_question or '未指定'}",
        f"证据矩阵记录数：{matrix.get('record_count', 0)}",
        f"证据维度数：{matrix.get('dimension_count', 0)}",
        f"维度命中统计：{json.dumps(dim_hit_counts, ensure_ascii=False)}",
        f"来源统计：{', '.join(source_lines) if source_lines else '无'}",
        "高覆盖记录：",
    ]
    summary_lines.extend(top_lines if top_lines else ["- 无"])
    return "\n".join(summary_lines)


def build_markdown_output(domain: str, clinical_question: str, corpus_summary: str, hypothesis_text: str) -> str:
    return "\n".join(
        [
            "# 课题设计假设（Qwen 本地生成）",
            "",
            "## 输入信息",
            f"- 研究领域：{domain}",
            f"- 临床问题：{clinical_question or '未指定'}",
            "",
            "## 证据摘要",
            "```text",
            corpus_summary,
            "```",
            "",
            "## 生成假设",
            hypothesis_text,
            "",
        ]
    )


def main() -> None:
    args = parse_args()

    corpus_summary = build_corpus_summary(args.evidence_json, args.clinical_question)

    llm = LLMEngine(
        max_tokens=args.max_tokens,
        n_ctx=args.n_ctx,
        temperature=args.temperature,
        verbose=False,
    )
    llm.load()
    try:
        hypothesis_text = llm.generate_research_hypothesis(
            domain=args.domain,
            corpus_summary=corpus_summary,
            existing_research=(
                f"临床问题：{args.clinical_question}" if args.clinical_question else ""
            ),
        )
    finally:
        llm.unload()

    markdown = build_markdown_output(
        domain=args.domain,
        clinical_question=args.clinical_question,
        corpus_summary=corpus_summary,
        hypothesis_text=hypothesis_text,
    )

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    summary = {
        "output_file": output_path.as_posix(),
        "domain": args.domain,
        "clinical_question": args.clinical_question,
        "used_evidence_json": bool(args.evidence_json),
        "hypothesis_preview": hypothesis_text[:300],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
