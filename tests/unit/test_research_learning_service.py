from __future__ import annotations

from src.contexts.lfitl.feedback_translator import TranslationPlan
from src.learning.research_learning_service import (
    RESEARCH_LEARNING_SERVICE_CONTRACT_VERSION,
    ResearchLearningService,
)


class _FakeLearningInsightRepo:
    def __init__(self) -> None:
        self.rows = []

    def upsert(self, payload):
        stored = dict(payload)
        for index, row in enumerate(self.rows):
            if row["insight_id"] == stored["insight_id"]:
                self.rows[index] = stored
                return stored
        self.rows.append(stored)
        return stored

    def list_active(self, target_phase=None, *, limit=100):
        rows = [row for row in self.rows if row.get("status") == "active"]
        if target_phase:
            rows = [row for row in rows if row.get("target_phase") == target_phase]
        return rows[:limit]


class _FakeGraphMiner:
    def execute_incremental_mining(self):
        return [
            {
                "herb": "桂枝",
                "prescription": "桂枝汤",
                "symptom": "营卫不和",
                "occurrence_freq": 92,
            }
        ]


class _FakePgAssetMiner:
    def mine_pg_assets(self, cycle_id):
        return [
            {
                "insight_id": f"pg:{cycle_id}:citation-grounding",
                "source": "pg_quality_feedback",
                "target_phase": "analyze",
                "insight_type": "method_policy",
                "description": "分析阶段需优先复核 EvidenceClaim 与引用出处的一致性。",
                "confidence": 0.78,
                "evidence_refs_json": [{"cycle_id": cycle_id, "source": "feedback"}],
                "status": "active",
            }
        ]


class _RecordingPromptBiasCompiler:
    def __init__(self) -> None:
        self.plan = None

    def compile(self, plan: TranslationPlan):
        self.plan = plan
        return {
            action.purpose: {
                "bias_text": action.bias_text,
                "avoid_fields": list(action.avoid_fields),
                "severity": action.severity,
            }
            for action in plan.prompt_bias_actions
        }


def test_run_cycle_learning_compiles_phase_specific_prompt_bias() -> None:
    repo = _FakeLearningInsightRepo()
    compiler = _RecordingPromptBiasCompiler()
    service = ResearchLearningService(
        learning_insight_repo=repo,
        graph_miner=_FakeGraphMiner(),
        pg_asset_miner=_FakePgAssetMiner(),
        prompt_bias_compiler=compiler,
    )

    result = service.run_cycle_learning("cycle-learning-1")

    assert result["contract_version"] == RESEARCH_LEARNING_SERVICE_CONTRACT_VERSION
    assert len(result["insights"]) == 2
    assert len(repo.rows) == 2
    assert compiler.plan is not None
    purposes = {action.purpose for action in compiler.plan.prompt_bias_actions}
    assert purposes == {"analyze", "hypothesis"}

    prompt_bias_blocks = result["prompt_bias_blocks"]
    assert "analyze" in prompt_bias_blocks
    assert "hypothesis" in prompt_bias_blocks
    assert "EvidenceClaim" in prompt_bias_blocks["analyze"]["bias_text"]
    assert "桂枝汤" in prompt_bias_blocks["hypothesis"]["bias_text"]
    assert prompt_bias_blocks["hypothesis"]["severity"] == "high"

    summary = result["policy_adjustment_summary"]
    assert summary["insight_count"] == 2
    assert summary["pg_insight_count"] == 1
    assert summary["neo4j_insight_count"] == 1
    assert summary["prompt_bias_phases"] == ["analyze", "hypothesis"]


def test_compile_prompt_bias_can_load_active_insights_from_repo() -> None:
    repo = _FakeLearningInsightRepo()
    repo.upsert(
        {
            "insight_id": "active-observe",
            "source": "pg_quality_feedback",
            "target_phase": "observe",
            "insight_type": "prompt_bias",
            "description": "观察阶段需保留版本 witness 证据。",
            "confidence": 0.88,
            "evidence_refs_json": [],
            "status": "active",
        }
    )
    repo.upsert(
        {
            "insight_id": "reviewed-observe",
            "source": "pg_quality_feedback",
            "target_phase": "observe",
            "insight_type": "prompt_bias",
            "description": "已复核，不应进入 prompt。",
            "confidence": 0.99,
            "evidence_refs_json": [],
            "status": "reviewed",
        }
    )
    compiler = _RecordingPromptBiasCompiler()
    service = ResearchLearningService(
        learning_insight_repo=repo,
        prompt_bias_compiler=compiler,
    )

    compiled = service.compile_prompt_bias("cycle-learning-2")

    assert list(compiled["prompt_bias_blocks"]) == ["observe"]
    assert "版本 witness" in compiled["prompt_bias_blocks"]["observe"]["bias_text"]
    assert "已复核" not in compiled["prompt_bias_blocks"]["observe"]["bias_text"]
    assert compiler.plan.summary["prompt_bias_action_count"] == 1
