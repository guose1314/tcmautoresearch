"""T7.2: 把专家批注后的 jsonl 反向写回 PG ``research_learning_feedback`` 作为高权重反馈。

调用方式::

    python tools/import_expert_review.py ^
        --connection-string sqlite:///./tcm.db ^
        --input reviews/round_1.jsonl ^
        --weight 5.0

工作流::

    tools/export_for_expert_review.py  → reviews/*.jsonl   (expert_grade=null)
                                       ↓ (专家批注)
    tools/import_expert_review.py      → research_learning_feedback (feedback_scope="expert_review")
                                       ↓ (next cycle)
    LearningLoopOrchestrator.prepare_cycle() + ExpertReviewFeedbackRepo
                                       → prompt_bias_blocks 含专家偏置

"幂等"：同一条 ``expert_review_id`` 重复导入会被跳过（依赖 PG metadata.expert_review_id）。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository

logger = logging.getLogger("tools.import_expert_review")

ALLOWED_GRADES = {"A", "B", "C", "D"}
GRADE_TO_SEVERITY = {
    "A": "low",
    "B": "low",
    "C": "medium",
    "D": "high",
}
GRADE_TO_SCORE = {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.2}
DEFAULT_WEIGHT = 5.0


# ---------------------------------------------------------------------------
# JSONL → ResearchLearningFeedback
# ---------------------------------------------------------------------------


def parse_jsonl(input_path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("第 %d 行 JSON 解析失败：%s", lineno, exc)
                continue
            if isinstance(payload, Mapping):
                records.append(dict(payload))
    return records


def _validate(record: Mapping[str, Any]) -> Optional[str]:
    cycle_id = str(record.get("cycle_id") or "").strip()
    if not cycle_id:
        return "missing cycle_id"
    grade = str(record.get("expert_grade") or "").strip().upper()
    if not grade:
        return "expert_grade is null/empty (skipping unannotated row)"
    if grade not in ALLOWED_GRADES:
        return f"invalid expert_grade={grade!r} (must be A/B/C/D)"
    return None


def build_feedback_record(
    record: Mapping[str, Any],
    *,
    weight: float,
    target_phase: str = "hypothesis",
) -> Dict[str, Any]:
    grade = str(record["expert_grade"]).strip().upper()
    severity = GRADE_TO_SEVERITY[grade]
    overall_score = GRADE_TO_SCORE[grade]
    expert_notes = str(record.get("expert_notes") or "").strip()
    expert_review_id = str(record.get("expert_review_id") or "").strip()

    hypothesis_id = str(record.get("hypothesis_id") or "").strip()
    statement = str(record.get("hypothesis_statement") or "").strip()
    methodology_tag = str(record.get("methodology_tag") or "").strip().lower() or "evidence_based"
    model_grade = str(record.get("evidence_grade") or "").strip().upper()

    # 专家偏置规则：当 expert_grade 比 model evidence_grade 严格更低时，记一条违规以拉响 bias
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1}
    violations: List[Dict[str, Any]] = []
    downgraded = bool(model_grade) and grade_order.get(grade, 2) < grade_order.get(model_grade, 2)
    if downgraded:
        violations.append(
            {
                "rule_id": f"expert_review:downgrade:{model_grade}->{grade}",
                "severity": "high",
                "expert_review_id": expert_review_id,
            }
        )
    elif grade in {"C", "D"}:
        violations.append(
            {
                "rule_id": f"expert_review:{grade}",
                "severity": severity,
                "expert_review_id": expert_review_id,
            }
        )

    issue_fields: List[str] = ["hypothesis"]
    if methodology_tag:
        issue_fields.append(f"methodology:{methodology_tag}")

    feedback_record = {
        "feedback_scope": "expert_review",
        "source_phase": "expert_review",
        "target_phase": target_phase,
        "feedback_status": "tracked",
        "overall_score": overall_score,
        "grade_level": grade,
        "weakness_count": 1 if grade in {"C", "D"} else 0,
        "strength_count": 1 if grade in {"A", "B"} else 0,
        "weak_phase_names": [target_phase] if grade in {"C", "D"} else [],
        "recorded_phase_names": [target_phase],
        "details": {
            "expert_grade": grade,
            "expert_notes": expert_notes,
            "model_evidence_grade": model_grade or None,
            "downgraded_by_expert": downgraded,
            "hypothesis_id": hypothesis_id,
            "hypothesis_statement": statement,
            "methodology_tag": methodology_tag,
            "four_pass_collation": record.get("four_pass_collation") or {},
            "evidence_bundle": list(record.get("evidence_bundle") or []),
        },
        "metadata": {
            "origin": "expert_review",
            "weight": float(weight),
            "expert_review_id": expert_review_id,
            "severity": severity,
            "source_phase": "hypothesis",
            "issue_fields": issue_fields,
            "violations": violations,
            "graph_targets": [hypothesis_id] if hypothesis_id else [],
        },
    }
    return feedback_record


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _existing_expert_review_ids(repo: ResearchSessionRepository, cycle_id: str) -> set[str]:
    try:
        page = repo.list_learning_feedback(
            cycle_id=cycle_id,
            feedback_scope="expert_review",
            limit=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("查询既有 expert_review 记录失败 (cycle=%s): %s", cycle_id, exc)
        return set()
    seen: set[str] = set()
    for item in (page or {}).get("items", []) or []:
        meta = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        rid = str(meta.get("expert_review_id") or "").strip()
        if rid:
            seen.add(rid)
    return seen


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def import_records(
    *,
    connection_string: str,
    input_path: Path,
    weight: float = DEFAULT_WEIGHT,
    target_phase: str = "hypothesis",
) -> Dict[str, Any]:
    db = DatabaseManager(connection_string)
    db.init_db()
    try:
        return _import_records_with_repo(
            ResearchSessionRepository(db),
            input_path=input_path,
            weight=weight,
            target_phase=target_phase,
        )
    finally:
        if db.engine is not None:
            db.engine.dispose()


def _import_records_with_repo(
    repo: ResearchSessionRepository,
    *,
    input_path: Path,
    weight: float = DEFAULT_WEIGHT,
    target_phase: str = "hypothesis",
) -> Dict[str, Any]:
    parsed = parse_jsonl(input_path)
    inserted = 0
    skipped: List[Dict[str, Any]] = []
    duplicate = 0
    cycles_touched: set[str] = set()

    seen_per_cycle: Dict[str, set[str]] = {}

    for record in parsed:
        reason = _validate(record)
        if reason:
            skipped.append({"reason": reason, "cycle_id": record.get("cycle_id")})
            continue
        cycle_id = str(record["cycle_id"]).strip()
        if cycle_id not in seen_per_cycle:
            seen_per_cycle[cycle_id] = _existing_expert_review_ids(repo, cycle_id)
        review_id = str(record.get("expert_review_id") or "").strip()
        if review_id and review_id in seen_per_cycle[cycle_id]:
            duplicate += 1
            continue

        feedback_record = build_feedback_record(
            record,
            weight=weight,
            target_phase=target_phase,
        )
        try:
            written = repo.append_learning_feedback_record(cycle_id, feedback_record)
        except Exception as exc:  # noqa: BLE001
            logger.exception("写入 expert_review 失败 (cycle=%s): %s", cycle_id, exc)
            skipped.append({"reason": str(exc), "cycle_id": cycle_id})
            continue
        if written is None:
            skipped.append({"reason": "session not found", "cycle_id": cycle_id})
            continue
        inserted += 1
        cycles_touched.add(cycle_id)
        if review_id:
            seen_per_cycle[cycle_id].add(review_id)

    return {
        "input": str(input_path),
        "records_parsed": len(parsed),
        "records_inserted": inserted,
        "records_duplicate": duplicate,
        "records_skipped": skipped,
        "cycles_touched": sorted(cycles_touched),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--connection-string", required=True, help="SQLAlchemy URL")
    parser.add_argument("--input", required=True, help="带 expert_grade 的 JSONL 文件")
    parser.add_argument(
        "--weight",
        type=float,
        default=DEFAULT_WEIGHT,
        help=f"专家反馈权重（写进 metadata.weight），默认 {DEFAULT_WEIGHT}",
    )
    parser.add_argument(
        "--target-phase",
        default="hypothesis",
        help="本批反馈针对的下游阶段（默认 hypothesis）",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    summary = import_records(
        connection_string=args.connection_string,
        input_path=Path(args.input),
        weight=args.weight,
        target_phase=args.target_phase,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
