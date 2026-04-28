"""迁移剩余 ORM 表 (research_sessions/phase_executions/research_results/
research_artifacts/research_learning_feedback) 从 SQLite 到 PG。
注意 FK 顺序：research_sessions → phase_executions → research_results
                                 → research_artifacts → research_learning_feedback
"""
from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[2]
SQLITE_ORM = ROOT / "data" / "tcmautoresearch.db"

PG = dict(host="localhost", port=5432, user="postgres",
          password="Hgk1989225", dbname="tcmautoresearch")


def copy_table(sl_path, table, pg_conn, conflict_col="id"):
    if not sl_path.exists():
        return 0, 0
    sl = sqlite3.connect(str(sl_path))
    sl.row_factory = sqlite3.Row
    sl_cur = sl.cursor()
    try:
        sl_cur.execute(f'SELECT * FROM "{table}"')
        rows = sl_cur.fetchall()
    except sqlite3.OperationalError:
        sl.close()
        return 0, 0
    if not rows:
        sl.close()
        return 0, 0

    pg_cur = pg_conn.cursor()
    pg_cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name=%s AND table_schema='public'",
        (table,),
    )
    pg_col_types = {r[0]: r[1] for r in pg_cur.fetchall()}
    if not pg_col_types:
        sl.close()
        return 0, 0

    cols = [c for c in rows[0].keys() if c in pg_col_types]
    placeholders = ", ".join(["%s"] * len(cols))
    colnames = ", ".join(f'"{c}"' for c in cols)
    sql = (
        f'INSERT INTO {table} ({colnames}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict_col}) DO NOTHING'
    )
    moved = 0
    failed = 0
    for r in rows:
        vals = []
        for c in cols:
            v = r[c]
            dtype = pg_col_types[c]
            if dtype == "ARRAY":
                if isinstance(v, str):
                    try:
                        v = _json.loads(v)
                        if not isinstance(v, list):
                            v = []
                    except Exception:
                        v = []
                elif v is None:
                    v = []
            elif dtype == "boolean" and isinstance(v, int):
                v = bool(v)
            vals.append(v)
        try:
            pg_cur.execute(sql, vals)
            moved += 1 if pg_cur.rowcount > 0 else 0
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  [warn] {table}: {str(e)[:140]}")
    sl.close()
    return moved, failed


def main():
    pg = psycopg2.connect(**PG)
    pg.autocommit = True

    plan = [
        ("research_sessions", "id"),
        ("phase_executions", "id"),
        ("research_results", "cycle_id"),
        ("research_artifacts", "id"),
        ("research_learning_feedback", "id"),
    ]
    for tbl, pk in plan:
        m, f = copy_table(SQLITE_ORM, tbl, pg, conflict_col=pk)
        print(f"{tbl:35s} migrated={m} failed={f}")

    cur = pg.cursor()
    for t in ("research_sessions", "phase_executions", "research_results",
              "research_artifacts", "research_learning_feedback"):
        cur.execute(f'SELECT count(*) FROM "{t}"')
        print(f"  PG.{t} = {cur.fetchone()[0]}")
    pg.close()


if __name__ == "__main__":
    main()
