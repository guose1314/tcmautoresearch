from __future__ import annotations

from pathlib import Path

from tools.small_model_phase_benchmark import load_phase_cases, run_phase_benchmark


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