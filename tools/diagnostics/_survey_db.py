"""Quick survey of research data in main DB."""
import json
import sqlite3

db = sqlite3.connect("data/development/tcmautoresearch.db")
cur = db.cursor()

tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()]
print("Tables:", tables)

for t in ["research_sessions", "phase_executions", "research_artifacts",
          "research_results", "documents", "entities", "entity_relationships"]:
    if t in tables:
        cnt = cur.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {cnt}")
    else:
        print(f"  {t}: N/A")

if "research_sessions" in tables:
    rows = cur.execute(
        "SELECT cycle_name, status, current_phase, created_at "
        "FROM research_sessions ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    print("\nRecent sessions:")
    for r in rows:
        print(f"  {r}")

if "research_results" in tables:
    rows = cur.execute(
        "SELECT cycle_id, status, created_at "
        "FROM research_results ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    print("\nRecent results:")
    for r in rows:
        print(f"  {r}")

# Also check output/research_results.db
try:
    db2 = sqlite3.connect("output/research_results.db")
    cur2 = db2.cursor()
    t2 = [r[0] for r in cur2.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    print("\noutput/research_results.db tables:", t2)
    for t in t2:
        cnt = cur2.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {cnt}")
    if "research_results" in t2:
        rows = cur2.execute(
            "SELECT cycle_id, status, created_at "
            "FROM research_results ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        print("\nOutput DB recent results:")
        for r in rows:
            print(f"  {r}")
    db2.close()
except Exception as e:
    print(f"\noutput/research_results.db error: {e}")

db.close()
