"""Phase L-4 — 配置 schema fail-fast 校验。

提供 pydantic v2 schema 与 :func:`validate_app_config` 入口，
让坏配置在启动期立即报错而不是延迟到运行时。

设计要点：
- 仅校验 **稳定的顶层 key**（``api`` / ``database`` / ``neo4j`` / ``models`` /
  ``output`` / ``logging`` / ``web_console`` / ``environment``）
- 子段使用 ``model_config = ConfigDict(extra="allow")``，避免对历史
  无 schema 段产生破坏性回归
- 默认 **非严格** —— 返回 :class:`ConfigValidationReport` 列出错误；
  ``strict=True`` 时对不可恢复错误抛 :class:`ConfigValidationError`

契约版本：``app-config-schema-v1``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CONTRACT_VERSION = "app-config-schema-v1"
APP_CONFIG_SCHEMA_CONTRACT_VERSION = CONTRACT_VERSION

__all__ = [
    "CONTRACT_VERSION",
    "APP_CONFIG_SCHEMA_CONTRACT_VERSION",
    "ApiConfig",
    "DatabaseConfig",
    "Neo4jConfig",
    "ModelsConfig",
    "OutputConfig",
    "LoggingConfig",
    "WebConsoleConfig",
    "AppConfigSchema",
    "ConfigValidationError",
    "ConfigValidationReport",
    "validate_app_config",
]


# ── 子段 schema ────────────────────────────────────────────────────────


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    version: Optional[str] = None
    cors_origins: Optional[List[str]] = None
    cors_methods: Optional[List[str]] = None
    cors_headers: Optional[List[str]] = None


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(default="sqlite")
    path: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    name: Optional[str] = None
    user: Optional[str] = None
    password_env: Optional[str] = None
    ssl_mode: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        normalized = str(value or "sqlite").strip().lower()
        if normalized not in {"sqlite", "postgresql", "postgres"}:
            raise ValueError(
                f"database.type 非法: {value!r}, 仅支持 sqlite / postgresql"
            )
        return "postgresql" if normalized == "postgres" else normalized

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if not isinstance(value, int) or not (1 <= int(value) <= 65535):
            raise ValueError(f"database.port 非法: {value!r}")
        return int(value)


class Neo4jConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    uri: Optional[str] = None
    user: Optional[str] = None
    password_env: Optional[str] = None
    database: Optional[str] = None

    @field_validator("uri")
    @classmethod
    def _validate_uri(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return value
        text = str(value).strip()
        valid_prefixes = ("neo4j://", "neo4j+s://", "bolt://", "bolt+s://")
        if not text.startswith(valid_prefixes):
            raise ValueError(
                f"neo4j.uri 非法: {value!r}, 必须以 {valid_prefixes} 之一开头"
            )
        return text


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    llm: Optional[Dict[str, Any]] = None


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_dir: Optional[str] = None
    paper_dir: Optional[str] = None


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: Optional[str] = None
    format: Optional[str] = None

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return value
        normalized = str(value).strip().upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in valid:
            raise ValueError(
                f"logging.level 非法: {value!r}, 必须为 {sorted(valid)}"
            )
        return normalized


class WebConsoleConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if not isinstance(value, int) or not (1 <= int(value) <= 65535):
            raise ValueError(f"web_console.port 非法: {value!r}")
        return int(value)


class AppConfigSchema(BaseModel):
    """应用配置顶层 schema —— 允许未知键，避免破坏历史段。"""

    model_config = ConfigDict(extra="allow")

    environment: Optional[str] = None
    api: Optional[ApiConfig] = None
    database: Optional[DatabaseConfig] = None
    neo4j: Optional[Neo4jConfig] = None
    models: Optional[ModelsConfig] = None
    output: Optional[OutputConfig] = None
    logging: Optional[LoggingConfig] = None
    web_console: Optional[WebConsoleConfig] = None


# ── 校验入口 ────────────────────────────────────────────────────────────


class ConfigValidationError(RuntimeError):
    """严格模式下配置校验失败时抛出。"""

    def __init__(self, message: str, *, errors: List[Dict[str, Any]]):
        super().__init__(message)
        self.errors = list(errors)


@dataclass
class ConfigValidationReport:
    """配置校验报告。"""

    ok: bool
    errors: List[Dict[str, Any]] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "contract_version": self.contract_version,
        }


def _format_errors(exc: ValidationError) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        errors.append(
            {
                "loc": ".".join(str(part) for part in loc),
                "type": err.get("type"),
                "msg": err.get("msg"),
            }
        )
    return errors


def validate_app_config(
    config: Mapping[str, Any],
    *,
    strict: bool = False,
) -> ConfigValidationReport:
    """对 ``config`` 字典做 fail-fast 校验。

    Parameters
    ----------
    config :
        通常来自 ``AppSettings.config`` 或 yaml 反序列化结果。
    strict :
        ``True`` 时校验失败抛 :class:`ConfigValidationError`；
        ``False`` 时返回 :class:`ConfigValidationReport`，由调用方决定后续行为。
    """
    if not isinstance(config, Mapping):
        message = f"config 必须是 Mapping，收到 {type(config).__name__}"
        if strict:
            raise ConfigValidationError(message, errors=[{"loc": "", "type": "type_error", "msg": message}])
        return ConfigValidationReport(ok=False, errors=[{"loc": "", "type": "type_error", "msg": message}])

    try:
        AppConfigSchema.model_validate(dict(config))
    except ValidationError as exc:
        errors = _format_errors(exc)
        if strict:
            raise ConfigValidationError(
                f"配置校验失败（{len(errors)} 处错误）",
                errors=errors,
            ) from exc
        return ConfigValidationReport(ok=False, errors=errors)

    return ConfigValidationReport(ok=True, errors=[])
