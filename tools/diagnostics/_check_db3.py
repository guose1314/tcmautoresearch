# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect("data/development/tcmautoresearch.db")
print("Latest docs:")
for r in conn.execute("SELECT source_file, entities_extracted_count, notes FROM documents ORDER BY created_at DESC LIMIT 5").fetchall():
    print(f"  {r}")
print()
print("Entities (herb):")
for r in conn.execute("SELECT name, type FROM entities WHERE type='herb' ORDER BY rowid DESC LIMIT 10").fetchall():
    print(f"  {r}")
print()
print("Relations:")
for r in conn.execute("""
    SELECT e1.name, rt.relationship_type, e2.name, er.confidence
    FROM entity_relationships er
    JOIN entities e1 ON er.source_entity_id = e1.id
    JOIN entities e2 ON er.target_entity_id = e2.id
    JOIN relationship_types rt ON er.relationship_type_id = rt.id
    ORDER BY er.rowid DESC LIMIT 10
""").fetchall():
    print(f"  {r}")
conn.close()
