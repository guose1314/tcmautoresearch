"""迁移 data/knowledge_graph.db 到 PostgreSQL + Neo4j。

knowledge_graph.db 模式：
  entities(name TEXT PK, type TEXT, metadata TEXT)
  relations(id INT PK, src TEXT, rel_type TEXT, dst TEXT, metadata TEXT)
  src/dst 形如 "type:name"

策略：
  1. 创建占位 document（如果不存在）。
  2. 按 name 对实体去重：PG 已有同 name+type 则复用，否则新建。
  3. 解析 relation 的 src/dst → name → PG entity id；relationship_type
     从 metadata.attributes.relationship_name 推断（默认 RELATED_TO）。
  4. 投影到 Neo4j（标签按 type，关系按 type）。
"""
from __future__ import annotations

import json as _json
import sqlite3
import uuid
from pathlib import Path

import psycopg2
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
KG_DB = ROOT / "data" / "knowledge_graph.db"

PG = dict(host="localhost", port=5432, user="postgres",
          password="Hgk1989225", dbname="tcmautoresearch")

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "Hgk1989225")
NEO4J_DB = "neo4j"

PLACEHOLDER_DOC_TITLE = "knowledge_graph_db_legacy"

TYPE_MAP = {"herb": "herb", "formula": "formula", "syndrome": "syndrome",
            "efficacy": "efficacy", "property": "property",
            "taste": "taste", "meridian": "meridian",
            "symptom": "other", "theory": "other", "generic": "other"}

REL_NAME_MAP = {
    "TREATS": "TREATS", "treats": "TREATS",
    "HAS_EFFICACY": "HAS_EFFICACY", "has_efficacy": "HAS_EFFICACY",
    "CONTAINS": "CONTAINS", "contains": "CONTAINS",
    "SOVEREIGN": "SOVEREIGN", "MINISTER": "MINISTER",
    "ASSISTANT": "ASSISTANT", "ENVOY": "ENVOY",
    "SIMILAR_TO": "SIMILAR_TO",
}


def ensure_placeholder_doc(pg_cur):
    pg_cur.execute(
        "SELECT id FROM documents WHERE source_file = %s",
        (PLACEHOLDER_DOC_TITLE,))
    row = pg_cur.fetchone()
    if row:
        return row[0]
    new_id = str(uuid.uuid4())
    pg_cur.execute(
        "INSERT INTO documents (id, source_file, document_title, "
        "version_metadata_json, processing_timestamp, raw_text_size, "
        "entities_extracted_count, process_status, quality_score, "
        "created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s, %s, NOW(), NOW())",
        (new_id, PLACEHOLDER_DOC_TITLE, PLACEHOLDER_DOC_TITLE,
         _json.dumps({"source": "knowledge_graph_db_legacy"}),
         0, 0, "imported", 0.0),
    )
    return new_id


def get_or_create_rel_type(pg_cur, rel_name: str) -> str:
    pg_cur.execute(
        "SELECT id FROM relationship_types WHERE relationship_type = %s",
        (rel_name,))
    row = pg_cur.fetchone()
    if row:
        return row[0]
    new_id = str(uuid.uuid4())
    pg_cur.execute(
        "INSERT INTO relationship_types (id, relationship_type, "
        "relationship_name, confidence_baseline, created_at) "
        "VALUES (%s, %s, %s, %s, NOW())",
        (new_id, rel_name, rel_name, 0.7))
    return new_id


def parse_endpoint(s: str) -> tuple[str, str]:
    """'type:name' → (type, name)；缺冒号则 type='other'."""
    if ":" in s:
        t, n = s.split(":", 1)
        return t.strip().lower(), n.strip()
    return "other", s.strip()


