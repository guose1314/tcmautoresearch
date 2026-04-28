"""T5.4: ExpertFeedbackLoop 接入 ReviewWorkbench dispute 闭环。

验收门：手工 dispute → close → research_learning_feedback 新增对应条目。
"""

from __future__ import annotations

import uuid

import pytest

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.learning.expert_feedback_loop import ExpertFeedbackLoop


@pytest.fixture()
def repo():
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.init_db()
    yield ResearchSessionRepository(mgr)
    mgr.close()


def _seed(repo) -> str:
    cycle_id = f"t54-{uuid.uuid4().hex[:8]}"
    repo.create_session(
        {
            "cycle_id": cycle_id,
            "cycle_name": "T5.4 接入测试",
            "description": "expert dispute → feedback library",
            "research_objective": "验证写盘",
        }
    )
    return cycle_id


# ---------------------------------------------------------------------------
# from_review_dispute 单元行为
# ---------------------------------------------------------------------------

def test_from_review_dispute_rejected_maps_to_high_severity_with_violation():
    dispute = {
        "case_id": "DISP-1",
        "asset_type": "catalog",
        "asset_key": "k-1",
        "resolution": "rejected",
        "resolution_notes": "证据不足",
        "summary": "请求重审",
        "arbitrator": "张专家",
        "dispute_status": "resolved",
    }
    entry = ExpertFeedbackLoop.from_review_dispute(dispute)
    assert entry.severity == "high"
    assert entry.graph_targets == ["k-1"]
    assert entry.source_phase == "review_workbench:catalog"
    assert entry.violations and entry.violations[0]["rule_id"] == "expert_dispute:rejected"
    assert entry.extra["dispute_case_id"] == "DISP-1"


def test_from_review_dispute_accepted_no_violation():
    entry = ExpertFeedbackLoop.from_review_dispute(
        {
            "case_id": "DISP-2",
            "asset_type": "catalog",
            "asset_key": "k-2",
            "resolution": "accepted",
        }
    )
    assert entry.severity == "medium"
    assert entry.violations == []


# ---------------------------------------------------------------------------
# 验收门：dispute close → 反馈库新增条目
# ---------------------------------------------------------------------------

def test_dispute_close_appends_learning_feedback_record(repo):
    cycle_id = _seed(repo)
    loop = ExpertFeedbackLoop()
    loop.attach_to_repo(repo)

    opened = repo.open_review_dispute(
        cycle_id, "catalog", "k-target", "李研究员",
        "需要专家重新审议此条版本谱系",
        arbitrator="张专家",
    )
    case_id = opened["case_id"]

    # 闭环前应没有 feedback
    library_before = repo.get_learning_feedback_library(cycle_id)
    assert library_before is None or len(library_before.get("records", [])) == 0

    resolved = repo.resolve_review_dispute(
        cycle_id, case_id, "rejected",
        resolved_by="张专家", resolution_notes="证据链不完整",
    )
    assert resolved["dispute_status"] == "resolved"

    library_after = repo.get_learning_feedback_library(cycle_id)
    assert library_after is not None
    records = library_after.get("records") or []
    assert len(records) == 1
    record = records[0]
    assert record["feedback_scope"] == "expert_dispute"
    assert record["source_phase"] == "review_workbench"
    assert record["grade_level"] == "high"
    metadata = record.get("metadata") or {}
    assert metadata.get("origin") == "expert_feedback_loop"
    assert metadata.get("dispute_case_id") == case_id
    assert metadata.get("resolution") == "rejected"


def test_record_dispute_feedback_without_repo_returns_none():
    loop = ExpertFeedbackLoop()
    out = loop.record_dispute_feedback(
        "cycle-x",
        {"case_id": "DISP-Z", "asset_type": "catalog", "asset_key": "k", "resolution": "accepted"},
    )
    assert out is None
