"""
层边界契约测试 — 验证 src/research/ 不反向依赖 src/cycle/，
且 cycle 层兼容重导出完好。
"""

import ast
import os
import unittest
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parents[2]
_RESEARCH_DIR = _WORKSPACE / "src" / "research"
_CYCLE_DIR = _WORKSPACE / "src" / "cycle"


class TestResearchNoCycleDependency(unittest.TestCase):
    """src/research/ 下所有 .py 文件不得 import src.cycle。"""

    def _collect_imports(self, filepath: Path):
        """解析 AST，返回所有 import 来源模块名。"""
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
        return modules

    def test_no_research_imports_from_cycle(self):
        violations = []
        for root, _dirs, files in os.walk(_RESEARCH_DIR):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(root) / fname
                for mod in self._collect_imports(fpath):
                    if mod.startswith("src.cycle") or mod.startswith(".cycle"):
                        rel = fpath.relative_to(_WORKSPACE)
                        violations.append(f"{rel}: {mod}")
        self.assertEqual(violations, [], f"research→cycle 反向依赖: {violations}")


class TestCycleBackwardCompatReExports(unittest.TestCase):
    """cycle 层的兼容重导出仍可被正常访问。"""

    def test_cycle_runner_reexports_module_pipeline_symbols(self):
        from src.cycle.cycle_runner import (
            ModuleLifecycle,
            build_real_modules,
            cleanup_real_modules,
            execute_real_module_pipeline,
            initialize_real_modules,
            summarize_module_quality,
        )
        for sym in (
            ModuleLifecycle,
            build_real_modules,
            cleanup_real_modules,
            execute_real_module_pipeline,
            initialize_real_modules,
            summarize_module_quality,
        ):
            self.assertIsNotNone(sym)

    def test_cycle_reporter_reexports_quality_symbols(self):
        from src.cycle.cycle_reporter import (
            _MODULE_CONTENT_KEYS,
            _MODULE_EXPECTED_KEYS,
            _compute_accuracy,
            _compute_completeness,
            _compute_consistency,
            extract_research_phase_results,
            summarize_module_quality,
        )
        for sym in (
            _MODULE_EXPECTED_KEYS,
            _MODULE_CONTENT_KEYS,
            _compute_completeness,
            _compute_accuracy,
            _compute_consistency,
            summarize_module_quality,
            extract_research_phase_results,
        ):
            self.assertIsNotNone(sym)

    def test_cycle_package_lazy_exports_still_work(self):
        from src.cycle import execute_real_module_pipeline
        self.assertTrue(callable(execute_real_module_pipeline))


class TestCanonicalLocationIsResearch(unittest.TestCase):
    """规范定义位于 src/research/ 而非 src/cycle/。"""

    def test_module_pipeline_canonical(self):
        from src.research.module_pipeline import (
            execute_real_module_pipeline,
            summarize_module_quality,
        )
        self.assertTrue(callable(execute_real_module_pipeline))
        self.assertTrue(callable(summarize_module_quality))

    def test_phase_result_canonical(self):
        from src.research.phase_result import extract_research_phase_results
        self.assertTrue(callable(extract_research_phase_results))

    def test_canonical_and_reexport_are_same_object(self):
        from src.research.module_pipeline import (
            execute_real_module_pipeline as canonical_exec,
            summarize_module_quality as canonical_qual,
        )
        from src.cycle.cycle_runner import (
            execute_real_module_pipeline as compat_exec,
            summarize_module_quality as compat_qual,
        )
        self.assertIs(canonical_exec, compat_exec)
        self.assertIs(canonical_qual, compat_qual)

    def test_extract_phase_results_same_object(self):
        from src.research.phase_result import (
            extract_research_phase_results as canonical,
        )
        from src.cycle.cycle_reporter import (
            extract_research_phase_results as compat,
        )
        self.assertIs(canonical, compat)


if __name__ == "__main__":
    unittest.main()
