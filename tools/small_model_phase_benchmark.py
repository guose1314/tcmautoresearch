from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infra.small_model_optimizer import SmallModelOptimizer
from src.infra.token_budget_policy import estimate_text_tokens

_FIXTURE_FILES: Dict[str, str] = {
    "hypothesis": "hypothesis_cases.json",
    "analyze": "analyze_cases.json",
    "publish": "publish_cases.json",
    "reflect": "reflect_cases.json",
}


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phase_i"


def _default_output_dir() -> Path:
    try:
        from src.infrastructure.config_loader import load_settings_section

        llm_config = load_settings_section("models.llm", default={})
        benchmark_settings = ((llm_config.get("small_model_optimizer") or {}).get("benchmark") or {})
        configured = str(benchmark_settings.get("output_dir") or "").strip()
        if configured:
            return Path(configured)
    except Exception:
        pass
    return Path("output") / "phase_benchmarks"


def build_optimizer() -> SmallModelOptimizer:
    try:
        from src.infrastructure.config_loader import load_settings_section

        llm_config = load_settings_section("models.llm", default={})
        return SmallModelOptimizer.from_config(llm_config)
    except Exception:
        return SmallModelOptimizer()


def load_phase_cases(fixtures_dir: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    root = Path(fixtures_dir or _default_fixtures_dir())
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for phase, file_name in _FIXTURE_FILES.items():
        case_path = root / file_name
        raw = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"benchmark fixtures must be a list: {case_path}")
        payload[phase] = [dict(item) for item in raw if isinstance(item, dict)]
    return payload


def _render_baseline_prompt(dossier_sections: Dict[str, Any]) -> str:
    rendered_sections = []
    for name, value in dossier_sections.items():
        text = str(value or "").strip()
        if text:
            rendered_sections.append(f"## {name}\n{text}")
    return "\n\n".join(rendered_sections)


def evaluate_case(case: Dict[str, Any], optimizer: SmallModelOptimizer) -> Dict[str, Any]:
    phase = str(case.get("phase") or "")
    task_type = str(case.get("task_type") or "summarization")
    purpose = str(case.get("purpose") or phase or "default")
    dossier_sections = {
        str(name): str(value or "")
        for name, value in (case.get("dossier_sections") or {}).items()
    }
    cache_hit_likelihood = float(case.get("cache_hit_likelihood") or 0.0)
    retry_count = int(case.get("retry_count") or 0)
    template_preferences = case.get("template_preferences")
    plan = optimizer.prepare_call(
        phase=phase,
        task_type=task_type,
        dossier_sections=dossier_sections,
        template_preferences=dict(template_preferences) if isinstance(template_preferences, dict) else None,
        cache_hit_likelihood=cache_hit_likelihood,
        retry_count=retry_count,
    )

    baseline_prompt = _render_baseline_prompt(dossier_sections)
    baseline_tokens = estimate_text_tokens(baseline_prompt)
    max_input_tokens = int(case.get("max_input_tokens") or 0)
    expected_action = str(case.get("expected_action") or "")
    expected_framework = str(case.get("expected_framework") or "")

    action_match = not expected_action or plan.action == expected_action
    framework_match = not expected_framework or plan.framework_name == expected_framework
    budget_hit = max_input_tokens <= 0 or plan.estimated_tokens <= max_input_tokens
    beats_baseline = baseline_tokens <= 0 or plan.estimated_tokens <= baseline_tokens
    quality_score = round(
        (
            float(action_match)
            + float(framework_match)
            + float(budget_hit)
            + float(beats_baseline)
        )
        / 4.0,
        4,
    )

    return {
        "case_id": str(case.get("case_id") or f"{phase}-{task_type}"),
        "phase": phase,
        "task_type": task_type,
        "purpose": purpose,
        "baseline": {
            "action": "direct_prompt",
            "framework_name": "direct_prompt",
            "estimated_tokens": baseline_tokens,
        },
        "optimized": {
            "action": plan.action,
            "framework_name": plan.framework_name,
            "layer_used": plan.layer_used,
            "estimated_tokens": plan.estimated_tokens,
            "decision_reason": plan.decision_reason,
            "degradation_hints": dict(plan.degradation_hints),
        },
        "expectations": {
            "expected_action": expected_action,
            "expected_framework": expected_framework,
            "max_input_tokens": max_input_tokens,
        },
        "score_components": {
            "action_match": action_match,
            "framework_match": framework_match,
            "budget_hit": budget_hit,
            "beats_baseline": beats_baseline,
        },
        "quality_score": quality_score,
        "token_delta": baseline_tokens - plan.estimated_tokens,
    }


