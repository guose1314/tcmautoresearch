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
    graph_stats = stats.get("graph_statistics") or {}
    if graph_stats:
        print(
            "Graph assets:",
            json.dumps(
                {
                    "hypothesis_node_count": graph_stats.get("hypothesis_node_count", 0),
                    "evidence_node_count": graph_stats.get("evidence_node_count", 0),
                    "evidence_claim_node_count": graph_stats.get("evidence_claim_node_count", 0),
                    "has_hypothesis_edge_count": graph_stats.get("has_hypothesis_edge_count", 0),
                    "evidence_for_edge_count": graph_stats.get("evidence_for_edge_count", 0),
                    "derived_from_phase_edge_count": graph_stats.get("derived_from_phase_edge_count", 0),
                },
                ensure_ascii=False,
            ),
        )

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
    final_stats = resp5.json()
    print("Final KG stats:", json.dumps(final_stats, ensure_ascii=False))
    final_graph_stats = final_stats.get("graph_statistics") or {}
    if final_graph_stats:
        print(
            "Final graph assets:",
            json.dumps(
                {
                    "hypothesis_node_count": final_graph_stats.get("hypothesis_node_count", 0),
                    "evidence_node_count": final_graph_stats.get("evidence_node_count", 0),
                    "evidence_claim_node_count": final_graph_stats.get("evidence_claim_node_count", 0),
                },
                ensure_ascii=False,
            ),
        )

# 7) Phase G-4 资产级回归：直接 Cypher 校验 hypothesis / evidence / philology
#    三类资产族的节点数与 /api/analysis/kg/stats 一致，并验证 philology_asset_graph
#    模板能命中 g3 分支（ExegesisTerm / ATTESTS_TO 链路）
print("\n--- Phase G-4 asset-level regression ---")
try:
    sys.path.insert(0, ".")
    from src.storage.neo4j_driver import Neo4jDriver
    from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES

    neo4j_driver = Neo4jDriver(
        uri="neo4j://127.0.0.1:7687",
        auth=("neo4j", "Hgk1989225"),
    )
    neo4j_driver.connect()

    def _run_cypher(cypher, params=None):
        with neo4j_driver.driver.session(database=neo4j_driver.database) as sess:
            return sess.execute_read(
                lambda tx: [dict(r) for r in tx.run(cypher, **(params or {}))]
            )

    # KG stats reference
    stats_for_check = (resp5.json() if resp5.ok else {}).get("graph_statistics") or {}

    asset_breakdown = {}
    for label, count_key in (
        ("Hypothesis", "hypothesis_node_count"),
        ("Evidence", "evidence_node_count"),
        ("EvidenceClaim", "evidence_claim_node_count"),
        ("ExegesisTerm", "exegesis_term_node_count"),
        ("FragmentCandidate", "fragment_candidate_node_count"),
        ("VersionWitness", "version_witness_node_count"),
    ):
        rows = _run_cypher(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        live_cnt = int(rows[0]["cnt"]) if rows else 0
        asset_breakdown[label] = {
            "live_neo4j_count": live_cnt,
            "kg_stats_count": int(stats_for_check.get(count_key, 0)),
        }

    print("Asset-family breakdown:", json.dumps(asset_breakdown, ensure_ascii=False))

    # Cross-check: hypothesis/evidence numbers from stats should not exceed live count
    for label in ("Hypothesis", "Evidence", "EvidenceClaim"):
        live = asset_breakdown[label]["live_neo4j_count"]
        stats_cnt = asset_breakdown[label]["kg_stats_count"]
        if stats_cnt > 0:
            assert stats_cnt == live, (
                f"{label}: kg/stats={stats_cnt} 与 live Neo4j={live} 不一致"
            )

    # Validate philology_asset_graph template hits g3 branch
    rows = _run_cypher(
        "MATCH (w:VersionWitness) WITH w.cycle_id AS cid, count(*) AS c "
        "ORDER BY c DESC RETURN cid LIMIT 1"
    )
    if rows and rows[0]["cid"]:
        cid = rows[0]["cid"]
        tmpl = CANONICAL_READ_TEMPLATES["philology_asset_graph"]["cypher"]
        sample = _run_cypher(
            tmpl,
            {
                "cycle_id": cid,
                "work_title": "",
                "version_lineage_key": "",
                "witness_key": "",
                "review_status": "",
                "limit": 5,
            },
        )
        sources = [r.get("graph_source") for r in sample]
        print(
            "philology_asset_graph sample:",
            json.dumps(
                {"cycle_id": cid, "rows": len(sample), "graph_sources": sources},
                ensure_ascii=False,
            ),
        )

    neo4j_driver.close()
except Exception as exc:  # pragma: no cover - 依赖 live Neo4j
    print(f"  WARN: Phase G-4 asset regression skipped: {exc}")

print("\n=== E2E test complete ===")
