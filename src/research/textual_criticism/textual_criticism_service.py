"""textual_criticism 子阶段服务实现 — 把"考据"从隐式判断变为可审计裁定。

主入口:
  assess_catalog_authenticity(catalog_entry, *, llm_caller=None) -> AuthenticityVerdict
  assess_catalog_batch(catalog_entries, *, llm_caller=None) -> list[AuthenticityVerdict]

实现策略（J-2 范围，纯规则可测）:
  1. 年代裁定: 朝代字段 / 著录时代 → DATE_VERDICTS 五分类
     - "佚名"/"传"/"托名" 触发 LEGENDARY
     - 朝代明确 → CONFIRMED
     - 仅朝代区间（汉/唐宋之际）→ RANGE
     - 关键词命中"伪/疑/争议" → DISPUTED
  2. 作者裁定:
     - 字段含"佚名"/空 → ANONYMOUS
     - "传 X 撰"/"X 旧题" → ATTRIBUTED
     - 字段含"伪托"/"疑伪" → DISPUTED
     - 否则 → CONFIRMED
  3. 真伪裁定:
     - LEGENDARY + DISPUTED → FORGED
     - DISPUTED 单独 → DOUBTFUL
     - CONFIRMED 双双 → AUTHENTIC
     - 其它 → INDETERMINATE
  4. 置信度: 基础分 + 证据条数加权
  5. 可选 LLM 注入: llm_caller(prompt) -> str 仅用于裁定理由文本润色
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence

from src.research.textual_criticism.verdict_contract import (
    AUTHENTICITY_AUTHENTIC,
    AUTHENTICITY_DOUBTFUL,
    AUTHENTICITY_FORGED,
    AUTHENTICITY_INDETERMINATE,
    AUTHOR_VERDICT_ANONYMOUS,
    AUTHOR_VERDICT_ATTRIBUTED,
    AUTHOR_VERDICT_CONFIRMED,
    AUTHOR_VERDICT_DISPUTED,
    DATE_VERDICT_CONFIRMED,
    DATE_VERDICT_DISPUTED,
    DATE_VERDICT_LEGENDARY,
    DATE_VERDICT_RANGE,
    DATE_VERDICT_UNKNOWN,
    AuthenticityVerdict,
    VerdictEvidence,
    normalize_authenticity_verdicts,
)

LLMCaller = Callable[[str], str]

# 朝代关键词集合（按可识别度排序）
_DYNASTY_KEYWORDS: tuple[str, ...] = (
    "先秦",
    "战国",
    "秦",
    "汉",
    "西汉",
    "东汉",
    "三国",
    "魏",
    "晋",
    "西晋",
    "东晋",
    "南朝",
    "北朝",
    "隋",
    "唐",
    "五代",
    "宋",
    "北宋",
    "南宋",
    "金",
    "元",
    "明",
    "清",
    "民国",
)

_LEGEND_KEYWORDS: tuple[str, ...] = ("托名", "伪托", "假托", "依托", "传为", "旧题")
_DISPUTE_KEYWORDS: tuple[str, ...] = ("争议", "疑伪", "疑为", "存疑", "未定")
_RANGE_HINTS: tuple[str, ...] = ("之际", "前后", "唐宋", "宋元", "明清", "约")
_ANONYMOUS_HINTS: tuple[str, ...] = ("佚名", "无名氏", "佚")
_ATTRIBUTED_HINTS: tuple[str, ...] = ("传", "旧题", "题")


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_texts(values: Iterable[Any]) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _as_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _iter_ref_values(value: Any, *, preferred_keys: Sequence[str]) -> Iterable[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, Mapping):
        values: List[str] = []
        for key in preferred_keys:
            text = _as_text(value.get(key))
            if text:
                values.append(text)
        return values
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values: List[str] = []
        for item in value:
            values.extend(_iter_ref_values(item, preferred_keys=preferred_keys))
        return values
    return [_as_text(value)]


def _extract_citation_refs(
    catalog_entry: Mapping[str, Any],
    evidence: Sequence[VerdictEvidence],
) -> List[str]:
    refs: List[str] = []
    for field_name in (
        "citation_refs",
        "source_refs",
        "source_ref",
        "lineage_source",
        "lineage_sources",
        "reference_refs",
        "references",
        "source_url",
        "url",
        "document_urn",
        "urn",
    ):
        refs.extend(
            _iter_ref_values(
                catalog_entry.get(field_name),
                preferred_keys=(
                    "source_ref",
                    "citation_ref",
                    "ref",
                    "id",
                    "url",
                    "urn",
                ),
            )
        )
    refs.extend(e.source_ref for e in evidence if e.source_ref)
    return _unique_texts(refs)


def _extract_witness_keys(catalog_entry: Mapping[str, Any]) -> List[str]:
    keys: List[str] = []
    for field_name in (
        "witness_keys",
        "witness_key",
        "witnesses",
        "witness",
        "version_lineage_key",
        "base_witness_key",
        "target_witness_key",
        "variant_readings",
    ):
        keys.extend(
            _iter_ref_values(
                catalog_entry.get(field_name),
                preferred_keys=(
                    "witness_key",
                    "key",
                    "id",
                    "base_witness_key",
                    "target_witness_key",
                ),
            )
        )
    version_metadata = catalog_entry.get("version_metadata")
    if isinstance(version_metadata, Mapping):
        keys.extend(_extract_witness_keys(version_metadata))
    return _unique_texts(keys)


def _classify_date(
    dynasty: str, work_title: str
) -> tuple[str, str, list[VerdictEvidence]]:
    """返回 (date_verdict, date_estimate, evidence_list)。"""
    text = f"{dynasty} {work_title}"
    evidence: list[VerdictEvidence] = []

    if any(k in text for k in _LEGEND_KEYWORDS):
        evidence.append(
            VerdictEvidence(
                kind="date",
                source_ref="catalog.dynasty",
                excerpt=text,
                weight=0.7,
            )
        )
        return DATE_VERDICT_LEGENDARY, dynasty, evidence

    if any(k in text for k in _DISPUTE_KEYWORDS):
        evidence.append(
            VerdictEvidence(
                kind="date",
                source_ref="catalog.dynasty",
                excerpt=text,
                weight=0.6,
            )
        )
        return DATE_VERDICT_DISPUTED, dynasty, evidence

    if any(k in text for k in _RANGE_HINTS):
        evidence.append(
            VerdictEvidence(
                kind="date",
                source_ref="catalog.dynasty",
                excerpt=text,
                weight=0.55,
            )
        )
        return DATE_VERDICT_RANGE, dynasty, evidence

    if dynasty and any(k in dynasty for k in _DYNASTY_KEYWORDS):
        evidence.append(
            VerdictEvidence(
                kind="date",
                source_ref="catalog.dynasty",
                excerpt=dynasty,
                weight=0.85,
            )
        )
        return DATE_VERDICT_CONFIRMED, dynasty, evidence

    return DATE_VERDICT_UNKNOWN, "", evidence


def _classify_author(author: str) -> tuple[str, str, list[VerdictEvidence]]:
    evidence: list[VerdictEvidence] = []
    if not author:
        return AUTHOR_VERDICT_ANONYMOUS, "", evidence

    if any(k in author for k in _ANONYMOUS_HINTS):
        evidence.append(
            VerdictEvidence(
                kind="author",
                source_ref="catalog.author",
                excerpt=author,
                weight=0.8,
            )
        )
        return AUTHOR_VERDICT_ANONYMOUS, "", evidence

    if any(k in author for k in _DISPUTE_KEYWORDS) or "伪" in author:
        evidence.append(
            VerdictEvidence(
                kind="author",
                source_ref="catalog.author",
                excerpt=author,
                weight=0.6,
            )
        )
        return AUTHOR_VERDICT_DISPUTED, author, evidence

    if any(k in author for k in _ATTRIBUTED_HINTS):
        evidence.append(
            VerdictEvidence(
                kind="author",
                source_ref="catalog.author",
                excerpt=author,
                weight=0.65,
            )
        )
        return AUTHOR_VERDICT_ATTRIBUTED, author, evidence

    evidence.append(
        VerdictEvidence(
            kind="author",
            source_ref="catalog.author",
            excerpt=author,
            weight=0.85,
        )
    )
    return AUTHOR_VERDICT_CONFIRMED, author, evidence


def _classify_authenticity(
    date_v: str, author_v: str
) -> tuple[str, list[VerdictEvidence]]:
    evidence: list[VerdictEvidence] = []
    if date_v == DATE_VERDICT_LEGENDARY and author_v == AUTHOR_VERDICT_DISPUTED:
        evidence.append(
            VerdictEvidence(
                kind="authenticity",
                source_ref="rule.legendary+disputed",
                excerpt="年代为托名上古且作者争议",
                weight=0.85,
            )
        )
        return AUTHENTICITY_FORGED, evidence
    if DATE_VERDICT_DISPUTED in (date_v,) or AUTHOR_VERDICT_DISPUTED in (author_v,):
        evidence.append(
            VerdictEvidence(
                kind="authenticity",
                source_ref="rule.disputed",
                excerpt="年代或作者存在争议",
                weight=0.6,
            )
        )
        return AUTHENTICITY_DOUBTFUL, evidence
    if date_v == DATE_VERDICT_LEGENDARY:
        evidence.append(
            VerdictEvidence(
                kind="authenticity",
                source_ref="rule.legendary",
                excerpt="年代托名上古",
                weight=0.7,
            )
        )
        return AUTHENTICITY_DOUBTFUL, evidence
    if date_v == DATE_VERDICT_CONFIRMED and author_v in (
        AUTHOR_VERDICT_CONFIRMED,
        AUTHOR_VERDICT_ATTRIBUTED,
    ):
        evidence.append(
            VerdictEvidence(
                kind="authenticity",
                source_ref="rule.confirmed",
                excerpt="年代与作者均有据可考",
                weight=0.85,
            )
        )
        return AUTHENTICITY_AUTHENTIC, evidence
    return AUTHENTICITY_INDETERMINATE, evidence


def _confidence_from(evidence: Sequence[VerdictEvidence]) -> float:
    if not evidence:
        return 0.2
    avg = sum(e.weight for e in evidence) / len(evidence)
    bonus = min(0.10, 0.02 * len(evidence))
    return round(min(1.0, avg + bonus), 4)


def _maybe_refine_reviewer_note(
    *,
    llm_caller: Optional[LLMCaller],
    catalog_id: str,
    date_v: str,
    author_v: str,
    authenticity: str,
) -> str:
    if llm_caller is None:
        return ""
    prompt = (
        "你是一位中医文献考据学顾问，请用一句中文给出此条裁定的复核要点：\n"
        f"catalog_id={catalog_id}\n"
        f"date={date_v}\n"
        f"author={author_v}\n"
        f"authenticity={authenticity}\n"
        "只输出一句话，不要前后缀。"
    )
    try:
        return _as_text(llm_caller(prompt))
    except Exception:
        return ""


def _resolve_needs_review(
    *,
    date_v: str,
    author_v: str,
    authenticity: str,
) -> tuple[bool, str]:
    reasons: List[str] = []
    if date_v == DATE_VERDICT_DISPUTED:
        reasons.append("年代裁定存在争议")
    if date_v == DATE_VERDICT_LEGENDARY:
        reasons.append("年代涉及托名或传说性归属")
    if author_v == AUTHOR_VERDICT_ANONYMOUS:
        reasons.append("作者佚名，需人工确认目录归属")
    if author_v == AUTHOR_VERDICT_DISPUTED:
        reasons.append("作者归属存在争议")
    if authenticity == AUTHENTICITY_DOUBTFUL:
        reasons.append("真伪裁定为 doubtful")
    if authenticity == AUTHENTICITY_FORGED:
        reasons.append("真伪裁定为 forged")
    if authenticity == AUTHENTICITY_INDETERMINATE:
        reasons.append("真伪裁定未定")
    return bool(reasons), "；".join(_unique_texts(reasons))


def assess_catalog_authenticity(
    catalog_entry: Mapping[str, Any],
    *,
    llm_caller: Optional[LLMCaller] = None,
) -> AuthenticityVerdict:
    """对单条 catalog 资产生成 AuthenticityVerdict。"""
    if not isinstance(catalog_entry, Mapping):
        raise TypeError("catalog_entry 必须是 Mapping")

    catalog_id = _as_text(
        catalog_entry.get("catalog_id")
        or catalog_entry.get("document_id")
        or catalog_entry.get("id")
    )
    if not catalog_id:
        raise ValueError("catalog_entry 必须含 catalog_id / document_id / id")

    work_title = _as_text(
        catalog_entry.get("work_title")
        or catalog_entry.get("document_title")
        or catalog_entry.get("title")
    )
    dynasty = _as_text(catalog_entry.get("dynasty"))
    author = _as_text(catalog_entry.get("author"))

    date_v, date_estimate, date_ev = _classify_date(dynasty, work_title)
    author_v, author_name, author_ev = _classify_author(author)
    authenticity, auth_ev = _classify_authenticity(date_v, author_v)

    evidence: list[VerdictEvidence] = [*date_ev, *author_ev, *auth_ev]
    confidence = _confidence_from(evidence)
    citation_refs = _extract_citation_refs(catalog_entry, evidence)
    witness_keys = _extract_witness_keys(catalog_entry)
    needs_review, needs_review_reason = _resolve_needs_review(
        date_v=date_v,
        author_v=author_v,
        authenticity=authenticity,
    )
    reviewer_note = _maybe_refine_reviewer_note(
        llm_caller=llm_caller,
        catalog_id=catalog_id,
        date_v=date_v,
        author_v=author_v,
        authenticity=authenticity,
    )

    return AuthenticityVerdict(
        catalog_id=catalog_id,
        work_title=work_title,
        date_verdict=date_v,
        date_estimate=date_estimate,
        author_verdict=author_v,
        author_name=author_name,
        authenticity=authenticity,
        evidence=evidence,
        citation_refs=citation_refs,
        witness_keys=witness_keys,
        confidence=confidence,
        reviewer=reviewer_note,
        needs_review=needs_review,
        needs_review_reason=needs_review_reason,
    )


def assess_catalog_batch(
    catalog_entries: Sequence[Mapping[str, Any]],
    *,
    llm_caller: Optional[LLMCaller] = None,
) -> List[AuthenticityVerdict]:
    """对一批 catalog 资产并行生成裁定。"""
    verdicts: list[AuthenticityVerdict] = []
    for entry in catalog_entries or []:
        try:
            verdicts.append(assess_catalog_authenticity(entry, llm_caller=llm_caller))
        except (TypeError, ValueError):
            # 单条失败不影响批次的其它条目
            continue
    return verdicts


def build_textual_criticism_summary(
    verdicts: Sequence[Any],
) -> dict:
    """构建 dashboard / artifact 友好的考据摘要卡片数据。"""
    normalized = normalize_authenticity_verdicts(verdicts)
    date_dist: dict[str, int] = {}
    author_dist: dict[str, int] = {}
    auth_dist: dict[str, int] = {}
    confidences: list[float] = []
    for v in normalized:
        date_dist[v["date_verdict"]] = date_dist.get(v["date_verdict"], 0) + 1
        author_dist[v["author_verdict"]] = author_dist.get(v["author_verdict"], 0) + 1
        auth_dist[v["authenticity"]] = auth_dist.get(v["authenticity"], 0) + 1
        try:
            confidences.append(float(v.get("confidence") or 0.0))
        except (TypeError, ValueError):
            pass
    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    needs_review = sum(1 for v in normalized if bool(v.get("needs_review")))
    citation_ref_count = len(
        {
            ref
            for v in normalized
            for ref in v.get("citation_refs") or []
            if str(ref or "").strip()
        }
    )
    witness_key_count = len(
        {
            key
            for v in normalized
            for key in v.get("witness_keys") or []
            if str(key or "").strip()
        }
    )
    return {
        "verdict_count": len(normalized),
        "date_distribution": {k: date_dist[k] for k in sorted(date_dist)},
        "author_distribution": {k: author_dist[k] for k in sorted(author_dist)},
        "authenticity_distribution": {k: auth_dist[k] for k in sorted(auth_dist)},
        "avg_confidence": avg_conf,
        "needs_review_count": needs_review,
        "citation_ref_count": citation_ref_count,
        "witness_key_count": witness_key_count,
        "contract_version": "authenticity-verdict-v1",
    }


class TextualCriticismService:
    """textual_criticism 子阶段服务（与 J-1 风格一致）。"""

    def __init__(
        self,
        *,
        catalog_entries: Optional[Sequence[Mapping[str, Any]]] = None,
        llm_caller: Optional[LLMCaller] = None,
    ) -> None:
        self._catalog_entries = list(catalog_entries or [])
        self._llm_caller = llm_caller

    def assess(
        self,
        catalog_entries: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> List[AuthenticityVerdict]:
        entries = (
            list(catalog_entries)
            if catalog_entries is not None
            else self._catalog_entries
        )
        return assess_catalog_batch(entries, llm_caller=self._llm_caller)


__all__ = [
    "TextualCriticismService",
    "assess_catalog_authenticity",
    "assess_catalog_batch",
    "build_textual_criticism_summary",
    "LLMCaller",
]
