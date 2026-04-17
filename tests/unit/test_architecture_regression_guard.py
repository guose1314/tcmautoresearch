"""
回流防护契约测试 — 防止旧 cycle API 与 demo wrapper 形态重新泄入
Web/transport/helper 层。

Guard #1: Web routes + ops 不得直接导入 src.cycle
Guard #2: src/ 中不得引用已删除的 legacy store 符号
Guard #3: cycle_research_session.py 必须保持薄包装
Guard #4: research_utils.py 只在 canonical 基线上追加环境路径
Guard #5: 共享 runtime profile 必须嵌入 canonical 默认值
Guard #6: job_manager / research_job_runner 边界约束
Guard #7: Web 层不得散落 runtime profile 默认值
Guard #8: 结构化存储主写路径收口 + 一致性合同不可绕过
Guard #9: 快照 backfill_dependency 标注不可缺失
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
        from src.orchestration.research_runtime_service import (
            CANONICAL_OBSERVE_DEFAULTS,
        )

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
        from src.orchestration.research_runtime_service import (
            CANONICAL_OBSERVE_DEFAULTS,
        )

        extra = set(DEFAULT_OBSERVE_PHASE_CONTEXT) - set(CANONICAL_OBSERVE_DEFAULTS)
        non_path = {k for k in extra if not (k.endswith("_dir") or k.endswith("_path"))}
        self.assertEqual(
            non_path,
            set(),
            f"research_utils.py 在 canonical observe 基线上追加了非路径键: {non_path}",
        )

    def test_publish_defaults_equal_canonical(self):
        from src.api.research_utils import DEFAULT_PUBLISH_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import (
            CANONICAL_PUBLISH_DEFAULTS,
        )

        self.assertEqual(DEFAULT_PUBLISH_PHASE_CONTEXT, CANONICAL_PUBLISH_DEFAULTS)


# ═══════════════════════════════════════════════════════════════════════
# Guard #5 — runtime profile 嵌入 canonical 默认值
# ═══════════════════════════════════════════════════════════════════════

class TestSharedRuntimeProfilesCanonical(unittest.TestCase):
    """_SHARED_RUNTIME_PROFILES 中每个 profile 都必须引用 canonical 基线。"""

    def test_profiles_use_canonical_observe(self):
        from src.orchestration.research_runtime_service import (
            _SHARED_RUNTIME_PROFILES,
            CANONICAL_OBSERVE_DEFAULTS,
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
            _SHARED_RUNTIME_PROFILES,
            CANONICAL_PUBLISH_DEFAULTS,
        )
        for name, profile in _SHARED_RUNTIME_PROFILES.items():
            ctx = profile.get("default_publish_context", {})
            for key, val in CANONICAL_PUBLISH_DEFAULTS.items():
                self.assertEqual(
                    ctx.get(key),
                    val,
                    f"profile '{name}' publish context '{key}' 偏离 canonical",
                )


# ═══════════════════════════════════════════════════════════════════════
# Guard #6 — job_manager / research_job_runner 边界约束
# ═══════════════════════════════════════════════════════════════════════

class TestJobManagerBoundary(unittest.TestCase):
    """job_manager.py 仅负责任务生命周期、SSE 推送与调度协调。"""

    _JOB_MANAGER = _SRC / "web" / "ops" / "job_manager.py"
    _MAX_LINES = 450

    # 业务逻辑层模块 — job_manager 不应直接导入
    _FORBIDDEN_IMPORT_PREFIXES = (
        "src.research.",
        "src.cycle.",
        "src.storage.",
        "src.llm.",
        "src.knowledge.",
    )

    # 这些模式意味着 job wrapper 侵入了研究执行逻辑
    _FORBIDDEN_PATTERNS = (
        "CANONICAL_OBSERVE_DEFAULTS",
        "CANONICAL_PUBLISH_DEFAULTS",
        "_SHARED_RUNTIME_PROFILES",
        "ResearchPipeline",
        "session_result[",
        "phase_results[",
    )

    def test_line_count_within_budget(self):
        lines = self._JOB_MANAGER.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(
            len(lines),
            self._MAX_LINES,
            f"job_manager.py 已超 {self._MAX_LINES} 行 ({len(lines)} 行)，"
            "可能重新长回业务逻辑",
        )

    def test_no_forbidden_business_imports(self):
        modules = _collect_imports(self._JOB_MANAGER)
        violations = [
            m
            for m in modules
            if any(m.startswith(prefix) for prefix in self._FORBIDDEN_IMPORT_PREFIXES)
        ]
        self.assertEqual(
            violations,
            [],
            f"job_manager.py 导入了业务层模块: {violations}",
        )

    def test_no_forbidden_patterns(self):
        source = _collect_all_names_in_source(self._JOB_MANAGER)
        found = [p for p in self._FORBIDDEN_PATTERNS if p in source]
        self.assertEqual(found, [], f"job_manager.py 包含业务回流模式: {found}")


class TestResearchJobRunnerBoundary(unittest.TestCase):
    """research_job_runner.py 必须保持纯 passthrough。"""

    _RUNNER = _SRC / "web" / "ops" / "research_job_runner.py"
    _MAX_LINES = 60

    _FORBIDDEN_PATTERNS = (
        "CANONICAL_OBSERVE_DEFAULTS",
        "CANONICAL_PUBLISH_DEFAULTS",
        "ResearchPipeline",
        "export_research_session",
        "output/research_session",
        "open(",
        "json.dump",
    )

    def test_line_count_within_budget(self):
        lines = self._RUNNER.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(
            len(lines),
            self._MAX_LINES,
            f"research_job_runner.py 已超 {self._MAX_LINES} 行 ({len(lines)} 行)，"
            "可能重新长回业务逻辑",
        )

    def test_only_imports_orchestration(self):
        """唯一允许的业务导入来自 src.orchestration。"""
        modules = _collect_imports(self._RUNNER)
        business_imports = [
            m
            for m in modules
            if m.startswith("src.") and not m.startswith("src.orchestration.")
        ]
        self.assertEqual(
            business_imports,
            [],
            f"research_job_runner.py 导入了非 orchestration 的业务模块: {business_imports}",
        )

    def test_no_forbidden_patterns(self):
        source = _collect_all_names_in_source(self._RUNNER)
        found = [p for p in self._FORBIDDEN_PATTERNS if p in source]
        self.assertEqual(found, [], f"research_job_runner.py 包含业务回流模式: {found}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #7 — Web 层不得散落 runtime profile 默认值
# ═══════════════════════════════════════════════════════════════════════

class TestNoScatteredProfileDefaults(unittest.TestCase):
    """routes/ 和 ops/ 下所有文件不得出现研究配置常量或硬编码 phase list。"""

    # 只有 orchestration 层可定义这些符号
    _FORBIDDEN_SYMBOLS = (
        "CANONICAL_OBSERVE_DEFAULTS",
        "CANONICAL_PUBLISH_DEFAULTS",
        "_SHARED_RUNTIME_PROFILES",
        "default_observe_context",
        "default_publish_context",
    )

    def _scan_dir(self, dirpath: Path) -> list[str]:
        violations = []
        for fname in os.listdir(dirpath):
            if not fname.endswith(".py"):
                continue
            fpath = dirpath / fname
            source = _collect_all_names_in_source(fpath)
            for sym in self._FORBIDDEN_SYMBOLS:
                if sym in source:
                    rel = fpath.relative_to(_WORKSPACE)
                    violations.append(f"{rel}: {sym}")
        return violations

    def test_routes_no_profile_defaults(self):
        violations = self._scan_dir(_SRC / "web" / "routes")
        self.assertEqual(violations, [], f"route 层散落 profile 默认值: {violations}")

    def test_ops_no_profile_defaults(self):
        violations = self._scan_dir(_SRC / "web" / "ops")
        self.assertEqual(violations, [], f"ops 层散落 profile 默认值: {violations}")

    def test_routes_no_direct_research_pipeline(self):
        """route 文件不得直接导入 ResearchPipeline。"""
        routes = _SRC / "web" / "routes"
        violations = []
        for fname in os.listdir(routes):
            if not fname.endswith(".py"):
                continue
            fpath = routes / fname
            for mod in _collect_imports(fpath):
                if "research_pipeline" in mod:
                    violations.append(f"{fpath.relative_to(_WORKSPACE)}: {mod}")
        self.assertEqual(violations, [], f"route 直接导入 ResearchPipeline: {violations}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #8 — 结构化存储主写路径收口 + 一致性合同不可绕过
# ═══════════════════════════════════════════════════════════════════════

class TestStorageConvergenceGuard(unittest.TestCase):
    """Guard #8: 结构化主写路径经由 StorageBackendFactory + TransactionCoordinator。

    保护不变式：
    - phase_orchestrator 的 _persist_result_structured 必须通过 factory.transaction()
    - cycle.metadata.storage_persistence 包含 consistency_state 与 eventual_consistency
    - TransactionResult 必须有完整观测字段（neo4j_error, compensation_details, needs_backfill）
    - monitoring 的 persistence summary 必须嵌入 consistency_state
    """

    def test_persist_structured_uses_factory_transaction(self):
        """_persist_result_structured 必须调用 factory.transaction()。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("factory.transaction()", source,
                       "_persist_result_structured 未使用 factory.transaction()")

    def test_persist_structured_embeds_consistency_state(self):
        """storage_persistence 必须包含 consistency_state 与 eventual_consistency。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn('"consistency_state": consistency_state.to_dict()', source,
                       "storage_persistence 缺少 consistency_state.to_dict()")
        self.assertIn('"eventual_consistency":', source,
                       "storage_persistence 缺少 eventual_consistency 字段")

    def test_transaction_result_observation_fields(self):
        """TransactionResult 必须包含完整观测字段。"""
        from src.storage.transaction import TransactionResult
        r = TransactionResult(success=True)
        self.assertTrue(hasattr(r, "neo4j_error"), "缺少 neo4j_error 字段")
        self.assertTrue(hasattr(r, "compensation_details"), "缺少 compensation_details 字段")
        self.assertTrue(hasattr(r, "needs_backfill"), "缺少 needs_backfill 字段")
        self.assertTrue(hasattr(r, "storage_mode"), "缺少 storage_mode 字段")

    def test_monitoring_embeds_consistency_state(self):
        """monitoring._build_persistence_summary 内嵌 consistency_state。"""
        source = (_SRC / "infrastructure" / "monitoring.py").read_text(encoding="utf-8")
        self.assertIn("consistency_state", source,
                       "monitoring 缺少 consistency_state 嵌入")
        self.assertIn("_get_consistency_state_dict", source,
                       "monitoring 缺少 _get_consistency_state_dict 方法")

    def test_graph_report_includes_projection_scope(self):
        """_project_cycle_to_neo4j 返回 graph_projection_scope。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn('"graph_projection_scope":', source,
                       "graph_report 缺少 graph_projection_scope")

    def test_no_direct_neo4j_writes_in_research_main_path(self):
        """研究主链 persist 路径不得绕过 transaction 直接写 Neo4j。

        _project_cycle_to_neo4j 的 transaction 分支使用 transaction.neo4j_batch_*，
        非 transaction 分支只用于 legacy/test；主链调用必须传 transaction。
        """
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        # _persist_result_structured 调用 _project_cycle_to_neo4j 时必须传 transaction=txn
        self.assertIn("transaction=txn", source,
                       "_persist_result_structured 必须向 _project_cycle_to_neo4j 传递 transaction=txn")


