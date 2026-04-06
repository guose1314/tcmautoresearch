"""端到端测试：知识图谱文本分析、持久化、统计、子图、LLM蒸馏。"""
import json
import sys

import requests

BASE = "http://127.0.0.1:18888"

# Login
login = requests.post(f"{BASE}/api/auth/login", json={"username": "hgk1988", "password": "Hgk1989225"})
jwt_token = login.json().get("access_token", "")
headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
print("Auth:", "OK" if jwt_token else "FAIL")

# 1) KG stats before
resp = requests.get(f"{BASE}/api/analysis/kg/stats", headers=headers)
print("KG stats before:", resp.status_code, json.dumps(resp.json(), ensure_ascii=False) if resp.ok else resp.text[:200])

# 2) Text analysis with persistence
text_body = {
    "raw_text": "桂枝汤由桂枝、芍药、甘草、生姜、大枣组成，主治太阳中风证，症见发热、汗出、恶风、脉浮缓。"
                "麻黄汤由麻黄、桂枝、杏仁、甘草组成，主治太阳伤寒证，症见恶寒发热、头身疼痛、无汗而喘。"
                "黄芪性温味甘，归肺脾经，功能补气固表、利水消肿、托毒生肌。"
}
resp2 = requests.post(f"{BASE}/api/analysis/text", json=text_body, headers=headers, timeout=60)
print("Text analysis:", resp2.status_code)
if resp2.ok:
    d = resp2.json()
    acc = d.get("knowledge_accumulation", {})
    print("  Knowledge accumulation:", json.dumps(acc, ensure_ascii=False))
    print("  Entities:", len(d.get("entities", {}).get("items", [])))
    ent_types = set()
    for e in d.get("entities", {}).get("items", []):
        ent_types.add(e.get("type") or e.get("entity_type", ""))
    print("  Entity types:", ent_types)
else:
    print("  Error:", resp2.text[:300])

# 3) KG stats after
resp3 = requests.get(f"{BASE}/api/analysis/kg/stats", headers=headers)
if resp3.ok:
    stats = resp3.json()
    print("KG stats after:", json.dumps(stats, ensure_ascii=False))

# 4) Subgraph endpoints
print("\n--- Subgraph queries ---")
for gt in ["herb_relations", "formula_composition", "syndrome_treatment", "literature_citation"]:
    r = requests.get(f"{BASE}/api/analysis/kg/subgraph?graph_type={gt}", headers=headers)
    if r.ok:
        d = r.json()
        st = d.get("statistics", {})
        print(f"  {gt} ({d.get('label', '')}): {st.get('nodes_count', 0)} nodes, {st.get('edges_count', 0)} edges")
    else:
        print(f"  {gt}: FAIL {r.status_code} {r.text[:200]}")

# 5) Run again to verify accumulation
print("\n--- Second run (accumulation test) ---")
text_body2 = {
    "raw_text": "四逆散由柴胡、芍药、枳实、甘草组成，主治阳郁厥逆证。小柴胡汤由柴胡、黄芩、人参、半夏、甘草、生姜、大枣组成。"
}
resp4 = requests.post(f"{BASE}/api/analysis/text", json=text_body2, headers=headers, timeout=60)
if resp4.ok:
    d = resp4.json()
    acc = d.get("knowledge_accumulation", {})
    print("  Second accumulation:", json.dumps(acc, ensure_ascii=False))

# 6) Final stats
resp5 = requests.get(f"{BASE}/api/analysis/kg/stats", headers=headers)
if resp5.ok:
    print("Final KG stats:", json.dumps(resp5.json(), ensure_ascii=False))

print("\n=== E2E test complete ===")
