from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from src.infra.layered_cache import get_layered_task_cache

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 平台级统一证据对象 — Typed Evidence Dataclasses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTRACT_VERSION = "evidence-claim-v2"

EVIDENCE_GRADES = ("high", "moderate", "low", "very_low")
REVIEW_STATUSES = ("pending", "accepted", "rejected")


@dataclass
class EvidenceProvenance:
    """证据溯源：记录一条证据的来源、版本、引用坐标。"""

    source: str = ""
    source_type: str = ""
    source_ref: str = ""
    document_urn: str = ""
    document_title: str = ""
    work_title: str = ""
    version_lineage_key: str = ""
    witness_key: str = ""
    title: str = ""
    excerpt: str = ""
    doi: str = ""
    url: str = ""
    journal: str = ""
    publisher: str = ""
    year: Any = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    entry_type: str = ""
    note: str = ""
    entity_spans: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceProvenance":
        d = dict(data) if isinstance(data, Mapping) else {}
        return cls(
            source=str(d.get("source") or ""),
            source_type=str(d.get("source_type") or ""),
            source_ref=str(d.get("source_ref") or d.get("document_urn") or ""),
            document_urn=str(d.get("document_urn") or ""),
            document_title=str(d.get("document_title") or ""),
            work_title=str(d.get("work_title") or ""),
            version_lineage_key=str(d.get("version_lineage_key") or ""),
            witness_key=str(d.get("witness_key") or ""),
            title=str(d.get("title") or ""),
            excerpt=str(d.get("excerpt") or d.get("text") or ""),
            doi=str(d.get("doi") or ""),
            url=str(d.get("url") or ""),
            journal=str(d.get("journal") or ""),
            publisher=str(d.get("publisher") or ""),
            year=d.get("year", ""),
            authors=list(d.get("authors") or []),
            abstract=str(d.get("abstract") or ""),
            entry_type=str(d.get("entry_type") or ""),
            note=str(d.get("note") or ""),
            entity_spans=list(d.get("entity_spans") or []),
        )


@dataclass
class EvidenceRecord:
    """单条证据记录 — 平台级统一结构。"""

    evidence_id: str = ""
    source_entity: str = ""
    target_entity: str = ""
    relation_type: str = "related"
    confidence: float = 0.0
    excerpt: str = ""
    entity_spans: List[Dict[str, Any]] = field(default_factory=list)
    evidence_grade: str = ""

    # 引用元数据
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: Any = ""
    journal: str = ""
    publisher: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    note: str = ""

    # 来源标识
    source_type: str = ""
    source_ref: str = ""
    document_title: str = ""
    work_title: str = ""
    version_lineage_key: str = ""
    witness_key: str = ""
    entry_type: str = ""

    # 嵌套溯源
    provenance: EvidenceProvenance = field(default_factory=EvidenceProvenance)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        """从 normalize_evidence_record 返回的 dict 构造类型化对象。"""
        d = dict(data) if isinstance(data, Mapping) else {}
        prov_data = d.pop("provenance", {})
        provenance = EvidenceProvenance.from_dict(prov_data) if isinstance(prov_data, Mapping) else EvidenceProvenance()
        return cls(
            evidence_id=str(d.get("evidence_id") or ""),
            source_entity=str(d.get("source_entity") or ""),
            target_entity=str(d.get("target_entity") or ""),
            relation_type=str(d.get("relation_type") or "related"),
            confidence=float(d.get("confidence") or 0.0),
            excerpt=str(d.get("excerpt") or ""),
            entity_spans=list(d.get("entity_spans") or []),
            evidence_grade=str(d.get("evidence_grade") or ""),
            title=str(d.get("title") or ""),
            authors=list(d.get("authors") or []),
            year=d.get("year", ""),
            journal=str(d.get("journal") or ""),
            publisher=str(d.get("publisher") or ""),
            doi=str(d.get("doi") or ""),
            url=str(d.get("url") or ""),
            abstract=str(d.get("abstract") or ""),
            note=str(d.get("note") or ""),
            source_type=str(d.get("source_type") or ""),
            source_ref=str(d.get("source_ref") or ""),
            document_title=str(d.get("document_title") or ""),
            work_title=str(d.get("work_title") or ""),
            version_lineage_key=str(d.get("version_lineage_key") or ""),
            witness_key=str(d.get("witness_key") or ""),
            entry_type=str(d.get("entry_type") or ""),
            provenance=provenance,
        )


