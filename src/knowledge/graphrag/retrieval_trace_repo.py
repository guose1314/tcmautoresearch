from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

RETRIEVAL_TRACE_REPO_VERSION = "graphrag-retrieval-trace-repo-v1"


class RetrievalTraceRepo:
    def __init__(
        self,
        *,
        cache_dir: Optional[str | Path] = None,
        log_path: Optional[str | Path] = None,
        max_cache_size: int = 256,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._cache_dir = Path(
            cache_dir or repo_root / "cache" / "graphrag" / "retrieval_traces"
        )
        self._log_path = Path(
            log_path or repo_root / "logs" / "graphrag_retrieval_traces.jsonl"
        )
        self._max_cache_size = max(1, int(max_cache_size or 1))
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def record_retrieval(
        self,
        result: Mapping[str, Any],
        *,
        query: str,
        cycle_id: str = "",
        phase: str = "analyze",
        task_id: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_result = _normalize_result(result)
        request_key = _request_key(
            normalized_result,
            query=query,
            cycle_id=cycle_id,
            phase=phase,
            task_id=task_id,
        )
        cached = self._memory_cache.get(request_key)
        if cached is not None:
            self._memory_cache.move_to_end(request_key)
            return {**dict(cached), "cache_hit": True}

        trace_id = _trace_id(request_key)
        trace_file = self._cache_dir / f"{trace_id}.json"
        if trace_file.exists():
            payload = self.load_trace(trace_id) or {}
            summary = _trace_summary(trace_id, trace_file, self._log_path, payload)
            summary["cache_hit"] = True
            self._remember(request_key, summary)
            return summary

        trace_payload = _build_trace_payload(
            normalized_result,
            trace_id=trace_id,
            query=query,
            cycle_id=cycle_id,
            phase=phase,
            task_id=task_id,
            metadata=metadata,
        )
        self._persist_trace(trace_file, trace_payload)
        summary = _trace_summary(trace_id, trace_file, self._log_path, trace_payload)
        summary["cache_hit"] = False
        self._remember(request_key, summary)
        return summary

    def load_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        file_path = self._cache_dir / f"{str(trace_id).strip()}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))

    def _persist_trace(self, trace_file: Path, payload: Mapping[str, Any]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "trace_id": payload.get("trace_id"),
                        "created_at": payload.get("created_at"),
                        "phase": payload.get("phase"),
                        "cycle_id": payload.get("cycle_id"),
                        "query": payload.get("query"),
                        "scope": payload.get("scope"),
                        "asset_type": payload.get("asset_type"),
                        "node_count": len(payload.get("node_ids") or []),
                        "relationship_count": len(
                            payload.get("relationship_ids") or []
                        ),
                        "fragment_count": len(payload.get("evidence_fragments") or []),
                        "insight_count": len(payload.get("insights") or []),
                        "prompt_entry_count": len(payload.get("prompt_entries") or []),
                        "contract_version": RETRIEVAL_TRACE_REPO_VERSION,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _remember(self, request_key: str, summary: Mapping[str, Any]) -> None:
        self._memory_cache[request_key] = dict(summary)
        self._memory_cache.move_to_end(request_key)
        while len(self._memory_cache) > self._max_cache_size:
            self._memory_cache.popitem(last=False)


def _normalize_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(result or {})
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    normalized_items = [dict(item) for item in items if isinstance(item, Mapping)]
    if not normalized_items and (
        str(payload.get("body") or "").strip() or payload.get("citations")
    ):
        normalized_items = [
            {
                "tier": str(
                    payload.get("asset_type") or payload.get("scope") or "graph_rag"
                ),
                "source": str(
                    payload.get("asset_type") or payload.get("scope") or "graph_rag"
                ),
                "body": str(payload.get("body") or ""),
                "confidence": float(payload.get("confidence") or 0.0),
                "expert_reviewed": False,
                "citations": [
                    dict(item)
                    for item in payload.get("citations") or []
                    if isinstance(item, Mapping)
                ],
                "traceability": dict(payload.get("traceability") or {}),
                "metadata": dict(payload.get("metadata") or {}),
            }
        ]
    return {
        "scope": str(payload.get("scope") or ""),
        "asset_type": str(payload.get("asset_type") or ""),
        "body": str(payload.get("body") or ""),
        "items": normalized_items,
        "citations": [
            dict(item)
            for item in payload.get("citations") or []
            if isinstance(item, Mapping)
        ],
        "traceability": dict(payload.get("traceability") or {}),
        "metadata": dict(payload.get("metadata") or {}),
        "token_count": int(payload.get("token_count") or 0),
        "truncated": bool(payload.get("truncated", False)),
    }


def _build_trace_payload(
    result: Mapping[str, Any],
    *,
    trace_id: str,
    query: str,
    cycle_id: str,
    phase: str,
    task_id: str,
    metadata: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    items = [
        dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)
    ]
    prompt_entries = _build_prompt_entries(items, str(result.get("body") or ""))
    citations = [
        dict(item)
        for item in result.get("citations") or []
        if isinstance(item, Mapping)
    ]
    result_traceability = result.get("traceability") or {}
    node_values = list(result_traceability.get("node_ids") or [])
    node_values.extend(
        value
        for item in items
        for value in ((item.get("traceability") or {}).get("node_ids") or [])
    )
    node_ids = _unique_strings(node_values)
    relationship_values = list(result_traceability.get("relationship_ids") or [])
    relationship_values.extend(
        value
        for item in items
        for value in ((item.get("traceability") or {}).get("relationship_ids") or [])
    )
    relationship_ids = _unique_strings(relationship_values)
    evidence_fragments = _evidence_fragments(items, citations)
    insights = _insight_entries(items, citations)
    return {
        "trace_id": trace_id,
        "contract_version": RETRIEVAL_TRACE_REPO_VERSION,
        "created_at": _now_iso(),
        "phase": str(phase or "analyze"),
        "task_id": str(task_id or ""),
        "cycle_id": str(cycle_id or ""),
        "query": str(query or ""),
        "scope": str(result.get("scope") or ""),
        "asset_type": str(result.get("asset_type") or ""),
        "token_count": int(result.get("token_count") or 0),
        "truncated": bool(result.get("truncated", False)),
        "prompt_body": str(result.get("body") or ""),
        "prompt_entries": prompt_entries,
        "items": items,
        "citations": citations,
        "traceability": dict(result.get("traceability") or {}),
        "node_ids": node_ids,
        "relationship_ids": relationship_ids,
        "evidence_fragments": evidence_fragments,
        "insights": insights,
        "metadata": dict(metadata or {}),
    }


def _build_prompt_entries(
    items: List[Dict[str, Any]],
    prompt_body: str,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    ranked: List[tuple[int, Dict[str, Any]]] = []
    for index, item in enumerate(items):
        tier = str(item.get("tier") or item.get("source") or f"entry-{index}")
        marker = f"[{tier}]"
        position = prompt_body.find(marker) if prompt_body else -1
        rank = position if position >= 0 else len(prompt_body) + index
        ranked.append((rank, item))
    for prompt_rank, (_, item) in enumerate(
        sorted(ranked, key=lambda value: value[0]), start=1
    ):
        body = str(item.get("body") or "").strip()
        citations = [
            dict(value)
            for value in item.get("citations") or []
            if isinstance(value, Mapping)
        ]
        entries.append(
            {
                "prompt_rank": prompt_rank,
                "tier": str(item.get("tier") or ""),
                "source": str(item.get("source") or ""),
                "included_in_prompt": bool(body),
                "confidence": float(item.get("confidence") or 0.0),
                "expert_reviewed": bool(item.get("expert_reviewed", False)),
                "excerpt": body[:240],
                "citation_ids": _unique_strings(
                    [value.get("id") or value.get("topic_key") for value in citations]
                ),
                "node_ids": _unique_strings(
                    ((item.get("traceability") or {}).get("node_ids") or [])
                ),
                "relationship_ids": _unique_strings(
                    ((item.get("traceability") or {}).get("relationship_ids") or [])
                ),
            }
        )
    return entries


def _evidence_fragments(
    items: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fragments: List[Dict[str, Any]] = []
    for entry in citations:
        fragments.append(
            {
                "id": str(entry.get("id") or entry.get("topic_key") or ""),
                "type": str(entry.get("type") or "citation"),
                "tier": str(entry.get("tier") or ""),
                "source": str(entry.get("source") or ""),
            }
        )
    for item in items:
        if str(item.get("tier") or "") != "segment":
            continue
        fragments.append(
            {
                "id": str(item.get("source") or item.get("tier") or "segment"),
                "type": "prompt_segment",
                "tier": str(item.get("tier") or "segment"),
                "source": str(item.get("source") or ""),
                "excerpt": str(item.get("body") or "")[:240],
            }
        )
    return _dedupe_dicts(fragments)


def _insight_entries(
    items: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    for item in items:
        tier = str(item.get("tier") or "")
        if tier != "expert_insight":
            continue
        insights.append(
            {
                "tier": tier,
                "source": str(item.get("source") or ""),
                "excerpt": str(item.get("body") or "")[:240],
                "node_ids": _unique_strings(
                    ((item.get("traceability") or {}).get("node_ids") or [])
                ),
                "relationship_ids": _unique_strings(
                    ((item.get("traceability") or {}).get("relationship_ids") or [])
                ),
            }
        )
    for citation in citations:
        citation_type = str(citation.get("type") or "").lower()
        if "claim" not in citation_type and "insight" not in citation_type:
            continue
        insights.append(
            {
                "id": str(citation.get("id") or ""),
                "type": str(citation.get("type") or ""),
                "tier": str(citation.get("tier") or ""),
                "source": str(citation.get("source") or ""),
            }
        )
    return _dedupe_dicts(insights)


def _request_key(
    result: Mapping[str, Any],
    *,
    query: str,
    cycle_id: str,
    phase: str,
    task_id: str,
) -> str:
    payload = {
        "query": str(query or ""),
        "cycle_id": str(cycle_id or ""),
        "phase": str(phase or ""),
        "task_id": str(task_id or ""),
        "scope": str(result.get("scope") or ""),
        "asset_type": str(result.get("asset_type") or ""),
        "items": result.get("items") or [],
        "citations": result.get("citations") or [],
        "traceability": result.get("traceability") or {},
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _trace_id(request_key: str) -> str:
    return f"graphrag-trace:{request_key[:20]}"


def _trace_summary(
    trace_id: str,
    trace_file: Path,
    log_path: Path,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "trace_id": trace_id,
        "trace_file": str(trace_file),
        "log_path": str(log_path),
        "created_at": payload.get("created_at"),
        "contract_version": RETRIEVAL_TRACE_REPO_VERSION,
    }


def _unique_strings(values: Any) -> List[str]:
    items: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _dedupe_dicts(values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["RETRIEVAL_TRACE_REPO_VERSION", "RetrievalTraceRepo"]
