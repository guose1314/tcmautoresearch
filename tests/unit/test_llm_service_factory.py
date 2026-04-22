"""Phase L-3 — `LLMServiceFactory` 与 ``Llama(`` 调用审计单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.infra.llm_service_factory import (
    CONTRACT_VERSION,
    DEFAULT_LLAMA_CALL_ALLOWLIST,
    LLM_SERVICE_FACTORY_CONTRACT_VERSION,
    LLMServiceFactory,
    LlamaCallViolation,
    assert_no_unexpected_llama_calls,
    scan_llama_call_violations,
)


class _FakeCachedLLMService:
    last_call: dict | None = None

    @classmethod
    def from_engine_config(cls, engine_config: dict, **kwargs):
        cls.last_call = {"method": "engine", "engine_config": engine_config, "kwargs": kwargs}
        return ("engine", engine_config)

    @classmethod
    def from_api_config(cls, api_config: dict, **kwargs):
        cls.last_call = {"method": "api", "api_config": api_config, "kwargs": kwargs}
        return ("api", api_config)

    @classmethod
    def from_config(cls, config: dict, **kwargs):
        cls.last_call = {"method": "config", "config": config, "kwargs": kwargs}
        return ("config", config)

    @classmethod
    def from_gap_config(cls, gap_config: dict, llm_config: dict, **kwargs):
        cls.last_call = {
            "method": "gap",
            "gap_config": gap_config,
            "llm_config": llm_config,
            "kwargs": kwargs,
        }
        return ("gap", gap_config, llm_config)


class TestContractVersion(unittest.TestCase):
    def test_contract_version(self) -> None:
        self.assertEqual(CONTRACT_VERSION, "llm-service-factory-v1")
        self.assertEqual(LLM_SERVICE_FACTORY_CONTRACT_VERSION, CONTRACT_VERSION)

    def test_default_allowlist_only_llm_engine(self) -> None:
        self.assertIn("src/llm/llm_engine.py", DEFAULT_LLAMA_CALL_ALLOWLIST)


class TestLLMServiceFactoryDelegation(unittest.TestCase):
    def setUp(self) -> None:
        _FakeCachedLLMService.last_call = None
        self.factory = LLMServiceFactory(cached_llm_service_cls=_FakeCachedLLMService)

    def test_create_from_engine_config(self) -> None:
        result = self.factory.create_from_engine_config({"k": 1}, extra=True)
        self.assertEqual(result, ("engine", {"k": 1}))
        self.assertEqual(_FakeCachedLLMService.last_call["method"], "engine")  # type: ignore[index]
        self.assertEqual(_FakeCachedLLMService.last_call["kwargs"], {"extra": True})  # type: ignore[index]

    def test_create_from_api_config(self) -> None:
        result = self.factory.create_from_api_config({"endpoint": "http://x"})
        self.assertEqual(result, ("api", {"endpoint": "http://x"}))

    def test_create_from_config(self) -> None:
        result = self.factory.create_from_config({"models": {}})
        self.assertEqual(result[0], "config")

    def test_create_from_gap_config(self) -> None:
        result = self.factory.create_from_gap_config({"g": 1}, {"l": 2})
        self.assertEqual(result, ("gap", {"g": 1}, {"l": 2}))

    def test_factory_records_contract_version(self) -> None:
        self.assertEqual(self.factory.contract_version, CONTRACT_VERSION)


class TestScanLlamaCallViolations(unittest.TestCase):
    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_clean_tree_no_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(root / "src" / "ok.py", "def foo():\n    return 1\n")
            violations = scan_llama_call_violations([root / "src"], workspace_root=root)
            self.assertEqual(violations, [])

    def test_unauthorized_call_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "src" / "bad.py",
                "from llama_cpp import Llama\nmodel = Llama(model_path='m')\n",
            )
            violations = scan_llama_call_violations([root / "src"], workspace_root=root)
            self.assertEqual(len(violations), 1)
            self.assertIsInstance(violations[0], LlamaCallViolation)
            self.assertEqual(violations[0].file_path, "src/bad.py")
            self.assertEqual(violations[0].line_number, 2)

    def test_allowlisted_file_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "src" / "llm" / "llm_engine.py",
                "from llama_cpp import Llama\nself._llm = Llama(model_path='m')\n",
            )
            violations = scan_llama_call_violations(
                [root / "src"],
                allowlist=("src/llm/llm_engine.py",),
                workspace_root=root,
            )
            self.assertEqual(violations, [])

    def test_comment_line_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "src" / "doc.py",
                "# example: Llama(model_path='m')\nx = 1\n",
            )
            violations = scan_llama_call_violations([root / "src"], workspace_root=root)
            self.assertEqual(violations, [])

    def test_assert_no_unexpected_raises_on_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(root / "src" / "bad.py", "x = Llama(1)\n")
            with self.assertRaises(AssertionError) as ctx:
                assert_no_unexpected_llama_calls([root / "src"], workspace_root=root)
            self.assertIn("Llama(", str(ctx.exception))

    def test_assert_no_unexpected_passes_on_clean_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(root / "src" / "ok.py", "x = 1\n")
            assert_no_unexpected_llama_calls([root / "src"], workspace_root=root)


class TestRepoOnlyAllowedLlamaCallExists(unittest.TestCase):
    """对真实仓库做一次审计：除 ``src/llm/llm_engine.py`` 外不应有 ``Llama(`` 调用。"""

    def test_repository_has_only_allowlisted_llama_calls(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        violations = scan_llama_call_violations(
            [repo_root / "src", repo_root / "web_console"],
            workspace_root=repo_root,
        )
        self.assertEqual(
            violations,
            [],
            f"仓库出现未授权 Llama( 调用: {[v.to_dict() for v in violations]}",
        )


if __name__ == "__main__":
    unittest.main()
