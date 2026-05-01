from __future__ import annotations

import tempfile

from src.learning.graph_pattern_miner import GraphPatternMiningDaemon


class _RecordingLearningEngine:
    def __init__(self) -> None:
        self.insights = []

    def register_graph_insight(self, insight):
        self.insights.append(dict(insight))


class _FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return [
            {
                "herb": "桂枝",
                "prescription": "桂枝汤",
                "symptom": "营卫不和",
                "occurrence_freq": 3,
            }
        ]


class _FakeNeo4jDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self):
        return self._session


def test_graph_pattern_miner_without_driver_returns_empty_by_default() -> None:
    engine = _RecordingLearningEngine()
    with tempfile.TemporaryDirectory() as tmp:
        daemon = GraphPatternMiningDaemon(
            state_dir=tmp,
            self_learning_engine=engine,
        )

        patterns = daemon.execute_incremental_mining()
        insights = daemon.mine_learning_insights(cycle_id="cycle-no-driver")

    assert patterns == []
    assert insights == []
    assert engine.insights == []
    assert "银翘散" not in str(patterns)
    assert "连翘" not in str(insights)


def test_graph_pattern_miner_mock_patterns_are_explicit_opt_in() -> None:
    engine = _RecordingLearningEngine()
    with tempfile.TemporaryDirectory() as tmp:
        daemon = GraphPatternMiningDaemon(
            state_dir=tmp,
            self_learning_engine=engine,
            allow_mock_patterns=True,
        )

        patterns = daemon.execute_incremental_mining()
        insights = daemon.patterns_to_learning_insights(
            patterns,
            cycle_id="cycle-mock",
        )

    assert patterns[0]["prescription"] == "银翘散"
    assert patterns[0]["mock"] is True
    assert len(engine.insights) == 1
    assert insights[0]["source"] == "neo4j_graph_pattern_miner"
    assert insights[0]["target_phase"] == "hypothesis"
    assert "银翘散" in insights[0]["description"]
    assert insights[0]["evidence_refs_json"][0]["mock"] is True


def test_graph_pattern_miner_query_uses_created_or_outbox_cursor() -> None:
    session = _FakeSession()
    with tempfile.TemporaryDirectory() as tmp:
        daemon = GraphPatternMiningDaemon(
            neo4j_driver=_FakeNeo4jDriver(session),
            state_dir=tmp,
        )
        daemon.last_mining_time = "2026-05-01T00:00:00+00:00"

        patterns = daemon.execute_incremental_mining()

    assert patterns == [
        {
            "herb": "桂枝",
            "prescription": "桂枝汤",
            "symptom": "营卫不和",
            "occurrence_freq": 3,
        }
    ]
    query, params = session.calls[0]
    assert "p.created_at" in query
    assert "p.outbox_processed_at" in query
    assert "p.projected_at" in query
    assert params["last_time"] == "2026-05-01T00:00:00+00:00"
