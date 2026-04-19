from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

from src.research.phase_result import get_phase_results, get_phase_value

REQUIRED_PUBLISH_ALIAS_FIELDS: List[str] = []


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_PROFILE_PATH = repo_root() / "tools" / "diagnostics" / "real_observe_smoke_profile.json"
DEFAULT_OUTPUT_DIR = repo_root() / "output" / "real_observe_smoke"


@dataclass(slots=True)
class SmokeThresholds:
    processed_document_count: int
    min_total_entities: int = 0
    min_semantic_graph_nodes: int = 0
    min_semantic_graph_edges: int = 0
    min_semantic_relationship_count: int = 0
    min_record_count: int = 0
    max_p_value: float | None = None
    min_effect_size: float = 0.0
    min_kg_path_count: int = 0
    min_association_rule_count: int = 0
    min_frequency_signal_count: int = 0
    min_observe_reasoning_confidence: float = 0.0
    min_reasoning_confidence: float = 0.0
    require_statistical_significance: bool = True
    expect_llm_generation_disabled: bool = True
    expected_protocol_source: str | None = "template"
    require_publish_aliases: List[str] = field(
        default_factory=lambda: list(REQUIRED_PUBLISH_ALIAS_FIELDS)
    )


@dataclass(slots=True)
class SmokeProfile:
    profile_name: str
    description: str
    cycle_name: str
    objective: str
    scope: str
    researchers: List[str]
    pipeline_config: Dict[str, Any]
    phase_context: Dict[str, Any]
    include_paths: List[str]
    thresholds: SmokeThresholds


def load_smoke_profile(
    profile_path: Path | None = None,
) -> SmokeProfile:
    resolved_path = Path(profile_path or DEFAULT_PROFILE_PATH)
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    thresholds = SmokeThresholds(**payload.pop("thresholds"))
    return SmokeProfile(thresholds=thresholds, **payload)


def resolve_include_paths(
    profile: SmokeProfile,
    root: Path | None = None,
) -> List[Path]:
    resolved_root = root or repo_root()
    resolved_paths: List[Path] = []
    for relative_path in profile.include_paths:
        candidate = Path(relative_path)
        if not candidate.is_absolute():
            candidate = (resolved_root / candidate).resolve()
        resolved_paths.append(candidate)
    return resolved_paths


def build_pipeline_config(
    profile: SmokeProfile,
    root: Path | None = None,
) -> Dict[str, Any]:
    resolved_root = root or repo_root()
    pipeline_config = copy.deepcopy(profile.pipeline_config)
    local_corpus = pipeline_config.get("local_corpus")
    if isinstance(local_corpus, dict) and local_corpus.get("data_dir"):
        local_corpus["data_dir"] = str(_resolve_repo_path(local_corpus["data_dir"], resolved_root))
    return pipeline_config


def build_phase_context(
    profile: SmokeProfile,
    include_paths: Sequence[Path],
    root: Path | None = None,
) -> Dict[str, Any]:
    resolved_root = root or repo_root()
    phase_context = copy.deepcopy(profile.phase_context)
    phase_context["include_paths"] = [str(path) for path in include_paths]

    if phase_context.get("local_data_dir"):
        phase_context["local_data_dir"] = str(
            _resolve_repo_path(phase_context["local_data_dir"], resolved_root)
        )
    else:
        phase_context["local_data_dir"] = str(resolved_root / "data")

    phase_context.setdefault("local_max_files", len(include_paths))
    phase_context.setdefault("max_texts", len(include_paths))
    return phase_context