@dataclass
class EvidenceClaim:
    """证据声明 — 将一条或多条 EvidenceRecord 关联到实体关系判断。"""

    claim_id: str = ""
    source_entity: str = ""
    target_entity: str = ""
    relation_type: str = "related"
    confidence: float = 0.0
    support_count: int = 0
    evidence_ids: List[str] = field(default_factory=list)

    document_title: str = ""
    work_title: str = ""
    version_lineage_key: str = ""
    witness_key: str = ""

    # 审核流程
    review_status: str = ""
    needs_manual_review: bool = False
    review_reasons: List[str] = field(default_factory=list)
    reviewer: str = ""
    reviewed_at: str = ""
    decision_basis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceClaim":
        d = dict(data) if isinstance(data, Mapping) else {}
        return cls(
            claim_id=str(d.get("claim_id") or ""),
            source_entity=str(d.get("source_entity") or ""),
            target_entity=str(d.get("target_entity") or ""),
            relation_type=str(d.get("relation_type") or "related"),
            confidence=float(d.get("confidence") or 0.0),
            support_count=int(d.get("support_count") or 0),
            evidence_ids=list(d.get("evidence_ids") or []),
            document_title=str(d.get("document_title") or ""),
            work_title=str(d.get("work_title") or ""),
            version_lineage_key=str(d.get("version_lineage_key") or ""),
            witness_key=str(d.get("witness_key") or ""),
            review_status=str(d.get("review_status") or ""),
            needs_manual_review=bool(d.get("needs_manual_review", False)),
            review_reasons=list(d.get("review_reasons") or []),
            reviewer=str(d.get("reviewer") or ""),
            reviewed_at=str(d.get("reviewed_at") or ""),
            decision_basis=str(d.get("decision_basis") or ""),
        )


@dataclass
class EvidenceGradeSummary:
    """GRADE 评估汇总。"""

    overall_grade: str = ""
    overall_score: float = 0.0
    study_count: int = 0
    factor_averages: Dict[str, float] = field(default_factory=dict)
    bias_risk_distribution: Dict[str, int] = field(default_factory=dict)
    summary: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceGradeSummary":
        d = dict(data) if isinstance(data, Mapping) else {}
        return cls(
            overall_grade=str(d.get("overall_grade") or ""),
            overall_score=float(d.get("overall_score") or 0.0),
            study_count=int(d.get("study_count") or 0),
            factor_averages=dict(d.get("factor_averages") or {}),
            bias_risk_distribution=dict(d.get("bias_risk_distribution") or {}),
            summary=list(d.get("summary") or []),
        )


