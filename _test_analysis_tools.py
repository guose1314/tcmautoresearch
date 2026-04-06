# -*- coding: utf-8 -*-
"""Test all three analysis tools + ORM persistence."""
import json
import sqlite3
import time

import requests

BASE = "http://127.0.0.1:18888"
DB = "data/development/tcmautoresearch.db"
s = requests.Session()

# Login
r = s.post(f"{BASE}/api/auth/login", json={"username": "hgk1988", "password": "Hgk1989225"})
assert r.status_code == 200, f"Login failed: {r.text}"
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# DB before
conn = sqlite3.connect(DB)
doc_before = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
ent_before = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
rel_before = conn.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0]
print(f"[DB BEFORE] docs={doc_before}, entities={ent_before}, relations={rel_before}")
conn.close()

# ====== 1) 文本处理链 /api/analysis/text ======
print("\n========== 1) 文本处理链 ==========")
text1 = "麻黄汤由麻黄、桂枝、杏仁、甘草组成，主治太阳伤寒表实证。麻黄辛温发汗解表，桂枝助麻黄发汗并温经止痛。"
t0 = time.time()
r = s.post(f"{BASE}/api/analysis/text", json={"raw_text": text1}, headers=headers, timeout=30)
print(f"  Status: {r.status_code}, Time: {time.time()-t0:.1f}s")
if r.status_code == 200:
    d = r.json()
    ent = (d.get("entities") or {}).get("items", [])
    graph_edges = ((d.get("semantic_graph") or {}).get("graph") or {}).get("edges", [])
    acc = d.get("knowledge_accumulation", {})
    print(f"  Entities: {len(ent)}, Edges: {len(graph_edges)}")
    print(f"  Accumulation: {json.dumps(acc, ensure_ascii=False)}")
    print(f"  Entity types: {set(e.get('type','?') for e in ent)}")
else:
    print(f"  ERROR: {r.text[:300]}")

# ====== 2) 方剂综合分析 /api/analysis/formula ======
print("\n========== 2) 方剂综合分析 ==========")
body2 = {
    "perspective": {
        "formula_name": "桂枝汤",
        "herbs": ["桂枝", "芍药", "甘草", "生姜", "大枣"],
        "description": "调和营卫，解肌发表",
    }
}
t0 = time.time()
r = s.post(f"{BASE}/api/analysis/formula", json=body2, headers=headers, timeout=30)
print(f"  Status: {r.status_code}, Time: {time.time()-t0:.1f}s")
if r.status_code == 200:
    d = r.json()
    print(f"  message: {d.get('message')}")
    result_keys = list((d.get("result") or {}).keys()) if isinstance(d.get("result"), dict) else str(d.get("result"))[:200]
    print(f"  result keys: {result_keys}")
else:
    print(f"  ERROR: {r.text[:300]}")

# ====== 3) 知识图谱生成 (text → graph) ======
print("\n========== 3) 知识图谱生成 ==========")
text3 = "桂枝汤主治太阳中风，头痛发热，汗出恶风。桂枝辛温解肌，芍药酸寒敛阴。甘草调和诸药，生姜辛温散寒，大枣甘平补脾。"
t0 = time.time()
r = s.post(f"{BASE}/api/analysis/text", json={"raw_text": text3}, headers=headers, timeout=30)
print(f"  Status: {r.status_code}, Time: {time.time()-t0:.1f}s")
if r.status_code == 200:
    d = r.json()
    graph = (d.get("semantic_graph") or {}).get("graph") or {}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    acc = d.get("knowledge_accumulation", {})
    print(f"  Nodes: {len(nodes)}, Edges: {len(edges)}")
    print(f"  Accumulation: {json.dumps(acc, ensure_ascii=False)}")
else:
    print(f"  ERROR: {r.text[:300]}")

# DB after
conn = sqlite3.connect(DB)
doc_after = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
ent_after = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
rel_after = conn.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0]
print(f"\n[DB AFTER] docs={doc_after} (+{doc_after-doc_before}), entities={ent_after} (+{ent_after-ent_before}), relations={rel_after} (+{rel_after-rel_before})")
conn.close()

# ====== 4) 分析工具页面 HTML 检查 ======
print("\n========== 4) 分析工具页面 ==========")
r = s.get(f"{BASE}/api/analysis/tools", headers=headers)
print(f"  Status: {r.status_code}, Content-Length: {len(r.text)}")
for fn in ["runTextPipeline", "runFormulaAnalysis", "runKgGenerate", "runKgDistill", "openTool"]:
    found = fn in r.text
    print(f"  JS function '{fn}': {'✓ found' if found else '✗ MISSING'}")
for btn_id in ["tool-btn-text", "tool-btn-formula", "tool-btn-kg"]:
    found = btn_id in r.text
    print(f"  Button '{btn_id}': {'✓ found' if found else '✗ MISSING'}")
