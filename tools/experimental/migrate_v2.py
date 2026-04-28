"""稳健版迁移：autocommit + ON CONFLICT + 每行独立事务。

来源：data/tcmautoresearch.db（ORM SQLite，UUID 主键）
目标：PG tcmautoresearch + Neo4j neo4j
"""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase

PG = dict(host="localhost", port=5432, user="postgres",
          password="Hgk1989225", dbname="tcmautoresearch")
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "Hgk1989225")
NEO4J_DB = "neo4j"

ROOT = Path(__file__).resolve().parents[2]
SQLITE_ORM = ROOT / "data" / "tcmautoresearch.db"


def copy_table(sl_path, table, pg_conn, conflict_col=None,
               skip_cols=None):
    """通用单表迁移。conflict_col 为 ON CONFLICT 列名（不传则按 id）。

    自动处理 PG ARRAY 列（SQLite 存为 JSON 字符串如 '[]'）。
    """
    import json as _json
    if not sl_path.exists():
        return 0, 0
    skip_cols = set(skip_cols or [])
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

    cols = [c for c in rows[0].keys()
            if c in pg_col_types and c not in skip_cols]
    if not cols:
        sl.close()
        return 0, 0

    placeholders = ", ".join(["%s"] * len(cols))
    colnames = ", ".join(f'"{c}"' for c in cols)
    conflict = conflict_col or "id"
    sql = (
        f'INSERT INTO {table} ({colnames}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict}) DO NOTHING'
    )
    moved = 0
    failed = 0
    for r in rows:
        vals = []
        for c in cols:
            v = r[c]
            dtype = pg_col_types[c]
            # JSON 字符串 → Python list（用于 ARRAY 列）
            if dtype == "ARRAY" and isinstance(v, str):
                try:
                    parsed = _json.loads(v)
                    if not isinstance(parsed, list):
                        parsed = []
                    v = parsed
                except Exception:
                    v = []
            elif dtype == "ARRAY" and v is None:
                v = []
            vals.append(v)
        try:
            pg_cur.execute(sql, vals)
            if pg_cur.rowcount > 0:
                moved += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  [warn] {table} 跳过: {str(e)[:120]}")
    sl.close()
    return moved, failed


def migrate():
    pg = psycopg2.connect(**PG)
    pg.autocommit = True

    print("\n--- 1. relationship_types ---")
    m, f = copy_table(SQLITE_ORM, "relationship_types", pg,
                      conflict_col="relationship_type")
    print(f"  迁移 {m} 条，失败 {f}")

    print("\n--- 2. documents ---")
    m, f = copy_table(SQLITE_ORM, "documents", pg)
    print(f"  迁移 {m} 条，失败 {f}")

    print("\n--- 3. entities ---")
    m, f = copy_table(SQLITE_ORM, "entities", pg)
    print(f"  迁移 {m} 条，失败 {f}")

    print("\n--- 4. entity_relationships (with rt_id remap) ---")
    m, f = migrate_relationships_with_remap(pg)
    print(f"  迁移 {m} 条，失败 {f}")

    pg.close()


