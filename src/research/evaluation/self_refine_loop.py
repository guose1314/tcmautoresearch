"""Evidence-focused Self-Refine loop for LLM research drafts."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

SELF_REFINE_LOOP_VERSION = "self-refine-evidence-loop-v1"

_CITATION_RE = re.compile(
    r"(\[@[^\]]+\]|\[(?:cite|citation|claim|claim_id):[^\]]+\]|"
    r"citation_keys?\s*[:=]|segment_id|document_id|source_ref|evidence_ref)",
    re.IGNORECASE,
)
_OVERSTRONG_TERMS = (
    "证明",
    "确证",
    "必然",
    "一定",
    "疗效确切",
    "直接治疗",
    "完全治愈",
    "决定",
    "唯一",
)
_HEDGE_TERMS = ("可能", "候选", "待证", "需复核", "尚待", "提示", "或可", "假设")
_COUNTER_EVIDENCE_TERMS = (
    "反证",
    "相反",
    "冲突",
    "不支持",
    "证据不足",
    "异文",
    "版本差异",
    "争议",
    "counter",
)


@dataclass(frozen=True)
class SelfRefineIssue:
    code: str
    severity: str
    message: str
    evidence: str = ""
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelfRefineLoopResult:
    status: str
    accepted: bool
    initial_draft: str
    final_draft: str
    revision_prompt: str
    diff: str
    issues_before: List[Dict[str, Any]] = field(default_factory=list)
    issues_after: List[Dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    expert_review_required: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = SELF_REFINE_LOOP_VERSION
        return payload


class SelfRefineLoop:
    """Second-pass reviewer for citation and evidence-boundary failures."""

    def __init__(self, *, require_citations: bool = True) -> None:
        self.require_citations = bool(require_citations)

    def run(
        self,
        draft: Any,
        *,
        context: Optional[Mapping[str, Any]] = None,
        llm_generate: Optional[Callable[..., Any]] = None,
    ) -> SelfRefineLoopResult:
        context = dict(context or {})
        initial_text = _draft_to_text(draft)
        issues_before = self.evaluate(draft, context=context)
        metadata = {
            "reviewer_version": SELF_REFINE_LOOP_VERSION,
            "task_type": str(context.get("task_type") or "research_draft"),
        }
        if not issues_before:
            return SelfRefineLoopResult(
                status="passed",
                accepted=True,
                initial_draft=initial_text,
                final_draft=initial_text,
                revision_prompt="",
                diff="",
                metadata=metadata,
            )

        revision_prompt = self.build_revision_prompt(
            initial_text,
            issues_before,
            context=context,
        )
        revised_text = self._retry_once(revision_prompt, context, llm_generate)
        retry_count = 1 if revised_text and revised_text != initial_text else 0
        final_text = revised_text or initial_text
        issues_after = self.evaluate(final_text, context=context)
        accepted = not issues_after
        status = "passed_after_retry" if accepted else "expert_pending_review"
        return SelfRefineLoopResult(
            status=status,
            accepted=accepted,
            initial_draft=initial_text,
            final_draft=final_text,
            revision_prompt=revision_prompt,
            diff=_unified_diff(initial_text, final_text),
            issues_before=[item.to_dict() for item in issues_before],
            issues_after=[item.to_dict() for item in issues_after],
            retry_count=retry_count,
            expert_review_required=not accepted,
            metadata={
                **metadata,
                "issue_count_before": len(issues_before),
                "issue_count_after": len(issues_after),
            },
        )

    def evaluate(
        self,
        draft: Any,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> List[SelfRefineIssue]:
        context = dict(context or {})
        text = _draft_to_text(draft)
        issues: List[SelfRefineIssue] = []
        require_citations = bool(
            context.get("require_citations", self.require_citations)
        )
        if require_citations and _looks_claim_like(text) and not _has_citation(draft):
            issues.append(
                SelfRefineIssue(
                    code="missing_citation",
                    severity="high",
                    message="LLM 初稿包含结论性表述但缺少引用或原文定位。",
                    evidence=_excerpt(text),
                    suggestion="为每个结论补充 citation_key、segment_id、source_ref 或降级为候选观察。",
                )
            )
        if _has_overstrong_claim(text) and not _has_strong_support(context):
            issues.append(
                SelfRefineIssue(
                    code="overstrong_relation",
                    severity="high",
                    message="关系或疗效表述过强，超过当前证据等级。",
                    evidence=_excerpt(text),
                    suggestion="将强断言改为候选、提示或待验证表述，并写明证据等级。",
                )
            )
        candidate_issue = _candidate_as_fact_issue(text, context)
        if candidate_issue is not None:
            issues.append(candidate_issue)
        if _has_counter_evidence(context) and not _mentions_counter_evidence(text):
            issues.append(
                SelfRefineIssue(
                    code="ignored_counter_evidence",
                    severity="medium",
                    message="上下文包含反证或冲突证据，但初稿没有处理。",
                    evidence=_counter_evidence_excerpt(context),
                    suggestion="补写反证处理，或把结论降级为 contested/candidate。",
                )
            )
        return issues

    def build_revision_prompt(
        self,
        draft_text: str,
        issues: Sequence[SelfRefineIssue],
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> str:
        issue_payload = [item.to_dict() for item in issues]
        return (
            "你是中医文献证据内审员。请只修订初稿，不新增未给出的证据。\n"
            "必须完成：补引用或原文定位；降低过强关系；候选不得写成事实；处理反证。\n"
            "若证据仍不足，请把结论标为 expert_pending_review 或 candidate_observation。\n\n"
            f"审查问题：\n{json.dumps(issue_payload, ensure_ascii=False, indent=2)}\n\n"
            f"上下文：\n{json.dumps(dict(context or {}), ensure_ascii=False, indent=2, default=str)}\n\n"
            f"初稿：\n{draft_text}\n\n"
            "请输出修订后的完整正文或 JSON。"
        )

    def _retry_once(
        self,
        revision_prompt: str,
        context: Mapping[str, Any],
        llm_generate: Optional[Callable[..., Any]],
    ) -> str:
        generator = llm_generate or context.get("llm_generate") or context.get("llm")
        if generator is None:
            generator = context.get("llm_service") or context.get("llm_engine")
        try:
            if callable(generator):
                value = generator(revision_prompt)
            elif hasattr(generator, "generate"):
                value = generator.generate(
                    revision_prompt,
                    system_prompt="你是严格的中医文献证据审查员。",
                )
            else:
                return ""
        except TypeError:
            try:
                value = generator.generate(revision_prompt)  # type: ignore[union-attr]
            except Exception:
                return ""
        except Exception:
            return ""
        return _draft_to_text(value).strip()


def run_self_refine_loop(
    draft: Any,
    *,
    context: Optional[Mapping[str, Any]] = None,
    llm_generate: Optional[Callable[..., Any]] = None,
    require_citations: bool = True,
) -> SelfRefineLoopResult:
    return SelfRefineLoop(require_citations=require_citations).run(
        draft,
        context=context,
        llm_generate=llm_generate,
    )


def _draft_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _has_citation(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if (
                key_text
                in {
                    "citation",
                    "citations",
                    "citation_keys",
                    "source_ref",
                    "source_refs",
                    "evidence_ref",
                    "evidence_refs",
                    "provenance",
                }
                and item
            ):
                return True
            if key_text == "segment_id" and value.get("quote_text"):
                return True
            if isinstance(item, (Mapping, list)) and _has_citation(item):
                return True
        return bool(_CITATION_RE.search(_draft_to_text(value)))
    if isinstance(value, list):
        return any(_has_citation(item) for item in value)
    return bool(_CITATION_RE.search(str(value or "")))


def _looks_claim_like(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (
            "治疗",
            "主治",
            "导致",
            "支持",
            "证明",
            "提示",
            "假设",
            "关系",
            "结论",
        )
    )


def _has_overstrong_claim(text: str) -> bool:
    return any(term in str(text or "") for term in _OVERSTRONG_TERMS)


def _has_strong_support(context: Mapping[str, Any]) -> bool:
    grade = str(context.get("evidence_grade") or context.get("grade") or "").upper()
    if grade == "A":
        return True
    try:
        grounding_score = float(context.get("grounding_score") or 0.0)
    except (TypeError, ValueError):
        grounding_score = 0.0
    return grounding_score >= 0.86 and bool(context.get("formal_conclusion_allowed"))


def _candidate_as_fact_issue(
    text: str,
    context: Mapping[str, Any],
) -> Optional[SelfRefineIssue]:
    candidates = _candidate_terms(context)
    if not candidates:
        return None
    normalized = str(text or "")
    for candidate in candidates:
        if candidate and candidate in normalized:
            window = _window_around(normalized, candidate)
            if not any(term in window for term in _HEDGE_TERMS):
                return SelfRefineIssue(
                    code="candidate_as_fact",
                    severity="high",
                    message="候选关系或候选术语被写成事实结论。",
                    evidence=window,
                    suggestion="在候选项附近明确写为可能、待证、需复核，或保留 candidate_observation。",
                )
    return None


def _candidate_terms(context: Mapping[str, Any]) -> List[str]:
    terms: List[str] = []
    for key in ("candidate_terms", "candidates", "candidate_relations", "hypotheses"):
        values = context.get(key)
        if isinstance(values, str):
            terms.append(values)
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, str):
                    terms.append(item)
                elif isinstance(item, Mapping):
                    text = "".join(
                        str(item.get(name) or "")
                        for name in ("source", "relation", "relation_type", "target")
                    )
                    terms.append(
                        text or str(item.get("name") or item.get("claim") or "")
                    )
    return [item for item in dict.fromkeys(term.strip() for term in terms) if item]


def _has_counter_evidence(context: Mapping[str, Any]) -> bool:
    for key in ("counter_evidence", "contradictions", "refutations"):
        value = context.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _mentions_counter_evidence(text: str) -> bool:
    return any(term in str(text or "") for term in _COUNTER_EVIDENCE_TERMS)


def _counter_evidence_excerpt(context: Mapping[str, Any]) -> str:
    for key in ("counter_evidence", "contradictions", "refutations"):
        value = context.get(key)
        if value:
            return _excerpt(_draft_to_text(value), limit=240)
    return ""


def _window_around(text: str, term: str, radius: int = 24) -> str:
    index = text.find(term)
    if index < 0:
        return _excerpt(text)
    return text[max(0, index - radius) : index + len(term) + radius]


def _excerpt(text: str, *, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def _unified_diff(before: str, after: str) -> str:
    if before == after:
        return ""
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


__all__ = [
    "SELF_REFINE_LOOP_VERSION",
    "SelfRefineIssue",
    "SelfRefineLoop",
    "SelfRefineLoopResult",
    "run_self_refine_loop",
]
