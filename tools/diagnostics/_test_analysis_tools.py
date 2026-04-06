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

# ====== 1) 鏂囨湰澶勭悊閾?/api/analysis/text ======
print("\n========== 1) 鏂囨湰澶勭悊閾?==========")
text1 = "楹婚粍姹ょ敱楹婚粍銆佹鏋濄€佹潖浠併€佺敇鑽夌粍鎴愶紝涓绘不澶槼浼ゅ瘨琛ㄥ疄璇併€傞夯榛勮緵娓╁彂姹楄В琛紝妗傛灊鍔╅夯榛勫彂姹楀苟娓╃粡姝㈢棝銆?
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

# ====== 2) 鏂瑰墏缁煎悎鍒嗘瀽 /api/analysis/formula ======
print("\n========== 2) 鏂瑰墏缁煎悎鍒嗘瀽 ==========")
body2 = {
    "perspective": {
        "formula_name": "妗傛灊姹?,
        "herbs": ["妗傛灊", "鑺嶈嵂", "鐢樿崏", "鐢熷", "澶ф灒"],
        "description": "璋冨拰钀ュ崼锛岃В鑲屽彂琛?,
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

# ====== 3) 鐭ヨ瘑鍥捐氨鐢熸垚 (text 鈫?graph) ======
print("\n========== 3) 鐭ヨ瘑鍥捐氨鐢熸垚 ==========")
text3 = "妗傛灊姹や富娌诲お闃充腑椋庯紝澶寸棝鍙戠儹锛屾睏鍑烘伓椋庛€傛鏋濊緵娓╄В鑲岋紝鑺嶈嵂閰稿瘨鏁涢槾銆傜敇鑽夎皟鍜岃鑽紝鐢熷杈涙俯鏁ｅ瘨锛屽ぇ鏋ｇ敇骞宠ˉ鑴俱€?
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

# ====== 4) 鍒嗘瀽宸ュ叿椤甸潰 HTML 妫€鏌?======
print("\n========== 4) 鍒嗘瀽宸ュ叿椤甸潰 ==========")
r = s.get(f"{BASE}/api/analysis/tools", headers=headers)
print(f"  Status: {r.status_code}, Content-Length: {len(r.text)}")
for fn in ["runTextPipeline", "runFormulaAnalysis", "runKgGenerate", "runKgDistill", "openTool"]:
    found = fn in r.text
    print(f"  JS function '{fn}': {'鉁?found' if found else '鉁?MISSING'}")
for btn_id in ["tool-btn-text", "tool-btn-formula", "tool-btn-kg"]:
    found = btn_id in r.text
    print(f"  Button '{btn_id}': {'鉁?found' if found else '鉁?MISSING'}")
