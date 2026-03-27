import ast
import tempfile
import unittest
from pathlib import Path

from tools.generate_dependency_graph import (
    build_dependency_graph,
    extract_internal_imports,
    generate_mermaid_package_graph,
    module_name_from_path,
    resolve_relative_import,
)


class TestDependencyGraphTool(unittest.TestCase):
    def test_module_name_from_path(self):
        src_root = Path("repo/src")
        self.assertEqual(
            module_name_from_path(src_root, Path("repo/src/core/architecture.py")),
            "src.core.architecture",
        )
        self.assertEqual(
            module_name_from_path(src_root, Path("repo/src/core/__init__.py")),
            "src.core",
        )

    def test_resolve_relative_import(self):
        self.assertEqual(
            resolve_relative_import("src.core.architecture", 1, "module_interface"),
            "src.core.module_interface",
        )
        self.assertEqual(
            resolve_relative_import("src.research.research_pipeline", 2, "llm.llm_engine"),
            "src.llm.llm_engine",
        )

    def test_extract_internal_imports(self):
        source = (
            "from src.core.module_base import BaseModule\n"
            "from .research_methods import FormulaStructureAnalyzer\n"
            "import json\n"
        )
        imports = extract_internal_imports("src.semantic_modeling.semantic_graph_builder", ast.parse(source))
        self.assertIn("src.core.module_base", imports)
        self.assertIn("src.semantic_modeling.research_methods", imports)
        self.assertNotIn("json", imports)

    def test_build_dependency_graph_and_mermaid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "core").mkdir(parents=True)
            (root / "src" / "research").mkdir(parents=True)
            (root / "src" / "core" / "module_base.py").write_text("class BaseModule: pass\n", encoding="utf-8")
            (root / "src" / "research" / "pipeline.py").write_text(
                "from src.core.module_base import BaseModule\n",
                encoding="utf-8",
            )

            graph = build_dependency_graph(root)
            self.assertEqual(graph["module_count"], 2)
            self.assertEqual(graph["package_count"], 2)
            self.assertEqual(graph["package_edge_count"], 1)

            mermaid = generate_mermaid_package_graph(graph)
            self.assertIn("src_research --> src_core", mermaid)


if __name__ == "__main__":
    unittest.main()