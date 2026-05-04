from __future__ import annotations

from src.llm.graph_rag import RetrievalResult
from src.research.phases.analyze_phase import AnalyzePhaseMixin


class _Runner:
    def retrieve(self, question_type: str, query: str, **kwargs):
        return RetrievalResult(
            scope=question_type,
            asset_type=str(kwargs.get("asset_type") or "evidence"),
            body="typed evidence context",
            token_count=3,
            citations=[{"type": "Evidence", "id": "ev-1", "asset_type": "evidence"}],
            traceability={
                "node_ids": ["ev-1"],
                "relationship_ids": ["rel-1"],
                "source_phase": "analyze",
                "cycle_id": "cycle-typed",
            },
        )


class _Harness(AnalyzePhaseMixin):
    def __init__(self) -> None:
        self.pipeline = type("_Pipeline", (), {"config": {}})()


class _Cycle:
    cycle_id = "cycle-typed"
    research_objective = "麻仁润肠"


def test_apply_graph_rag_persists_trace_and_writes_trace_id(tmp_path) -> None:
    harness = _Harness()
    context = {
        "enable_graph_rag": True,
        "graph_rag_runner": _Runner(),
        "graph_rag_asset_type": "evidence",
        "graph_rag_entity_ids": ["ev-1"],
        "graph_rag_query": "麻仁",
        "graph_rag_trace_cache_dir": tmp_path / "cache",
        "graph_rag_trace_log_path": tmp_path / "graphrag_trace.jsonl",
    }

    block = harness._apply_graph_rag(context, _Cycle())

    assert block["trace_id"].startswith("graphrag-trace:")
    assert block["retrieval_trace"]["trace_id"] == block["trace_id"]
    assert context["graph_rag_context"]["trace_id"] == block["trace_id"]
    assert tmp_path.joinpath("graphrag_trace.jsonl").exists()
