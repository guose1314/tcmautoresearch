"""幂等地把 SQLite documents 表对齐到 ORM 模型。

背景：data/tcmautoresearch.db 中 documents 表只保留了早期 11 列，
而 ORM 模型已扩展到 24 列。因 SQLite 不支持 ALTER COLUMN，本脚本仅
按列名差集追加缺失列与对应索引，可重复执行。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(r"C:\Users\hgk\tcmautoresearch\data\tcmautoresearch.db")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
