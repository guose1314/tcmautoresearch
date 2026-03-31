"""科研图片生成服务 — 网络图、热力图、森林图、Venn 图等出版级科研图片。"""

from __future__ import annotations

import importlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

_DEFAULT_PALETTE = ["#1B4965", "#5FA8D3", "#62B6CB", "#CAE9FF", "#F4A259", "#BC4B51"]
_SUPPORTED_FORMATS = {"png", "pdf", "svg", "tif", "tiff"}


@dataclass
class FigureSpec:
    """图片生成规格。"""

    figure_type: str = ""
    title: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    style: Dict[str, Any] = field(default_factory=dict)
    output_format: str = "png"
    file_name: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FigureSpec":
        return cls(
            figure_type=str(payload.get("figure_type") or payload.get("type") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            data=dict(payload.get("data") or {}),
            style=dict(payload.get("style") or {}),
            output_format=str(payload.get("output_format") or payload.get("format") or "png").strip(),
            file_name=str(payload.get("file_name") or "").strip(),
        )


@dataclass
class FigureResult:
    """图片生成结果。"""

    success: bool
    file_path: str = ""
    figure_type: str = ""
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "file_path": self.file_path,
            "figure_type": self.figure_type,
            "title": self.title,
            "metadata": self.metadata,
            "error": self.error,
        }


