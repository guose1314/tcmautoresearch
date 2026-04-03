"""
tests/test_config_manager.py
ConfigManager 单元测试
"""
import os
import tempfile
import textwrap

import pytest
import yaml

from src.infra.config_manager import ConfigManager

# ---------- helpers ----------

MINIMAL_CONFIG = {
    "system": {"name": "Test System", "version": "1.0.0"},
    "monitoring": {"enabled": True, "interval_seconds": 30},
    "database": {"path": "./db/test.db"},
    "output": {"directory": "./output"},
    "modules": {
        "preprocessor": {"max_length": 512},
    },
}

EXTRA_MODULE_CONFIG = {
    **MINIMAL_CONFIG,
    "my_module": {"key": "value"},
}


def _write_yaml(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


@pytest.fixture(autouse=True)
def reset_singleton():
    ConfigManager.reset()
    yield
    ConfigManager.reset()


@pytest.fixture
def tmp_config(tmp_path):
    p = tmp_path / "config.yml"
    _write_yaml(MINIMAL_CONFIG, str(p))
    return str(p)


@pytest.fixture
def cm():
    return ConfigManager()


# ---------- singleton ----------

class TestSingleton:
    def test_same_instance(self):
        a = ConfigManager.get_instance()
        b = ConfigManager.get_instance()
        assert a is b

    def test_reset_gives_new_instance(self):
        a = ConfigManager.get_instance()
        ConfigManager.reset()
        b = ConfigManager.get_instance()
        assert a is not b


# ---------- load ----------

class TestLoad:
    def test_load_returns_dict(self, cm, tmp_config):
        result = cm.load(tmp_config)
        assert isinstance(result, dict)

    def test_load_sets_loaded(self, cm, tmp_config):
        assert not cm.loaded
        cm.load(tmp_config)
        assert cm.loaded

    def test_load_sets_path(self, cm, tmp_config):
        cm.load(tmp_config)
        assert cm.path is not None
        assert cm.path.endswith("config.yml")

    def test_load_top_level_keys_present(self, cm, tmp_config):
        cfg = cm.load(tmp_config)
        assert "system" in cfg
        assert "monitoring" in cfg

    def test_load_missing_file_raises(self, cm):
        with pytest.raises(FileNotFoundError):
            cm.load("/nonexistent/path/config.yml")

    def test_load_invalid_yaml_raises(self, tmp_path, cm):
        bad = tmp_path / "bad.yml"
        bad.write_text("key: [unclosed", encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            cm.load(str(bad))

    def test_load_non_mapping_raises(self, tmp_path, cm):
        p = tmp_path / "list.yml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError):
            cm.load(str(p))

    def test_load_with_utf8_content(self, tmp_path, cm):
        data = {"system": {"name": "中医系统", "version": "2.0.0"},
                "monitoring": {"enabled": True},
                "database": {"path": "./db"},
                "output": {"directory": "./out"}}
        p = tmp_path / "utf8.yml"
        _write_yaml(data, str(p))
        cfg = cm.load(str(p))
        assert cfg["system"]["name"] == "中医系统"


# ---------- get_module_config ----------

class TestGetModuleConfig:
    def test_module_in_modules_block(self, cm, tmp_config):
        cm.load(tmp_config)
        cfg = cm.get_module_config("preprocessor")
        assert cfg == {"max_length": 512}

    def test_module_at_top_level(self, tmp_path, cm):
        p = tmp_path / "c.yml"
        _write_yaml(EXTRA_MODULE_CONFIG, str(p))
        cm.load(str(p))
        cfg = cm.get_module_config("my_module")
        assert cfg == {"key": "value"}

    def test_unknown_module_returns_empty_dict(self, cm, tmp_config):
        cm.load(tmp_config)
        assert cm.get_module_config("nonexistent") == {}

    def test_returns_copy_not_reference(self, cm, tmp_config):
        cm.load(tmp_config)
        cfg = cm.get_module_config("preprocessor")
        cfg["injected"] = True
        assert "injected" not in cm.get_module_config("preprocessor")


# ---------- validate ----------

class TestValidate:
    def test_validate_before_load(self, cm):
        issues = cm.validate()
        assert len(issues) == 1
        assert "not loaded" in issues[0].lower()

    def test_validate_clean_config(self, cm, tmp_config):
        cm.load(tmp_config)
        issues = cm.validate()
        assert issues == []

    def test_validate_missing_top_level_key(self, tmp_path, cm):
        data = {k: v for k, v in MINIMAL_CONFIG.items() if k != "monitoring"}
        p = tmp_path / "no_monitoring.yml"
        _write_yaml(data, str(p))
        cm.load(str(p))
        issues = cm.validate()
        assert any("monitoring" in i for i in issues)

    def test_validate_missing_nested_key(self, tmp_path, cm):
        data = {**MINIMAL_CONFIG}
        data["system"] = {"name": "X"}  # missing 'version'
        p = tmp_path / "no_version.yml"
        _write_yaml(data, str(p))
        cm.load(str(p))
        issues = cm.validate()
        assert any("system.version" in i for i in issues)

    def test_validate_type_mismatch(self, tmp_path, cm):
        data = {**MINIMAL_CONFIG}
        data["monitoring"] = {"enabled": "yes", "interval_seconds": 60}  # bool expected
        p = tmp_path / "bad_type.yml"
        _write_yaml(data, str(p))
        cm.load(str(p))
        issues = cm.validate()
        assert any("monitoring.enabled" in i for i in issues)

    def test_validate_returns_list(self, cm, tmp_config):
        cm.load(tmp_config)
        assert isinstance(cm.validate(), list)