def migrate_relationships_with_remap(pg_conn):
    """迁移 entity_relationships，按 relationship_type 名重映射 PG 的 rt id。"""
    sl = sqlite3.connect(str(SQLITE_ORM))
    sl.row_factory = sqlite3.Row
    sl_cur = sl.cursor()

    # SQLite rt_id → relationship_type 名
    sl_cur.execute("SELECT id, relationship_type FROM relationship_types")
    sl_rt = {r["id"]: r["relationship_type"] for r in sl_cur.fetchall()}

    # PG relationship_type 名 → PG rt_id
    pg_cur = pg_conn.cursor()
    pg_cur.execute("SELECT id, relationship_type FROM relationship_types")
    pg_rt_by_name = {r[1]: r[0] for r in pg_cur.fetchall()}

    sl_to_pg_rt = {}
    for sl_id, name in sl_rt.items():
        pg_id = pg_rt_by_name.get(name)
        if pg_id is None:
            # 在 PG 中创建该 rt
            pg_cur.execute(
                "INSERT INTO relationship_types (id, relationship_type) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING id",
                (sl_id, name),
            )
            row = pg_cur.fetchone()
            pg_id = row[0] if row else sl_id
        sl_to_pg_rt[sl_id] = pg_id

    print(f"  rt 映射: SQLite {len(sl_rt)} → PG {len(sl_to_pg_rt)}")

    # 迁移
    sl_cur.execute("SELECT * FROM entity_relationships")
    rows = sl_cur.fetchall()
    moved = 0
    failed = 0
    cols = ["id", "source_entity_id", "target_entity_id",
            "relationship_type_id", "confidence", "created_by_module",
            "evidence", "relationship_metadata", "created_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    colnames = ", ".join(f'"{c}"' for c in cols)
    sql = (
        f'INSERT INTO entity_relationships ({colnames}) VALUES ({placeholders}) '
        f'ON CONFLICT (id) DO NOTHING'
    )
    for r in rows:
        rt_id = sl_to_pg_rt.get(r["relationship_type_id"],
                                r["relationship_type_id"])
        vals = [r["id"], r["source_entity_id"], r["target_entity_id"],
                rt_id, r["confidence"], r["created_by_module"],
                r["evidence"], r["relationship_metadata"], r["created_at"]]
        try:
            pg_cur.execute(sql, vals)
            if pg_cur.rowcount > 0:
                moved += 1
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  [warn] rel 跳过: {str(e)[:120]}")
    sl.close()
    return moved, failed


def project_pg_to_neo4j():
    pg = psycopg2.connect(**PG)
    pcur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    pcur.execute("SELECT id, name, type FROM entities")
    entities = pcur.fetchall()
    print(f"\n[neo4j] 待投影实体: {len(entities)}")

    pcur.execute("""
        SELECT er.source_entity_id AS src, er.target_entity_id AS dst,
               rt.relationship_type AS rt
        FROM entity_relationships er
        JOIN relationship_types rt ON rt.id = er.relationship_type_id
    """)
    relations = pcur.fetchall()
    print(f"[neo4j] 待投影关系: {len(relations)}")
    pg.close()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session(database=NEO4J_DB) as s:
        by_label = defaultdict(list)
        for n in entities:
            etype = n["type"]
            if hasattr(etype, "value"):
                etype = etype.value
            label = str(etype or "Entity").capitalize()
            if not label.replace("_", "").isalnum():
                label = "Entity"
            by_label[label].append({"id": str(n["id"]), "name": n["name"]})
        total_n = 0
        for label, batch in by_label.items():
            for i in range(0, len(batch), 1000):
                chunk = batch[i:i + 1000]
                s.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label} {{id: row.id}}) "
                    f"SET n.name = row.name",
                    rows=chunk,
                ).consume()
            total_n += len(batch)
            print(f"  :{label} 合并 {len(batch)} 节点")

        by_rel = defaultdict(list)
        for r in relations:
            rt = (r["rt"] or "RELATED").upper()
            if not rt.replace("_", "").isalnum():
                rt = "RELATED"
            by_rel[rt].append({"src": str(r["src"]), "dst": str(r["dst"])})
        total_e = 0
        for rt, batch in by_rel.items():
            for i in range(0, len(batch), 1000):
                chunk = batch[i:i + 1000]
                s.run(
                    f"UNWIND $rows AS row "
                    f"MATCH (a {{id: row.src}}), (b {{id: row.dst}}) "
                    f"MERGE (a)-[:{rt}]->(b)",
                    rows=chunk,
                ).consume()
            total_e += len(batch)
            print(f"  :{rt} 合并 {len(batch)} 边")
        print(f"[neo4j] 总计 {total_n} 节点 / {total_e} 边")
    driver.close()


def final_stats():
    print("\n--- 最终 ---")
    pg = psycopg2.connect(**PG)
    cur = pg.cursor()
    for t in ["documents", "entities", "entity_relationships",
              "relationship_types"]:
        cur.execute(f"SELECT count(*) FROM {t}")
        print(f"  PG.{t}: {cur.fetchone()[0]}")
    pg.close()
    d = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with d.session(database=NEO4J_DB) as s:
        n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        e = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        print(f"  Neo4j: {n} 节点 / {e} 边")
    d.close()


if __name__ == "__main__":
    try:
        migrate()
        project_pg_to_neo4j()
        final_stats()
        print("\nOK")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