# ═══════════════════════════════════════════════════════════════════════
# Guard #9 — 快照 backfill_dependency 标注不可缺失
# ═══════════════════════════════════════════════════════════════════════

class TestSnapshotBackfillAnnotationGuard(unittest.TestCase):
    """Guard #9: 快照 backfill_dependency 标注完整性。

    保护不变式：
    - get_full_snapshot 返回 backfill_dependency 字段
    - backfill_dependency 包含 observe_philology / version_lineages / graph_projection
    - backfill 工具输出包含 fields_written 标注
    """

    def test_snapshot_includes_backfill_dependency(self):
        """get_full_snapshot 必须返回 backfill_dependency 字段。"""
        source = (_SRC / "infrastructure" / "research_session_repo.py").read_text(encoding="utf-8")
        self.assertIn('backfill_dependency', source,
                       "get_full_snapshot 缺少 backfill_dependency")
        self.assertIn('_classify_backfill_dependency', source,
                       "缺少 _classify_backfill_dependency 方法")

    def test_backfill_dependency_covers_three_groups(self):
        """_classify_backfill_dependency 必须标注三组字段。"""
        source = (_SRC / "infrastructure" / "research_session_repo.py").read_text(encoding="utf-8")
        for group in ["observe_philology", "version_lineages", "graph_projection"]:
            self.assertIn(f'"{group}":', source,
                           f"backfill_dependency 缺少 {group} 分组")

    def test_backfill_dependency_includes_depends_on(self):
        """每组标注必须包含 depends_on 字段。"""
        source = (_SRC / "infrastructure" / "research_session_repo.py").read_text(encoding="utf-8")
        self.assertIn('"depends_on":', source,
                       "backfill_dependency 缺少 depends_on")

    def test_backfill_tool_annotates_fields_written(self):
        """backfill 工具输出必须包含 fields_written。"""
        source = (_WORKSPACE / "tools" / "backfill_research_session_nodes.py").read_text(encoding="utf-8")
        self.assertIn("fields_written", source,
                       "backfill 工具缺少 fields_written 标注")

    def test_classify_eventual_consistency_exists(self):
        """_classify_eventual_consistency 必须存在于 phase_orchestrator。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("_classify_eventual_consistency", source,
                       "缺少 _classify_eventual_consistency 方法")


if __name__ == "__main__":
    unittest.main()