def _summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    action_distribution = Counter(item["optimized"]["action"] for item in results)
    framework_distribution = Counter(item["optimized"]["framework_name"] for item in results)
    if total == 0:
        return {
            "case_count": 0,
            "action_distribution": {},
            "framework_distribution": {},
            "template_hit_rate": 0.0,
            "action_hit_rate": 0.0,
            "budget_hit_rate": 0.0,
            "baseline_win_rate": 0.0,
            "average_quality_score": 0.0,
            "average_token_delta": 0.0,
        }

    return {
        "case_count": total,
        "action_distribution": dict(action_distribution),
        "framework_distribution": dict(framework_distribution),
        "template_hit_rate": round(
            sum(1 for item in results if item["score_components"]["framework_match"]) / total,
            4,
        ),
        "action_hit_rate": round(
            sum(1 for item in results if item["score_components"]["action_match"]) / total,
            4,
        ),
        "budget_hit_rate": round(
            sum(1 for item in results if item["score_components"]["budget_hit"]) / total,
            4,
        ),
        "baseline_win_rate": round(
            sum(1 for item in results if item["score_components"]["beats_baseline"]) / total,
            4,
        ),
        "average_quality_score": round(sum(item["quality_score"] for item in results) / total, 4),
        "average_token_delta": round(sum(item["token_delta"] for item in results) / total, 2),
    }


def _build_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        "# SmallModel Phase Benchmark",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "## Global Summary",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key, value in report["global_summary"].items():
        if isinstance(value, dict):
            continue
        lines.append(f"| {key} | {value} |")

    for phase_name, phase_report in report["phase_reports"].items():
        lines.extend(
            [
                "",
                f"## {phase_name}",
                "",
                "| case_id | action | framework | est_tokens | quality_score |",
                "| --- | --- | --- | ---: | ---: |",
            ]
        )
        for case in phase_report["cases"]:
            optimized = case["optimized"]
            lines.append(
                f"| {case['case_id']} | {optimized['action']} | {optimized['framework_name']} | {optimized['estimated_tokens']} | {case['quality_score']} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_benchmark_report(report: Dict[str, Any], output_dir: Optional[Path] = None) -> Dict[str, str]:
    output_root = Path(output_dir or _default_output_dir())
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_root / f"small_model_phase_benchmark_{stamp}.json"
    markdown_path = output_root / f"small_model_phase_benchmark_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_markdown_report(report), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


def run_phase_benchmark(
    fixtures_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    *,
    write_output: bool = True,
) -> Dict[str, Any]:
    optimizer = build_optimizer()
    cases_by_phase = load_phase_cases(fixtures_dir)
    phase_reports: Dict[str, Dict[str, Any]] = {}
    all_results: List[Dict[str, Any]] = []

    for phase_name, phase_cases in cases_by_phase.items():
        case_results = [evaluate_case(case, optimizer) for case in phase_cases]
        phase_reports[phase_name] = {
            "summary": _summarize_results(case_results),
            "cases": case_results,
        }
        all_results.extend(case_results)

    report = {
        "generated_at": datetime.now().isoformat(),
        "fixtures_dir": str(Path(fixtures_dir or _default_fixtures_dir())),
        "phase_reports": phase_reports,
        "global_summary": _summarize_results(all_results),
    }
    if write_output:
        report["artifacts"] = write_benchmark_report(report, output_dir)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run phase-level benchmark for SmallModelOptimizer.")
    parser.add_argument("--fixtures-dir", type=Path, default=None, help="Custom phase fixture directory.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Custom benchmark output directory.")
    parser.add_argument("--no-write", action="store_true", help="Do not write JSON/Markdown artifacts.")
    args = parser.parse_args()

    report = run_phase_benchmark(
        fixtures_dir=args.fixtures_dir,
        output_dir=args.output_dir,
        write_output=not args.no_write,
    )
    print(json.dumps(report["global_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()