"""
生成投稿模板图包（Figure 1-5，统一标题，A/B 子图布局，打印友好学术风）。

示例：
  c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe examples/generate_submission_figure_pack.py \
    --input-json output/local_tcm_llm_analysis.json \
    --output-dir output/figure_pack \
    --dpi 300 \
    --format png
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
    parser = argparse.ArgumentParser(description="生成投稿模板图包（Figure 1-5）")
    parser.add_argument("--input-json", default="output/local_tcm_llm_analysis.json", help="分析结果 JSON")
    parser.add_argument("--output-dir", default="output/figure_pack", help="图包输出目录")
    parser.add_argument("--dpi", type=int, default=300, help="导出 DPI，投稿建议 300+")
    parser.add_argument("--format", default="png", choices=["png", "tif", "tiff", "pdf"], help="导出格式")
    return parser.parse_args()


def setup_journal_style() -> None:
    """设置统一的投稿图风格：打印友好、可灰度识别、配色克制。"""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "figure.titlesize": 13,
            "axes.linewidth": 1.0,
            "grid.linewidth": 0.5,
            "grid.alpha": 0.5,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.08,
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )


PALETTE = ["#1B4965", "#5FA8D3", "#62B6CB", "#CAE9FF", "#FAF3DD", "#F4A259", "#BC4B51"]
HATCHES = ["///", "\\\\", "xx", "..", "++", "--", "oo"]
LEGENDS_FILENAME = "Figure_legends_submission.md"

FIGURE67_LEGENDS_BLOCK = """
## Figure 6. Evidence Matrix Dimension Heatmap
A. Evidence Dimension Heatmap. 该图展示证据矩阵中“文献 × 证据维度”的命中强度，颜色越深表示对应维度关键词命中次数越高。横轴为证据维度（如 condition/intervention/outcome/method），纵轴为按覆盖度排序的文献记录，可用于快速识别证据分布不均衡与潜在研究空白。

B. Matrix Reading Guidance. 每个热图单元代表某篇文献在特定证据维度的关键词匹配数量。该图主要用于描述性证据盘点，不直接表示因果强度或临床效应大小。

## Figure 7. Evidence Source Comparison
A. Evidence Count by Source. 该子图比较不同检索来源纳入记录数量，用于评估来源覆盖范围与贡献结构。

