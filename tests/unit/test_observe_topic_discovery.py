from __future__ import annotations

import logging
import unittest
from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import patch

from src.research.phases.observe_phase import ObservePhaseMixin
from src.research.topic_discovery import (
    TOPIC_PROPOSAL_CONTRACT_VERSION,
    TOPIC_PROPOSAL_MAX,
    TOPIC_PROPOSAL_MIN,
)


class _StubPipeline:
    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger("test_observe_topic_discovery")
        self.knowledge_graph = None


class _ObserveHarness(ObservePhaseMixin):
    def __init__(self, pipeline: _StubPipeline) -> None:
        self.pipeline = pipeline


@dataclass
class _Cycle:
    cycle_id: str = "cycle-topic"
    research_objective: str = "少阳证治研究"
    description: str = ""
    cycle_name: str = ""


def _build_harness(ingestion_result: Dict[str, Any]) -> _ObserveHarness:
    harness = _ObserveHarness(_StubPipeline())

    def collect_observe_corpus(_context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "documents": [{"urn": "doc-topic", "title": "宋本伤寒论"}],
        }

    def run_observe_ingestion(
        _corpus: Dict[str, Any],
        _context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return ingestion_result

    harness._collect_observe_corpus_if_enabled = collect_observe_corpus  # type: ignore[assignment]
    harness._run_observe_literature_if_enabled = lambda _context: None  # type: ignore[assignment]
    harness._run_observe_ingestion_if_enabled = run_observe_ingestion  # type: ignore[assignment]
    harness._run_observe_collation_if_enabled = lambda _corpus, _ingestion, _context: (
        None
    )  # type: ignore[assignment]
    harness._build_observe_philology_artifacts = lambda _ingestion: []  # type: ignore[assignment]
    harness._build_observe_graph_assets = lambda _cycle_id, _ingestion: {}  # type: ignore[assignment]
    harness._build_observe_metadata = lambda *args, **kwargs: {}  # type: ignore[assignment]
    harness._append_corpus_observe_updates = lambda *args, **kwargs: None  # type: ignore[assignment]
    harness._append_ingestion_observe_updates = lambda *args, **kwargs: None  # type: ignore[assignment]
    harness._append_literature_observe_updates = lambda *args, **kwargs: None  # type: ignore[assignment]
    harness._append_collation_observe_updates = lambda *args, **kwargs: None  # type: ignore[assignment]
    return harness


class ObserveTopicDiscoveryTest(unittest.TestCase):
    def test_execute_observe_phase_includes_topic_discovery_payload(self) -> None:
        ingestion_result = {
            "documents": [
                {
                    "urn": "doc-topic",
                    "title": "宋本伤寒论",
                    "metadata": {
                        "version_metadata": {
                            "catalog_id": "catalog::shaoyang",
                            "work_title": "伤寒论",
                            "fragment_title": "辨少阳病脉证并治",
                            "version_lineage_key": "lineage::shaoyang",
                            "witness_key": "witness::song",
                        },
                    },
                },
            ],
            "processed_document_count": 1,
            "aggregate": {},
        }
        harness = _build_harness(ingestion_result)

        result = harness.execute_observe_phase(_Cycle(), {})

        topic_discovery = result["results"]["topic_discovery"]
        proposals = topic_discovery["proposals"]
        self.assertEqual(
            topic_discovery["contract_version"], TOPIC_PROPOSAL_CONTRACT_VERSION
        )
        self.assertGreaterEqual(len(proposals), TOPIC_PROPOSAL_MIN)
        self.assertLessEqual(len(proposals), TOPIC_PROPOSAL_MAX)
        self.assertEqual(
            topic_discovery["summary"]["contract_version"],
            TOPIC_PROPOSAL_CONTRACT_VERSION,
        )
        self.assertTrue(topic_discovery["summary"]["meets_count_contract"])
        source_refs = {
            source["source_ref"]
            for proposal in proposals
            for source in proposal.get("source_candidates", [])
        }
        self.assertIn("catalog::shaoyang", source_refs)

        metadata = result["metadata"]
        self.assertEqual(metadata["topic_proposal_count"], len(proposals))
        self.assertTrue(metadata["topic_discovery_generated"])
        self.assertEqual(
            metadata["topic_discovery_contract_version"],
            TOPIC_PROPOSAL_CONTRACT_VERSION,
        )

    def test_topic_discovery_failure_does_not_block_observe(self) -> None:
        harness = _build_harness({"documents": [], "aggregate": {}})

        with patch(
            "src.research.phases.observe_phase.propose_topics",
            side_effect=RuntimeError("topic service down"),
        ):
            result = harness.execute_observe_phase(
                _Cycle(research_objective="少阳证治研究"), {}
            )

        self.assertEqual(result["status"], "completed")
        topic_discovery = result["results"]["topic_discovery"]
        self.assertEqual(topic_discovery["proposals"], [])
        self.assertEqual(topic_discovery["degraded_reason"], "topic_discovery_failed")
        self.assertIn("topic service down", topic_discovery["error"])

        metadata = result["metadata"]
        self.assertEqual(metadata["topic_proposal_count"], 0)
        self.assertFalse(metadata["topic_discovery_generated"])
        self.assertEqual(
            metadata["topic_discovery_degraded_reason"], "topic_discovery_failed"
        )
        self.assertIn("topic service down", metadata["topic_discovery_error"])


if __name__ == "__main__":
    unittest.main()
