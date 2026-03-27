"""
基于本地中医经典分析 JSON 结果，生成 300 DPI 的期刊级医学研究图表。

示例：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/generate_medical_research_figures.py \
    --input-json output/local_tcm_llm_analysis.json \
    --output-dir output/figures \
    --dpi 300
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成医学研究论文常见图表（300 DPI）")
    parser.add_argument("--input-json", default="output/local_tcm_llm_analysis.json", help="分析结果 JSON")
    parser.add_argument("--output-dir", default="output/figures", help="图表输出目录")
    parser.add_argument("--dpi", type=int, default=300, help="导出 DPI，期刊建议 300+")
    parser.add_argument("--format", default="png", choices=["png", "tif", "tiff", "pdf"], help="图像格式")
    return parser.parse_args()


def setup_publication_style() -> None:
    """设置偏期刊风格的绘图主题。"""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.titlesize": 13,
            "axes.linewidth": 1.0,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.08,
            # 常见中文字体回退，避免中文标题显示为方块
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )


def load_result(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"分析结果不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_figure(fig: Figure, output_dir: Path, file_stem: str, ext: str, dpi: int) -> str:
    output_path = output_dir / f"{file_stem}.{ext}"
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path.as_posix()


def build_type_matrix(documents: List[Dict[str, Any]]) -> Tuple[List[str], List[str], np.ndarray]:
    all_types = sorted({etype for doc in documents for etype in doc.get("entity_types", {}).keys()})
    doc_names = [doc.get("title", "unknown") for doc in documents]
    matrix = np.zeros((len(doc_names), len(all_types)), dtype=float)

    for i, doc in enumerate(documents):
        etypes = doc.get("entity_types", {})
        for j, entity_type in enumerate(all_types):
            matrix[i, j] = float(etypes.get(entity_type, 0))

    return doc_names, all_types, matrix


def plot_overall_entity_distribution(result: Dict[str, Any]) -> Figure:
    data = result.get("aggregate_entity_types", {})
    labels = list(data.keys())
    values = [data[label] for label in labels]

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    bars = ax.bar(labels, values, color=["#3A7CA5", "#2A9D8F", "#E9C46A", "#E76F51", "#7B2CBF"])  # fixed palette
    ax.set_title("Figure 1. Overall Entity Type Distribution")
    ax.set_xlabel("Entity Type")
    ax.set_ylabel("Count")

    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{int(value)}", ha="center", va="bottom")

    return fig


def plot_document_entity_stacked(result: Dict[str, Any]) -> Figure:
    documents = result.get("documents", [])
    doc_names, all_types, matrix = build_type_matrix(documents)

    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    bottom = np.zeros(len(doc_names))
    palette = ["#3A7CA5", "#2A9D8F", "#E9C46A", "#E76F51", "#7B2CBF", "#4F772D", "#9D4EDD"]

    for idx, entity_type in enumerate(all_types):
        ax.bar(doc_names, matrix[:, idx], bottom=bottom, label=entity_type, color=palette[idx % len(palette)])
        bottom += matrix[:, idx]

    ax.set_title("Figure 2. Document-Level Stacked Entity Composition")
    ax.set_xlabel("Document")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(title="Entity Type", ncol=2)
    return fig


def plot_semantic_graph_complexity(result: Dict[str, Any]) -> Figure:
    documents = result.get("documents", [])
    names = [doc.get("title", "unknown") for doc in documents]
    nodes = [float(doc.get("semantic_graph_nodes", 0)) for doc in documents]
    edges = [float(doc.get("semantic_graph_edges", 0)) for doc in documents]

    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.bar(x - width / 2, nodes, width, label="Nodes", color="#3A7CA5")
    ax.bar(x + width / 2, edges, width, label="Edges", color="#E76F51")

    ax.set_title("Figure 3. Semantic Graph Complexity by Document")
    ax.set_xlabel("Document")
    ax.set_ylabel("Count")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=20)
    ax.legend()
    return fig


def plot_confidence_vs_entity_count(result: Dict[str, Any]) -> Figure:
    documents = result.get("documents", [])
    counts = np.array([float(doc.get("entity_count", 0)) for doc in documents])
    confs = np.array([float(doc.get("average_confidence", 0.0)) for doc in documents])
    nodes = np.array([float(doc.get("semantic_graph_nodes", 1)) for doc in documents])
    names = [doc.get("title", "unknown") for doc in documents]

    bubble_size = np.clip(nodes * 18.0, 80.0, 700.0)

    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.scatter(counts, confs, s=bubble_size, alpha=0.75, c="#2A9D8F", edgecolors="black", linewidths=0.8)

    for x, y, name in zip(counts, confs, names):
        ax.annotate(name, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8)

    ax.set_title("Figure 4. Mean Confidence vs Entity Count")
    ax.set_xlabel("Entity Count")
    ax.set_ylabel("Mean Confidence")
    ax.set_ylim(0.0, 1.02)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    return fig


def plot_entity_heatmap(result: Dict[str, Any]) -> Figure:
    documents = result.get("documents", [])
    doc_names, all_types, matrix = build_type_matrix(documents)

    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    im = ax.imshow(matrix, cmap="YlGnBu", aspect="auto")
    ax.set_title("Figure 5. Heatmap of Entity Types Across Documents")
    ax.set_xlabel("Entity Type")
    ax.set_ylabel("Document")
    ax.set_xticks(np.arange(len(all_types)))
    ax.set_xticklabels(all_types, rotation=25, ha="right")
    ax.set_yticks(np.arange(len(doc_names)))
    ax.set_yticklabels(doc_names)

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i, j]
            ax.text(j, i, f"{int(val)}", ha="center", va="center", color="black", fontsize=8)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Count")
    return fig


def main() -> None:
    args = parse_args()
    input_json = Path(args.input_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    setup_publication_style()
    result = load_result(input_json)

    exported: List[str] = []
    exported.append(save_figure(plot_overall_entity_distribution(result), output_dir, "fig1_overall_entity_distribution", args.format, args.dpi))
    exported.append(save_figure(plot_document_entity_stacked(result), output_dir, "fig2_document_entity_stacked", args.format, args.dpi))
    exported.append(save_figure(plot_semantic_graph_complexity(result), output_dir, "fig3_semantic_graph_complexity", args.format, args.dpi))
    exported.append(save_figure(plot_confidence_vs_entity_count(result), output_dir, "fig4_confidence_vs_entity_count", args.format, args.dpi))
    exported.append(save_figure(plot_entity_heatmap(result), output_dir, "fig5_entity_heatmap", args.format, args.dpi))

    summary = {
        "input_json": input_json.as_posix(),
        "output_dir": output_dir.as_posix(),
        "dpi": args.dpi,
        "format": args.format,
        "figures": exported,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