@dataclass
class EvidenceEnvelope:
    """平台级统一证据信封 — 打包 records + claims + grade + citations。

    这是所有层（analyze / publish / dashboard / API / dossier）交换证据
    的唯一权威容器。
    """

    contract_version: str = CONTRACT_VERSION
    phase_origin: str = ""
    records: List[EvidenceRecord] = field(default_factory=list)
    claims: List[EvidenceClaim] = field(default_factory=list)
    grade_summary: EvidenceGradeSummary = field(default_factory=EvidenceGradeSummary)
    citation_records: List[Dict[str, Any]] = field(default_factory=list)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    research_grade: Dict[str, Any] = field(default_factory=dict)

    # ── 汇总指标 ──
    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def citation_count(self) -> int:
        return len(self.citation_records)

    @property
    def linked_claim_count(self) -> int:
        return sum(1 for c in self.claims if c.evidence_ids)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为与现有 evidence_protocol dict 完全兼容的格式。"""
        records_list = [r.to_dict() for r in self.records]
        claims_list = [c.to_dict() for c in self.claims]
        return {
            "contract_version": self.contract_version,
            "phase_origin": self.phase_origin,
            "evidence_records": records_list,
            "claims": claims_list,
            "evidence_summary": self.evidence_summary,
            "evidence_grade_summary": self.grade_summary.to_dict(),
            "citation_records": list(self.citation_records),
            "citation_count": self.citation_count,
            "research_grade": self.research_grade,
            "summary": _build_protocol_summary(
                records_list, claims_list, self.citation_records,
            ),
            "contract": {
                "required_fields": [
                    "evidence_id", "source_type", "source_ref",
                    "excerpt", "evidence_grade", "provenance",
                ],
                "claim_fields": [
                    "claim_id", "source_entity", "target_entity",
                    "relation_type", "confidence", "support_count", "evidence_ids",
                ],
                "citation_fields": [
                    "title", "authors", "year", "source_type", "source_ref",
                ],
            },
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str, **kwargs)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceEnvelope":
        """从现有 evidence_protocol dict 构造类型化信封。"""
        d = dict(data) if isinstance(data, Mapping) else {}
        records = [
            EvidenceRecord.from_dict(r)
            for r in (d.get("evidence_records") or [])
            if isinstance(r, Mapping)
        ]
        claims = [
            EvidenceClaim.from_dict(c)
            for c in (d.get("claims") or [])
            if isinstance(c, Mapping)
        ]
        grade_summary = EvidenceGradeSummary.from_dict(
            d.get("evidence_grade_summary") or {}
        )
        return cls(
            contract_version=str(d.get("contract_version") or CONTRACT_VERSION),
            phase_origin=str(d.get("phase_origin") or ""),
            records=records,
            claims=claims,
            grade_summary=grade_summary,
            citation_records=list(d.get("citation_records") or []),
            evidence_summary=dict(d.get("evidence_summary") or {}),
            research_grade=dict(d.get("research_grade") or {}),
        )

    @classmethod
    def from_protocol(cls, protocol: Mapping[str, Any]) -> "EvidenceEnvelope":
        """Alias for from_dict — 从 build_evidence_protocol 返回值构建。"""
        return cls.from_dict(protocol)


def build_evidence_protocol(
    reasoning_payload: Any,
    *,
    evidence_records: Optional[Iterable[Any]] = None,
    evidence_grade: Optional[Mapping[str, Any]] = None,
    evidence_summary: Optional[Mapping[str, Any]] = None,
    max_evidence_records: Optional[int] = None,
    max_claims: Optional[int] = None,
) -> Dict[str, Any]:
    resolved_evidence_records = list(evidence_records) if evidence_records is not None else None
    cache_payload = {
        "cache_version": "evidence-cache-v1",
        "contract_version": CONTRACT_VERSION,
        "reasoning_payload": reasoning_payload,
        "evidence_records": resolved_evidence_records,
        "evidence_grade": evidence_grade,
        "evidence_summary": evidence_summary,
        "max_evidence_records": max_evidence_records,
        "max_claims": max_claims,
    }
    task_cache = get_layered_task_cache()
    cached = task_cache.get_json("evidence", "build_evidence_protocol", cache_payload)
    if cached is not None:
        return cached if isinstance(cached, dict) else {}

    protocol = _build_evidence_protocol_uncached(
        reasoning_payload,
        evidence_records=resolved_evidence_records,
        evidence_grade=evidence_grade,
        evidence_summary=evidence_summary,
        max_evidence_records=max_evidence_records,
        max_claims=max_claims,
    )
    task_cache.put_json(
        "evidence",
        "build_evidence_protocol",
        cache_payload,
        protocol,
        meta={
            "contract_version": CONTRACT_VERSION,
            "record_count": len(protocol.get("evidence_records") or []),
            "claim_count": len(protocol.get("claims") or []),
        },
    )
    return protocol


def _build_evidence_protocol_uncached(
    reasoning_payload: Any,
    *,
    evidence_records: Optional[Iterable[Any]] = None,
    evidence_grade: Optional[Mapping[str, Any]] = None,
    evidence_summary: Optional[Mapping[str, Any]] = None,
    max_evidence_records: Optional[int] = None,
    max_claims: Optional[int] = None,
) -> Dict[str, Any]:
    reasoning = _as_dict(reasoning_payload)
    nested_reasoning = _as_dict(reasoning.get("reasoning_results"))

    raw_evidence_records = list(evidence_records) if evidence_records is not None else _as_list(
        reasoning.get("evidence_records") or nested_reasoning.get("evidence_records")
    )
    raw_claims = _as_list(reasoning.get("entity_relationships") or nested_reasoning.get("entity_relationships"))
    raw_evidence_summary = _as_dict(evidence_summary)
    if not raw_evidence_summary:
        raw_evidence_summary = _as_dict(reasoning.get("evidence_summary") or nested_reasoning.get("evidence_summary"))

    evidence_grade_summary = normalize_evidence_grade_summary(
        evidence_grade
        or _as_dict(reasoning.get("evidence_grade"))
        or _as_dict(nested_reasoning.get("evidence_grade"))
    )
    default_evidence_grade = _as_text(evidence_grade_summary.get("overall_grade"))

    normalized_records = [
        normalize_evidence_record(record, default_evidence_grade=default_evidence_grade)
        for record in raw_evidence_records
        if isinstance(record, Mapping)
    ]
    normalized_claims = [
        normalize_claim_record(claim)
        for claim in raw_claims
        if isinstance(claim, Mapping)
    ]

    if max_evidence_records is not None:
        normalized_records = normalized_records[: max(0, int(max_evidence_records))]
    if max_claims is not None:
        normalized_claims = normalized_claims[: max(0, int(max_claims))]

    citation_records = build_citation_records_from_evidence_records(normalized_records)
    research_grade = _build_research_grade_protocol(reasoning, nested_reasoning)

    if not any(
        (
            normalized_records,
            normalized_claims,
            raw_evidence_summary,
            evidence_grade_summary,
            citation_records,
            research_grade,
        )
    ):
        return {}

    return {
        "contract_version": CONTRACT_VERSION,
        "evidence_records": normalized_records,
        "claims": normalized_claims,
        "evidence_summary": raw_evidence_summary,
        "evidence_grade_summary": evidence_grade_summary,
        "citation_records": citation_records,
        "citation_count": len(citation_records),
        "research_grade": research_grade,
        "summary": _build_protocol_summary(normalized_records, normalized_claims, citation_records),
        "contract": {
            "required_fields": [
                "evidence_id",
                "source_type",
                "source_ref",
                "excerpt",
                "evidence_grade",
                "provenance",
            ],
            "claim_fields": [
                "claim_id",
                "source_entity",
                "target_entity",
                "relation_type",
                "confidence",
                "support_count",
                "evidence_ids",
            ],
            "citation_fields": [
                "title",
                "authors",
                "year",
                "source_type",
                "source_ref",
            ],
        },
    }


def normalize_evidence_record(
    record: Mapping[str, Any],
    *,
    default_evidence_grade: str = "",
) -> Dict[str, Any]:
    payload = _as_dict(record)
    provenance = _normalize_provenance(payload.get("provenance"), payload)
    source_entity = _as_text(payload.get("source_entity") or payload.get("source"))
    target_entity = _as_text(payload.get("target_entity") or payload.get("target"))
    relation_type = _as_text(payload.get("relation_type") or payload.get("type") or "related") or "related"
    title = _first_text(
        payload.get("title"),
        payload.get("document_title"),
        provenance.get("title"),
        provenance.get("document_title"),
        provenance.get("work_title"),
    )
    document_title = _first_text(payload.get("document_title"), provenance.get("document_title"), title)
    work_title = _first_text(payload.get("work_title"), provenance.get("work_title"))
    source_type = _first_text(payload.get("source_type"), provenance.get("source_type"), provenance.get("source"))
    source_ref = _first_text(
        payload.get("source_ref"),
        provenance.get("source_ref"),
        provenance.get("document_urn"),
        provenance.get("urn"),
        provenance.get("source_id"),
    )
    evidence_id = _first_text(payload.get("evidence_id"), payload.get("id"))
    if not evidence_id:
        evidence_id = _derive_record_id(source_entity, target_entity, relation_type, title, source_ref)

    normalized = {
        "evidence_id": evidence_id,
        "source_entity": source_entity,
        "target_entity": target_entity,
        "relation_type": relation_type,
        "confidence": _as_float(payload.get("confidence"), 0.0),
        "excerpt": _first_text(
            payload.get("excerpt"),
            payload.get("evidence"),
            provenance.get("excerpt"),
            provenance.get("text"),
            provenance.get("snippet"),
            provenance.get("sentence"),
        ),
        "entity_spans": _normalize_entity_spans(payload.get("entity_spans") or provenance.get("entity_spans")),
        "evidence_grade": _first_text(payload.get("evidence_grade"), default_evidence_grade),
        "title": title,
        "authors": _normalize_string_list(payload.get("authors") or provenance.get("authors")),
        "year": _normalize_year(payload.get("year") or provenance.get("year") or provenance.get("publication_year")),
        "journal": _first_text(payload.get("journal"), provenance.get("journal")),
        "publisher": _first_text(payload.get("publisher"), provenance.get("publisher")),
        "doi": _first_text(payload.get("doi"), provenance.get("doi")),
        "url": _first_text(payload.get("url"), provenance.get("url")),
        "abstract": _first_text(payload.get("abstract"), provenance.get("abstract")),
        "note": _first_text(payload.get("note"), provenance.get("note")),
        "source_type": source_type,
        "source_ref": source_ref,
        "document_title": document_title,
        "work_title": work_title,
        "version_lineage_key": _first_text(payload.get("version_lineage_key"), provenance.get("version_lineage_key")),
        "witness_key": _first_text(payload.get("witness_key"), provenance.get("witness_key")),
        "provenance": provenance,
    }
    entry_type = _first_text(payload.get("entry_type"), provenance.get("entry_type"), _infer_citation_entry_type(normalized))
    if entry_type:
        normalized["entry_type"] = entry_type
    return normalized


def normalize_claim_record(claim: Mapping[str, Any]) -> Dict[str, Any]:
    payload = _as_dict(claim)
    evidence_ids = [
        item
        for item in (_as_text(candidate) for candidate in _as_list(payload.get("evidence_ids")))
        if item
    ]
    source_entity = _as_text(payload.get("source_entity") or payload.get("source"))
    target_entity = _as_text(payload.get("target_entity") or payload.get("target"))
    relation_type = _as_text(payload.get("relation_type") or payload.get("type") or "related") or "related"
    claim_id = _first_text(payload.get("claim_id"), payload.get("id"))
    if not claim_id:
        claim_id = _derive_record_id(source_entity, target_entity, relation_type, "claim", ",".join(evidence_ids))

    support_count = payload.get("support_count")
    try:
        normalized_support_count = int(support_count)
    except (TypeError, ValueError):
        normalized_support_count = len(evidence_ids)

    return {
        "claim_id": claim_id,
        "source_entity": source_entity,
        "target_entity": target_entity,
        "relation_type": relation_type,
        "confidence": _as_float(payload.get("confidence"), 0.0),
        "support_count": normalized_support_count,
        "evidence_ids": evidence_ids,
        "document_title": _as_text(payload.get("document_title")),
        "work_title": _as_text(payload.get("work_title")),
        "version_lineage_key": _as_text(payload.get("version_lineage_key")),
        "witness_key": _as_text(payload.get("witness_key")),
        "review_status": _as_text(payload.get("review_status")),
        "needs_manual_review": bool(payload.get("needs_manual_review", False)),
        "review_reasons": _normalize_string_list(payload.get("review_reasons")),
        "reviewer": _as_text(payload.get("reviewer")),
        "reviewed_at": _as_text(payload.get("reviewed_at")),
        "decision_basis": _as_text(payload.get("decision_basis")),
    }


def build_citation_records_from_evidence_protocol(evidence_protocol: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return build_citation_records_from_evidence_records(
        _as_list(_as_dict(evidence_protocol).get("evidence_records"))
    )


def build_citation_records_from_evidence_records(records: Iterable[Any]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for record in records:
        normalized = record if isinstance(record, dict) else normalize_evidence_record(_as_dict(record))
        title = _first_text(normalized.get("title"), normalized.get("document_title"), normalized.get("work_title"))
        source_ref = _as_text(normalized.get("source_ref"))
        doi = _as_text(normalized.get("doi"))
        url = _as_text(normalized.get("url"))
        if not any((title, source_ref, doi, url)):
            continue

        dedupe_key = (title, source_ref, doi, url)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        note_segments = []
        evidence_id = _as_text(normalized.get("evidence_id"))
        if evidence_id:
            note_segments.append(f"evidence_id={evidence_id}")
        relation_type = _as_text(normalized.get("relation_type"))
        if relation_type:
            note_segments.append(f"relation_type={relation_type}")

        citation = {
            "title": title or source_ref or evidence_id,
            "authors": _normalize_string_list(normalized.get("authors")),
            "year": normalized.get("year"),
            "journal": _as_text(normalized.get("journal")),
            "publisher": _as_text(normalized.get("publisher")),
            "doi": doi,
            "url": url,
            "abstract": _as_text(normalized.get("abstract")),
            "note": "; ".join(note_segments),
            "source": _as_text(normalized.get("source_type") or "evidence_protocol"),
            "source_type": _as_text(normalized.get("source_type")),
            "source_ref": source_ref,
            "entry_type": _as_text(normalized.get("entry_type") or _infer_citation_entry_type(normalized)),
        }
        citations.append(citation)

    return citations


def normalize_evidence_grade_summary(evidence_grade: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    payload = _as_dict(evidence_grade)
    if not payload:
        return {}

    bias_distribution: Dict[str, int] = {}
    for key, value in _as_dict(payload.get("bias_risk_distribution")).items():
        try:
            bias_distribution[str(key)] = int(value)
        except (TypeError, ValueError):
            continue

    factor_averages: Dict[str, float] = {}
    for key, value in _as_dict(payload.get("factor_averages")).items():
        numeric = _as_float(value, None)
        if numeric is None:
            continue
        factor_averages[str(key)] = round(numeric, 4)

    summary_lines = _normalize_string_list(payload.get("summary"))
    study_results = _as_list(payload.get("study_results"))
    study_count = payload.get("study_count")
    try:
        normalized_study_count = int(study_count)
    except (TypeError, ValueError):
        normalized_study_count = len(study_results)

    return {
        "overall_grade": _as_text(payload.get("overall_grade")),
        "overall_score": round(_as_float(payload.get("overall_score"), 0.0), 4),
        "study_count": normalized_study_count,
        "factor_averages": factor_averages,
        "bias_risk_distribution": bias_distribution,
        "summary": summary_lines,
    }


def _build_research_grade_protocol(
    reasoning: Mapping[str, Any],
    nested_reasoning: Mapping[str, Any],
) -> Dict[str, Any]:
    diagnostics = _as_dict(reasoning.get("research_grade_diagnostics") or nested_reasoning.get("research_grade_diagnostics"))
    fusion = _as_dict(reasoning.get("multimodal_fusion") or nested_reasoning.get("multimodal_fusion"))
    if not diagnostics and not fusion:
        return {}
    return {
        "diagnostics": diagnostics,
        "fusion": {
            "confidence": _as_float(fusion.get("confidence"), 0.0),
            "evidence_score": _as_float(fusion.get("evidence_score"), 0.0),
            "strategy": _as_text(fusion.get("strategy") or "attention"),
        },
    }


def _build_protocol_summary(
    evidence_records: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    citation_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    source_type_counts: Dict[str, int] = {}
    relation_type_counts: Dict[str, int] = {}
    linked_claim_count = 0

    for record in evidence_records:
        source_type = _as_text(record.get("source_type")) or "unknown"
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        relation_type = _as_text(record.get("relation_type")) or "related"
        relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

    for claim in claims:
        if _as_list(claim.get("evidence_ids")):
            linked_claim_count += 1

    return {
        "evidence_record_count": len(evidence_records),
        "claim_count": len(claims),
        "citation_count": len(citation_records),
        "source_type_counts": source_type_counts,
        "relation_type_counts": relation_type_counts,
        "linked_claim_count": linked_claim_count,
    }


def _normalize_provenance(value: Any, record: Mapping[str, Any]) -> Dict[str, Any]:
    provenance = _as_dict(value)
    field_map = {
        "source": "source",
        "source_type": "source_type",
        "source_ref": "source_ref",
        "document_urn": "document_urn",
        "document_title": "document_title",
        "work_title": "work_title",
        "version_lineage_key": "version_lineage_key",
        "witness_key": "witness_key",
        "title": "title",
        "excerpt": "excerpt",
        "text": "text",
        "doi": "doi",
        "url": "url",
        "journal": "journal",
        "publisher": "publisher",
        "year": "year",
        "publication_year": "publication_year",
        "authors": "authors",
        "abstract": "abstract",
        "entry_type": "entry_type",
        "note": "note",
        "entity_spans": "entity_spans",
    }
    for target_key, source_key in field_map.items():
        if target_key in provenance and provenance.get(target_key) not in (None, "", [], {}):
            continue
        candidate = record.get(source_key)
        if candidate in (None, "", [], {}):
            continue
        provenance[target_key] = candidate
    return provenance


def _infer_citation_entry_type(record: Mapping[str, Any]) -> str:
    journal = _as_text(record.get("journal"))
    publisher = _as_text(record.get("publisher"))
    if journal:
        return "article"
    if publisher:
        return "book"
    return "misc"


def _derive_record_id(
    source_entity: str,
    target_entity: str,
    relation_type: str,
    title: str,
    source_ref: str,
) -> str:
    parts = [source_entity, target_entity, relation_type, title or source_ref or "evidence"]
    normalized_parts = [_slugify(part) for part in parts if part]
    if not normalized_parts:
        return "derived:evidence"
    return "derived:" + ":".join(normalized_parts)


def _slugify(value: Any) -> str:
    text = _as_text(value).lower().replace(" ", "_")
    allowed = []
    for char in text:
        if char.isalnum() or char in {"_", "-", ":"}:
            allowed.append(char)
    return "".join(allowed)[:64] or "item"


def _normalize_entity_spans(value: Any) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, Mapping):
            continue
        spans.append(dict(item))
    return spans


def _normalize_string_list(value: Any) -> List[str]:
    normalized: List[str] = []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    for item in _as_list(value):
        text = _as_text(item)
        if text:
            normalized.append(text)
    return normalized


def _normalize_year(value: Any) -> Any:
    if value in (None, ""):
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return _as_text(value)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase-level lightweight evidence protocol builder  (Phase F-1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_phase_evidence_protocol(
    phase: str,
    *,
    evidence_records: Optional[Iterable[Mapping[str, Any]]] = None,
    claims: Optional[Iterable[Mapping[str, Any]]] = None,
    evidence_grade: str = "preliminary",
    evidence_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """为非 analyze 阶段构建轻量 evidence_protocol。

    与 ``build_evidence_protocol`` 不同，此函数不需要 reasoning_payload，
    也不做缓存，适合 observe / hypothesis / experiment_execution / reflect
    这类阶段把自己产出的线索归并到 evidence-claim-v2 信封里。

    返回值与 ``build_evidence_protocol`` 形状兼容，可直接放入
    ``PhaseResult.results["evidence_protocol"]``。
    """
    raw_records = [
        normalize_evidence_record(r, default_evidence_grade=evidence_grade)
        for r in (evidence_records or [])
        if isinstance(r, Mapping)
    ]
    raw_claims = [
        normalize_claim_record(c)
        for c in (claims or [])
        if isinstance(c, Mapping)
    ]
    citation_records = build_citation_records_from_evidence_records(raw_records)
    grade_summary = normalize_evidence_grade_summary(
        {"overall_grade": evidence_grade}
    )
    summary = _build_protocol_summary(raw_records, raw_claims, citation_records)

    return {
        "contract_version": CONTRACT_VERSION,
        "phase_origin": str(phase),
        "evidence_records": raw_records,
        "claims": raw_claims,
        "evidence_summary": dict(evidence_summary or {}),
        "evidence_grade_summary": grade_summary,
        "citation_records": citation_records,
        "citation_count": len(citation_records),
        "research_grade": {},
        "summary": summary,
    }