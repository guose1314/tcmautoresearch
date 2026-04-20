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
Guard #19: PG/Neo4j 事务边界收敛、降级状态观测与回填元数据标注
Guard #20: LLM 获取统一走 LLMGateway / CachedLLMService，禁止直接 new LLMEngine
Guard #21: ResearchDossierBuilder 存在性、接口契约与集成点保护
Guard #22: LearningLoopOrchestrator 学习闭环编排器结构与集成
Guard #23: EvidenceContract v2 平台级统一证据对象与 EvidenceEnvelope
Guard #28: Observe / Analyze / Publish phase dossier 压缩器与上下文注入路径保护
Guard #30: token budget policy 统一输入预算与主路径接线保护
Guard #31: 存储治理组件强一致基础设施（DegradationGovernor / BackfillLedger / StorageObservability）
Guard #32: 学习闭环策略调整与外部导入质量校验（PolicyAdjuster / ImportQualityValidator）
Guard #33: 小模型优化基础设施（ReasoningTemplateSelector / DynamicInvocationStrategy / DossierLayerCompressor / SmallModelOptimizer）
Guard #34: EvidenceEnvelope 跨阶段 phase_origin 统一协议（Phase F-1）
Guard #35: Phase output 形状收口 — metadata 最小公约键（Phase F-3）
Guard #36: Neo4j graph schema versioning 与标签注册表（Phase G-1）
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

    def test_storage_factory_lazy_cached_not_per_call(self):
        """_persist_result_structured 必须使用缓存的 factory 而非每次新建。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("_get_storage_factory()", source,
                       "_persist_result_structured 应通过 _get_storage_factory() 获取缓存 factory")
        self.assertIn("self._storage_factory", source,
                       "PhaseOrchestrator 应持有 _storage_factory 缓存字段")
        self.assertIn("close_storage_factory", source,
                       "PhaseOrchestrator 应提供 close_storage_factory() 显式释放方法")

    def test_no_raw_sqlite3_in_persist_path(self):
        """phase_orchestrator 持久化路径不得绕过 factory 直连 sqlite3。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertNotIn("import sqlite3", source,
                         "phase_orchestrator 不应直接 import sqlite3，所有持久化经由 factory")
        self.assertNotIn("sqlite3.connect", source,
                         "phase_orchestrator 不应直接调用 sqlite3.connect")


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


# ═══════════════════════════════════════════════════════════════════════
# Guard #10 — Schema 完整性：ORM 表与 Alembic 迁移覆盖一致
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaCompletenessGuard(unittest.TestCase):
    """Guard #10: 所有 ORM 表必须有对应的 Alembic migration 覆盖。

    保护不变式：
    - 每张 ORM __tablename__ 在 alembic/versions/ 的某次 migration 中有 create_table
    - DatabaseManager.init_db 包含 _verify_schema_completeness 调用
    - backend_factory.initialize 报告 schema_completeness
    """

    def test_all_orm_tables_covered_by_alembic_migrations(self):
        """每张 ORM 声明的表必须在至少一个 Alembic migration 中出现。"""
        import re

        from src.infrastructure.persistence import Base

        expected_tables = set(Base.metadata.tables.keys())
        versions_dir = _WORKSPACE / "alembic" / "versions"
        migration_sources = "".join(
            p.read_text(encoding="utf-8")
            for p in versions_dir.glob("*.py")
            if not p.name.startswith("__")
        )
        covered_tables = set(re.findall(r"op\.create_table\(\s*['\"](\w+)['\"]", migration_sources))
        missing = sorted(expected_tables - covered_tables)
        self.assertEqual(
            missing, [],
            f"以下 ORM 表缺少 Alembic migration 覆盖: {missing}",
        )

    def test_init_db_calls_schema_completeness_check(self):
        """DatabaseManager.init_db 必须调用 _verify_schema_completeness。"""
        source = (_SRC / "infrastructure" / "persistence.py").read_text(encoding="utf-8")
        self.assertIn("_verify_schema_completeness", source,
                       "init_db 缺少 schema 完整性验证")

    def test_factory_reports_schema_completeness(self):
        """backend_factory.initialize 报告中必须包含 schema_completeness。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("schema_completeness", source,
                       "factory initialize 报告缺少 schema_completeness")

    def test_sqlite_init_creates_all_orm_tables(self):
        """SQLite 模式下 init_db 后所有 ORM 表都存在。"""
        import tempfile

        from src.infrastructure.persistence import Base, DatabaseManager

        with tempfile.TemporaryDirectory() as tmp:
            import os
            db_path = os.path.join(tmp, "test_schema.db")
            mgr = DatabaseManager(f"sqlite:///{db_path}")
            mgr.init_db()
            report = mgr.get_schema_completeness_report()
            mgr.close()
            self.assertEqual(report["status"], "ok",
                             f"SQLite schema 不完整: {report.get('missing_tables')}")
            self.assertEqual(report["missing_tables"], [])


# ═══════════════════════════════════════════════════════════════════════
# Guard #11 — RuntimeService ↔ Factory 生命周期绑定
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeServiceFactoryLifecycleGuard(unittest.TestCase):
    """Guard #11: ResearchRuntimeService 必须管理 StorageBackendFactory 生命周期。

    保护不变式：
    - ResearchRuntimeService 持有 _storage_factory 属性
    - ResearchRuntimeService 暴露 get_consistency_state / close 方法
    - ResearchPipeline 接受 storage_factory 参数并注入 PhaseOrchestrator
    - PhaseOrchestrator.__init__ 接受 storage_factory 关键字参数
    - PhaseOrchestrator 区分外部注入 / 自建 factory（_storage_factory_owned）
    """

    def test_runtime_service_owns_factory_attribute(self):
        """ResearchRuntimeService 必须声明 _storage_factory 属性。"""
        source = (_SRC / "orchestration" / "research_runtime_service.py").read_text(encoding="utf-8")
        self.assertIn("self._storage_factory", source)

    def test_runtime_service_exposes_consistency_state(self):
        """ResearchRuntimeService 必须暴露 get_consistency_state 方法。"""
        source = (_SRC / "orchestration" / "research_runtime_service.py").read_text(encoding="utf-8")
        self.assertIn("def get_consistency_state(self)", source)

    def test_runtime_service_has_close_method(self):
        """ResearchRuntimeService 必须有 close() 释放 factory 资源。"""
        source = (_SRC / "orchestration" / "research_runtime_service.py").read_text(encoding="utf-8")
        self.assertIn("def close(self)", source)

    def test_pipeline_accepts_storage_factory(self):
        """ResearchPipeline.__init__ 必须接受 storage_factory 关键字参数。"""
        source = (_SRC / "research" / "research_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("storage_factory", source)

    def test_orchestrator_accepts_storage_factory(self):
        """PhaseOrchestrator.__init__ 必须接受 storage_factory 关键字参数。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("storage_factory: Any = None", source)

    def test_orchestrator_tracks_factory_ownership(self):
        """PhaseOrchestrator 必须跟踪 factory 所有权以避免双重 close。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("_storage_factory_owned", source)

    def test_pipeline_injects_factory_to_orchestrator(self):
        """ResearchPipeline 必须将 storage_factory 传递给 PhaseOrchestrator。"""
        source = (_SRC / "research" / "research_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("storage_factory=self._injected_storage_factory", source)

    def test_runtime_service_injects_factory_to_pipeline(self):
        """ResearchRuntimeService.run 创建 pipeline 时必须传入 storage_factory。"""
        source = (_SRC / "orchestration" / "research_runtime_service.py").read_text(encoding="utf-8")
        self.assertIn("storage_factory=self._storage_factory", source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #12 — 事务观测与收敛合同
# ═══════════════════════════════════════════════════════════════════════

class TestTransactionObservabilityGuard(unittest.TestCase):
    """Guard #12: TransactionCoordinator 必须提供阶段耗时、观测摘要、observer 协议。

    保护不变式：
    - TransactionResult 包含阶段耗时字段（pg_flush_ms, neo4j_execute_ms, pg_commit_ms, total_ms）
    - TransactionResult 提供 to_observation_dict() 方法
    - TransactionCoordinator 接受 observer 参数
    - TransactionCoordinator 暴露 last_result 属性
    - TransactionObserver 协议已定义
    - factory.transaction() 接受 observer 参数
    - _persist_result_structured 嵌入 transaction_observation
    """

    def test_transaction_result_has_timing_fields(self):
        """TransactionResult 必须包含阶段耗时字段。"""
        source = (_SRC / "storage" / "transaction.py").read_text(encoding="utf-8")
        for field_name in ("pg_flush_ms", "neo4j_execute_ms", "pg_commit_ms", "total_ms"):
            self.assertIn(field_name, source, f"TransactionResult 缺少 {field_name}")

    def test_transaction_result_has_observation_dict(self):
        """TransactionResult 必须提供 to_observation_dict。"""
        source = (_SRC / "storage" / "transaction.py").read_text(encoding="utf-8")
        self.assertIn("def to_observation_dict(self)", source)

    def test_coordinator_accepts_observer(self):
        """TransactionCoordinator.__init__ 必须接受 observer 参数。"""
        source = (_SRC / "storage" / "transaction.py").read_text(encoding="utf-8")
        self.assertIn("observer:", source)

    def test_coordinator_exposes_last_result(self):
        """TransactionCoordinator 必须暴露 last_result。"""
        source = (_SRC / "storage" / "transaction.py").read_text(encoding="utf-8")
        self.assertIn("self.last_result", source)

    def test_observer_protocol_defined(self):
        """TransactionObserver 协议必须已定义。"""
        source = (_SRC / "storage" / "transaction.py").read_text(encoding="utf-8")
        self.assertIn("class TransactionObserver", source)
        self.assertIn("on_transaction_complete", source)

    def test_factory_transaction_accepts_observer(self):
        """backend_factory.transaction() 必须接受 observer 参数。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("observer=observer", source)

    def test_orchestrator_surfaces_transaction_observation(self):
        """_persist_result_structured 必须嵌入 transaction_observation。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("transaction_observation", source)

    def test_orchestrator_logs_needs_backfill(self):
        """_persist_result_structured 必须在 needs_backfill 时记录警告。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("needs_backfill", source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #13 — 插件持久化路径收口到 StorageBackendFactory
# ═══════════════════════════════════════════════════════════════════════

class TestPluginStorageConvergenceGuard(unittest.TestCase):
    """Guard #13: 论文插件持久化已收口到 StorageBackendFactory + TransactionCoordinator。

    保护不变式：
    - cycle_storage_persist 不得引用 UnifiedStorageDriver / storage_driver
    - cycle_storage_persist 必须使用 StorageBackendFactory
    - cycle_storage_persist 必须使用 factory.transaction()
    - UnifiedStorageDriver 已标记弃用（DeprecationWarning）
    - 主科研路径（src/research, src/orchestration）不得导入 UnifiedStorageDriver
    """

    def test_cycle_persist_no_unified_storage_driver_import(self):
        """cycle_storage_persist 不得引用 UnifiedStorageDriver。"""
        source = (_SRC / "cycle" / "cycle_storage_persist.py").read_text(encoding="utf-8")
        self.assertNotIn("UnifiedStorageDriver", source)

    def test_cycle_persist_no_storage_driver_module_import(self):
        """cycle_storage_persist 不得直接 import storage_driver 模块。"""
        source = (_SRC / "cycle" / "cycle_storage_persist.py").read_text(encoding="utf-8")
        self.assertNotIn("storage_driver", source)

    def test_cycle_persist_uses_backend_factory(self):
        """cycle_storage_persist 必须通过 StorageBackendFactory 存储。"""
        source = (_SRC / "cycle" / "cycle_storage_persist.py").read_text(encoding="utf-8")
        self.assertIn("StorageBackendFactory", source)

    def test_cycle_persist_uses_transaction(self):
        """cycle_storage_persist 必须使用 factory.transaction() 保证原子性。"""
        source = (_SRC / "cycle" / "cycle_storage_persist.py").read_text(encoding="utf-8")
        self.assertIn("factory.transaction()", source)

    def test_unified_storage_driver_is_deprecated(self):
        """UnifiedStorageDriver 必须标记 DeprecationWarning。"""
        source = (_SRC / "storage" / "storage_driver.py").read_text(encoding="utf-8")
        self.assertIn("DeprecationWarning", source)
        self.assertIn("已弃用", source)

    def test_research_path_does_not_import_unified_storage_driver(self):
        """src/research/ 不得引用 UnifiedStorageDriver。"""
        research_dir = _SRC / "research"
        for py_file in research_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "UnifiedStorageDriver", source,
                f"{py_file.relative_to(_WORKSPACE)} 不应引用 UnifiedStorageDriver",
            )

    def test_orchestration_path_does_not_import_unified_storage_driver(self):
        """src/orchestration/ 不得引用 UnifiedStorageDriver。"""
        orch_dir = _SRC / "orchestration"
        for py_file in orch_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "UnifiedStorageDriver", source,
                f"{py_file.relative_to(_WORKSPACE)} 不应引用 UnifiedStorageDriver",
            )


