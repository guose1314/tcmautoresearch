from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infra.lexicon_service import reset_lexicon  # noqa: E402
from src.orchestration.research_runtime_service import (
    ResearchRuntimeService,  # noqa: E402
)
from src.research.phase_result import (  # noqa: E402
    get_phase_artifact_map,
    get_phase_value,
)
from src.research.real_observe_smoke import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE_PATH,
    build_phase_context,
    build_pipeline_config,
    build_smoke_summary,
    load_smoke_profile,
    resolve_include_paths,
    validate_smoke_summary,
    write_smoke_artifacts,
)

MISSING_LEXICON_PATH = ROOT / "data" / "__missing_tcm_lexicon__.jsonl"
MISSING_SYNONYMS_PATH = ROOT / "data" / "__missing_tcm_synonyms__.jsonl"


@contextmanager
def temporary_env(overrides: Dict[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    reset_lexicon()
    try:
        yield
    finally:
        reset_lexicon()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_lexicon()


def excerpt(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def resolve_artifact_path(path_text: str) -> Path | None:
    raw_path = str(path_text or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (ROOT / candidate).resolve()
    return candidate if candidate.exists() else None


def read_text_artifact(path_text: str) -> str:
    artifact_path = resolve_artifact_path(path_text)
    if artifact_path is None:
        return ""
    try:
        return artifact_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return artifact_path.read_text(encoding="utf-8-sig")


def extract_markdown_section(markdown_text: str, markers: Sequence[str]) -> str:
    lines = str(markdown_text or "").splitlines()
    normalized_markers = [str(marker).strip().lower() for marker in markers if str(marker).strip()]
    collecting = False
    collected: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            if collecting:
                break
            if any(marker in heading for marker in normalized_markers):
                collecting = True
            continue
        if collecting:
            collected.append(line)

    return "\n".join(collected).strip()


def build_paper_quality(
    paper_markdown: str,
    publications: Sequence[Dict[str, Any]],
    primary_association: Dict[str, Any],
) -> Dict[str, Any]:
    abstract = extract_markdown_section(paper_markdown, ("摘要", "abstract"))
    results_text = extract_markdown_section(paper_markdown, ("结果", "results", "result"))
    main_publication = next(
        (
            item
            for item in publications
            if isinstance(item, dict) and item.get("status") in {"draft_generated", "draft_empty"}
        ),
        {},
    )
    herb = str(primary_association.get("herb") or "")
    syndrome = str(primary_association.get("syndrome") or "")

    def signals(text: str) -> Dict[str, bool]:
        return {
            "mentions_significance": any(token in text for token in ("显著", "统计学", "p值", "P值", "p<", "P<", "卡方", "χ")),
            "mentions_effect_size": any(token in text for token in ("效应量", "effect size")),
            "mentions_association": any(token in text for token in ("关联", "规则", "组合", "相关")),
            "mentions_primary_herb": bool(herb) and herb in text,
            "mentions_primary_syndrome": bool(syndrome) and syndrome in text,
        }

    abstract_signals = signals(abstract)
    results_signals = signals(results_text)
    return {
        "review_score": float(main_publication.get("review_score") or 0.0),
        "section_count": int(main_publication.get("section_count") or 0),
        "reference_count": int(main_publication.get("reference_count") or 0),
        "abstract_length": len(abstract.strip()),
        "results_length": len(results_text.strip()),
        "abstract_signals": abstract_signals,
        "results_signals": results_signals,
        "abstract_signal_count": sum(1 for value in abstract_signals.values() if value),
        "results_signal_count": sum(1 for value in results_signals.values() if value),
        "abstract_excerpt": excerpt(abstract),
        "results_excerpt": excerpt(results_text),
    }


def run_profile(mode_name: str, profile_path: Path, output_dir: Path, env_overrides: Dict[str, str | None]) -> Dict[str, Any]:
    with temporary_env(env_overrides):
        profile = load_smoke_profile(profile_path)
        include_paths = resolve_include_paths(profile, ROOT)
        missing_paths = [str(path) for path in include_paths if not path.exists()]
        if missing_paths:
            raise FileNotFoundError("Missing real observe source files: " + ", ".join(missing_paths))
        phase_context = build_phase_context(profile, include_paths, ROOT)
        started_at = datetime.now().isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        publish_temp_dir: tempfile.TemporaryDirectory[str] | None = None

        try:
            publish_temp_dir = tempfile.TemporaryDirectory(dir=str(output_dir))
            publish_context = dict(phase_context)
            publish_context.setdefault("paper_output_formats", ["markdown"])
            publish_context.setdefault("report_output_formats", ["markdown"])
            publish_context["paper_output_dir"] = publish_temp_dir.name
            publish_context["output_dir"] = publish_temp_dir.name

            runtime_service = ResearchRuntimeService({
                "phases": ["observe", "hypothesis", "experiment", "analyze", "publish", "reflect"],
                "pipeline_config": build_pipeline_config(profile, ROOT),
                "researchers": list(profile.researchers),
            })

            runtime_result = runtime_service.run(
                profile.objective,
                cycle_name=profile.cycle_name,
                description=profile.description,
                scope=profile.scope,
                phase_contexts={
                    "observe": dict(phase_context),
                    "hypothesis": dict(phase_context),
                    "experiment": dict(phase_context),
                    "analyze": dict(phase_context),
                    "publish": publish_context,
                    "reflect": dict(phase_context),
                },
                report_output_formats=["markdown"],
                report_output_dir=publish_temp_dir.name,
            )

            phase_results = runtime_result.session_result.get("phase_results") or {}
            observe = phase_results.get("observe") or {}
            hypothesis = phase_results.get("hypothesis") or {}
            experiment = phase_results.get("experiment") or {}
            analyze = phase_results.get("analyze") or {}
            publish = phase_results.get("publish") or {}
            reflect = phase_results.get("reflect") or {}

            summary = build_smoke_summary(
                profile,
                phase_context,
                include_paths,
                observe,
                hypothesis,
                experiment,
                analyze,
                publish,
                reflect,
                started_at,
            )
            violations = validate_smoke_summary(summary, profile.thresholds)
            summary["validation_status"] = "passed" if not violations else "failed"
            summary["violations"] = violations
            summary["artifacts"] = write_smoke_artifacts(summary, output_dir)

            observe_ingestion = get_phase_value(observe, "ingestion_pipeline", {}) or {}
            observe_aggregate = observe_ingestion.get("aggregate") or {}
            artifact_map = get_phase_artifact_map(publish)
            paper_markdown = read_text_artifact(artifact_map.get("markdown") or "")
            publications = get_phase_value(publish, "publications", []) or []
            paper_quality = build_paper_quality(
                paper_markdown,
                publications if isinstance(publications, list) else [],
                summary.get("primary_association") or {},
            )
            return {
                "mode": mode_name,
                "summary": summary,
                "entity_type_counts": dict(sorted((observe_aggregate.get("entity_type_counts") or {}).items())),
                "paper_quality": paper_quality,
            }
        finally:
            if publish_temp_dir is not None:
                publish_temp_dir.cleanup()


def build_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_summary = before.get("summary") or {}
    after_summary = after.get("summary") or {}
    before_counts = before.get("entity_type_counts") or {}
    after_counts = after.get("entity_type_counts") or {}
    keys = sorted(set(before_counts) | set(after_counts))
    paper_before = before.get("paper_quality") or {}
    paper_after = after.get("paper_quality") or {}
    before_primary = before_summary.get("primary_association") or {}
    after_primary = after_summary.get("primary_association") or {}
    return {
        "metric_delta": {
            "total_entities": int(after_summary.get("total_entities") or 0) - int(before_summary.get("total_entities") or 0),
            "semantic_relationship_count": int(after_summary.get("semantic_relationship_count") or 0) - int(before_summary.get("semantic_relationship_count") or 0),
            "record_count": int(after_summary.get("record_count") or 0) - int(before_summary.get("record_count") or 0),
            "kg_path_count": int(after_summary.get("kg_path_count") or 0) - int(before_summary.get("kg_path_count") or 0),
            "association_rule_count": int(after_summary.get("association_rule_count") or 0) - int(before_summary.get("association_rule_count") or 0),
            "frequency_signal_count": int(after_summary.get("frequency_signal_count") or 0) - int(before_summary.get("frequency_signal_count") or 0),
        },
        "entity_type_count_delta": {
            key: int(after_counts.get(key) or 0) - int(before_counts.get(key) or 0)
            for key in keys
        },
        "primary_association": {
            "before": before_primary,
            "after": after_primary,
            "changed": before_primary != after_primary,
        },
        "paper_quality_delta": {
            "review_score": float(paper_after.get("review_score") or 0.0) - float(paper_before.get("review_score") or 0.0),
            "abstract_length": int(paper_after.get("abstract_length") or 0) - int(paper_before.get("abstract_length") or 0),
            "results_length": int(paper_after.get("results_length") or 0) - int(paper_before.get("results_length") or 0),
            "abstract_signal_count": int(paper_after.get("abstract_signal_count") or 0) - int(paper_before.get("abstract_signal_count") or 0),
            "results_signal_count": int(paper_after.get("results_signal_count") or 0) - int(paper_before.get("results_signal_count") or 0),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare fixed real-cycle smoke profile with and without the rebuilt TCM lexicon.")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="Path to the smoke profile JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR / "compare_lexicon_modes"), help="Directory for per-mode artifacts and combined comparison JSON.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = Path(args.profile)

    before = run_profile(
        "without_lexicon",
        profile_path,
        output_dir / "without_lexicon",
        {
            "TCM_LEXICON_PATH": str(MISSING_LEXICON_PATH),
            "TCM_SYNONYMS_PATH": str(MISSING_SYNONYMS_PATH),
        },
    )
    after = run_profile(
        "rebuilt_lexicon",
        profile_path,
        output_dir / "rebuilt_lexicon",
        {
            "TCM_LEXICON_PATH": None,
            "TCM_SYNONYMS_PATH": None,
        },
    )

    comparison = {
        "generated_at": datetime.now().isoformat(),
        "profile": str(profile_path),
        "without_lexicon": before,
        "rebuilt_lexicon": after,
        "diff": build_diff(before, after),
    }
    comparison_path = output_dir / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())