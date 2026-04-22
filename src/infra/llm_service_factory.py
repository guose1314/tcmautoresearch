"""Phase L-3 — 统一 LLM 服务工厂入口。

将 ``Llama(...)``、``LLMEngine``、``CachedLLMService.from_*`` 等多种 LLM
入口收口到 :class:`LLMServiceFactory`，业务代码只需依赖该工厂即可获得：

- ``CachedLLMService`` 实例（按 engine / api / gap config）
- 启动期审计：仓库内是否仍存在未授权的 ``Llama(`` 直接调用

允许的 ``Llama(`` 调用点：仅 ``src/llm/llm_engine.py``。其他位置出现
``Llama(`` 都会被 :func:`assert_no_unexpected_llama_calls` 视为违规。

契约版本：``llm-service-factory-v1``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Tuple

CONTRACT_VERSION = "llm-service-factory-v1"
LLM_SERVICE_FACTORY_CONTRACT_VERSION = CONTRACT_VERSION

DEFAULT_LLAMA_CALL_ALLOWLIST: Tuple[str, ...] = (
    "src/llm/llm_engine.py",
    # 工厂自身的 docstring / 常量定义会出现 ``Llama(`` 字面量，需放行
    "src/infra/llm_service_factory.py",
)

_LLAMA_CALL_PATTERN = re.compile(r"\bLlama\s*\(")

__all__ = [
    "CONTRACT_VERSION",
    "LLM_SERVICE_FACTORY_CONTRACT_VERSION",
    "DEFAULT_LLAMA_CALL_ALLOWLIST",
    "LlamaCallViolation",
    "LLMServiceFactory",
    "scan_llama_call_violations",
    "assert_no_unexpected_llama_calls",
]


@dataclass(frozen=True)
class LlamaCallViolation:
    """一次未授权的 ``Llama(`` 直接调用记录。"""

    file_path: str
    line_number: int
    line_text: str

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_text": self.line_text,
        }


@dataclass
class LLMServiceFactory:
    """统一 LLM 服务工厂。

    Parameters
    ----------
    cached_llm_service_cls :
        可注入的 ``CachedLLMService`` 替身（用于测试）。默认 ``None`` 表示
        懒加载真实实现，避免在导入期硬依赖 llama-cpp-python。
    """

    cached_llm_service_cls: Optional[Any] = None
    contract_version: str = field(default=CONTRACT_VERSION, init=False)

    def _resolve_cls(self) -> Any:
        if self.cached_llm_service_cls is not None:
            return self.cached_llm_service_cls
        # 懒导入，避免模块加载期触发底层依赖检查
        from src.infra.llm_service import CachedLLMService

        return CachedLLMService

    # ── 工厂方法 ─────────────────────────────────────────────────────

    def create_from_engine_config(self, engine_config: Mapping[str, Any], **kwargs: Any) -> Any:
        cls = self._resolve_cls()
        return cls.from_engine_config(dict(engine_config or {}), **kwargs)

    def create_from_api_config(self, api_config: Mapping[str, Any], **kwargs: Any) -> Any:
        cls = self._resolve_cls()
        return cls.from_api_config(dict(api_config or {}), **kwargs)

    def create_from_config(self, config: Mapping[str, Any], **kwargs: Any) -> Any:
        cls = self._resolve_cls()
        return cls.from_config(dict(config or {}), **kwargs)

    def create_from_gap_config(
        self,
        gap_config: Mapping[str, Any],
        llm_config: Mapping[str, Any],
        **kwargs: Any,
    ) -> Any:
        cls = self._resolve_cls()
        return cls.from_gap_config(dict(gap_config or {}), dict(llm_config or {}), **kwargs)


def scan_llama_call_violations(
    roots: Iterable[Path | str],
    *,
    allowlist: Iterable[str] = DEFAULT_LLAMA_CALL_ALLOWLIST,
    workspace_root: Path | str | None = None,
) -> List[LlamaCallViolation]:
    """扫描指定根目录下所有 ``*.py`` 文件，返回未授权的 ``Llama(`` 调用。

    ``allowlist`` 中的文件路径以仓库根为基准（POSIX 分隔符），
    例如 ``src/llm/llm_engine.py``。
    """
    base_root = Path(workspace_root).resolve() if workspace_root else None
    normalized_allowlist = {str(item).replace("\\", "/").strip("/") for item in allowlist}
    violations: List[LlamaCallViolation] = []

    for raw_root in roots:
        root_path = Path(raw_root)
        if not root_path.is_absolute() and base_root is not None:
            root_path = base_root / root_path
        if not root_path.exists():
            continue

        for file_path in root_path.rglob("*.py"):
            try:
                relative = (
                    file_path.resolve().relative_to(base_root)
                    if base_root is not None
                    else file_path
                )
            except ValueError:
                relative = file_path
            rel_text = str(relative).replace("\\", "/")
            if rel_text in normalized_allowlist:
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if _LLAMA_CALL_PATTERN.search(line):
                    violations.append(
                        LlamaCallViolation(
                            file_path=rel_text,
                            line_number=line_number,
                            line_text=line.rstrip(),
                        )
                    )

    return violations


def assert_no_unexpected_llama_calls(
    roots: Iterable[Path | str],
    *,
    allowlist: Iterable[str] = DEFAULT_LLAMA_CALL_ALLOWLIST,
    workspace_root: Path | str | None = None,
) -> None:
    """若存在未授权的 ``Llama(`` 直接调用则抛 :class:`AssertionError`。"""
    violations = scan_llama_call_violations(
        roots,
        allowlist=allowlist,
        workspace_root=workspace_root,
    )
    if violations:
        formatted = "\n".join(
            f"  - {v.file_path}:{v.line_number}: {v.line_text}" for v in violations
        )
        raise AssertionError(
            f"检测到 {len(violations)} 处未授权的 Llama( 直接调用，"
            f"请改用 LLMServiceFactory：\n{formatted}"
        )
