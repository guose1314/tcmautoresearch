"""入口合约测试 — 确保 ResearchRuntimeService 为唯一推荐主链。

验证点：
1. __init__.py 导出结构中 ResearchRuntimeService 和 ResearchRuntimeResult 可正常导入
2. run_research() 发出 DeprecationWarning
3. 规范默认值 CANONICAL_OBSERVE_DEFAULTS / CANONICAL_PUBLISH_DEFAULTS 被所有 profile 继承
4. API 层 DEFAULT_OBSERVE_PHASE_CONTEXT 是 canonical 的超集
5. 所有 profile 的 default_observe_context 包含 canonical 基线
"""

import unittest
import warnings


class TestEntryPointExports(unittest.TestCase):
    """__init__.py 导出结构合约。"""

    def test_recommended_exports_are_importable(self):
        from src.orchestration import ResearchRuntimeService, ResearchRuntimeResult

        self.assertTrue(callable(ResearchRuntimeService))
        self.assertTrue(callable(ResearchRuntimeResult))

    def test_legacy_exports_are_still_importable(self):
        from src.orchestration import (
            OrchestrationResult,
            PhaseOutcome,
            ResearchOrchestrator,
            run_research,
            topic_to_phase_context,
        )

        self.assertTrue(callable(ResearchOrchestrator))
        self.assertTrue(callable(run_research))

    def test_run_research_emits_deprecation_warning(self):
        from src.orchestration import run_research

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                run_research("dummy-topic-for-deprecation-test")
            except Exception:
                pass  # 不关心执行结果，只验证 warning

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            len(deprecation_warnings) >= 1,
            f"期望 DeprecationWarning，但实际收到: {[w.category.__name__ for w in caught]}",
        )
        self.assertIn("run_research", str(deprecation_warnings[0].message))


class TestCanonicalPhaseDefaults(unittest.TestCase):
    """规范阶段 context 默认值合约。"""

    def test_canonical_observe_defaults_have_required_keys(self):
        from src.orchestration.research_runtime_service import CANONICAL_OBSERVE_DEFAULTS

        required_keys = {"data_source", "use_local_corpus", "run_preprocess_and_extract"}
        self.assertTrue(required_keys.issubset(CANONICAL_OBSERVE_DEFAULTS.keys()))

    def test_canonical_publish_defaults_have_required_keys(self):
        from src.orchestration.research_runtime_service import CANONICAL_PUBLISH_DEFAULTS

        self.assertIn("allow_pipeline_citation_fallback", CANONICAL_PUBLISH_DEFAULTS)

    def test_all_profiles_inherit_canonical_observe_defaults(self):
        from src.orchestration.research_runtime_service import (
            CANONICAL_OBSERVE_DEFAULTS,
            _SHARED_RUNTIME_PROFILES,
        )

        for profile_name, profile in _SHARED_RUNTIME_PROFILES.items():
            observe_ctx = profile.get("default_observe_context", {})
            for key, value in CANONICAL_OBSERVE_DEFAULTS.items():
                self.assertEqual(
                    observe_ctx.get(key),
                    value,
                    f"profile '{profile_name}' 的 default_observe_context['{key}'] "
                    f"应为 {value!r}，实际为 {observe_ctx.get(key)!r}",
                )

    def test_all_profiles_inherit_canonical_publish_defaults(self):
        from src.orchestration.research_runtime_service import (
            CANONICAL_PUBLISH_DEFAULTS,
            _SHARED_RUNTIME_PROFILES,
        )

        for profile_name, profile in _SHARED_RUNTIME_PROFILES.items():
            publish_ctx = profile.get("default_publish_context", {})
            for key, value in CANONICAL_PUBLISH_DEFAULTS.items():
                self.assertEqual(
                    publish_ctx.get(key),
                    value,
                    f"profile '{profile_name}' 的 default_publish_context['{key}'] "
                    f"应为 {value!r}，实际为 {publish_ctx.get(key)!r}",
                )

    def test_api_observe_defaults_are_superset_of_canonical(self):
        from src.api.research_utils import DEFAULT_OBSERVE_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import CANONICAL_OBSERVE_DEFAULTS

        for key, value in CANONICAL_OBSERVE_DEFAULTS.items():
            self.assertEqual(
                DEFAULT_OBSERVE_PHASE_CONTEXT.get(key),
                value,
                f"API DEFAULT_OBSERVE_PHASE_CONTEXT['{key}'] 应与 canonical 一致",
            )
        # API 层还应携带 local_data_dir
        self.assertIn("local_data_dir", DEFAULT_OBSERVE_PHASE_CONTEXT)

    def test_api_publish_defaults_match_canonical(self):
        from src.api.research_utils import DEFAULT_PUBLISH_PHASE_CONTEXT
        from src.orchestration.research_runtime_service import CANONICAL_PUBLISH_DEFAULTS

        for key, value in CANONICAL_PUBLISH_DEFAULTS.items():
            self.assertEqual(
                DEFAULT_PUBLISH_PHASE_CONTEXT.get(key),
                value,
                f"API DEFAULT_PUBLISH_PHASE_CONTEXT['{key}'] 应与 canonical 一致",
            )


class TestRuntimeServiceIsMainChain(unittest.TestCase):
    """ResearchRuntimeService 主链不变性。"""

    def test_service_resolves_profile_defaults_into_config(self):
        from src.orchestration.research_runtime_service import (
            CANONICAL_OBSERVE_DEFAULTS,
            ResearchRuntimeService,
        )

        svc = ResearchRuntimeService({"runtime_profile": "web_research"})
        observe_ctx = svc.config.get("default_observe_context", {})
        for key, value in CANONICAL_OBSERVE_DEFAULTS.items():
            self.assertEqual(
                observe_ctx.get(key),
                value,
                f"web_research profile 经 ResearchRuntimeService 解析后 "
                f"default_observe_context['{key}'] 应为 {value!r}",
            )

    def test_service_demo_profile_only_runs_observe(self):
        from src.orchestration.research_runtime_service import ResearchRuntimeService

        svc = ResearchRuntimeService({"runtime_profile": "demo_research"})
        self.assertEqual(svc.phase_names, ["observe"])


if __name__ == "__main__":
    unittest.main()
