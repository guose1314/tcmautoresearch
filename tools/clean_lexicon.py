"""清理 data/tcm_lexicon.jsonl：剔除噪声词条。

噪声判定（与 audit_lexicon.py 同源）：
  1. 处方语片段前缀 (加/各/每/或/若/用/以/再/另/将/兼/并)
  2. 剂量描述前缀 (一钱/三两/五分/十枚 …)
  3. 含标点或空白字符
  4. herb 长度 > 5（典型为剂量/工艺残段）
  5. 已知通用病人称谓 / 工艺词

写入 data/tcm_lexicon.jsonl（覆盖；先在原地备份 .bak）。
同时输出 data/tcm_lexicon_removed.jsonl —— 被剔除条目（带 reason 字段）。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

LEXICON = Path(__file__).resolve().parents[1] / "data" / "tcm_lexicon.jsonl"
REMOVED = LEXICON.with_name("tcm_lexicon_removed.jsonl")
BAK = LEXICON.with_suffix(".jsonl.bak")

# --- 规则 ---
PREFIX_NOISE = (
    "加", "各", "每", "或", "若", "用", "以", "再", "另", "将", "兼", "并",
)
DOSAGE_HEAD_RE = re.compile(
    r"^(?:一|二|三|四|五|六|七|八|九|十|百|千|万|两|半|\d+)+\s*(?:钱|两|分|斤|升|毫|枚|颗|粒|锭|丸|匙|杯|盏|瓢|勺|滴|片|寸)"
)
DOSAGE_HEAD_HERB_RE = re.compile(
    r"^(?:一|二|三|四|五|六|七|八|九|十|百|千|万)+\s*(?:钱|两|分|斤|升)$"
)
PUNCT_WHITESPACE_RE = re.compile(
    r"[，。、；：！？,\.;:?!\(\)（）【】\[\]「」『』《》\"'“”‘’\s]"
)
GENERIC_HUMAN = {
    "小儿", "妇人", "男子", "病人", "病者", "诸药", "上药", "上述",
    "以上", "服药", "共享", "甘草小儿童子", "以上各",
}
HERB_MAX_LEN = 5  # herb 类目超过 5 字几乎都是处方语 / 配伍片段


def is_noise(term: str, category: str) -> str | None:
    """返回 reason；None 表示保留。"""
    if not term or not isinstance(term, str):
        return "empty"
    if PUNCT_WHITESPACE_RE.search(term):
        return "punct_or_whitespace"
    if term in GENERIC_HUMAN:
        return "generic_human"
    if category == "herb" and len(term) > HERB_MAX_LEN:
        return f"herb_len>{HERB_MAX_LEN}"
    if category == "herb" and any(term.startswith(p) for p in PREFIX_NOISE):
        return "prefix_noise"
    if category == "herb" and DOSAGE_HEAD_HERB_RE.match(term):
        return "dosage_only"
    if category == "herb" and DOSAGE_HEAD_RE.match(term):
        return "dosage_prefix"
    return None


def main() -> None:
    if not LEXICON.exists():
        raise SystemExit(f"lexicon not found: {LEXICON}")

    # 备份
    shutil.copy2(LEXICON, BAK)

    keep: list[dict] = []
    drop: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for line in LEXICON.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        term = (rec.get("term") or "").strip()
        category = (rec.get("category") or "").strip()
        reason = is_noise(term, category)
        if reason:
            drop.append({**rec, "reason": reason})
            continue
        # 去重
        key = (term, category)
        if key in seen_pairs:
            drop.append({**rec, "reason": "duplicate"})
            continue
        seen_pairs.add(key)
        keep.append({"term": term, "category": category})

    # 写回
    with LEXICON.open("w", encoding="utf-8") as f:
        for rec in keep:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with REMOVED.open("w", encoding="utf-8") as f:
        for rec in drop:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    by_cat_kept: dict[str, int] = {}
    for r in keep:
        by_cat_kept[r["category"]] = by_cat_kept.get(r["category"], 0) + 1
    by_reason: dict[str, int] = {}
    for r in drop:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1

    print(f"backup -> {BAK.name}")
    print(f"kept   = {len(keep)}  removed = {len(drop)}")
    print("by_category_kept:", json.dumps(by_cat_kept, ensure_ascii=False))
    print("by_reason_removed:", json.dumps(by_reason, ensure_ascii=False))


if __name__ == "__main__":
    main()
