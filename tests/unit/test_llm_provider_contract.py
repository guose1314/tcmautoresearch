"""
LLM 提供者合约测试 — 验证 get_llm_service 单例化、用途 profile 覆盖、
以及业务模块不再直接实例化 LLMEngine。
"""

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_WORKSPACE = Path(__file__).resolve().parents[2]
_SRC = _WORKSPACE / "src"


class TestGetLlmServiceContract(unittest.TestCase):
    """get_llm_service 行为合约。"""

    def setUp(self):
        from src.infra.llm_service import reset_llm_registry
        reset_llm_registry()

    def tearDown(self):
        from src.infra.llm_service import reset_llm_registry
        reset_llm_registry()

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_default_purpose_reads_config(self, mock_load, mock_from_config):
        mock_load.return_value = {"mode": "local", "temperature": 0.7}
        mock_svc = MagicMock()
        mock_from_config.return_value = mock_svc

        from src.infra.llm_service import get_llm_service
        svc = get_llm_service("default")

        mock_load.assert_called_once_with("models.llm", default={})
        mock_from_config.assert_called_once_with({"mode": "local", "temperature": 0.7})
        self.assertIs(svc, mock_svc)

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_translation_profile_overrides_temperature(self, mock_load, mock_from_config):
        mock_load.return_value = {"mode": "local", "temperature": 0.7, "max_tokens": 1024}
        mock_svc = MagicMock()
        mock_from_config.return_value = mock_svc

        from src.infra.llm_service import get_llm_service
        get_llm_service("translation")

        call_args = mock_from_config.call_args[0][0]
        self.assertAlmostEqual(call_args["temperature"], 0.1)
        self.assertEqual(call_args["max_tokens"], 2048)

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_paper_plugin_profile_overrides(self, mock_load, mock_from_config):
        mock_load.return_value = {"mode": "local", "temperature": 0.7}
        mock_svc = MagicMock()
        mock_from_config.return_value = mock_svc

        from src.infra.llm_service import get_llm_service
        get_llm_service("paper_plugin")

        call_args = mock_from_config.call_args[0][0]
        self.assertAlmostEqual(call_args["temperature"], 0.2)
        self.assertEqual(call_args["max_tokens"], 1500)

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_singleton_per_purpose(self, mock_load, mock_from_config):
        mock_load.return_value = {}
        mock_svc = MagicMock()
        mock_from_config.return_value = mock_svc

        from src.infra.llm_service import get_llm_service
        svc1 = get_llm_service("default")
        svc2 = get_llm_service("default")

        self.assertIs(svc1, svc2)
        self.assertEqual(mock_from_config.call_count, 1, "应仅创建一次实例")

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    @patch("src.infrastructure.config_loader.load_settings_section")
    def test_different_purposes_are_separate_instances(self, mock_load, mock_from_config):
        mock_load.return_value = {}
        mock_from_config.side_effect = [MagicMock(), MagicMock()]

        from src.infra.llm_service import get_llm_service
        svc_a = get_llm_service("default")
        svc_t = get_llm_service("translation")

        self.assertIsNot(svc_a, svc_t)
        self.assertEqual(mock_from_config.call_count, 2)

    @patch("src.infra.llm_service.CachedLLMService.from_config")
    def test_explicit_llm_config_skips_config_loader(self, mock_from_config):
        mock_svc = MagicMock()
        mock_from_config.return_value = mock_svc

        from src.infra.llm_service import get_llm_service
        custom = {"mode": "api", "api_url": "http://test", "model": "m"}
        svc = get_llm_service("custom", llm_config=custom)

        self.assertIs(svc, mock_svc)
        mock_from_config.assert_called_once()

    def test_reset_clears_registry(self):
        from src.infra.llm_service import _llm_registry, reset_llm_registry
        _llm_registry["test_sentinel"] = MagicMock()
        reset_llm_registry()
        self.assertEqual(len(_llm_registry), 0)


class TestNoDirectLLMEngineInBusinessCode(unittest.TestCase):
    """业务模块不得直接 import LLMEngine()（应走 get_llm_service）。"""

    # 允许直接引用 LLMEngine 的白名单文件
    _WHITELIST = {
        # LLM 核心定义
        os.path.join("src", "llm", "llm_engine.py"),
        # 工厂方法内部
        os.path.join("src", "infra", "llm_service.py"),
        # 测试
    }

    def _collect_llm_engine_imports(self, dirpath: Path):
        """扫描 AST，返回直接 import LLMEngine 的文件。"""
        violations = []
        for root, _dirs, files in os.walk(dirpath):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = Path(root) / fname
                rel = str(fpath.relative_to(_WORKSPACE))
                if rel.replace("\\", os.sep).replace("/", os.sep) in {
                    w.replace("/", os.sep) for w in self._WHITELIST
                }:
                    continue

                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and "llm_engine" in node.module:
                            names = [alias.name for alias in node.names]
                            if "LLMEngine" in names:
                                violations.append(f"{rel}:{node.lineno}")
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if "llm_engine" in alias.name:
                                violations.append(f"{rel}:{node.lineno}")
        return violations

    def test_no_direct_llm_engine_in_src(self):
        violations = self._collect_llm_engine_imports(_SRC)
        self.assertEqual(
            violations, [],
            f"以下文件仍直接 import LLMEngine，应改用 get_llm_service(): {violations}",
        )


class TestPurposeProfilesComplete(unittest.TestCase):
    """确保所有预定义 profile 都在注册表内。"""

    def test_known_profiles_exist(self):
        from src.infra.llm_service import _LLM_PURPOSE_PROFILES
        self.assertIn("translation", _LLM_PURPOSE_PROFILES)
        self.assertIn("paper_plugin", _LLM_PURPOSE_PROFILES)

    def test_translation_profile_values(self):
        from src.infra.llm_service import _LLM_PURPOSE_PROFILES
        t = _LLM_PURPOSE_PROFILES["translation"]
        self.assertAlmostEqual(t["temperature"], 0.1)
        self.assertEqual(t["max_tokens"], 2048)

    def test_paper_plugin_profile_values(self):
        from src.infra.llm_service import _LLM_PURPOSE_PROFILES
        p = _LLM_PURPOSE_PROFILES["paper_plugin"]
        self.assertAlmostEqual(p["temperature"], 0.2)
        self.assertEqual(p["max_tokens"], 1500)


if __name__ == "__main__":
    unittest.main()
