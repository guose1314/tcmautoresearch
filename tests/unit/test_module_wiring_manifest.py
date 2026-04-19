"""tests/unit/test_module_wiring_manifest.py — ModuleWiringManifest 单元测试。"""

import os
import unittest

from src.core.module_wiring_manifest import (
    MODULE_MANIFEST,
    TIER_ACTIVE,
    TIER_DORMANT,
    TIER_OPTIONAL,
    VALID_TIERS,
    get_manifest_summary,
    get_modules_by_tier,
    validate_manifest_paths,
)

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestManifestStructure(unittest.TestCase):
    """清单结构完整性。"""

    def test_manifest_is_non_empty(self):
        self.assertGreater(len(MODULE_MANIFEST), 0)

    def test_every_entry_has_required_fields(self):
        required = {"tier", "path", "description", "activation"}
        for key, entry in MODULE_MANIFEST.items():
            missing = required - entry.keys()
            self.assertFalse(missing, f"模块 {key} 缺少字段: {missing}")

    def test_all_tiers_are_valid(self):
        for key, entry in MODULE_MANIFEST.items():
            self.assertIn(entry["tier"], VALID_TIERS,
                          f"模块 {key} 使用了无效层级: {entry['tier']}")

    def test_at_least_one_per_tier(self):
        tiers_present = {e["tier"] for e in MODULE_MANIFEST.values()}
        for t in VALID_TIERS:
            self.assertIn(t, tiers_present,
                          f"清单中没有任何 {t} 层级模块")


class TestManifestPathValidity(unittest.TestCase):
    """清单路径必须指向实际存在的文件。"""

    def test_all_paths_exist(self):
        missing = validate_manifest_paths(_WORKSPACE)
        self.assertEqual(
            missing, [],
            f"以下清单条目指向不存在的文件: "
            + ", ".join(f"{m['module_key']}→{m['path']}" for m in missing),
        )


class TestSummaryAPI(unittest.TestCase):
    """get_manifest_summary 返回正确统计。"""

    def test_summary_total(self):
        s = get_manifest_summary()
        self.assertEqual(s["total"], len(MODULE_MANIFEST))

    def test_summary_counts_sum(self):
        s = get_manifest_summary()
        self.assertEqual(sum(s["counts"].values()), s["total"])

    def test_summary_tiers_list(self):
        s = get_manifest_summary()
        self.assertEqual(set(s["tiers"]), VALID_TIERS)


class TestGetModulesByTier(unittest.TestCase):
    """按层级查询。"""

    def test_active_modules_non_empty(self):
        active = get_modules_by_tier(TIER_ACTIVE)
        self.assertGreater(len(active), 0)

    def test_optional_modules_non_empty(self):
        optional = get_modules_by_tier(TIER_OPTIONAL)
        self.assertGreater(len(optional), 0)

    def test_dormant_modules_non_empty(self):
        dormant = get_modules_by_tier(TIER_DORMANT)
        self.assertGreater(len(dormant), 0)

    def test_invalid_tier_raises(self):
        with self.assertRaises(ValueError):
            get_modules_by_tier("unknown")

    def test_each_result_has_module_key(self):
        for item in get_modules_by_tier(TIER_ACTIVE):
            self.assertIn("module_key", item)


class TestTierClassificationConsistency(unittest.TestCase):
    """关键模块的层级分类一致性检查。"""

    def test_core_pipeline_is_active(self):
        for key in ("research_pipeline", "phase_orchestrator",
                     "research_runtime_service"):
            self.assertEqual(MODULE_MANIFEST[key]["tier"], TIER_ACTIVE,
                             f"{key} 必须为 active 层级")

    def test_self_learning_is_optional(self):
        self.assertEqual(MODULE_MANIFEST["self_learning_engine"]["tier"],
                         TIER_OPTIONAL)

    def test_cycle_runner_is_dormant(self):
        self.assertEqual(MODULE_MANIFEST["cycle_runner"]["tier"], TIER_DORMANT)

    def test_deprecated_orchestrator_is_dormant(self):
        self.assertEqual(
            MODULE_MANIFEST["research_orchestrator_deprecated"]["tier"],
            TIER_DORMANT,
        )


if __name__ == "__main__":
    unittest.main()
