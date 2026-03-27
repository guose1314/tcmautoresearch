"""
Generate an internal dependency graph for the application.

The tool scans Python files under src/, extracts internal imports, and emits:
1) dependency-graph.json: module-level nodes and edges
2) dependency-graph.mmd: package-level Mermaid graph
3) dependency-graph.md: readable summary + Mermaid embed

Usage:
    python tools/generate_dependency_graph.py
    python tools/generate_dependency_graph.py --root . --output docs/architecture
"""

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Set

SRC_PACKAGE = "src"


@dataclass(frozen=True)
class ModuleNode:
    module: str
    file_path: str
    package: str


def iter_python_files(src_root: Path) -> Iterable[Path]:
    for path in src_root.rglob("*.py"):
        if path.is_file():
            yield path


def module_name_from_path(src_root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(src_root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = file_path.stem
    return ".".join([SRC_PACKAGE] + parts)


def package_name_from_module(module_name: str) -> str:
    parts = module_name.split(".")
    if len(parts) < 2:
        return module_name
    if len(parts) == 2:
        return module_name
    return ".".join(parts[:2])


def resolve_relative_import(module_name: str, level: int, imported_module: str | None) -> str | None:
    current_package = module_name if module_name.count(".") == 1 else module_name.rsplit(".", 1)[0]
    parts = current_package.split(".")
    anchor_count = len(parts) - (level - 1)
    if anchor_count <= 0:
        return None
    anchor = parts[:anchor_count]
    if imported_module:
        anchor.extend(imported_module.split("."))
    return ".".join(anchor)


def _is_internal_module_name(module_name: str | None) -> bool:
    if not module_name:
        return False
    return module_name == SRC_PACKAGE or module_name.startswith(SRC_PACKAGE + ".")


def _extract_from_import(module_name: str, node: ast.ImportFrom) -> str | None:
    if node.level and node.level > 0:
        resolved = resolve_relative_import(module_name, node.level, node.module)
        return resolved if _is_internal_module_name(resolved) else None
    if _is_internal_module_name(node.module):
        return node.module
    return None


def _extract_direct_imports(node: ast.Import) -> Set[str]:
    return {
        alias.name
        for alias in node.names
        if _is_internal_module_name(alias.name)
    }


def extract_internal_imports(module_name: str, tree: ast.AST) -> Set[str]:
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(_extract_direct_imports(node))
        elif isinstance(node, ast.ImportFrom):
            extracted = _extract_from_import(module_name, node)
            if extracted:
                imports.add(extracted)
    imports.discard(module_name)
    return imports


def build_dependency_graph(project_root: Path) -> Dict[str, object]:
    src_root = project_root / SRC_PACKAGE
    modules: Dict[str, ModuleNode] = {}
    module_edges: Set[tuple[str, str]] = set()

    for file_path in iter_python_files(src_root):
        module_name = module_name_from_path(src_root, file_path)
        modules[module_name] = ModuleNode(
            module=module_name,
            file_path=str(file_path.relative_to(project_root)).replace("\\", "/"),
            package=package_name_from_module(module_name),
        )

        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for imported in extract_internal_imports(module_name, tree):
            module_edges.add((module_name, imported))

    package_edges: Set[tuple[str, str]] = set()
    package_in_degree: Dict[str, int] = defaultdict(int)
    package_out_degree: Dict[str, int] = defaultdict(int)

    for source, target in module_edges:
        source_package = package_name_from_module(source)
        target_package = package_name_from_module(target)
        if source_package == target_package:
            continue
        edge = (source_package, target_package)
        if edge not in package_edges:
            package_edges.add(edge)
            package_out_degree[source_package] += 1
            package_in_degree[target_package] += 1

    package_nodes = sorted({node.package for node in modules.values()})
    return {
        "module_count": len(modules),
        "module_edge_count": len(module_edges),
        "package_count": len(package_nodes),
        "package_edge_count": len(package_edges),
        "modules": [modules[name].__dict__ for name in sorted(modules)],
        "module_edges": [
            {"source": source, "target": target}
            for source, target in sorted(module_edges)
        ],
        "packages": [
            {
                "package": package,
                "in_degree": package_in_degree.get(package, 0),
                "out_degree": package_out_degree.get(package, 0),
            }
            for package in package_nodes
        ],
        "package_edges": [
            {"source": source, "target": target}
            for source, target in sorted(package_edges)
        ],
    }


def generate_mermaid_package_graph(graph: Dict[str, object]) -> str:
    lines = ["flowchart LR"]
    for package_info in graph["packages"]:
        package = package_info["package"]
        node_id = package.replace(".", "_")
        label = package.replace("src.", "")
        lines.append(f"    {node_id}[\"{label}\"]")
    for edge in graph["package_edges"]:
        source = edge["source"].replace(".", "_")
        target = edge["target"].replace(".", "_")
        lines.append(f"    {source} --> {target}")
    return "\n".join(lines) + "\n"


def generate_markdown_report(graph: Dict[str, object], mermaid: str) -> str:
    lines = [
        "# Dependency Graph",
        "",
        "This document is generated from internal imports under src/.",
        "",
        "## Summary",
        "",
        f"- Module count: {graph['module_count']}",
        f"- Module edges: {graph['module_edge_count']}",
        f"- Package count: {graph['package_count']}",
        f"- Package edges: {graph['package_edge_count']}",
        "",
        "## Package Graph",
        "",
        "```mermaid",
        mermaid.rstrip(),
        "```",
        "",
        "## Packages",
        "",
        "| Package | In Degree | Out Degree |",
        "|---|---:|---:|",
    ]
    for package_info in graph["packages"]:
        lines.append(
            f"| {package_info['package']} | {package_info['in_degree']} | {package_info['out_degree']} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(graph: Dict[str, object], output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "dependency-graph.json"
    mermaid_path = output_dir / "dependency-graph.mmd"
    markdown_path = output_dir / "dependency-graph.md"

    mermaid = generate_mermaid_package_graph(graph)
    json_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    mermaid_path.write_text(mermaid, encoding="utf-8")
    markdown_path.write_text(generate_markdown_report(graph, mermaid), encoding="utf-8")

    return {
        "json": json_path,
        "mermaid": mermaid_path,
        "markdown": markdown_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate internal dependency graph")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--output", default="docs/architecture", help="Output directory")
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    graph = build_dependency_graph(project_root)
    outputs = write_outputs(graph, project_root / args.output)

    print("[dependency-graph] Generated outputs:")
    for name, path in outputs.items():
        print(f"- {name}: {path.relative_to(project_root)}")
    print(
        "[dependency-graph] Summary: "
        f"{graph['module_count']} modules, {graph['module_edge_count']} module edges, "
        f"{graph['package_count']} packages, {graph['package_edge_count']} package edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())