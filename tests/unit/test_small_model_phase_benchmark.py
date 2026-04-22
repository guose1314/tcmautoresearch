from __future__ import annotations

from pathlib import Path

from tools.small_model_phase_benchmark import (
    build_optimizer,
    evaluate_case,
    load_phase_cases,
    run_phase_benchmark,
)


def test_load_phase_cases_returns_all_target_phases() -> None:
    cases = load_phase_cases()
    assert set(cases.keys()) == {"hypothesis", "analyze", "publish", "reflect"}
    assert all(cases[phase] for phase in cases)


def test_run_phase_benchmark_returns_summary_without_writing(tmp_path: Path) -> None:
    report = run_phase_benchmark(output_dir=tmp_path, write_output=False)
    assert "global_summary" in report
    assert report["global_summary"]["case_count"] >= 4
    assert "phase_reports" in report
    assert report["phase_reports"]["hypothesis"]["summary"]["case_count"] >= 1


def test_run_phase_benchmark_writes_json_and_markdown(tmp_path: Path) -> None:
    report = run_phase_benchmark(output_dir=tmp_path, write_output=True)
    artifacts = report["artifacts"]
    assert Path(artifacts["json"]).exists()
    assert Path(artifacts["markdown"]).exists()


# ---------------------------------------------------------------------------
# Phase I / I-2 — replay determinism + failed_cases + prompt registry snapshot
# ---------------------------------------------------------------------------


def test_report_carries_prompt_registry_snapshot_with_fingerprint(tmp_path: Path) -> None:
    report = run_phase_benchmark(output_dir=tmp_path, write_output=False)
    snapshot = report["prompt_registry_snapshot"]
    assert snapshot["total_prompts"] > 0
    assert isinstance(snapshot["fingerprint"], str) and len(snapshot["fingerprint"]) == 64
    assert isinstance(snapshot["entries"], list) and snapshot["entries"]


def test_phase_reports_include_failed_cases_buckets(tmp_path: Path) -> None:
    report = run_phase_benchmark(output_dir=tmp_path, write_output=False)
    for phase_name, phase_report in report["phase_reports"].items():
        assert "failed_cases" in phase_report, f"{phase_name} 缺 failed_cases"
        assert isinstance(phase_report["failed_cases"], list)
        for entry in phase_report["failed_cases"]:
            assert entry["case_id"]
            assert entry["missing"], "failed case 必须列出未达成的指标"


def test_replay_returns_identical_dossier_snapshots(tmp_path: Path) -> None:
    optimizer = build_optimizer()
    cases = load_phase_cases()
    sample_cases = []
    for phase_cases in cases.values():
        if phase_cases:
            sample_cases.append(phase_cases[0])

    first_pass = [evaluate_case(case, optimizer) for case in sample_cases]
    second_pass = [evaluate_case(case, optimizer) for case in sample_cases]

    for a, b in zip(first_pass, second_pass):
        assert a["dossier_snapshot"]["fingerprint"] == b["dossier_snapshot"]["fingerprint"]
        assert a["optimized"]["framework_name"] == b["optimized"]["framework_name"]
        assert a["optimized"]["action"] == b["optimized"]["action"]
        assert a["optimized"]["estimated_tokens"] == b["optimized"]["estimated_tokens"]


def test_each_case_result_carries_dossier_snapshot(tmp_path: Path) -> None:
    report = run_phase_benchmark(output_dir=tmp_path, write_output=False)
    for phase_report in report["phase_reports"].values():
        for case in phase_report["cases"]:
            snapshot = case["dossier_snapshot"]
            assert snapshot["section_count"] >= 0
            assert isinstance(snapshot["fingerprint"], str)
            assert len(snapshot["fingerprint"]) == 64
            for entry in snapshot["sections"]:
                assert entry["name"]
                assert isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64
