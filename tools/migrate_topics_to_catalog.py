"""T3.2: 把旧 ResearchTopic / HAS_LATENT_TOPIC / HAS_TOPIC_MEMBER 一次性迁到 Catalog。

迁移规则：
  - ResearchTopic.name (兜底 label/community_id/id) → Topic.key
  - 保留 ResearchTopic.id 作为 Topic.legacy_id 以便回滚
  - 每条 (doc)-[:HAS_LATENT_TOPIC]->(rt) 复制为 (doc)-[:BELONGS_TO_TOPIC {weight, legacy_rel}]->(t)
  - HAS_TOPIC_MEMBER 关系不复制（Topic 不再持有具体 member 列表，由 Document 子图自行表达）

验收门：
  - 迁移后 ``MATCH (t:Topic) RETURN count(t) >= 旧 ResearchTopic 数``
  - ``count(BELONGS_TO_TOPIC) >= count(HAS_LATENT_TOPIC)``（每条旧关系至少有一对应）

Usage::

    python tools/migrate_topics_to_catalog.py --uri neo4j://localhost:7687 \\
        --user neo4j --password ****
    python tools/migrate_topics_to_catalog.py --apply  # 实际执行
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 允许直接以脚本方式运行
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contexts.catalog import CatalogContext  # noqa: E402
from src.contexts.catalog import cypher as catalog_cypher  # noqa: E402

logger = logging.getLogger("migrate_topics_to_catalog")


def _build_driver(uri: str, user: str, password: str):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(uri, auth=(user, password))


def _run_scalar(session, query: str, key: str) -> int:
    record = session.run(query).single()
    return int(record[key]) if record is not None else 0


def migrate(driver, *, database: str, apply: bool) -> dict:
    """执行迁移；apply=False 时仅 dry-run 统计。

    返回字典：legacy_topic / topic / legacy_edge / belongs_edge / migrated_topics / migrated_edges。
    """
    catalog = CatalogContext(driver, database=database)
    catalog.ensure_constraints()

    with driver.session(database=database) as session:
        legacy_topic = _run_scalar(session, catalog_cypher.COUNT_RESEARCH_TOPIC, "legacy_count")
        topic_before = _run_scalar(session, catalog_cypher.COUNT_TOPIC, "topic_count")
        legacy_edge = _run_scalar(session, catalog_cypher.COUNT_HAS_LATENT_TOPIC, "legacy_edge_count")
        belongs_before = _run_scalar(session, catalog_cypher.COUNT_BELONGS_TO_TOPIC, "edge_count")
        legacy_member = _run_scalar(session, catalog_cypher.COUNT_HAS_TOPIC_MEMBER, "legacy_member_count")

        logger.info(
            "[before] ResearchTopic=%d Topic=%d HAS_LATENT_TOPIC=%d BELONGS_TO_TOPIC=%d HAS_TOPIC_MEMBER=%d",
            legacy_topic, topic_before, legacy_edge, belongs_before, legacy_member,
        )

        migrated_topics = 0
        migrated_edges = 0
        if apply:
            t_record = session.run(catalog_cypher.MIGRATE_RESEARCH_TOPIC_TO_TOPIC).single()
            migrated_topics = int(t_record["topic_count"]) if t_record is not None else 0
            e_record = session.run(catalog_cypher.MIGRATE_HAS_LATENT_TOPIC_TO_BELONGS).single()
            migrated_edges = int(e_record["edge_count"]) if e_record is not None else 0
            logger.info("[applied] migrated_topics=%d migrated_edges=%d", migrated_topics, migrated_edges)
        else:
            logger.info("[dry-run] no writes performed; pass --apply to execute")

        topic_after = _run_scalar(session, catalog_cypher.COUNT_TOPIC, "topic_count")
        belongs_after = _run_scalar(session, catalog_cypher.COUNT_BELONGS_TO_TOPIC, "edge_count")

    summary = {
        "legacy_topic": legacy_topic,
        "topic_before": topic_before,
        "topic_after": topic_after,
        "legacy_edge": legacy_edge,
        "belongs_before": belongs_before,
        "belongs_after": belongs_after,
        "legacy_member": legacy_member,
        "migrated_topics": migrated_topics,
        "migrated_edges": migrated_edges,
        "applied": apply,
    }

    if apply:
        # 验收门
        if topic_after < legacy_topic:
            raise SystemExit(
                f"acceptance failed: Topic count {topic_after} < legacy ResearchTopic {legacy_topic}"
            )
        if belongs_after < legacy_edge:
            raise SystemExit(
                f"acceptance failed: BELONGS_TO_TOPIC {belongs_after} < HAS_LATENT_TOPIC {legacy_edge}"
            )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=os.environ.get("TCM_NEO4J_URI", "neo4j://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("TCM_NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("TCM_NEO4J_PASSWORD", ""))
    parser.add_argument("--database", default=os.environ.get("TCM_NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--apply", action="store_true", help="执行迁移；缺省仅 dry-run")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.password:
        logger.error("--password (or TCM_NEO4J_PASSWORD env) is required")
        return 2

    driver = _build_driver(args.uri, args.user, args.password)
    try:
        summary = migrate(driver, database=args.database, apply=args.apply)
    finally:
        driver.close()

    print("MIGRATION SUMMARY:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
