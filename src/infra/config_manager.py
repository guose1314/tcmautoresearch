"""
src/infra/config_manager.py
统一配置管理器 — 加载、分发、校验 config.yml
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# 顶级必须键
_REQUIRED_TOP_LEVEL_KEYS: List[str] = ["system", "monitoring", "database", "output"]

# 各顶级键下必须存在的子键
_REQUIRED_NESTED: Dict[str, List[str]] = {
    "system": ["name", "version"],
    "monitoring": ["enabled"],
    "database": ["path"],
    "output": ["directory"],
}

# 期望类型（只校验存在且类型可验证的字段）
_EXPECTED_TYPES: Dict[tuple, type] = {
    ("system", "version"): str,
    ("monitoring", "enabled"): bool,
    ("monitoring", "interval_seconds"): int,
}


class ConfigManager:
    """
    单例配置管理器。

    用法::

        cm = ConfigManager()
        cm.load("config.yml")
        issues = cm.validate()
        module_cfg = cm.get_module_config("document_preprocessing")
    """

    _instance: "Optional[ConfigManager]" = None

    # ---------- singleton ----------

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """清空单例，供测试使用。"""
        cls._instance = None

    # ---------- lifecycle ----------

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {}
        self._path: Optional[str] = None
        self._loaded: bool = False

    # ---------- public API ----------

    def load(self, path: str = "config.yml") -> Dict[str, Any]:
        """
        加载 YAML 配置文件。

        Args:
            path: 配置文件路径，支持相对路径（相对于当前工作目录）。

        Returns:
            加载后的配置字典。

        Raises:
            FileNotFoundError: 文件不存在。
            yaml.YAMLError: YAML 语法错误。
        """
        config_path = Path(path)
        if not config_path.is_absolute():
            config_path = Path.cwd() / config_path

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Config file must be a YAML mapping, got {type(data).__name__}")

        self._config = data
        self._path = str(config_path)
        self._loaded = True
        logger.info("ConfigManager loaded config from %s (%d top-level keys)", config_path, len(data))
        return self._config

    def get_module_config(self, module_name: str) -> Dict[str, Any]:
        """
        返回指定模块名称的配置子字典。

        查找顺序：
        1. config["modules"][module_name]
        2. config[module_name]
        3. 空字典（模块未配置时返回默认值）

        Args:
            module_name: 模块名称字符串。

        Returns:
            模块配置字典（不存在时返回 ``{}``）。
        """
        modules_block = self._config.get("modules", {})
        if isinstance(modules_block, dict) and module_name in modules_block:
            return dict(modules_block[module_name] or {})
        top_level = self._config.get(module_name)
        if isinstance(top_level, dict):
            return dict(top_level)
        return {}

    def validate(self) -> List[str]:
        """
        对已加载的配置执行基础架构校验。

        Returns:
            问题描述列表，空列表表示无问题。
        """
        if not self._loaded:
            return ["Config not loaded — call load() first"]

        issues: List[str] = []

        # 1. 必须存在的顶级键
        for key in _REQUIRED_TOP_LEVEL_KEYS:
            if key not in self._config:
                issues.append(f"Missing required top-level key: '{key}'")

        # 2. 各顶级键下必须存在的子键
        for top_key, sub_keys in _REQUIRED_NESTED.items():
            block = self._config.get(top_key)
            if not isinstance(block, dict):
                continue
            for sub_key in sub_keys:
                if sub_key not in block:
                    issues.append(f"Missing required key: '{top_key}.{sub_key}'")

        # 3. 类型校验
        for key_path, expected_type in _EXPECTED_TYPES.items():
            value = self._config
            try:
                for k in key_path:
                    value = value[k]
            except (KeyError, TypeError):
                continue  # 缺失的字段已在步骤 2 报告，此处跳过
            if not isinstance(value, expected_type):
                issues.append(
                    f"Type mismatch at '{'.'.join(key_path)}': "
                    f"expected {expected_type.__name__}, got {type(value).__name__}"
                )

        return issues

    # ---------- properties ----------

    @property
    def config(self) -> Dict[str, Any]:
        """返回完整配置字典（只读视图）。"""
        return dict(self._config)

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def path(self) -> Optional[str]:
        return self._path
