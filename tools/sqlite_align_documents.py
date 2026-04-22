"""幂等地把 SQLite documents 表对齐到 ORM 模型，并把 alembic_version 标到 head。

背景：data/tcmautoresearch.db 中 documents 表只保留了早期 11 列，
而 ORM 模型已扩展到 24 列（对应 alembic revision e4c6d2b7a9f1）。
该开发库 alembic_version 长期为空，新 revision 始终无法增量上去。

本脚本两件事，均幂等：
  1. 按列名/索引差集追加 documents 缺失的列与索引（容灾兜底）。
  2. 调 alembic stamp head，把 alembic_version 标到当前 head，
     之后即可正常 `alembic upgrade head`。

用法：
  python tools/sqlite_align_documents.py            # 对齐 + stamp head
  python tools/sqlite_align_documents.py --no-stamp # 仅对齐
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "tcmautoresearch.db"

# (column_name, column_ddl)
COLUMNS = [
    ("document_urn", "VARCHAR(500)"),
    ("document_title", "VARCHAR(500)"),
    ("source_type", "VARCHAR(64)"),
    ("catalog_id", "VARCHAR(255)"),
    ("work_title", "VARCHAR(255)"),
    ("fragment_title", "VARCHAR(255)"),
    ("work_fragment_key", "VARCHAR(500)"),
    ("version_lineage_key", "VARCHAR(500)"),
    ("witness_key", "VARCHAR(500)"),
    ("dynasty", "VARCHAR(255)"),
    ("author", "VARCHAR(255)"),
    ("edition", "VARCHAR(255)"),
    ("version_metadata_json", "JSON NOT NULL DEFAULT '{}'"),
]

INDEXES = [
    ("idx_documents_urn", "document_urn"),
    ("idx_documents_catalog_id", "catalog_id"),
    ("idx_documents_lineage", "version_lineage_key"),
    ("idx_documents_work_fragment", "work_fragment_key"),
    ("idx_documents_witness", "witness_key"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="只对齐表结构，不调用 alembic stamp head",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1
    con = sqlite3.connect(DB_PATH)
    try:
        existing = {row[1] for row in con.execute("PRAGMA table_info(documents)").fetchall()}
        added: list[str] = []
        for name, ddl in COLUMNS:
            if name in existing:
                continue
            con.execute(f"ALTER TABLE documents ADD COLUMN {name} {ddl}")
            added.append(name)

        existing_idx = {row[1] for row in con.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='documents'"
        ).fetchall()}
        added_idx: list[str] = []
        for idx_name, col in INDEXES:
            if idx_name in existing_idx:
                continue
            con.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON documents({col})")
            added_idx.append(idx_name)

        con.commit()
    finally:
        con.close()

    print(f"added columns: {added}")
    print(f"added indexes: {added_idx}")

    if args.no_stamp:
        print("--no-stamp: skip alembic stamp")
        return 0

    stamped = _stamp_alembic_head()
    if stamped:
        print(f"alembic stamp head -> {stamped}")
    return 0


def _stamp_alembic_head() -> str | None:
    """把 alembic_version 标到当前 head，幂等。"""
    # 仅在 sys.path 准备好后再 import alembic，避免污染顶部
    sys.path.insert(0, str(REPO_ROOT))
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    from alembic import command

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}"
    )
    head = ScriptDirectory.from_config(cfg).get_current_head()

    engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current == head:
        print(f"alembic_version already at head ({head}), skip stamp")
        return None

    command.stamp(cfg, "head")
    return head or "(unknown)"


if __name__ == "__main__":
    sys.exit(main())
