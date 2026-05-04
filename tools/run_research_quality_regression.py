"""Run gold-set research quality regression checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.evaluation.citation_grounding_evaluator import (  # noqa: E402
    evaluate_citation_grounding,
)

DEFAULT_GOLDEN_DIR = ROOT / "tests" / "golden"
DEFAULT_BASELINE = DEFAULT_GOLDEN_DIR / "quality_baseline.json"


def evaluate_gold_set(
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
    *,
    baseline_path: str | Path = DEFAULT_BASELINE,
) -> dict[str, Any]:
    cases = _load_cases(Path(golden_dir))
    baseline = _load_baseline(Path(baseline_path))
    entity_expected_total = 0
    entity_actual_total = 0
    entity_match_total = 0
    relation_expected_total = 0
    relation_actual_total = 0
    relation_match_total = 0
    grounding_asset_total = 0
    grounding_supported_total = 0
    unsupported_claim_total = 0
    citation_mismatch_total = 0
    candidate_total = 0
    candidate_accepted_total = 0
    categories: set[str] = set()
    case_results: list[dict[str, Any]] = []

    for case in cases:
        category = str(case.get("category") or "").strip()
        if category:
            categories.add(category)
        expected = _mapping(case.get("expected"))
        actual = _mapping(case.get("actual"))
        expected_entities = _entity_keys(expected.get("entities") or [])
        actual_entities = _entity_keys(actual.get("entities") or [])
        expected_relations = _relationship_keys(expected.get("relationships") or [])
        actual_relations = _relationship_keys(actual.get("relationships") or [])
        entity_matches = len(expected_entities & actual_entities)
        relation_matches = len(expected_relations & actual_relations)
        entity_expected_total += len(expected_entities)
        entity_actual_total += len(actual_entities)
        entity_match_total += entity_matches
        relation_expected_total += len(expected_relations)
        relation_actual_total += len(actual_relations)
        relation_match_total += relation_matches

        grounding = evaluate_citation_grounding(
            llm_output=actual,
            text_segments=(
                actual.get("text_segments")
                if isinstance(actual.get("text_segments"), list)
                else None
            ),
            reviewed_evidence=(
                actual.get("reviewed_evidence")
                if isinstance(actual.get("reviewed_evidence"), list)
                else None
            ),
            evidence_protocol=(
                actual.get("evidence_protocol")
                if isinstance(actual.get("evidence_protocol"), Mapping)
                else None
            ),
            graph_rag_context=(
                actual.get("graph_rag_context")
                if isinstance(actual.get("graph_rag_context"), Mapping)
                else None
            ),
            citation_records=(
                actual.get("citation_records")
                if isinstance(actual.get("citation_records"), list)
                else None
            ),
        )
        grounding_asset_total += int(grounding.get("asset_count") or 0)
        grounding_supported_total += int(grounding.get("supported_asset_count") or 0)
        unsupported_claim_total += len(grounding.get("unsupported_claims") or [])
        citation_mismatch_total += len(grounding.get("citation_mismatch") or [])

        candidate_total_case, candidate_accepted_case = _candidate_acceptance_counts(
            actual
        )
        candidate_total += candidate_total_case
        candidate_accepted_total += candidate_accepted_case
        case_results.append(
            {
                "case_id": case.get("case_id"),
                "category": category,
                "precision": _safe_rate(
                    entity_matches + relation_matches,
                    len(actual_entities) + len(actual_relations),
                ),
                "recall": _safe_rate(
                    entity_matches + relation_matches,
                    len(expected_entities) + len(expected_relations),
                ),
                "grounding_score": grounding.get("grounding_score", 1.0),
                "unsupported_claim_count": len(
                    grounding.get("unsupported_claims") or []
                ),
                "citation_mismatch_count": len(
                    grounding.get("citation_mismatch") or []
                ),
                "candidate_acceptance_rate": _safe_rate(
                    candidate_accepted_case, candidate_total_case
                ),
            }
        )

    precision = _safe_rate(
        entity_match_total + relation_match_total,
        entity_actual_total + relation_actual_total,
    )
    recall = _safe_rate(
        entity_match_total + relation_match_total,
        entity_expected_total + relation_expected_total,
    )
    grounding_score = _safe_rate(grounding_supported_total, grounding_asset_total)
    candidate_acceptance_rate = _safe_rate(candidate_accepted_total, candidate_total)
    unsupported_claim_rate = _safe_rate(unsupported_claim_total, grounding_asset_total)
    metrics = {
        "precision": precision,
        "recall": recall,
        "grounding_score": grounding_score,
        "candidate_acceptance_rate": candidate_acceptance_rate,
        "unsupported_claim_rate": unsupported_claim_rate,
    }
    regressions = _compare_to_baseline(metrics, baseline)
    return {
        "contract_version": "research-quality-regression-v1",
        "status": "failed" if regressions else "passed",
        "case_count": len(cases),
        "categories": sorted(categories),
        "metrics": metrics,
        "precision": precision,
        "recall": recall,
        "grounding_score": grounding_score,
        "candidate_acceptance_rate": candidate_acceptance_rate,
        "unsupported_claim_rate": unsupported_claim_rate,
        "unsupported_claim_count": unsupported_claim_total,
        "citation_mismatch_count": citation_mismatch_total,
        "baseline": baseline.get("metrics", {}),
        "allowed_regression": baseline.get("allowed_regression", {}),
        "regressions": regressions,
        "cases": case_results,
    }


def _load_cases(golden_dir: Path) -> list[dict[str, Any]]:
    if not golden_dir.exists():
        raise FileNotFoundError(f"golden directory not found: {golden_dir}")
    cases: list[dict[str, Any]] = []
    for path in sorted(golden_dir.glob("*.json")):
        if path.name == "quality_baseline.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("cases"), list):
            for item in payload["cases"]:
                if isinstance(item, Mapping):
                    case = dict(item)
                    case.setdefault("fixture_file", path.name)
                    cases.append(case)
        elif isinstance(payload, Mapping):
            case = dict(payload)
            case.setdefault("fixture_file", path.name)
            cases.append(case)
    return cases


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"metrics": {}, "allowed_regression": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else {}


def _compare_to_baseline(
    metrics: Mapping[str, float],
    baseline: Mapping[str, Any],
) -> list[dict[str, Any]]:
    baseline_metrics = _mapping(baseline.get("metrics"))
    allowed = _mapping(baseline.get("allowed_regression"))
    regressions: list[dict[str, Any]] = []
    for key, value in metrics.items():
        if key not in baseline_metrics:
            continue
        baseline_value = float(baseline_metrics.get(key) or 0.0)
        tolerance = float(allowed.get(key) or 0.0)
        if key == "unsupported_claim_rate":
            if value > baseline_value + tolerance:
                regressions.append(
                    {
                        "metric": key,
                        "actual": value,
                        "baseline": baseline_value,
                        "allowed_increase": tolerance,
                    }
                )
        elif value < baseline_value - tolerance:
            regressions.append(
                {
                    "metric": key,
                    "actual": value,
                    "baseline": baseline_value,
                    "allowed_drop": tolerance,
                }
            )
    return regressions


def _entity_keys(items: Iterable[Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entity_type = _normalize(item.get("type") or item.get("entity_type"))
        name = _normalize(item.get("name") or item.get("canonical"))
        if entity_type and name:
            keys.add((entity_type, name))
    return keys


def _relationship_keys(items: Iterable[Any]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        relation_type = _normalize(item.get("type") or item.get("relation_type"))
        source = _normalize(item.get("source"))
        target = _normalize(item.get("target"))
        if relation_type and source and target:
            keys.add((relation_type, source, target))
    return keys


def _candidate_acceptance_counts(actual: Mapping[str, Any]) -> tuple[int, int]:
    candidates = []
    for key in ("expert_feedback", "candidate_relations", "candidate_edges"):
        values = actual.get(key)
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, Mapping))
    total = 0
    accepted = 0
    for item in candidates:
        status = str(item.get("review_status") or item.get("status") or "").lower()
        if status in {"accepted", "rejected", "needs_source", "pending"}:
            total += 1
            accepted += int(status == "accepted")
    return total, accepted


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(float(numerator) / float(denominator), 6)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", default=str(DEFAULT_GOLDEN_DIR))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args(argv)

    summary = evaluate_gold_set(args.golden_dir, baseline_path=args.baseline)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.print_only:
        return 0
    return 1 if summary["regressions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
