"""J-3 测试: LLMRoleProfile 池 + KVCacheDescriptor + prepare_planned_llm_call(role=...)。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.infra.llm_service import PlannedLLMCall, prepare_planned_llm_call
from src.research.llm_role_profile import (
    DEFAULT_ROLE_NAMES,
    ROLE_JIAOKAN,
    ROLE_JINGFANG,
    ROLE_PROFILE_CONTRACT_VERSION,
    ROLE_WENBING,
    ROLE_XUNGU,
    ROLE_YIJING,
    KVCacheDescriptor,
    KVCacheStore,
    LLMRoleProfile,
    get_role_profile,
    list_role_profiles,
    register_role_profile,
    reset_role_profiles_for_tests,
)


class _FakeEngine:
    def generate(self, *args, **kwargs):  # pragma: no cover - 不被实际调用
        return ""


class LLMRoleProfileContractTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_role_profiles_for_tests()

    def test_default_pool_has_five_roles(self) -> None:
        names = {p.role_name for p in list_role_profiles()}
        self.assertEqual(
            names,
            {ROLE_YIJING, ROLE_JINGFANG, ROLE_WENBING, ROLE_JIAOKAN, ROLE_XUNGU},
        )
        self.assertEqual(set(DEFAULT_ROLE_NAMES), names)

    def test_each_role_carries_system_prompt_and_temperature(self) -> None:
        for name in DEFAULT_ROLE_NAMES:
            profile = get_role_profile(name)
            self.assertIsNotNone(profile)
            assert profile is not None  # for type checker
            self.assertTrue(profile.system_prompt.strip())
            self.assertGreaterEqual(profile.temperature, 0.0)
            self.assertLessEqual(profile.temperature, 2.0)
            self.assertTrue(profile.kv_cache_key.startswith("role."))

    def test_round_trip_preserves_fields(self) -> None:
        profile = get_role_profile(ROLE_JINGFANG)
        assert profile is not None
        text = json.dumps(profile.to_dict(), ensure_ascii=False)
        rebuilt = LLMRoleProfile.from_dict(json.loads(text))
        self.assertEqual(rebuilt.role_name, ROLE_JINGFANG)
        self.assertEqual(rebuilt.system_prompt, profile.system_prompt)
        self.assertAlmostEqual(rebuilt.temperature, profile.temperature, places=4)
        self.assertEqual(rebuilt.style_tags, profile.style_tags)
        self.assertEqual(rebuilt.kv_cache_key, profile.kv_cache_key)

    def test_contract_version_emitted(self) -> None:
        profile = get_role_profile(ROLE_YIJING)
        assert profile is not None
        self.assertEqual(profile.to_dict()["contract_version"], ROLE_PROFILE_CONTRACT_VERSION)

    def test_register_custom_role(self) -> None:
        custom = LLMRoleProfile(
            role_name="本草家",
            system_prompt="精研本草纲目",
            temperature=0.4,
            kv_cache_key="role.bencao.v1",
        )
        register_role_profile(custom)
        looked_up = get_role_profile("本草家")
        self.assertIsNotNone(looked_up)
        assert looked_up is not None
        self.assertEqual(looked_up.system_prompt, "精研本草纲目")

    def test_register_rejects_invalid(self) -> None:
        with self.assertRaises(TypeError):
            register_role_profile({"role_name": "x"})  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            register_role_profile(LLMRoleProfile(role_name=""))

    def test_unknown_role_returns_none(self) -> None:
        self.assertIsNone(get_role_profile("不存在"))
        self.assertIsNone(get_role_profile(""))
        self.assertIsNone(get_role_profile(None))


class KVCacheDescriptorTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        desc = KVCacheDescriptor(
            role_name=ROLE_JIAOKAN,
            kv_cache_key="role.jiaokan.v1",
            cache_path="/tmp/x.kv",
            prompt_signature="sha:abc",
            token_count=1024,
            valid=True,
        )
        rebuilt = KVCacheDescriptor.from_dict(desc.to_dict())
        self.assertEqual(rebuilt.role_name, desc.role_name)
        self.assertEqual(rebuilt.kv_cache_key, desc.kv_cache_key)
        self.assertEqual(rebuilt.token_count, 1024)
        self.assertTrue(rebuilt.valid)

    def test_negative_token_count_normalized(self) -> None:
        rebuilt = KVCacheDescriptor.from_dict({"token_count": -5, "valid": "yes"})
        self.assertEqual(rebuilt.token_count, 0)
        self.assertTrue(rebuilt.valid)


class KVCacheStoreTests(unittest.TestCase):
    def test_upsert_and_retrieve(self) -> None:
        with TemporaryDirectory() as tmp:
            store = KVCacheStore(tmp)
            profile = get_role_profile(ROLE_WENBING)
            assert profile is not None
            cache_path = store.cache_path_for(profile)
            self.assertTrue(str(cache_path).endswith(".kv"))

            descriptor = KVCacheDescriptor(
                role_name=profile.role_name,
                kv_cache_key=profile.kv_cache_key,
                cache_path=str(cache_path),
                prompt_signature="sha:1",
                token_count=128,
                valid=True,
            )
            store.upsert(descriptor)

            store2 = KVCacheStore(tmp)
            got = store2.get(profile.kv_cache_key)
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.token_count, 128)
            self.assertTrue(got.valid)

            store2.invalidate(profile.kv_cache_key)
            store3 = KVCacheStore(tmp)
            again = store3.get(profile.kv_cache_key)
            assert again is not None
            self.assertFalse(again.valid)

    def test_cache_path_requires_key(self) -> None:
        with TemporaryDirectory() as tmp:
            store = KVCacheStore(tmp)
            with self.assertRaises(ValueError):
                store.cache_path_for(LLMRoleProfile(role_name="x"))


class PrepareCallRoleInjectionTests(unittest.TestCase):
    def _stub_settings(self, *_a, **_kw):
        return {"small_model_optimizer": {"enabled": True}}

    def test_role_injects_profile_into_planned_call(self) -> None:
        with patch(
            "src.infrastructure.config_loader.load_settings_section",
            side_effect=self._stub_settings,
        ):
            call = prepare_planned_llm_call(
                phase="phase_2",
                task_type="topic_discovery",
                purpose="topic_discovery",
                dossier_sections={"topic": "湿病"},
                llm_engine=_FakeEngine(),
                role=ROLE_YIJING,
            )
        self.assertIsInstance(call, PlannedLLMCall)
        self.assertIsNotNone(call.role_profile)
        assert call.role_profile is not None
        self.assertEqual(call.role_profile.role_name, ROLE_YIJING)

        merged_prompt, merged_system = call.build_prompt("请提出研究主题", "")
        self.assertIn("医经家", merged_system)

        meta = call.to_metadata()
        self.assertEqual(meta.get("role_name"), ROLE_YIJING)
        self.assertIn("role_temperature", meta)
        self.assertIn("role_kv_cache_key", meta)

    def test_unknown_role_does_not_crash(self) -> None:
        with patch(
            "src.infrastructure.config_loader.load_settings_section",
            side_effect=self._stub_settings,
        ):
            call = prepare_planned_llm_call(
                phase="phase_2",
                task_type="topic_discovery",
                purpose="topic_discovery",
                dossier_sections={"topic": "湿病"},
                llm_engine=_FakeEngine(),
                role="不存在的角色",
            )
        self.assertIsNone(call.role_profile)
        meta = call.to_metadata()
        self.assertNotIn("role_name", meta)

    def test_kv_cache_descriptor_passthrough(self) -> None:
        descriptor = KVCacheDescriptor(
            role_name=ROLE_XUNGU,
            kv_cache_key="role.xungu.v1",
            valid=True,
        )
        with patch(
            "src.infrastructure.config_loader.load_settings_section",
            side_effect=self._stub_settings,
        ):
            call = prepare_planned_llm_call(
                phase="phase_2",
                task_type="textual_research",
                purpose="entity_extraction",
                dossier_sections={"text": "本经"},
                llm_engine=_FakeEngine(),
                role=ROLE_XUNGU,
                kv_cache_descriptor=descriptor,
            )
        self.assertIs(call.kv_cache_descriptor, descriptor)
        meta = call.to_metadata()
        self.assertTrue(meta.get("kv_cache_valid"))

    def test_build_prompt_without_plan_still_prepends_role(self) -> None:
        profile = get_role_profile(ROLE_JIAOKAN)
        call = PlannedLLMCall(
            phase="phase_2",
            task_type="t",
            purpose="p",
            llm_service=_FakeEngine(),
            role_profile=profile,
        )
        _, merged_system = call.build_prompt("校勘问题", "原系统提示")
        self.assertIn("校勘", merged_system)
        self.assertIn("原系统提示", merged_system)


if __name__ == "__main__":
    unittest.main()
