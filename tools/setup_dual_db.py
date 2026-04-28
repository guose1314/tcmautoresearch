"""创建 PostgreSQL tcmautoresearch 数据库；验证 Neo4j 可写。"""
import sys

import psycopg2
from neo4j import GraphDatabase

PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASS = "Hgk1989225"
PG_DB = "tcmautoresearch"

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "Hgk1989225"


def setup_pg():
    c = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                         password=PG_PASS, dbname="postgres")
    c.autocommit = True
    cur = c.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (PG_DB,))
    if cur.fetchone():
        print(f"[PG] 数据库 {PG_DB} 已存在")
    else:
        cur.execute(f'CREATE DATABASE "{PG_DB}"')
        print(f"[PG] 已创建数据库 {PG_DB}")
    cur.close()
    c.close()
    # 验证可连
    c2 = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                          password=PG_PASS, dbname=PG_DB)
    cur2 = c2.cursor()
    cur2.execute("SELECT current_database(), version()")
    db, ver = cur2.fetchone()
    print(f"[PG] 连接成功: db={db} ver={ver[:60]}")
    cur2.close()
    c2.close()


def setup_neo4j():
    d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with d.session(database="neo4j") as s:
        s.run("MATCH (n:_TestPing) DETACH DELETE n").consume()
        s.run("CREATE (n:_TestPing {ts: datetime()}) RETURN n").consume()
        cnt = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        s.run("MATCH (n:_TestPing) DETACH DELETE n").consume()
        print(f"[NEO4J] 写入测试通过；当前节点数={cnt}")
    d.close()


if __name__ == "__main__":
    try:
        setup_pg()
        setup_neo4j()
        print("OK")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
