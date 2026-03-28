#!/usr/bin/env python3
"""Small-sample train script used by AutoResearch workflow.

This script simulates an ML training loop and emits:
- val_bpb=<float>  (lower is better)
- vram_peak_mb=<int>

The score is deterministic by hyperparameters so AutoResearch can optimize safely.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def compute_val_bpb(lr: float, dropout: float, wd: float, grad_clip: float, batch_size: int) -> float:
    # Synthetic but smooth objective with a known optimum.
    # Best region around: lr = 0.0025, dropout = 0.1, wd=0.015, grad_clip = 0.8, batch_size = 128
    score = 1.25
    score += 120.0 * (lr - 0.0025) ** 2
    score += 1.5 * (dropout - 0.10) ** 2
    score += 2.0 * (wd - 0.015) ** 2
    score += 0.8 * (grad_clip - 0.8) ** 2
    score += 0.00003 * (batch_size - 128) ** 2
    return score


def estimate_vram_mb(batch_size: int, seq_len: int, hidden_size: int, n_layers: int) -> int:
    base = 1100
    dynamic = int(batch_size * seq_len * hidden_size * n_layers / 2_000_000)
    return base + dynamic


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoResearch toy training")
    parser.add_argument("--max-seconds", type=int, default=300)
    parser.add_argument("--log-json", type=str, default="")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # ===== Tunable hypers (AutoResearch edits this block) =====
    lr = 0.0025
    dropout = 0.1
    weight_decay = 0.015
    grad_clip = 0.8
    batch_size = 128
    seq_len = 256
    hidden_size = 512
    n_layers = 8
    # ===== End tunable block =====

    random.seed(args.seed)

    # Simulate short training time, independent from timeout budget.
    run_s = min(8, max(3, args.max_seconds // 60))
    time.sleep(run_s)

    val_bpb = compute_val_bpb(lr, dropout, weight_decay, grad_clip, batch_size)
    vram_peak_mb = estimate_vram_mb(batch_size, seq_len, hidden_size, n_layers)

    # Add tiny noise to mimic run variance.
    val_bpb += random.uniform(-0.002, 0.002)
    val_bpb = round(val_bpb, 6)

    print(f"val_bpb={val_bpb}")
    print(f"vram_peak_mb={vram_peak_mb}")

    if args.log_json:
        payload = {
            "val_bpb": val_bpb,
            "vram_peak_mb": vram_peak_mb,
            "hparams": {
                "lr": lr,
                "dropout": dropout,
                "weight_decay": weight_decay,
                "grad_clip": grad_clip,
                "batch_size": batch_size,
                "seq_len": seq_len,
                "hidden_size": hidden_size,
                "n_layers": n_layers,
            },
        }
        Path(args.log_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
