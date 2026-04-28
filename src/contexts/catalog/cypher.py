"""Catalog Cypher 模板 — Topic / SubjectClass / DynastySlice。

集中放置写入侧 MERGE 模板、关系模板与约束 DDL。
保持纯字符串常量便于在 service 层组合执行，也方便单元测试断言。
"""

from __future__ import annotations

from typing import Tuple

# ---------------------------------------------------------------------------
# 约束（启动时幂等创建）
# ---------------------------------------------------------------------------

CONSTRAINT_TOPIC_KEY = (
    "CREATE CONSTRAINT topic_key IF NOT EXISTS FOR (t:Topic) REQUIRE t.key IS UNIQUE"
)
CONSTRAINT_SUBJECT_CODE = (
    "CREATE CONSTRAINT subject_class_code IF NOT EXISTS "
    "FOR (s:SubjectClass) REQUIRE s.code IS UNIQUE"
)
CONSTRAINT_DYNASTY_NAME = (
    "CREATE CONSTRAINT dynasty_slice_dynasty IF NOT EXISTS "
    "FOR (d:DynastySlice) REQUIRE d.dynasty IS UNIQUE"
)

CATALOG_CONSTRAINTS: Tuple[str, ...] = (
    CONSTRAINT_TOPIC_KEY,
    CONSTRAINT_SUBJECT_CODE,
    CONSTRAINT_DYNASTY_NAME,
)

# ---------------------------------------------------------------------------
# 节点 MERGE 模板
# ---------------------------------------------------------------------------

MERGE_TOPIC = """
MERGE (t:Topic {key: $key})
ON CREATE SET t.created_at = timestamp(),
              t.label = coalesce($label, $key),
              t.description = coalesce($description, '')
ON MATCH  SET t.updated_at = timestamp(),
              t.label = coalesce($label, t.label),
              t.description = coalesce($description, t.description)
RETURN t.key AS key
""".strip()

MERGE_SUBJECT_CLASS = """
MERGE (s:SubjectClass {code: $code})
ON CREATE SET s.created_at = timestamp(),
              s.name = coalesce($name, $code),
              s.scheme = coalesce($scheme, 'CLC')
ON MATCH  SET s.updated_at = timestamp(),
              s.name = coalesce($name, s.name),
              s.scheme = coalesce($scheme, s.scheme)
RETURN s.code AS code
""".strip()

MERGE_DYNASTY_SLICE = """
MERGE (d:DynastySlice {dynasty: $dynasty})
ON CREATE SET d.created_at = timestamp(),
              d.start_year = $start_year,
              d.end_year = $end_year
ON MATCH  SET d.updated_at = timestamp(),
              d.start_year = coalesce($start_year, d.start_year),
              d.end_year = coalesce($end_year, d.end_year)
RETURN d.dynasty AS dynasty
""".strip()

# ---------------------------------------------------------------------------
# 关系 MERGE 模板（Document → 视图节点）
# ---------------------------------------------------------------------------

LINK_DOCUMENT_TO_TOPIC = """
MATCH (doc:Document {id: $document_id})
MERGE (t:Topic {key: $key})
MERGE (doc)-[r:BELONGS_TO_TOPIC]->(t)
ON CREATE SET r.weight = coalesce($weight, 1.0),
              r.created_at = timestamp()
ON MATCH  SET r.weight = coalesce($weight, r.weight),
              r.updated_at = timestamp()
""".strip()

LINK_DOCUMENT_TO_SUBJECT = """
MATCH (doc:Document {id: $document_id})
MERGE (s:SubjectClass {code: $code})
MERGE (doc)-[r:IN_SUBJECT]->(s)
ON CREATE SET r.created_at = timestamp()
""".strip()

LINK_DOCUMENT_TO_DYNASTY = """
MATCH (doc:Document {id: $document_id})
MERGE (d:DynastySlice {dynasty: $dynasty})
MERGE (doc)-[r:IN_DYNASTY]->(d)
ON CREATE SET r.created_at = timestamp()
""".strip()

# ---------------------------------------------------------------------------
# 查询模板
# ---------------------------------------------------------------------------

QUERY_TOPIC_DOCUMENTS = """
MATCH (doc:Document)-[r:BELONGS_TO_TOPIC]->(t:Topic {key: $key})
RETURN doc.id AS document_id,
       doc.source_file AS source_file,
       coalesce(r.weight, 1.0) AS weight
ORDER BY weight DESC
LIMIT $limit
""".strip()

QUERY_SUBJECT_DOCUMENTS = """
MATCH (doc:Document)-[:IN_SUBJECT]->(s:SubjectClass {code: $code})
RETURN doc.id AS document_id,
       doc.source_file AS source_file
LIMIT $limit
""".strip()

