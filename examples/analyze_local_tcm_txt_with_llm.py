"""
对 data 目录下中医经典 txt 文献进行真实分析，并调用本地 LLM 生成研究摘要。

建议使用 venv310 运行：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/analyze_local_tcm_txt_with_llm.py
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.semantic_graph import SemanticGraphBuilder
from src.llm.llm_engine import LLMEngine

ENCODING_CANDIDATES = ["utf-8", "utf-8-sig", "gb18030", "gbk", "big5"]
DEFAULT_KEYWORDS = ["神农本草经", "伤寒论", "黄帝内经"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用本地 LLM 分析 data 目录中的中医经典 txt 文献")
    parser.add_argument("--data-dir", default="data", help="txt 文献目录")
    parser.add_argument("--keyword", action="append", dest="keywords", help="文献筛选关键词，可重复指定")
    parser.add_argument("--max-docs", type=int, default=3, help="最多分析多少篇文献")
    parser.add_argument("--max-chars", type=int, default=2500, help="每篇送入处理链路的最大字符数")
    parser.add_argument("--output-file", default="output/local_tcm_llm_analysis.json", help="结果输出文件")
    parser.add_argument("--input-json", default="", help="已有分析结果 JSON 文件；提供后将跳过分析，直接导出 Markdown")
    parser.add_argument("--markdown-file", default="", help="Markdown 报告输出文件，默认与 JSON 同名")
    return parser.parse_args()


def detect_and_read_text(file_path: Path) -> Dict[str, Any]:
    raw_bytes = file_path.read_bytes()
    for encoding in ENCODING_CANDIDATES:
        try:
            text = raw_bytes.decode(encoding)
            return {
                "file_path": str(file_path),
                "encoding": encoding,
                "text": text
            }
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw_bytes, 0, 1, f"无法识别文件编码: {file_path}")


def select_documents(data_dir: Path, keywords: List[str], max_docs: int) -> List[Path]:
    candidates = sorted(path for path in data_dir.glob("*.txt") if path.is_file())
    matched: List[Path] = []
    normalized_keywords = [keyword for keyword in keywords if keyword]

    for path in candidates:
        name = path.name
        if any(keyword in name for keyword in normalized_keywords):
            matched.append(path)
        if len(matched) >= max_docs:
            break

    if matched:
        return matched
    return candidates[:max_docs]


def build_llm_prompt(document_summaries: List[Dict[str, Any]]) -> str:
    payload = []
    for summary in document_summaries:
        payload.append(
            {
                "title": summary["title"],
                "entity_count": summary["entity_count"],
                "top_entity_types": summary["entity_types"],
                "semantic_nodes": summary["semantic_graph_nodes"],
                "semantic_edges": summary["semantic_graph_edges"],
                "sample_text": summary["processed_text_preview"]
            }
        )

    return (
        "以下是本地 data 目录中中医经典 txt 文献的结构化分析结果：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "请完成一次研究型分析，输出以下内容：\n"
        "1. 这些文本的核心主题与学术价值\n"
        "2. 可观察到的中医理论、药物或方证规律\n"
        "3. 适合继续深挖的 3 个研究问题\n"
        "4. 对当前语料质量与后续采集的建议\n"
        "请用中文，尽量具体、专业。"
    )


def run_analysis(data_dir: Path, keywords: List[str], max_docs: int, max_chars: int, output_file: Path) -> Dict[str, Any]:
    selected_files = select_documents(data_dir, keywords, max_docs)
    if not selected_files:
        raise FileNotFoundError("未在 data 目录中找到可分析的 txt 文献")

    preprocessor = DocumentPreprocessor()
    extractor = AdvancedEntityExtractor()
    semantic_builder = SemanticGraphBuilder()

    if not preprocessor.initialize():
        raise RuntimeError("文档预处理器初始化失败")
    if not extractor.initialize():
        preprocessor.cleanup()
        raise RuntimeError("实体抽取器初始化失败")
    if not semantic_builder.initialize():
        extractor.cleanup()
        preprocessor.cleanup()
        raise RuntimeError("语义图构建器初始化失败")

    document_summaries: List[Dict[str, Any]] = []
    aggregate_type_counter: Counter[str] = Counter()

    try:
        for file_path in selected_files:
            loaded = detect_and_read_text(file_path)
            raw_text = loaded["text"][:max_chars]

            preprocess_result = preprocessor.execute(
                {
                    "raw_text": raw_text,
                    "source_file": file_path.name,
                    "metadata": {
                        "encoding": loaded["encoding"],
                        "analysis_source": "local_data_txt"
                    }
                }
            )
            extraction_result = extractor.execute(preprocess_result)
            semantic_result = semantic_builder.execute(extraction_result)

            entity_types = extraction_result.get("statistics", {}).get("by_type", {})
            aggregate_type_counter.update(entity_types)

            document_summaries.append(
                {
                    "title": file_path.stem,
                    "file_path": str(file_path),
                    "encoding": loaded["encoding"],
                    "entity_count": extraction_result.get("statistics", {}).get("total_count", 0),
                    "entity_types": entity_types,
                    "average_confidence": extraction_result.get("confidence_scores", {}).get("average_confidence", 0.0),
                    "semantic_graph_nodes": semantic_result.get("graph_statistics", {}).get("nodes_count", 0),
                    "semantic_graph_edges": semantic_result.get("graph_statistics", {}).get("edges_count", 0),
                    "processed_text_preview": preprocess_result.get("processed_text", "")[:300]
                }
            )
    finally:
        semantic_builder.cleanup()
        extractor.cleanup()
        preprocessor.cleanup()

    llm = LLMEngine(max_tokens=768, n_ctx=4096, temperature=0.2, verbose=False)
    llm.load()
    try:
        llm_analysis = llm.generate(
            build_llm_prompt(document_summaries),
            system_prompt="你是一位擅长中医古籍文本挖掘与科研选题设计的研究助手。"
        )
    finally:
        llm.unload()

    result = {
        "generated_at": datetime.now().isoformat(),
        "selected_keywords": keywords,
        "selected_files": [str(path) for path in selected_files],
        "document_count": len(document_summaries),
        "aggregate_entity_types": dict(aggregate_type_counter),
        "documents": document_summaries,
        "llm_analysis": llm_analysis
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def render_markdown_report(result: Dict[str, Any], json_path: Path) -> str:
    generated_at = result.get("generated_at", "")
    selected_files = result.get("selected_files", [])
    aggregate_types = result.get("aggregate_entity_types", {})
    documents = result.get("documents", [])
    llm_analysis = result.get("llm_analysis", "")

    lines: List[str] = []
    lines.append("# 本地中医经典语料研究摘要")
    lines.append("")
    lines.append("## 概览")
    lines.append(f"- 生成时间：{generated_at}")
    lines.append(f"- 文献数量：{result.get('document_count', 0)}")
    lines.append(f"- 关键词：{', '.join(result.get('selected_keywords', []))}")
    lines.append(f"- 来源 JSON：{json_path.as_posix()}")
    lines.append("")

    lines.append("## 入选文献")
    if selected_files:
        for file_path in selected_files:
            lines.append(f"- {file_path}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 实体类型汇总")
    if aggregate_types:
        lines.append("| 实体类型 | 计数 |")
        lines.append("| --- | ---: |")
        for entity_type, count in sorted(aggregate_types.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"| {entity_type} | {count} |")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 文献级分析")
    if documents:
        for index, doc in enumerate(documents, start=1):
            lines.append(f"### {index}. {doc.get('title', '未知标题')}")
            lines.append(f"- 文件：{doc.get('file_path', '')}")
            lines.append(f"- 编码：{doc.get('encoding', '')}")
            lines.append(f"- 实体数：{doc.get('entity_count', 0)}")
            lines.append(f"- 平均置信度：{doc.get('average_confidence', 0.0):.4f}")
            lines.append(f"- 语义图节点：{doc.get('semantic_graph_nodes', 0)}")
            lines.append(f"- 语义图边：{doc.get('semantic_graph_edges', 0)}")

            entity_types = doc.get("entity_types", {})
            if entity_types:
                lines.append("- 实体类型分布：")
                for entity_type, count in sorted(entity_types.items(), key=lambda item: item[1], reverse=True):
                    lines.append(f"  - {entity_type}: {count}")

            preview = doc.get("processed_text_preview", "")
            if preview:
                lines.append("- 文本片段：")
                lines.append("")
                lines.append("> " + preview.replace("\n", " "))
            lines.append("")
    else:
        lines.append("- 无")
        lines.append("")

    lines.append("## LLM 研究结论")
    lines.append("")
    if llm_analysis:
        lines.append(llm_analysis)
    else:
        lines.append("无")
    lines.append("")

    return "\n".join(lines)


def export_markdown_report(result: Dict[str, Any], json_path: Path, markdown_path: Path) -> Path:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_text = render_markdown_report(result, json_path)
    markdown_path.write_text(markdown_text, encoding="utf-8")
    return markdown_path


def main() -> None:
    args = parse_args()
    output_json_path = Path(args.output_file)

    if args.input_json:
        input_json_path = Path(args.input_json)
        result = json.loads(input_json_path.read_text(encoding="utf-8"))
        output_json_path = input_json_path
    else:
        data_dir = Path(args.data_dir)
        keywords = args.keywords or DEFAULT_KEYWORDS
        result = run_analysis(
            data_dir=data_dir,
            keywords=keywords,
            max_docs=args.max_docs,
            max_chars=args.max_chars,
            output_file=output_json_path
        )

    markdown_path = Path(args.markdown_file) if args.markdown_file else output_json_path.with_suffix(".md")
    export_markdown_report(result, output_json_path, markdown_path)

    summary = {
        "document_count": result["document_count"],
        "selected_files": result["selected_files"],
        "aggregate_entity_types": result["aggregate_entity_types"],
        "output_file": output_json_path.as_posix(),
        "markdown_file": markdown_path.as_posix(),
        "llm_analysis_preview": result["llm_analysis"][:600]
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
