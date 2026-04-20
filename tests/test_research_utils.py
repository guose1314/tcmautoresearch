import tempfile
import unittest
from pathlib import Path

from src.api.research_utils import (
    WORKSPACE_ROOT,
    _resolve_dashboard_data_mining_methods,
    _resolve_data_mining_summary,
    _resolve_primary_association,
    build_markdown_report,
    build_research_dashboard_payload,
    format_phase_name,
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

    def test_format_phase_name_marks_experiment_as_protocol_design(self):
        self.assertEqual(format_phase_name("experiment"), "实验方案阶段")

    def test_format_phase_name_marks_experiment_execution_explicitly(self):
        self.assertEqual(format_phase_name("experiment_execution"), "外部实验结果导入阶段")

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

    def test_resolve_preferred_report_artifact_supports_phase_result_artifacts(self):
        with tempfile.TemporaryDirectory(dir=WORKSPACE_ROOT) as temp_dir:
            root = Path(temp_dir)
            markdown_path = root / "publish-report.md"
            docx_path = root / "publish-report.docx"
            markdown_path.write_text("# publish report\n", encoding="utf-8")
            docx_path.write_bytes(b"docx")

            payload = {
                "phase": "publish",
                "status": "completed",
                "results": {},
                "artifacts": [
                    {"name": "markdown", "path": str(markdown_path)},
                    {"name": "docx", "path": str(docx_path)},
                ],
                "metadata": {},
                "error": None,
            }

            self.assertEqual(
                resolve_preferred_report_artifact(payload, "markdown"),
                markdown_path.resolve(),
            )
            self.assertEqual(
                resolve_preferred_report_artifact(payload, "auto"),
                docx_path.resolve(),
            )

    def test_build_research_dashboard_payload_uses_standard_nested_fields_and_graph_summary(self):
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
                    "statistical_analysis": {
                        "primary_association": {
                            "herb": "桂枝",
                            "syndrome": "营卫不和",
                            "p_value": 0.004,
                        }
                    },
                    "data_mining_result": {
                        "record_count": 9,
                        "transaction_count": 9,
                        "item_count": 4,
                        "methods_executed": ["association_rules", "clustering"],
                        "association_rules": {"rules": [{"rule_id": "r-1"}, {"rule_id": "r-2"}, {"rule_id": "r-3"}]},
                        "clustering": {"cluster_summary": [{"cluster_id": "c-1"}]},
                        "frequency_chi_square": {
                            "chi_square_top": [{"herb": "桂枝", "chi2": 4.2}],
                            "herb_frequency": [{"herb": "桂枝", "count": 5}],
                        },
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
        review_workbench = payload["evidence_board"]["review_workbench"]
        section_map = {section["asset_type"]: section for section in review_workbench["sections"]}
        self.assertEqual(section_map["claim"]["count"], 2)

    def test_build_research_dashboard_payload_prefers_publish_phase_result_contract(self):
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
                    "quality_metrics": {"confidence_score": 0.12, "completeness": 0.34},
                },
                "research_artifact": {
                    "similar_formula_graph_evidence_summary": {"matches": []},
                },
                "phase_results": {
                    "publish": {
                        "phase": "publish",
                        "status": "completed",
                        "results": {
                            "analysis_results": {
                                "quality_metrics": {"confidence_score": 0.82, "completeness": 0.91},
                                "evidence_protocol": {
                                    "evidence_records": [{"id": "ev-1"}],
                                    "claims": [{"id": "claim-1"}, {"id": "claim-2"}],
                                },
                                "statistical_analysis": {
                                    "primary_association": {
                                        "herb": "桂枝",
                                        "syndrome": "营卫不和",
                                        "p_value": 0.004,
                                    }
                                },
                                "data_mining_result": {
                                    "record_count": 9,
                                    "transaction_count": 9,
                                    "item_count": 4,
                                    "methods_executed": ["association_rules", "clustering"],
                                    "association_rules": {"rules": [{"rule_id": "r-1"}, {"rule_id": "r-2"}, {"rule_id": "r-3"}]},
                                    "clustering": {"cluster_summary": [{"cluster_id": "c-1"}]},
                                    "frequency_chi_square": {
                                        "chi_square_top": [{"herb": "桂枝", "chi2": 4.2}],
                                        "herb_frequency": [{"herb": "桂枝", "count": 5}],
                                    },
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
                        "metadata": {},
                        "error": None,
                    }
                },
            },
        }

        payload = build_research_dashboard_payload(snapshot)

        self.assertEqual(payload["quality_board"]["confidence_score"], 0.82)
        self.assertEqual(payload["evidence_board"]["evidence_count"], 1)
        self.assertEqual(payload["evidence_board"]["association_rule_count"], 3)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["node_count"], 2)
        self.assertEqual(payload["knowledge_graph_board"]["highlights"][0]["title"], "桂枝汤 -> 桂枝加葛根汤")

    def test_build_research_dashboard_payload_includes_observe_philology(self):
        snapshot = {
            "job_id": "job-philology",
            "topic": "补血汤 philology dashboard",
            "status": "completed",
            "progress": 100,
            "current_phase": "publish",
            "result": {
                "cycle_id": "cycle-philology",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 1},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "philology-demo"},
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                        }
                    ],
                    "collation_entries": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:1",
                            "difference_type": "replace",
                            "base_text": "黃芪",
                            "witness_text": "黃耆",
                        }
                    ],
                    "annotation_report": {
                        "summary": {
                            "processed_document_count": 1,
                            "philology_notes": ["输出 1 条可复用校勘条目"],
                        }
                    },
                    "catalog_summary": {
                        "summary": {
                            "catalog_document_count": 1,
                            "work_count": 1,
                            "work_fragment_count": 1,
                            "version_lineage_count": 1,
                            "witness_count": 1,
                            "missing_core_metadata_count": 0,
                        },
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:1",
                                "source_type": "local",
                                "catalog_id": "local:catalog:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:doc:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            }
                        ],
                        "version_lineages": [
                            {
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "work_fragment_key": "补血汤|补血汤",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                                "witness_count": 1,
                                "witnesses": [
                                    {
                                        "title": "补血汤宋本",
                                        "urn": "doc:1",
                                        "source_type": "local",
                                        "catalog_id": "local:catalog:1",
                                        "witness_key": "local:doc:1",
                                    }
                                ],
                            }
                        ],
                    },
                },
            },
        }

        payload = build_research_dashboard_payload(snapshot)

        self.assertEqual(payload["evidence_board"]["terminology_standard_table_count"], 1)
        self.assertEqual(payload["evidence_board"]["collation_entry_count"], 1)
        self.assertEqual(payload["evidence_board"]["philology_document_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_document_count"], 1)
        self.assertEqual(payload["evidence_board"]["version_lineage_count"], 1)
        self.assertEqual(payload["evidence_board"]["witness_count"], 1)
        self.assertEqual(payload["evidence_board"]["philology"]["terminology_standard_table"][0]["canonical"], "黄芪")
        self.assertEqual(payload["evidence_board"]["philology"]["collation_entries"][0]["witness_text"], "黃耆")
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["summary"]["work_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["summary"]["exegesis_entry_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["summary"]["temporal_semantic_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["summary"]["pending_review_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["temporal_semantics"]["dynasty"], "明")
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["review_status"], "pending")
        self.assertTrue(payload["evidence_board"]["catalog_summary"]["documents"][0]["needs_manual_review"])
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["exegesis_entries"][0]["canonical"], "黄芪")
        self.assertEqual(
            payload["evidence_board"]["catalog_summary"]["documents"][0]["exegesis_entries"][0]["definition_source"],
            "structured_tcm_knowledge",
        )
        self.assertIn(
            "补气",
            payload["evidence_board"]["catalog_summary"]["documents"][0]["exegesis_entries"][0]["definition"],
        )
        self.assertIn(
            "TCMRelationshipDefinitions.HERB_EFFICACY_MAP",
            payload["evidence_board"]["catalog_summary"]["documents"][0]["exegesis_entries"][0]["source_refs"],
        )
        review_workbench = payload["evidence_board"]["review_workbench"]
        section_map = {section["asset_type"]: section for section in review_workbench["sections"]}
        self.assertEqual(section_map["catalog_version_lineage"]["count"], 1)
        self.assertEqual(section_map["terminology_row"]["count"], 1)
        self.assertEqual(section_map["collation_entry"]["count"], 1)
        self.assertEqual(section_map["fragment_candidate"]["count"], 0)

    def test_build_research_dashboard_payload_prefers_config_note_for_exegesis_definition(self):
        snapshot = {
            "job_id": "job-philology-config-exegesis",
            "topic": "文献学权威义项",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-philology-config-exegesis",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 1},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "philology-config-exegesis"},
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:config:1",
                            "canonical": "黄芪",
                            "category": "herb",
                            "label": "本草药名",
                            "status": "standardized",
                            "observed_forms": ["黃芪"],
                            "sources": ["config_terminology_standard"],
                            "notes": ["补气固表，托毒生肌，为补气要药。"],
                        }
                    ],
                    "catalog_summary": {
                        "summary": {
                            "catalog_document_count": 1,
                            "work_count": 1,
                            "work_fragment_count": 1,
                            "version_lineage_count": 1,
                            "witness_count": 1,
                            "missing_core_metadata_count": 0,
                        },
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:config:1",
                                "source_type": "local",
                                "catalog_id": "local:catalog:config:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:witness:config:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            }
                        ],
                        "version_lineages": [
                            {
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "work_fragment_key": "补血汤|补血汤",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                                "witness_count": 1,
                                "witnesses": [
                                    {
                                        "title": "补血汤宋本",
                                        "urn": "doc:config:1",
                                        "source_type": "local",
                                        "catalog_id": "local:catalog:config:1",
                                        "witness_key": "local:witness:config:1",
                                    }
                                ],
                            }
                        ],
                    },
                },
            },
        }

        payload = build_research_dashboard_payload(snapshot)

        exegesis_entry = payload["evidence_board"]["catalog_summary"]["documents"][0]["exegesis_entries"][0]
        self.assertEqual(exegesis_entry["definition_source"], "config_terminology_standard")
        self.assertEqual(exegesis_entry["definition"], "补气固表，托毒生肌，为补气要药。")
        self.assertEqual(exegesis_entry["source_refs"], ["config_terminology_standard"])

    def test_build_research_dashboard_payload_applies_review_workbench_decisions(self):
        snapshot = {
            "job_id": "job-philology-review-workbench",
            "topic": "文献学校核看板",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-philology-review-workbench",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 1},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "philology-review-demo"},
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:review-workbench:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                        }
                    ],
                    "catalog_summary": {
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:review-workbench:1",
                                "source_type": "local",
                                "catalog_id": "local:catalog:review-workbench:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:witness:review-workbench:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            }
                        ]
                    },
                },
            },
        }

        baseline_payload = build_research_dashboard_payload(snapshot)
        baseline_sections = {
            section["asset_type"]: section
            for section in baseline_payload["evidence_board"]["review_workbench"]["sections"]
        }
        baseline_item = baseline_sections["terminology_row"]["items"][0]
        snapshot["result"]["observe_philology"]["review_workbench_decisions"] = [
            {
                "asset_type": "terminology_row",
                "asset_key": baseline_item["asset_key"],
                "review_status": "accepted",
                "reviewer": "tester",
                "decision_basis": "人工术语复核",
            }
        ]

        reviewed_payload = build_research_dashboard_payload(snapshot)
        reviewed_sections = {
            section["asset_type"]: section
            for section in reviewed_payload["evidence_board"]["review_workbench"]["sections"]
        }
        reviewed_item = reviewed_sections["terminology_row"]["items"][0]

        self.assertEqual(reviewed_item["review_status"], "accepted")
        self.assertFalse(reviewed_item["needs_manual_review"])
        self.assertEqual(reviewed_item["reviewer"], "tester")
        self.assertEqual(reviewed_item["decision_basis"], "人工术语复核")

    def test_build_research_dashboard_payload_exposes_review_queue_filters_workload_and_batch_audit(self):
        snapshot = {
            "job_id": "job-review-queue",
            "topic": "批量复核队列看板",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-review-queue",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 1},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "review-queue-demo"},
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:review-queue:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                        }
                    ],
                    "catalog_summary": {
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:review-queue:1",
                                "source_type": "local",
                                "catalog_id": "local:catalog:review-queue:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:witness:review-queue:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            }
                        ]
                    },
                },
            },
        }

        baseline_payload = build_research_dashboard_payload(snapshot)
        terminology_item = next(
            section["items"][0]
            for section in baseline_payload["evidence_board"]["review_workbench"]["sections"]
            if section["asset_type"] == "terminology_row" and section["items"]
        )
        snapshot["result"]["observe_philology"]["review_workbench_decisions"] = [
            {
                "asset_type": "terminology_row",
                "asset_key": terminology_item["asset_key"],
                "review_status": "accepted",
                "reviewer": "tester",
                "decision_basis": "批量术语复核",
                "review_reasons": ["reviewer_batch"],
            }
        ]
        snapshot["result"]["observe_philology"]["review_workbench_batch_audit_trail"] = [
            {
                "applied_at": "2026-04-20T12:00:00",
                "applied_count": 1,
                "reviewer": "tester",
                "shared_decision_basis": "批量术语复核",
                "shared_review_reasons": ["reviewer_batch"],
                "selection_snapshot": {
                    "selection_strategy": "current_filtered_selection",
                    "selected_count": 1,
                    "asset_types": ["terminology_row"],
                },
            }
        ]

        payload = build_research_dashboard_payload(
            snapshot,
            philology_filters={
                "asset_type": "terminology_row",
                "review_status": "accepted",
                "reviewer": "tester",
            },
        )

        evidence_board = payload["evidence_board"]
        review_workbench = evidence_board["review_workbench"]
        self.assertEqual(review_workbench["total_item_count"], 1)
        self.assertGreater(review_workbench["all_item_count"], review_workbench["total_item_count"])
        self.assertEqual(evidence_board["queue_filters"]["active_filters"]["asset_type"], "terminology_row")
        self.assertEqual(evidence_board["queue_filters"]["active_filters"]["review_status"], "accepted")
        self.assertEqual(evidence_board["queue_filters"]["active_filters"]["reviewer"], "tester")
        self.assertEqual(evidence_board["review_queue"]["total_pending"], 0)
        self.assertEqual(evidence_board["review_queue"]["reviewer_workload"][0]["reviewer"], "tester")
        self.assertEqual(
            review_workbench["review_queue"]["recent_batch_operations"][0]["shared_decision_basis"],
            "批量术语复核",
        )
        self.assertEqual(
            review_workbench["review_queue"]["recent_batch_operations"][0]["selection_snapshot"]["selected_count"],
            1,
        )

    def test_build_research_dashboard_payload_includes_learning_feedback_board(self):
        snapshot = {
            "job_id": "job-learning-feedback",
            "topic": "学习反馈看板",
            "status": "completed",
            "progress": 100,
            "current_phase": "reflect",
            "result": {
                "cycle_id": "cycle-learning-feedback",
                "phases": [
                    {
                        "phase": "reflect",
                        "status": "completed",
                        "duration_sec": 2.0,
                        "summary": {"feedback_record_count": 3},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "feedback-demo"},
                "learning_feedback_library": {
                    "contract_version": "research-feedback-library.v1",
                    "summary": {
                        "record_count": 3,
                        "phase_record_count": 2,
                        "latest_cycle_score": 0.82,
                        "cycle_trend": "improving",
                        "weak_phase_names": ["analyze"],
                        "recorded_phase_names": ["observe", "analyze"],
                        "strategy_changed": True,
                    },
                    "replay_feedback": {
                        "status": "completed",
                        "iteration_number": 3,
                        "learning_summary": {
                            "recorded_phases": ["observe", "analyze"],
                            "weak_phases": ["analyze"],
                            "tuned_parameters": {
                                "max_concurrent_tasks": 6,
                                "quality_threshold": 0.74,
                            },
                        },
                    },
                    "records": [
                        {
                            "feedback_scope": "cycle_summary",
                            "feedback_status": "summary",
                            "overall_score": 0.82,
                            "cycle_trend": "improving",
                            "strategy_changed": True,
                            "improvement_priorities": ["优先: 提升analyze阶段数据完整性 (评分 0.35)"],
                            "details": {
                                "learning_summary": {
                                    "recorded_phases": ["observe", "analyze"],
                                    "weak_phases": ["analyze"],
                                    "tuned_parameters": {
                                        "max_concurrent_tasks": 6,
                                        "quality_threshold": 0.74,
                                    },
                                }
                            },
                        },
                        {
                            "feedback_scope": "phase_assessment",
                            "target_phase": "observe",
                            "feedback_status": "strength",
                            "overall_score": 0.88,
                        },
                        {
                            "feedback_scope": "phase_assessment",
                            "target_phase": "analyze",
                            "feedback_status": "weakness",
                            "overall_score": 0.35,
                            "issues": ["证据链衔接松散"],
                        },
                    ],
                },
            },
        }

        payload = build_research_dashboard_payload(snapshot)
        board = payload["learning_feedback_board"]

        self.assertTrue(board["available"])
        self.assertEqual(board["contract_version"], "research-feedback-library.v1")
        self.assertEqual(board["record_count"], 3)
        self.assertEqual(board["phase_record_count"], 2)
        self.assertEqual(board["cycle_trend_label"], "持续改善")
        self.assertEqual(board["weak_phase_labels"], ["分析阶段"])
        self.assertEqual(board["recorded_phase_labels"], ["观察阶段", "分析阶段"])
        self.assertTrue(board["strategy_changed"])
        self.assertEqual(board["iteration_number"], 3)
        self.assertEqual(board["tuned_parameters"]["quality_threshold"], 0.74)
        self.assertEqual(board["improvement_priorities"][0], "优先: 提升analyze阶段数据完整性 (评分 0.35)")
        self.assertEqual(board["recent_records"][0]["feedback_status_label"], "优势")
        self.assertEqual(board["recent_records"][1]["feedback_status_label"], "薄弱项")
        self.assertEqual(board["recent_records"][1]["issue_preview"], ["证据链衔接松散"])

    def test_build_research_dashboard_payload_applies_catalog_filters_and_exposes_filter_options(self):
        snapshot = {
            "job_id": "job-filtered-philology",
            "topic": "文献学筛选看板",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-filtered-philology",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 2},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "philology-filter-demo"},
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                            "notes": ["黃芪 统一为 黄芪（本草药名）"],
                        },
                        {
                            "document_title": "十全大补汤影印本",
                            "document_urn": "doc:2",
                            "canonical": "当归",
                            "label": "本草药名",
                            "notes": ["當歸 统一为 当归（本草药名）"],
                        },
                    ],
                    "catalog_summary": {
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:1",
                                "source_type": "local",
                                "catalog_id": "local:catalog:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:witness:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            },
                            {
                                "document_title": "十全大补汤影印本",
                                "document_urn": "doc:2",
                                "source_type": "scan",
                                "catalog_id": "scan:catalog:2",
                                "work_title": "十全大补汤",
                                "fragment_title": "十全大补汤",
                                "work_fragment_key": "十全大补汤|十全大补汤",
                                "version_lineage_key": "十全大补汤|十全大补汤|清|佚名|影印本",
                                "witness_key": "scan:witness:2",
                                "dynasty": "清",
                                "author": "佚名",
                                "edition": "影印本",
                            },
                        ]
                    },
                },
            },
        }

        payload = build_research_dashboard_payload(
            snapshot,
            philology_filters={"work_title": "补血汤", "witness_key": "local:witness:1"},
        )

        self.assertEqual(payload["evidence_board"]["active_catalog_filters"]["work_title"], "补血汤")
        self.assertEqual(payload["evidence_board"]["active_catalog_filters"]["witness_key"], "local:witness:1")
        self.assertEqual(len(payload["evidence_board"]["catalog_filter_options"]["work_title"]), 2)
        self.assertEqual(payload["evidence_board"]["catalog_document_count"], 1)
        self.assertEqual(payload["evidence_board"]["philology"]["terminology_standard_table_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["work_title"], "补血汤")
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["witness_key"], "local:witness:1")
        review_workbench = payload["evidence_board"]["review_workbench"]
        section_map = {section["asset_type"]: section for section in review_workbench["sections"]}
        self.assertEqual(section_map["catalog_version_lineage"]["count"], 1)
        self.assertEqual(section_map["terminology_row"]["count"], 1)

    def test_build_research_dashboard_payload_filters_fragment_candidates_by_witness_side_keys(self):
        snapshot = {
            "job_id": "job-fragment-filter",
            "topic": "辑佚候选筛选看板",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-fragment-filter",
                "phases": [
                    {
                        "phase": "observe",
                        "status": "completed",
                        "duration_sec": 3.0,
                        "summary": {"observation_count": 1},
                    }
                ],
                "pipeline_metadata": {"cycle_name": "fragment-filter-demo"},
                "observe_philology": {
                    "catalog_summary": {
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:fragment:1",
                                "source_type": "local",
                                "catalog_id": "catalog:fragment:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "local:witness:fragment:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            },
                            {
                                "document_title": "补血汤明抄本",
                                "document_urn": "doc:fragment:2",
                                "source_type": "local",
                                "catalog_id": "catalog:fragment:2",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|明抄本",
                                "witness_key": "local:witness:fragment:2",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "明抄本",
                            },
                        ]
                    },
                    "fragment_candidates": [
                        {
                            "fragment_candidate_id": "frag-filter-1",
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:fragment:1",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "local:witness:fragment:1",
                            "witness_title": "补血汤明抄本",
                            "witness_urn": "doc:fragment:2",
                            "witness_work_title": "补血汤",
                            "witness_fragment_title": "补血汤",
                            "witness_version_lineage_key": "补血汤|补血汤|明|李时珍|明抄本",
                            "witness_witness_key": "local:witness:fragment:2",
                            "match_score": 0.81,
                            "source_refs": ["见证本:补血汤明抄本"],
                            "reconstruction_basis": "明抄本保留补文，可作为辑佚候选。",
                        }
                    ],
                },
            },
        }

        payload = build_research_dashboard_payload(
            snapshot,
            philology_filters={"witness_key": "local:witness:fragment:2"},
        )

        section_map = {
            section["asset_type"]: section
            for section in payload["evidence_board"]["review_workbench"]["sections"]
        }
        self.assertEqual(section_map["fragment_candidate"]["count"], 1)
        self.assertEqual(
            payload["evidence_board"]["active_catalog_filters"]["witness_key"],
            "local:witness:fragment:2",
        )

    def test_dashboard_statistical_alias_helpers_require_standard_nested_fields(self):
        analysis_results = {
            "statistical_analysis": {
                "primary_association": {
                    "herb": "黄芪",
                    "syndrome": "气虚证",
                    "p_value": 0.01,
                }
            },
            "primary_association": {
                "herb": "legacy-herb",
                "syndrome": "legacy-syndrome",
                "p_value": 0.99,
            },
            "data_mining_result": {
                "record_count": 12,
                "transaction_count": 12,
                "item_count": 4,
                "methods_executed": ["frequency_chi_square"],
                "association_rules": {"rules": [{"rule_id": "rule-1"}]},
                "clustering": {"cluster_summary": [{"cluster_id": "c-1"}]},
                "frequency_chi_square": {
                    "chi_square_top": [{"herb": "黄芪", "chi2": 4.2}],
                    "herb_frequency": [{"herb": "黄芪", "count": 6}],
                },
            },
            "data_mining_summary": {
                "record_count": 12,
                "transaction_count": 12,
                "item_count": 4,
                "association_rule_count": 999,
                "cluster_count": 999,
                "frequency_signal_count": 999,
                "methods_executed": ["legacy_method"],
            },
            "data_mining_methods": ["legacy_method"],
        }

        primary_association = _resolve_primary_association(analysis_results, {})
        data_mining_summary = _resolve_data_mining_summary(analysis_results, {})
        data_mining_methods = _resolve_dashboard_data_mining_methods(analysis_results, data_mining_summary)

        self.assertEqual(primary_association["herb"], "黄芪")
        self.assertEqual(primary_association["syndrome"], "气虚证")
        self.assertEqual(data_mining_summary["record_count"], 12)
        self.assertEqual(data_mining_summary["transaction_count"], 12)
        self.assertEqual(data_mining_summary["item_count"], 4)
        self.assertEqual(data_mining_summary["association_rule_count"], 1)
        self.assertEqual(data_mining_summary["cluster_count"], 1)
        self.assertEqual(data_mining_summary["frequency_signal_count"], 1)
        self.assertEqual(data_mining_methods, ["frequency_chi_square"])

    def test_dashboard_statistical_alias_helpers_ignore_alias_only_payloads(self):
        analysis_results = {
            "primary_association": {
                "herb": "legacy-herb",
                "syndrome": "legacy-syndrome",
            },
            "data_mining_summary": {
                "record_count": 24,
                "methods_executed": ["legacy_method"],
            },
            "data_mining_methods": ["legacy_method"],
        }
        research_artifact = {
            "primary_association": {
                "herb": "artifact-herb",
                "syndrome": "artifact-syndrome",
            },
            "data_mining_summary": {
                "record_count": 12,
            },
            "data_mining_result": {
                "methods_executed": ["artifact_method"],
            },
        }

        primary_association = _resolve_primary_association(analysis_results, research_artifact)
        data_mining_summary = _resolve_data_mining_summary(analysis_results, research_artifact)
        data_mining_methods = _resolve_dashboard_data_mining_methods(analysis_results, data_mining_summary)

        self.assertEqual(primary_association, {})
        self.assertEqual(data_mining_summary, {})
        self.assertEqual(data_mining_methods, [])


if __name__ == "__main__":
    unittest.main()
