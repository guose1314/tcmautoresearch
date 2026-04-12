from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

_CONTRACT_VERSION = "phase_result.v1"
_STANDARD_KEYS = frozenset({"phase", "status", "results", "artifacts", "metadata", "error"})
_DEPRECATED_FALLBACKS_KEY = "deprecated_field_fallbacks"
_REMOVED_COMPATIBILITY_EXTRA_FIELDS_BY_PHASE = {
    "publish": frozenset(
        {
            "publications",
            "deliverables",
            "citations",
            "bibtex",
            "gbt7714",
            "formatted_references",
            "paper_draft",
            "imrd_reports",
            "paper_language",
            "output_files",
            "report_output_files",
            "report_generation_errors",
            "report_session_result",
            "analysis_results",
            "research_artifact",
        }
    ),
}
_REMOVED_RESULT_FIELDS_BY_PHASE = {
    "publish": frozenset(
        {
            "paper_draft",
            "imrd_reports",
        }
    ),
}


@dataclass
class PhaseResult:
    """研究阶段统一返回契约。"""

    phase: str
    status: str = "completed"
    results: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self, extra_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "phase": self.phase,
            "status": self.status,
            "results": self.results,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "error": self.error,
        }
        if extra_fields:
            for key, value in extra_fields.items():
                if key not in _STANDARD_KEYS:
                    payload[key] = value
        return payload


