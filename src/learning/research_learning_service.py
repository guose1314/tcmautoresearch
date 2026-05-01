from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.contexts.lfitl.feedback_translator import PromptBiasAction, TranslationPlan
from src.contexts.lfitl.prompt_bias_compiler import PromptBiasCompiler
from src.learning.learning_insight_repo import STATUS_ACTIVE

logger = logging.getLogger(__name__)

RESEARCH_LEARNING_SERVICE_CONTRACT_VERSION = "research-learning-service-v1"
DEFAULT_GRAPH_PATTERN_SOURCE = "neo4j_graph_pattern_miner"
DEFAULT_PG_ASSET_SOURCE = "pg_asset_miner"


class ResearchLearningService:
    """Coordinates PG/Neo4j learning mining and LFITL prompt-bias output."""

    def __init__(
        self,
        *,
        learning_insight_repo: Any = None,
        graph_miner: Any = None,
        pg_asset_miner: Any = None,
        feedback_repo: Any = None,
        prompt_bias_compiler: Any = None,
        active_insight_limit: int = 100,
        min_prompt_bias_confidence: float = 0.0,
    ) -> None:
        self._learning_insight_repo = learning_insight_repo
        self._graph_miner = graph_miner
        self._pg_asset_miner = pg_asset_miner
        self._feedback_repo = feedback_repo
        self._prompt_bias_compiler = prompt_bias_compiler or PromptBiasCompiler()
        self._active_insight_limit = max(int(active_insight_limit or 0), 0)
        self._min_prompt_bias_confidence = max(
            0.0, min(1.0, float(min_prompt_bias_confidence or 0.0))
        )
        self._last_run_insights: List[Dict[str, Any]] = []

    def run_cycle_learning(self, cycle_id: str) -> Dict[str, Any]:
        normalized_cycle_id = _text(cycle_id) or "unknown-cycle"
        warnings: List[str] = []

        pg_insights = self.mine_pg_assets(normalized_cycle_id)
        neo4j_insights = self.mine_neo4j_patterns(normalized_cycle_id)
        insights = _dedupe_insights([*pg_insights, *neo4j_insights])
        self._last_run_insights = insights

        compiled = self.compile_prompt_bias(normalized_cycle_id, insights=insights)
        warnings.extend(compiled.get("warnings") or [])
        policy_summary = {
            "cycle_id": normalized_cycle_id,
            "insight_count": len(insights),
            "pg_insight_count": len(pg_insights),
            "neo4j_insight_count": len(neo4j_insights),
            "prompt_bias_phase_count": len(compiled.get("prompt_bias_blocks") or {}),
            "prompt_bias_phases": sorted(
                (compiled.get("prompt_bias_blocks") or {}).keys()
            ),
            "policy_adjustment_mode": "prompt_bias_only",
            "warnings": list(warnings),
        }

        return {
            "contract_version": RESEARCH_LEARNING_SERVICE_CONTRACT_VERSION,
            "cycle_id": normalized_cycle_id,
            "insights": insights,
            "pg_insights": pg_insights,
            "neo4j_insights": neo4j_insights,
            "prompt_bias_blocks": compiled.get("prompt_bias_blocks") or {},
            "lfitl_plan": compiled.get("lfitl_plan") or {},
            "policy_adjustment_summary": policy_summary,
            "warnings": list(warnings),
        }

    def mine_pg_assets(self, cycle_id: str) -> List[Dict[str, Any]]:
        normalized_cycle_id = _text(cycle_id) or "unknown-cycle"
        raw_items: Sequence[Any] = []
        if self._pg_asset_miner is not None:
            raw_items = self._call_miner(
                self._pg_asset_miner,
                ("mine_pg_assets", "mine", "run"),
                normalized_cycle_id,
            )
        elif self._feedback_repo is not None:
            raw_items = self._read_feedback_items(normalized_cycle_id)

        insights = [
            _normalize_insight_payload(
                item,
                cycle_id=normalized_cycle_id,
                default_source=DEFAULT_PG_ASSET_SOURCE,
                default_phase="reflect",
                index=index,
            )
            for index, item in enumerate(raw_items or [])
        ]
        return self._persist_insights(insights)

    def mine_neo4j_patterns(self, cycle_id: str) -> List[Dict[str, Any]]:
        normalized_cycle_id = _text(cycle_id) or "unknown-cycle"
        if self._graph_miner is None:
            return []

        if hasattr(self._graph_miner, "mine_learning_insights"):
            try:
                raw_insights = self._graph_miner.mine_learning_insights(
                    cycle_id=normalized_cycle_id
                )
            except TypeError:
                raw_insights = self._graph_miner.mine_learning_insights()
            except Exception as exc:  # noqa: BLE001
                logger.warning("graph miner mine_learning_insights failed: %s", exc)
                raw_insights = []
            insights = [
                _normalize_insight_payload(
                    item,
                    cycle_id=normalized_cycle_id,
                    default_source=DEFAULT_GRAPH_PATTERN_SOURCE,
                    default_phase="hypothesis",
                    index=index,
                )
                for index, item in enumerate(raw_insights or [])
            ]
            return self._persist_insights(insights)

        patterns = self._call_miner(
            self._graph_miner,
            ("execute_incremental_mining", "mine"),
            normalized_cycle_id,
        )
        insights = [
            _pattern_to_learning_insight(pattern, normalized_cycle_id, index)
            for index, pattern in enumerate(patterns or [])
        ]
        return self._persist_insights(insights)

    def compile_prompt_bias(
        self,
        cycle_id: str,
        *,
        insights: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        normalized_cycle_id = _text(cycle_id) or "unknown-cycle"
        source_insights = (
            list(insights) if insights is not None else self._load_active_insights()
        )
        eligible = [
            dict(item)
            for item in source_insights
            if _text(item.get("status") or STATUS_ACTIVE) == STATUS_ACTIVE
            and _confidence(item.get("confidence")) >= self._min_prompt_bias_confidence
        ]
        actions = _build_prompt_bias_actions(eligible)
        plan = TranslationPlan(
            prompt_bias_actions=actions,
            mined_patterns=[
                _extract_pattern_ref(item)
                for item in eligible
                if item.get("source") == DEFAULT_GRAPH_PATTERN_SOURCE
            ],
            summary={
                "cycle_id": normalized_cycle_id,
                "insight_count": len(eligible),
                "prompt_bias_action_count": len(actions),
                "phases_touched": sorted({action.purpose for action in actions}),
            },
        )
        warnings: List[str] = []
        try:
            prompt_bias_blocks = self._prompt_bias_compiler.compile(plan)
        except Exception as exc:  # noqa: BLE001
            logger.warning("research learning prompt bias compile failed: %s", exc)
            prompt_bias_blocks = {}
            warnings.append(f"prompt_bias_compile_failed:{type(exc).__name__}: {exc}")
        return {
            "cycle_id": normalized_cycle_id,
            "prompt_bias_blocks": prompt_bias_blocks,
            "lfitl_plan": plan.to_dict(),
            "insights": eligible,
            "warnings": warnings,
        }

    def _persist_insights(
        self, insights: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        persisted: List[Dict[str, Any]] = []
        for item in insights or []:
            normalized = dict(item)
            if self._learning_insight_repo is None:
                persisted.append(normalized)
                continue
            try:
                stored = self._learning_insight_repo.upsert(normalized)
            except Exception as exc:  # noqa: BLE001
                logger.warning("learning insight upsert failed: %s", exc)
                persisted.append({**normalized, "persist_error": str(exc)})
                continue
            persisted.append(dict(stored or normalized))
        return persisted

    def _load_active_insights(self) -> List[Dict[str, Any]]:
        if self._learning_insight_repo is None:
            return list(self._last_run_insights)
        try:
            return list(
                self._learning_insight_repo.list_active(
                    limit=self._active_insight_limit
                )
            )
        except TypeError:
            return list(self._learning_insight_repo.list_active())
        except Exception as exc:  # noqa: BLE001
            logger.warning("learning insight list_active failed: %s", exc)
            return list(self._last_run_insights)

    @staticmethod
    def _call_miner(
        target: Any, method_names: Sequence[str], cycle_id: str
    ) -> List[Any]:
        for method_name in method_names:
            method = getattr(target, method_name, None)
            if not callable(method):
                continue
            try:
                return list(method(cycle_id=cycle_id))
            except TypeError:
                try:
                    return list(method(cycle_id))
                except TypeError:
                    return list(method())
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "research learning miner %s failed: %s", method_name, exc
                )
                return []
        return []

    def _read_feedback_items(self, cycle_id: str) -> List[Any]:
        repo = self._feedback_repo
        if repo is None:
            return []
        if hasattr(repo, "list_learning_feedback"):
            try:
                payload = repo.list_learning_feedback(cycle_id=cycle_id, limit=100)
                if isinstance(payload, Mapping):
                    return list(payload.get("items") or [])
                return list(payload or [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("feedback repo list_learning_feedback failed: %s", exc)
        if hasattr(repo, "recent"):
            try:
                return list(repo.recent(limit=100) or [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("feedback repo recent failed: %s", exc)
        return []


def _build_prompt_bias_actions(
    insights: Sequence[Mapping[str, Any]],
) -> List[PromptBiasAction]:
    per_phase: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for item in insights:
        phase = _text(item.get("target_phase")) or "hypothesis"
        per_phase[phase].append(item)

    actions: List[PromptBiasAction] = []
    for phase, phase_insights in sorted(per_phase.items()):
        descriptions = [_text(item.get("description")) for item in phase_insights]
        descriptions = [item for item in descriptions if item]
        if not descriptions:
            continue
        bias_text = "学习洞察提示：" + " ".join(
            f"{index}. {description}"
            for index, description in enumerate(descriptions[:8], start=1)
        )
        insight_types = sorted(
            {
                _text(item.get("insight_type"))
                for item in phase_insights
                if item.get("insight_type")
            }
        )
        actions.append(
            PromptBiasAction(
                purpose=phase,
                bias_text=bias_text,
                avoid_fields=insight_types,
                severity=_max_severity(phase_insights),
            )
        )
    return actions


def _normalize_insight_payload(
    item: Any,
    *,
    cycle_id: str,
    default_source: str,
    default_phase: str,
    index: int,
) -> Dict[str, Any]:
    payload = _to_dict(item)
    if _looks_like_graph_pattern(payload):
        return _pattern_to_learning_insight(payload, cycle_id, index)
    description = _text(
        payload.get("description")
        or payload.get("bias_text")
        or payload.get("summary")
        or payload.get("expert_notes")
    )
    if not description:
        description = _describe_feedback(payload) or f"PG 学习资产 #{index + 1}"
    source = _text(payload.get("source")) or default_source
    target_phase = (
        _text(
            payload.get("target_phase")
            or payload.get("phase")
            or payload.get("source_phase")
        )
        or default_phase
    )
    insight_type = _text(payload.get("insight_type")) or "prompt_bias"
    insight_id = _text(payload.get("insight_id")) or _stable_insight_id(
        source, cycle_id, target_phase, description, index
    )
    return {
        "insight_id": insight_id,
        "source": source,
        "target_phase": target_phase,
        "insight_type": insight_type,
        "description": description,
        "confidence": _confidence(payload.get("confidence"), payload),
        "evidence_refs_json": _normalize_evidence_refs(
            payload.get("evidence_refs_json") or payload.get("evidence_refs") or payload
        ),
        "status": _text(payload.get("status")) or STATUS_ACTIVE,
        "expires_at": payload.get("expires_at"),
        "created_at": payload.get("created_at") or _now_iso(),
    }


def _pattern_to_learning_insight(
    pattern: Any, cycle_id: str, index: int
) -> Dict[str, Any]:
    payload = _to_dict(pattern)
    herb = _text(payload.get("herb"))
    prescription = _text(payload.get("prescription") or payload.get("formula"))
    symptom = _text(payload.get("symptom") or payload.get("syndrome"))
    if herb or prescription or symptom:
        description = (
            f"配伍规律: 【{prescription or '某方'}】常包含【{herb or '某药'}】"
            f"用于治疗【{symptom or '相关证候'}】。"
        )
        confidence = _confidence(payload.get("confidence"), payload)
    else:
        labels = list(payload.get("node_labels") or [])
        rels = list(payload.get("rel_types") or [])
        shape = "->".join(str(item) for item in labels if str(item).strip())
        rel_text = "/".join(str(item) for item in rels if str(item).strip())
        description = (
            f"高频图模式提示: {shape or 'unknown-shape'} {rel_text or ''}".strip()
        )
        confidence = _confidence(payload.get("confidence"), payload)
    return {
        "insight_id": _text(payload.get("insight_id"))
        or _stable_insight_id(
            DEFAULT_GRAPH_PATTERN_SOURCE, cycle_id, "hypothesis", description, index
        ),
        "source": _text(payload.get("source")) or DEFAULT_GRAPH_PATTERN_SOURCE,
        "target_phase": _text(payload.get("target_phase")) or "hypothesis",
        "insight_type": _text(payload.get("insight_type")) or "prompt_bias",
        "description": description,
        "confidence": confidence,
        "evidence_refs_json": _normalize_evidence_refs(payload),
        "status": _text(payload.get("status")) or STATUS_ACTIVE,
        "expires_at": payload.get("expires_at"),
        "created_at": payload.get("created_at") or _now_iso(),
    }


def _describe_feedback(payload: Mapping[str, Any]) -> str:
    issue_fields = [
        str(item) for item in payload.get("issue_fields") or [] if str(item).strip()
    ]
    violations = [
        _text((item or {}).get("rule_id"))
        for item in payload.get("violations") or []
        if isinstance(item, Mapping)
    ]
    parts: List[str] = []
    if issue_fields:
        parts.append("关注历史问题字段: " + "、".join(issue_fields))
    if violations:
        parts.append(
            "避免再次触发规则: " + "、".join(item for item in violations if item)
        )
    return "；".join(parts)


def _normalize_evidence_refs(value: Any) -> List[Dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return [{"ref": str(value)}]


def _extract_pattern_ref(item: Mapping[str, Any]) -> Dict[str, Any]:
    refs = item.get("evidence_refs_json") or []
    first = refs[0] if isinstance(refs, list) and refs else {}
    return dict(first) if isinstance(first, Mapping) else {}


def _dedupe_insights(insights: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in insights:
        insight_id = _text(item.get("insight_id"))
        if not insight_id or insight_id in seen:
            continue
        seen.add(insight_id)
        deduped.append(dict(item))
    return deduped


def _looks_like_graph_pattern(payload: Mapping[str, Any]) -> bool:
    return any(
        key in payload
        for key in ("herb", "prescription", "symptom", "node_labels", "rel_types")
    )


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        try:
            payload = value.to_dict()
            return dict(payload) if isinstance(payload, Mapping) else {}
        except Exception:
            return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_insight_id(
    source: str, cycle_id: str, phase: str, text: str, index: int
) -> str:
    seed = f"{source}|{cycle_id}|{phase}|{text}|{index}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{cycle_id}:{phase}:{digest}"[:128]


def _confidence(value: Any, payload: Optional[Mapping[str, Any]] = None) -> float:
    if value in (None, "") and payload is not None:
        value = (
            payload.get("occurrence_freq")
            or payload.get("support")
            or payload.get("overall_score")
        )
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    if confidence > 1.0:
        confidence = confidence / 100.0
    return round(max(0.0, min(1.0, confidence)), 4)


def _max_severity(insights: Sequence[Mapping[str, Any]]) -> str:
    severity_by_confidence = "low"
    max_confidence = max(
        (_confidence(item.get("confidence")) for item in insights), default=0.0
    )
    if max_confidence >= 0.85:
        severity_by_confidence = "high"
    elif max_confidence >= 0.5:
        severity_by_confidence = "medium"
    explicit = [
        _text(item.get("severity")) for item in insights if item.get("severity")
    ]
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    candidates = [severity_by_confidence, *explicit]
    return max(candidates, key=lambda item: order.get(item, 0))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_GRAPH_PATTERN_SOURCE",
    "DEFAULT_PG_ASSET_SOURCE",
    "RESEARCH_LEARNING_SERVICE_CONTRACT_VERSION",
    "ResearchLearningService",
]
