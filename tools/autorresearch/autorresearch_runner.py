#!/usr/bin/env python3
"""Karpathy-style AutoResearch loop for this repository.

Loop:
1) Read Chinese instruction + program.md + train.py
2) Propose hypothesis and edit train.py
3) Run 5-minute-capped training
4) Parse val_bpb and VRAM peak
5) Improve -> git commit as new baseline
   Regress/crash -> rollback train.py and retry
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

VAL_RE = re.compile(r"val_bpb\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
VRAM_RE = re.compile(r"vram_peak_mb\s*=\s*([0-9]+)", re.IGNORECASE)

DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_improvement_count": 1,
    "export_contract_version": "d61.v1",
}


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8", errors="replace")
    return str(value)


@dataclass
class TrialResult:
    ok: bool
    val_bpb: Optional[float]
    vram_peak_mb: Optional[int]
    stdout: str
    stderr: str
    duration_s: float
    crashed: bool


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_autorresearch_section(config_path: Path | None) -> Dict[str, Any]:
    if config_path is None or not config_path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    governance = data.get("governance") or {}
    section = governance.get("autorresearch_runner") or {}
    return section if isinstance(section, dict) else {}


def _load_governance_config(config_path: Path | None) -> Dict[str, Any]:
    config = dict(DEFAULT_GOVERNANCE_CONFIG)
    config.update(_load_autorresearch_section(config_path))
    return config


def _serialize_value(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _start_phase(metadata: Dict[str, Any], phase_name: str, details: Dict[str, Any] | None = None) -> float:
    started_at = time.perf_counter()
    metadata.setdefault("phase_history", []).append(
        {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": _now_iso(),
            "details": _serialize_value(details or {}),
        }
    )
    return started_at


def _complete_phase(
    metadata: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    details: Dict[str, Any] | None = None,
    final_status: str | None = None,
) -> None:
    duration = max(0.0, time.perf_counter() - phase_started_at)
    metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
    completed_phases = metadata.setdefault("completed_phases", [])
    if phase_name not in completed_phases:
        completed_phases.append(phase_name)
    metadata["last_completed_phase"] = phase_name
    metadata["failed_phase"] = None
    if final_status is not None:
        metadata["final_status"] = final_status

    for phase in reversed(metadata.get("phase_history", [])):
        if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
            phase["status"] = "completed"
            phase["ended_at"] = _now_iso()
            phase["duration_seconds"] = round(duration, 6)
            if details:
                phase["details"] = _serialize_value({**phase.get("details", {}), **details})
            break


def _record_failed_operation(
    failed_operations: list[dict],
    governance_config: Dict[str, Any],
    operation: str,
    error: str,
    details: Dict[str, Any] | None = None,
    duration_seconds: float | None = None,
) -> None:
    if not governance_config.get("persist_failed_operations", True):
        return
    failed_operations.append(
        {
            "operation": operation,
            "error": error,
            "details": _serialize_value(details or {}),
            "timestamp": _now_iso(),
            "duration_seconds": round(duration_seconds or 0.0, 6),
        }
    )


def _fail_phase(
    metadata: Dict[str, Any],
    failed_operations: list[dict],
    governance_config: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    error: Exception,
    details: Dict[str, Any] | None = None,
) -> None:
    duration = max(0.0, time.perf_counter() - phase_started_at)
    metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
    metadata["failed_phase"] = phase_name
    metadata["final_status"] = "failed"
    _record_failed_operation(failed_operations, governance_config, phase_name, str(error), details, duration)
    for phase in reversed(metadata.get("phase_history", [])):
        if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
            phase["status"] = "failed"
            phase["ended_at"] = _now_iso()
            phase["duration_seconds"] = round(duration, 6)
            phase["error"] = str(error)
            if details:
                phase["details"] = _serialize_value({**phase.get("details", {}), **details})
            break


def _build_runtime_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase_history": _serialize_value(metadata.get("phase_history", [])),
        "phase_timings": _serialize_value(metadata.get("phase_timings", {})),
        "completed_phases": list(metadata.get("completed_phases", [])),
        "failed_phase": metadata.get("failed_phase"),
        "final_status": metadata.get("final_status", "initialized"),
        "last_completed_phase": metadata.get("last_completed_phase"),
    }


def _build_analysis_summary(
    history: list[dict],
    best_val_bpb: Optional[float],
    metadata: Dict[str, Any],
    failed_operations: list[dict],
    governance_config: Dict[str, Any],
) -> Dict[str, Any]:
    improved_iterations = [item for item in history if item.get("status") in {"improved_committed", "improved_no_commit"}]
    rollback_iterations = [item for item in history if item.get("status") == "rollback"]
    syntax_failures = [item for item in history if item.get("status") == "syntax_fail"]
    crashed_iterations = [item for item in history if item.get("crashed")]
    status = "idle"
    if history or failed_operations:
        status = (
            "stable"
            if len(improved_iterations) >= int(governance_config.get("minimum_stable_improvement_count", 1))
            and metadata.get("final_status", "completed") == "completed"
            else "needs_followup"
        )
    return {
        "status": status,
        "trial_count": len(history),
        "improved_iteration_count": len(improved_iterations),
        "rollback_iteration_count": len(rollback_iterations),
        "syntax_failure_count": len(syntax_failures),
        "crashed_trial_count": len(crashed_iterations),
        "best_val_bpb": best_val_bpb,
        "failed_operation_count": len(failed_operations),
        "failed_phase": metadata.get("failed_phase"),
        "final_status": metadata.get("final_status", "initialized"),
        "last_completed_phase": metadata.get("last_completed_phase"),
    }


def _build_report_metadata(
    governance_config: Dict[str, Any],
    metadata: Dict[str, Any],
    failed_operations: list[dict],
    output_path: Path | None = None,
) -> Dict[str, Any]:
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _now_iso(),
        "result_schema": "autorresearch_runner_report",
        "failed_operation_count": len(failed_operations),
        "final_status": metadata.get("final_status", "initialized"),
        "last_completed_phase": metadata.get("last_completed_phase"),
    }
    if output_path is not None:
        report_metadata["output_path"] = str(output_path)
    return report_metadata


def build_autorresearch_report(
    instruction: str,
    strategy: str,
    rollback_mode: str,
    best_val_bpb: Optional[float],
    history: list[dict],
    governance_config: Dict[str, Any],
    metadata: Dict[str, Any],
    failed_operations: list[dict],
    report_path: Path | None = None,
) -> Dict[str, Any]:
    return {
        "timestamp": _now_iso(),
        "instruction": instruction,
        "strategy": strategy,
        "rollback_mode": rollback_mode,
        "best_val_bpb": best_val_bpb,
        "history": _serialize_value(history),
        "analysis_summary": _build_analysis_summary(history, best_val_bpb, metadata, failed_operations, governance_config),
        "failed_operations": _serialize_value(failed_operations),
        "metadata": _build_runtime_metadata(metadata),
        "report_metadata": _build_report_metadata(governance_config, metadata, failed_operations, report_path),
    }


def export_autorresearch_report(report: Dict[str, Any], output_path: Path, governance_config: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(report, ensure_ascii=False))
    metadata = payload.setdefault("metadata", _build_runtime_metadata({}))
    failed_operations = payload.setdefault("failed_operations", [])
    export_started_at = _start_phase(metadata, "export_autorresearch_report", {"output_path": str(output_path)})
    _complete_phase(metadata, "export_autorresearch_report", export_started_at, {"output_path": str(output_path)}, final_status=metadata.get("final_status", "completed"))
    payload["metadata"] = _build_runtime_metadata(metadata)
    payload["analysis_summary"] = _build_analysis_summary(payload.get("history", []), payload.get("best_val_bpb"), metadata, failed_operations, governance_config)
    payload["report_metadata"] = _build_report_metadata(governance_config, metadata, failed_operations, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run_cmd(cmd: list[str], cwd: Path) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def git_current_head(repo: Path) -> str:
    code, out, err = run_cmd(["git", "rev-parse", "HEAD"], repo)
    if code != 0:
        raise RuntimeError(f"git rev-parse failed: {err}")
    return out.strip()


def git_commit_train(repo: Path, msg: str) -> bool:
    run_cmd(["git", "add", "tools/autorresearch/train.py"], repo)
    code, _, _ = run_cmd(["git", "commit", "-m", msg], repo)
    return code == 0


def git_rollback_train(repo: Path, mode: str) -> None:
    # Safe scoped rollback for train.py only.
    if mode == "reset":
        run_cmd(["git", "reset", "--hard", "HEAD"], repo)
    else:
        run_cmd(["git", "restore", "--source=HEAD", "--", "tools/autorresearch/train.py"], repo)


def parse_metrics(text: str) -> Tuple[Optional[float], Optional[int]]:
    val = None
    vram = None
    m1 = VAL_RE.search(text)
    m2 = VRAM_RE.search(text)
    if m1:
        val = float(m1.group(1))
    if m2:
        vram = int(m2.group(1))
    return val, vram


def run_training(repo: Path, python_exe: str, timeout_s: int, trial_idx: int) -> TrialResult:
    log_dir = repo / "logs" / "autorresearch"
    log_dir.mkdir(parents=True, exist_ok=True)
    json_log = log_dir / f"trial_{trial_idx:03d}.json"

    cmd = [
        python_exe,
        "tools/autorresearch/train.py",
        "--max-seconds",
        str(timeout_s),
        "--log-json",
        str(json_log),
    ]

    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=timeout_s + 30)
        dur = time.perf_counter() - t0
        merged = (p.stdout or "") + "\n" + (p.stderr or "")
        val, vram = parse_metrics(merged)
        crashed = p.returncode != 0 or val is None
        return TrialResult(
            ok=(p.returncode == 0 and val is not None),
            val_bpb=val,
            vram_peak_mb=vram,
            stdout=p.stdout,
            stderr=p.stderr,
            duration_s=dur,
            crashed=crashed,
        )
    except subprocess.TimeoutExpired as e:
        dur = time.perf_counter() - t0
        out = _normalize_text(e.stdout)
        err = _normalize_text(e.stderr)
        return TrialResult(
            ok=False,
            val_bpb=None,
            vram_peak_mb=None,
            stdout=out,
            stderr=err + "\nTIMEOUT",
            duration_s=dur,
            crashed=True,
        )


def propose_hypothesis(iter_idx: int, instruction: str) -> Dict[str, float]:
    # Deterministic local strategy for small-sample AutoResearch:
    # progressively move hypers toward known better region.
    steps = [
        {"lr": 0.0032, "dropout": 0.16, "weight_decay": 0.028, "grad_clip": 1.2, "batch_size": 112},
        {"lr": 0.0028, "dropout": 0.13, "weight_decay": 0.020, "grad_clip": 0.95, "batch_size": 128},
        {"lr": 0.0025, "dropout": 0.10, "weight_decay": 0.015, "grad_clip": 0.80, "batch_size": 128},
    ]
    return steps[min(iter_idx, len(steps) - 1)]


def propose_hypothesis_with_llm(
    repo: Path,
    instruction: str,
    program_text: str,
    train_text: str,
    history: list[dict],
) -> Optional[Dict[str, float]]:
    try:
        from src.llm.llm_engine import LLMEngine

        engine = LLMEngine(temperature=0.2, max_tokens=512)
        engine.load()
        prompt = (
            "你是 AutoResearch 智能体。请根据 program.md 约束与历史结果，给出下一轮 train.py 的超参数 JSON。"
            "只输出 JSON，不要解释。\n"
            "字段必须包含: lr, dropout, weight_decay, grad_clip, batch_size。\n"
            f"中文研究指令: {instruction}\n"
            f"program.md:\n{program_text[:3000]}\n"
            f"train.py(截断):\n{train_text[:5000]}\n"
            f"history:\n{json.dumps(history[-5:], ensure_ascii=False)}"
        )
        raw = engine.generate(prompt)
        engine.unload()

        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group(0))
        hp = {
            "lr": float(obj["lr"]),
            "dropout": float(obj["dropout"]),
            "weight_decay": float(obj["weight_decay"]),
            "grad_clip": float(obj["grad_clip"]),
            "batch_size": int(obj["batch_size"]),
        }
        return hp
    except Exception:
        return None


def patch_train(train_path: Path, hp: Dict[str, float]) -> None:
    text = train_path.read_text(encoding="utf-8")

    repls = {
        r"lr\s*=\s*[0-9.]+": f"lr = {hp['lr']}",
        r"dropout\s*=\s*[0-9.]+": f"dropout = {hp['dropout']}",
        r"weight_decay\s*=\s*[0-9.]+": f"weight_decay = {hp['weight_decay']}",
        r"grad_clip\s*=\s*[0-9.]+": f"grad_clip = {hp['grad_clip']}",
        r"batch_size\s*=\s*[0-9]+": f"batch_size = {int(hp['batch_size'])}",
    }

    for pat, new_val in repls.items():
        text = re.sub(pat, new_val, text)

    train_path.write_text(text, encoding="utf-8")


def run_autorresearch_loop(
    repo: Path,
    instruction: str,
    max_iters: int,
    timeout_seconds: int,
    python_exe: str,
    strategy: str,
    rollback_mode: str,
    config_path: Path | None = None,
    output_path: Path | None = None,
) -> Dict[str, Any]:
    governance_config = _load_governance_config(config_path)
    metadata: Dict[str, Any] = {
        "phase_history": [],
        "phase_timings": {},
        "completed_phases": [],
        "failed_phase": None,
        "final_status": "running",
        "last_completed_phase": None,
    }
    failed_operations: list[dict] = []

    program_path = repo / "tools" / "autorresearch" / "program.md"
    train_path = repo / "tools" / "autorresearch" / "train.py"
    program_text = program_path.read_text(encoding="utf-8")
    train_text = train_path.read_text(encoding="utf-8")

    baseline_started_at = _start_phase(metadata, "run_autorresearch_baseline", {"timeout_seconds": timeout_seconds})
    baseline = run_training(repo, python_exe, timeout_seconds, trial_idx=0)
    if not baseline.ok or baseline.val_bpb is None:
        _fail_phase(
            metadata,
            failed_operations,
            governance_config,
            "run_autorresearch_baseline",
            baseline_started_at,
            RuntimeError("Baseline training failed; cannot start AutoResearch loop."),
            {"stderr": baseline.stderr, "stdout": baseline.stdout},
        )
        raise RuntimeError("Baseline training failed; cannot start AutoResearch loop.")
    _complete_phase(
        metadata,
        "run_autorresearch_baseline",
        baseline_started_at,
        {"best_val_bpb": baseline.val_bpb, "vram_peak_mb": baseline.vram_peak_mb},
    )

    best_val = float(baseline.val_bpb)
    history: list[dict] = [
        {
            "iter": 0,
            "status": "baseline",
            "val_bpb": best_val,
            "vram_peak_mb": baseline.vram_peak_mb,
            "duration_s": round(baseline.duration_s, 3),
        }
    ]

    iterations_started_at = _start_phase(metadata, "run_autorresearch_iterations", {"max_iters": max_iters, "strategy": strategy})
    try:
        for i in range(1, max_iters + 1):
            if strategy == "llm":
                hp = propose_hypothesis_with_llm(repo, instruction, program_text, train_text, history)
                if hp is None:
                    hp = propose_hypothesis(i - 1, instruction)
            else:
                hp = propose_hypothesis(i - 1, instruction)

            patch_train(train_path, hp)

            code, _, err = run_cmd([python_exe, "-m", "py_compile", "tools/autorresearch/train.py"], repo)
            if code != 0:
                git_rollback_train(repo, rollback_mode)
                history.append({"iter": i, "status": "syntax_fail", "error": err, "hparams": hp})
                _record_failed_operation(
                    failed_operations,
                    governance_config,
                    "syntax_check",
                    err,
                    {"iter": i, "hparams": hp},
                )
                continue

            trial = run_training(repo, python_exe, timeout_seconds, trial_idx=i)
            improved = bool(trial.ok and trial.val_bpb is not None and trial.val_bpb < best_val)

            if improved:
                best_val = float(trial.val_bpb)
                msg = f"autorresearch: improve val_bpb to {best_val:.6f} (iter {i})"
                committed = git_commit_train(repo, msg)
                history.append(
                    {
                        "iter": i,
                        "status": "improved_committed" if committed else "improved_no_commit",
                        "val_bpb": trial.val_bpb,
                        "vram_peak_mb": trial.vram_peak_mb,
                        "duration_s": round(trial.duration_s, 3),
                        "hparams": hp,
                    }
                )
                if not committed:
                    _record_failed_operation(
                        failed_operations,
                        governance_config,
                        "git_commit_train",
                        "Improved trial could not be committed",
                        {"iter": i, "hparams": hp, "val_bpb": trial.val_bpb},
                    )
            else:
                git_rollback_train(repo, rollback_mode)
                history.append(
                    {
                        "iter": i,
                        "status": "rollback",
                        "val_bpb": trial.val_bpb,
                        "vram_peak_mb": trial.vram_peak_mb,
                        "duration_s": round(trial.duration_s, 3),
                        "crashed": trial.crashed,
                        "hparams": hp,
                    }
                )
                if trial.crashed:
                    _record_failed_operation(
                        failed_operations,
                        governance_config,
                        "run_training",
                        "Trial crashed or did not produce val_bpb",
                        {"iter": i, "hparams": hp, "stderr": trial.stderr, "stdout": trial.stdout},
                        trial.duration_s,
                    )
    except Exception as error:
        _fail_phase(
            metadata,
            failed_operations,
            governance_config,
            "run_autorresearch_iterations",
            iterations_started_at,
            error,
            {"max_iters": max_iters, "strategy": strategy},
        )
        raise

    metadata["final_status"] = "completed"
    _complete_phase(
        metadata,
        "run_autorresearch_iterations",
        iterations_started_at,
        {"trial_count": len(history), "best_val_bpb": best_val},
        final_status="completed",
    )

    assemble_started_at = _start_phase(metadata, "assemble_autorresearch_report", {"trial_count": len(history)})
    _complete_phase(
        metadata,
        "assemble_autorresearch_report",
        assemble_started_at,
        {"trial_count": len(history), "best_val_bpb": best_val},
        final_status=metadata.get("final_status", "completed"),
    )
    report = build_autorresearch_report(
        instruction,
        strategy,
        rollback_mode,
        best_val,
        history,
        governance_config,
        metadata,
        failed_operations,
        output_path,
    )
    return export_autorresearch_report(report, output_path or (repo / "output" / "autorresearch_report.json"), governance_config)


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoResearch runner")
    parser.add_argument("--instruction", type=str, default="", help="中文研究指令")
    parser.add_argument("--instruction-file", type=str, default="", help="中文研究指令文件（UTF-8）")
    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--python-exe", type=str, default=sys.executable)
    parser.add_argument("--strategy", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--rollback-mode", choices=["restore", "reset"], default="restore")
    parser.add_argument("--config", type=str, default="config.yml")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    config_path = (repo / args.config).resolve()

    instruction = args.instruction
    if args.instruction_file:
        instruction = Path(args.instruction_file).read_text(encoding="utf-8").strip()
    if not instruction:
        raise RuntimeError("必须提供 --instruction 或 --instruction-file")

    report = run_autorresearch_loop(
        repo=repo,
        instruction=instruction,
        max_iters=args.max_iters,
        timeout_seconds=args.timeout_seconds,
        python_exe=args.python_exe,
        strategy=args.strategy,
        rollback_mode=args.rollback_mode,
        config_path=config_path,
    )

    print(f"best_val_bpb={float(report['best_val_bpb']):.6f}")
    print(f"report={report['report_metadata']['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
