"""Schema registry adapter for LLMGateway structured outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from src.infra.prompt_registry import (
    _build_schema_instruction,
    _extract_json_payload,
    _validate_schema,
    get_prompt_template,
    load_prompt_registry_settings,
)


@dataclass(frozen=True)
class SchemaBinding:
    """Resolved JSON schema bound to an LLMGateway request."""

    name: str
    schema: Dict[str, Any]
    output_kind: str = "json"
    source: str = ""
    schema_version: str = "v1"

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "schema_name": self.name,
            "schema_found": True,
            "schema_source": self.source,
            "schema_version": self.schema_version,
            "output_kind": self.output_kind,
        }


@dataclass(frozen=True)
class SchemaResolution:
    """Schema lookup outcome plus prompt-registry behavior settings."""

    schema_name: str
    binding: Optional[SchemaBinding]
    settings: Dict[str, Any]
    warnings: List[str]

    def to_metadata(self, *, prompt_schema_included: bool = False) -> Dict[str, Any]:
        payload = {
            "schema_name": self.schema_name,
            "schema_found": self.binding is not None,
            "prompt_schema_included": bool(prompt_schema_included),
            "fail_on_schema_validation": bool(
                self.settings.get("fail_on_schema_validation", False)
            ),
        }
        if self.binding is not None:
            payload.update(self.binding.to_metadata())
        if self.warnings:
            payload["resolution_warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class SchemaValidation:
    """JSON parse and lightweight schema validation result."""

    schema_name: str
    parsed: Any = None
    schema_valid: bool = False
    errors: List[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            object.__setattr__(self, "errors", [])

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_valid": bool(self.schema_valid),
            "error_count": len(self.errors or []),
            "errors": list(self.errors or []),
        }


def resolve_schema_binding(
    schema_name: str,
    *,
    context: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> SchemaResolution:
    """Resolve a schema_name from request payloads or the Prompt Registry."""

    normalized_name = str(schema_name or "").strip()
    settings = load_prompt_registry_settings()
    if not normalized_name:
        return SchemaResolution("", None, settings, [])

    if not settings.get("enabled", True):
        return SchemaResolution(
            normalized_name,
            None,
            settings,
            [f"schema_registry_disabled:{normalized_name}"],
        )

    for source_name, payload in (
        ("request.context", context or {}),
        ("request.metadata", metadata or {}),
    ):
        schema = _schema_from_payload(normalized_name, payload)
        if schema is not None:
            return SchemaResolution(
                normalized_name,
                SchemaBinding(
                    name=normalized_name,
                    schema=schema,
                    output_kind=_infer_output_kind(schema),
                    source=source_name,
                    schema_version=str(
                        _read_schema_version(normalized_name, payload) or "v1"
                    ),
                ),
                settings,
                [],
            )

    try:
        template = get_prompt_template(normalized_name)
    except KeyError:
        template = None
    if template is not None and isinstance(template.output_schema, Mapping):
        return SchemaResolution(
            normalized_name,
            SchemaBinding(
                name=normalized_name,
                schema=dict(template.output_schema),
                output_kind=str(template.output_kind or "json"),
                source="prompt_registry",
                schema_version=str(template.schema_version or "v1"),
            ),
            settings,
            [],
        )

    return SchemaResolution(
        normalized_name,
        None,
        settings,
        [f"schema_missing:{normalized_name}"],
    )


def build_schema_prompt_instruction(resolution: SchemaResolution) -> str:
    """Build the schema prompt suffix for a resolved schema."""

    if resolution.binding is None:
        return ""
    if not resolution.settings.get("include_schema_in_prompt", True):
        return ""
    return _build_schema_instruction(
        resolution.binding.output_kind,
        resolution.binding.schema,
        resolution.settings,
    )


def validate_schema_output(
    resolution: SchemaResolution,
    raw: Any,
) -> Optional[SchemaValidation]:
    """Parse and validate generated output for a resolved schema."""

    binding = resolution.binding
    if binding is None:
        return None

    parsed = _extract_json_payload(raw, expected_root=_expected_root(binding))
    if parsed is None:
        return SchemaValidation(
            schema_name=binding.name,
            parsed=None,
            schema_valid=False,
            errors=["未提取到合法 JSON"],
        )

    errors = _validate_schema(parsed, binding.schema)
    return SchemaValidation(
        schema_name=binding.name,
        parsed=parsed,
        schema_valid=not errors,
        errors=list(errors),
    )


def build_schema_warning(validation: SchemaValidation) -> str:
    """Convert a failed schema validation into a gateway warning string."""

    errors = list(validation.errors or [])
    detail = "; ".join(errors[:3]) if errors else "unknown schema validation error"
    if errors == ["未提取到合法 JSON"]:
        return f"schema_invalid_json:{validation.schema_name}: {detail}"
    return f"schema_validation_failed:{validation.schema_name}: {detail}"


def _schema_from_payload(
    schema_name: str,
    payload: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    for registry_key in ("schema_registry", "schemas", "json_schemas"):
        registry = payload.get(registry_key)
        if not isinstance(registry, Mapping):
            continue
        schema = registry.get(schema_name)
        if isinstance(schema, Mapping):
            return dict(schema)

    for direct_key in ("output_schema", "json_schema"):
        schema = payload.get(direct_key)
        if not isinstance(schema, Mapping):
            continue
        nested = schema.get(schema_name)
        if isinstance(nested, Mapping):
            return dict(nested)
        if _looks_like_json_schema(schema):
            return dict(schema)
    return None


def _read_schema_version(schema_name: str, payload: Mapping[str, Any]) -> str:
    versions = payload.get("schema_versions")
    if isinstance(versions, Mapping) and schema_name in versions:
        return str(versions[schema_name] or "").strip()
    return str(payload.get("schema_version") or "").strip()


def _looks_like_json_schema(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("type", "properties", "items", "required"))


def _infer_output_kind(schema: Mapping[str, Any]) -> str:
    root_type = schema.get("type")
    if root_type == "object":
        return "json_object"
    if root_type == "array":
        return "json_array"
    if isinstance(root_type, list):
        if "object" in root_type:
            return "json_object"
        if "array" in root_type:
            return "json_array"
    return "json"


def _expected_root(binding: SchemaBinding) -> Optional[str]:
    if binding.output_kind == "json_object":
        return "object"
    if binding.output_kind == "json_array":
        return "array"
    return None


__all__ = [
    "SchemaBinding",
    "SchemaResolution",
    "SchemaValidation",
    "build_schema_prompt_instruction",
    "build_schema_warning",
    "resolve_schema_binding",
    "validate_schema_output",
]
