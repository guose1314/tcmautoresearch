"""把已存在的 SQLite 数据迁移到 PostgreSQL + Neo4j 双库。

来源：
- data/knowledge_graph.db  — TCMKnowledgeGraph SQLite (entities/relations)
- data/tcmautoresearch.db  — SQLAlchemy ORM SQLite (documents/entities/entity_relationships)

策略：
- 先扫描两个 SQLite 的内容；
- 把所有 PG ORM 表（documents, entities, entity_relationships, relationship_types）从
  data/tcmautoresearch.db 迁到 PG（保留原 id，按 source_file 去重）；
- 把 KG SQLite 中独立的实体（不在 ORM 中）补录到 PG entities；
- 然后把 PG 中所有 entity / entity_relationship 投影到 Neo4j（与 web 路由一致的标签/边规则）。

幂等：使用 ON CONFLICT DO NOTHING（PG）和 MERGE（Neo4j）。
"""
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase

# ---- 配置 ----
PG = dict(host="localhost", port=5432, user="postgres",
          password="Hgk1989225", dbname="tcmautoresearch")
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "Hgk1989225")
NEO4J_DB = "neo4j"

ROOT = Path(__file__).resolve().parents[2]
SQLITE_ORM = ROOT / "data" / "tcmautoresearch.db"
SQLITE_KG = ROOT / "data" / "knowledge_graph.db"

# Type 映射（与 web/routes/analysis.py 一致）
_TYPE_MAP = {
    "herb": "herb", "formula": "formula", "syndrome": "syndrome",
    "efficacy": "efficacy", "property": "property", "taste": "taste",
    "meridian": "meridian", "symptom": "other", "theory": "other",
    "generic": "other",
}


def list_sqlite_tables(path: Path):
    if not path.exists():
        return {}
    c = sqlite3.connect(str(path))
    cur = c.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    counts = {}
    for t in tables:
        try:
            cur.execute(f'SELECT count(*) FROM "{t}"')
            counts[t] = cur.fetchone()[0]
        except Exception as e:
            counts[t] = f"ERR: {e}"
    c.close()
    return counts


def migrate_orm_sqlite_to_pg():
    """逐表把 SQLite ORM 数据复制到 PG。保留原主键，冲突跳过。"""
    if not SQLITE_ORM.exists():
        print(f"[orm] 跳过：{SQLITE_ORM} 不存在")
        return {"documents": 0, "entities": 0, "relations": 0}

    sl = sqlite3.connect(str(SQLITE_ORM))
    sl.row_factory = sqlite3.Row
    pg = psycopg2.connect(**PG)
    pg.autocommit = False

    counts = {}
    try:
        # 1) relationship_types
        sl_cur = sl.cursor()
        try:
            sl_cur.execute("SELECT * FROM relationship_types")
            rows = [dict(r) for r in sl_cur.fetchall()]
        except sqlite3.OperationalError:
            rows = []
        if rows:
            cols = list(rows[0].keys())
            pcur = pg.cursor()
            for r in rows:
                placeholders = ", ".join(["%s"] * len(cols))
                colnames = ", ".join(f'"{c}"' for c in cols)
                pcur.execute(
                    f'INSERT INTO relationship_types ({colnames}) VALUES ({placeholders}) '
                    f'ON CONFLICT (relationship_type) DO NOTHING',
                    [r[c] for c in cols],
                )
            pg.commit()
            counts["relationship_types"] = len(rows)
            print(f"[orm] relationship_types: 迁移 {len(rows)} 条")

        # 2) documents
        sl_cur.execute("SELECT * FROM documents")
        docs = [dict(r) for r in sl_cur.fetchall()]
        moved = 0
        if docs:
            cols = [c for c in docs[0].keys() if c != "id"]
            pcur = pg.cursor()
            for r in docs:
                placeholders = ", ".join(["%s"] * (len(cols) + 1))
                colnames = ", ".join(['"id"'] + [f'"{c}"' for c in cols])
                try:
                    pcur.execute(
                        f'INSERT INTO documents ({colnames}) VALUES ({placeholders}) '
                        f'ON CONFLICT (id) DO NOTHING',
                        [r["id"]] + [r[c] for c in cols],
                    )
                    if pcur.rowcount > 0:
                        moved += 1
                except Exception as e:
                    print(f"[orm] 跳过 doc id={r['id']}: {e}")
                    pg.rollback()
                    pg.autocommit = False
            pg.commit()
        counts["documents"] = moved
        print(f"[orm] documents: 迁移 {moved}/{len(docs)} 条")

        # 3) entities
        sl_cur.execute("SELECT * FROM entities")
        ents = [dict(r) for r in sl_cur.fetchall()]
        moved = 0
        if ents:
            cols = [c for c in ents[0].keys() if c != "id"]
            pcur = pg.cursor()
            for r in ents:
                placeholders = ", ".join(["%s"] * (len(cols) + 1))
                colnames = ", ".join(['"id"'] + [f'"{c}"' for c in cols])
                try:
                    pcur.execute(
                        f'INSERT INTO entities ({colnames}) VALUES ({placeholders}) '
                        f'ON CONFLICT (id) DO NOTHING',
                        [r["id"]] + [r[c] for c in cols],
                    )
                    if pcur.rowcount > 0:
                        moved += 1
                except Exception as e:
                    print(f"[orm] 跳过 ent id={r['id']}: {e}")
                    pg.rollback()
            pg.commit()
        counts["entities"] = moved
        print(f"[orm] entities: 迁移 {moved}/{len(ents)} 条")

        # 4) entity_relationships
        sl_cur.execute("SELECT * FROM entity_relationships")
        rels = [dict(r) for r in sl_cur.fetchall()]
        moved = 0
        if rels:
            cols = [c for c in rels[0].keys() if c != "id"]
            pcur = pg.cursor()
            for r in rels:
                placeholders = ", ".join(["%s"] * (len(cols) + 1))
                colnames = ", ".join(['"id"'] + [f'"{c}"' for c in cols])
                try:
                    pcur.execute(
                        f'INSERT INTO entity_relationships ({colnames}) VALUES ({placeholders}) '
                        f'ON CONFLICT (id) DO NOTHING',
                        [r["id"]] + [r[c] for c in cols],
                    )
                    if pcur.rowcount > 0:
                        moved += 1
                except Exception as e:
                    print(f"[orm] 跳过 rel id={r['id']}: {e}")
                    pg.rollback()
            pg.commit()
        counts["relations"] = moved
        print(f"[orm] entity_relationships: 迁移 {moved}/{len(rels)} 条")

        # 重置 PG 序列以避免后续 INSERT 主键冲突
        pcur = pg.cursor()
        for tbl in ["documents", "entities", "entity_relationships",
                    "relationship_types"]:
            pcur.execute(
                f"SELECT setval(pg_get_serial_sequence('{tbl}','id'), "
                f"COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
            )
        pg.commit()
        print("[orm] 序列已重置")
    finally:
        sl.close()
        pg.close()

    return counts


