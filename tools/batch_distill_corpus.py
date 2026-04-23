"""批量把 data/*.txt 灌入 /api/analysis/distill。

阶段：
  1. 编码归一化：把所有 .txt 探测编码并改写为 UTF-8（原文件覆盖；BOM 去掉）。
  2. 蒸馏推送：登录 8765，逐文件 POST /api/analysis/distill。
     /distill 内部已串联：preprocess → entity 抽取 → semantic graph →
     LLM 蒸馏（按 1400 字切片）→ 双库持久化（KG SQLite + 业务 ORM）。

注意规模：1602 文件 / 358MB / 7B Q8 GPU 推理约 5-15s/片，全量需要数十天。
默认 --max-bytes 80000 只取每文件前 ~80KB（≈57 片，每文件几分钟）。
用 --max-bytes 0 解除上限。--limit-files 控制处理多少个文件。
进度写入 logs/batch_distill_progress.jsonl，可断点续跑（--resume，默认开）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import chardet
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
LOG_PATH = REPO_ROOT / "logs" / "batch_distill_progress.jsonl"


def detect_and_normalize_utf8(path: Path) -> Dict[str, Any]:
    """把单个文件转成 UTF-8（无 BOM）。返回 {converted, encoding, size}。"""
    raw = path.read_bytes()
    # 已经是 UTF-8 / UTF-8-BOM 的快速路径
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])
        return {"converted": True, "encoding": "utf-8-bom", "size": len(raw) - 3}
    try:
        raw.decode("utf-8")
        return {"converted": False, "encoding": "utf-8", "size": len(raw)}
    except UnicodeDecodeError:
        pass
    # 探测
    enc = (chardet.detect(raw[:65536]) or {}).get("encoding") or "gb18030"
    # gb2312/gbk 一律按 gb18030 解（兼容超集）
    if enc.lower() in {"gb2312", "gbk", "windows-1252", "ascii"}:
        enc = "gb18030"
    try:
        text = raw.decode(enc, errors="replace")
    except LookupError:
        text = raw.decode("gb18030", errors="replace")
    path.write_text(text, encoding="utf-8")
    return {"converted": True, "encoding": enc, "size": len(text.encode("utf-8"))}


def login(base_url: str, username: str, password: str) -> str:
    r = requests.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def load_done_set() -> set[str]:
    if not LOG_PATH.exists():
        return set()
    done: set[str] = set()
    for line in LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("ok"):
                done.add(rec["file"])
        except Exception:
            continue
    return done


def append_log(rec: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def distill_one(
    base_url: str,
    token: str,
    file_path: Path,
    max_bytes: int,
    timeout: int,
) -> Dict[str, Any]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    truncated = False
    if max_bytes > 0:
        # max_bytes 是字符数上限（避免 UTF-8 切坏字）
        if len(text) > max_bytes:
            text = text[:max_bytes]
            truncated = True
    payload = {"raw_text": text, "source_file": file_path.name}
    t0 = time.time()
    r = requests.post(
        f"{base_url}/api/analysis/distill",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    elapsed = time.time() - t0
    if r.status_code != 200:
        return {
            "ok": False,
            "status": r.status_code,
            "elapsed_s": round(elapsed, 1),
            "truncated": truncated,
            "chars_sent": len(text),
            "error": r.text[:500],
        }
    body = r.json()
    return {
        "ok": True,
        "status": 200,
        "elapsed_s": round(elapsed, 1),
        "truncated": truncated,
        "chars_sent": len(text),
        "llm": body.get("llm_extracted", {}),
        "rule": body.get("rule_extracted", {}),
        "merged": body.get("merged", {}),
        "kg": {
            "new_entities": body.get("knowledge_accumulation", {}).get("new_entities"),
            "new_relations": body.get("knowledge_accumulation", {}).get("new_relations"),
            "total_entities": body.get("knowledge_accumulation", {}).get("total_entities"),
            "total_relations": body.get("knowledge_accumulation", {}).get("total_relations"),
            "orm_entities": body.get("knowledge_accumulation", {}).get("orm_entities"),
            "orm_relations": body.get("knowledge_accumulation", {}).get("orm_relations"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--username", default="hgk1988")
    ap.add_argument("--password", default="Hgk1989225")
    ap.add_argument("--limit-files", type=int, default=0,
                    help="最多处理多少个文件 (0=全部)")
    ap.add_argument("--max-bytes", type=int, default=80000,
                    help="单文件取前 N 字符 (0=不截断)")
    ap.add_argument("--skip-larger-than", type=int, default=2_000_000,
                    help="跳过原始字节数超此值的巨型文件 (0=不跳)")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--no-utf8-fix", action="store_true",
                    help="跳过 UTF-8 归一化阶段")
    ap.add_argument("--no-resume", action="store_true",
                    help="忽略历史进度，从头跑")
    ap.add_argument("--sort", choices=["asc", "desc", "name"], default="asc",
                    help="按字节数升 / 降 / 文件名排序")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.txt"), key=lambda p: p.name)
    if args.sort == "asc":
        files.sort(key=lambda p: p.stat().st_size)
    elif args.sort == "desc":
        files.sort(key=lambda p: -p.stat().st_size)

    if args.skip_larger_than > 0:
        files = [p for p in files if p.stat().st_size <= args.skip_larger_than]

    print(f"[scan] 目标文件数={len(files)} (跳过>{args.skip_larger_than}B 的巨型文件)")

    # 阶段 1: UTF-8 归一化
    if not args.no_utf8_fix:
        converted = 0
        for i, p in enumerate(files, 1):
            try:
                info = detect_and_normalize_utf8(p)
                if info["converted"]:
                    converted += 1
                    if converted <= 20 or converted % 50 == 0:
                        print(f"[utf8] {i}/{len(files)} {p.name} <- {info['encoding']}")
            except Exception as exc:
                print(f"[utf8-err] {p.name}: {exc}")
        print(f"[utf8] 完成，重写 {converted} 个文件")

    # 阶段 2: 登录 + 蒸馏
    print(f"[login] {args.base_url}")
    token = login(args.base_url, args.username, args.password)
    print("[login] OK")

    done = set() if args.no_resume else load_done_set()
    if done:
        print(f"[resume] 已完成 {len(done)} 个，跳过")

    pending = [p for p in files if p.name not in done]
    if args.limit_files > 0:
        pending = pending[: args.limit_files]
    print(f"[plan] 本次处理 {len(pending)} 个文件")

    ok_n = err_n = 0
    t_start = time.time()
    for i, p in enumerate(pending, 1):
        try:
            res = distill_one(args.base_url, token, p, args.max_bytes, args.timeout)
        except requests.exceptions.ReadTimeout:
            res = {"ok": False, "status": 0, "error": "read-timeout"}
        except Exception as exc:
            res = {"ok": False, "status": 0, "error": f"{type(exc).__name__}: {exc}"}
        rec = {"file": p.name, "size": p.stat().st_size, **res}
        append_log(rec)
        if res.get("ok"):
            ok_n += 1
            kg = res.get("kg", {})
            print(
                f"[{i}/{len(pending)}] OK {p.name} "
                f"({res['chars_sent']}字, {res['elapsed_s']}s) "
                f"llm={res['llm']} rule={res['rule']} "
                f"kg_total={kg.get('total_entities')}/{kg.get('total_relations')} "
                f"orm={kg.get('orm_entities')}/{kg.get('orm_relations')}"
            )
        else:
            err_n += 1
            print(f"[{i}/{len(pending)}] FAIL {p.name} status={res.get('status')} {str(res.get('error'))[:200]}")

        # 阶段性总结
        if i % 10 == 0:
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed else 0
            eta = (len(pending) - i) / rate if rate else 0
            print(f"  [stat] ok={ok_n} err={err_n} rate={rate:.2f} f/s eta={eta/60:.1f}min")

    print(f"[done] ok={ok_n} err={err_n} total_time={(time.time()-t_start)/60:.1f}min")
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
