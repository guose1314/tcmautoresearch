"""T7.2: 把四校结论 + 假说 + 证据分级导出 jsonl 给文献学专家批注。

调用方式::

    python tools/export_for_expert_review.py ^
        --connection-string sqlite:///./tcm.db ^
        --cycle-ids cycle-1,cycle-2 ^
        --output reviews/round_1.jsonl

输出 JSONL 行结构（每条 = 一条假说，便于专家逐条批注）::

    {
      "schema_version": "expert-review.v1",
      "cycle_id": "...",
      "research_topic": "...",
      "hypothesis_id": "...",
      "hypothesis_statement": "...",
      "methodology_tag": "evidence_based",
      "evidence_grade": "B",
      "four_pass_collation": {
          "summary": {"total": 4, "succeeded": 3, "failed": 1},
          "strategies": {"cross": {...}, "intra": {...}, "external": {...}, "rational": {...}}
      },
      "evidence_bundle": [...],
      "expert_grade": null,
      "expert_notes": null,
      "expert_review_id": "expert-<cycle>-<hyp>"
    }

专家在每条 jsonl 旁补 ``expert_grade`` (A/B/C/D) 与 ``expert_notes``，再用
``tools/import_expert_review.py`` 反向写回 PG ``research_learning_feedback``。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository

logger = logging.getLogger("tools.export_for_expert_review")

EXPORT_SCHEMA_VERSION = "expert-review.v1"


# ---------------------------------------------------------------------------
# Snapshot → 评审条目
# ---------------------------------------------------------------------------


def extract_hypotheses(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """从 snapshot 中提取 hypothesis 列表（来自 hypothesis phase output 或 artifacts）。"""
    hypotheses: List[Dict[str, Any]] = []

    # 优先：hypothesis 阶段输出
    for phase in snapshot.get("phase_executions") or []:
        if str(phase.get("phase") or "").strip().lower() != "hypothesis":
            continue
        output = phase.get("output") if isinstance(phase.get("output"), Mapping) else {}
        bag = (
            (output.get("results") or {}).get("hypotheses")
            if isinstance(output.get("results"), Mapping)
            else None
        )
        if not bag:
            bag = output.get("hypotheses")
        for item in bag or []:
            if isinstance(item, Mapping):
                hypotheses.append(dict(item))

    # 次选：artifact 中的 hypothesis content
    if not hypotheses:
        for artifact in snapshot.get("artifacts") or []:
            atype = str(artifact.get("artifact_type") or "").strip().lower()
            name = str(artifact.get("name") or "").strip().lower()
            if atype != "hypothesis" and "hypothes" not in name:
                continue
            content = artifact.get("content")
            if isinstance(content, Mapping):
                items = content.get("hypotheses") or [content]
                for item in items:
                    if isinstance(item, Mapping):
                        hypotheses.append(dict(item))
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, Mapping):
                        hypotheses.append(dict(item))

    return hypotheses


def extract_four_pass_collation(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """从 observe phase output 中聚合四校结论（cross/intra/external/rational）。"""
    aggregate: Dict[str, Any] = {
        "document_count": 0,
        "strategies_enabled": [],
        "succeeded_total": 0,
        "failed_total": 0,
        "documents": [],
    }
    for phase in snapshot.get("phase_executions") or []:
        if str(phase.get("phase") or "").strip().lower() != "observe":
            continue
        output = phase.get("output") if isinstance(phase.get("output"), Mapping) else {}
        collation = (
            output.get("collation_result")
            or (output.get("results") or {}).get("collation")
            or {}
        )
        if not isinstance(collation, Mapping):
            continue
        aggregate["document_count"] += int(collation.get("document_count") or 0)
        aggregate["succeeded_total"] += int(collation.get("succeeded_total") or 0)
        aggregate["failed_total"] += int(collation.get("failed_total") or 0)
        for s in collation.get("strategies_enabled") or []:
            if s not in aggregate["strategies_enabled"]:
                aggregate["strategies_enabled"].append(s)
        for report in collation.get("reports") or []:
            if isinstance(report, Mapping):
                aggregate["documents"].append(dict(report))
    return aggregate


def build_review_records(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """对单个 cycle 的 snapshot，输出可批注的 review record 列表。"""
    cycle_id = str(snapshot.get("cycle_id") or "").strip()
    research_topic = str(
        snapshot.get("research_objective") or snapshot.get("cycle_name") or ""
    ).strip()
    collation = extract_four_pass_collation(snapshot)
    hypotheses = extract_hypotheses(snapshot)

    if not hypotheses:
        # 没有假说也要让专家看到 cycle 概况，便于人工补充
        return [
            _make_record(
                cycle_id=cycle_id,
                research_topic=research_topic,
                hypothesis={
                    "id": "_no_hypothesis",
                    "statement": "(本周期未生成假说)",
                    "methodology_tag": "unknown",
                    "evidence_grade": "C",
                },
                four_pass=collation,
            )
        ]

    return [
        _make_record(
            cycle_id=cycle_id,
            research_topic=research_topic,
            hypothesis=hyp,
            four_pass=collation,
        )
        for hyp in hypotheses
    ]


def _make_record(
    *,
    cycle_id: str,
    research_topic: str,
    hypothesis: Mapping[str, Any],
    four_pass: Mapping[str, Any],
) -> Dict[str, Any]:
    hypothesis_id = (
        str(
            hypothesis.get("id")
            or hypothesis.get("hypothesis_id")
            or hypothesis.get("statement", "")[:32]
        )
        or "hyp"
    )
    statement = str(
        hypothesis.get("statement") or hypothesis.get("description") or ""
    ).strip()
    methodology_tag = (
        str(
            hypothesis.get("methodology_tag")
            or hypothesis.get("methodology")
            or "evidence_based"
        )
        .strip()
        .lower()
        or "evidence_based"
    )
    evidence_grade = str(hypothesis.get("evidence_grade") or "C").strip().upper() or "C"
    evidence_bundle = list(
        hypothesis.get("evidence_bundle") or hypothesis.get("evidence") or []
    )

    review_id_seed = f"{cycle_id}|{hypothesis_id}"
    expert_review_id = (
        "expert-" + hashlib.sha1(review_id_seed.encode("utf-8")).hexdigest()[:16]
    )

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "research_topic": research_topic,
        "hypothesis_id": hypothesis_id,
        "hypothesis_statement": statement,
        "methodology_tag": methodology_tag,
        "evidence_grade": evidence_grade,
        "four_pass_collation": _summarize_collation(four_pass),
        "evidence_bundle": evidence_bundle,
        "expert_grade": None,
        "expert_notes": None,
        "expert_review_id": expert_review_id,
    }


def _summarize_collation(four_pass: Mapping[str, Any]) -> Dict[str, Any]:
    summary = {
        "document_count": int(four_pass.get("document_count") or 0),
        "strategies_enabled": list(four_pass.get("strategies_enabled") or []),
        "succeeded_total": int(four_pass.get("succeeded_total") or 0),
        "failed_total": int(four_pass.get("failed_total") or 0),
    }
    # 把每文档的 strategies 摘要平铺，方便专家阅读
    documents = []
    for doc in four_pass.get("documents") or []:
        if not isinstance(doc, Mapping):
            continue
        documents.append(
            {
                "document_id": doc.get("document_id"),
                "summary": doc.get("summary"),
                "strategies": {
                    name: {
                        "succeeded": bool((sd or {}).get("succeeded")),
                        "error": (sd or {}).get("error"),
                    }
                    for name, sd in (doc.get("strategies") or {}).items()
                },
            }
        )
    return {"summary": summary, "documents": documents}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_cycle_ids(
    repo: ResearchSessionRepository, args: argparse.Namespace
) -> List[str]:
    if args.cycle_ids:
        return [c.strip() for c in args.cycle_ids.split(",") if c.strip()]
    # 全表 fallback：取最近 limit 条
    listing = (
        repo.list_sessions(limit=int(args.limit or 50))
        if hasattr(repo, "list_sessions")
        else None
    )
    if not isinstance(listing, Mapping):
        return []
    cycle_ids: List[str] = []
    for item in listing.get("items") or []:
        cid = str((item or {}).get("cycle_id") or "").strip()
        if cid:
            cycle_ids.append(cid)
    return cycle_ids


def export(
    *,
    connection_string: str,
    cycle_ids: Iterable[str],
    output: Path,
) -> Dict[str, Any]:
    """主入口：把指定 cycle 的评审条目写入 ``output`` (JSONL)。"""
    db = DatabaseManager(connection_string)
    db.init_db()
    try:
        repo = ResearchSessionRepository(db)
        output.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        skipped: List[str] = []
        cycles_with_records = 0
        with output.open("w", encoding="utf-8") as fh:
            for cycle_id in cycle_ids:
                snapshot = repo.get_full_snapshot(cycle_id)
                if snapshot is None:
                    skipped.append(cycle_id)
                    continue
                records = build_review_records(snapshot)
                if not records:
                    skipped.append(cycle_id)
                    continue
                cycles_with_records += 1
                for record in records:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1

        return {
            "output": str(output),
            "records_written": written,
            "cycles_exported": cycles_with_records,
            "cycles_skipped": skipped,
        }
    finally:
        if db.engine is not None:
            db.engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--connection-string", required=True, help="SQLAlchemy URL")
    parser.add_argument(
        "--cycle-ids",
        default="",
        help="逗号分隔的 cycle_id 列表；省略时取 list_sessions() 最近 --limit 条",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="未指定 cycle_ids 时的回填数量上限"
    )
    parser.add_argument("--output", required=True, help="输出 JSONL 文件路径")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
    )
    db = DatabaseManager(args.connection_string)
    db.init_db()
    repo = ResearchSessionRepository(db)
    cycle_ids = _resolve_cycle_ids(repo, args)
    if not cycle_ids:
        logger.error("没有可导出的 cycle_id，请显式提供 --cycle-ids")
        return 2
    summary = export(
        connection_string=args.connection_string,
        cycle_ids=cycle_ids,
        output=Path(args.output),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
