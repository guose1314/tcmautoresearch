"""Architecture 3.0 配置中心，支持环境隔离与环境变量覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_NAME = "config.yml"
DEFAULT_ENVIRONMENT = "development"
MODULE_CONFIG_CANDIDATES = {
    "normalizer": (("normalizer",), ("collector", "normalizer")),
    "document_preprocessor": (("document_preprocessor",), ("modules", "document_preprocessing")),
    "advanced_entity_extractor": (("advanced_entity_extractor",), ("modules", "entity_extraction")),
    "relation_extractor": (("relation_extractor",),),
}
MODULE_DEFAULTS = {
    "normalizer": {
        "convert_mode": "t2s",
        "default_language": "zh",
        "drop_empty_metadata": True,
    },
    "document_preprocessor": {
        "convert_mode": "t2s",
    },
    "advanced_entity_extractor": {
        "external_dicts": [],
    },
    "relation_extractor": {},
}
DEFAULT_CONFIG = {
    "config_center": {
        "default_environment": DEFAULT_ENVIRONMENT,
        "environments_dir": "./config",
        "secrets_dir": "./secrets",
        "secrets_file": "./secrets.yml",
        "env_prefix": "TCM",
        "isolate_paths": True,
    },
    "api": {
        "title": "TCM Auto Research API",
        "version": "3.0.0",
        "cors_origins": ["*"],
    },
    "web_console": {
        "title": "TCM Auto Research Web Console",
        "version": "0.2.0",
        "job_storage_dir": f"./output/{DEFAULT_ENVIRONMENT}/web_console_jobs",
        "cors_origins": ["*"],
    },
}
PATH_KEYS = (
    ("database", "path"),
    ("output", "directory"),
    ("output", "backup_directory"),
    ("logging", "file"),
    ("models", "llm", "cache_dir"),
    ("ctext_corpus", "whitelist", "path"),
    ("ctext_corpus", "batch_manifest_output"),
    ("web_console", "job_storage_dir"),
)
RUNTIME_SECRET_MAPPINGS = (
    (("models", "llm", "api_key"), (("models", "llm", "api_key"),)),
    (("clinical_gap_analysis", "api_key"), (("clinical_gap_analysis", "api_key"), ("models", "llm", "api_key"))),
    (("literature_retrieval", "pubmed_email"), (("literature_retrieval", "pubmed_email"),)),
    (("literature_retrieval", "pubmed_api_key"), (("literature_retrieval", "pubmed_api_key"),)),
    (("literature_retrieval", "source_credentials", "google_scholar", "api_key"), (("literature_retrieval", "source_credentials", "google_scholar", "api_key"),)),
    (("literature_retrieval", "source_credentials", "cochrane", "api_key"), (("literature_retrieval", "source_credentials", "cochrane", "api_key"),)),
    (("literature_retrieval", "source_credentials", "embase", "api_key"), (("literature_retrieval", "source_credentials", "embase", "api_key"),)),
    (("literature_retrieval", "source_credentials", "scopus", "api_key"), (("literature_retrieval", "source_credentials", "scopus", "api_key"),)),
    (("literature_retrieval", "source_credentials", "web_of_science", "api_key"), (("literature_retrieval", "source_credentials", "web_of_science", "api_key"),)),
    (("literature_retrieval", "source_credentials", "lexicomp", "api_key"), (("literature_retrieval", "source_credentials", "lexicomp", "api_key"),)),
    (("literature_retrieval", "source_credentials", "clinicalkey", "api_key"), (("literature_retrieval", "source_credentials", "clinicalkey", "api_key"),)),
)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
            continue
        merged[key] = value
    return merged


def _read_yaml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件必须是映射结构: {path}")
    return payload


def _normalize_environment_name(environment: str | None) -> str:
    candidate = str(environment or "").strip().lower().replace("-", "_")
    return candidate or DEFAULT_ENVIRONMENT


def _normalize_key_path(path: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(path, str):
        return tuple(segment for segment in path.split(".") if segment)
    return tuple(str(segment) for segment in path if str(segment))


def _get_nested(mapping: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _set_nested(mapping: Dict[str, Any], keys: Sequence[str], value: Any) -> None:
    current = mapping
    for key in keys[:-1]:
        nested = current.get(key)
        if not isinstance(nested, dict):
            nested = {}
            current[key] = nested
        current = nested
    current[keys[-1]] = value


def _load_env_overrides(config: Dict[str, Any], env_prefix: str) -> Dict[str, Any]:
    normalized_prefix = f"{str(env_prefix or 'TCM').strip().upper()}__"
    overridden = dict(config)
    for name, raw_value in os.environ.items():
        if not name.startswith(normalized_prefix):
            continue
        suffix = name[len(normalized_prefix) :]
        path_keys = [segment.strip().lower() for segment in suffix.split("__") if segment.strip()]
        if not path_keys:
            continue
        try:
            value = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            value = raw_value
        _set_nested(overridden, path_keys, value)
    return overridden


def _load_secret_overrides(env_prefix: str) -> Dict[str, Any]:
    overridden: Dict[str, Any] = {}
    prefixes = (
        f"{str(env_prefix or 'TCM').strip().upper()}__SECRETS__",
        f"{str(env_prefix or 'TCM').strip().upper()}_SECRET__",
    )
    for name, raw_value in os.environ.items():
        matched_prefix = next((prefix for prefix in prefixes if name.startswith(prefix)), None)
        if matched_prefix is None:
            continue
        suffix = name[len(matched_prefix) :]
        path_keys = [segment.strip().lower() for segment in suffix.split("__") if segment.strip()]
        if not path_keys:
            continue
        try:
            value = yaml.safe_load(raw_value)
        except yaml.YAMLError:
            value = raw_value
        _set_nested(overridden, path_keys, value)
    return overridden


def _resolve_relative_path(root_path: Path, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate:
        return value
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((root_path / path).resolve())


def _resolve_config_paths(root_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    resolved = dict(config)
    for key_path in PATH_KEYS:
        current_value = _get_nested(resolved, key_path)
        if current_value is None:
            continue
        _set_nested(resolved, key_path, _resolve_relative_path(root_path, current_value))
    return resolved


@dataclass(frozen=True)
class AppSettings:
    root_path: Path
    environment: str
    config: Dict[str, Any]
    secrets: Dict[str, Any]
    loaded_files: tuple[str, ...]
    loaded_secret_files: tuple[str, ...]
    env_prefix: str

    def get(self, dotted_path: str, default: Any = None) -> Any:
        keys = _normalize_key_path(dotted_path)
        if not keys:
            return default
        return _get_nested(self.config, keys, default)

    def get_section(
        self,
        *candidates: str | Sequence[str],
        default: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(default or {})
        found_mapping = False
        for candidate in candidates:
            keys = _normalize_key_path(candidate)
            if not keys:
                continue
            payload = _get_nested(self.config, keys)
            if isinstance(payload, Mapping):
                merged = _deep_merge(merged, payload)
                found_mapping = True
        return merged if found_mapping or default is not None else {}

    def get_secret(
        self,
        *candidates: str | Sequence[str],
        default: Any = None,
    ) -> Any:
        for candidate in candidates:
            keys = _normalize_key_path(candidate)
            if not keys:
                continue
            payload = _get_nested(self.secrets, keys)
            if payload is not None:
                return payload
        return default

    def get_secret_section(
        self,
        *candidates: str | Sequence[str],
        default: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(default or {})
        found_mapping = False
        for candidate in candidates:
            keys = _normalize_key_path(candidate)
            if not keys:
                continue
            payload = _get_nested(self.secrets, keys)
            if isinstance(payload, Mapping):
                merged = _deep_merge(merged, payload)
                found_mapping = True
        return merged if found_mapping or default is not None else {}

    def materialize_runtime_config(self) -> Dict[str, Any]:
        materialized = _deep_merge({}, self.config)
        for target_path, secret_candidates in RUNTIME_SECRET_MAPPINGS:
            secret_value = self.get_secret(*secret_candidates)
            if secret_value is None:
                continue
            _set_nested(materialized, target_path, secret_value)
        return materialized

    def module_config(self, module_name: str) -> Dict[str, Any]:
        normalized_name = str(module_name or "").strip()
        merged = dict(MODULE_DEFAULTS.get(normalized_name, {}))
        for key_path in MODULE_CONFIG_CANDIDATES.get(normalized_name, ()): 
            payload = _get_nested(self.config, key_path, {})
            if isinstance(payload, Mapping):
                merged = _deep_merge(merged, payload)
        merged.setdefault("environment", self.environment)
        return merged

    @property
    def api_title(self) -> str:
        return str(self.get("api.title", DEFAULT_CONFIG["api"]["title"]))

    @property
    def api_version(self) -> str:
        configured = self.get("api.version") or self.get("system.version")
        return str(configured or DEFAULT_CONFIG["api"]["version"])

    @property
    def api_cors_origins(self) -> list[str]:
        origins = self.get("api.cors_origins", ["*"])
        if isinstance(origins, Iterable) and not isinstance(origins, (str, bytes, dict)):
            return [str(origin) for origin in origins]
        return ["*"]

    @property
    def web_console_title(self) -> str:
        return str(self.get("web_console.title", DEFAULT_CONFIG["web_console"]["title"]))

    @property
    def web_console_version(self) -> str:
        return str(self.get("web_console.version", DEFAULT_CONFIG["web_console"]["version"]))

    @property
    def web_console_cors_origins(self) -> list[str]:
        origins = self.get("web_console.cors_origins", self.api_cors_origins)
        if isinstance(origins, Iterable) and not isinstance(origins, (str, bytes, dict)):
            return [str(origin) for origin in origins]
        return list(self.api_cors_origins)

    @property
    def job_storage_dir(self) -> str:
        value = self.get("web_console.job_storage_dir")
        if isinstance(value, str) and value.strip():
            return value
        fallback = self.root_path / "output" / self.environment / "web_console_jobs"
        return str(fallback.resolve())

    @property
    def export_directory(self) -> Path:
        base_output = self.get("output.directory")
        if isinstance(base_output, str) and base_output.strip():
            output_dir = Path(base_output)
        else:
            output_dir = (self.root_path / "output" / self.environment).resolve()
        return output_dir / "system_exports"

    @property
    def system_name(self) -> str:
        return str(self.get("system.name", "中医古籍全自动研究系统"))

    @property
    def system_description(self) -> str:
        return str(self.get("system.description", "Architecture 3.0 FastAPI REST API service layer"))


class ConfigCenter:
    """集中管理基础配置、环境覆盖与环境变量覆盖。"""

    def __init__(
        self,
        *,
        root_path: str | Path | None = None,
        config_path: str | Path | None = None,
        environment: str | None = None,
    ):
        resolved_root_path = Path(root_path or WORKSPACE_ROOT).expanduser()
        if config_path is not None:
            resolved_config_path = Path(config_path).expanduser()
            if root_path is None and resolved_config_path.is_absolute():
                resolved_root_path = resolved_config_path.parent
            resolved_root_path = resolved_root_path.resolve()
            if not resolved_config_path.is_absolute():
                resolved_config_path = (resolved_root_path / resolved_config_path).resolve()
            else:
                resolved_config_path = resolved_config_path.resolve()
        else:
            resolved_root_path = resolved_root_path.resolve()
            resolved_config_path = resolved_root_path / DEFAULT_CONFIG_NAME

        self.root_path = resolved_root_path
        self.config_path = resolved_config_path
        self.requested_environment = environment

    def load(self) -> AppSettings:
        base_config = _deep_merge(DEFAULT_CONFIG, _read_yaml_file(self.config_path))
        config_center_config = base_config.get("config_center") if isinstance(base_config.get("config_center"), dict) else {}
        default_environment = config_center_config.get("default_environment", DEFAULT_ENVIRONMENT)
        environment = _normalize_environment_name(
            self.requested_environment
            or os.getenv("TCM_ENV")
            or os.getenv("APP_ENV")
            or base_config.get("environment", {}).get("name")
            or default_environment
        )
        env_prefix = str(config_center_config.get("env_prefix") or "TCM").strip().upper() or "TCM"

        merged = dict(base_config)
        loaded_files = [str(self.config_path)]
        for candidate in self._candidate_environment_files(environment, config_center_config):
            if candidate.exists():
                merged = _deep_merge(merged, _read_yaml_file(candidate))
                loaded_files.append(str(candidate.resolve()))
                break

        environment_config = merged.get("environment") if isinstance(merged.get("environment"), dict) else {}
        environment_config = dict(environment_config)
        environment_config["name"] = environment
        merged["environment"] = environment_config
        merged = _load_env_overrides(merged, env_prefix)
        merged = _resolve_config_paths(self.root_path, merged)

        merged_secrets: Dict[str, Any] = {}
        loaded_secret_files: list[str] = []
        for candidate in self._candidate_secret_files(environment, config_center_config):
            if candidate.exists():
                merged_secrets = _deep_merge(merged_secrets, _read_yaml_file(candidate))
                loaded_secret_files.append(str(candidate.resolve()))
        merged_secrets = _deep_merge(merged_secrets, _load_secret_overrides(env_prefix))

        return AppSettings(
            root_path=self.root_path,
            environment=environment,
            config=merged,
            secrets=merged_secrets,
            loaded_files=tuple(loaded_files),
            loaded_secret_files=tuple(loaded_secret_files),
            env_prefix=env_prefix,
        )

    def _candidate_environment_files(
        self,
        environment: str,
        config_center_config: Mapping[str, Any],
    ) -> list[Path]:
        environments_dir = Path(str(config_center_config.get("environments_dir") or "./config"))
        if not environments_dir.is_absolute():
            environments_dir = (self.root_path / environments_dir).resolve()
        return [
            environments_dir / f"{environment}.yml",
            environments_dir / f"{environment}.yaml",
            self.root_path / f"config.{environment}.yml",
            self.root_path / f"config.{environment}.yaml",
        ]

    def _candidate_secret_files(
        self,
        environment: str,
        config_center_config: Mapping[str, Any],
    ) -> list[Path]:
        configured_secret_file = str(config_center_config.get("secrets_file") or "./secrets.yml")
        base_secret_file = Path(configured_secret_file)
        if not base_secret_file.is_absolute():
            base_secret_file = (self.root_path / base_secret_file).resolve()

        secrets_dir = Path(str(config_center_config.get("secrets_dir") or "./secrets"))
        if not secrets_dir.is_absolute():
            secrets_dir = (self.root_path / secrets_dir).resolve()

        return [
            base_secret_file,
            secrets_dir / f"{environment}.yml",
            secrets_dir / f"{environment}.yaml",
            self.root_path / f"secrets.{environment}.yml",
            self.root_path / f"secrets.{environment}.yaml",
        ]


def load_settings(
    *,
    root_path: str | Path | None = None,
    config_path: str | Path | None = None,
    environment: str | None = None,
) -> AppSettings:
    return ConfigCenter(root_path=root_path, config_path=config_path, environment=environment).load()


def load_settings_section(
    *candidates: str | Sequence[str],
    root_path: str | Path | None = None,
    config_path: str | Path | None = None,
    environment: str | None = None,
    default: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    settings = load_settings(root_path=root_path, config_path=config_path, environment=environment)
    return settings.get_section(*candidates, default=default)


def load_secret_section(
    *candidates: str | Sequence[str],
    root_path: str | Path | None = None,
    config_path: str | Path | None = None,
    environment: str | None = None,
    default: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    settings = load_settings(root_path=root_path, config_path=config_path, environment=environment)
    return settings.get_secret_section(*candidates, default=default)