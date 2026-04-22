"""tests/test_web_console_api.py — 3.4 FastAPI + SSE 接口测试"""

import json
import os
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient

from src.infrastructure.research_session_repo import ResearchSessionRepository
from web_console.app import create_app
from web_console.job_manager import ResearchJobManager


def _make_learning_feedback_payload():
    replay_feedback = {
        "status": "completed",
        "iteration_number": 3,
        "learning_summary": {
            "recorded_phases": ["observe", "analyze"],
            "weak_phase_count": 1,
            "cycle_trend": "improving",
            "tuned_parameters": {
                "max_concurrent_tasks": 6,
                "quality_threshold": 0.74,
            },
        },
        "quality_assessment": {"overall_cycle_score": 0.82},
    }
    return {
        "contract_version": "research-feedback-library.v1",
        "replay_feedback": replay_feedback,
        "records": [
            {
                "feedback_scope": "cycle_summary",
                "source_phase": "reflect",
                "feedback_status": "summary",
                "overall_score": 0.82,
                "cycle_trend": "improving",
                "issue_count": 1,
                "weakness_count": 1,
                "strength_count": 1,
                "strategy_changed": True,
                "strategy_before_fingerprint": "before-001",
                "strategy_after_fingerprint": "after-001",
                "recorded_phase_names": ["observe", "analyze"],
                "weak_phase_names": ["analyze"],
                "improvement_priorities": ["优先: 提升analyze阶段数据完整性 (评分 0.35)"],
                "replay_feedback": replay_feedback,
                "details": {
                    "learning_summary": replay_feedback["learning_summary"],
                    "quality_assessment": replay_feedback["quality_assessment"],
                    "strategy_diff": {
                        "changed": True,
                        "before_fingerprint": "before-001",
                        "after_fingerprint": "after-001",
                    },
                },
            },
            {
                "feedback_scope": "phase_assessment",
                "source_phase": "reflect",
                "target_phase": "observe",
                "feedback_status": "strength",
                "overall_score": 0.88,
                "grade_level": "high",
                "strength_count": 1,
                "recorded_phase_names": ["observe"],
                "quality_dimensions": {
                    "completeness": 0.9,
                    "consistency": 0.84,
                    "evidence_quality": 0.86,
                },
                "details": {
                    "strength": {"phase": "observe", "score": 0.88},
                },
            },
            {
                "feedback_scope": "phase_assessment",
                "source_phase": "reflect",
                "target_phase": "analyze",
                "feedback_status": "weakness",
                "overall_score": 0.35,
                "grade_level": "very_low",
                "issue_count": 1,
                "weakness_count": 1,
                "recorded_phase_names": ["analyze"],
                "weak_phase_names": ["analyze"],
                "quality_dimensions": {
                    "completeness": 0.31,
                    "consistency": 0.42,
                    "evidence_quality": 0.28,
                },
                "issues": ["证据链衔接松散"],
                "details": {
                    "weakness": {"phase": "analyze", "score": 0.35, "issues": ["证据链衔接松散"]},
                },
            },
        ],
    }


class FakeRunner:

    def __init__(self, _config=None):
        self._config = _config or {}

    def run(self, payload, emit=None):
        topic = payload["topic"]
        protocol_inputs = {
            "study_type": payload.get("study_type"),
            "primary_outcome": payload.get("primary_outcome"),
            "intervention": payload.get("intervention"),
            "comparison": payload.get("comparison"),
        }
        if emit is not None:
            emit("cycle_created", {"topic": topic, "cycle_id": "cycle-1", "cycle_name": "demo", "scope": "test"})
            emit("phase_started", {"phase": "observe", "index": 1, "total": 2, "progress": 0.0})
            emit(
                "phase_completed",
                {
                    "phase": "observe",
                    "status": "completed",
                    "duration_sec": 0.01,
                    "error": "",
                    "summary": {"observation_count": 2},
                    "index": 1,
                    "total": 2,
                    "progress": 50.0,
                },
            )
            emit("phase_started", {"phase": "analyze", "index": 2, "total": 2, "progress": 50.0})
            emit(
                "phase_completed",
                {
                    "phase": "analyze",
                    "status": "completed",
                    "duration_sec": 0.01,
                    "error": "",
                    "summary": {"key_findings": ["A"]},
                    "index": 2,
                    "total": 2,
                    "progress": 100.0,
                },
            )
            result = {
                "topic": topic,
                "cycle_id": "cycle-1",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "output_files": {"markdown": self._config.get("artifact_markdown_path", "")},
                "analysis_results": {
                    "statistical_analysis": {
                        "interpretation": "桂枝汤核心配伍与营卫调和证据之间存在稳定关联",
                        "p_value": 0.003,
                        "confidence_level": 0.95,
                        "effect_size": 0.76,
                        "primary_association": {
                            "herb": "桂枝",
                            "syndrome": "营卫不和",
                            "p_value": 0.003,
                            "effect_size": 0.76,
                            "chi2": 8.42,
                            "sample_size": 24,
                            "contingency_table": {"a": 8, "b": 2, "c": 1, "d": 13},
                        },
                    },
                    "evidence_protocol": {
                        "evidence_records": [{"evidence_id": "ev-1"}],
                        "claims": [{"claim_id": "claim-1"}],
                    },
                    "data_mining_result": {
                        "record_count": 24,
                        "transaction_count": 24,
                        "item_count": 8,
                        "methods_executed": ["association_rules", "clustering"],
                        "frequency_chi_square": {
                            "chi_square_top": [
                                {
                                    "herb": "桂枝",
                                    "syndrome": "营卫不和",
                                    "chi2": 8.42,
                                    "p_value": 0.003,
                                    "effect_size": 0.76,
                                }
                            ],
                            "herb_frequency": [
                                {"herb": "桂枝", "count": 10},
                                {"herb": "白芍", "count": 9},
                            ],
                        },
                        "association_rules": {"rules": [{"rule_id": "r-1"}]},
                        "clustering": {"cluster_summary": [{"cluster": 0}]},
                    },
                    "quality_metrics": {"confidence_score": 0.92, "completeness": 0.88},
                    "recommendations": ["建议增加更多样本以提高准确性"],
                },
                "research_artifact": {
                    "hypothesis": [{"title": "桂枝汤调和营卫假设"}],
                    "evidence": [{"evidence_id": "ev-1"}],
                    "statistical_analysis": {
                        "interpretation": "桂枝汤核心配伍与营卫调和证据之间存在稳定关联",
                        "p_value": 0.003,
                        "confidence_level": 0.95,
                        "effect_size": 0.76,
                        "primary_association": {
                            "herb": "桂枝",
                            "syndrome": "营卫不和",
                            "p_value": 0.003,
                            "effect_size": 0.76,
                            "chi2": 8.42,
                            "sample_size": 24,
                            "contingency_table": {"a": 8, "b": 2, "c": 1, "d": 13},
                        },
                    },
                    "data_mining_result": {
                        "record_count": 24,
                        "transaction_count": 24,
                        "item_count": 8,
                        "methods_executed": ["association_rules", "clustering"],
                        "frequency_chi_square": {
                            "chi_square_top": [
                                {
                                    "herb": "桂枝",
                                    "syndrome": "营卫不和",
                                    "chi2": 8.42,
                                    "p_value": 0.003,
                                    "effect_size": 0.76,
                                }
                            ],
                            "herb_frequency": [
                                {"herb": "桂枝", "count": 10},
                                {"herb": "白芍", "count": 9},
                            ],
                        },
                        "association_rules": {"rules": [{"rule_id": "r-1"}]},
                        "clustering": {"cluster_summary": [{"cluster": 0}]},
                    },
                    "similar_formula_graph_evidence_summary": {
                        "formula_count": 1,
                        "match_count": 1,
                        "matches": [
                            {"formula_name": "桂枝汤", "similar_formula_name": "桂麻各半汤"}
                        ],
                    },
                },
                "observe_philology": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:console:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                        }
                    ],
                    "collation_entries": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:console:1",
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
                        "documents": [
                            {
                                "document_title": "补血汤宋本",
                                "document_urn": "doc:console:1",
                                "source_type": "local",
                                "catalog_id": "console:catalog:1",
                                "work_title": "补血汤",
                                "fragment_title": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "witness_key": "console:witness:1",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                            }
                        ]
                    },
                },
                "phases": [
                    {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 2}},
                    {"phase": "analyze", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"key_findings": ["A"]}},
                ],
                "pipeline_metadata": {"cycle_name": "demo", "protocol_inputs": protocol_inputs},
            }
            emit("job_completed", {"status": "completed", "result": result})
            return _ResultWrapper(result)

        return _ResultWrapper(
            {
                "topic": topic,
                "cycle_id": "cycle-sync",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [],
                "pipeline_metadata": {"cycle_name": "sync-demo", "protocol_inputs": protocol_inputs},
            }
        )


