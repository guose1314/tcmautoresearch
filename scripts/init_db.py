#!/usr/bin/env python3
"""
scripts/init_db.py — 数据库 Schema 初始化脚本（指令 I-03）

一次性运行，初始化：
  - PostgreSQL：learning_records、research_results 表及索引
  - Neo4j：Formula/Herb/Syndrome/Target/Pathway 唯一性约束 + 全文索引

用法::

    python scripts/init_db.py                  # 使用 config.yml 中的默认配置
    python scripts/init_db.py --config custom.yml
    TCM_POSTGRES_URL=postgresql://... python scripts/init_db.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("init_db")

# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL DDL
# ─────────────────────────────────────────────────────────────────────────────

_PG_DDL = [
    # 学习记录表
    """
    CREATE TABLE IF NOT EXISTS learning_records (
        id            SERIAL PRIMARY KEY,
        task_id       VARCHAR(64) UNIQUE NOT NULL,
        phase         VARCHAR(32),
        performance   FLOAT,
        feedback      FLOAT,
        input_summary TEXT,
        output_summary TEXT,
        ewma_score    FLOAT,
        created_at    TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lr_phase       ON learning_records(phase)",
    "CREATE INDEX IF NOT EXISTS idx_lr_performance ON learning_records(performance)",
    "CREATE INDEX IF NOT EXISTS idx_lr_created     ON learning_records(created_at DESC)",

    # 研究结果表
    """
    CREATE TABLE IF NOT EXISTS research_results (
        id          SERIAL PRIMARY KEY,
        cycle_id    VARCHAR(64)  NOT NULL,
        phase       VARCHAR(32),
        result_json TEXT,
        summary     TEXT,
        created_at  TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rr_cycle   ON research_results(cycle_id)",
    "CREATE INDEX IF NOT EXISTS idx_rr_phase   ON research_results(phase)",
    "CREATE INDEX IF NOT EXISTS idx_rr_created ON research_results(created_at DESC)",

    # 研究任务主表（供 FastAPI status 查询）
    """
    CREATE TABLE IF NOT EXISTS research_jobs (
        id          SERIAL PRIMARY KEY,
        job_id      VARCHAR(64) UNIQUE NOT NULL,
        topic       TEXT,
        status      VARCHAR(32) DEFAULT 'pending',
        current_phase VARCHAR(32),
        progress    FLOAT DEFAULT 0.0,
        error_msg   TEXT,
        created_at  TIMESTAMP DEFAULT NOW(),
        updated_at  TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON research_jobs(status)",
]

# ─────────────────────────────────────────────────────────────────────────────
# Neo4j Cypher 约束 & 索引
# ─────────────────────────────────────────────────────────────────────────────

_NEO4J_CONSTRAINTS = [
    # 唯一性约束（Neo4j 5.x 语法）
    "CREATE CONSTRAINT formula_id IF NOT EXISTS FOR (f:Formula) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT herb_name  IF NOT EXISTS FOR (h:Herb)    REQUIRE h.name IS UNIQUE",
    "CREATE CONSTRAINT syndrome_name IF NOT EXISTS FOR (s:Syndrome) REQUIRE s.name IS UNIQUE",
    "CREATE CONSTRAINT target_name IF NOT EXISTS FOR (t:Target)  REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT pathway_id IF NOT EXISTS FOR (p:Pathway)  REQUIRE p.id IS UNIQUE",
    # 全文索引
    "CREATE FULLTEXT INDEX herb_fulltext IF NOT EXISTS FOR (h:Herb) ON EACH [h.name, h.aliases]",
    "CREATE FULLTEXT INDEX formula_fulltext IF NOT EXISTS FOR (f:Formula) ON EACH [f.name, f.description]",
]


def _resolve_env_var(value: str) -> str:
    """解析 ${VAR:-default} 格式的环境变量。"""
    if not value.startswith("${"):
        return value
    import re
    m = re.match(r"\$\{(\w+):-(.+)\}", value)
    if m:
        return os.environ.get(m.group(1), m.group(2))
    return value


def init_postgres(pg_config: dict) -> bool:
    """初始化 PostgreSQL schema。"""
    url = _resolve_env_var(pg_config.get("url", ""))
    if not url:
        logger.warning("PostgreSQL URL 未配置，跳过")
        return False
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True, echo=False)
        with engine.begin() as conn:
            for stmt in _PG_DDL:
                conn.execute(text(stmt.strip()))
        engine.dispose()
        logger.info("✅ PostgreSQL schema 初始化成功 (%s)", url.split("@")[-1])
        return True
    except ImportError:
        logger.error("❌ sqlalchemy 未安装，请运行: pip install sqlalchemy psycopg2-binary")
        return False
    except Exception as exc:
        logger.error("❌ PostgreSQL 初始化失败: %s", exc)
        return False


def init_neo4j(neo4j_config: dict) -> bool:
    """初始化 Neo4j 约束和全文索引。"""
    uri = _resolve_env_var(neo4j_config.get("uri", "bolt://localhost:7687"))
    user = _resolve_env_var(neo4j_config.get("username", "neo4j"))
    password = _resolve_env_var(neo4j_config.get("password", "neo4j"))
    database = neo4j_config.get("database", "neo4j")
    try:
        from neo4j import GraphDatabase  # type: ignore

        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as session:
            for cypher in _NEO4J_CONSTRAINTS:
                try:
                    session.run(cypher)
                except Exception as inner:
                    logger.debug("Neo4j DDL（可忽略）: %s — %s", cypher[:60], inner)
        driver.close()
        logger.info("✅ Neo4j 约束/索引初始化成功 (%s)", uri)
        return True
    except ImportError:
        logger.warning("neo4j driver 未安装，Neo4j 初始化跳过（安装: pip install neo4j）")
        return False
    except Exception as exc:
        logger.error("❌ Neo4j 初始化失败: %s", exc)
        return False


def load_config(config_path: str = "config.yml") -> dict:
    """加载 YAML 配置文件。"""
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("配置文件 %s 不存在，使用默认值", config_path)
        return {}
    except Exception as exc:
        logger.error("配置文件加载失败: %s", exc)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 TCM Research 数据库 Schema")
    parser.add_argument("--config", default="config.yml", help="YAML 配置文件路径")
    parser.add_argument("--pg-only", action="store_true", help="仅初始化 PostgreSQL")
    parser.add_argument("--neo4j-only", action="store_true", help="仅初始化 Neo4j")
    args = parser.parse_args()

    config = load_config(args.config)
    db_config = config.get("database", {})

    pg_cfg = db_config.get("postgresql", {})
    neo4j_cfg = db_config.get("neo4j", {})

    results = {}

    if not args.neo4j_only:
        results["postgresql"] = init_postgres(pg_cfg)

    if not args.pg_only:
        results["neo4j"] = init_neo4j(neo4j_cfg)

    print("\n── 初始化结果 ──")
    for backend, ok in results.items():
        status = "✅ 成功" if ok else "❌ 失败/跳过"
        print(f"  {backend:12s}: {status}")

    if any(results.values()):
        print("\n数据库 schema 已就绪，现在可以将 config.yml 中 enabled 改为 true 并启动应用。")
    else:
        print("\n提示：请确保 Neo4j / PostgreSQL 服务已运行，或通过环境变量传递连接信息。")


if __name__ == "__main__":
    main()
