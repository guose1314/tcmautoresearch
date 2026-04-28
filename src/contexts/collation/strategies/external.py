"""他校（external collation）：调 LiteratureRetriever 抓 arxiv + google_scholar，
结果写入 ``external_evidence`` 表。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


def _record_to_dict(record: Any) -> Dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    # duck typing fallback
    keys = (
        "title",
        "authors",
        "year",
        "doi",
        "url",
        "abstract",
        "citation_count",
        "external_id",
    )
    return {k: getattr(record, k, None) for k in keys}


class ExternalCollationStrategy:
    """他校：抓 arxiv + scholar，落 external_evidence 表。"""

    name = "external"

    def __init__(
        self,
        *,
        literature_retriever: Any = None,
        db_session_factory: Any = None,
        sources: Sequence[str] = ("arxiv", "google_scholar"),
        max_per_source: int = 10,
    ) -> None:
        self._retriever = literature_retriever
        self._session_factory = db_session_factory
        self._sources = tuple(sources)
        self._max_per_source = int(max_per_source)

    def run(self, document_id: str, *, context: Mapping[str, Any]) -> Dict[str, Any]:
        if self._retriever is None:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "LiteratureRetriever not provided",
                "evidence_count": 0,
                "persisted_count": 0,
                "sources": list(self._sources),
            }

        query = str(context.get("query") or context.get("title") or "").strip()
        if not query:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "no query provided",
                "evidence_count": 0,
                "persisted_count": 0,
                "sources": list(self._sources),
            }

        sources = list(context.get("external_sources") or self._sources)
        max_per_source = int(context.get("max_per_source") or self._max_per_source)

        try:
            search_result = self._retriever.search(
                query=query,
                sources=sources,
                max_results_per_source=max_per_source,
                offline_plan_only=bool(context.get("offline_plan_only", False)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("external retrieval failed for doc=%s", document_id)
            return {
                "document_id": document_id,
                "enabled": True,
                "reason": f"retrieval failed: {exc}",
                "evidence_count": 0,
                "persisted_count": 0,
                "sources": sources,
            }

        # LiteratureRetriever.search 返回 {"open_api_results": {source: [LiteratureRecord]}}
        open_api = (search_result or {}).get("open_api_results") or {}
        evidence_records: List[Dict[str, Any]] = []
        for source, records in open_api.items():
            for record in records or []:
                payload = _record_to_dict(record)
                payload.setdefault("source", source)
                evidence_records.append({"source": source, "record": payload})

        persisted = self._persist(document_id, query, evidence_records)
        return {
            "document_id": document_id,
            "enabled": True,
            "evidence_count": len(evidence_records),
            "persisted_count": persisted,
            "sources": sources,
            "query": query,
            "samples": [r["record"].get("title") for r in evidence_records[:3]],
        }

    # ------------------------------------------------------------------ #
    def _persist(
        self, document_id: str, query: str, evidence_records: Iterable[Dict[str, Any]]
    ) -> int:
        if self._session_factory is None:
            return 0
        try:
            from src.infrastructure.persistence import ExternalEvidence
        except Exception:
            logger.warning("ExternalEvidence model unavailable; skip persistence")
            return 0

        try:
            session_cm = self._session_factory()
        except Exception:
            logger.warning("db_session_factory call failed", exc_info=True)
            return 0

        count = 0
        try:
            with session_cm as session:
                for entry in evidence_records:
                    record = entry["record"] or {}
                    obj = ExternalEvidence(
                        document_id=document_id,
                        source=str(
                            entry.get("source") or record.get("source") or "unknown"
                        ),
                        external_id=str(record.get("external_id") or "") or None,
                        title=record.get("title") or None,
                        authors_json=list(record.get("authors") or []),
                        year=record.get("year"),
                        doi=str(record.get("doi") or "") or None,
                        url=str(record.get("url") or "") or None,
                        abstract=record.get("abstract") or None,
                        citation_count=record.get("citation_count"),
                        query=query,
                        relevance_score=record.get("relevance_score"),
                        payload_json=record,
                    )
                    session.add(obj)
                    count += 1
                session.commit() if hasattr(session, "commit") else None
        except Exception:
            logger.exception("persist external_evidence failed")
            return 0
        return count


__all__ = ["ExternalCollationStrategy"]
