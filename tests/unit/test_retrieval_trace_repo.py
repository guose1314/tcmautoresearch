from __future__ import annotations

from src.knowledge.graphrag.retrieval_trace_repo import RetrievalTraceRepo


def _tiered_result() -> dict:
    return {
        "scope": "tiered",
        "asset_type": "tiered",
        "body": "[expert_insight] reviewed=True confidence=0.950\n专家审核 insight 层：麻仁润肠证据已复核。\n\n[segment] reviewed=False confidence=0.740\n片段层：麻仁润肠通便，可用于便秘证。",
        "items": [
            {
                "tier": "segment",
                "source": "graph_rag:evidence",
                "body": "片段层：麻仁润肠通便，可用于便秘证。",
                "confidence": 0.74,
                "expert_reviewed": False,
                "citations": [{"type": "Evidence", "id": "ev-1", "tier": "segment"}],
                "traceability": {"node_ids": ["ev-1"], "relationship_ids": ["rel-ev"]},
                "metadata": {},
            },
            {
                "tier": "expert_insight",
                "source": "graph_rag:claim",
                "body": "专家审核 insight 层：麻仁润肠证据已复核。",
                "confidence": 0.95,
                "expert_reviewed": True,
                "citations": [
                    {"type": "EvidenceClaim", "id": "claim-1", "tier": "expert_insight"}
                ],
                "traceability": {
                    "node_ids": ["claim-1"],
                    "relationship_ids": ["rel-claim"],
                },
                "metadata": {},
            },
        ],
        "citations": [
            {"type": "Evidence", "id": "ev-1", "tier": "segment"},
            {"type": "EvidenceClaim", "id": "claim-1", "tier": "expert_insight"},
        ],
        "traceability": {
            "node_ids": ["ev-1", "claim-1"],
            "relationship_ids": ["rel-ev", "rel-claim"],
        },
        "metadata": {"retrieval_policy": "expert_reviewed_first"},
        "token_count": 42,
        "truncated": False,
    }


def test_repo_persists_trace_file_and_log(tmp_path) -> None:
    repo = RetrievalTraceRepo(
        cache_dir=tmp_path / "cache",
        log_path=tmp_path / "graphrag_retrieval_traces.jsonl",
    )

    summary = repo.record_retrieval(
        _tiered_result(),
        query="麻仁润肠",
        cycle_id="cycle-1",
        phase="analyze",
        task_id="task-1",
    )

    assert summary["trace_id"].startswith("graphrag-trace:")
    payload = repo.load_trace(summary["trace_id"])
    assert payload is not None
    assert payload["node_ids"] == ["ev-1", "claim-1"]
    assert payload["relationship_ids"] == ["rel-ev", "rel-claim"]
    assert payload["prompt_entries"][0]["tier"] == "expert_insight"
    assert payload["insights"][0]["tier"] == "expert_insight"
    assert (tmp_path / "graphrag_retrieval_traces.jsonl").exists()


def test_repo_returns_cache_hit_for_same_request(tmp_path) -> None:
    repo = RetrievalTraceRepo(
        cache_dir=tmp_path / "cache",
        log_path=tmp_path / "graphrag_retrieval_traces.jsonl",
    )

    first = repo.record_retrieval(
        _tiered_result(),
        query="麻仁润肠",
        cycle_id="cycle-1",
        phase="analyze",
        task_id="task-1",
    )
    second = repo.record_retrieval(
        _tiered_result(),
        query="麻仁润肠",
        cycle_id="cycle-1",
        phase="analyze",
        task_id="task-1",
    )

    assert first["trace_id"] == second["trace_id"]
    assert second["cache_hit"] is True
