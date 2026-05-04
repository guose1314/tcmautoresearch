from __future__ import annotations

from src.research.evaluation.self_refine_loop import (
    SelfRefineLoop,
    run_self_refine_loop,
)


def test_self_refine_loop_detects_evidence_review_failures() -> None:
    result = run_self_refine_loop(
        "桂枝汤直接治疗高血压，疗效确切。",
        context={
            "candidate_terms": ["桂枝汤直接治疗高血压"],
            "counter_evidence": ["现代研究证据不足，古籍无高血压病名。"],
        },
    )

    codes = {issue["code"] for issue in result.issues_before}
    assert "missing_citation" in codes
    assert "overstrong_relation" in codes
    assert "candidate_as_fact" in codes
    assert "ignored_counter_evidence" in codes
    assert result.status == "expert_pending_review"
    assert result.expert_review_required is True
    assert result.revision_prompt


def test_self_refine_loop_retries_once_and_keeps_diff() -> None:
    def fake_llm(_prompt: str) -> str:
        return "候选观察：桂枝汤与高血压的关系证据不足，需专家复核。[citation:review-1] 已考虑反证。"

    result = run_self_refine_loop(
        "桂枝汤直接治疗高血压，疗效确切。",
        context={
            "candidate_terms": ["桂枝汤与高血压"],
            "counter_evidence": ["古籍无高血压病名。"],
        },
        llm_generate=fake_llm,
    )

    assert result.status == "passed_after_retry"
    assert result.retry_count == 1
    assert result.diff
    assert "-桂枝汤直接治疗高血压" in result.diff
    assert result.issues_after == []


def test_self_refine_loop_passes_grounded_cautious_draft() -> None:
    draft = {
        "claim_id": "claim-1",
        "claim_text": "候选观察：桂枝汤可能关联营卫不和。",
        "citation_keys": ["seg-1"],
    }

    result = SelfRefineLoop().run(
        draft,
        context={"candidate_terms": ["桂枝汤可能关联营卫不和"]},
    )

    assert result.status == "passed"
    assert result.accepted is True
    assert result.expert_review_required is False
