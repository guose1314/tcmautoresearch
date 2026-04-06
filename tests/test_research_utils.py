import tempfile
import unittest
from pathlib import Path

from src.api.research_utils import (
    WORKSPACE_ROOT,
    build_markdown_report,
    build_research_dashboard_payload,
    iter_output_file_candidates,
    normalize_research_request,
    resolve_preferred_report_artifact,
)


class TestResearchUtils(unittest.TestCase):
    def test_normalize_research_request_injects_phase_defaults(self):
        normalized = normalize_research_request({"topic": "桂枝汤研究"})

        observe_ctx = normalized["phase_contexts"]["observe"]
        self.assertTrue(observe_ctx["use_local_corpus"])
        self.assertTrue(observe_ctx["collect_local_corpus"])
        self.assertEqual(observe_ctx["data_source"], "local")
        self.assertTrue(observe_ctx["run_preprocess_and_extract"])
        self.assertFalse(observe_ctx["run_literature_retrieval"])
        self.assertFalse(observe_ctx["use_ctext_whitelist"])
        self.assertTrue(str(observe_ctx["local_data_dir"]).endswith("data"))

        publish_ctx = normalized["phase_contexts"]["publish"]
        self.assertFalse(publish_ctx["allow_pipeline_citation_fallback"])

    def test_normalize_research_request_allows_override(self):
        normalized = normalize_research_request(
            {
                "topic": "麻黄汤研究",
                "phase_contexts": {
                    "observe": {
                        "use_local_corpus": False,
                        "run_literature_retrieval": True,
                    },
                    "publish": {
                        "allow_pipeline_citation_fallback": True,
                    },
                },
            }
        )

        observe_ctx = normalized["phase_contexts"]["observe"]
        self.assertFalse(observe_ctx["use_local_corpus"])
        self.assertTrue(observe_ctx["run_literature_retrieval"])
        # Defaults still remain available when only partial observe overrides are supplied.
        self.assertIn("local_data_dir", observe_ctx)

        publish_ctx = normalized["phase_contexts"]["publish"]
        self.assertTrue(publish_ctx["allow_pipeline_citation_fallback"])

    def test_build_markdown_report_renders_phase_details(self):
        report = build_markdown_report(
            "job-1",
            {
                "topic": "桂枝汤研究",
                "cycle_id": "cycle-1",
                "status": "completed",
                "started_at": "2026-04-06T00:00:00",
                "completed_at": "2026-04-06T00:10:00",
                "total_duration_sec": 600,
                "pipeline_metadata": {"cycle_name": "demo", "scope": "test"},
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 12.5,
                        "summary": {"observation_count": 3, "key_findings": ["桂枝", "白芍"]},
                    },
                    {
                        "phase": "analyze",
                        "status": "failed",
                        "duration_sec": 2.5,
                        "error": "chi square unavailable",
                        "summary": {},
                    },
                ],
            },
        )

        self.assertIn("# 研究任务报告", report)
        self.assertIn("### 观察阶段", report)
        self.assertIn("### 分析阶段", report)
        self.assertIn("- 错误：chi square unavailable", report)
        self.assertIn("关键发现：桂枝、白芍", report)

    def test_iter_output_candidates_and_resolve_preferred_report_artifact(self):
        with tempfile.TemporaryDirectory(dir=WORKSPACE_ROOT) as temp_dir:
            root = Path(temp_dir)
            markdown_path = root / "report.md"
            json_path = root / "report.json"
            markdown_path.write_text("# report\n", encoding="utf-8")
            json_path.write_text("{}\n", encoding="utf-8")

            payload = {
                "report_files": {
                    "markdown_file": str(markdown_path),
                    "json_file": str(json_path),
                },
                "nested": [
                    {"result_path": str(json_path)},
                ],
            }

            candidates = list(iter_output_file_candidates(payload))
            self.assertIn(("markdown_file", str(markdown_path)), candidates)
            self.assertIn(("json_file", str(json_path)), candidates)
            self.assertIn(("result_path", str(json_path)), candidates)

            self.assertEqual(
                resolve_preferred_report_artifact(payload, "markdown"),
                markdown_path.resolve(),
            )
            self.assertEqual(
                resolve_preferred_report_artifact(payload, "json"),
                json_path.resolve(),
            )

    def test_build_research_dashboard_payload_uses_alias_fields_and_graph_summary(self):
        snapshot = {
            "job_id": "job-1",
            "topic": "桂枝汤 dashboard",
            "status": "completed",
            "progress": 100,
            "current_phase": "publish",
            "started_at": "2026-04-06T00:00:00",
            "completed_at": "2026-04-06T00:10:00",
            "result": {
                "cycle_id": "cycle-1",
                "total_duration_sec": 18.0,
                "started_at": "2026-04-06T00:00:00",
                "completed_at": "2026-04-06T00:10:00",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 8.0,
                        "summary": {"observation_count": 4},
                    },
                    {
                        "phase": "publish",
                        "status": "completed",
                        "duration_sec": 10.0,
                        "summary": {"key_findings": ["桂枝", "白芍"]},
                    },
                ],
                "pipeline_metadata": {
                    "cycle_name": "demo",
                    "protocol_inputs": {
                        "study_type": "RCT",
                        "primary_outcome": "症状改善",
                        "intervention": "桂枝汤",
                        "comparison": "常规治疗",
                    },
                },
                "analysis_results": {
                    "quality_metrics": {"confidence_score": 0.82, "completeness": 0.91},
                    "evidence_protocol": {
                        "evidence_records": [{"id": "ev-1"}],
                        "claims": [{"id": "claim-1"}, {"id": "claim-2"}],
                    },
                    "data_mining_summary": {
                        "association_rule_count": 3,
                        "cluster_count": 1,
                        "methods_executed": ["association_rules", "clustering"],
                    },
                    "primary_association": {
                        "herb": "桂枝",
                        "syndrome": "营卫不和",
                        "p_value": 0.004,
                    },
                    "relation_statistics": {"total_relations": 7},
                },
                "research_artifact": {
                    "similar_formula_graph_evidence_summary": {
                        "formula_count": 1,
                        "match_count": 1,
                        "matches": [
                            {
                                "formula_name": "桂枝汤",
                                "similar_formula_name": "桂枝加葛根汤",
                                "similarity_score": 0.84,
                                "evidence_score": 0.76,
                                "shared_herbs": ["桂枝", "白芍"],
                                "shared_syndromes": ["营卫不和"],
                                "retrieval_sources": ["kg"],
                            }
                        ],
                    }
                },
            },
        }

        payload = build_research_dashboard_payload(snapshot)

        self.assertEqual(payload["overview"]["status_label"], "已完成")
        self.assertEqual(payload["phase_board"]["completed"], 2)
        self.assertEqual(payload["evidence_board"]["evidence_count"], 1)
        self.assertEqual(payload["evidence_board"]["claim_count"], 2)
        self.assertEqual(payload["evidence_board"]["association_rule_count"], 3)
        self.assertEqual(payload["evidence_board"]["data_mining_methods"], ["association_rules", "clustering"])
        self.assertEqual(payload["evidence_board"]["primary_association"]["herb"], "桂枝")
        self.assertEqual(
            payload["knowledge_graph_board"]["source"],
            "research_artifact.similar_formula_graph_evidence_summary",
        )
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["node_count"], 2)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["edge_count"], 1)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["analysis_relation_count"], 7)
        self.assertEqual(
            payload["knowledge_graph_board"]["highlights"][0]["title"],
            "桂枝汤 -> 桂枝加葛根汤",
        )
        self.assertEqual(payload["protocol_inputs"]["study_type"], "RCT")


if __name__ == "__main__":
    unittest.main()
