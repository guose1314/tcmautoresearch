"""
Quality consumer inventory.

This tool scans tools modules and root orchestration scripts that consume
quality artifacts and inventories which ones have not yet adopted the unified
governance contract.

Usage:
    python tools/quality_consumer_inventory.py
    python tools/quality_consumer_inventory.py --root . --output output/quality-consumer-inventory.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _normalize_key_path(path: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(path, str):
        return tuple(segment for segment in path.split(".") if segment)
    return tuple(str(segment) for segment in path if str(segment))


def _get_nested(mapping: Dict[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
            continue
        merged[key] = value
    return merged


def _resolve_fallback_config_path(
    root_path: str | Path | None,
    config_path: str | Path | None,
) -> Path:
    if config_path is not None:
        candidate = Path(config_path)
        if not candidate.is_absolute():
            base_root = Path(root_path).resolve() if root_path is not None else Path.cwd()
            candidate = (base_root / candidate).resolve()
        return candidate

    if root_path is not None:
        return (Path(root_path).resolve() / "config.yml").resolve()

    return (Path.cwd() / "config.yml").resolve()


def _fallback_load_settings_section(
    *candidates: str | tuple[str, ...] | list[str],
    root_path: str | Path | None = None,
    config_path: str | Path | None = None,
    environment: str | None = None,
    default: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del environment

    merged_default = dict(default or {})
    try:
        yaml_module = __import__("yaml")
    except Exception:
        return merged_default

    resolved_config = _resolve_fallback_config_path(root_path, config_path)
    if not resolved_config.exists():
        return merged_default

    try:
        payload = yaml_module.safe_load(resolved_config.read_text(encoding="utf-8")) or {}
    except Exception:
        return merged_default

    if not isinstance(payload, dict):
        return merged_default

    merged = dict(merged_default)
    found_mapping = False
    for candidate in candidates:
        keys = _normalize_key_path(candidate)
        if not keys:
            continue
        section = _get_nested(payload, keys)
        if isinstance(section, dict):
            merged = _deep_merge(merged, section)
            found_mapping = True

    if found_mapping or default is not None:
        return merged
    return {}

_CONFIG_LOADER_REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src" / "infrastructure" / "config_loader.py").exists()),
    None,
)
if _CONFIG_LOADER_REPO_ROOT is not None and str(_CONFIG_LOADER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONFIG_LOADER_REPO_ROOT))

try:
    from src.infrastructure.config_loader import load_settings_section
except Exception:
    load_settings_section = _fallback_load_settings_section

ARTIFACT_PATTERNS = {
    "quality_gate": ["output/quality-gate.json", "quality-gate.json"],
    "quality_assessment": ["output/quality-assessment.json", "quality-assessment.json"],
    "quality_history": ["output/quality-history.jsonl", "quality-history.jsonl"],
    "continuous_improvement": ["output/continuous-improvement.json", "continuous-improvement.json"],
    "quality_archive_history": ["output/quality-improvement-archive.jsonl", "quality-improvement-archive.jsonl"],
    "quality_archive_latest": ["output/quality-improvement-archive-latest.json", "quality-improvement-archive-latest.json"],
    "quality_feedback": ["output/quality-feedback.json", "quality-feedback.json"],
    "quality_feedback_markdown": ["output/quality-feedback.md", "quality-feedback.md"],
    "quality_feedback_issue_index": ["output/quality-feedback-issues.json", "quality-feedback-issues.json"],
    "cycle_demo_report": [
        "output/cycle-demo-report.json",
        "cycle-demo-report.json",
        "output/cycle_demo_results_",
        "cycle_demo_results_",
        "cycle_demo_report",
    ],
    "autorresearch_report": [
        "output/autorresearch_report.json",
        "autorresearch_report.json",
        "autorresearch_report",
    ],
}

REQUIRED_CONTRACT_FIELDS = [
    "metadata",
    "report_metadata",
    "analysis_summary",
    "failed_operations",
]

DIRECT_READ_MARKERS = [
    "json.loads(",
    "_safe_load_json(",
    "read_text(",
]

WRITE_MARKERS = [
    "write_text(",
    "json.dump(",
    "Set-Content",
    "Out-File",
    "ConvertTo-Json",
]

COMMAND_ONLY_MARKERS = [
    "tools/quality_gate.py",
    "tools/quality_assessment.py",
    "tools/continuous_improvement_loop.py",
    "tools/quality_improvement_archive.py",
    "tools/quality_feedback.py",
]

DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "include_root_scripts": True,
    "minimum_candidate_score": 40,
    "export_contract_version": "d62.v1",
}

ROOT_OBSERVATION_RULES = [
    {
        "category": "non_governance_domain_script",
        "label": "非治理域脚本",
        "patterns": [
            "storage_test_results.json",
            "storage test",
            "storage performance",
            "performance report",
            "系统性能报告",
            "性能测试报告",
        ],
        "reason": "Root script belongs to a separate reporting or validation domain and does not consume quality governance artifacts.",
    }
]

OUT_OF_SCOPE_PATHS = {
    "tools/quality_gate.py",
    "tools/quality_assessment.py",
    "tools/continuous_improvement_loop.py",
    "tools/quality_improvement_archive.py",
    "tools/quality_feedback.py",
    "tools/quality_consumer_inventory.py",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_inventory_section(config_path: Path | None) -> Dict[str, Any]:
    return load_settings_section(
        "governance.quality_consumer_inventory",
        config_path=config_path,
        default={},
    )


def _load_governance_config(config_path: Path | None) -> Dict[str, Any]:
    config = dict(DEFAULT_GOVERNANCE_CONFIG)
    config.update(_load_inventory_section(config_path))
    return config


def _iter_inventory_paths(root: Path, governance_config: Dict[str, Any]) -> List[Path]:
    discovered: List[Path] = []
    tools_dir = root / "tools"
    if tools_dir.exists():
        discovered.extend(
            path
            for path in sorted(tools_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".py", ".ps1"}
        )

    if governance_config.get("include_root_scripts", True):
        discovered.extend(
            path
            for path in sorted(root.iterdir())
            if path.is_file()
            and path.suffix.lower() in {".py", ".ps1"}
            and not path.name.startswith("test_")
        )

    unique_paths: Dict[str, Path] = {}
    for path in discovered:
        unique_paths.setdefault(path.resolve().as_posix(), path)
    return list(unique_paths.values())


def _build_scan_scope(governance_config: Dict[str, Any]) -> List[str]:
    scope = ["tools"]
    if governance_config.get("include_root_scripts", True):
        scope.append("root_scripts")
    return scope


def _build_root_observation_category_counts(root_script_observations: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in root_script_observations:
        category = item.get("observation_category", "uncategorized_root_script")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _is_root_level_script(path: Path, repo_root: Path) -> bool:
    return path.is_file() and path.parent == repo_root and path.suffix.lower() in {".py", ".ps1"}


def _serialize_value(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _start_phase(metadata: Dict[str, Any], phase_name: str) -> None:
    timestamp = _now_iso()
    metadata.setdefault("phase_history", []).append({"phase": phase_name, "event": "started", "timestamp": timestamp})
    metadata.setdefault("phase_timings", {})[phase_name] = {"started_at": timestamp}


def _complete_phase(metadata: Dict[str, Any], phase_name: str) -> None:
    timestamp = _now_iso()
    metadata.setdefault("phase_history", []).append({"phase": phase_name, "event": "completed", "timestamp": timestamp})
    timings = metadata.setdefault("phase_timings", {}).setdefault(phase_name, {})
    timings["completed_at"] = timestamp
    metadata.setdefault("completed_phases", []).append(phase_name)
    metadata["last_completed_phase"] = phase_name


def _record_failed_operation(failed_operations: List[Dict[str, Any]], operation: str, error: str, details: Dict[str, Any] | None = None) -> None:
    failed_operations.append(
        {
            "operation": operation,
            "error": error,
            "details": _serialize_value(details or {}),
            "timestamp": _now_iso(),
            "duration_seconds": 0.0,
        }
    )


def _fail_phase(metadata: Dict[str, Any], failed_operations: List[Dict[str, Any]], phase_name: str, error: Exception, details: Dict[str, Any] | None = None) -> None:
    metadata.setdefault("phase_history", []).append({"phase": phase_name, "event": "failed", "timestamp": _now_iso()})
    metadata["failed_phase"] = phase_name
    metadata["final_status"] = "failed"
    _record_failed_operation(failed_operations, phase_name, str(error), details)


def _detect_artifact_inputs(text: str) -> List[str]:
    found: List[str] = []
    for artifact_name, patterns in ARTIFACT_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            found.append(artifact_name)
    return found


def _find_evidence_lines(path: Path, text: str, patterns: List[str]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        if any(pattern in line for pattern in patterns):
            evidence.append({"line": line_number, "snippet": line.strip()})
    return evidence[:8]


def _determine_consumption_mode(path: Path, text: str, artifact_inputs: List[str]) -> str:
    if not artifact_inputs:
        return "none"
    if path.suffix.lower() == ".ps1":
        return "command_orchestration"
    if any(marker in text for marker in DIRECT_READ_MARKERS):
        return "direct_artifact_read"
    if any(marker in text for marker in COMMAND_ONLY_MARKERS):
        return "command_orchestration"
    return "artifact_reference"


def _detect_output_targets(text: str) -> List[str]:
    targets: List[str] = []
    for artifact_name, patterns in ARTIFACT_PATTERNS.items():
        if any(pattern in text for pattern in patterns) and any(marker in text for marker in WRITE_MARKERS):
            targets.append(artifact_name)
    return targets


def _classify_root_script_observation(text: str) -> Dict[str, str]:
    lowered = text.lower()
    for rule in ROOT_OBSERVATION_RULES:
        if any(pattern.lower() in lowered for pattern in rule["patterns"]):
            return {
                "observation_category": rule["category"],
                "observation_category_label": rule["label"],
                "reason": rule["reason"],
            }
    return {
        "observation_category": "uncategorized_root_script",
        "observation_category_label": "待归类脚本",
        "reason": "Root script was scanned but did not reference any configured quality or aggregation artifact patterns.",
    }


def _detect_contract_fields(text: str) -> Dict[str, bool]:
    fields = {field: field in text for field in REQUIRED_CONTRACT_FIELDS}
    fields["export_contract_version"] = "export_contract_version" in text
    return fields


def _score_candidate(consumption_mode: str, artifact_inputs: List[str], output_targets: List[str], governed: bool) -> int:
    score = 0
    if governed:
        return 0
    if consumption_mode == "direct_artifact_read":
        score += 60
    elif consumption_mode == "command_orchestration":
        score += 30
    elif consumption_mode == "artifact_reference":
        score += 20
    score += min(len(artifact_inputs) * 10, 30)
    score += min(len(output_targets) * 5, 10)
    return score


def analyze_quality_consumer(path: Path, repo_root: Path) -> Dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    artifact_inputs = _detect_artifact_inputs(text)
    if not artifact_inputs:
        return None

    relative_path = path.relative_to(repo_root).as_posix()
    if relative_path == "tools/quality_consumer_inventory.py":
        return None

    contract_fields = _detect_contract_fields(text)
    governed = all(contract_fields[field] for field in REQUIRED_CONTRACT_FIELDS) and contract_fields["export_contract_version"]
    consumption_mode = _determine_consumption_mode(path, text, artifact_inputs)
    output_targets = _detect_output_targets(text)
    evidence_patterns = []
    for artifact_name in artifact_inputs:
        evidence_patterns.extend(ARTIFACT_PATTERNS[artifact_name])
    evidence = _find_evidence_lines(path, text, evidence_patterns)
    missing_fields = [field for field in REQUIRED_CONTRACT_FIELDS if not contract_fields[field]]
    if not contract_fields["export_contract_version"]:
        missing_fields.append("export_contract_version")

    return {
        "path": relative_path,
        "consumption_mode": consumption_mode,
        "artifact_inputs": artifact_inputs,
        "output_targets": output_targets,
        "target_scope": "out_of_scope" if relative_path in OUT_OF_SCOPE_PATHS else "eligible",
        "contract_status": "governed" if governed else "missing_contract",
        "missing_contract_fields": missing_fields if not governed else [],
        "candidate_score": _score_candidate(consumption_mode, artifact_inputs, output_targets, governed),
        "evidence": evidence,
    }


def observe_unmatched_root_script(path: Path, repo_root: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    relative_path = path.relative_to(repo_root).as_posix()
    output_targets = _detect_output_targets(text)
    evidence = _find_evidence_lines(path, text, WRITE_MARKERS)
    classification = _classify_root_script_observation(text)
    return {
        "path": relative_path,
        "observation_status": "no_artifact_match",
        "observation_category": classification["observation_category"],
        "observation_category_label": classification["observation_category_label"],
        "reason": classification["reason"],
        "output_targets": output_targets,
        "evidence": evidence,
    }


def _recommend_candidate(consumers: List[Dict[str, Any]], minimum_candidate_score: int) -> Dict[str, Any]:
    candidates = [
        item
        for item in consumers
        if item["target_scope"] == "eligible"
        and item["contract_status"] == "missing_contract"
        and item["candidate_score"] >= minimum_candidate_score
    ]
    if not candidates:
        return {
            "recommended_path": None,
            "reason": "No additional quality artifact consumers above the configured D54 threshold.",
            "candidate_count": 0,
        }

    ranked = sorted(candidates, key=lambda item: (-item["candidate_score"], item["path"]))
    top = ranked[0]
    return {
        "recommended_path": top["path"],
        "reason": "Highest-priority adjacent consumer outside the governed quality chain.",
        "candidate_count": len(ranked),
        "top_candidates": [
            {
                "path": item["path"],
                "candidate_score": item["candidate_score"],
                "consumption_mode": item["consumption_mode"],
                "artifact_inputs": item["artifact_inputs"],
            }
            for item in ranked[:3]
        ],
    }


def _build_analysis_summary(
    consumers: List[Dict[str, Any]],
    recommendation: Dict[str, Any],
    governance_config: Dict[str, Any],
    root_script_observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    missing_contract = [item for item in consumers if item["contract_status"] == "missing_contract"]
    eligible_missing_contract = [item for item in missing_contract if item["target_scope"] == "eligible"]
    return {
        "scanned_consumer_count": len(consumers),
        "missing_contract_count": len(missing_contract),
        "eligible_missing_contract_count": len(eligible_missing_contract),
        "governed_consumer_count": len(consumers) - len(missing_contract),
        "recommended_next_target": recommendation["recommended_path"],
        "scan_scope": _build_scan_scope(governance_config),
        "root_script_observation_count": len(root_script_observations),
        "root_script_observation_category_counts": _build_root_observation_category_counts(root_script_observations),
    }


def _build_report_metadata(governance_config: Dict[str, Any], metadata: Dict[str, Any], failed_operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _now_iso(),
        "result_schema": "quality_consumer_inventory_report",
        "failed_operation_count": len(failed_operations),
        "final_status": metadata.get("final_status", "completed"),
        "last_completed_phase": metadata.get("last_completed_phase"),
    }


def build_quality_consumer_inventory(root: Path, config_path: Path | None = None) -> Dict[str, Any]:
    governance_config = _load_governance_config(config_path)
    metadata: Dict[str, Any] = {
        "phase_history": [],
        "phase_timings": {},
        "completed_phases": [],
        "failed_phase": None,
        "final_status": "completed",
        "last_completed_phase": None,
    }
    failed_operations: List[Dict[str, Any]] = []

    try:
        _start_phase(metadata, "scan_quality_consumers")
        consumers: List[Dict[str, Any]] = []
        root_script_observations: List[Dict[str, Any]] = []
        for path in _iter_inventory_paths(root, governance_config):
            consumer = analyze_quality_consumer(path, root)
            if consumer is not None:
                consumers.append(consumer)
                continue
            if _is_root_level_script(path, root):
                root_script_observations.append(observe_unmatched_root_script(path, root))
        _complete_phase(metadata, "scan_quality_consumers")
    except Exception as error:
        _fail_phase(metadata, failed_operations, "scan_quality_consumers", error, {"root": str(root)})
        consumers = []
        root_script_observations = []

    _start_phase(metadata, "build_quality_consumer_inventory")
    recommendation = _recommend_candidate(consumers, int(governance_config.get("minimum_candidate_score", 40)))
    report = {
        "timestamp": _now_iso(),
        "root": root.resolve().as_posix(),
        "inventory": consumers,
        "root_script_observations": root_script_observations,
        "recommendation": recommendation,
        "metadata": metadata,
        "analysis_summary": _build_analysis_summary(consumers, recommendation, governance_config, root_script_observations),
        "failed_operations": failed_operations,
    }
    _complete_phase(metadata, "build_quality_consumer_inventory")
    report["report_metadata"] = _build_report_metadata(governance_config, metadata, failed_operations)
    return _serialize_value(report)


def render_inventory_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Quality Consumer Inventory",
        "",
        "## Summary",
        "",
        "- scanned_consumer_count: {count}".format(count=report["analysis_summary"]["scanned_consumer_count"]),
        "- missing_contract_count: {count}".format(count=report["analysis_summary"]["missing_contract_count"]),
        "- eligible_missing_contract_count: {count}".format(count=report["analysis_summary"]["eligible_missing_contract_count"]),
        "- governed_consumer_count: {count}".format(count=report["analysis_summary"]["governed_consumer_count"]),
        "- recommended_next_target: {target}".format(target=report["analysis_summary"]["recommended_next_target"] or "none"),
        "- root_script_observation_count: {count}".format(count=report["analysis_summary"].get("root_script_observation_count", 0)),
        "",
        "## Consumers",
        "",
        "| Path | Scope | Mode | Inputs | Contract | Missing Fields | Score |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["inventory"]:
        lines.append(
            "| {path} | {scope} | {mode} | {inputs} | {status} | {missing} | {score} |".format(
                path=item["path"],
                scope=item["target_scope"],
                mode=item["consumption_mode"],
                inputs=", ".join(item["artifact_inputs"]),
                status=item["contract_status"],
                missing=", ".join(item["missing_contract_fields"]) or "-",
                score=item["candidate_score"],
            )
        )
    lines.extend([
        "",
        "## Root Script Observations",
        "",
        "- observation_categories: {categories}".format(
            categories=(
                ", ".join(
                    "{category}={count}".format(category=category, count=count)
                    for category, count in sorted(report["analysis_summary"].get("root_script_observation_category_counts", {}).items())
                )
                or "none"
            )
        ),
        "",
        "| Path | Category | Observation | Output Targets | Reason |",
        "| --- | --- | --- | --- | --- |",
    ])
    for item in report.get("root_script_observations", []):
        lines.append(
            "| {path} | {category} | {status} | {outputs} | {reason} |".format(
                path=item["path"],
                category=item.get("observation_category_label", item.get("observation_category", "-")),
                status=item["observation_status"],
                outputs=", ".join(item.get("output_targets", [])) or "-",
                reason=item["reason"],
            )
        )
    if not report.get("root_script_observations"):
        lines.append("| none | - | - | - | No unmatched root scripts were observed. |")
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- recommended_path: {path}".format(path=report["recommendation"]["recommended_path"] or "none"),
        "- reason: {reason}".format(reason=report["recommendation"]["reason"]),
    ])
    return "\n".join(lines) + "\n"


def export_quality_consumer_inventory(report: Dict[str, Any], output_path: Path, markdown_path: Path) -> Dict[str, Any]:
    metadata = report.setdefault("metadata", {})
    _start_phase(metadata, "export_quality_consumer_inventory")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    _complete_phase(metadata, "export_quality_consumer_inventory")
    report["report_metadata"]["generated_at"] = _now_iso()
    report["report_metadata"]["last_completed_phase"] = metadata.get("last_completed_phase")
    report["report_metadata"]["final_status"] = metadata.get("final_status", "completed")
    payload = _serialize_value(report)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_inventory_markdown(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory tools and root script consumers of quality artifacts")
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument("--config", default="config.yml", help="Path to config YAML")
    parser.add_argument("--output", default="output/quality-consumer-inventory.json", help="Path to inventory JSON")
    parser.add_argument("--markdown", default="output/quality-consumer-inventory.md", help="Path to inventory markdown")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve()
    report = build_quality_consumer_inventory(root, config_path)
    exported = export_quality_consumer_inventory(report, Path(args.output).resolve(), Path(args.markdown).resolve())

    print("[quality-consumer-inventory] scanned={count}".format(count=exported["analysis_summary"]["scanned_consumer_count"]))
    print("[quality-consumer-inventory] missing-contract={count}".format(count=exported["analysis_summary"]["missing_contract_count"]))
    print("[quality-consumer-inventory] recommended={path}".format(path=exported["analysis_summary"]["recommended_next_target"] or "none"))
    print("[quality-consumer-inventory] json={path}".format(path=Path(args.output).resolve()))
    print("[quality-consumer-inventory] markdown={path}".format(path=Path(args.markdown).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())