"""模块工厂：提供轻量依赖注入能力。"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Dict, Optional

Provider = Callable[[Dict[str, Any]], Any]


@dataclass
class FactorySpec:
    """工厂注册项。"""

    key: str
    provider: Provider


class ModuleFactory:
    """模块工厂（Module Factory）。

    支持两类注册：
    1. register(key, provider): 注册可调用 provider(config) -> instance
    2. register_path(key, "pkg.module:ClassName"): 从路径动态加载类并实例化
    """

    def __init__(self) -> None:
        self._providers: Dict[str, Provider] = {}

    def register(self, key: str, provider: Provider) -> None:
        if not key:
            raise ValueError("factory key 不能为空")
        self._providers[key] = provider

    def register_path(self, key: str, class_path: str) -> None:
        if ":" not in class_path:
            raise ValueError(f"非法 class_path: {class_path}")
        module_name, class_name = class_path.split(":", 1)

        def _provider(config: Dict[str, Any]) -> Any:
            module = import_module(module_name)
            cls = getattr(module, class_name)
            return cls(config)

        self.register(key, _provider)

    def create(self, key: str, config: Optional[Dict[str, Any]] = None) -> Any:
        if key not in self._providers:
            raise KeyError(f"未注册模块: {key}")
        return self._providers[key](config or {})

    def has(self, key: str) -> bool:
        return key in self._providers

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "ModuleFactory":
        factory = cls()
        cfg = config or {}
        mapping = cfg.get("providers")
        if isinstance(mapping, dict):
            for key, class_path in mapping.items():
                if isinstance(class_path, str) and class_path:
                    factory.register_path(key, class_path)
        return factory