def main():
    if not KG_DB.exists():
        print(f"[skip] {KG_DB} 不存在")
        return

    sl = sqlite3.connect(str(KG_DB))
    sl.row_factory = sqlite3.Row
    sl_cur = sl.cursor()

    sl_cur.execute("SELECT name, type, metadata FROM entities")
    sl_entities = sl_cur.fetchall()
    sl_cur.execute("SELECT src, rel_type, dst, metadata FROM relations")
    sl_rels = sl_cur.fetchall()
    sl.close()

    print(f"[kg_db] 读取 {len(sl_entities)} 实体 / {len(sl_rels)} 关系")

    pg = psycopg2.connect(**PG)
    pg.autocommit = True
    pg_cur = pg.cursor()

    placeholder_doc = ensure_placeholder_doc(pg_cur)
    print(f"[kg_db] 占位文档 id={placeholder_doc}")

    # 实体：按 (name, type) 去重，先查 PG 已有
    name_to_id: dict[tuple[str, str], str] = {}
    created = 0
    for r in sl_entities:
        name = r["name"]
        raw_type = (r["type"] or "other").lower()
        norm_type = TYPE_MAP.get(raw_type, "other")

        pg_cur.execute(
            "SELECT id FROM entities WHERE name=%s AND type=%s LIMIT 1",
            (name, norm_type),
        )
        row = pg_cur.fetchone()
        if row:
            name_to_id[(name, norm_type)] = row[0]
            continue

        new_id = str(uuid.uuid4())
        meta = r["metadata"] or "{}"
        try:
            meta_obj = _json.loads(meta)
        except Exception:
            meta_obj = {}
        confidence = float(meta_obj.get("confidence", 0.7) or 0.7)
        position = int(meta_obj.get("position", 0) or 0)
        length = int(meta_obj.get("length", len(name)) or len(name))
        meta_obj["raw_type"] = raw_type
        meta_obj["source"] = "knowledge_graph_db"

        try:
            pg_cur.execute(
                "INSERT INTO entities (id, document_id, name, type, "
                "confidence, position, length, alternative_names, "
                "entity_metadata, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()) "
                "ON CONFLICT (id) DO NOTHING",
                (new_id, placeholder_doc, name, norm_type,
                 confidence, position, length, [], _json.dumps(meta_obj)),
            )
            name_to_id[(name, norm_type)] = new_id
            created += 1
        except Exception as e:
            print(f"  [warn] entity {name}: {str(e)[:120]}")

    print(f"[kg_db] 新建 entities {created}，复用 {len(sl_entities) - created}")

    # 关系
    rel_type_cache: dict[str, str] = {}
    rel_inserted = 0
    rel_skipped = 0
    rel_failed = 0
    for r in sl_rels:
        src_t, src_n = parse_endpoint(r["src"])
        dst_t, dst_n = parse_endpoint(r["dst"])
        src_t = TYPE_MAP.get(src_t, "other")
        dst_t = TYPE_MAP.get(dst_t, "other")

        src_id = name_to_id.get((src_n, src_t))
        dst_id = name_to_id.get((dst_n, dst_t))
        if not src_id or not dst_id:
            # 在 PG 直接查（可能是新 batch 已写入的）
            if not src_id:
                pg_cur.execute(
                    "SELECT id FROM entities WHERE name=%s LIMIT 1", (src_n,))
                row = pg_cur.fetchone()
                src_id = row[0] if row else None
            if not dst_id:
                pg_cur.execute(
                    "SELECT id FROM entities WHERE name=%s LIMIT 1", (dst_n,))
                row = pg_cur.fetchone()
                dst_id = row[0] if row else None
        if not src_id or not dst_id:
            rel_skipped += 1
            continue

        # 关系类型
        meta = r["metadata"] or "{}"
        try:
            meta_obj = _json.loads(meta)
        except Exception:
            meta_obj = {}
        attrs = meta_obj.get("attributes", {}) or {}
        rel_name_raw = (attrs.get("relationship_name")
                        or attrs.get("relationship_type")
                        or r["rel_type"]
                        or "RELATED_TO")
        rel_name = REL_NAME_MAP.get(rel_name_raw, rel_name_raw.upper())

        rt_id = rel_type_cache.get(rel_name)
        if not rt_id:
            rt_id = get_or_create_rel_type(pg_cur, rel_name)
            rel_type_cache[rel_name] = rt_id

        try:
            pg_cur.execute(
                "INSERT INTO entity_relationships (id, source_entity_id, "
                "target_entity_id, relationship_type_id, confidence, "
                "created_by_module, relationship_metadata, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW()) "
                "ON CONFLICT (id) DO NOTHING",
                (str(uuid.uuid4()), src_id, dst_id, rt_id,
                 float(attrs.get("confidence", 0.7) or 0.7),
                 "kg_db_migration", _json.dumps(meta_obj)),
            )
            rel_inserted += 1
        except Exception as e:
            rel_failed += 1
            if rel_failed <= 3:
                print(f"  [warn] rel {src_n}->{dst_n}: {str(e)[:120]}")

    print(f"[kg_db] 关系：新建 {rel_inserted}，跳过 {rel_skipped}，失败 {rel_failed}")

    # 投影到 Neo4j
    print("[neo4j] 全量重新投影...")
    drv = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with drv.session(database=NEO4J_DB) as s:
        # 投影本次新建的实体
        if name_to_id:
            ids = list(name_to_id.values())
            pg_cur.execute(
                "SELECT id::text, name, type FROM entities "
                "WHERE id::text = ANY(%s)", (ids,))
            ents = pg_cur.fetchall()
            by_label: dict[str, list[dict]] = {}
            for eid, name, typ in ents:
                label = (typ or "Entity").replace("_", "")
                if not label.isalnum():
                    label = "Entity"
                label = label[:1].upper() + label[1:]
                by_label.setdefault(label, []).append(
                    {"id": eid, "name": name})
            for label, rows in by_label.items():
                s.run(
                    f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) "
                    f"SET n.name = row.name", rows=rows)
                print(f"  :{label} 合并 {len(rows)}")

        # 投影本次新建关系
        pg_cur.execute(
            "SELECT er.source_entity_id::text, er.target_entity_id::text, "
            "rt.relationship_type FROM entity_relationships er "
            "JOIN relationship_types rt ON er.relationship_type_id = rt.id "
            "WHERE er.created_by_module = 'kg_db_migration'")
        rel_rows = pg_cur.fetchall()
        by_rt: dict[str, list[dict]] = {}
        for src, dst, rt in rel_rows:
            rt_clean = "".join(ch if ch.isalnum() or ch == "_"
                               else "_" for ch in (rt or "RELATED_TO").upper())
            by_rt.setdefault(rt_clean, []).append({"src": src, "dst": dst})
        for rt, rows in by_rt.items():
            s.run(
                f"UNWIND $rows AS row "
                f"MATCH (a {{id: row.src}}), (b {{id: row.dst}}) "
                f"MERGE (a)-[:{rt}]->(b)", rows=rows)
            print(f"  :{rt} 合并 {len(rows)}")

        n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        e = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        print(f"[neo4j] 总计 {n} 节点 / {e} 边")

    drv.close()
    pg.close()


if __name__ == "__main__":
    main()