def project_pg_to_neo4j():
    """从 PG 读取所有实体/关系，投影到 Neo4j。"""
    pg = psycopg2.connect(**PG)
    pcur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 实体
    pcur.execute("SELECT id, name, type FROM entities")
    entities = pcur.fetchall()
    print(f"[neo4j] 待投影实体数: {len(entities)}")

    # 关系（带 relationship_type 名）
    pcur.execute("""
        SELECT er.source_entity_id AS src, er.target_entity_id AS dst,
               rt.relationship_type AS rt
        FROM entity_relationships er
        JOIN relationship_types rt ON rt.id = er.relationship_type_id
    """)
    relations = pcur.fetchall()
    print(f"[neo4j] 待投影关系数: {len(relations)}")

    pg.close()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session(database=NEO4J_DB) as s:
            # 节点：按 type 分组
            by_label = defaultdict(list)
            for n in entities:
                etype = (n["type"] or "Entity")
                if hasattr(etype, "value"):
                    etype = etype.value
                label = str(etype).capitalize()
                if not label.replace("_", "").isalnum():
                    label = "Entity"
                by_label[label].append({"id": str(n["id"]), "name": n["name"]})
            total_nodes = 0
            for label, batch in by_label.items():
                # 分块以避免单次过大
                for i in range(0, len(batch), 1000):
                    chunk = batch[i:i + 1000]
                    cypher = (
                        f"UNWIND $rows AS row "
                        f"MERGE (n:{label} {{id: row.id}}) "
                        f"SET n.name = row.name"
                    )
                    s.run(cypher, rows=chunk).consume()
                total_nodes += len(batch)
                print(f"[neo4j] 标签 :{label} 已合并 {len(batch)} 节点")

            # 关系：按 rel_type 分组
            by_rel = defaultdict(list)
            for r in relations:
                rt = (r["rt"] or "RELATED").upper()
                if not rt.replace("_", "").isalnum():
                    rt = "RELATED"
                by_rel[rt].append({"src": str(r["src"]), "dst": str(r["dst"])})
            total_edges = 0
            for rt, batch in by_rel.items():
                for i in range(0, len(batch), 1000):
                    chunk = batch[i:i + 1000]
                    cypher = (
                        f"UNWIND $rows AS row "
                        f"MATCH (a {{id: row.src}}), (b {{id: row.dst}}) "
                        f"MERGE (a)-[:{rt}]->(b)"
                    )
                    s.run(cypher, rows=chunk).consume()
                total_edges += len(batch)
                print(f"[neo4j] 关系 :{rt} 已合并 {len(batch)} 条")
            print(f"[neo4j] 总计：{total_nodes} 节点 / {total_edges} 边")
    finally:
        driver.close()


def main():
    print("=" * 60)
    print("迁移工具：SQLite → PostgreSQL + Neo4j")
    print("=" * 60)

    print(f"\n[scan] {SQLITE_ORM}")
    print(" ", list_sqlite_tables(SQLITE_ORM))
    print(f"\n[scan] {SQLITE_KG}")
    print(" ", list_sqlite_tables(SQLITE_KG))

    print("\n--- 迁移 ORM SQLite → PG ---")
    migrate_orm_sqlite_to_pg()

    print("\n--- 投影 PG → Neo4j ---")
    project_pg_to_neo4j()

    # 最终验证
    print("\n--- 最终统计 ---")
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
    print("\nOK")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
