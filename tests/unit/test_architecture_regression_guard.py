"""
回流防护契约测试 — 防止旧 cycle API 与 demo wrapper 形态重新泄入
Web/transport/helper 层。

Guard #1: Web routes + ops 不得直接导入 src.cycle
Guard #2: src/ 中不得引用已删除的 legacy store 符号
Guard #3: cycle_research_session.py 必须保持薄包装
Guard #4: research_utils.py 只在 canonical 基线上追加环境路径
Guard #5: 共享 runtime profile 必须嵌入 canonical 默认值
"""

import ast
import os
import unittest
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parents[2]
_SRC = _WORKSPACE / "src"


# ═══════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════

def _collect_imports(filepath: Path) -> list[str]:
    """Return all imported module names from a Python file."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def _collect_all_names_in_source(filepath: Path) -> str:
    """Return raw source text (for substring searches)."""
    return filepath.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Guard #1 — Web 层不得直接导入 cycle 层
# ═══════════════════════════════════════════════════════════════════════

class TestWebLayerNoCycleImport(unittest.TestCase):
    """src/web/routes/ 和 src/web/ops/ 下所有文件不得 import src.cycle。"""

    def _scan_dir_for_cycle_imports(self, dirpath: Path) -> list[str]:
        violations = []
        for fname in os.listdir(dirpath):
            if not fname.endswith(".py"):
                continue
            fpath = dirpath / fname
            for mod in _collect_imports(fpath):
                if mod.startswith("src.cycle") or mod.startswith(".cycle"):
                    violations.append(f"{fpath.relative_to(_WORKSPACE)}:{mod}")
        return violations

    def test_routes_no_cycle_import(self):
        routes = _SRC / "web" / "routes"
        violations = self._scan_dir_for_cycle_imports(routes)
        self.assertEqual(violations, [], f"route→cycle 回流: {violations}")

    def test_ops_no_cycle_import(self):
        ops = _SRC / "web" / "ops"
        violations = self._scan_dir_for_cycle_imports(ops)
        self.assertEqual(violations, [], f"ops→cycle 回流: {violations}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #2 — 已删除的 legacy store 符号不得复现
# ═══════════════════════════════════════════════════════════════════════

class TestNoLegacyStoreResurrection(unittest.TestCase):
    """src/ 下不得出现 get_legacy_research_store / LegacyResearchRuntimeStore。"""

    _FORBIDDEN_SYMBOLS = (
        "get_legacy_research_store",
        "LegacyResearchRuntimeStore",
    )

    def test_no_legacy_store_references(self):
        violations = []
        for root, _dirs, files in os.walk(_SRC):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(root) / fname
                source = _collect_all_names_in_source(fpath)
                for sym in self._FORBIDDEN_SYMBOLS:
                    if sym in source:
                        rel = fpath.relative_to(_WORKSPACE)
                        violations.append(f"{rel}: {sym}")
        self.assertEqual(violations, [], f"legacy store 回流: {violations}")

    def test_no_legacy_ops_files(self):
        ops = _SRC / "web" / "ops"
        legacy_files = [f for f in os.listdir(ops) if f.startswith("legacy")]
        self.assertEqual(legacy_files, [], f"legacy ops 文件回流: {legacy_files}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #3 — cycle_research_session.py 必须保持薄包装
# ═══════════════════════════════════════════════════════════════════════

class TestDemoWrapperStaysThin(unittest.TestCase):
    """cycle_research_session.py 行数不超限，且只做参数透传。"""

    _SESSION_FILE = _SRC / "cycle" / "cycle_research_session.py"
    _MAX_LINES = 60

    # 这些模式一旦出现意味着 demo wrapper 重新长回业务逻辑
    _FORBIDDEN_PATTERNS = (
        "output/research_session_",        # 直写 session 文件
        "export_research_session_reports",  # 导出逻辑回流
        "generated_by",                    # demo 来源标记
        "session_result[",                 # DTO 字段直写
        "session_result.update",           # DTO 组装
        '["status"]',                      # 本地 status 组装
        "open(",                           # 文件 IO 回流
    )

    def test_line_count_within_budget(self):
        lines = self._SESSION_FILE.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(
            len(lines),
            self._MAX_LINES,
            f"cycle_research_session.py 已超 {self._MAX_LINES} 行 ({len(lines)} 行)，"
            "可能重新长回业务逻辑",
        )

    def test_only_imports_runtime_service(self):
        """唯一允许的业务导入是 ResearchRuntimeService。"""
        modules = _collect_imports(self._SESSION_FILE)
        business_imports = [
            m for m in modules
            if m.startswith("src.") and m != "src.orchestration.research_runtime_service"
        ]
        self.assertEqual(
            business_imports,
            [],
            f"demo wrapper 导入了非 runtime_service 的业务模块: {business_imports}",
        )

    def test_no_forbidden_patterns(self):
        source = _collect_all_names_in_source(self._SESSION_FILE)
        found = [p for p in self._FORBIDDEN_PATTERNS if p in source]
        self.assertEqual(found, [], f"demo wrapper 包含回流模式: {found}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #4 — research_utils.py 只追加环境路径
# ═══════════════════════════════════════════════════════════════════════

class TestResearchUtilsCanonicalBaseline(unittest.TestCase):
    """research_utils.py 的 observe/publish 默认值必须基于 canonical 基线。"""

    def test_observe_defaults_are_canonical_superset(self):
        from src.api.research_utils import DEFAULT_OBSERVE_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import CANONICAL_OBSERVE_DEFAULTS

        for key, val in CANONICAL_OBSERVE_DEFAULTS.items():
            self.assertIn(key, DEFAULT_OBSERVE_PHASE_CONTEXT)
            self.assertEqual(
                DEFAULT_OBSERVE_PHASE_CONTEXT[key],
                val,
                f"observe 默认值 '{key}' 偏离 canonical 基线",
            )

    def test_observe_only_adds_path_keys(self):
        """API 层只允许在 canonical 基线上追加以 _dir / _path 结尾的键。"""
        from src.api.research_utils import DEFAULT_OBSERVE_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import CANONICAL_OBSERVE_DEFAULTS

        extra = set(DEFAULT_OBSERVE_PHASE_CONTEXT) - set(CANONICAL_OBSERVE_DEFAULTS)
        non_path = {k for k in extra if not (k.endswith("_dir") or k.endswith("_path"))}
        self.assertEqual(
            non_path,
            set(),
            f"research_utils.py 在 canonical observe 基线上追加了非路径键: {non_path}",
        )

    def test_publish_defaults_equal_canonical(self):
        from src.api.research_utils import DEFAULT_PUBLISH_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import CANONICAL_PUBLISH_DEFAULTS

        self.assertEqual(DEFAULT_PUBLISH_PHASE_CONTEXT, CANONICAL_PUBLISH_DEFAULTS)


# ═══════════════════════════════════════════════════════════════════════
# Guard #5 — runtime profile 嵌入 canonical 默认值
# ═══════════════════════════════════════════════════════════════════════

class TestSharedRuntimeProfilesCanonical(unittest.TestCase):
    """_SHARED_RUNTIME_PROFILES 中每个 profile 都必须引用 canonical 基线。"""

    def test_profiles_use_canonical_observe(self):
        from src.orchestration.research_runtime_service import (
            CANONICAL_OBSERVE_DEFAULTS,
            _SHARED_RUNTIME_PROFILES,
        )
        for name, profile in _SHARED_RUNTIME_PROFILES.items():
            ctx = profile.get("default_observe_context", {})
            for key, val in CANONICAL_OBSERVE_DEFAULTS.items():
                self.assertEqual(
                    ctx.get(key),
                    val,
                    f"profile '{name}' observe context '{key}' 偏离 canonical",
                )

    def test_profiles_use_canonical_publish(self):
        from src.orchestration.research_runtime_service import (
            CANONICAL_PUBLISH_DEFAULTS,
            _SHARED_RUNTIME_PROFILES,
        )
        for name, profile in _SHARED_RUNTIME_PROFILES.items():
            ctx = profile.get("default_publish_context", {})
            for key, val in CANONICAL_PUBLISH_DEFAULTS.items():
                self.assertEqual(
                    ctx.get(key),
                    val,
                    f"profile '{name}' publish context '{key}' 偏离 canonical",
                )


if __name__ == "__main__":
    unittest.main()
