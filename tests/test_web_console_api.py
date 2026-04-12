"""tests/test_web_console_api.py — 3.4 FastAPI + SSE 接口测试"""

import json
import os
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient

from web_console.app import create_app
from web_console.job_manager import ResearchJobManager


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
        )
        self.manager = manager
        app = create_app(job_manager=manager)
        app.state.settings.secrets.pop("security", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

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


if __name__ == "__main__":
    unittest.main()