QUERY_DYNASTY_DOCUMENTS = """
MATCH (doc:Document)-[:IN_DYNASTY]->(d:DynastySlice {dynasty: $dynasty})
RETURN doc.id AS document_id,
       doc.source_file AS source_file
LIMIT $limit
""".strip()

# ---------------------------------------------------------------------------
# 视图列表（含文档计数 + 分页）
# ---------------------------------------------------------------------------

LIST_TOPIC_VIEW = """
MATCH (t:Topic)
OPTIONAL MATCH (doc:Document)-[:BELONGS_TO_TOPIC]->(t)
WITH t, count(DISTINCT doc) AS document_count
RETURN t.key AS key,
       coalesce(t.label, t.key) AS label,
       coalesce(t.description, '') AS description,
       document_count
ORDER BY document_count DESC, key ASC
SKIP $skip LIMIT $limit
""".strip()

LIST_SUBJECT_VIEW = """
MATCH (s:SubjectClass)
OPTIONAL MATCH (doc:Document)-[:IN_SUBJECT]->(s)
WITH s, count(DISTINCT doc) AS document_count
RETURN s.code AS code,
       coalesce(s.name, s.code) AS name,
       coalesce(s.scheme, 'CLC') AS scheme,
       document_count
ORDER BY document_count DESC, code ASC
SKIP $skip LIMIT $limit
""".strip()

LIST_DYNASTY_VIEW = """
MATCH (d:DynastySlice)
OPTIONAL MATCH (doc:Document)-[:IN_DYNASTY]->(d)
WITH d, count(DISTINCT doc) AS document_count
RETURN d.dynasty AS dynasty,
       d.start_year AS start_year,
       d.end_year AS end_year,
       document_count
ORDER BY document_count DESC, dynasty ASC
SKIP $skip LIMIT $limit
""".strip()

# ---------------------------------------------------------------------------
# T3.2 迁移：ResearchTopic → Topic
# ---------------------------------------------------------------------------

MIGRATE_RESEARCH_TOPIC_TO_TOPIC = """
MATCH (rt:ResearchTopic)
WITH rt, coalesce(rt.name, rt.label, rt.community_id, rt.id) AS topic_key
WHERE topic_key IS NOT NULL AND topic_key <> ''
MERGE (t:Topic {key: topic_key})
ON CREATE SET t.created_at = timestamp(),
              t.label = coalesce(rt.label, rt.name, topic_key),
              t.description = coalesce(rt.description, ''),
              t.legacy_id = coalesce(rt.id, rt.community_id)
ON MATCH  SET t.updated_at = timestamp(),
              t.label = coalesce(t.label, rt.label, rt.name, topic_key),
              t.legacy_id = coalesce(t.legacy_id, rt.id, rt.community_id)
RETURN count(t) AS topic_count
""".strip()

MIGRATE_HAS_LATENT_TOPIC_TO_BELONGS = """
MATCH (doc)-[r:HAS_LATENT_TOPIC]->(rt:ResearchTopic)
WITH doc, rt, r,
     coalesce(rt.name, rt.label, rt.community_id, rt.id) AS topic_key,
     coalesce(r.weight, r.cohesion, r.size * 1.0, 1.0) AS weight
WHERE topic_key IS NOT NULL AND topic_key <> ''
MATCH (t:Topic {key: topic_key})
MERGE (doc)-[bt:BELONGS_TO_TOPIC]->(t)
ON CREATE SET bt.weight = weight,
              bt.created_at = timestamp(),
              bt.legacy_rel = 'HAS_LATENT_TOPIC'
ON MATCH  SET bt.weight = coalesce(bt.weight, weight),
              bt.updated_at = timestamp()
RETURN count(bt) AS edge_count
""".strip()

COUNT_RESEARCH_TOPIC = "MATCH (rt:ResearchTopic) RETURN count(rt) AS legacy_count"
COUNT_TOPIC = "MATCH (t:Topic) RETURN count(t) AS topic_count"
COUNT_HAS_LATENT_TOPIC = (
    "MATCH ()-[r:HAS_LATENT_TOPIC]->() RETURN count(r) AS legacy_edge_count"
)
COUNT_BELONGS_TO_TOPIC = (
    "MATCH ()-[r:BELONGS_TO_TOPIC]->() RETURN count(r) AS edge_count"
)
COUNT_HAS_TOPIC_MEMBER = (
    "MATCH ()-[r:HAS_TOPIC_MEMBER]->() RETURN count(r) AS legacy_member_count"
)
