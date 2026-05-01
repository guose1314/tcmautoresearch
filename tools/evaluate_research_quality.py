from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from src.quality.citation_grounding_evaluator import evaluate_citation_grounding

REQUIRED_CATEGORIES = {
    "formula_composition",
    "herb_alias",
    "syndrome_sense",
    "version_variant",
    "citation_review",
}

DEFAULT_THRESHOLDS = {
    "precision": 0.70,
    "recall": 0.70,
    "citation_support_rate": 0.70,
    "json_schema_pass_rate": 1.0,
}


def evaluate_fixture_dir(
    fixture_dir: str | Path,
    *,
    thresholds: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    fixtures = _load_fixtures(Path(fixture_dir))
    effective_thresholds = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        effective_thresholds.update(
            {key: float(value) for key, value in thresholds.items()}
        )

    schema_pass_count = 0
    entity_expected_total = 0
    entity_actual_total = 0
    entity_match_total = 0
    relationship_expected_total = 0
    relationship_actual_total = 0
    relationship_match_total = 0
    citation_expected_total = 0
    citation_match_total = 0
    citation_grounding_record_total = 0
    citation_grounding_supported_total = 0
    citation_grounding_unsupported_total = 0
    philology_expected_total = 0
    philology_match_total = 0
    categories: Set[str] = set()
    case_results: List[Dict[str, Any]] = []

    for fixture in fixtures:
        schema_pass = _fixture_schema_passes(fixture)
        schema_pass_count += int(schema_pass)
        category = str(fixture.get("category") or "").strip()
        if category:
            categories.add(category)
        expected = (
            fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
        )
        actual = (
            fixture.get("actual") if isinstance(fixture.get("actual"), dict) else {}
        )

        expected_entities = _entity_keys(expected.get("entities") or [])
        actual_entities = _entity_keys(actual.get("entities") or [])
        expected_relationships = _relationship_keys(expected.get("relationships") or [])
        actual_relationships = _relationship_keys(actual.get("relationships") or [])

        entity_matches = len(expected_entities & actual_entities)
        relationship_matches = len(expected_relationships & actual_relationships)
        entity_expected_total += len(expected_entities)
        entity_actual_total += len(actual_entities)
        entity_match_total += entity_matches
        relationship_expected_total += len(expected_relationships)
        relationship_actual_total += len(actual_relationships)
        relationship_match_total += relationship_matches

        citation_total, citation_matches = _score_citation_support(
            expected.get("citation_support") or [],
            actual.get("citation_support") or [],
        )
        citation_expected_total += citation_total
        citation_match_total += citation_matches

        grounding_summary = _evaluate_actual_citation_grounding(actual)
        citation_grounding_record_total += int(
            grounding_summary.get("record_count") or 0
        )
        citation_grounding_supported_total += int(
            grounding_summary.get("supported_count") or 0
        )
        citation_grounding_unsupported_total += int(
            grounding_summary.get("unsupported_count") or 0
        )

        philology_expected_total += 1
        if _philology_verdict_key(
            expected.get("philology_verdict")
        ) == _philology_verdict_key(actual.get("philology_verdict")):
            philology_match_total += 1

        case_results.append(
            {
                "case_id": fixture.get("case_id"),
                "category": category,
                "schema_pass": schema_pass,
                "entity_precision": _safe_rate(entity_matches, len(actual_entities)),
                "entity_recall": _safe_rate(entity_matches, len(expected_entities)),
                "relationship_precision": _safe_rate(
                    relationship_matches,
                    len(actual_relationships),
                ),
                "relationship_recall": _safe_rate(
                    relationship_matches,
                    len(expected_relationships),
                ),
                "citation_grounding_record_count": int(
                    grounding_summary.get("record_count") or 0
                ),
                "citation_grounding_support_rate": grounding_summary.get(
                    "citation_grounding_support_rate",
                    1.0,
                ),
            }
        )

    precision_matches = entity_match_total + relationship_match_total
    precision_actual = entity_actual_total + relationship_actual_total
    recall_expected = entity_expected_total + relationship_expected_total
    precision = _safe_rate(precision_matches, precision_actual)
    recall = _safe_rate(precision_matches, recall_expected)
    citation_support_rate = _safe_rate(citation_match_total, citation_expected_total)
    citation_grounding_support_rate = _safe_rate(
        citation_grounding_supported_total,
        citation_grounding_record_total,
    )
    json_schema_pass_rate = _safe_rate(schema_pass_count, len(fixtures))
    philology_verdict_rate = _safe_rate(philology_match_total, philology_expected_total)

    warnings = _build_warnings(
        {
            "precision": precision,
            "recall": recall,
            "citation_support_rate": citation_support_rate,
            "json_schema_pass_rate": json_schema_pass_rate,
        },
        effective_thresholds,
    )
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        warnings.append(
            "missing required gold-set categories: " + ", ".join(missing_categories)
        )

    return {
        "status": "warning" if warnings else "passed",
        "case_count": len(fixtures),
        "categories": sorted(categories),
        "precision": precision,
        "recall": recall,
        "citation_support_rate": citation_support_rate,
        "citation_grounding_support_rate": citation_grounding_support_rate,
        "citation_grounding_record_count": citation_grounding_record_total,
        "unsupported_citation_grounding_count": citation_grounding_unsupported_total,
        "json_schema_pass_rate": json_schema_pass_rate,
        "philology_verdict_rate": philology_verdict_rate,
        "thresholds": effective_thresholds,
        "warnings": warnings,
        "cases": case_results,
    }


def _load_fixtures(fixture_dir: Path) -> List[Dict[str, Any]]:
    if not fixture_dir.exists():
        raise FileNotFoundError(f"fixture directory not found: {fixture_dir}")
    fixtures: List[Dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload.setdefault("fixture_file", path.name)
            fixtures.append(payload)
    return fixtures


def _fixture_schema_passes(fixture: Mapping[str, Any]) -> bool:
    expected = fixture.get("expected")
    return bool(
        fixture.get("case_id")
        and fixture.get("category") in REQUIRED_CATEGORIES
        and isinstance(fixture.get("input"), dict)
        and isinstance(expected, dict)
        and isinstance(expected.get("entities"), list)
        and isinstance(expected.get("relationships"), list)
        and isinstance(expected.get("philology_verdict"), dict)
        and isinstance(expected.get("citation_support"), list)
    )


def _entity_keys(items: Iterable[Any]) -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entity_type = _normalize_text(item.get("type") or item.get("entity_type"))
        name = _normalize_text(item.get("name") or item.get("canonical"))
        if entity_type and name:
            keys.add((entity_type, name))
    return keys


def _relationship_keys(items: Iterable[Any]) -> Set[Tuple[str, str, str]]:
    keys: Set[Tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        relation_type = _normalize_text(item.get("type") or item.get("relation_type"))
        source = _normalize_text(item.get("source"))
        target = _normalize_text(item.get("target"))
        if relation_type and source and target:
            keys.add((relation_type, source, target))
    return keys


def _score_citation_support(
    expected_items: Iterable[Any],
    actual_items: Iterable[Any],
) -> Tuple[int, int]:
    actual_by_claim = {
        str(item.get("claim_id") or "").strip(): item
        for item in actual_items
        if isinstance(item, Mapping) and str(item.get("claim_id") or "").strip()
    }
    total = 0
    matches = 0
    for expected in expected_items:
        if not isinstance(expected, Mapping):
            continue
        claim_id = str(expected.get("claim_id") or "").strip()
        if not claim_id:
            continue
        total += 1
        actual = actual_by_claim.get(claim_id, {})
        expected_supported = bool(expected.get("supported", True))
        actual_supported = bool(actual.get("supported", False))
        expected_citations = set(_normalize_list(expected.get("citation_keys") or []))
        actual_citations = set(_normalize_list(actual.get("citation_keys") or []))
        if expected_supported == actual_supported and (
            not expected_supported or expected_citations <= actual_citations
        ):
            matches += 1
    return total, matches


def _evaluate_actual_citation_grounding(actual: Mapping[str, Any]) -> Dict[str, Any]:
    publish_result = actual.get("publish_result")
    report_markdown = str(
        actual.get("report_markdown")
        or actual.get("markdown_report")
        or actual.get("paper_markdown")
        or ""
    )
    grounding_records = actual.get("citation_grounding_records")
    if not isinstance(publish_result, Mapping):
        publish_result = {}
    if not isinstance(grounding_records, list):
        grounding_records = None
    if not report_markdown and not publish_result and not grounding_records:
        return {
            "record_count": 0,
            "supported_count": 0,
            "unsupported_count": 0,
            "citation_grounding_support_rate": 1.0,
        }
    return evaluate_citation_grounding(
        publish_result=publish_result,
        report_markdown=report_markdown,
        grounding_records=grounding_records,
    )


def _philology_verdict_key(value: Any) -> Tuple[str, str]:
    if not isinstance(value, Mapping):
        return "", ""
    return (
        _normalize_text(value.get("status") or value.get("verdict")),
        _normalize_text(value.get("variant") or value.get("reading") or ""),
    )


def _build_warnings(
    metrics: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> List[str]:
    warnings: List[str] = []
    for key, threshold in thresholds.items():
        if key in metrics and metrics[key] < float(threshold):
            warnings.append(f"{key} {metrics[key]:.3f} below threshold {threshold:.3f}")
    return warnings


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_list(values: Sequence[Any]) -> List[str]:
    return [_normalize_text(value) for value in values if _normalize_text(value)]


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(float(numerator) / float(denominator), 6)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the research gold set.")
    parser.add_argument(
        "--fixture-dir",
        default=str(
            Path(__file__).resolve().parents[1]
            / "tests"
            / "fixtures"
            / "research_gold_set"
        ),
        help="Directory containing research gold-set JSON fixtures.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when threshold warnings are emitted.",
    )
    args = parser.parse_args(argv)

    summary = evaluate_fixture_dir(args.fixture_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict and summary["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