class FigureGenerator(BaseModule):
    """科研图片生成器 — 输出出版级科研配图。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("figure_generator", config)
        self.output_dir = os.path.abspath(str(self.config.get("output_dir", "output/figures")))
        self.default_format = str(self.config.get("default_format", "png")).lower()
        self.default_dpi = int(self.config.get("dpi", 300))
        self.default_figsize = tuple(self.config.get("figsize", (8.5, 5.0)))
        self.palette = list(self.config.get("palette") or _DEFAULT_PALETTE)
        self.enable_seaborn = bool(self.config.get("enable_seaborn", True))
        self._plt: Any = None
        self._matplotlib: Any = None
        self._nx: Any = None
        self._sns: Any = None

    def _do_initialize(self) -> bool:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg", force=True)
        self._matplotlib = matplotlib
        self._plt = importlib.import_module("matplotlib.pyplot")
        try:
            self._sns = importlib.import_module("seaborn") if self.enable_seaborn else None
        except ImportError:
            self._sns = None
        self._nx = importlib.import_module("networkx")
        os.makedirs(self.output_dir, exist_ok=True)
        self._setup_publication_style()
        logger.info("FigureGenerator 初始化完成: output_dir=%s", self.output_dir)
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        specs = self._resolve_specs(context)
        if not specs:
            raise ValueError("FigureGenerator 需要 figure_spec、figure_specs 或 figure_type 输入")

        output_dir = os.path.abspath(str(context.get("output_dir") or self.output_dir))
        os.makedirs(output_dir, exist_ok=True)
        dpi = int(context.get("dpi", self.default_dpi))

        results: List[FigureResult] = []
        for spec in specs:
            results.append(self.generate_figure(spec, output_dir=output_dir, dpi=dpi))

        success_count = sum(1 for item in results if item.success)
        failed = [item.to_dict() for item in results if not item.success]
        figure_rows = [item.to_dict() for item in results]
        return {
            "success": len(failed) == 0,
            "output_dir": output_dir,
            "generated_count": success_count,
            "requested_count": len(results),
            "figures": figure_rows,
            "figure_paths": [item.file_path for item in results if item.success],
            "errors": failed,
        }

    def _do_cleanup(self) -> bool:
        if self._plt is not None:
            self._plt.close("all")
        return True

    def generate_figure(
        self,
        spec: FigureSpec | Dict[str, Any],
        output_dir: Optional[str] = None,
        dpi: Optional[int] = None,
    ) -> FigureResult:
        figure_spec = spec if isinstance(spec, FigureSpec) else FigureSpec.from_dict(spec)
        figure_type = figure_spec.figure_type.lower()
        renderer = {
            "network": self._render_network_figure,
            "heatmap": self._render_heatmap_figure,
            "forest": self._render_forest_figure,
            "venn": self._render_venn_figure,
            "bar": self._render_bar_figure,
            "scatter": self._render_scatter_figure,
        }.get(figure_type)

        if renderer is None:
            return FigureResult(
                success=False,
                figure_type=figure_type,
                title=figure_spec.title,
                error=f"不支持的 figure_type: {figure_spec.figure_type}",
            )

        try:
            figure, metadata = renderer(figure_spec)
            saved_path = self._save_figure(
                figure,
                figure_spec,
                output_dir=os.path.abspath(output_dir or self.output_dir),
                dpi=int(dpi or self.default_dpi),
            )
            metadata.update(
                {
                    "output_format": self._resolve_output_format(figure_spec.output_format),
                    "dpi": int(dpi or self.default_dpi),
                }
            )
            return FigureResult(
                success=True,
                file_path=saved_path,
                figure_type=figure_type,
                title=figure_spec.title,
                metadata=metadata,
            )
        except Exception as exc:
            logger.exception("科研图片生成失败: %s", exc)
            return FigureResult(
                success=False,
                figure_type=figure_type,
                title=figure_spec.title,
                error=str(exc),
            )

    def _resolve_specs(self, context: Dict[str, Any]) -> List[FigureSpec]:
        if context.get("figure_specs"):
            return self._coerce_spec_list(context.get("figure_specs", []))
        if context.get("figures"):
            return self._coerce_spec_list(context.get("figures", []))
        if context.get("figure_spec"):
            raw = context.get("figure_spec")
            spec = self._coerce_spec(raw)
            return [spec] if spec is not None else []
        if context.get("figure_type"):
            return [FigureSpec.from_dict(context)]
        return []

    def _coerce_spec(self, payload: Any) -> Optional[FigureSpec]:
        if isinstance(payload, FigureSpec):
            return payload
        if isinstance(payload, dict):
            return FigureSpec.from_dict(payload)
        return None

    def _coerce_spec_list(self, payloads: Sequence[Any]) -> List[FigureSpec]:
        specs: List[FigureSpec] = []
        for payload in payloads:
            spec = self._coerce_spec(payload)
            if spec is not None:
                specs.append(spec)
        return specs

    def _setup_publication_style(self) -> None:
        plt = self._require_plt()
        if plt is None:
            return
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
                "grid.alpha": 0.45,
                "savefig.bbox": "tight",
                "savefig.pad_inches": 0.08,
                "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
                "axes.unicode_minus": False,
            }
        )

    def _render_network_figure(self, spec: FigureSpec):
        nx = self._require_nx()
        plt = self._require_plt()
        nodes = list(spec.data.get("nodes") or [])
        edges = list(spec.data.get("edges") or spec.data.get("herb_target_edges") or [])
        directed = bool(spec.style.get("directed", False))
        graph = nx.DiGraph() if directed else nx.Graph()

        for node in nodes:
            if isinstance(node, dict):
                node_id = str(node.get("id") or node.get("name") or node.get("label") or "")
                if not node_id:
                    continue
                graph.add_node(node_id, **node)
            else:
                graph.add_node(str(node))

        for edge in edges:
            if isinstance(edge, dict):
                source = edge.get("source") or edge.get("from") or edge.get("herb")
                target = edge.get("target") or edge.get("to") or edge.get("pathway") or edge.get("target")
                if source is None or target is None:
                    continue
                graph.add_edge(str(source), str(target), **edge)
            elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
                graph.add_edge(str(edge[0]), str(edge[1]))

        figure, ax = plt.subplots(figsize=self._figure_size(spec))
        title = spec.title or "Research Network Figure"
        ax.set_title(title, loc="left", fontweight="bold")

        if graph.number_of_nodes() == 0:
            ax.text(0.5, 0.5, "No network data available", ha="center", va="center")
            ax.axis("off")
            return figure, {"node_count": 0, "edge_count": 0}

        positions = nx.spring_layout(graph, seed=42)
        node_colors = [self.palette[index % len(self.palette)] for index, _ in enumerate(graph.nodes())]
        edge_widths = []
        for _source, _target, data in graph.edges(data=True):
            weight = float(data.get("weight", data.get("score", 1.0)) or 1.0)
            edge_widths.append(max(1.0, min(weight, 5.0)))

        nx.draw_networkx(
            graph,
            pos=positions,
            ax=ax,
            node_color=node_colors,
            node_size=spec.style.get("node_size", 1200),
            width=edge_widths or 1.2,
            font_size=spec.style.get("font_size", 9),
            edge_color="#7F8C8D",
            arrows=directed,
        )
        ax.axis("off")
        return figure, {"node_count": graph.number_of_nodes(), "edge_count": graph.number_of_edges()}

    def _render_heatmap_figure(self, spec: FigureSpec):
        plt = self._require_plt()
        matrix = np.asarray(spec.data.get("matrix") or [], dtype=float)
        row_labels = list(spec.data.get("row_labels") or spec.data.get("y_labels") or [])
        col_labels = list(spec.data.get("col_labels") or spec.data.get("x_labels") or [])
        figure, ax = plt.subplots(figsize=self._figure_size(spec, fallback=(8.8, 5.2)))
        title = spec.title or "Research Heatmap"
        ax.set_title(title, loc="left", fontweight="bold")

        if matrix.size == 0:
            ax.text(0.5, 0.5, "No heatmap data available", ha="center", va="center")
            ax.axis("off")
            return figure, {"shape": [0, 0]}

        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)

        if self._sns is not None:
            heatmap = self._sns.heatmap(
                matrix,
                ax=ax,
                cmap=spec.style.get("cmap", "YlGnBu"),
                annot=bool(spec.style.get("annot", True)),
                fmt=spec.style.get("fmt", ".0f"),
                linewidths=0.5,
                cbar_kws={"label": spec.style.get("colorbar_label", "Value")},
            )
            _ = heatmap
        else:
            image = ax.imshow(matrix, cmap=spec.style.get("cmap", "YlGnBu"), aspect="auto")
            cbar = figure.colorbar(image, ax=ax)
            cbar.set_label(spec.style.get("colorbar_label", "Value"))
            if bool(spec.style.get("annot", True)):
                for row_index in range(matrix.shape[0]):
                    for col_index in range(matrix.shape[1]):
                        ax.text(col_index, row_index, f"{matrix[row_index, col_index]:.0f}", ha="center", va="center", fontsize=8)

        ax.set_xlabel(spec.style.get("xlabel", "Features"))
        ax.set_ylabel(spec.style.get("ylabel", "Samples"))
        if col_labels:
            ax.set_xticks(np.arange(len(col_labels)) + 0.5 if self._sns is not None else np.arange(len(col_labels)))
            ax.set_xticklabels(col_labels, rotation=25, ha="right")
        if row_labels:
            ax.set_yticks(np.arange(len(row_labels)) + 0.5 if self._sns is not None else np.arange(len(row_labels)))
            ax.set_yticklabels(row_labels)
        return figure, {"shape": [int(matrix.shape[0]), int(matrix.shape[1])]}

    def _render_forest_figure(self, spec: FigureSpec):
        plt = self._require_plt()
        records = list(spec.data.get("effects") or spec.data.get("records") or [])
        figure, ax = plt.subplots(figsize=self._figure_size(spec, fallback=(8.2, 5.6)))
        title = spec.title or "Forest Plot"
        ax.set_title(title, loc="left", fontweight="bold")

        if not records:
            ax.text(0.5, 0.5, "No forest plot data available", ha="center", va="center")
            ax.axis("off")
            return figure, {"effect_count": 0}

        labels = [str(item.get("label") or item.get("name") or f"study_{index + 1}") for index, item in enumerate(records)]
        effects = np.array([float(item.get("effect", item.get("estimate", 0.0))) for item in records], dtype=float)
        lowers = np.array([float(item.get("lower", item.get("ci_lower", item.get("effect", 0.0)))) for item in records], dtype=float)
        uppers = np.array([float(item.get("upper", item.get("ci_upper", item.get("effect", 0.0)))) for item in records], dtype=float)
        y_positions = np.arange(len(records))

        ax.errorbar(
            effects,
            y_positions,
            xerr=[effects - lowers, uppers - effects],
            fmt="o",
            color=self.palette[0],
            ecolor="#7F8C8D",
            capsize=4,
        )
        reference_value = float(spec.style.get("reference_line", 1.0))
        ax.axvline(reference_value, color="#BC4B51", linestyle="--", linewidth=1.2)
        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels)
        ax.set_xlabel(spec.style.get("xlabel", "Effect Size"))
        ax.set_ylabel(spec.style.get("ylabel", "Study / Endpoint"))
        ax.invert_yaxis()
        return figure, {"effect_count": len(records), "reference_line": reference_value}

    def _render_venn_figure(self, spec: FigureSpec):
        plt = self._require_plt()
        sets_payload = spec.data.get("sets") or {}
        if isinstance(sets_payload, dict):
            labels = list(sets_payload.keys())
            values = [set(sets_payload[label]) for label in labels]
        else:
            labels = [item.get("label", f"Set {index + 1}") for index, item in enumerate(sets_payload)]
            values = [set(item.get("values") or []) for item in sets_payload]

        figure, ax = plt.subplots(figsize=self._figure_size(spec, fallback=(7.6, 5.4)))
        title = spec.title or "Venn Diagram"
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 7)
        ax.axis("off")

        if not values or len(values) not in {2, 3}:
            ax.text(0.5, 0.5, "Venn data must contain 2 or 3 sets", ha="center", va="center", transform=ax.transAxes)
            return figure, {"set_count": len(values), "intersection_count": 0}

        Circle = importlib.import_module("matplotlib.patches").Circle
        centers = [(3.6, 3.6), (6.2, 3.6), (4.9, 5.0)]
        radii = [2.2, 2.2, 2.2]
        alphas = [0.35, 0.35, 0.35]

        for index, value_set in enumerate(values):
            circle = Circle(centers[index], radii[index], color=self.palette[index % len(self.palette)], alpha=alphas[index])
            ax.add_patch(circle)
            ax.text(centers[index][0], centers[index][1] + 2.45, labels[index], ha="center", va="bottom", fontsize=10, fontweight="bold")
            ax.text(centers[index][0], centers[index][1], str(len(value_set)), ha="center", va="center", fontsize=12)

        if len(values) >= 2:
            overlap_12 = len(values[0].intersection(values[1]))
            ax.text(4.9, 3.6, str(overlap_12), ha="center", va="center", fontsize=11)
        if len(values) == 3:
            overlap_13 = len(values[0].intersection(values[2]))
            overlap_23 = len(values[1].intersection(values[2]))
            overlap_123 = len(values[0].intersection(values[1], values[2]))
            ax.text(4.2, 4.45, str(overlap_13), ha="center", va="center", fontsize=11)
            ax.text(5.6, 4.45, str(overlap_23), ha="center", va="center", fontsize=11)
            ax.text(4.9, 4.0, str(overlap_123), ha="center", va="center", fontsize=11, fontweight="bold")

        intersection_count = len(set.intersection(*values)) if values else 0
        return figure, {"set_count": len(values), "intersection_count": intersection_count}

    def _render_bar_figure(self, spec: FigureSpec):
        plt = self._require_plt()
        labels = list(spec.data.get("labels") or [])
        values = [float(value) for value in spec.data.get("values") or []]
        figure, ax = plt.subplots(figsize=self._figure_size(spec))
        title = spec.title or "Bar Chart"
        ax.set_title(title, loc="left", fontweight="bold")

        if not labels or not values:
            ax.text(0.5, 0.5, "No bar chart data available", ha="center", va="center")
            ax.axis("off")
            return figure, {"bar_count": 0}

        positions = np.arange(len(labels))
        colors = [self.palette[index % len(self.palette)] for index in range(len(labels))]
        bars = ax.bar(positions, values, color=colors)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_xlabel(spec.style.get("xlabel", "Category"))
        ax.set_ylabel(spec.style.get("ylabel", "Value"))
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height(), f"{value:.2f}", ha="center", va="bottom", fontsize=8)
        return figure, {"bar_count": len(labels)}

    def _render_scatter_figure(self, spec: FigureSpec):
        plt = self._require_plt()
        x_values = np.asarray(spec.data.get("x") or [], dtype=float)
        y_values = np.asarray(spec.data.get("y") or [], dtype=float)
        labels = list(spec.data.get("labels") or [])
        figure, ax = plt.subplots(figsize=self._figure_size(spec))
        title = spec.title or "Scatter Plot"
        ax.set_title(title, loc="left", fontweight="bold")

        if x_values.size == 0 or y_values.size == 0:
            ax.text(0.5, 0.5, "No scatter data available", ha="center", va="center")
            ax.axis("off")
            return figure, {"point_count": 0}

        ax.scatter(x_values, y_values, c=self.palette[0], s=70, alpha=0.85)
        ax.set_xlabel(spec.style.get("xlabel", "X"))
        ax.set_ylabel(spec.style.get("ylabel", "Y"))
        if labels:
            for x_value, y_value, label in zip(x_values, y_values, labels):
                ax.text(float(x_value), float(y_value), str(label), fontsize=8, ha="left", va="bottom")
        return figure, {"point_count": int(min(len(x_values), len(y_values)))}

    def _save_figure(self, figure: Any, spec: FigureSpec, output_dir: str, dpi: int) -> str:
        plt = self._require_plt()
        output_format = self._resolve_output_format(spec.output_format)
        file_name = spec.file_name or self._build_file_name(spec)
        target_path = os.path.abspath(os.path.join(output_dir, f"{file_name}.{output_format}"))
        figure.savefig(target_path, dpi=dpi)
        plt.close(figure)
        return target_path

    def _figure_size(self, spec: FigureSpec, fallback: Optional[Sequence[float]] = None) -> tuple[float, float]:
        size = spec.style.get("figsize") or fallback or self.default_figsize
        if isinstance(size, (list, tuple)) and len(size) == 2:
            return float(size[0]), float(size[1])
        return float(self.default_figsize[0]), float(self.default_figsize[1])

    def _resolve_output_format(self, output_format: str) -> str:
        value = str(output_format or self.default_format).strip().lower()
        if value not in _SUPPORTED_FORMATS:
            raise ValueError(f"不支持的输出格式: {value}")
        return value

    def _build_file_name(self, spec: FigureSpec) -> str:
        title = spec.title or spec.figure_type or "figure"
        return _slugify(title)

    def _require_plt(self) -> Any:
        if self._plt is None:
            raise RuntimeError("FigureGenerator 未初始化 matplotlib.pyplot")
        return self._plt

    def _require_nx(self) -> Any:
        if self._nx is None:
            raise RuntimeError("FigureGenerator 未初始化 networkx")
        return self._nx


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "figure"
