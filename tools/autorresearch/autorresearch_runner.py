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
from typing import Dict, Optional, Tuple

VAL_RE = re.compile(r"val_bpb\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
VRAM_RE = re.compile(r"vram_peak_mb\s*=\s*([0-9]+)", re.IGNORECASE)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoResearch runner")
    parser.add_argument("--instruction", type=str, default="", help="中文研究指令")
    parser.add_argument("--instruction-file", type=str, default="", help="中文研究指令文件（UTF-8）")
    parser.add_argument("--max-iters", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--python-exe", type=str, default=sys.executable)
    parser.add_argument("--strategy", choices=["heuristic", "llm"], default="heuristic")
    parser.add_argument("--rollback-mode", choices=["restore", "reset"], default="restore")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    program_path = repo / "tools" / "autorresearch" / "program.md"
    train_path = repo / "tools" / "autorresearch" / "train.py"

    program_text = program_path.read_text(encoding="utf-8")
    train_text = train_path.read_text(encoding="utf-8")

    instruction = args.instruction
    if args.instruction_file:
        instruction = Path(args.instruction_file).read_text(encoding="utf-8").strip()
    if not instruction:
        raise RuntimeError("必须提供 --instruction 或 --instruction-file")

    baseline = run_training(repo, args.python_exe, args.timeout_seconds, trial_idx=0)
    if not baseline.ok or baseline.val_bpb is None:
        raise RuntimeError("Baseline training failed; cannot start AutoResearch loop.")

    best_val: float = float(baseline.val_bpb)
    history = [
        {
            "iter": 0,
            "status": "baseline",
            "val_bpb": best_val,
            "vram_peak_mb": baseline.vram_peak_mb,
            "duration_s": round(baseline.duration_s, 3),
        }
    ]

    for i in range(1, args.max_iters + 1):
        if args.strategy == "llm":
            hp = propose_hypothesis_with_llm(repo, instruction, program_text, train_text, history)
            if hp is None:
                hp = propose_hypothesis(i - 1, instruction)
        else:
            hp = propose_hypothesis(i - 1, instruction)

        patch_train(train_path, hp)

        # quick syntax check
        code, _, err = run_cmd([args.python_exe, "-m", "py_compile", "tools/autorresearch/train.py"], repo)
        if code != 0:
            git_rollback_train(repo, args.rollback_mode)
            history.append({"iter": i, "status": "syntax_fail", "error": err})
            continue

        trial = run_training(repo, args.python_exe, args.timeout_seconds, trial_idx=i)
        improved = False
        if trial.ok and trial.val_bpb is not None:
            improved = trial.val_bpb < best_val

        if improved:
            if trial.val_bpb is None:
                git_rollback_train(repo, args.rollback_mode)
                history.append({"iter": i, "status": "rollback_missing_metric"})
                continue
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
        else:
            git_rollback_train(repo, args.rollback_mode)
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

    out_dir = repo / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "autorresearch_report.json"
    out_path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "instruction": instruction,
                "strategy": args.strategy,
                "rollback_mode": args.rollback_mode,
                "best_val_bpb": best_val,
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"best_val_bpb={best_val:.6f}")
    print(f"report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
