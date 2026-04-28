"""PromptRegistry 版本化（T2.1）回归测试。

覆盖三类场景：
1. ``get_prompt_template(name)`` / ``version="latest"`` 默认返回最新版本。
2. 显式版本号可定向命中（含历史版本）。
3. 缺失版本号或缺失 prompt 时抛出明确 ``KeyError``。

附加 1 条：渲染与缓存键消费版本字段，确保 T1.2 缓存隔离。
"""

from __future__ import annotations

import unittest
from unittest import mock

from src.infra.prompt_registry import (
    PROMPT_REGISTRY,
    PromptTemplate,
    call_registered_prompt,
    get_prompt_template,
    list_prompt_versions,
    register_prompt_version,
    render_prompt,
)

_TEST_NAME = "research_advisor.hypothesis_suggestion"


class _FakeEngine:
    """最简 generate engine：返回固定字符串并记录调用。"""

    def __init__(self, payload: str = "[]") -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []
        # describe_llm_engine 会读这些字段
        self.model_name = "fake-llm"
        self.llm_mode = "test"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        return self.payload


class TestPromptRegistryVersioning(unittest.TestCase):
    def setUp(self) -> None:
        # 备份将被改动的注册表槽位，避免污染其他测试
        self._snapshot = PROMPT_REGISTRY[_TEST_NAME]

    def tearDown(self) -> None:
        # 还原 latest 槽与版本桶
        from src.infra import prompt_registry as pr

        pr.PROMPT_REGISTRY[_TEST_NAME] = self._snapshot
        bucket = pr._VERSIONED_PROMPT_REGISTRY[_TEST_NAME]
        for ver in list(bucket.keys()):
            if ver != self._snapshot.version:
                bucket.pop(ver, None)
        bucket[self._snapshot.version] = self._snapshot

    # ── 1. latest 默认 ────────────────────────────────────────────────
    def test_get_returns_latest_by_default(self) -> None:
        spec_default = get_prompt_template(_TEST_NAME)
        spec_latest = get_prompt_template(_TEST_NAME, version="latest")
        self.assertIs(spec_default, spec_latest)
        self.assertEqual(spec_default.version, "v1")
        self.assertEqual(spec_default.schema_version, "v1")

    def test_latest_tracks_newly_registered_version(self) -> None:
        v2 = PromptTemplate(
            name=_TEST_NAME,
            purpose=self._snapshot.purpose,
            task=self._snapshot.task,
            system_prompt=self._snapshot.system_prompt + "\n# v2 note",
            user_template=self._snapshot.user_template,
            output_kind=self._snapshot.output_kind,
            output_schema=self._snapshot.output_schema,
            version="v2",
            parent_version="v1",
            schema_version="v1",
        )
        register_prompt_version(v2)
        self.assertEqual(get_prompt_template(_TEST_NAME).version, "v2")
        self.assertEqual(list_prompt_versions(_TEST_NAME), ["v1", "v2"])

    # ── 2. 显式版本 ────────────────────────────────────────────────
    def test_get_returns_explicit_version(self) -> None:
        v2 = PromptTemplate(
            name=_TEST_NAME,
            purpose=self._snapshot.purpose,
            task=self._snapshot.task,
            system_prompt="explicit-v2",
            user_template=self._snapshot.user_template,
            output_kind=self._snapshot.output_kind,
            output_schema=self._snapshot.output_schema,
            version="v2",
            parent_version="v1",
            schema_version="v2",
        )
        register_prompt_version(v2)
        self.assertEqual(get_prompt_template(_TEST_NAME, version="v1"), self._snapshot)
        self.assertIs(get_prompt_template(_TEST_NAME, version="v2"), v2)

    # ── 3. 缺失版本 ────────────────────────────────────────────────
    def test_get_unknown_version_raises(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_prompt_template(_TEST_NAME, version="v9")
        self.assertIn("v9", str(ctx.exception))

    def test_get_unknown_name_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_prompt_template("not.registered.prompt")
        with self.assertRaises(KeyError):
            list_prompt_versions("not.registered.prompt")

    # ── 4. 缓存键消费版本字段（与 T1.2 联通验证） ────────────────────
    def test_call_registered_prompt_isolates_cache_by_version(self) -> None:
        # 注册两个版本，render 后通过 call_registered_prompt 走缓存路径，
        # 期望两个版本不共享缓存键 → 各自触发一次 engine.generate。
        v2 = PromptTemplate(
            name=_TEST_NAME,
            purpose=self._snapshot.purpose,
            task=self._snapshot.task,
            system_prompt=self._snapshot.system_prompt,
            user_template=self._snapshot.user_template,
            output_kind=self._snapshot.output_kind,
            output_schema=self._snapshot.output_schema,
            version="v2",
            parent_version="v1",
            schema_version="v2",
        )
        register_prompt_version(v2)

        fake = _FakeEngine(payload="[{\"hypothesis\":\"h\",\"confidence\":0.5,\"rationale\":\"r\",\"suggested_methods\":[]}]")
        rendered_v1 = render_prompt(_TEST_NAME, topic="T", literature_section="")
        # 强制把 rendered.version 设为 v1（render_prompt 默认走 latest）
        from dataclasses import replace

        rendered_v1 = replace(rendered_v1, version="v1", schema_version="v1")
        rendered_v2 = render_prompt(_TEST_NAME, topic="T", literature_section="")  # latest=v2

        # 用一个 in-memory 任务缓存替身
        store: dict[str, str] = {}

        class _StubTaskCache:
            def get_text(self, layer, name, payload):
                import hashlib
                import json

                key = hashlib.sha256(
                    json.dumps([layer, name, payload], sort_keys=True, default=str).encode()
                ).hexdigest()
                return store.get(key)

            def put_text(self, layer, name, payload, value, meta=None):
                import hashlib
                import json

                key = hashlib.sha256(
                    json.dumps([layer, name, payload], sort_keys=True, default=str).encode()
                ).hexdigest()
                store[key] = value

        with mock.patch(
            "src.infra.prompt_registry.get_layered_task_cache", return_value=_StubTaskCache()
        ):
            call_registered_prompt(fake, _TEST_NAME, rendered=rendered_v1)
            call_registered_prompt(fake, _TEST_NAME, rendered=rendered_v1)  # 命中缓存
            call_registered_prompt(fake, _TEST_NAME, rendered=rendered_v2)  # v2 应未命中

        # v1 触发 1 次，v2 再触发 1 次 → 总 2 次
        self.assertEqual(len(fake.calls), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