def execute_real_observe_smoke(
    profile: SmokeProfile | None = None,
    *,
    output_dir: Path | None = None,
    root: Path | None = None,
) -> Dict[str, Any]:
    from src.orchestration.research_runtime_service import ResearchRuntimeService

    resolved_root = root or repo_root()
    smoke_profile = profile or load_smoke_profile()
    include_paths = resolve_include_paths(smoke_profile, resolved_root)
    missing_paths = [str(path) for path in include_paths if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(
            "Missing real observe smoke source files: " + ", ".join(missing_paths)
        )

    output_root = Path(output_dir or DEFAULT_OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)
    phase_context = build_phase_context(smoke_profile, include_paths, resolved_root)

    publish_temp_dir = tempfile.TemporaryDirectory(dir=str(output_root))
    publish_context = dict(phase_context)
    publish_context.setdefault("paper_output_formats", ["markdown"])
    publish_context.setdefault("report_output_formats", ["markdown"])
    publish_context["paper_output_dir"] = publish_temp_dir.name
    publish_context["output_dir"] = publish_temp_dir.name

    phase_contexts = {
        "observe": dict(phase_context),
        "hypothesis": dict(phase_context),
        "experiment": dict(phase_context),
        "experiment_execution": dict(phase_context),
        "analyze": dict(phase_context),
        "publish": publish_context,
        "reflect": dict(phase_context),
    }

    pipeline_config = build_pipeline_config(smoke_profile, resolved_root)
    runtime_config = {
        "pipeline_config": pipeline_config,
        "researchers": list(smoke_profile.researchers),
    }

    started_at = datetime.now().isoformat()
    try:
        service = ResearchRuntimeService(runtime_config)
        result = service.run(
            smoke_profile.objective,
            cycle_name=smoke_profile.cycle_name,
            description=smoke_profile.description,
            scope=smoke_profile.scope,
            phase_contexts=phase_contexts,
        )
        phase_results = result.phase_results or {}

        summary = build_smoke_summary(
            smoke_profile,
            phase_context,
            include_paths,
            phase_results.get("observe", {}),
            phase_results.get("hypothesis", {}),
            phase_results.get("experiment", {}),
            phase_results.get("experiment_execution", {}),
            phase_results.get("analyze", {}),
            phase_results.get("publish", {}),
            phase_results.get("reflect", {}),
            started_at,
        )
        violations = validate_smoke_summary(summary, smoke_profile.thresholds)
        summary["validation_status"] = "passed" if not violations else "failed"
        summary["violations"] = violations
        summary["artifacts"] = write_smoke_artifacts(summary, output_root)
        return summary
    finally:
        publish_temp_dir.cleanup()


def build_smoke_summary(
    profile: SmokeProfile,
    phase_context: Dict[str, Any],
    include_paths: Sequence[Path],
    observe: Dict[str, Any],
    hypothesis: Dict[str, Any],
    experiment: Dict[str, Any],
    experiment_execution: Dict[str, Any],
    analyze: Dict[str, Any],
    publish: Dict[str, Any],
    reflect: Dict[str, Any],
    started_at: str,
) -> Dict[str, Any]:
    observe_ingestion = get_phase_value(observe, "ingestion_pipeline", {}) or {}
    observe_aggregate = observe_ingestion.get("aggregate") or {}
    analyze_metadata = analyze.get("metadata") or {}
    analyze_results = get_phase_results(analyze)
    statistical_analysis = analyze_results.get("statistical_analysis") or {}
    reasoning_results = analyze_results.get("reasoning_results") if isinstance(analyze_results.get("reasoning_results"), dict) else {}
    reasoning_payload = reasoning_results.get("reasoning_results") or {}
    publish_analysis = get_phase_value(publish, "analysis_results", {}) or {}
    publish_artifact = get_phase_value(publish, "research_artifact", {}) or {}
    experiment_study_protocol = get_phase_value(experiment, "study_protocol", {}) or {}
    publish_statistical_analysis = (
        publish_analysis.get("statistical_analysis")
        if isinstance(publish_analysis.get("statistical_analysis"), dict)
        else {}
    )
    artifact_statistical_analysis = (
        publish_artifact.get("statistical_analysis")
        if isinstance(publish_artifact.get("statistical_analysis"), dict)
        else {}
    )
    publish_data_mining_result = (
        publish_analysis.get("data_mining_result")
        if isinstance(publish_analysis.get("data_mining_result"), dict)
        else {}
    )
    if not publish_data_mining_result and isinstance(publish_artifact.get("data_mining_result"), dict):
        publish_data_mining_result = publish_artifact.get("data_mining_result") or {}

    frequency_chi_square = publish_data_mining_result.get("frequency_chi_square") or {}
    if not isinstance(frequency_chi_square, dict):
        frequency_chi_square = {}

    association_rules = publish_data_mining_result.get("association_rules") or {}
    if not isinstance(association_rules, dict):
        association_rules = {}

    primary_association = publish_statistical_analysis.get("primary_association")
    if not isinstance(primary_association, dict) or not primary_association:
        primary_association = artifact_statistical_analysis.get("primary_association") or {}
    if not isinstance(primary_association, dict):
        primary_association = {}

    alias_fields = list(profile.thresholds.require_publish_aliases)
    analysis_alias_fields = {
        field_name: field_name in publish_analysis for field_name in alias_fields
    }
    artifact_alias_fields = {
        field_name: field_name in publish_artifact for field_name in alias_fields
    }

    summary = {
        "profile_name": profile.profile_name,
        "description": profile.description,
        "generated_at": datetime.now().isoformat(),
        "started_at": started_at,
        "include_file_count": len(include_paths),
        "include_paths": [_as_repo_relative(path) for path in include_paths],
        "phase_context": {
            "max_texts": phase_context.get("max_texts"),
            "max_chars_per_text": phase_context.get("max_chars_per_text"),
            "run_literature_retrieval": phase_context.get("run_literature_retrieval"),
            "use_llm_generation": phase_context.get("use_llm_generation"),
            "use_llm_protocol_generation": phase_context.get("use_llm_protocol_generation"),
        },
        "thresholds": asdict(profile.thresholds),
        "processed_document_count": int(observe_ingestion.get("processed_document_count") or 0),
        "total_entities": int(observe_aggregate.get("total_entities") or 0),
        "semantic_graph_nodes": int(observe_aggregate.get("semantic_graph_nodes") or 0),
        "semantic_graph_edges": int(observe_aggregate.get("semantic_graph_edges") or 0),
        "semantic_relationship_count": len(observe_aggregate.get("semantic_relationships") or []),
        "observe_reasoning_confidence": _safe_float(
            (observe_aggregate.get("reasoning_summary") or {}).get("inference_confidence")
        ),
        "analysis_modules": list(analyze_metadata.get("analysis_modules") or []),
        "record_count": int(analyze_metadata.get("record_count") or 0),
        "p_value": _safe_float(statistical_analysis.get("p_value")),
        "effect_size": _safe_float(statistical_analysis.get("effect_size")),
        "statistical_significance": bool(
            statistical_analysis.get("statistical_significance")
        ),
        "reasoning_confidence": _safe_float(reasoning_payload.get("inference_confidence")),
        "kg_path_count": len(reasoning_results.get("kg_paths") or []),
        "association_rule_count": len((association_rules.get("rules") or [])),
        "frequency_signal_count": len((frequency_chi_square.get("chi_square_top") or [])),
        "primary_association": primary_association,
        "used_llm_generation": bool(
            (hypothesis.get("metadata") or {}).get("used_llm_generation")
        ),
        "experiment_protocol_source": str(
            (experiment_study_protocol or {}).get("protocol_source")
            or (experiment.get("metadata") or {}).get("protocol_source")
            or ""
        ),
        "experiment_execution_status": str(
            get_phase_value(experiment_execution, "execution_status", "")
            or (experiment_execution.get("metadata") or {}).get("execution_status")
            or ""
        ),
        "experiment_execution_imported_record_count": int(
            (experiment_execution.get("metadata") or {}).get("imported_record_count") or 0
        ),
        "reflect_count": int((reflect.get("metadata") or {}).get("reflection_count") or 0),
    }

    if alias_fields:
        summary["publish_alias_fields"] = {
            "analysis_results": analysis_alias_fields,
            "research_artifact": artifact_alias_fields,
        }
        summary["publish_aliases_present"] = {
            "analysis_results": all(analysis_alias_fields.values()),
            "research_artifact": all(artifact_alias_fields.values()),
        }

    return summary


def validate_smoke_summary(
    summary: Dict[str, Any],
    thresholds: SmokeThresholds,
) -> List[str]:
    violations: List[str] = []

    _require_equal(
        violations,
        "processed_document_count",
        summary.get("processed_document_count"),
        thresholds.processed_document_count,
    )
    _require_minimum(
        violations,
        "total_entities",
        summary.get("total_entities"),
        thresholds.min_total_entities,
    )
    _require_minimum(
        violations,
        "semantic_graph_nodes",
        summary.get("semantic_graph_nodes"),
        thresholds.min_semantic_graph_nodes,
    )
    _require_minimum(
        violations,
        "semantic_graph_edges",
        summary.get("semantic_graph_edges"),
        thresholds.min_semantic_graph_edges,
    )
    _require_minimum(
        violations,
        "semantic_relationship_count",
        summary.get("semantic_relationship_count"),
        thresholds.min_semantic_relationship_count,
    )
    _require_minimum(
        violations,
        "record_count",
        summary.get("record_count"),
        thresholds.min_record_count,
    )
    _require_minimum(
        violations,
        "kg_path_count",
        summary.get("kg_path_count"),
        thresholds.min_kg_path_count,
    )
    _require_minimum(
        violations,
        "association_rule_count",
        summary.get("association_rule_count"),
        thresholds.min_association_rule_count,
    )
    _require_minimum(
        violations,
        "frequency_signal_count",
        summary.get("frequency_signal_count"),
        thresholds.min_frequency_signal_count,
    )
    _require_minimum(
        violations,
        "observe_reasoning_confidence",
        summary.get("observe_reasoning_confidence"),
        thresholds.min_observe_reasoning_confidence,
    )
    _require_minimum(
        violations,
        "reasoning_confidence",
        summary.get("reasoning_confidence"),
        thresholds.min_reasoning_confidence,
    )
    _require_minimum(
        violations,
        "effect_size",
        summary.get("effect_size"),
        thresholds.min_effect_size,
    )

    if thresholds.max_p_value is not None:
        p_value = _safe_float(summary.get("p_value"))
        if p_value is None:
            violations.append("p_value missing from smoke summary")
        elif p_value > thresholds.max_p_value:
            violations.append(
                f"p_value {p_value:.6f} exceeded max {thresholds.max_p_value:.6f}"
            )

    if thresholds.require_statistical_significance and not bool(
        summary.get("statistical_significance")
    ):
        violations.append("statistical_significance was false")

    if thresholds.expect_llm_generation_disabled and bool(summary.get("used_llm_generation")):
        violations.append("used_llm_generation regressed to true")

    if thresholds.expected_protocol_source is not None:
        protocol_source = str(summary.get("experiment_protocol_source") or "")
        if protocol_source != thresholds.expected_protocol_source:
            violations.append(
                f"experiment_protocol_source expected '{thresholds.expected_protocol_source}' but got '{protocol_source}'"
            )

    if thresholds.require_publish_aliases:
        publish_alias_fields = summary.get("publish_alias_fields") or {}
        for container_name in ("analysis_results", "research_artifact"):
            field_map = publish_alias_fields.get(container_name) or {}
            missing = [
                field_name
                for field_name in thresholds.require_publish_aliases
                if not bool(field_map.get(field_name))
            ]
            if missing:
                violations.append(
                    f"{container_name} missing publish aliases: {', '.join(missing)}"
                )

    return violations


def write_smoke_artifacts(
    summary: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path = output_dir / "latest.json"
    dossier_path = output_dir / "dossier.md"
    timeline_path = output_dir / "timeline.jsonl"

    latest_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    dossier_path.write_text(_build_dossier(summary), encoding="utf-8")

    timeline_entry = {
        "generated_at": summary.get("generated_at"),
        "profile_name": summary.get("profile_name"),
        "validation_status": summary.get("validation_status"),
        "processed_document_count": summary.get("processed_document_count"),
        "record_count": summary.get("record_count"),
        "p_value": summary.get("p_value"),
        "effect_size": summary.get("effect_size"),
        "statistical_significance": summary.get("statistical_significance"),
        "violations": summary.get("violations") or [],
    }
    with timeline_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(timeline_entry, ensure_ascii=False) + "\n")

    return {
        "latest_json": _as_repo_relative(latest_path),
        "dossier_markdown": _as_repo_relative(dossier_path),
        "timeline_jsonl": _as_repo_relative(timeline_path),
    }


def _build_dossier(summary: Dict[str, Any]) -> str:
    primary_association = summary.get("primary_association") or {}
    violations = summary.get("violations") or []
    lines = [
        "# Real Observe Smoke Dossier",
        "",
        f"- Profile: {summary.get('profile_name', '')}",
        f"- Generated At: {summary.get('generated_at', '')}",
        f"- Validation Status: {summary.get('validation_status', '')}",
        f"- Include File Count: {summary.get('include_file_count', 0)}",
        f"- Processed Documents: {summary.get('processed_document_count', 0)}",
        f"- Record Count: {summary.get('record_count', 0)}",
        f"- P Value: {summary.get('p_value')}",
        f"- Effect Size: {summary.get('effect_size')}",
        f"- Statistical Significance: {summary.get('statistical_significance')}",
        f"- KG Path Count: {summary.get('kg_path_count', 0)}",
        f"- Association Rule Count: {summary.get('association_rule_count', 0)}",
        f"- Frequency Signal Count: {summary.get('frequency_signal_count', 0)}",
        f"- LLM Generation Disabled: {not bool(summary.get('used_llm_generation'))}",
        f"- Experiment Protocol Source: {summary.get('experiment_protocol_source', '')}",
        "",
        "## Primary Association",
        "",
        f"- Herb: {primary_association.get('herb', '')}",
        f"- Syndrome: {primary_association.get('syndrome', '')}",
        f"- Chi2: {primary_association.get('chi2')}",
        f"- P Value: {primary_association.get('p_value')}",
        f"- Effect Size: {primary_association.get('effect_size')}",
        "",
        "## Include Paths",
        "",
    ]
    lines.extend(f"- {path}" for path in summary.get("include_paths") or [])
    lines.extend([
        "",
        "## Violations",
        "",
    ])
    if violations:
        lines.extend(f"- {item}" for item in violations)
    else:
        lines.append("- none")

    publish_alias_fields = summary.get("publish_alias_fields")
    if isinstance(publish_alias_fields, dict):
        lines.extend([
            "",
            "## Publish Alias Coverage",
            "",
            "```json",
            json.dumps(publish_alias_fields, ensure_ascii=False, indent=2),
            "```",
        ])
    return "\n".join(lines) + "\n"


def _require_equal(
    violations: List[str],
    metric_name: str,
    actual_value: Any,
    expected_value: int,
) -> None:
    try:
        normalized = int(actual_value)
    except (TypeError, ValueError):
        violations.append(f"{metric_name} missing or not an integer")
        return
    if normalized != expected_value:
        violations.append(
            f"{metric_name} expected {expected_value} but got {normalized}"
        )


def _require_minimum(
    violations: List[str],
    metric_name: str,
    actual_value: Any,
    minimum_value: float,
) -> None:
    if minimum_value <= 0:
        return
    normalized = _safe_float(actual_value)
    if normalized is None:
        violations.append(f"{metric_name} missing from smoke summary")
        return
    if normalized < minimum_value:
        violations.append(
            f"{metric_name} expected >= {minimum_value} but got {normalized}"
        )


def _resolve_repo_path(raw_path: str, root: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_repo_relative(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(repo_root())
        return relative.as_posix()
    except ValueError:
        return str(path.resolve())


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_PROFILE_PATH",
    "REQUIRED_PUBLISH_ALIAS_FIELDS",
    "SmokeProfile",
    "SmokeThresholds",
    "build_phase_context",
    "build_pipeline_config",
    "build_smoke_summary",
    "execute_real_observe_smoke",
    "load_smoke_profile",
    "repo_root",
    "resolve_include_paths",
    "validate_smoke_summary",
    "write_smoke_artifacts",
]