class _ResultWrapper:

    def __init__(self, payload):
        self._payload = payload
        self.status = payload["status"]

    def to_dict(self):
        return self._payload


class BlockingRunner:

    def __init__(self, _config=None):
        self._config = _config or {}
        self._started = self._config["started"]
        self._continue = self._config["continue"]

    def run(self, payload, emit=None):
        topic = payload["topic"]
        if emit is not None:
            emit("cycle_created", {"topic": topic, "cycle_id": "cycle-blocked", "cycle_name": "demo", "scope": "test"})
            emit("phase_started", {"phase": "observe", "index": 1, "total": 1, "progress": 0.0})
            self._started.set()
            self._continue.wait(timeout=5.0)
            emit(
                "phase_completed",
                {
                    "phase": "observe",
                    "status": "completed",
                    "duration_sec": 0.01,
                    "error": "",
                    "summary": {"observation_count": 1},
                    "index": 1,
                    "total": 1,
                    "progress": 100.0,
                },
            )
            result = {
                "topic": topic,
                "cycle_id": "cycle-blocked",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [
                    {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 1}},
                ],
                "pipeline_metadata": {"cycle_name": "demo"},
            }
            emit("job_completed", {"status": "completed", "result": result})
            return _ResultWrapper(result)

        return _ResultWrapper(
            {
                "topic": topic,
                "cycle_id": "cycle-blocked-sync",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [],
                "pipeline_metadata": {"cycle_name": "sync-demo"},
            }
        )


