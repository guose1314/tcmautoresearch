"""build_community_summaries — 离线脚本：对 :class:`Topic` 跑 LLM 生成 :class:`CommunitySummary`。

设计目标
========

把 T3.1 已沉淀的 Topic 节点（``MATCH (t:Topic) RETURN t.key``）逐个：

1. 拉取该 Topic 下挂载的 Document / 实体 / 关系（采样）；
2. 调 LLM (Self-Refine 友好的提示) 生成 ≤ ``--max-tokens`` 的中文社区摘要；
3. 写回 Neo4j::

       MERGE (cs:CommunitySummary {topic_key:$key})
       SET cs.body=$body, cs.token_count=$n

CLI 用法（典型）::

    python tools/build_community_summaries.py \
        --max-tokens 1500 \
        --neo4j-database neo4j \
        --dry-run

``--dry-run`` 模式只打印目标 Topic 数量，不实际调用 LLM。
``--llm-call`` 默认走 :func:`_default_llm_call`，但单测可注入 fake callable。
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


CYPHER_LIST_TOPICS = "MATCH (t:Topic) RETURN t.key AS key, t.label AS label"

CYPHER_TOPIC_DOCUMENTS = (
    "MATCH (doc:Document)-[:BELONGS_TO_TOPIC]->(t:Topic {key:$key}) "
    "RETURN doc.id AS id, coalesce(doc.title, '') AS title, "
    "       coalesce(doc.summary, '') AS summary "
    "LIMIT $sample_size"
)

CYPHER_UPSERT_SUMMARY = (
    "MERGE (cs:CommunitySummary {topic_key:$key}) "
    "SET cs.body=$body, cs.token_count=$n, cs.updated_at=timestamp() "
    "RETURN cs.topic_key AS key"
)


def _default_llm_call(prompt: str, *, max_tokens: int = 1500) -> str:
    """默认 LLM 调用占位：返回 prompt 头部摘要 + 截断标记。

    生产环境应替换为 ``src.llm.client.LLMClient`` 等真实客户端。
    保留 stub 是为了让离线脚本即使没装 LLM 依赖也能完成 dry-run。
    """
    snippet = prompt.strip().splitlines()[0:3]
    head = "\n".join(snippet)[: max_tokens * 2]
    return f"[summary stub]\n{head}"


def _build_prompt(
    topic_key: str, label: str, documents: Sequence[Dict[str, Any]]
) -> str:
    lines = [f"为主题「{label or topic_key}」生成中文社区摘要（≤ 1500 tokens）。"]
    lines.append("素材：")
    for doc in documents:
        title = (doc.get("title") or "").strip() or doc.get("id")
        summary = (doc.get("summary") or "").strip()
        lines.append(f"- {title}: {summary[:200]}")
    lines.append("请输出：1) 主题概述；2) 关键实体；3) 高频关系；4) 风险提示。")
    return "\n".join(lines)


def _open_session(driver: Any, database: str):
    inner = getattr(driver, "driver", None)
    if inner is not None and hasattr(inner, "session"):
        return inner.session(database=database)
    return driver.session(database=database)


def build_community_summaries(
    *,
    neo4j_driver: Any,
    neo4j_database: str = "neo4j",
    max_tokens: int = 1500,
    sample_size: int = 20,
    dry_run: bool = False,
    llm_call: Callable[..., str] = _default_llm_call,
    estimate_tokens: Optional[Callable[[str], int]] = None,
) -> Dict[str, Any]:
    """对所有 Topic 生成 CommunitySummary，返回汇总统计。"""

    if estimate_tokens is None:
        estimate_tokens = lambda s: max(1, (len(s) + 1) // 2)  # noqa: E731

    written: List[str] = []
    skipped: List[str] = []
    if neo4j_driver is None:
        return {"written": [], "skipped": [], "dry_run": dry_run, "error": "no driver"}

    with _open_session(neo4j_driver, neo4j_database) as session:
        topics = list(session.run(CYPHER_LIST_TOPICS))
        for rec in topics:
            key = rec.get("key") if hasattr(rec, "get") else rec["key"]
            label = rec.get("label") if hasattr(rec, "get") else rec["label"]
            if not key:
                continue
            docs = list(
                session.run(
                    CYPHER_TOPIC_DOCUMENTS, key=key, sample_size=int(sample_size)
                )
            )
            doc_payloads = [
                {
                    "id": (r.get("id") if hasattr(r, "get") else r["id"]),
                    "title": (r.get("title") if hasattr(r, "get") else r["title"]),
                    "summary": (
                        r.get("summary") if hasattr(r, "get") else r["summary"]
                    ),
                }
                for r in docs
            ]
            prompt = _build_prompt(str(key), str(label or ""), doc_payloads)
            if dry_run:
                skipped.append(str(key))
                continue
            try:
                body = llm_call(prompt, max_tokens=max_tokens)
            except Exception as exc:  # noqa: BLE001
                logger.exception("LLM call failed for topic %s: %s", key, exc)
                skipped.append(str(key))
                continue
            tokens = int(estimate_tokens(body))
            session.run(CYPHER_UPSERT_SUMMARY, key=str(key), body=str(body), n=tokens)
            written.append(str(key))

    return {
        "written": written,
        "skipped": skipped,
        "dry_run": dry_run,
        "topic_count": len(written) + len(skipped),
    }


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate CommunitySummary nodes for all Topics."
    )
    parser.add_argument("--neo4j-database", default="neo4j")
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    try:
        from src.storage.neo4j_driver import Neo4jDriver  # type: ignore
    except Exception:
        logger.error("Neo4jDriver not available; cannot run build_community_summaries")
        return 1
    driver = Neo4jDriver()  # type: ignore[call-arg]
    result = build_community_summaries(
        neo4j_driver=driver,
        neo4j_database=args.neo4j_database,
        max_tokens=args.max_tokens,
        sample_size=args.sample_size,
        dry_run=args.dry_run,
    )
    print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