# ═══════════════════════════════════════════════════════════════════════
# Guard #14 — SelfLearningEngine 安全持久化与接线契约
# ═══════════════════════════════════════════════════════════════════════

class TestSelfLearningEngineGuard(unittest.TestCase):
    """Guard #14: SelfLearningEngine 不使用 pickle 反序列化，使用 JSON 持久化。

    保护不变式：
    - self_learning_engine.py 不含 pickle.load 调用（顶层）
    - _save_learning_data 使用 json.dump
    - _load_learning_data 使用 json.load
    - model_improvement_log 有上限 (_MAX_IMPROVEMENT_LOG)
    - ResearchPipeline 集成 SelfLearningEngine
    - reflect 阶段回调 learn_from_cycle_reflection
    - _persist_cycle_learning_feedback 落库 learning_feedback_library
    """

    def test_no_toplevel_pickle_load(self):
        """self_learning_engine.py 不得在顶层 import pickle。"""
        source = (_SRC / "learning" / "self_learning_engine.py").read_text(encoding="utf-8")
        # 仅检查顶层（无缩进）import，允许方法内局部 import（如迁移用途）
        import_lines = [
            line for line in source.splitlines()
            if not line.startswith((" ", "\t"))
            and (line.strip().startswith("import pickle") or line.strip().startswith("from pickle"))
        ]
        self.assertEqual(import_lines, [], "self_learning_engine.py 不应顶层 import pickle")

    def test_save_uses_json(self):
        """_save_learning_data 必须使用 json.dump。"""
        source = (_SRC / "learning" / "self_learning_engine.py").read_text(encoding="utf-8")
        self.assertIn("json.dump(", source)

    def test_load_uses_json(self):
        """_load_learning_data 必须使用 json.load。"""
        source = (_SRC / "learning" / "self_learning_engine.py").read_text(encoding="utf-8")
        self.assertIn("json.load(", source)

    def test_improvement_log_has_cap(self):
        """model_improvement_log 必须有上限。"""
        source = (_SRC / "learning" / "self_learning_engine.py").read_text(encoding="utf-8")
        self.assertIn("_MAX_IMPROVEMENT_LOG", source)

    def test_pipeline_bootstraps_learning_engine(self):
        """ResearchPipeline 必须通过 _bootstrap_self_learning_engine 装配学习引擎。"""
        source = (_SRC / "research" / "research_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("_bootstrap_self_learning_engine", source)
        self.assertIn("self.self_learning_engine", source)

    def test_reflect_phase_feeds_learning_engine(self):
        """reflect 阶段必须调用 learn_from_cycle_reflection。"""
        source = (_SRC / "research" / "phases" / "reflect_phase.py").read_text(encoding="utf-8")
        self.assertIn("learn_from_cycle_reflection", source)

    def test_orchestrator_persists_learning_feedback(self):
        """phase_orchestrator 必须调用 _persist_cycle_learning_feedback。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("_persist_cycle_learning_feedback", source)
        self.assertIn("replace_learning_feedback_library", source)

    def test_deferred_save_via_dirty_flag(self):
        """_save_learning_data 使用 _save_dirty 延迟写入。"""
        source = (_SRC / "learning" / "self_learning_engine.py").read_text(encoding="utf-8")
        self.assertIn("_save_dirty", source)


# ── Guard #15: LLM 统一入口 ─────────────────────────────────────────────────


class TestLLMUnifiedEntryGuard(unittest.TestCase):
    """Guard #15: 所有 LLM 使用路径必须通过 get_llm_service / CachedLLMService 工厂。

    保护不变式：
    - cycle_plugin_workflows.py 不直接实例化 LLMEngine
    - cycle_plugin_workflows.py 通过 get_llm_service 获取 LLM
    - arxiv_quick_helper 使用 generate() 标准接口（非 query()）
    - google_scholar_helper 优先使用 generate() 标准接口
    - get_llm_service 按用途单例化并返回 CachedLLMService
    - _LLM_PURPOSE_PROFILES 包含 translation 和 paper_plugin
    """

    def test_cycle_plugin_no_raw_llm_engine(self):
        """cycle_plugin_workflows.py 不得直接构造 LLMEngine()。"""
        source = (_SRC / "cycle" / "cycle_plugin_workflows.py").read_text(encoding="utf-8")
        self.assertNotIn(
            '"LLMEngine")()',
            source,
            "cycle_plugin_workflows 不应直接实例化 LLMEngine，应使用 get_llm_service()",
        )

    def test_cycle_plugin_uses_get_llm_service(self):
        """cycle_plugin_workflows.py 通过 get_llm_service 获取 LLM 实例。"""
        source = (_SRC / "cycle" / "cycle_plugin_workflows.py").read_text(encoding="utf-8")
        self.assertIn("get_llm_service", source)

    def test_arxiv_helper_uses_generate(self):
        """arxiv_quick_helper 翻译路径必须优先使用 generate() 而非 query()。"""
        source = (_SRC / "research" / "arxiv_quick_helper.py").read_text(encoding="utf-8")
        self.assertIn('hasattr(llm_engine, "generate")', source)
        self.assertIn("llm_engine.generate(", source)

    def test_google_scholar_helper_prefers_generate(self):
        """google_scholar_helper LLM 调用优先 generate()。"""
        source = (_SRC / "research" / "google_scholar_helper.py").read_text(encoding="utf-8")
        self.assertIn("llm_engine.generate(", source)

    def test_get_llm_service_returns_cached(self):
        """get_llm_service 必须返回 CachedLLMService 单例。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("_llm_registry", source)
        self.assertIn("CachedLLMService.from_config(", source)

    def test_purpose_profiles_translation_and_paper(self):
        """_LLM_PURPOSE_PROFILES 必须包含 translation 和 paper_plugin。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn('"translation"', source)
        self.assertIn('"paper_plugin"', source)


# ── Guard #16: cycle demo shared_modules 兼容壳收敛 ────────────────────────


class TestCycleDemoSharedModulesGuard(unittest.TestCase):
    """Guard #16: 默认主链不构建旧 shared_modules，旧路径标记 DeprecationWarning。

    保护不变式：
    - run_full_cycle_demo 默认路径（run_iteration=None）不调用 lifecycle.build()
    - _default_pipeline_iteration 不消费 shared_modules（del）
    - run_iteration_cycle 标记 DeprecationWarning
    - build_real_modules 标记 DeprecationWarning
    - 默认 run_iteration 桥接 _default_pipeline_iteration
    """

    def test_default_path_skips_legacy_module_build(self):
        """run_full_cycle_demo 默认路径使用 _uses_legacy_modules 门控跳过构建。"""
        source = (_SRC / "cycle" / "cycle_runner.py").read_text(encoding="utf-8")
        self.assertIn("_uses_legacy_modules", source)
        self.assertIn("if _uses_legacy_modules:", source)

    def test_default_pipeline_iteration_discards_shared_modules(self):
        """_default_pipeline_iteration 必须 del shared_modules。"""
        source = (_SRC / "cycle" / "cycle_runner.py").read_text(encoding="utf-8")
        self.assertIn("del shared_modules", source)

    def test_run_iteration_cycle_deprecated(self):
        """run_iteration_cycle 必须发出 DeprecationWarning。"""
        source = (_SRC / "cycle" / "cycle_runner.py").read_text(encoding="utf-8")
        # 在 run_iteration_cycle 函数体中应有 DeprecationWarning
        idx_func = source.index("def run_iteration_cycle(")
        # 查找该函数到下一个 def 之间的片段
        next_def = source.index("\ndef ", idx_func + 1)
        func_body = source[idx_func:next_def]
        self.assertIn("DeprecationWarning", func_body)

    def test_build_real_modules_deprecated(self):
        """build_real_modules 必须发出 DeprecationWarning。"""
        source = (_SRC / "research" / "module_pipeline.py").read_text(encoding="utf-8")
        idx_func = source.index("def build_real_modules(")
        next_def = source.index("\ndef ", idx_func + 1)
        func_body = source[idx_func:next_def]
        self.assertIn("DeprecationWarning", func_body)

    def test_default_iteration_bridges_to_pipeline(self):
        """默认 run_iteration 必须桥接 _default_pipeline_iteration → run_pipeline_iteration。"""
        source = (_SRC / "cycle" / "cycle_runner.py").read_text(encoding="utf-8")
        self.assertIn("_default_pipeline_iteration", source)
        self.assertIn("run_pipeline_iteration", source)


# ── Guard #17: ResearchRuntimeService 唯一主线 ──────────────────────────────


class TestResearchRuntimeServiceMainlineGuard(unittest.TestCase):
    """Guard #17: ResearchRuntimeService 是唯一 research mainline，旧旁路全部标记弃用。

    保护不变式：
    - ResearchOrchestrator.__init__ 发出 DeprecationWarning
    - run_research() 发出 DeprecationWarning（已有 Guard 验证，此处交叉确认）
    - real_observe_smoke 不直接导入/实例化 ResearchPipeline
    - real_observe_smoke 通过 ResearchRuntimeService 执行
    - cycle_research_session 通过 ResearchRuntimeService 执行
    - Web job_runner 通过 ResearchRuntimeService 执行
    """

    def test_research_orchestrator_init_deprecated(self):
        """ResearchOrchestrator.__init__ 必须发出 DeprecationWarning。"""
        source = (_SRC / "orchestration" / "research_orchestrator.py").read_text(encoding="utf-8")
        idx_init = source.index("def __init__(self, config")
        next_def = source.index("\n    def ", idx_init + 1)
        init_body = source[idx_init:next_def]
        self.assertIn("DeprecationWarning", init_body)

    def test_run_research_deprecated(self):
        """run_research() 必须发出 DeprecationWarning。"""
        source = (_SRC / "orchestration" / "research_orchestrator.py").read_text(encoding="utf-8")
        idx_func = source.index("def run_research(")
        func_body = source[idx_func:]
        self.assertIn("DeprecationWarning", func_body)

    def test_real_observe_smoke_no_direct_pipeline(self):
        """real_observe_smoke 不得直接导入 ResearchPipeline。"""
        source = (_SRC / "research" / "real_observe_smoke.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "from src.research.research_pipeline import",
            source,
            "real_observe_smoke 不应直接导入 ResearchPipeline",
        )

    def test_real_observe_smoke_uses_runtime_service(self):
        """real_observe_smoke 必须通过 ResearchRuntimeService 执行。"""
        source = (_SRC / "research" / "real_observe_smoke.py").read_text(encoding="utf-8")
        self.assertIn("ResearchRuntimeService", source)

    def test_cycle_research_session_uses_runtime_service(self):
        """cycle_research_session 必须通过 ResearchRuntimeService 执行。"""
        source = (_SRC / "cycle" / "cycle_research_session.py").read_text(encoding="utf-8")
        self.assertIn("ResearchRuntimeService", source)
        self.assertNotIn("ResearchPipeline", source)

    def test_web_job_runner_uses_runtime_service(self):
        """Web research_job_runner 必须通过 ResearchRuntimeService 执行。"""
        source = (_SRC / "web" / "ops" / "research_job_runner.py").read_text(encoding="utf-8")
        self.assertIn("ResearchRuntimeService", source)
        self.assertNotIn("ResearchPipeline", source)

    def test_src_no_new_direct_pipeline_construction(self):
        """src/ 非 Pipeline 内部模块不得直接构造 ResearchPipeline。

        允许列表：
        - research_runtime_service.py（唯一合法消费者）
        - research_orchestrator.py（已弃用，有 DeprecationWarning）
        - research_pipeline.py 本身及其 phases/handlers
        - pipeline_orchestrator.py / pipeline_phase_handlers.py（内部组件）
        """
        import ast

        _ALLOWED_PIPELINE_FILES = {
            "research_runtime_service.py",
            "research_orchestrator.py",
            "research_pipeline.py",
            "pipeline_orchestrator.py",
            "pipeline_phase_handlers.py",
        }
        # Phase 内部文件也允许引用 Pipeline 类型
        _ALLOWED_DIRS = {"phases", "phase_handlers"}

        violations = []
        for py_file in _SRC.rglob("*.py"):
            if py_file.name in _ALLOWED_PIPELINE_FILES:
                continue
            if py_file.parent.name in _ALLOWED_DIRS:
                continue
            source = py_file.read_text(encoding="utf-8")
            if "ResearchPipeline(" not in source:
                continue
            # 排除注释和字符串中的引用 — 用简单行扫描
            for line_no, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                if "ResearchPipeline(" in stripped:
                    violations.append(f"{py_file.relative_to(_SRC)}:{line_no}")

        self.assertEqual(
            violations,
            [],
            f"以下文件直接构造 ResearchPipeline，应迁移至 ResearchRuntimeService: {violations}",
        )

    def test_examples_and_tools_no_direct_pipeline_construction(self):
        """examples/ 与 tools/ 中的脚本不得直接构造 ResearchPipeline。"""
        _PROJECT_ROOT = _SRC.parent
        scan_dirs = [_PROJECT_ROOT / "examples", _PROJECT_ROOT / "tools"]
        # tools/ 下的 _extract_observe_phase.py 和 _rebuild_observe_phase.py 仅做类型注解，不构造实例
        _TYPE_ANNOTATION_ONLY_FILES = {"_extract_observe_phase.py", "_rebuild_observe_phase.py"}

        violations = []
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob("*.py"):
                if py_file.name in _TYPE_ANNOTATION_ONLY_FILES:
                    continue
                source = py_file.read_text(encoding="utf-8")
                if "ResearchPipeline(" not in source:
                    continue
                for line_no, line in enumerate(source.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                        continue
                    if "ResearchPipeline(" in stripped:
                        violations.append(f"{py_file.relative_to(_PROJECT_ROOT)}:{line_no}")

        self.assertEqual(
            violations,
            [],
            f"以下 examples/tools 文件直接构造 ResearchPipeline，应迁移至 ResearchRuntimeService: {violations}",
        )


# ── Guard #18: RuntimeConfigAssembler 配置统一入口 ──────────────────────────


class TestRuntimeConfigAssemblerGuard(unittest.TestCase):
    """Guard #18: 配置加载统一走 RuntimeConfigAssembler / ConfigCenter，禁止直接读取 YAML。

    保护不变式：
    - Web auth 模块不直接 yaml.safe_load 读取 secrets 文件
    - routes/auth.py 通过 ConfigCenter (load_settings) 加载安全配置
    - dashboard settings_page 不直接调用 load_settings()（应从 app.state 获取）
    - api/dependencies.py 的 load_settings 兜底路径有 warning 日志
    - web/auth.py 不直接读取 secrets.yml YAML 文件
    """

    def test_web_auth_no_direct_yaml_read(self):
        """src/web/auth.py 不得包含 yaml.safe_load 对 secrets 文件的直接读取。"""
        source = (_SRC / "web" / "auth.py").read_text(encoding="utf-8")
        # 不应有 secrets_path 相关的 YAML 读取循环
        self.assertNotIn(
            "yaml_module.safe_load(secrets_path",
            source,
            "web/auth.py 不应直接 yaml.safe_load 读取 secrets 文件",
        )

    def test_routes_auth_no_direct_yaml_read(self):
        """src/web/routes/auth.py 不得包含 yaml.safe_load 对配置文件的直接读取。"""
        source = (_SRC / "web" / "routes" / "auth.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "yaml_module.safe_load(",
            source,
            "routes/auth.py 不应直接调用 yaml.safe_load",
        )
        self.assertNotIn(
            "yaml.safe_load(",
            source,
            "routes/auth.py 不应直接调用 yaml.safe_load",
        )

    def test_routes_auth_uses_config_center(self):
        """routes/auth.py 的 _load_security_config 应通过 load_settings 加载。"""
        source = (_SRC / "web" / "routes" / "auth.py").read_text(encoding="utf-8")
        idx_func = source.index("def _load_security_config(")
        next_def_pos = source.find("\ndef ", idx_func + 1)
        if next_def_pos == -1:
            next_def_pos = len(source)
        func_body = source[idx_func:next_def_pos]
        self.assertIn("load_settings", func_body)
        self.assertIn("get_secret_section", func_body)

    def test_dashboard_settings_page_uses_app_state(self):
        """dashboard settings_page 应优先从 request.app.state.settings 获取配置。"""
        source = (_SRC / "web" / "routes" / "dashboard.py").read_text(encoding="utf-8")
        idx_func = source.index("async def settings_page(")
        next_def_pos = source.find("\nasync def ", idx_func + 1)
        if next_def_pos == -1:
            next_def_pos = source.find("\ndef ", idx_func + 1)
        if next_def_pos == -1:
            next_def_pos = len(source)
        func_body = source[idx_func:next_def_pos]
        self.assertIn("request", func_body, "settings_page 应接受 request 参数")
        self.assertIn("app.state", func_body, "settings_page 应从 app.state 获取 settings")

    def test_api_dependencies_fallback_has_warning(self):
        """api/dependencies.py 的 load_settings 兜底路径应有 warning 日志。"""
        source = (_SRC / "api" / "dependencies.py").read_text(encoding="utf-8")
        # get_settings 函数应有 warning
        idx_func = source.index("def get_settings(")
        next_def_pos = source.find("\ndef ", idx_func + 1)
        if next_def_pos == -1:
            next_def_pos = len(source)
        func_body = source[idx_func:next_def_pos]
        self.assertIn("logger.warning", func_body)
        self.assertIn("RuntimeConfigAssembler", func_body)

    def test_no_new_direct_secrets_yaml_read_in_web(self):
        """src/web/ 下不得新增直接 yaml.safe_load 读取 secrets 文件的代码。

        允许列表为空 — 所有 web 模块应通过 ConfigCenter 读取密钥。
        """
        web_dir = _SRC / "web"
        violations = []
        for py_file in web_dir.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "safe_load(" in stripped and "secret" in source[max(0, source.find(stripped) - 200):source.find(stripped)].lower():
                    violations.append(f"{py_file.relative_to(_SRC)}:{line_no}")
                    break  # 每个文件只报一次
        self.assertEqual(violations, [], f"以下 web 文件直接读取 secrets YAML: {violations}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #19 — PG/Neo4j 事务边界、降级观测与回填治理
# ═══════════════════════════════════════════════════════════════════════

class TestPgNeo4jTxnDegradationBackfillGuard(unittest.TestCase):
    """Guard #19: PG/Neo4j 事务边界收敛、降级状态可观测、回填元数据标注。"""

    # ---- D-1: /health 端点不得硬编码 "ok" —————————————————————

    def test_api_health_not_hardcoded_ok(self):
        """src/api/app.py 的 /health 端点必须包含降级探测逻辑。"""
        source = (_SRC / "api" / "app.py").read_text(encoding="utf-8")
        # 旧代码: return {"status": "ok" ...} — 无降级检查
        # 新代码: 包含 "degraded" 关键词作为降级状态
        self.assertIn("degraded", source,
                       "api/app.py /health 端点必须包含 'degraded' 降级状态分支")

    def test_web_health_not_hardcoded_ok(self):
        """src/web/app.py 的 /health 端点必须包含 DB 可用性检查。"""
        source = (_SRC / "web" / "app.py").read_text(encoding="utf-8")
        self.assertIn("degraded", source,
                       "web/app.py /health 端点必须包含 'degraded' 降级状态分支")

    # ---- D-2: fallback persist 路径必须标记 storage_persistence ——

    def test_fallback_persist_writes_storage_persistence_metadata(self):
        """_persist_result_via_factory 必须在 cycle.metadata 中写入 storage_persistence。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        # 找到 _persist_result_via_factory 方法体
        idx = source.find("def _persist_result_via_factory")
        self.assertNotEqual(idx, -1, "_persist_result_via_factory 方法不存在")
        body = source[idx:idx + 3000]
        self.assertIn("storage_persistence", body,
                       "fallback persist 路径必须写入 storage_persistence 元数据")
        self.assertIn("needs_backfill", body,
                       "fallback persist 路径必须声明 needs_backfill")
        self.assertIn("factory_fallback", body,
                       "fallback persist 路径必须标记 mode 为 factory_fallback")

    # ---- A-2: analysis.py ORM 路径标记 needs_backfill ————————

    def test_analysis_persist_to_orm_marks_needs_backfill(self):
        """web/routes/analysis.py _persist_to_orm 必须在返回值中包含 needs_backfill。"""
        source = (_SRC / "web" / "routes" / "analysis.py").read_text(encoding="utf-8")
        idx = source.find("def _persist_to_orm")
        self.assertNotEqual(idx, -1, "_persist_to_orm 函数不存在")
        body = source[idx:idx + 5000]
        self.assertIn("needs_backfill", body,
                       "_persist_to_orm 必须在返回值中标注 needs_backfill")

    # ---- B-2: monitoring 一致性获取失败不得静默返回 None ———————

    def test_monitoring_consistency_fetch_not_silent_none(self):
        """monitoring._get_consistency_state_dict 失败时不得静默返回 None。"""
        source = (_SRC / "infrastructure" / "monitoring.py").read_text(encoding="utf-8")
        idx = source.find("def _get_consistency_state_dict")
        self.assertNotEqual(idx, -1, "_get_consistency_state_dict 方法不存在")
        body = source[idx:idx + 1500]
        # 不允许 except 块中直接 return None
        import re
        silent_none = re.search(r"except\s+Exception[^:]*:\s*\n\s*return\s+None", body)
        self.assertIsNone(silent_none,
                          "_get_consistency_state_dict except 块不得静默 return None，应返回降级字典")

    # ---- 主写路径必须保持 transaction() 语义 ——————————————

    def test_main_persist_uses_transaction_not_session_scope(self):
        """_persist_result_structured 必须使用 factory.transaction() 而非 session_scope()。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        idx = source.find("def _persist_result_structured")
        self.assertNotEqual(idx, -1, "_persist_result_structured 方法不存在")
        body = source[idx:idx + 4000]
        self.assertIn("factory.transaction()", body,
                       "主写路径必须使用 factory.transaction() 获取 TransactionCoordinator")


# ═══════════════════════════════════════════════════════════════════════
# Guard #20 — LLM 获取统一走 LLMGateway / CachedLLMService
# ═══════════════════════════════════════════════════════════════════════

class TestLLMGatewayUnificationGuard(unittest.TestCase):
    """Guard #20: 禁止 src/ 和 tools/ 直接 new LLMEngine，必须通过 get_llm_service。

    允许列表：
    - src/infra/llm_service.py — 工厂本身需要实例化 LLMEngine
    - src/llm/llm_engine.py — 引擎定义文件本身
    - tests/ — 测试代码可直接使用
    - examples/ — 示例代码可直接使用
    """

    # 允许直接 import/使用 LLMEngine 的文件（相对于 workspace root）
    _ALLOWLIST = {
        "src/infra/llm_service.py",
        "src/llm/llm_engine.py",
        "src/llm/__init__.py",
        # research_pipeline 通过 _try_import 延迟引入 LLMEngine 做类型引用，
        # 不直接实例化（无 LLMEngine( 调用），属于合法用法。
        "src/research/research_pipeline.py",
    }

    def _scan_for_direct_llm_engine(self, root: Path, label: str) -> list[str]:
        """扫描目录下所有 .py 文件，返回直接导入/实例化 LLMEngine 的违规列表。"""
        violations = []
        for py_file in root.rglob("*.py"):
            rel = py_file.relative_to(_WORKSPACE).as_posix()
            if rel in self._ALLOWLIST:
                continue
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # 检测 from src.llm.llm_engine import LLMEngine 或 LLMEngine(
                if "LLMEngine(" in stripped or (
                    "import" in stripped and "LLMEngine" in stripped
                    and "llm_service" not in stripped
                ):
                    violations.append(f"{rel}:{line_no}: {stripped[:120]}")
        return violations

    def test_src_no_direct_llm_engine(self):
        """src/ 业务代码不得直接 import 或实例化 LLMEngine（llm_service.py 工厂除外）。"""
        violations = self._scan_for_direct_llm_engine(_SRC, "src")
        self.assertEqual(violations, [],
                         f"以下 src/ 文件直接使用 LLMEngine，应改为 get_llm_service(): {violations}")

    def test_tools_no_direct_llm_engine(self):
        """tools/ 脚本不得直接 import 或实例化 LLMEngine，应通过 get_llm_service()。"""
        tools_dir = _WORKSPACE / "tools"
        if not tools_dir.exists():
            return
        violations = self._scan_for_direct_llm_engine(tools_dir, "tools")
        self.assertEqual(violations, [],
                         f"以下 tools/ 文件直接使用 LLMEngine，应改为 get_llm_service(): {violations}")

    def test_get_llm_service_is_canonical_entry(self):
        """src/infra/llm_service.py 必须导出 get_llm_service 函数。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("def get_llm_service(", source,
                       "llm_service.py 必须定义 get_llm_service 工厂函数")

    def test_cached_llm_service_wraps_engine(self):
        """CachedLLMService 必须在 llm_service.py 中定义并包含缓存逻辑。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("class CachedLLMService", source,
                       "llm_service.py 必须定义 CachedLLMService 类")
        self.assertIn("cache", source.lower(),
                       "CachedLLMService 必须包含缓存相关逻辑")

    def test_purpose_profiles_exist(self):
        """get_llm_service 必须在 _LLM_PURPOSE_PROFILES 中定义 translation 和 paper_plugin，
        且 get_llm_service 支持 default 用途（不在 profiles 中的 purpose 回退到全局配置）。
        """
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        # 显式 profile 条目
        for purpose in ("translation", "paper_plugin"):
            self.assertIn(f'"{purpose}"', source,
                          f'llm_service.py _LLM_PURPOSE_PROFILES 必须包含 "{purpose}"')
        # default 是 get_llm_service 的默认参数值
        self.assertIn('"default"', source,
                      'get_llm_service 必须以 "default" 作为默认 purpose')


# ═══════════════════════════════════════════════════════════════════════
# Guard #21 — ResearchDossierBuilder 存在性、接口契约与集成点
# ═══════════════════════════════════════════════════════════════════════

class TestResearchDossierBuilderGuard(unittest.TestCase):
    """Guard #21: ResearchDossierBuilder 模块契约。"""

    _DOSSIER_FILE = _SRC / "research" / "dossier_builder.py"

    def test_dossier_builder_module_exists(self):
        """src/research/dossier_builder.py 必须存在。"""
        self.assertTrue(self._DOSSIER_FILE.exists(),
                        "dossier_builder.py 模块不存在")

    def test_dossier_builder_class_exists(self):
        """模块必须导出 ResearchDossierBuilder 类。"""
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        self.assertIn("class ResearchDossierBuilder", source)

    def test_dossier_dataclass_exists(self):
        """模块必须导出 ResearchDossier 数据类。"""
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        self.assertIn("class ResearchDossier", source)

    def test_build_method_exists(self):
        """ResearchDossierBuilder 必须有 build() 方法。"""
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        self.assertIn("def build(", source)

    def test_dossier_has_serialization_methods(self):
        """ResearchDossier 必须支持 to_text / to_dict / to_json 序列化。"""
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        for method in ("def to_text(", "def to_dict(", "def to_json("):
            self.assertIn(method, source,
                          f"ResearchDossier 缺少 {method.split('(')[0]} 方法")

    def test_builder_uses_get_llm_service_not_llm_engine(self):
        """DossierBuilder 的 LLM 压缩必须通过 get_llm_service，不得直接 LLMEngine。"""
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        self.assertNotIn("from src.llm.llm_engine import", source,
                         "dossier_builder 不得直接 import LLMEngine")
        self.assertIn("get_llm_service", source,
                      "dossier_builder 必须通过 get_llm_service 获取 LLM")

    def test_pipeline_orchestrator_integrates_dossier(self):
        """pipeline_orchestrator.py 必须在 cycle 完成时构建 dossier。"""
        source = (_SRC / "research" / "pipeline_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("dossier_builder", source,
                      "pipeline_orchestrator 必须导入 dossier_builder")
        self.assertIn("research_dossier", source,
                      "pipeline_orchestrator 必须将 dossier 写入 cycle.metadata")

    def test_config_has_dossier_section(self):
        """config.yml iteration_cycle.research_pipeline 下必须有 dossier 配置节。"""
        import yaml
        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        ic = cfg.get("iteration_cycle", {})
        rp = ic.get("research_pipeline", {})
        dossier_cfg = rp.get("dossier", {})
        self.assertIn("max_context_tokens", dossier_cfg,
                      "config.yml iteration_cycle.research_pipeline.dossier 缺少 max_context_tokens")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #22 — LearningLoopOrchestrator 学习闭环编排器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLearningLoopOrchestratorGuard(unittest.TestCase):
    """Guard #22: LearningLoopOrchestrator 结构与集成约束。"""

    _MODULE_PATH = _WORKSPACE / "src" / "research" / "learning_loop_orchestrator.py"

    def test_module_exists(self):
        self.assertTrue(self._MODULE_PATH.exists(),
                        "src/research/learning_loop_orchestrator.py 必须存在")

    def test_class_importable(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator
        self.assertTrue(callable(LearningLoopOrchestrator))

    def test_lifecycle_methods_exist(self):
        """LearningLoopOrchestrator 必须提供完整生命周期方法。"""
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator
        required_methods = [
            "prepare_cycle",
            "inject_phase_context",
            "record_phase_learning",
            "execute_reflect_learning",
            "build_cycle_summary",
            "prepare_next_cycle_strategy",
        ]
        for name in required_methods:
            self.assertTrue(
                callable(getattr(LearningLoopOrchestrator, name, None)),
                f"LearningLoopOrchestrator 缺少方法: {name}",
            )

    def test_uses_canonical_learning_strategy_functions(self):
        """必须使用 learning_strategy 模块的 build_strategy_snapshot / build_strategy_diff。"""
        source = self._MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("build_strategy_snapshot", source)
        self.assertIn("build_strategy_diff", source)

    def test_does_not_bypass_self_learning_engine(self):
        """不得直接构造 SelfLearningEngine，应通过 pipeline.config 获取。"""
        source = self._MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("SelfLearningEngine(", source,
                         "LearningLoopOrchestrator 不应直接实例化 SelfLearningEngine")

    def test_runtime_service_uses_learning_loop(self):
        """ResearchRuntimeService 必须集成 LearningLoopOrchestrator。"""
        rts_path = _WORKSPACE / "src" / "orchestration" / "research_runtime_service.py"
        source = rts_path.read_text(encoding="utf-8")
        self.assertIn("LearningLoopOrchestrator", source,
                      "research_runtime_service.py 必须引用 LearningLoopOrchestrator")
        self.assertIn("prepare_cycle", source,
                      "research_runtime_service.py 应调用 prepare_cycle")

    def test_config_has_learning_loop_section(self):
        """config.yml iteration_cycle.research_pipeline 下必须有 learning_loop 配置节。"""
        import yaml
        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        ic = cfg.get("iteration_cycle", {})
        rp = ic.get("research_pipeline", {})
        ll_cfg = rp.get("learning_loop", {})
        self.assertIn("enabled", ll_cfg,
                      "config.yml iteration_cycle.research_pipeline.learning_loop 缺少 enabled")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #23 — EvidenceContract v2 平台级统一证据对象
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestEvidenceContractV2Guard(unittest.TestCase):
    """Guard #23: EvidenceContract v2 typed dataclasses 与 EvidenceEnvelope 结构约束。"""

    _MODULE_PATH = _WORKSPACE / "src" / "research" / "evidence_contract.py"

    def test_module_exists(self):
        self.assertTrue(self._MODULE_PATH.exists(),
                        "src/research/evidence_contract.py 必须存在")

    def test_typed_dataclasses_importable(self):
        """平台级统一证据对象必须可导入。"""
        from src.research.evidence_contract import (  # noqa: F401
            CONTRACT_VERSION,
            EvidenceClaim,
            EvidenceEnvelope,
            EvidenceGradeSummary,
            EvidenceProvenance,
            EvidenceRecord,
        )
        self.assertEqual(CONTRACT_VERSION, "evidence-claim-v2")

    def test_evidence_record_has_required_fields(self):
        """EvidenceRecord 必须包含 evidence_id, source_entity, target_entity, confidence, evidence_grade, provenance。"""
        from src.research.evidence_contract import EvidenceRecord
        record = EvidenceRecord()
        for field_name in ("evidence_id", "source_entity", "target_entity",
                           "confidence", "evidence_grade", "provenance"):
            self.assertTrue(hasattr(record, field_name),
                            f"EvidenceRecord 缺少字段: {field_name}")

    def test_evidence_claim_has_review_workflow(self):
        """EvidenceClaim 必须包含审核流程字段。"""
        from src.research.evidence_contract import EvidenceClaim
        claim = EvidenceClaim()
        for field_name in ("review_status", "needs_manual_review", "review_reasons",
                           "reviewer", "reviewed_at", "decision_basis"):
            self.assertTrue(hasattr(claim, field_name),
                            f"EvidenceClaim 缺少审核字段: {field_name}")

    def test_evidence_envelope_round_trip(self):
        """EvidenceEnvelope.from_dict(envelope.to_dict()) 必须无损往返。"""
        from src.research.evidence_contract import (
            EvidenceClaim,
            EvidenceEnvelope,
            EvidenceRecord,
        )
        original = EvidenceEnvelope(
            records=[EvidenceRecord(evidence_id="e1", source_entity="麻黄")],
            claims=[EvidenceClaim(claim_id="c1", evidence_ids=["e1"])],
        )
        d = original.to_dict()
        restored = EvidenceEnvelope.from_dict(d)
        self.assertEqual(restored.record_count, 1)
        self.assertEqual(restored.claim_count, 1)
        self.assertEqual(restored.records[0].evidence_id, "e1")

    def test_envelope_to_dict_compatible_with_protocol(self):
        """EvidenceEnvelope.to_dict() 必须输出与 build_evidence_protocol 兼容的键结构。"""
        from src.research.evidence_contract import EvidenceEnvelope
        d = EvidenceEnvelope().to_dict()
        required_keys = {"contract_version", "evidence_records", "claims",
                         "evidence_grade_summary", "citation_records", "contract"}
        self.assertTrue(required_keys.issubset(d.keys()),
                        f"EvidenceEnvelope.to_dict() 缺少键: {required_keys - d.keys()}")

    def test_build_evidence_protocol_uses_contract_version_constant(self):
        """build_evidence_protocol 必须引用 CONTRACT_VERSION 常量而非硬编码字符串。"""
        source = self._MODULE_PATH.read_text(encoding="utf-8")
        # The function body should use CONTRACT_VERSION, not a string literal
        # Find the build_evidence_protocol function and check
        self.assertIn('CONTRACT_VERSION', source,
                      "evidence_contract.py 必须定义 CONTRACT_VERSION 常量")
        # 确保 build_evidence_protocol 使用常量
        import re
        fn_match = re.search(
            r'def build_evidence_protocol\b.*?(?=\ndef\s|\Z)',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(fn_match, "找不到 build_evidence_protocol 函数")
        fn_body = fn_match.group(0)
        self.assertIn("CONTRACT_VERSION", fn_body,
                      "build_evidence_protocol 应使用 CONTRACT_VERSION 常量")

    def test_from_protocol_alias(self):
        """EvidenceEnvelope.from_protocol 必须存在且等效于 from_dict。"""
        from src.research.evidence_contract import EvidenceEnvelope
        self.assertTrue(callable(getattr(EvidenceEnvelope, "from_protocol", None)))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #24 — ModuleWiringManifest 模块接线状态清单
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestModuleWiringManifestGuard(unittest.TestCase):
    """Guard #24: ModuleWiringManifest 存在性、完整性与分类准确性。"""

    _MANIFEST_FILE = _SRC / "core" / "module_wiring_manifest.py"

    def test_manifest_module_exists(self):
        """src/core/module_wiring_manifest.py 必须存在。"""
        self.assertTrue(self._MANIFEST_FILE.exists(),
                        "module_wiring_manifest.py 模块不存在")

    def test_exports_module_manifest_dict(self):
        """模块必须导出 MODULE_MANIFEST 字典。"""
        from src.core.module_wiring_manifest import MODULE_MANIFEST
        self.assertIsInstance(MODULE_MANIFEST, dict)
        self.assertGreater(len(MODULE_MANIFEST), 30,
                           "MODULE_MANIFEST 应包含至少 30 个模块条目")

    def test_tier_constants_exported(self):
        """模块必须导出三个层级常量。"""
        from src.core.module_wiring_manifest import (
            TIER_ACTIVE,
            TIER_DORMANT,
            TIER_OPTIONAL,
            VALID_TIERS,
        )
        self.assertEqual({TIER_ACTIVE, TIER_OPTIONAL, TIER_DORMANT}, VALID_TIERS)

    def test_all_manifest_paths_exist(self):
        """清单中所有模块路径必须指向真实文件。"""
        from src.core.module_wiring_manifest import validate_manifest_paths
        missing = validate_manifest_paths(str(_WORKSPACE))
        self.assertEqual(
            missing, [],
            f"清单中有不存在的路径: {[m['module_key'] for m in missing]}",
        )

    def test_three_tiers_all_populated(self):
        """active / optional / dormant 三层都必须有至少一个条目。"""
        from src.core.module_wiring_manifest import (
            VALID_TIERS,
            get_manifest_summary,
        )
        s = get_manifest_summary()
        for tier in VALID_TIERS:
            self.assertGreater(s["counts"][tier], 0,
                               f"层级 {tier} 无任何模块条目")

    def test_core_pipeline_modules_are_active(self):
        """核心管线模块必须被标记为 active。"""
        from src.core.module_wiring_manifest import MODULE_MANIFEST
        core_keys = [
            "research_pipeline", "phase_orchestrator",
            "pipeline_orchestrator", "research_runtime_service",
        ]
        for key in core_keys:
            self.assertIn(key, MODULE_MANIFEST, f"缺少核心模块 {key}")
            self.assertEqual(MODULE_MANIFEST[key]["tier"], "active",
                             f"{key} 应为 active 层级")

    def test_deprecated_modules_are_dormant(self):
        """已弃用模块必须被标记为 dormant。"""
        from src.core.module_wiring_manifest import MODULE_MANIFEST
        self.assertEqual(
            MODULE_MANIFEST["research_orchestrator_deprecated"]["tier"],
            "dormant",
        )

    def test_config_gated_modules_are_optional(self):
        """需要配置标志的模块必须为 optional。"""
        from src.core.module_wiring_manifest import MODULE_MANIFEST
        for key in ("self_learning_engine", "neo4j_driver"):
            self.assertIn(key, MODULE_MANIFEST, f"缺少可选模块 {key}")
            self.assertEqual(MODULE_MANIFEST[key]["tier"], "optional",
                             f"{key} 应为 optional 层级")

    def test_query_api_functions_exist(self):
        """清单模块必须提供 get_modules_by_tier / get_manifest_summary / validate_manifest_paths。"""
        from src.core import module_wiring_manifest as m
        for fn_name in ("get_modules_by_tier", "get_manifest_summary",
                         "validate_manifest_paths"):
            self.assertTrue(callable(getattr(m, fn_name, None)),
                            f"module_wiring_manifest 缺少函数: {fn_name}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #25 — Neo4j Cypher 查询规范模板与文档反模式治理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestNeo4jCypherGovernanceGuard(unittest.TestCase):
    """Guard #25: Neo4j 查询规范模板存在性、lint 工具可用性、仓库合规性。"""

    def test_query_templates_module_exists(self):
        """tools/neo4j_query_templates.py 必须存在。"""
        self.assertTrue(
            (_WORKSPACE / "tools" / "neo4j_query_templates.py").exists(),
            "neo4j_query_templates.py 不存在",
        )

    def test_doc_lint_module_exists(self):
        """tools/cypher_doc_lint.py 必须存在。"""
        self.assertTrue(
            (_WORKSPACE / "tools" / "cypher_doc_lint.py").exists(),
            "cypher_doc_lint.py 不存在",
        )

    def test_canonical_read_templates_non_empty(self):
        """规范读查询模板至少包含 2 个条目。"""
        from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES
        self.assertGreaterEqual(len(CANONICAL_READ_TEMPLATES), 2)

    def test_canonical_write_templates_non_empty(self):
        """规范写查询模板至少包含 2 个条目。"""
        from tools.neo4j_query_templates import CANONICAL_WRITE_TEMPLATES
        self.assertGreaterEqual(len(CANONICAL_WRITE_TEMPLATES), 2)

    def test_anti_patterns_defined(self):
        """反模式列表至少包含 comma_separated_match。"""
        from tools.neo4j_query_templates import ANTI_PATTERNS
        names = {ap.name for ap in ANTI_PATTERNS}
        self.assertIn("comma_separated_match", names)

    def test_troubleshooting_templates_exist(self):
        """排障模板不为空且包含 cartesian_product_notification。"""
        from tools.neo4j_query_templates import TROUBLESHOOTING_TEMPLATES
        self.assertIn("cartesian_product_notification", TROUBLESHOOTING_TEMPLATES)

    def test_validate_cypher_snippet_api(self):
        """validate_cypher_snippet 函数可调用。"""
        from tools.neo4j_query_templates import validate_cypher_snippet
        self.assertTrue(callable(validate_cypher_snippet))

    def test_canonical_templates_pass_self_validation(self):
        """所有规范模板自身不得触发反模式检测。"""
        from tools.neo4j_query_templates import (
            CANONICAL_READ_TEMPLATES,
            CANONICAL_WRITE_TEMPLATES,
            validate_cypher_snippet,
        )
        for name, tpl in {**CANONICAL_READ_TEMPLATES, **CANONICAL_WRITE_TEMPLATES}.items():
            violations = validate_cypher_snippet(tpl["cypher"])
            self.assertEqual(violations, [],
                             f"规范模板 {name} 自身未通过检测")

    def test_repo_md_files_pass_cypher_lint(self):
        """仓库中所有 .md 文件的 Cypher 代码块不含已知反模式。"""
        from tools.cypher_doc_lint import lint_file
        md_files = list(_WORKSPACE.glob("*.md")) + list(_WORKSPACE.glob("docs/**/*.md"))
        all_violations = []
        for f in md_files:
            all_violations.extend(lint_file(f))
        self.assertEqual(
            all_violations, [],
            f"文档 Cypher 反模式: {[(v.file, v.line, v.rule) for v in all_violations]}",
        )

    def test_neo4j_driver_passes_cypher_lint(self):
        """neo4j_driver.py 不含 Cypher 反模式。"""
        from tools.cypher_doc_lint import lint_file
        driver = _WORKSPACE / "src" / "storage" / "neo4j_driver.py"
        if driver.exists():
            violations = lint_file(driver)
            self.assertEqual(violations, [],
                             f"neo4j_driver.py Cypher 违规: {[(v.line, v.rule) for v in violations]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #26 — LLM 任务适配性策略 (§10.1 职责分配)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLLMTaskPolicyGuard(unittest.TestCase):
    """Guard #26: LLM 任务适配性策略存在性、三级分类与集成点。"""

    _POLICY_FILE = _SRC / "infra" / "llm_task_policy.py"

    def test_policy_module_exists(self):
        """src/infra/llm_task_policy.py 必须存在。"""
        self.assertTrue(self._POLICY_FILE.exists(),
                        "llm_task_policy.py 模块不存在")

    def test_three_tier_enum(self):
        """SuitabilityTier 必须定义 suitable / cautious / unsuitable_solo 三级。"""
        from src.infra.llm_task_policy import SuitabilityTier
        self.assertEqual(
            {t.value for t in SuitabilityTier},
            {"suitable", "cautious", "unsuitable_solo"},
        )

    def test_task_policy_covers_audit_10_1(self):
        """TASK_POLICY 必须覆盖审计文档 §10.1 列出的所有任务类型。"""
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        # suitable 类
        for key in ("hypothesis_generation", "question_rewrite",
                     "terminology_explanation", "structured_summary",
                     "discussion_draft", "reflect_diagnosis"):
            self.assertIn(key, TASK_POLICY, f"缺少 §10.1 适合任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.SUITABLE)
        # cautious 类
        for key in ("long_form_generation", "graph_reasoning",
                     "unsupported_conclusion"):
            self.assertIn(key, TASK_POLICY, f"缺少 §10.1 谨慎任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.CAUTIOUS)
        # unsuitable_solo 类
        for key in ("large_evidence_synthesis", "end_to_end_research_judgment"):
            self.assertIn(key, TASK_POLICY, f"缺少 §10.1 不建议任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.UNSUITABLE_SOLO)

    def test_evaluate_api_exists(self):
        """evaluate_task / evaluate_purpose / check_suitability 函数必须可调用。"""
        from src.infra import llm_task_policy as m
        for fn_name in ("evaluate_task", "evaluate_purpose", "check_suitability"):
            self.assertTrue(callable(getattr(m, fn_name, None)),
                            f"llm_task_policy 缺少函数: {fn_name}")

    def test_purpose_task_map_covers_existing_purposes(self):
        """PURPOSE_TASK_MAP 必须覆盖已有的 get_llm_service purpose。"""
        from src.infra.llm_task_policy import PURPOSE_TASK_MAP
        for p in ("default", "translation", "paper_plugin"):
            self.assertIn(p, PURPOSE_TASK_MAP,
                          f"PURPOSE_TASK_MAP 缺少现有 purpose: {p}")

    def test_get_llm_service_integrates_policy(self):
        """get_llm_service 源码必须调用 check_suitability。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("check_suitability", source,
                      "get_llm_service 必须集成 check_suitability 调用")

    def test_config_has_task_policy_section(self):
        """config.yml models.llm 下必须有 task_policy 配置节。"""
        import yaml
        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        llm_cfg = cfg.get("models", {}).get("llm", {})
        tp_cfg = llm_cfg.get("task_policy", {})
        self.assertIn("enabled", tp_cfg,
                      "config.yml models.llm.task_policy 缺少 enabled")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #27 — Prompt Registry + JSON Schema 输出约束 (§10.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPromptRegistryGuard(unittest.TestCase):
    """Guard #27: Prompt Registry 与 JSON Schema 输出约束必须存在并接入主路径。"""

    _REGISTRY_FILE = _SRC / "infra" / "prompt_registry.py"

    def test_prompt_registry_module_exists(self):
        """src/infra/prompt_registry.py 必须存在。"""
        self.assertTrue(self._REGISTRY_FILE.exists(),
                        "prompt_registry.py 模块不存在")

    def test_prompt_registry_covers_high_value_structured_tasks(self):
        """注册表必须覆盖 GapAnalyzer / HypothesisEngine / ResearchAdvisor。"""
        from src.infra.prompt_registry import PROMPT_REGISTRY
        for name in (
            "research_advisor.hypothesis_suggestion",
            "research_advisor.experiment_design",
            "research_advisor.novelty_evaluation",
            "gap_analyzer.structured_report",
            "hypothesis_engine.default_hypothesis",
            "hypothesis_engine.kg_enhanced",
        ):
            self.assertIn(name, PROMPT_REGISTRY, f"Prompt Registry 缺少: {name}")

    def test_render_and_parse_apis_exist(self):
        """render_prompt / parse_registered_output API 必须可调用。"""
        from src.infra import prompt_registry as m
        for fn_name in ("render_prompt", "parse_registered_output", "get_registry_summary"):
            self.assertTrue(callable(getattr(m, fn_name, None)),
                            f"prompt_registry 缺少函数: {fn_name}")

    def test_llm_service_exposes_generate_registered(self):
        """LLMService 必须提供 generate_registered 便捷入口。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("def generate_registered", source,
                      "LLMService 必须提供 generate_registered()")

    def test_config_has_prompt_registry_section(self):
        """config.yml models.llm 下必须有 prompt_registry 配置节。"""
        import yaml
        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        llm_cfg = cfg.get("models", {}).get("llm", {})
        registry_cfg = llm_cfg.get("prompt_registry", {})
        self.assertIn("enabled", registry_cfg,
                      "config.yml models.llm.prompt_registry 缺少 enabled")
        self.assertIn("include_schema_in_prompt", registry_cfg,
                      "config.yml models.llm.prompt_registry 缺少 include_schema_in_prompt")

    def test_high_value_modules_use_prompt_registry(self):
        """关键模块源码必须接入 render_prompt / parse_registered_output。"""
        for relative in (
            _SRC / "research" / "gap_analyzer.py",
            _SRC / "research" / "hypothesis_engine.py",
            _SRC / "ai_assistant" / "research_advisor.py",
        ):
            source = relative.read_text(encoding="utf-8")
            self.assertIn("render_prompt", source,
                          f"{relative.name} 尚未接入 render_prompt")
            self.assertIn("parse_registered_output", source,
                          f"{relative.name} 尚未接入 parse_registered_output")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #28 — Observe / Analyze / Publish phase dossier 压缩器 (§10.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPhaseDossierGuard(unittest.TestCase):
    """Guard #28: phase-specific dossier builder、metadata 存储和 Publish 接线必须存在。"""

    _DOSSIER_FILE = _SRC / "research" / "dossier_builder.py"
    _PIPELINE_ORCHESTRATOR = _SRC / "research" / "pipeline_orchestrator.py"
    _PUBLISH_PHASE = _SRC / "research" / "phases" / "publish_phase.py"

    def test_dossier_builder_exposes_phase_specific_apis(self):
        source = self._DOSSIER_FILE.read_text(encoding="utf-8")
        for method_name in (
            "def build_phase_dossier(",
            "def build_phase_dossiers(",
            "def build_observe_dossier(",
            "def build_analyze_dossier(",
            "def build_publish_dossier(",
        ):
            self.assertIn(method_name, source,
                          f"ResearchDossierBuilder 缺少 phase dossier API: {method_name}")

    def test_pipeline_orchestrator_persists_phase_dossiers(self):
        source = self._PIPELINE_ORCHESTRATOR.read_text(encoding="utf-8")
        self.assertIn("phase_dossiers", source,
                      "pipeline_orchestrator 必须把 phase dossier 写入 cycle.metadata['phase_dossiers']")
        self.assertIn("_sync_phase_dossier_metadata", source,
                      "pipeline_orchestrator 缺少单阶段 dossier 同步逻辑")
        self.assertIn("_attach_phase_dossiers_to_phase_context", source,
                      "pipeline_orchestrator 缺少 phase dossier 注入 phase_context 逻辑")

    def test_publish_phase_consumes_phase_dossiers(self):
        source = self._PUBLISH_PHASE.read_text(encoding="utf-8")
        for marker in ("observe_dossier", "analyze_dossier", "phase_dossiers", "paper_draft"):
            self.assertIn(marker, source,
                          f"publish_phase 缺少 phase dossier / paper_draft 集成标记: {marker}")

    def test_config_has_phase_dossier_settings(self):
        import yaml
        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        dossier_cfg = cfg.get("iteration_cycle", {}).get("research_pipeline", {}).get("dossier", {})
        self.assertIn("build_phase_dossiers", dossier_cfg,
                      "config.yml dossier 配置缺少 build_phase_dossiers")
        self.assertIn("attach_phase_dossiers_to_context", dossier_cfg,
                      "config.yml dossier 配置缺少 attach_phase_dossiers_to_context")
        phase_budget_cfg = dossier_cfg.get("phase_max_context_tokens", {})
        self.assertEqual(
            sorted(phase_budget_cfg.keys()),
            ["analyze", "observe", "publish"],
            "config.yml dossier.phase_max_context_tokens 必须覆盖 observe/analyze/publish",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #29 — prompt / evidence / artifact 分层缓存 (§10.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLayeredCacheGuard(unittest.TestCase):
    """Guard #29: 分层缓存基础设施与主路径接入必须存在。"""

    _LAYERED_CACHE = _SRC / "infra" / "layered_cache.py"
    _PROMPT_REGISTRY = _SRC / "infra" / "prompt_registry.py"
    _EVIDENCE_CONTRACT = _SRC / "research" / "evidence_contract.py"
    _OUTPUT_GENERATOR = _SRC / "generation" / "output_formatter.py"

    def test_layered_cache_module_exists(self):
        self.assertTrue(self._LAYERED_CACHE.exists(),
                        "layered_cache.py 模块不存在")

    def test_layered_cache_exposes_expected_apis(self):
        from src.infra import layered_cache as m

        self.assertTrue(callable(getattr(m, "load_layered_cache_settings", None)))
        self.assertTrue(callable(getattr(m, "get_layered_task_cache", None)))
        self.assertTrue(callable(getattr(m, "stable_cache_json", None)))
        self.assertTrue(callable(getattr(m, "describe_llm_engine", None)))
        self.assertTrue(callable(getattr(m, "LayeredTaskCache", None)))

    def test_config_has_layered_cache_section(self):
        import yaml

        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        layered_cfg = cfg.get("iteration_cycle", {}).get("research_pipeline", {}).get("layered_cache", {})
        self.assertIn("enabled", layered_cfg,
                      "config.yml research_pipeline.layered_cache 缺少 enabled")
        self.assertIn("cache_dir", layered_cfg,
                      "config.yml research_pipeline.layered_cache 缺少 cache_dir")
        self.assertEqual(
            sorted(key for key in layered_cfg.keys() if key in {"prompt", "evidence", "artifact"}),
            ["artifact", "evidence", "prompt"],
            "layered_cache 必须覆盖 prompt/evidence/artifact 三层",
        )

    def test_prompt_evidence_artifact_paths_use_layered_cache(self):
        prompt_source = self._PROMPT_REGISTRY.read_text(encoding="utf-8")
        evidence_source = self._EVIDENCE_CONTRACT.read_text(encoding="utf-8")
        artifact_source = self._OUTPUT_GENERATOR.read_text(encoding="utf-8")

        self.assertIn("prompt-cache-v1", prompt_source,
                      "prompt_registry 缺少 prompt cache 接线")
        self.assertIn("call_registered_prompt", prompt_source,
                      "prompt_registry 必须提供 call_registered_prompt")
        self.assertIn("evidence-cache-v1", evidence_source,
                      "evidence_contract 缺少 evidence cache 接线")
        self.assertIn("artifact-cache-v1", artifact_source,
                      "output_formatter 缺少 artifact cache 接线")
        self.assertIn("get_layered_task_cache", prompt_source)
        self.assertIn("get_layered_task_cache", evidence_source)
        self.assertIn("get_layered_task_cache", artifact_source)

    def test_high_value_modules_route_registered_prompts_through_cache_helper(self):
        for relative in (
            _SRC / "research" / "gap_analyzer.py",
            _SRC / "research" / "hypothesis_engine.py",
            _SRC / "ai_assistant" / "research_advisor.py",
        ):
            source = relative.read_text(encoding="utf-8")
            self.assertIn("call_registered_prompt", source,
                          f"{relative.name} 尚未通过 call_registered_prompt 接入 prompt cache")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Guard #30 — token budget policy (§10.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTokenBudgetPolicyGuard(unittest.TestCase):
    """Guard #30: 统一 token budget policy 与主路径接线必须存在。"""

    _POLICY_FILE = _SRC / "infra" / "token_budget_policy.py"
    _PROMPT_REGISTRY_FILE = _SRC / "infra" / "prompt_registry.py"
    _LLM_SERVICE_FILE = _SRC / "infra" / "llm_service.py"

    def test_policy_module_exists(self):
        self.assertTrue(self._POLICY_FILE.exists(),
                        "token_budget_policy.py 模块不存在")

    def test_policy_exports_expected_apis(self):
        from src.infra import token_budget_policy as m

        for fn_name in (
            "load_token_budget_policy_settings",
            "reset_token_budget_policy_settings_cache",
            "estimate_text_tokens",
            "resolve_token_budget",
            "apply_token_budget_to_prompt",
        ):
            self.assertTrue(callable(getattr(m, fn_name, None)),
                            f"token_budget_policy 缺少函数: {fn_name}")

    def test_prompt_registry_integrates_policy(self):
        source = self._PROMPT_REGISTRY_FILE.read_text(encoding="utf-8")
        self.assertIn("apply_token_budget_to_prompt", source,
                      "prompt_registry 必须集成 apply_token_budget_to_prompt")
        self.assertIn("suffix_prompt=schema_instruction", source,
                      "prompt_registry 必须保留 schema 尾部预算")

    def test_llm_service_integrates_policy(self):
        source = self._LLM_SERVICE_FILE.read_text(encoding="utf-8")
        self.assertIn("apply_token_budget_to_prompt", source,
                      "llm_service 必须集成 apply_token_budget_to_prompt")
        self.assertIn("purpose=self._purpose", source,
                      "CachedLLMService.generate 必须携带 purpose 做兜底预算")

    def test_config_has_token_budget_policy_section(self):
        import yaml

        config_path = _WORKSPACE / "config.yml"
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        policy_cfg = cfg.get("models", {}).get("llm", {}).get("token_budget_policy", {})
        self.assertIn("enabled", policy_cfg,
                      "config.yml models.llm.token_budget_policy 缺少 enabled")
        self.assertIn("default_input_tokens", policy_cfg,
                      "config.yml models.llm.token_budget_policy 缺少 default_input_tokens")
        self.assertIn("reserve_output_tokens", policy_cfg,
                      "config.yml models.llm.token_budget_policy 缺少 reserve_output_tokens")
        self.assertIn("task_input_budgets", policy_cfg,
                      "config.yml models.llm.token_budget_policy 缺少 task_input_budgets")
        self.assertIn("purpose_input_budgets", policy_cfg,
                      "config.yml models.llm.token_budget_policy 缺少 purpose_input_budgets")


# ═══════════════════════════════════════════════════════════════════════
# Guard #31 — 存储治理组件强一致基础设施
# ═══════════════════════════════════════════════════════════════════════


class TestStorageGovernanceInfraGuard(unittest.TestCase):
    """Guard #31: StorageBackendFactory 必须集成 DegradationGovernor / BackfillLedger / StorageObservability。

    保护不变式：
    - backend_factory.py 导入三大治理组件
    - StorageBackendFactory.__init__ 初始化三个组件属性
    - StorageBackendFactory 暴露 degradation_governor / backfill_ledger / observability 属性
    - factory.transaction() 在 commit 后记录 observability 与 governor
    - factory.get_governance_report() 方法存在
    - DegradationGovernor 模块存在且包含 set_initial_mode / record_transaction_result / to_governance_report
    - BackfillLedger 模块存在且包含 record_pending / mark_completed / get_summary
    - StorageObservability 模块存在且包含 record / get_health_report
    """

    def test_factory_imports_governance_components(self):
        """backend_factory.py 必须导入三大治理组件。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("DegradationGovernor", source)
        self.assertIn("BackfillLedger", source)
        self.assertIn("StorageObservability", source)

    def test_factory_initializes_governance_in_init(self):
        """StorageBackendFactory.__init__ 必须创建 _degradation_governor / _backfill_ledger / _observability。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("self._degradation_governor", source)
        self.assertIn("self._backfill_ledger", source)
        self.assertIn("self._observability", source)

    def test_factory_exposes_governance_properties(self):
        """StorageBackendFactory 必须暴露三个治理属性。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("def degradation_governor(self)", source)
        self.assertIn("def backfill_ledger(self)", source)
        self.assertIn("def observability(self)", source)

    def test_factory_transaction_records_observability(self):
        """factory.transaction() commit 后必须调用 observability.record 与 governor.record_transaction_result。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("self._observability.record(", source)
        self.assertIn("self._degradation_governor.record_transaction_result(", source)

    def test_factory_has_get_governance_report(self):
        """StorageBackendFactory 必须提供 get_governance_report 方法。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("def get_governance_report(self)", source)

    def test_degradation_governor_module_structure(self):
        """degradation_governor.py 必须实现核心 API。"""
        source = (_SRC / "storage" / "degradation_governor.py").read_text(encoding="utf-8")
        for method in ("set_initial_mode", "record_transaction_result", "to_governance_report", "is_production_ready"):
            self.assertIn(method, source, f"DegradationGovernor 缺少 {method}")

    def test_backfill_ledger_module_structure(self):
        """backfill_ledger.py 必须实现核心 API。"""
        source = (_SRC / "storage" / "backfill_ledger.py").read_text(encoding="utf-8")
        for method in ("record_pending", "record_from_transaction_result", "mark_completed", "get_pending", "get_summary"):
            self.assertIn(method, source, f"BackfillLedger 缺少 {method}")

    def test_observability_module_structure(self):
        """observability.py 必须实现核心 API。"""
        source = (_SRC / "storage" / "observability.py").read_text(encoding="utf-8")
        for method in ("record", "get_health_report", "get_recent_failures"):
            self.assertIn(method, source, f"StorageObservability 缺少 {method}")

    def test_factory_initialize_sets_governor_mode(self):
        """factory.initialize() 必须在初始化后设置 governor 初始模式。"""
        source = (_SRC / "storage" / "backend_factory.py").read_text(encoding="utf-8")
        self.assertIn("_degradation_governor.set_initial_mode", source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #32 — 学习闭环策略调整与外部导入质量校验基础设施
# ═══════════════════════════════════════════════════════════════════════


class TestLearningLoopPhaseDGuard(unittest.TestCase):
    """Guard #32: LearningLoopOrchestrator 集成 PolicyAdjuster，ExperimentExecutionPhase 集成 ImportQualityValidator。

    保护不变式：
    - PolicyAdjuster 模块存在且包含 adjust / get_active_policy / get_evidence_policy / get_policy_history
    - ImportQualityValidator 模块存在且包含 validate_records / validate_relationships
    - LearningLoopOrchestrator 导入并使用 PolicyAdjuster
    - LearningLoopOrchestrator.execute_reflect_learning 调用 policy_adjuster.adjust
    - LearningLoopOrchestrator.prepare_next_cycle_strategy 输出包含 evidence_policy
    - ExperimentExecutionPhase 导入并使用 ImportQualityValidator
    """

    def test_policy_adjuster_module_exists(self):
        """policy_adjuster.py 必须实现核心 API。"""
        source = (_SRC / "learning" / "policy_adjuster.py").read_text(encoding="utf-8")
        for method in ("def adjust(", "get_active_policy", "get_evidence_policy", "get_policy_history"):
            self.assertIn(method, source, f"PolicyAdjuster 缺少 {method}")

    def test_import_quality_validator_module_exists(self):
        """import_quality_validator.py 必须实现核心 API。"""
        source = (_SRC / "research" / "import_quality_validator.py").read_text(encoding="utf-8")
        for method in ("validate_records", "validate_relationships", "ValidationReport", "ValidationSeverity"):
            self.assertIn(method, source, f"ImportQualityValidator 缺少 {method}")

    def test_orchestrator_imports_policy_adjuster(self):
        """LearningLoopOrchestrator 必须导入 PolicyAdjuster。"""
        source = (_SRC / "research" / "learning_loop_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("from src.learning.policy_adjuster import PolicyAdjuster", source)

    def test_orchestrator_initializes_policy_adjuster(self):
        """LearningLoopOrchestrator.__init__ 必须创建 _policy_adjuster。"""
        source = (_SRC / "research" / "learning_loop_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("self._policy_adjuster = PolicyAdjuster()", source)

    def test_orchestrator_calls_adjust_in_reflect(self):
        """execute_reflect_learning 必须调用 _policy_adjuster.adjust。"""
        source = (_SRC / "research" / "learning_loop_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("self._policy_adjuster.adjust(", source)

    def test_orchestrator_outputs_evidence_policy(self):
        """prepare_next_cycle_strategy 必须输出 evidence_policy。"""
        source = (_SRC / "research" / "learning_loop_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("evidence_policy", source)
        self.assertIn("template_preferences", source)

    def test_experiment_execution_imports_validator(self):
        """ExperimentExecutionPhase 必须导入 ImportQualityValidator。"""
        source = (_SRC / "research" / "phases" / "experiment_execution_phase.py").read_text(encoding="utf-8")
        self.assertIn("from src.research.import_quality_validator import ImportQualityValidator", source)

    def test_experiment_execution_calls_validate(self):
        """ExperimentExecutionPhase 必须调用 _validate_import_quality。"""
        source = (_SRC / "research" / "phases" / "experiment_execution_phase.py").read_text(encoding="utf-8")
        self.assertIn("self._validate_import_quality(", source)
        self.assertIn("import_quality_validation", source)

    def test_policy_adjuster_evidence_grade_constants(self):
        """PolicyAdjuster 必须定义证据等级常量。"""
        source = (_SRC / "learning" / "policy_adjuster.py").read_text(encoding="utf-8")
        self.assertIn("_EVIDENCE_GRADES", source)
        self.assertIn("_CONFIDENCE_BOUNDS", source)

    def test_import_validator_strictness_levels(self):
        """ImportQualityValidator 必须支持 strict/standard/lenient 三级。"""
        source = (_SRC / "research" / "import_quality_validator.py").read_text(encoding="utf-8")
        for level in ("STRICT", "STANDARD", "LENIENT"):
            self.assertIn(level, source, f"ImportQualityValidator 缺少 strictness 等级 {level}")


# ═══════════════════════════════════════════════════════════════════════
# Guard #33 — 小模型优化基础设施（ReasoningTemplateSelector / DynamicInvocationStrategy / DossierLayerCompressor / SmallModelOptimizer）
# ═══════════════════════════════════════════════════════════════════════


class TestPhaseELLMOptimizationGuard(unittest.TestCase):
    """Guard #33: 小模型优化组件存在性、接口契约与集成点保护。

    保护不变式：
    - ReasoningTemplateSelector 必须存在且包含 select / 5 个框架
    - DynamicInvocationStrategy 必须存在且包含 decide / record_completion / get_cost_report
    - DossierLayerCompressor 必须存在且包含 compress / 三层配置
    - SmallModelOptimizer 必须存在且集成三组件
    - llm_service.py 必须暴露 get_small_model_optimizer 入口
    """

    def test_reasoning_template_selector_exists(self):
        """reasoning_template_selector.py 必须实现核心 API。"""
        source = (_SRC / "infra" / "reasoning_template_selector.py").read_text(encoding="utf-8")
        for method in ("class ReasoningTemplateSelector", "def select(", "SelectionResult", "ReasoningFramework"):
            self.assertIn(method, source, f"ReasoningTemplateSelector 缺少 {method}")

    def test_reasoning_template_selector_has_five_frameworks(self):
        """必须有 5 个推理框架。"""
        source = (_SRC / "infra" / "reasoning_template_selector.py").read_text(encoding="utf-8")
        for fw in ("analytical", "dialectical", "comparative", "evidential", "concise"):
            self.assertIn(fw, source, f"缺少推理框架: {fw}")

    def test_dynamic_invocation_strategy_exists(self):
        """dynamic_invocation_strategy.py 必须实现核心 API。"""
        source = (_SRC / "infra" / "dynamic_invocation_strategy.py").read_text(encoding="utf-8")
        for method in ("class DynamicInvocationStrategy", "def decide(", "def record_completion(", "def get_cost_report("):
            self.assertIn(method, source, f"DynamicInvocationStrategy 缺少 {method}")

    def test_dynamic_invocation_strategy_actions(self):
        """必须支持 proceed/decompose/skip/retry_simplified 四种动作。"""
        source = (_SRC / "infra" / "dynamic_invocation_strategy.py").read_text(encoding="utf-8")
        for action in ("proceed", "decompose", "skip", "retry_simplified"):
            self.assertIn(f'"{action}"', source, f"缺少调用动作: {action}")

    def test_dossier_layer_compressor_exists(self):
        """dossier_layer_compressor.py 必须实现核心 API。"""
        source = (_SRC / "infra" / "dossier_layer_compressor.py").read_text(encoding="utf-8")
        for method in ("class DossierLayerCompressor", "def compress(", "LayeredDossier", "CompressedLayer"):
            self.assertIn(method, source, f"DossierLayerCompressor 缺少 {method}")

    def test_dossier_layer_compressor_three_layers(self):
        """必须配置 3 个层级 (0=critical, 1=core, 2=full)。"""
        source = (_SRC / "infra" / "dossier_layer_compressor.py").read_text(encoding="utf-8")
        self.assertIn("0: 512", source)
        self.assertIn("1: 1536", source)
        self.assertIn("2: 3072", source)

    def test_small_model_optimizer_exists(self):
        """small_model_optimizer.py 必须实现核心 API。"""
        source = (_SRC / "infra" / "small_model_optimizer.py").read_text(encoding="utf-8")
        for method in ("class SmallModelOptimizer", "def prepare_call(", "CallPlan", "def get_cost_report("):
            self.assertIn(method, source, f"SmallModelOptimizer 缺少 {method}")

    def test_small_model_optimizer_integrates_all_three(self):
        """SmallModelOptimizer 必须导入并集成三组件。"""
        source = (_SRC / "infra" / "small_model_optimizer.py").read_text(encoding="utf-8")
        self.assertIn("from src.infra.reasoning_template_selector import", source)
        self.assertIn("from src.infra.dynamic_invocation_strategy import", source)
        self.assertIn("from src.infra.dossier_layer_compressor import", source)

    def test_llm_service_exposes_optimizer_entry_point(self):
        """llm_service.py 必须暴露 get_small_model_optimizer。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("def get_small_model_optimizer(", source)
        self.assertIn("SmallModelOptimizer", source)

    def test_llm_service_exposes_planned_call_helper(self):
        """llm_service.py 必须暴露 planner helper。"""
        source = (_SRC / "infra" / "llm_service.py").read_text(encoding="utf-8")
        self.assertIn("class PlannedLLMCall", source)
        self.assertIn("def prepare_planned_llm_call(", source)

    def test_call_plan_has_should_call_llm(self):
        """CallPlan 必须有 should_call_llm 属性。"""
        source = (_SRC / "infra" / "small_model_optimizer.py").read_text(encoding="utf-8")
        self.assertIn("should_call_llm", source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #39 — SmallModelOptimizer 默认执行路径接线
# ═══════════════════════════════════════════════════════════════════════


class TestPhaseISmallModelPlannerWiringGuard(unittest.TestCase):
    """Guard #39: hypothesis / quality / reflect / experiment 必须接入 planner helper。"""

    def test_hypothesis_engine_uses_planner_helper(self):
        source = (_SRC / "research" / "hypothesis_engine.py").read_text(encoding="utf-8")
        self.assertIn("prepare_planned_llm_call", source)

    def test_quality_assessor_uses_planner_helper(self):
        source = (_SRC / "quality" / "quality_assessor.py").read_text(encoding="utf-8")
        self.assertIn("prepare_planned_llm_call", source)

    def test_reflect_phase_uses_planner_helper(self):
        source = (_SRC / "research" / "phases" / "reflect_phase.py").read_text(encoding="utf-8")
        self.assertIn("prepare_planned_llm_call", source)

    def test_experiment_designer_uses_planner_helper(self):
        source = (_SRC / "research" / "experiment_designer.py").read_text(encoding="utf-8")
        self.assertIn("prepare_planned_llm_call", source)

    def test_publish_phase_exposes_section_planner_preview(self):
        source = (_SRC / "research" / "phases" / "publish_phase.py").read_text(encoding="utf-8")
        self.assertIn("prepare_planned_llm_call", source)
        self.assertIn("publish_section_plans", source)
        self.assertIn("deterministic_paper_writer", source)

    def test_phase_result_common_metadata_has_small_model_keys(self):
        source = (_SRC / "research" / "phase_result.py").read_text(encoding="utf-8")
        self.assertIn("small_model_plan", source)
        self.assertIn("llm_cost_report", source)
        self.assertIn("fallback_path", source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #34 — EvidenceEnvelope 跨阶段 phase_origin 统一协议 (Phase F-1)
# ═══════════════════════════════════════════════════════════════════════


class TestEvidenceEnvelopePhasOriginGuard(unittest.TestCase):
    """Guard #34: 所有 7 阶段 phase mixin 产出的 evidence_protocol 必须遵循 evidence-claim-v2 信封。

    保护不变式：
    - EvidenceEnvelope 必须包含 phase_origin 字段
    - build_phase_evidence_protocol 必须可导入
    - get_evidence_protocol helper 必须存在于 phase_result.py
    - 5 个非 publish/synthesize 的 phase mixin 必须 import evidence_contract
    """

    def test_evidence_envelope_has_phase_origin(self):
        """EvidenceEnvelope 数据类必须包含 phase_origin 字段。"""
        source = (_SRC / "research" / "evidence_contract.py").read_text(encoding="utf-8")
        self.assertIn("phase_origin", source, "EvidenceEnvelope 缺少 phase_origin 字段")

    def test_build_phase_evidence_protocol_exists(self):
        """build_phase_evidence_protocol 函数必须存在。"""
        source = (_SRC / "research" / "evidence_contract.py").read_text(encoding="utf-8")
        self.assertIn("def build_phase_evidence_protocol(", source)

    def test_phase_result_has_get_evidence_protocol(self):
        """phase_result.py 必须暴露 get_evidence_protocol helper。"""
        source = (_SRC / "research" / "phase_result.py").read_text(encoding="utf-8")
        self.assertIn("def get_evidence_protocol(", source)

    def test_observe_phase_imports_evidence(self):
        """observe_phase.py 必须导入 evidence_contract。"""
        source = (_SRC / "research" / "phases" / "observe_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)

    def test_hypothesis_phase_imports_evidence(self):
        """hypothesis_phase.py 必须导入 evidence_contract。"""
        source = (_SRC / "research" / "phases" / "hypothesis_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)

    def test_experiment_execution_phase_imports_evidence(self):
        """experiment_execution_phase.py 必须导入 evidence_contract。"""
        source = (_SRC / "research" / "phases" / "experiment_execution_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)

    def test_reflect_phase_imports_evidence(self):
        """reflect_phase.py 必须导入 evidence_contract。"""
        source = (_SRC / "research" / "phases" / "reflect_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)

    def test_analyze_phase_sets_phase_origin(self):
        """analyze_phase.py 必须设置 phase_origin。"""
        source = (_SRC / "research" / "phases" / "analyze_phase.py").read_text(encoding="utf-8")
        self.assertIn("phase_origin", source)

    def test_experiment_phase_imports_evidence(self):
        """experiment_phase.py 必须导入 build_phase_evidence_protocol 并产出 evidence_protocol。"""
        source = (_SRC / "research" / "phases" / "experiment_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)
        self.assertIn("evidence_protocol", source)

    def test_publish_phase_imports_phase_evidence(self):
        """publish_phase.py 必须导入 build_phase_evidence_protocol 并产出 evidence_protocol。"""
        source = (_SRC / "research" / "phases" / "publish_phase.py").read_text(encoding="utf-8")
        self.assertIn("build_phase_evidence_protocol", source)
        self.assertIn('"evidence_protocol"', source)


# ═══════════════════════════════════════════════════════════════════════
# Guard #35 — Phase output 形状收口 (Phase F-3)
# ═══════════════════════════════════════════════════════════════════════


class TestPhaseOutputShapeGuard(unittest.TestCase):
    """Guard #35: phase_result.py 必须定义公约键常量，build_phase_result 自动注入。

    保护不变式：
    - PHASE_RESULT_COMMON_RESULT_KEYS / PHASE_RESULT_COMMON_METADATA_KEYS 必须可导入
    - build_phase_result 输出的 results / metadata 包含公约键
    - observe metadata 必须有 learning 和 learning_strategy_applied
    - reflect extra_fields 不再包含与 results 完全重复的键
    - experiment_execution results 包含 execution_boundary 子对象
    """

    def test_common_keys_importable(self):
        """phase_result.py 必须导出公约键常量。"""
        source = (_SRC / "research" / "phase_result.py").read_text(encoding="utf-8")
        self.assertIn("PHASE_RESULT_COMMON_RESULT_KEYS", source)
        self.assertIn("PHASE_RESULT_COMMON_METADATA_KEYS", source)

    def test_build_phase_result_injects_common_result_keys(self):
        """build_phase_result 输出 results 必须包含 evidence_protocol 和 summary。"""
        source = (_SRC / "research" / "phase_result.py").read_text(encoding="utf-8")
        self.assertIn("PHASE_RESULT_COMMON_RESULT_KEYS", source)
        self.assertIn("setdefault", source)

    def test_observe_phase_has_learning_metadata(self):
        """observe_phase.py 必须在 metadata 中设置 learning。"""
        source = (_SRC / "research" / "phases" / "observe_phase.py").read_text(encoding="utf-8")
        self.assertIn('"learning"', source)
        self.assertIn("learning_strategy_applied", source)

    def test_reflect_phase_has_strategy_diff_in_extra_fields(self):
        """reflect_phase.py extra_fields 应包含 strategy_diff（非 results 重复的扩展键）。"""
        source = (_SRC / "research" / "phases" / "reflect_phase.py").read_text(encoding="utf-8")
        import re
        extra_block = re.search(r"extra_fields=\{([^}]+)\}", source, re.DOTALL)
        self.assertIsNotNone(extra_block, "reflect_phase 缺少 extra_fields")
        block_text = extra_block.group(1)
        self.assertIn("strategy_diff", block_text)

    def test_experiment_execution_has_execution_boundary(self):
        """experiment_execution_phase.py results 必须包含 execution_boundary 子对象。"""
        source = (_SRC / "research" / "phases" / "experiment_execution_phase.py").read_text(encoding="utf-8")
        self.assertIn("execution_boundary", source)

    def test_monitoring_has_storage_governance_gauges(self):
        """monitoring.py 必须包含 storage_governance gauge 创建逻辑。"""
        source = (_SRC / "infrastructure" / "monitoring.py").read_text(encoding="utf-8")
        self.assertIn("tcm_storage_health_score", source)
        self.assertIn("tcm_storage_is_degraded", source)
        self.assertIn("tcm_storage_mode_info", source)
        self.assertIn("storage_governance", source)
        self.assertIn("bind_storage_factory", source)
        self.assertIn("backfill_ledger", source)


# Guard #36 — Neo4j graph schema versioning 与标签注册表 (Phase G-1)

class TestGuard36_GraphSchemaVersioning(unittest.TestCase):
    """Guard #36: Neo4j graph schema 注册表必须存在，且 driver/orchestrator/backfill 均引用之。"""

    def test_graph_schema_module_exists(self):
        """graph_schema.py 必须存在并可导入。"""
        path = _SRC / "storage" / "graph_schema.py"
        self.assertTrue(path.exists(), "src/storage/graph_schema.py 不存在")

    def test_graph_schema_has_version_constant(self):
        source = (_SRC / "storage" / "graph_schema.py").read_text(encoding="utf-8")
        self.assertIn("GRAPH_SCHEMA_VERSION", source)

    def test_graph_schema_has_node_label_enum(self):
        source = (_SRC / "storage" / "graph_schema.py").read_text(encoding="utf-8")
        self.assertIn("class NodeLabel", source)
        self.assertIn("RESEARCH_SESSION", source)
        self.assertIn("HYPOTHESIS", source)
        self.assertIn("EVIDENCE", source)

    def test_graph_schema_has_rel_type_enum(self):
        source = (_SRC / "storage" / "graph_schema.py").read_text(encoding="utf-8")
        self.assertIn("class RelType", source)
        self.assertIn("HAS_PHASE", source)
        self.assertIn("CAPTURED", source)

    def test_neo4j_driver_imports_graph_schema(self):
        """neo4j_driver.py 必须引用 graph_schema。"""
        source = (_SRC / "storage" / "neo4j_driver.py").read_text(encoding="utf-8")
        self.assertIn("graph_schema", source)
        self.assertIn("_bootstrap_schema", source)
        self.assertIn("get_schema_version", source)
        self.assertIn("ensure_schema_version", source)

    def test_orchestrator_imports_graph_schema(self):
        """phase_orchestrator.py 的 _project_cycle_to_neo4j 必须使用 NodeLabel/RelType。"""
        source = (_SRC / "research" / "phase_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("from src.storage.graph_schema import", source)
        self.assertIn("NodeLabel.", source)
        self.assertIn("RelType.", source)

    def test_backfill_imports_graph_schema(self):
        """research_session_graph_backfill.py 必须引用 graph_schema。"""
        source = (_SRC / "research" / "research_session_graph_backfill.py").read_text(encoding="utf-8")
        self.assertIn("from src.storage.graph_schema import", source)
        self.assertIn("NodeLabel.", source)
        self.assertIn("RelType.", source)

    def test_get_graph_statistics_includes_schema_fields(self):
        """get_graph_statistics 返回值应包含 schema_version 字段。"""
        source = (_SRC / "storage" / "neo4j_driver.py").read_text(encoding="utf-8")
        self.assertIn("schema_version", source)
        self.assertIn("schema_drift_detected", source)

    def test_kg_stats_endpoint_includes_schema_info(self):
        """kg/stats 端点必须返回 schema_version。"""
        source = (_SRC / "web" / "routes" / "analysis.py").read_text(encoding="utf-8")
        self.assertIn("_get_graph_schema_info", source)
        self.assertIn("schema_version", source)


if __name__ == "__main__":
    unittest.main()