B. Mean Coverage Score by Source. 该子图展示不同来源文献在证据矩阵中的平均覆盖分数（coverage score），用于衡量来源在多维证据命中上的综合表现。该指标为结构化命中统计，适用于来源间的相对比较。
""".strip()


def load_result(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"分析结果不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_figure(fig: Figure, output_dir: Path, file_name: str, ext: str, dpi: int) -> str:
    output_path = output_dir / f"{file_name}.{ext}"
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path.as_posix()


def ensure_figure67_legends(output_dir: Path) -> Path:
    legends_path = output_dir / LEGENDS_FILENAME
    legends_exists = legends_path.exists()
    if legends_path.exists():
        content = legends_path.read_text(encoding="utf-8")
    else:
        fallback_path = Path("output/figure_pack_tiff600") / LEGENDS_FILENAME
        if fallback_path.exists():
            content = fallback_path.read_text(encoding="utf-8")
        else:
            content = "# Figure Legends\n"

    has_figure6 = "## Figure 6. Evidence Matrix Dimension Heatmap" in content
    has_figure7 = "## Figure 7. Evidence Source Comparison" in content
    if has_figure6 and has_figure7 and legends_exists:
        return legends_path

    insertion_text = "\n\n" + FIGURE67_LEGENDS_BLOCK + "\n"
    marker = "\n## Statistical Notes"
    if (not has_figure6 or not has_figure7) and marker in content:
        content = content.replace(marker, insertion_text + marker, 1)
    elif not has_figure6 or not has_figure7:
        content = content.rstrip() + insertion_text

    legends_path.write_text(content, encoding="utf-8")
    return legends_path


def build_type_matrix(documents: List[Dict[str, Any]]) -> Tuple[List[str], List[str], np.ndarray]:
    all_types = sorted({etype for doc in documents for etype in doc.get("entity_types", {}).keys()})
    doc_names = [doc.get("title", "unknown") for doc in documents]
    matrix = np.zeros((len(doc_names), len(all_types)), dtype=float)

    for i, doc in enumerate(documents):
        etypes = doc.get("entity_types", {})
        for j, entity_type in enumerate(all_types):
            matrix[i, j] = float(etypes.get(entity_type, 0))
    return doc_names, all_types, matrix


def resolve_evidence_matrix(result: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(result.get("evidence_matrix"), dict):
        return result.get("evidence_matrix", {})

    literature_pipeline = result.get("literature_pipeline") or {}
    if isinstance(literature_pipeline.get("evidence_matrix"), dict):
        return literature_pipeline.get("evidence_matrix", {})

    return {}


def resolve_literature_source_stats(result: Dict[str, Any], evidence_matrix: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    literature_pipeline = result.get("literature_pipeline") or {}
    source_stats = literature_pipeline.get("source_stats") or {}
    if source_stats:
        return source_stats

    stats: Dict[str, Dict[str, Any]] = {}
    for row in evidence_matrix.get("records", []) or []:
        source = row.get("source", "unknown") or "unknown"
        stats.setdefault(source, {"count": 0, "mode": "unknown", "source_name": source})
        stats[source]["count"] += 1
    return stats


def fig1_study_overview(result: Dict[str, Any]) -> Figure:
    """Figure 1: 研究设计与总体统计。"""
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), constrained_layout=True)

    # A: 简化流程图
    ax = axes[0]
    ax.set_title("A. Study Workflow Overview", loc="left", fontweight="bold")
    ax.axis("off")

    steps = ["Corpus Input", "Preprocess", "Entity Extraction", "Semantic Modeling", "LLM Synthesis"]
    x_positions = np.linspace(0.08, 0.92, len(steps))
    y = 0.55

    for i, (x, label) in enumerate(zip(x_positions, steps)):
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": PALETTE[i % len(PALETTE)], "alpha": 0.22, "edgecolor": "black"},
            transform=ax.transAxes,
        )
        if i < len(steps) - 1:
            ax.annotate(
                "",
                xy=(x_positions[i + 1] - 0.06, y),
                xytext=(x + 0.06, y),
                arrowprops={"arrowstyle": "->", "lw": 1.2},
                xycoords=ax.transAxes,
            )

    ax.text(
        0.02,
        0.15,
        f"n_documents = {result.get('document_count', 0)}\nkeywords = {', '.join(result.get('selected_keywords', []))}",
        transform=ax.transAxes,
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "#F7F7F7", "edgecolor": "#777777"},
    )

    # B: 总体实体分布
    ax2 = axes[1]
    ax2.set_title("B. Aggregate Entity Composition", loc="left", fontweight="bold")
    aggregate = result.get("aggregate_entity_types", {})
    labels = list(aggregate.keys())
    values = np.array([aggregate[k] for k in labels], dtype=float)

    if values.size == 0 or values.sum() == 0:
        ax2.text(0.5, 0.5, "No entity data", ha="center", va="center")
        ax2.axis("off")
    else:
        wedges, _, autotexts = ax2.pie(
            values,
            labels=labels,
            autopct=lambda p: f"{p:.1f}%",
            startangle=90,
            colors=[PALETTE[i % len(PALETTE)] for i in range(len(labels))],
            wedgeprops={"linewidth": 1.0, "edgecolor": "black"},
            textprops={"fontsize": 8},
        )
        for idx, w in enumerate(wedges):
            w.set_hatch(HATCHES[idx % len(HATCHES)])
        for t in autotexts:
            t.set_fontsize(8)

    fig.suptitle("Figure 1. Study Overview and Aggregate Composition", fontweight="bold")
    return fig


def fig2_entity_profile(result: Dict[str, Any]) -> Figure:
    """Figure 2: 文献层面实体统计与构成差异。"""
    docs = result.get("documents", [])
    names, all_types, matrix = build_type_matrix(docs)

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.0), constrained_layout=True)

    # A: 堆叠横条（打印友好）
    ax = axes[0]
    ax.set_title("A. Stacked Entity Composition by Document", loc="left", fontweight="bold")
    y = np.arange(len(names))
    left = np.zeros(len(names))

    for idx, entity_type in enumerate(all_types):
        vals = matrix[:, idx]
        bars = ax.barh(
            y,
            vals,
            left=left,
            color=PALETTE[idx % len(PALETTE)],
            edgecolor="black",
            linewidth=0.8,
            label=entity_type,
        )
        for b in bars:
            b.set_hatch(HATCHES[idx % len(HATCHES)])
        left += vals

    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("Count")
    ax.set_ylabel("Document")
    ax.legend(title="Entity Type", ncol=2, frameon=True)

    # B: 实体总数与置信度双轴
    ax2 = axes[1]
    ax2.set_title("B. Entity Count and Mean Confidence", loc="left", fontweight="bold")
    entity_count = np.array([doc.get("entity_count", 0) for doc in docs], dtype=float)
    mean_conf = np.array([doc.get("average_confidence", 0.0) for doc in docs], dtype=float)

    x = np.arange(len(names))
    bars = ax2.bar(x, entity_count, color=PALETTE[0], edgecolor="black", hatch=HATCHES[0], width=0.55, label="Entity Count")
    ax2.set_ylabel("Entity Count")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=15)

    ax2b = ax2.twinx()
    ax2b.plot(x, mean_conf, marker="o", color=PALETTE[6], linewidth=1.8, label="Mean Confidence")
    ax2b.set_ylim(0.0, 1.0)
    ax2b.set_ylabel("Mean Confidence")

    for bar, value in zip(bars, entity_count):
        ax2.text(bar.get_x() + bar.get_width() / 2, value, f"{int(value)}", ha="center", va="bottom", fontsize=8)

    # 合并图例
    handles1, labels1 = ax2.get_legend_handles_labels()
    handles2, labels2 = ax2b.get_legend_handles_labels()
    ax2.legend(handles1 + handles2, labels1 + labels2, loc="upper left", frameon=True)

    fig.suptitle("Figure 2. Document-Level Entity Profiles", fontweight="bold")
    return fig


def fig3_semantic_network_metrics(result: Dict[str, Any]) -> Figure:
    """Figure 3: 语义网络指标比较。"""
    docs = result.get("documents", [])
    names = [doc.get("title", "unknown") for doc in docs]
    nodes = np.array([doc.get("semantic_graph_nodes", 0) for doc in docs], dtype=float)
    edges = np.array([doc.get("semantic_graph_edges", 0) for doc in docs], dtype=float)
    ratio = np.divide(edges, nodes, out=np.zeros_like(edges), where=nodes > 0)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.0), constrained_layout=True)

    # A: 节点边数对比
    ax = axes[0]
    ax.set_title("A. Nodes and Edges by Document", loc="left", fontweight="bold")
    x = np.arange(len(names))
    width = 0.35
    b1 = ax.bar(x - width / 2, nodes, width, color=PALETTE[1], edgecolor="black", hatch=HATCHES[1], label="Nodes")
    b2 = ax.bar(x + width / 2, edges, width, color=PALETTE[5], edgecolor="black", hatch=HATCHES[5], label="Edges")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15)
    ax.set_ylabel("Count")
    ax.legend(frameon=True)

    for bars in [b1, b2]:
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(bar.get_height())}", ha="center", va="bottom", fontsize=8)

    # B: 边节点比
    ax2 = axes[1]
    ax2.set_title("B. Edge-to-Node Ratio", loc="left", fontweight="bold")
    ax2.plot(x, ratio, marker="s", color=PALETTE[6], linewidth=2.0)
    ax2.fill_between(x, 0, ratio, alpha=0.2, color=PALETTE[6])
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=15)
    ax2.set_ylabel("Edges / Nodes")
    ax2.set_ylim(bottom=0)

    for xi, r in zip(x, ratio):
        ax2.text(xi, r, f"{r:.2f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle("Figure 3. Semantic Network Metrics", fontweight="bold")
    return fig


def fig4_cross_document_patterns(result: Dict[str, Any]) -> Figure:
    """Figure 4: 跨文献模式图（热图 + 气泡图）。"""
    docs = result.get("documents", [])
    names, all_types, matrix = build_type_matrix(docs)

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), constrained_layout=True)

    # A: 热图
    ax = axes[0]
    ax.set_title("A. Entity Type Heatmap", loc="left", fontweight="bold")
    im = ax.imshow(matrix, cmap="Blues", aspect="auto")
    ax.set_xticks(np.arange(len(all_types)))
    ax.set_xticklabels(all_types, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(names)))
    ax.set_yticklabels(names)
    ax.set_xlabel("Entity Type")
    ax.set_ylabel("Document")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Count")

    # B: 气泡图（实体数、置信度、节点）
    ax2 = axes[1]
    ax2.set_title("B. Confidence-Count Bubble Map", loc="left", fontweight="bold")
    counts = np.array([doc.get("entity_count", 0) for doc in docs], dtype=float)
    confs = np.array([doc.get("average_confidence", 0.0) for doc in docs], dtype=float)
    nodes = np.array([doc.get("semantic_graph_nodes", 1) for doc in docs], dtype=float)

    size = np.clip(nodes * 22.0, 90.0, 820.0)
    scatter = ax2.scatter(counts, confs, s=size, c=PALETTE[2], alpha=0.75, edgecolors="black", linewidths=0.9)
    scatter.set_hatch(HATCHES[2])

    for x, y, name in zip(counts, confs, names):
        ax2.annotate(name, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)

    ax2.set_xlabel("Entity Count")
    ax2.set_ylabel("Mean Confidence")
    ax2.set_ylim(0, 1.02)

    fig.suptitle("Figure 4. Cross-Document Pattern Analysis", fontweight="bold")
    return fig


def fig5_publication_summary(result: Dict[str, Any]) -> Figure:
    """Figure 5: 投稿摘要页（关键结论 + 数值概览）。"""
    docs = result.get("documents", [])
    aggregate = result.get("aggregate_entity_types", {})

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 5.0), constrained_layout=True)

    # A: 横向排名图
    ax = axes[0]
    ax.set_title("A. Top Aggregate Entity Types", loc="left", fontweight="bold")
    sorted_items = sorted(aggregate.items(), key=lambda item: item[1], reverse=True)
    if sorted_items:
        labels = [x[0] for x in sorted_items]
        values = [x[1] for x in sorted_items]
        y = np.arange(len(labels))
        bars = ax.barh(y, values, color=PALETTE[3], edgecolor="black")
        for i, b in enumerate(bars):
            b.set_hatch(HATCHES[i % len(HATCHES)])
            ax.text(values[i], i, f" {values[i]}", va="center", fontsize=8)
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Count")
    else:
        ax.text(0.5, 0.5, "No aggregate entity data", ha="center", va="center")
        ax.axis("off")

    # B: 文本摘要板
    ax2 = axes[1]
    ax2.set_title("B. Submission-Oriented Key Messages", loc="left", fontweight="bold")
    ax2.axis("off")

    n_docs = result.get("document_count", 0)
    total_entities = int(sum(doc.get("entity_count", 0) for doc in docs))
    mean_conf = float(np.mean([doc.get("average_confidence", 0.0) for doc in docs])) if docs else 0.0
    total_nodes = int(sum(doc.get("semantic_graph_nodes", 0) for doc in docs))
    total_edges = int(sum(doc.get("semantic_graph_edges", 0) for doc in docs))

    message = (
        f"• Documents analyzed: {n_docs}\n"
        f"• Total entities extracted: {total_entities}\n"
        f"• Mean confidence: {mean_conf:.3f}\n"
        f"• Semantic nodes / edges: {total_nodes} / {total_edges}\n\n"
        "Recommended manuscript highlights:\n"
        "1) Classical TCM theory dominates entity space.\n"
        "2) Entity confidence is stable across included texts.\n"
        "3) Semantic graph complexity differs by text genre."
    )

    ax2.text(
        0.02,
        0.98,
        message,
        ha="left",
        va="top",
        fontsize=9.5,
        linespacing=1.35,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#F8F9FA", "edgecolor": "#666666"},
        transform=ax2.transAxes,
    )

    fig.suptitle("Figure 5. Publication-Ready Summary Panel", fontweight="bold")
    return fig


def fig6_evidence_dimension_heatmap(result: Dict[str, Any]) -> Figure:
    """Figure 6: 证据矩阵维度热图。"""
    evidence_matrix = resolve_evidence_matrix(result)
    records = evidence_matrix.get("records", []) or []
    dimensions = list((evidence_matrix.get("dimension_keywords") or {}).keys())

    fig, ax = plt.subplots(1, 1, figsize=(10.6, 5.0), constrained_layout=True)
    ax.set_title("Figure 6. Evidence Dimension Heatmap", loc="left", fontweight="bold")

    if not records or not dimensions:
        ax.text(0.5, 0.5, "No evidence_matrix data available", ha="center", va="center")
        ax.axis("off")
        return fig

    top_n = min(20, len(records))
    selected = records[:top_n]
    row_labels = [r.get("title", "")[:30] or f"record_{idx+1}" for idx, r in enumerate(selected)]
    matrix = np.zeros((len(selected), len(dimensions)), dtype=float)

    for i, row in enumerate(selected):
        hits_map = row.get("dimension_hits", {}) or {}
        for j, dimension in enumerate(dimensions):
            matrix[i, j] = float(len(hits_map.get(dimension, []) or []))

    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(np.arange(len(dimensions)))
    ax.set_xticklabels(dimensions, rotation=20, ha="right")
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_xlabel("Evidence Dimension")
    ax.set_ylabel("Top Records (by coverage score)")

    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = int(matrix[i, j])
            if val > 0:
                ax.text(j, i, str(val), ha="center", va="center", fontsize=7, color="black")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Matched keywords count")
    return fig


def fig7_evidence_source_comparison(result: Dict[str, Any]) -> Figure:
    """Figure 7: 证据来源对比图。"""
    evidence_matrix = resolve_evidence_matrix(result)
    source_stats = resolve_literature_source_stats(result, evidence_matrix)
    evidence_records = evidence_matrix.get("records", []) or []

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.8), constrained_layout=True)

    ax = axes[0]
    ax.set_title("A. Evidence Count by Source", loc="left", fontweight="bold")
    if not source_stats:
        ax.text(0.5, 0.5, "No source statistics available", ha="center", va="center")
        ax.axis("off")
    else:
        labels = list(source_stats.keys())
        values = [int((source_stats.get(label) or {}).get("count", 0)) for label in labels]
        bars = ax.bar(labels, values, color=PALETTE[: len(labels)], edgecolor="black")
        for i, bar in enumerate(bars):
            bar.set_hatch(HATCHES[i % len(HATCHES)])
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(values[i]), ha="center", va="bottom", fontsize=8)
        ax.set_ylabel("Record Count")
        ax.tick_params(axis="x", rotation=15)

    ax2 = axes[1]
    ax2.set_title("B. Mean Coverage Score by Source", loc="left", fontweight="bold")
    if not evidence_records:
        ax2.text(0.5, 0.5, "No evidence records available", ha="center", va="center")
        ax2.axis("off")
    else:
        grouped: Dict[str, List[float]] = {}
        for row in evidence_records:
            source = row.get("source", "unknown") or "unknown"
            grouped.setdefault(source, []).append(float(row.get("coverage_score", 0)))

        labels = list(grouped.keys())
        means = [float(np.mean(grouped[label])) if grouped[label] else 0.0 for label in labels]
        bars = ax2.bar(labels, means, color=PALETTE[2: 2 + len(labels)], edgecolor="black")
        for i, bar in enumerate(bars):
            bar.set_hatch(HATCHES[(i + 2) % len(HATCHES)])
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{means[i]:.2f}", ha="center", va="bottom", fontsize=8)
        ax2.set_ylabel("Mean Coverage Score")
        ax2.tick_params(axis="x", rotation=15)

    fig.suptitle("Figure 7. Evidence Source Comparison", fontweight="bold")
    return fig


def main() -> None:
    args = parse_args()
    setup_journal_style()

    input_json = Path(args.input_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = load_result(input_json)

    exported: List[str] = []
    exported.append(save_figure(fig1_study_overview(result), output_dir, "Figure1_study_overview_AB", args.format, args.dpi))
    exported.append(save_figure(fig2_entity_profile(result), output_dir, "Figure2_entity_profile_AB", args.format, args.dpi))
    exported.append(save_figure(fig3_semantic_network_metrics(result), output_dir, "Figure3_semantic_network_metrics_AB", args.format, args.dpi))
    exported.append(save_figure(fig4_cross_document_patterns(result), output_dir, "Figure4_cross_document_patterns_AB", args.format, args.dpi))
    exported.append(save_figure(fig5_publication_summary(result), output_dir, "Figure5_publication_summary_AB", args.format, args.dpi))
    exported.append(save_figure(fig6_evidence_dimension_heatmap(result), output_dir, "Figure6_evidence_dimension_heatmap", args.format, args.dpi))
    exported.append(save_figure(fig7_evidence_source_comparison(result), output_dir, "Figure7_evidence_source_comparison_AB", args.format, args.dpi))
    legends_file = ensure_figure67_legends(output_dir)

    output = {
        "input_json": input_json.as_posix(),
        "output_dir": output_dir.as_posix(),
        "dpi": args.dpi,
        "format": args.format,
        "figure_pack": exported,
        "legends_file": legends_file.as_posix(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