class TestWebConsoleApi(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.artifact_markdown_path = os.path.join(self.tempdir.name, "final-report.md")
        self.job_storage_dir = os.path.join(self.tempdir.name, "jobs")
        with open(self.artifact_markdown_path, "w", encoding="utf-8") as handle:
            handle.write("# 真实最终产物\n\n这是测试用的最终 Markdown 报告。\n")

        manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner({**config, "artifact_markdown_path": self.artifact_markdown_path}),
            storage_dir=self.job_storage_dir,
            default_orchestrator_config={"runtime_profile": "web_research"},
        )
        self.manager = manager
        app = create_app(job_manager=manager)
        app.state.settings.secrets.pop("security", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

    def _persist_catalog_review_session(self, cycle_id: str) -> None:
        repo = ResearchSessionRepository(self.client.app.state.db_manager)
        if repo.get_session(cycle_id) is not None:
            repo.delete_session(cycle_id)
        repo.create_session(
            {
                "cycle_id": cycle_id,
                "cycle_name": "console review session",
                "description": "catalog review writeback",
                "research_objective": "验证目录学 review 写回",
                "status": "completed",
                "current_phase": "analyze",
            }
        )
        phase = repo.add_phase_execution(
            cycle_id,
            {"phase": "observe", "status": "completed", "output": {"phase": "observe", "status": "completed"}},
        )
        repo.add_artifact(
            cycle_id,
            {
                "phase_execution_id": phase["id"],
                "name": "observe_philology_catalog_summary",
                "artifact_type": "dataset",
                "content": {
                    "summary": {
                        "catalog_document_count": 1,
                        "work_count": 1,
                        "work_fragment_count": 1,
                        "version_lineage_count": 1,
                        "witness_count": 1,
                        "missing_core_metadata_count": 0,
                        "source_type_counts": {"local": 1},
                    },
                    "documents": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:console:1",
                            "source_type": "local",
                            "catalog_id": "console:catalog:1",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "console:witness:1",
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
                                    "urn": "doc:console:1",
                                    "source_type": "local",
                                    "catalog_id": "console:catalog:1",
                                    "witness_key": "console:witness:1",
                                }
                            ],
                        }
                    ],
                },
            },
        )

    def _persist_learning_feedback_session(self, cycle_id: str, analyze_target_phase: str = "analyze") -> None:
        repo = ResearchSessionRepository(self.client.app.state.db_manager)
        if repo.get_session(cycle_id) is not None:
            repo.delete_session(cycle_id)
        payload = json.loads(json.dumps(_make_learning_feedback_payload(), ensure_ascii=False))
        if analyze_target_phase != "analyze":
            payload["records"][0]["weak_phase_names"] = [analyze_target_phase]
            payload["records"][0]["improvement_priorities"] = [
                f"优先: 提升{analyze_target_phase}阶段数据完整性 (评分 0.35)"
            ]
            payload["records"][0]["details"]["learning_summary"]["recorded_phases"] = ["observe", analyze_target_phase]
            payload["records"][0]["details"]["learning_summary"]["weak_phase_count"] = 1
            payload["records"][2]["target_phase"] = analyze_target_phase
            payload["records"][2]["recorded_phase_names"] = [analyze_target_phase]
            payload["records"][2]["weak_phase_names"] = [analyze_target_phase]
            payload["records"][2]["details"]["weakness"]["phase"] = analyze_target_phase
        repo.create_session(
            {
                "cycle_id": cycle_id,
                "cycle_name": "learning feedback session",
                "description": "learning feedback query api",
                "research_objective": "验证 learning feedback 管理 API 查询入口",
                "status": "completed",
                "current_phase": "reflect",
            }
        )
        phase = repo.add_phase_execution(
            cycle_id,
            {"phase": "reflect", "status": "completed", "output": {"phase": "reflect", "status": "completed"}},
        )
        repo.replace_learning_feedback_library(
            cycle_id,
            payload,
            phase_execution_id=phase["id"],
        )

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_root_probe_endpoints(self):
        liveness = self.client.get("/liveness")
        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(liveness.json()["probe_type"], "liveness")

        readiness = self.client.get("/readiness")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["probe_type"], "readiness")

    def test_index_page_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("登录", response.text)
        self.assertIn("中医智慧科研平台", response.text)
        self.assertIn("/api/auth/login", response.text)

    def test_console_page_served(self):
        response = self.client.get("/console")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("中医自动科研控制台", response.text)
        self.assertIn("initializeJwtAuth", response.text)
        self.assertIn("authenticatedFetch", response.text)
        self.assertIn("getJwtToken", response.text)
        self.assertIn("Console Session", response.text)
        self.assertIn('id="progress-bar"', response.text)
        self.assertIn("EventSource", response.text)
        self.assertIn("WebSocket", response.text)
        self.assertIn('id="transport-select"', response.text)
        self.assertIn('id="active-transport"', response.text)
        self.assertIn("openRealtimeChannel", response.text)
        self.assertIn("结果摘要", response.text)
        self.assertIn('id="result-summary"', response.text)
        self.assertIn("研究看板", response.text)
        self.assertIn('id="research-dashboard"', response.text)
        self.assertIn("renderResearchDashboard", response.text)
        self.assertIn("文献学校核工作台", response.text)
        self.assertIn("submitCatalogReview", response.text)
        self.assertIn("submitPhilologyReview", response.text)
        self.assertIn("submitBatchPhilologyReview", response.text)
        self.assertIn("全选当前筛选结果", response.text)
        self.assertIn("批量标记已核", response.text)
        self.assertIn("清空筛选", response.text)
        self.assertIn("queueResearchDashboardRefresh", response.text)
        self.assertIn("resolveHealthTier", response.text)
        self.assertIn("buildPhaseSegmentTitle", response.text)
        self.assertIn("dashboard-alert", response.text)
        self.assertIn("dashboard-phase-error", response.text)
        self.assertIn('id="dashboard-phase-modal"', response.text)
        self.assertIn('id="dashboard-modal-association-section"', response.text)
        self.assertIn('id="dashboard-modal-association-summary"', response.text)
        self.assertIn('id="dashboard-modal-association-visual"', response.text)
        self.assertIn('id="dashboard-graph-modal"', response.text)
        self.assertIn("toggleDashboardPhaseFilter", response.text)
        self.assertIn("openDashboardPhaseDetail", response.text)
        self.assertIn("buildPrimaryAssociationSummarySection", response.text)
        self.assertIn("buildDashboardPrimaryAssociationBox", response.text)
        self.assertIn("renderPrimaryAssociationVisual", response.text)
        self.assertIn("primary-association-matrix", response.text)
        self.assertIn("buildDashboardPrimaryAssociationDetail", response.text)
        self.assertIn("列联表 (a/b/c/d)", response.text)
        self.assertIn("chi2", response.text)
        self.assertIn("bindDashboardModalEvents", response.text)
        self.assertIn("buildKnowledgeGraphBoardSection", response.text)
        self.assertIn("openDashboardKnowledgeGraphModal", response.text)
        self.assertIn("renderKnowledgeGraphStage", response.text)
        self.assertIn("放大展示知识关系", response.text)
        self.assertIn('id="study-type-input"', response.text)
        self.assertIn('id="primary-outcome-input"', response.text)
        self.assertIn('id="intervention-input"', response.text)
        self.assertIn('id="comparison-input"', response.text)
        self.assertIn('observe: "观察阶段"', response.text)
        self.assertIn('observation_count: "观察记录数"', response.text)
        self.assertIn('analysis_results: "分析结果"', response.text)
        self.assertIn('research_artifact: "研究产物"', response.text)
        self.assertIn('interpretation: "结果解释"', response.text)
        self.assertIn('match_count: "图谱匹配数"', response.text)
        self.assertIn("localStorage", response.text)
        self.assertIn("restoreLastJob", response.text)
        self.assertIn("最近任务", response.text)
        self.assertIn('id="recent-job-list"', response.text)
        self.assertIn("清除失效记录", response.text)
        self.assertIn("清理本地记录", response.text)
        self.assertIn("删除任务", response.text)
        self.assertIn("deleteJobById", response.text)
        self.assertIn("refreshRecentJobs", response.text)
        self.assertIn("打开最终产物", response.text)
        self.assertIn("导出 JSON 报告", response.text)

    def test_console_auth_endpoints_report_open_mode(self):
        status_response = self.client.get("/api/console/auth/status")
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertFalse(status_payload["auth_required"])
        self.assertEqual(status_payload["auth_mode"], "open")
        self.assertEqual(status_payload["token_label"], "控制台会话令牌")
        self.assertEqual(status_payload["credential_label"], "可选访问令牌")
        self.assertTrue(status_payload["guest_allowed"])

        login_response = self.client.post(
            "/api/console/auth/login",
            json={"username": "开放控制台访客", "api_key": ""},
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertTrue(login_payload["authenticated"])
        self.assertFalse(login_payload["auth_required"])
        self.assertEqual(login_payload["principal"], "开放控制台访客")
        self.assertFalse(login_payload["token_supplied"])
        self.assertEqual(login_payload["session_token"], "")

    def test_console_auth_endpoints_require_management_key_when_enabled(self):
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.setdefault("security", {})["management_api_key"] = "console-secret"
        app.state.settings.secrets.setdefault("security", {}).pop("console_auth", None)
        client = TestClient(app)

        status_response = client.get("/api/v1/console/auth/status")
        self.assertEqual(status_response.status_code, 200)
        status_payload = status_response.json()
        self.assertTrue(status_payload["auth_required"])
        self.assertEqual(status_payload["auth_mode"], "management_api_key")
        self.assertEqual(status_payload["credential_label"], "管理 API Key")

        denied_response = client.post(
            "/api/console/auth/login",
            json={"username": "管理员", "api_key": "wrong-key"},
        )
        self.assertEqual(denied_response.status_code, 401)

        allowed_response = client.post(
            "/api/console/auth/login",
            json={"username": "管理员", "api_key": "console-secret"},
        )
        self.assertEqual(allowed_response.status_code, 200)
        allowed_payload = allowed_response.json()
        self.assertTrue(allowed_payload["authenticated"])
        self.assertTrue(allowed_payload["auth_required"])
        self.assertEqual(allowed_payload["principal"], "管理员")
        self.assertTrue(allowed_payload["token_supplied"])
        self.assertTrue(allowed_payload["session_token"])
        self.assertEqual(allowed_payload["auth_source"], "management_api_key")

    def test_console_username_password_login_issues_session_token_and_can_access_protected_routes(self):
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.setdefault("security", {})["console_auth"] = {
            "users": [
                {
                    "username": "researcher",
                    "password": "s3cret-pass",
                    "display_name": "科研管理员",
                }
            ]
        }
        client = TestClient(app)

        status_response = client.get("/api/console/auth/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["auth_mode"], "password")

        denied_response = client.post(
            "/api/console/auth/login",
            json={"username": "researcher", "password": "wrong-pass"},
        )
        self.assertEqual(denied_response.status_code, 401)

        login_response = client.post(
            "/api/console/auth/login",
            json={"username": "researcher", "password": "s3cret-pass"},
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        session_token = login_payload["session_token"]
        self.assertTrue(session_token)
        self.assertEqual(login_payload["principal"], "科研管理员")
        self.assertEqual(login_payload["auth_source"], "password")

        create_response = client.post(
            "/api/research/jobs",
            json={"topic": "密码登录任务"},
            headers={"Authorization": f"Bearer {session_token}"},
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = client.get(
                f"/api/research/jobs/{job_id}",
                headers={"Authorization": f"Bearer {session_token}"},
            )
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        events_response = client.get(f"/api/research/jobs/{job_id}/events?api_key={session_token}")
        self.assertEqual(events_response.status_code, 200)
        self.assertIn("text/event-stream", events_response.headers["content-type"])

        with client.websocket_connect(f"/api/research/jobs/{job_id}/ws?api_key={session_token}") as websocket:
            received_events = []
            for _ in range(20):
                event = websocket.receive_json()
                received_events.append(event["event"])
                if event["event"] == "job_completed":
                    break
        self.assertIn("job_completed", received_events)

        logout_response = client.post(
            "/api/console/auth/logout",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["revoked"])

        revoked_response = client.post(
            "/api/research/jobs",
            json={"topic": "失效会话任务"},
            headers={"Authorization": f"Bearer {session_token}"},
        )
        self.assertEqual(revoked_response.status_code, 401)

    def test_sync_run_endpoint(self):
        response = self.client.post("/api/research/run", json={"topic": "四君子汤研究"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["pipeline_metadata"]["cycle_name"], "sync-demo")

    def test_sync_run_endpoint_accepts_explicit_protocol_inputs(self):
        response = self.client.post(
            "/api/research/run",
            json={
                "topic": "黄芪颗粒治疗疲劳",
                "study_type": "rct",
                "primary_outcome": "疲劳量表评分变化",
                "intervention": "黄芪颗粒",
                "comparison": "安慰剂",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        protocol_inputs = payload["pipeline_metadata"]["protocol_inputs"]
        self.assertEqual(protocol_inputs["study_type"], "rct")
        self.assertEqual(protocol_inputs["primary_outcome"], "疲劳量表评分变化")
        self.assertEqual(protocol_inputs["intervention"], "黄芪颗粒")
        self.assertEqual(protocol_inputs["comparison"], "安慰剂")

    def test_job_manager_resolves_web_runtime_profile_for_sync_and_async_entries(self):
        self.assertEqual(self.manager._resolve_orchestrator_config({})["runtime_profile"], "web_research")
        self.assertEqual(
            self.manager._resolve_orchestrator_config(
                {"orchestrator_config": {"phases": ["observe"]}}
            )["runtime_profile"],
            "web_research",
        )
        self.assertEqual(
            self.manager._resolve_orchestrator_config(
                {"orchestrator_config": {"runtime_profile": "custom_profile"}}
            )["runtime_profile"],
            "custom_profile",
        )

    def test_create_job_accepts_explicit_protocol_inputs(self):
        create_response = self.client.post(
            "/api/research/jobs",
            json={
                "topic": "黄芪颗粒治疗疲劳",
                "study_type": "rct",
                "primary_outcome": "疲劳量表评分变化",
                "intervention": "黄芪颗粒",
                "comparison": "安慰剂",
            },
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self.assertEqual(payload["status"], "completed")
        protocol_inputs = payload["result"]["pipeline_metadata"]["protocol_inputs"]
        self.assertEqual(protocol_inputs["study_type"], "rct")
        self.assertEqual(protocol_inputs["primary_outcome"], "疲劳量表评分变化")
        self.assertEqual(protocol_inputs["intervention"], "黄芪颗粒")
        self.assertEqual(protocol_inputs["comparison"], "安慰剂")

    def test_create_job_and_get_status(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "麻黄汤研究"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["progress"], 100.0)
        self.assertEqual(payload["result"]["cycle_id"], "cycle-1")
        self.assertEqual(payload["result"]["analysis_results"]["statistical_analysis"]["p_value"], 0.003)
        self.assertEqual(
            payload["result"]["analysis_results"]["statistical_analysis"]["primary_association"]["herb"],
            "桂枝",
        )
        self.assertEqual(
            payload["result"]["analysis_results"]["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(payload["result"]["research_artifact"]["similar_formula_graph_evidence_summary"]["match_count"], 1)

    def test_learning_feedback_session_endpoint_returns_library(self):
        self._persist_learning_feedback_session("feedback-api")

        response = self.client.get("/api/research/sessions/feedback-api/learning-feedback")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["cycle_id"], "feedback-api")
        self.assertEqual(payload["contract_version"], "research-feedback-library.v1")
        self.assertEqual(payload["summary"]["record_count"], 3)
        self.assertEqual(payload["summary"]["cycle_trend"], "improving")
        self.assertEqual(payload["records"][0]["feedback_scope"], "cycle_summary")
        self.assertEqual(
            payload["replay_feedback"]["learning_summary"]["tuned_parameters"]["max_concurrent_tasks"],
            6,
        )

    def test_learning_feedback_job_endpoint_resolves_cycle_id(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "learning feedback job"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self._persist_learning_feedback_session("cycle-1")
        response = self.client.get(f"/api/research/jobs/{job_id}/learning-feedback")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["cycle_id"], "cycle-1")
        self.assertEqual(payload["summary"]["weak_phase_names"], ["analyze"])
        self.assertEqual(len(payload["records"]), 3)

    def test_learning_feedback_list_endpoint_filters_items(self):
        self._persist_learning_feedback_session("feedback-list-a", analyze_target_phase="synthesize")
        self._persist_learning_feedback_session("feedback-list-b", analyze_target_phase="synthesize")

        response = self.client.get(
            "/api/research/learning-feedback?feedback_scope=phase_assessment&target_phase=synthesize&limit=10"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["limit"], 10)
        self.assertEqual(payload["filters"]["feedback_scope"], "phase_assessment")
        self.assertEqual(payload["filters"]["target_phase"], "synthesize")
        self.assertTrue(all(item["target_phase"] == "synthesize" for item in payload["items"]))

    def test_job_status_omits_publish_mining_alias_fields(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "桂枝汤 publish 契约"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(payload["status"], "completed")

        analysis_results = payload["result"]["analysis_results"]
        research_artifact = payload["result"]["research_artifact"]

        for removed_key in (
            "primary_association",
            "data_mining_summary",
            "data_mining_methods",
            "frequency_chi_square",
            "association_rules",
            "clustering",
        ):
            self.assertNotIn(removed_key, analysis_results)
            self.assertNotIn(removed_key, research_artifact)

        self.assertEqual(
            analysis_results["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["herb"],
            "桂枝",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["syndrome"],
            "营卫不和",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["clustering"]["cluster_summary"][0]["cluster"],
            0,
        )
        self.assertEqual(
            analysis_results["statistical_analysis"]["primary_association"]["herb"],
            "桂枝",
        )

        self.assertEqual(
            research_artifact["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["herb"],
            "桂枝",
        )
        self.assertEqual(
            research_artifact["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(
            research_artifact["data_mining_result"]["clustering"]["cluster_summary"][0]["cluster"],
            0,
        )
        self.assertEqual(
            research_artifact["statistical_analysis"]["primary_association"]["syndrome"],
            "营卫不和",
        )

    def test_dashboard_endpoint_returns_visualization_payload(self):
        create_response = self.client.post(
            "/api/research/jobs",
            json={
                "topic": "桂枝汤证据看板",
                "study_type": "rct",
                "primary_outcome": "症状评分",
                "intervention": "桂枝汤",
                "comparison": "常规治疗",
            },
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        dashboard_response = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        payload = dashboard_response.json()

        self.assertEqual(payload["job_id"], job_id)
        self.assertEqual(payload["topic"], "桂枝汤证据看板")
        self.assertEqual(payload["overview"]["status"], "completed")
        self.assertGreaterEqual(payload["overview"]["health_score"], 0.0)
        self.assertLessEqual(payload["overview"]["health_score"], 1.0)

        self.assertEqual(payload["phase_board"]["total"], 2)
        self.assertEqual(payload["phase_board"]["completed"], 2)
        self.assertEqual(payload["phase_board"]["failed"], 0)
        self.assertAlmostEqual(payload["phase_board"]["completion_rate"], 1.0, places=3)
        self.assertEqual(len(payload["phase_board"]["items"]), 2)

        self.assertAlmostEqual(payload["quality_board"]["confidence_score"], 0.92, places=3)
        self.assertAlmostEqual(payload["quality_board"]["completeness"], 0.88, places=3)
        self.assertAlmostEqual(payload["quality_board"]["quality_score"], 0.9, places=3)

        self.assertEqual(payload["evidence_board"]["evidence_count"], 1)
        self.assertEqual(payload["evidence_board"]["claim_count"], 1)
        self.assertEqual(payload["evidence_board"]["association_rule_count"], 1)
        self.assertEqual(payload["evidence_board"]["cluster_count"], 1)
        self.assertEqual(payload["evidence_board"]["primary_association"]["herb"], "桂枝")
        self.assertEqual(payload["evidence_board"]["primary_association"]["syndrome"], "营卫不和")
        self.assertEqual(payload["evidence_board"]["primary_association"]["chi2"], 8.42)
        self.assertEqual(payload["evidence_board"]["primary_association"]["contingency_table"]["a"], 8)
        self.assertEqual(payload["evidence_board"]["data_mining_summary"]["record_count"], 24)
        self.assertEqual(payload["evidence_board"]["data_mining_summary"]["association_rule_count"], 1)
        self.assertEqual(payload["evidence_board"]["data_mining_summary"]["cluster_count"], 1)
        self.assertEqual(payload["evidence_board"]["data_mining_methods"], ["association_rules", "clustering"])
        self.assertEqual(payload["evidence_board"]["terminology_standard_table_count"], 1)
        self.assertEqual(payload["evidence_board"]["collation_entry_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_document_count"], 1)
        self.assertEqual(payload["evidence_board"]["philology"]["terminology_standard_table"][0]["canonical"], "黄芪")
        self.assertEqual(payload["evidence_board"]["philology"]["collation_entries"][0]["witness_text"], "黃耆")
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["review_status"], "pending")
        self.assertEqual(payload["evidence_board"]["active_catalog_filters"], {})
        self.assertEqual(payload["evidence_board"]["catalog_filter_options"]["work_title"][0]["value"], "补血汤")

        self.assertEqual(payload["knowledge_graph_board"]["source"], "research_artifact.similar_formula_graph_evidence_summary")
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["node_count"], 2)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["edge_count"], 1)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["formula_count"], 1)
        self.assertEqual(payload["knowledge_graph_board"]["stats"]["match_count"], 1)
        self.assertEqual(payload["knowledge_graph_board"]["edges"][0]["source"], "桂枝汤")
        self.assertEqual(payload["knowledge_graph_board"]["edges"][0]["target"], "桂麻各半汤")

        self.assertEqual(payload["protocol_inputs"]["study_type"], "rct")
        self.assertEqual(payload["protocol_inputs"]["primary_outcome"], "症状评分")
        self.assertEqual(payload["protocol_inputs"]["intervention"], "桂枝汤")
        self.assertEqual(payload["protocol_inputs"]["comparison"], "常规治疗")

    def test_dashboard_endpoint_includes_learning_feedback_board_from_repository(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "学习反馈 dashboard"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self._persist_learning_feedback_session("cycle-1")

        dashboard_response = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        payload = dashboard_response.json()
        board = payload["learning_feedback_board"]

        self.assertTrue(board["available"])
        self.assertEqual(board["contract_version"], "research-feedback-library.v1")
        self.assertEqual(board["record_count"], 3)
        self.assertEqual(board["phase_record_count"], 2)
        self.assertEqual(board["cycle_trend_label"], "持续改善")
        self.assertEqual(board["weak_phase_labels"], ["分析阶段"])
        self.assertTrue(board["strategy_changed"])
        self.assertEqual(board["iteration_number"], 3)
        self.assertEqual(board["tuned_parameters"]["quality_threshold"], 0.74)
        self.assertEqual(board["recent_records"][0]["feedback_status"], "strength")
        self.assertEqual(board["recent_records"][1]["feedback_status"], "weakness")

    def test_dashboard_endpoint_accepts_catalog_filter_query_params(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "目录筛选看板"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        dashboard_response = self.client.get(
            f"/api/research/jobs/{job_id}/dashboard?work_title=%E8%A1%A5%E8%A1%80%E6%B1%A4&witness_key=console%3Awitness%3A1"
        )
        self.assertEqual(dashboard_response.status_code, 200)
        payload = dashboard_response.json()

        self.assertEqual(payload["evidence_board"]["active_catalog_filters"]["work_title"], "补血汤")
        self.assertEqual(payload["evidence_board"]["active_catalog_filters"]["witness_key"], "console:witness:1")
        self.assertEqual(payload["evidence_board"]["catalog_document_count"], 1)
        self.assertEqual(payload["evidence_board"]["catalog_summary"]["documents"][0]["work_title"], "补血汤")

    def test_catalog_review_writeback_updates_dashboard_snapshot(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "目录写回看板"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self._persist_catalog_review_session("cycle-1")
        review_response = self.client.post(
            f"/api/research/jobs/{job_id}/catalog-review",
            json={
                "scope": "version_lineage",
                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                "review_status": "accepted",
                "decision_basis": "控制台人工复核说明",
            },
        )
        self.assertEqual(review_response.status_code, 200)
        review_payload = review_response.json()
        self.assertEqual(review_payload["cycle_id"], "cycle-1")
        self.assertEqual(
            review_payload["observe_philology"]["catalog_summary"]["documents"][0]["review_status"],
            "accepted",
        )
        self.assertEqual(
            review_payload["observe_philology"]["catalog_summary"]["documents"][0]["decision_basis"],
            "控制台人工复核说明",
        )

        dashboard_response = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = dashboard_response.json()
        self.assertEqual(
            dashboard_payload["evidence_board"]["catalog_summary"]["documents"][0]["review_status"],
            "accepted",
        )
        self.assertEqual(
            dashboard_payload["evidence_board"]["catalog_summary"]["documents"][0]["decision_basis"],
            "控制台人工复核说明",
        )
        self.assertFalse(
            dashboard_payload["evidence_board"]["catalog_summary"]["documents"][0]["needs_manual_review"]
        )

    def test_philology_review_writeback_updates_claim_workbench_card(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "claim 写回看板"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self._persist_catalog_review_session("cycle-1")
        initial_dashboard = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(initial_dashboard.status_code, 200)
        initial_payload = initial_dashboard.json()
        section_map = {
            section["asset_type"]: section
            for section in initial_payload["evidence_board"]["review_workbench"]["sections"]
        }
        claim_item = section_map["claim"]["items"][0]

        review_response = self.client.post(
            f"/api/research/jobs/{job_id}/philology-review",
            json={
                "asset_type": "claim",
                "asset_key": claim_item["asset_key"],
                "review_status": "accepted",
                "decision_basis": "控制台考据 claim 复核",
                "claim_id": claim_item.get("claim_id"),
                "source_entity": claim_item.get("source_entity"),
                "target_entity": claim_item.get("target_entity"),
                "relation_type": claim_item.get("relation_type"),
            },
        )
        self.assertEqual(review_response.status_code, 200)
        review_payload = review_response.json()
        self.assertEqual(review_payload["cycle_id"], "cycle-1")
        self.assertEqual(review_payload["review_artifact"]["name"], "observe_philology_review_workbench")

        dashboard_response = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = dashboard_response.json()
        section_map = {
            section["asset_type"]: section
            for section in dashboard_payload["evidence_board"]["review_workbench"]["sections"]
        }
        reviewed_claim = section_map["claim"]["items"][0]
        self.assertEqual(reviewed_claim["review_status"], "accepted")
        self.assertEqual(reviewed_claim["decision_basis"], "控制台考据 claim 复核")
        self.assertFalse(reviewed_claim["needs_manual_review"])

    def test_batch_philology_review_writeback_records_batch_audit_summary(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "批量 claim 写回看板"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self._persist_catalog_review_session("cycle-1")
        initial_dashboard = self.client.get(f"/api/research/jobs/{job_id}/dashboard")
        self.assertEqual(initial_dashboard.status_code, 200)
        initial_payload = initial_dashboard.json()
        section_map = {
            section["asset_type"]: section
            for section in initial_payload["evidence_board"]["review_workbench"]["sections"]
        }
        claim_item = section_map["claim"]["items"][0]

        review_response = self.client.post(
            f"/api/research/jobs/{job_id}/batch-philology-review",
            json={
                "decisions": [
                    {
                        "asset_type": "claim",
                        "asset_key": claim_item["asset_key"],
                        "review_status": "needs_source",
                        "claim_id": claim_item.get("claim_id"),
                        "source_entity": claim_item.get("source_entity"),
                        "target_entity": claim_item.get("target_entity"),
                        "relation_type": claim_item.get("relation_type"),
                    }
                ],
                "selection_snapshot": {
                    "selection_strategy": "current_filtered_selection",
                    "selected_count": 1,
                    "asset_types": ["claim"],
                },
                "shared_decision_basis": "控制台批量文献学校核",
                "shared_review_reasons": ["needs_source", "reviewer_batch"],
            },
        )
        self.assertEqual(review_response.status_code, 200)
        review_payload = review_response.json()
        self.assertEqual(review_payload["applied_count"], 1)
        self.assertEqual(
            review_payload["observe_philology"]["review_workbench_last_batch_summary"]["shared_decision_basis"],
            "控制台批量文献学校核",
        )
        self.assertEqual(
            review_payload["observe_philology"]["review_workbench_last_batch_summary"]["selection_snapshot"]["selected_count"],
            1,
        )
        self.assertEqual(
            review_payload["observe_philology"]["review_workbench_last_batch_summary"]["shared_review_reasons"],
            ["needs_source", "reviewer_batch"],
        )

        dashboard_response = self.client.get(
            f"/api/research/jobs/{job_id}/dashboard?asset_type=claim&review_status=needs_source&reviewer=%E7%AE%A1%E7%90%86%20API"
        )
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = dashboard_response.json()
        self.assertEqual(dashboard_payload["evidence_board"]["queue_filters"]["active_filters"]["asset_type"], "claim")
        self.assertEqual(dashboard_payload["evidence_board"]["queue_filters"]["active_filters"]["review_status"], "needs_source")
        self.assertEqual(dashboard_payload["evidence_board"]["queue_filters"]["active_filters"]["reviewer"], "管理 API")
        self.assertGreaterEqual(dashboard_payload["evidence_board"]["review_queue"]["total_pending"], 1)
        reviewed_section_map = {
            section["asset_type"]: section
            for section in dashboard_payload["evidence_board"]["review_workbench"]["sections"]
            if section.get("items")
        }
        reviewed_claim = reviewed_section_map["claim"]["items"][0]
        self.assertEqual(reviewed_claim["review_status"], "needs_source")
        self.assertEqual(reviewed_claim["decision_basis"], "控制台批量文献学校核")

    def test_list_jobs_endpoint_returns_recent_persisted_jobs(self):
        first_job = self.client.post("/api/research/jobs", json={"topic": "最近任务 A"}).json()["job_id"]
        second_job = self.client.post("/api/research/jobs", json={"topic": "最近任务 B"}).json()["job_id"]

        for target_job in (first_job, second_job):
            for _ in range(20):
                status_response = self.client.get(f"/api/research/jobs/{target_job}")
                payload = status_response.json()
                if payload["status"] in {"completed", "partial", "failed"}:
                    break
                time.sleep(0.01)

        response = self.client.get("/api/research/jobs?limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 2)
        self.assertEqual(payload["limit"], 5)
        self.assertTrue(any(job["job_id"] == first_job for job in payload["jobs"]))
        self.assertTrue(any(job["job_id"] == second_job for job in payload["jobs"]))
        self.assertTrue(all("result" not in job for job in payload["jobs"]))

    def test_delete_completed_job_endpoint_removes_persistent_job(self):
        job_id = self.client.post("/api/research/jobs", json={"topic": "可删除任务"}).json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        delete_response = self.client.delete(f"/api/research/jobs/{job_id}")
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.json()
        self.assertEqual(delete_payload["job_id"], job_id)
        self.assertTrue(delete_payload["deleted"])

        not_found_response = self.client.get(f"/api/research/jobs/{job_id}")
        self.assertEqual(not_found_response.status_code, 404)

        list_payload = self.client.get("/api/research/jobs?limit=10").json()
        self.assertFalse(any(job["job_id"] == job_id for job in list_payload["jobs"]))

    def test_delete_running_job_endpoint_returns_conflict(self):
        started = threading.Event()
        proceed = threading.Event()
        manager = ResearchJobManager(
            runner_factory=lambda config: BlockingRunner({**config, "started": started, "continue": proceed}),
            storage_dir=os.path.join(self.tempdir.name, "blocking-jobs"),
        )
        _app = create_app(job_manager=manager)
        _app.state.settings.secrets.pop("security", None)
        client = TestClient(_app)

        job_id = client.post("/api/research/jobs", json={"topic": "运行中任务"}).json()["job_id"]
        self.assertTrue(started.wait(timeout=2.0))

        delete_response = client.delete(f"/api/research/jobs/{job_id}")
        self.assertEqual(delete_response.status_code, 409)
        self.assertIn("仅支持删除已完成、部分完成或失败的任务", delete_response.json()["detail"])

        proceed.set()
        manager.close()

    def test_report_export_endpoint_prefers_real_artifact_then_supports_json(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "桂枝汤研究"})
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        artifact_response = self.client.get(f"/api/research/jobs/{job_id}/report?format=auto")
        self.assertEqual(artifact_response.status_code, 200)
        self.assertIn("text/markdown", artifact_response.headers["content-type"])
        self.assertIn("真实最终产物", artifact_response.text)
        self.assertNotIn("研究任务报告", artifact_response.text)

        json_response = self.client.get(f"/api/research/jobs/{job_id}/report?format=json")
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("application/json", json_response.headers["content-type"])
        payload = json_response.json()
        self.assertEqual(payload["cycle_id"], "cycle-1")
        self.assertEqual(payload["phases"][0]["summary"]["observation_count"], 2)
        self.assertEqual(payload["analysis_results"]["quality_metrics"]["confidence_score"], 0.92)
        self.assertEqual(payload["research_artifact"]["hypothesis"][0]["title"], "桂枝汤调和营卫假设")

    def test_report_export_endpoint_falls_back_to_web_console_markdown(self):
        manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(config),
            storage_dir=os.path.join(self.tempdir.name, "fallback-jobs"),
        )
        _app = create_app(job_manager=manager)
        _app.state.settings.secrets.pop("security", None)
        client = TestClient(_app)

        create_response = client.post("/api/research/jobs", json={"topic": "白虎汤研究"})
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = client.get(f"/api/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        fallback_response = client.get(f"/api/research/jobs/{job_id}/report?format=auto")
        self.assertEqual(fallback_response.status_code, 200)
        self.assertIn("text/markdown", fallback_response.headers["content-type"])
        self.assertIn("研究任务报告", fallback_response.text)
        self.assertIn("研究主题：白虎汤研究", fallback_response.text)

    def test_sse_stream_returns_progress_events(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "小柴胡汤研究"})
        job_id = create_response.json()["job_id"]

        with self.client.stream("GET", f"/api/research/jobs/{job_id}/events") as response:
            self.assertEqual(response.status_code, 200)
            raw_lines = []
            for line in response.iter_lines():
                if not line:
                    continue
                raw_lines.append(line)
                if line == "event: job_completed":
                    break

        events = [line for line in raw_lines if line.startswith("event: ")]
        self.assertIn("event: phase_started", events)
        self.assertIn("event: phase_completed", events)
        self.assertIn("event: job_completed", events)

        data_lines = [line for line in raw_lines if line.startswith("data: ")]
        decoded = [json.loads(line[len("data: "):]) for line in data_lines]
        self.assertTrue(any(item.get("progress") == 50.0 for item in decoded if isinstance(item, dict)))

    def test_websocket_stream_returns_progress_events(self):
        create_response = self.client.post("/api/research/jobs", json={"topic": "柴胡桂枝汤研究"})
        job_id = create_response.json()["job_id"]

        received_events = []
        with self.client.websocket_connect(f"/api/research/jobs/{job_id}/ws") as websocket:
            for _ in range(20):
                event = websocket.receive_json()
                received_events.append(event["event"])
                if event["event"] == "job_completed":
                    break

        self.assertIn("cycle_created", received_events)
        self.assertIn("phase_started", received_events)
        self.assertIn("phase_completed", received_events)
        self.assertIn("job_completed", received_events)

    def test_job_not_found(self):
        response = self.client.get("/api/research/jobs/not-found")
        self.assertEqual(response.status_code, 404)

    def test_completed_job_is_restored_from_persistent_storage(self):
        manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner({**config, "artifact_markdown_path": self.artifact_markdown_path}),
            storage_dir=os.path.join(self.tempdir.name, "persistent-jobs"),
        )

        job = manager.create_job({"topic": "持久化恢复测试"})
        for _ in range(40):
            snapshot = manager.get_job(job.job_id).snapshot()
            if snapshot["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)
        manager.close()

        reloaded = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(config),
            storage_dir=os.path.join(self.tempdir.name, "persistent-jobs"),
        )
        restored_job = reloaded.get_job(job.job_id)

        self.assertIsNotNone(restored_job)
        restored_snapshot = restored_job.snapshot()
        self.assertEqual(restored_snapshot["status"], "completed")
        self.assertEqual(restored_snapshot["result"]["cycle_id"], "cycle-1")
        self.assertGreaterEqual(restored_snapshot["event_count"], 1)

    def test_incomplete_persisted_job_is_marked_failed_on_reload(self):
        storage_dir = os.path.join(self.tempdir.name, "interrupted-jobs")
        os.makedirs(storage_dir, exist_ok=True)
        payload = {
            "version": 1,
            "job": {
                "job_id": "interrupted-job",
                "topic": "中断任务",
                "status": "running",
                "progress": 42.0,
                "current_phase": "analyze",
                "created_at": "2026-03-30T00:00:00",
                "started_at": "2026-03-30T00:00:01",
                "completed_at": "",
                "error": "",
                "result": None,
                "event_count": 2,
            },
            "events": [
                {"sequence": 1, "event": "job_queued", "job_id": "interrupted-job", "timestamp": "2026-03-30T00:00:00", "data": {"status": "queued"}},
                {"sequence": 2, "event": "phase_started", "job_id": "interrupted-job", "timestamp": "2026-03-30T00:00:01", "data": {"phase": "analyze", "status": "running"}},
            ],
        }
        with open(os.path.join(storage_dir, "interrupted-job.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(config),
            storage_dir=storage_dir,
        )
        restored_job = manager.get_job("interrupted-job")

        self.assertIsNotNone(restored_job)
        self.assertEqual(restored_job.status, "failed")
        self.assertIn("任务执行中断", restored_job.error)
        self.assertEqual(restored_job.events[-1]["event"], "job_failed")


class TestReviewAssignmentEndpoints(unittest.TestCase):
    """Phase H / H-2: claim / release / reassign / list / workload endpoints."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.artifact_markdown_path = os.path.join(self.tempdir.name, "final-report.md")
        self.job_storage_dir = os.path.join(self.tempdir.name, "jobs")
        with open(self.artifact_markdown_path, "w", encoding="utf-8") as handle:
            handle.write("# H-2 测试产物\n")

        self.manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(
                {**config, "artifact_markdown_path": self.artifact_markdown_path}
            ),
            storage_dir=self.job_storage_dir,
            default_orchestrator_config={"runtime_profile": "web_research"},
        )
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.pop("security", None)
        self.client = TestClient(app)

        repo = ResearchSessionRepository(self.client.app.state.db_manager)
        self.cycle_id = "cycle-h2-endpoints"
        if repo.get_session(self.cycle_id) is not None:
            repo.delete_session(self.cycle_id)
        repo.create_session(
            {
                "cycle_id": self.cycle_id,
                "cycle_name": "H-2 review assignments",
                "description": "endpoint smoke",
                "research_objective": "review assignments REST API",
                "status": "running",
                "current_phase": "observe",
            }
        )

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

    def _claim(self, asset_key: str, reviewer: str, **extra):
        body = {
            "asset_type": "catalog",
            "asset_key": asset_key,
            "reviewer": reviewer,
        }
        body.update(extra)
        return self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-assignments/claim",
            json=body,
        )

    def test_claim_endpoint_creates_assignment(self):
        response = self._claim("k-1", "李研究员", priority_bucket="high", notes="紧急")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["cycle_id"], self.cycle_id)
        assignment = payload["assignment"]
        self.assertEqual(assignment["assignee"], "李研究员")
        self.assertEqual(assignment["queue_status"], "claimed")
        self.assertEqual(assignment["priority_bucket"], "high")
        self.assertEqual(assignment["reviewer_label"], "李研究员")

    def test_claim_endpoint_404_when_session_missing(self):
        response = self.client.post(
            "/api/research/sessions/missing-cycle/review-assignments/claim",
            json={"asset_type": "catalog", "asset_key": "k-1", "reviewer": "李研究员"},
        )
        self.assertEqual(response.status_code, 404)

    def test_release_endpoint_clears_assignee(self):
        self._claim("k-1", "李研究员")
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-assignments/release",
            json={"asset_type": "catalog", "asset_key": "k-1", "notes": "退回"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        assignment = response.json()["assignment"]
        self.assertIsNone(assignment["assignee"])
        self.assertEqual(assignment["queue_status"], "unassigned")
        self.assertEqual(assignment["reviewer_label"], "未认领")

    def test_release_endpoint_404_for_unknown_target(self):
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-assignments/release",
            json={"asset_type": "catalog", "asset_key": "missing"},
        )
        self.assertEqual(response.status_code, 404)

    def test_reassign_endpoint_updates_assignee(self):
        self._claim("k-1", "李研究员")
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-assignments/reassign",
            json={
                "asset_type": "catalog",
                "asset_key": "k-1",
                "new_reviewer": "张研究员",
                "priority_bucket": "low",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        assignment = response.json()["assignment"]
        self.assertEqual(assignment["assignee"], "张研究员")
        self.assertEqual(assignment["priority_bucket"], "low")

    def test_list_endpoint_supports_filtering(self):
        self._claim("k-1", "李研究员", priority_bucket="high")
        self._claim("k-2", "李研究员", priority_bucket="medium")
        self._claim("k-3", "张研究员", priority_bucket="low")

        all_response = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-assignments"
        )
        self.assertEqual(all_response.status_code, 200)
        payload = all_response.json()
        self.assertEqual(payload["count"], 3)

        only_li = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-assignments",
            params={"assignee": "李研究员"},
        )
        keys = {item["asset_key"] for item in only_li.json()["items"]}
        self.assertEqual(keys, {"k-1", "k-2"})

        only_high = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-assignments",
            params={"priority_bucket": "high"},
        )
        self.assertEqual(
            [item["asset_key"] for item in only_high.json()["items"]],
            ["k-1"],
        )

    def test_workload_endpoint_groups_by_reviewer(self):
        self._claim("k-1", "李研究员", priority_bucket="high")
        self._claim("k-2", "张研究员")
        self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-assignments/release",
            json={"asset_type": "catalog", "asset_key": "k-2"},
        )

        response = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/reviewer-workload"
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        labels = [bucket["reviewer_label"] for bucket in payload["items"]]
        self.assertIn("李研究员", labels)
        self.assertIn("未认领", labels)
        self.assertEqual(labels[-1], "未认领")
        by_label = {bucket["reviewer_label"]: bucket for bucket in payload["items"]}
        self.assertEqual(by_label["李研究员"]["high_priority"], 1)
        self.assertEqual(by_label["未认领"]["unassigned"], 1)


class TestReviewDisputeEndpoints(unittest.TestCase):
    """Phase H / H-3: open / assign / resolve / withdraw / list dispute endpoints."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.artifact_markdown_path = os.path.join(self.tempdir.name, "final-report.md")
        self.job_storage_dir = os.path.join(self.tempdir.name, "jobs")
        with open(self.artifact_markdown_path, "w", encoding="utf-8") as handle:
            handle.write("# H-3 测试产物\n")

        self.manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(
                {**config, "artifact_markdown_path": self.artifact_markdown_path}
            ),
            storage_dir=self.job_storage_dir,
            default_orchestrator_config={"runtime_profile": "web_research"},
        )
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.pop("security", None)
        self.client = TestClient(app)

        repo = ResearchSessionRepository(self.client.app.state.db_manager)
        self.cycle_id = "cycle-h3-endpoints"
        if repo.get_session(self.cycle_id) is not None:
            repo.delete_session(self.cycle_id)
        repo.create_session(
            {
                "cycle_id": self.cycle_id,
                "cycle_name": "H-3 dispute archive",
                "description": "endpoint smoke",
                "research_objective": "review dispute REST API",
                "status": "running",
                "current_phase": "observe",
            }
        )

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

    def _open(self, asset_key: str, opened_by: str, summary: str = "争议", **extra):
        body = {
            "asset_type": "catalog",
            "asset_key": asset_key,
            "summary": summary,
            "opened_by": opened_by,
        }
        body.update(extra)
        return self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-disputes/open",
            json=body,
        )

    def test_open_endpoint_creates_case(self):
        response = self._open("k-1", "李研究员")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["cycle_id"], self.cycle_id)
        dispute = payload["dispute"]
        self.assertEqual(dispute["asset_key"], "k-1")
        self.assertEqual(dispute["dispute_status"], "open")
        self.assertEqual(dispute["opened_by"], "李研究员")
        self.assertTrue(dispute["case_id"].startswith("DISP-"))

    def test_open_endpoint_with_arbitrator_assigns(self):
        response = self._open("k-1", "李研究员", arbitrator="张专家")
        self.assertEqual(response.status_code, 200, response.text)
        dispute = response.json()["dispute"]
        self.assertEqual(dispute["dispute_status"], "assigned")
        self.assertEqual(dispute["arbitrator"], "张专家")

    def test_open_endpoint_404_when_session_missing(self):
        response = self.client.post(
            "/api/research/sessions/missing-cycle/review-disputes/open",
            json={
                "asset_type": "catalog",
                "asset_key": "k-1",
                "summary": "争议",
                "opened_by": "李研究员",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_assign_endpoint_updates_arbitrator(self):
        opened = self._open("k-1", "李研究员").json()["dispute"]
        case_id = opened["case_id"]
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-disputes/{case_id}/assign",
            json={"arbitrator": "张专家", "notes": "安排裁决"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        dispute = response.json()["dispute"]
        self.assertEqual(dispute["arbitrator"], "张专家")
        self.assertEqual(dispute["dispute_status"], "assigned")

    def test_resolve_endpoint_marks_resolved(self):
        opened = self._open("k-1", "李研究员").json()["dispute"]
        case_id = opened["case_id"]
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-disputes/{case_id}/resolve",
            json={
                "resolution": "accepted",
                "resolved_by": "张专家",
                "resolution_notes": "同意原审",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        dispute = response.json()["dispute"]
        self.assertEqual(dispute["dispute_status"], "resolved")
        self.assertEqual(dispute["resolution"], "accepted")

    def test_withdraw_endpoint_marks_withdrawn(self):
        opened = self._open("k-1", "李研究员").json()["dispute"]
        case_id = opened["case_id"]
        response = self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-disputes/{case_id}/withdraw",
            json={"notes": "撤回"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        dispute = response.json()["dispute"]
        self.assertEqual(dispute["dispute_status"], "withdrawn")

    def test_list_endpoint_supports_filters(self):
        a = self._open("k-1", "李研究员").json()["dispute"]
        b = self._open("k-2", "张研究员", arbitrator="王专家").json()["dispute"]
        c = self._open("k-3", "李研究员").json()["dispute"]
        # Resolve c
        self.client.post(
            f"/api/research/sessions/{self.cycle_id}/review-disputes/{c['case_id']}/resolve",
            json={"resolution": "rejected", "resolved_by": "裁判"},
        )

        response = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-disputes",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 3)

        only_open = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-disputes",
            params={"dispute_status": "open"},
        )
        case_ids = {item["case_id"] for item in only_open.json()["items"]}
        self.assertEqual(case_ids, {a["case_id"]})

        only_arbitrator = self.client.get(
            f"/api/research/sessions/{self.cycle_id}/review-disputes",
            params={"arbitrator": "王专家"},
        )
        case_ids = {item["case_id"] for item in only_arbitrator.json()["items"]}
        self.assertEqual(case_ids, {b["case_id"]})


if __name__ == "__main__":
    unittest.main()