def build_phase_result(
    phase: str,
    *,
    status: str = "completed",
    results: Optional[Dict[str, Any]] = None,
    artifacts: Optional[Iterable[Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error: Optional[Any] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_extra_fields = dict(extra_fields or {})
    normalized_artifacts = _normalize_artifacts(artifacts, raw_extra_fields)
    filtered_extra_fields = _filter_phase_extra_fields(str(phase), raw_extra_fields)
    normalized_metadata = dict(metadata or {})
    normalized_metadata.setdefault("contract_version", _CONTRACT_VERSION)
    normalized_metadata.setdefault("artifact_count", len(normalized_artifacts))
    normalized_metadata.setdefault("status", status)
    payload = PhaseResult(
        phase=str(phase),
        status=str(status),
        results=dict(results or {}),
        artifacts=normalized_artifacts,
        metadata=normalized_metadata,
        error=_normalize_error(error),
    )
    return payload.to_dict(extra_fields=filtered_extra_fields)


def normalize_phase_result(phase: str, raw_result: Any) -> Dict[str, Any]:
    if isinstance(raw_result, PhaseResult):
        raw_payload: Dict[str, Any] = raw_result.to_dict()
    elif isinstance(raw_result, dict):
        raw_payload = dict(raw_result)
    else:
        raw_payload = {"results": {"value": raw_result}}

    phase_name = str(raw_payload.get("phase") or phase)
    metadata = raw_payload.get("metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    normalized_results = raw_payload.get("results")
    if isinstance(normalized_results, dict):
        normalized_results = dict(normalized_results)
        inferred_results = _infer_results(phase_name, raw_payload)
        for key, value in inferred_results.items():
            normalized_results.setdefault(key, value)
    else:
        normalized_results = _infer_results(phase_name, raw_payload)
    normalized_results = _filter_phase_results(phase_name, normalized_results)

    error = _normalize_error(raw_payload.get("error"))
    status = str(raw_payload.get("status") or _infer_status(phase_name, raw_payload, normalized_metadata, error)).strip().lower()
    if not status:
        status = "completed"

    normalized_metadata.setdefault("contract_version", _CONTRACT_VERSION)
    normalized_metadata.setdefault("status", status)
    artifacts = _normalize_artifacts(raw_payload.get("artifacts"), raw_payload)
    normalized_metadata.setdefault("artifact_count", len(artifacts))

    return build_phase_result(
        phase_name,
        status=status,
        results=normalized_results,
        artifacts=artifacts,
        metadata=normalized_metadata,
        error=error,
        extra_fields=raw_payload,
    )


def get_phase_results(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    payload = result.get("results")
    if isinstance(payload, dict):
        return payload
    return {}


def is_phase_result_payload(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return (
        "phase" in result
        and isinstance(result.get("results"), dict)
        and isinstance(result.get("metadata"), dict)
        and "error" in result
    )


def get_phase_value(result: Any, key: str, default: Any = None) -> Any:
    if not isinstance(result, dict):
        return default
    nested = get_phase_results(result)
    if key in nested and nested.get(key) is not None:
        return nested.get(key)
    if key in result and result.get(key) is not None:
        _record_deprecated_fallback(result, key)
        return result.get(key)
    return default


def get_phase_artifact_map(result: Any) -> Dict[str, str]:
    if not isinstance(result, dict):
        return {}

    artifact_map: Dict[str, str] = {}
    for artifact in result.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        name = str(artifact.get("name") or artifact.get("type") or "").strip()
        path = str(artifact.get("path") or "").strip()
        if name and path:
            artifact_map[name] = path

    if artifact_map:
        return artifact_map

    fallback = result.get("output_files")
    if isinstance(fallback, dict):
        _record_deprecated_fallback(result, "output_files")
        return {
            str(name): str(path)
            for name, path in fallback.items()
            if path not in (None, "", [], {})
        }
    return {}


def get_phase_deprecated_fallbacks(result: Any) -> List[str]:
    if not isinstance(result, dict):
        return []
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return []
    fallbacks = metadata.get(_DEPRECATED_FALLBACKS_KEY)
    if not isinstance(fallbacks, list):
        return []
    return [str(item) for item in fallbacks if str(item).strip()]


def _record_deprecated_fallback(result: Dict[str, Any], key: str) -> None:
    metadata = result.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return
    fallbacks = metadata.setdefault(_DEPRECATED_FALLBACKS_KEY, [])
    if not isinstance(fallbacks, list):
        return
    marker = str(key).strip()
    if marker and marker not in fallbacks:
        fallbacks.append(marker)


def _infer_status(
    phase: str,
    payload: Dict[str, Any],
    metadata: Dict[str, Any],
    error: Optional[str],
) -> str:
    if error:
        return "failed"

    metadata_status = str(metadata.get("status") or "").strip().lower()
    if metadata_status:
        return metadata_status

    validation_status = str(metadata.get("validation_status") or "").strip().lower()
    if validation_status == "blocked":
        return "blocked"

    if phase == "experiment" and payload.get("selected_hypothesis") is None:
        return "blocked"

    return "completed"


def _infer_results(phase: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    phase_key_map = {
        "observe": (
            "observations",
            "findings",
            "corpus_collection",
            "ingestion_pipeline",
            "literature_pipeline",
        ),
        "hypothesis": (
            "hypotheses",
            "validation_iterations",
            "domain",
        ),
        "experiment": (
            "experiments",
            "study_protocol",
            "selected_hypothesis",
            "success_rate",
        ),
        "analyze": (
            "reasoning_results",
            "data_mining_result",
        ),
        "publish": (
            "publications",
            "deliverables",
            "citations",
            "bibtex",
            "gbt7714",
            "formatted_references",
            "output_files",
            "analysis_results",
            "research_artifact",
        ),
        "reflect": (
            "reflections",
            "improvement_plan",
            "quality_assessment",
            "learning_summary",
        ),
    }
    keys = phase_key_map.get(phase, ())
    inferred = {
        key: payload[key]
        for key in keys
        if key in payload and payload.get(key) is not None
    }
    if inferred:
        return inferred
    removed_fields = _REMOVED_COMPATIBILITY_EXTRA_FIELDS_BY_PHASE.get(str(phase), frozenset())
    return {
        key: value
        for key, value in payload.items()
        if key not in _STANDARD_KEYS and key not in removed_fields and value is not None
    }


def _filter_phase_extra_fields(phase: str, extra_fields: Dict[str, Any]) -> Dict[str, Any]:
    removed_fields = _REMOVED_COMPATIBILITY_EXTRA_FIELDS_BY_PHASE.get(str(phase), frozenset())
    if not removed_fields:
        return dict(extra_fields)
    return {
        key: value
        for key, value in extra_fields.items()
        if key not in removed_fields
    }


def _filter_phase_results(phase: str, results: Dict[str, Any]) -> Dict[str, Any]:
    removed_fields = _REMOVED_RESULT_FIELDS_BY_PHASE.get(str(phase), frozenset())
    if not removed_fields:
        return dict(results)
    return {
        key: value
        for key, value in results.items()
        if key not in removed_fields
    }


def _normalize_error(error: Any) -> Optional[str]:
    if error in (None, "", [], {}):
        return None
    return str(error)


def _normalize_artifacts(artifacts: Optional[Iterable[Any]], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if artifacts is not None:
        normalized.extend(_artifact_sequence_to_list(artifacts))
    else:
        normalized.extend(_artifact_sequence_to_list(_infer_artifacts(payload)))

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for artifact in normalized:
        identity = (
            str(artifact.get("name") or artifact.get("type") or "artifact"),
            str(artifact.get("path") or artifact.get("value") or artifact.get("label") or ""),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(artifact)
    return deduped


def _infer_artifacts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for field_name in ("output_files", "report_output_files"):
        field_value = payload.get(field_name)
        if not isinstance(field_value, dict):
            continue
        for name, path in field_value.items():
            if path in (None, "", [], {}):
                continue
            candidates.append(
                {
                    "name": str(name),
                    "path": str(path),
                    "source": field_name,
                    "type": "file",
                }
            )
    return candidates


def _artifact_sequence_to_list(artifacts: Iterable[Any]) -> List[Dict[str, Any]]:
    if isinstance(artifacts, dict):
        return [
            {
                "name": str(key),
                "path": str(value),
                "type": "file",
            }
            for key, value in artifacts.items()
            if value not in (None, "", [], {})
        ]

    normalized: List[Dict[str, Any]] = []
    for artifact in artifacts:
        if artifact in (None, "", [], {}):
            continue
        if isinstance(artifact, dict):
            entry = dict(artifact)
            entry.setdefault("type", "artifact")
            normalized.append(entry)
            continue
        if isinstance(artifact, str):
            normalized.append({"name": artifact, "path": artifact, "type": "file"})
            continue
        normalized.append({"value": str(artifact), "type": "artifact"})
    return normalized