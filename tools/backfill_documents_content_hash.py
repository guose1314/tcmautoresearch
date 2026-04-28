"""T2.3 一次性 backfill：填充 documents.content_hash / ingest_run_id 并去重。

策略（用户决定方案 A）：
  1. 扫所有 documents 行；
  2. 把遗留 source_file '<original>_<YYYYMMDD_HHMMSS>_<8hex>' 拆成
     canonical source_file + ingest_run_id 后写回；
  3. 按 canonical source_file 在 data/ 中找原始 .txt（递归），读盘 SHA-256
     填 content_hash；找不到的留 sentinel hash（'__missing_disk__' + uid）
     避免 NOT NULL 阶段卡死；
  4. 复合 UNIQUE (source_file, content_hash) 触发的重复行：保留 created_at
     最早一条，其余 children entities/relationships/logs 经 ON DELETE
     CASCADE 一并清理。

跑前必须升到 head (`alembic upgrade head`)。dry-run 默认开启。

示例：
    venv310/Scripts/python.exe tools/backfill_documents_content_hash.py \
        --connection-string sqlite:///./tcmautoresearch.db --apply

CI 兜底场景已被 [tools/cleanup_duplicate_batch_assets.py](cleanup_duplicate_batch_assets.py)
取代，本脚本是其唯一的"正向迁移"形态。
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

logger = logging.getLogger("backfill_documents_content_hash")

_LEGACY_SUFFIX_RE = re.compile(r"_(?P<ts>\d{8}_\d{6})_(?P<uid>[0-9a-f]{8})$")


def _split_legacy(source_file: str) -> Tuple[str, Optional[str]]:
    m = _LEGACY_SUFFIX_RE.search(source_file)
    if not m:
        return source_file, None
    return source_file[: m.start()], f"{m.group('ts')}_{m.group('uid')}"


def _resolve_disk_path(canonical_name: str) -> Optional[Path]:
    """Find the disk file for a canonical source_file.

    Tries (in order):
      - DATA_DIR / canonical_name (if it ends with .txt or has any extension)
      - DATA_DIR / f"{canonical_name}.txt"
      - first match of DATA_DIR.rglob(canonical_name)
      - first match of DATA_DIR.rglob(f"{canonical_name}.txt")
    """
    candidates: List[Path] = []
    raw = canonical_name.strip()
    if not raw:
        return None
    direct = (DATA_DIR / raw)
    if direct.exists():
        return direct
    if not raw.endswith(".txt"):
        with_ext = DATA_DIR / f"{raw}.txt"
        if with_ext.exists():
            return with_ext
    base = os.path.basename(raw)
    matches = list(DATA_DIR.rglob(base))
    if not matches and not base.endswith(".txt"):
        matches = list(DATA_DIR.rglob(f"{base}.txt"))
    if matches:
        return matches[0]
    return candidates[0] if candidates else None


def _hash_disk(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection-string",
        required=True,
        help="SQLAlchemy connection string (e.g. sqlite:///./tcmautoresearch.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default: dry-run, prints plan only).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    engine = create_engine(args.connection_string)
    Session = sessionmaker(bind=engine)

    # Phase 1: read-only inventory.
    with Session() as session:
        rows = session.execute(
            text(
                """
                SELECT id, source_file, content_hash, ingest_run_id, created_at
                FROM documents
                ORDER BY created_at ASC
                """
            )
        ).all()

    logger.info("scanned documents rows=%d", len(rows))

    # Pass 1: split legacy suffix, resolve disk hash, plan updates.
    plan: List[Dict[str, str]] = []
    canonical_to_hash: Dict[str, str] = {}
    missing: List[str] = []

    for row in rows:
        doc_id = str(row.id)
        original_sf = row.source_file or ""
        canonical, suffix_run_id = _split_legacy(original_sf)
        new_run_id = row.ingest_run_id or suffix_run_id

        if canonical not in canonical_to_hash:
            disk = _resolve_disk_path(canonical)
            if disk is None:
                missing.append(canonical)
                # Sentinel hash: deterministic per canonical name; later UNIQUE
                # collisions still collapse like-for-like.
                canonical_to_hash[canonical] = (
                    "missing_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:56]
                )
            else:
                canonical_to_hash[canonical] = _hash_disk(disk)
        new_hash = row.content_hash or canonical_to_hash[canonical]

        plan.append(
            {
                "id": doc_id,
                "old_source_file": original_sf,
                "new_source_file": canonical,
                "new_content_hash": new_hash,
                "new_ingest_run_id": new_run_id or "",
                "created_at": str(row.created_at),
            }
        )

    # Pass 2: dedup planning. Group by (canonical, hash); keep earliest, delete rest.
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for entry in plan:
        grouped[(entry["new_source_file"], entry["new_content_hash"])].append(entry)

    keep_ids: List[str] = []
    delete_ids: List[str] = []
    for (sf, h), entries in grouped.items():
        # earliest created_at first (already sorted ASC above)
        keep_ids.append(entries[0]["id"])
        for extra in entries[1:]:
            delete_ids.append(extra["id"])

    logger.info(
        "plan: rows=%d unique_keys=%d keep=%d delete=%d disk_missing=%d",
        len(plan), len(grouped), len(keep_ids), len(delete_ids), len(missing),
    )
    if missing:
        sample = ", ".join(sorted(set(missing))[:5])
        logger.warning("disk-missing canonical names (%d total) sample: %s", len(missing), sample)

    if not args.apply:
        logger.info("dry-run only; rerun with --apply to persist")
        return 0

    # Pass 3: write updates and deletions.
    with Session() as session:
        with session.begin():
            for entry in plan:
                if entry["id"] in delete_ids:
                    continue
                session.execute(
                    text(
                        """
                        UPDATE documents
                        SET source_file = :sf,
                            content_hash = :ch,
                            ingest_run_id = NULLIF(:rid, '')
                        WHERE id = :id
                        """
                    ),
                    {
                        "sf": entry["new_source_file"],
                        "ch": entry["new_content_hash"],
                        "rid": entry["new_ingest_run_id"],
                        "id": entry["id"],
                    },
                )
            for doc_id in delete_ids:
                # Children (entities/relationships/logs) cascade via FK.
                session.execute(
                    text("DELETE FROM documents WHERE id = :id"),
                    {"id": doc_id},
                )
    logger.info("apply complete: kept=%d deleted=%d", len(keep_ids), len(delete_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
