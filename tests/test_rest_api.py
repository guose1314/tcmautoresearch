"""Architecture 3.0 REST API tests."""

import os
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from src.api.app import create_app
from web_console.job_manager import ResearchJobManager


class FakeRunner:
    def __init__(self, _config=None):
        self._config = _config or {}

    def _build_publish_contract_payload(self):
        analysis_results = {
            "statistical_analysis": {
                "interpretation": "桂枝汤核心配伍与营卫调和证据之间存在稳定关联",
                "p_value": 0.004,
                "confidence_level": 0.95,
                "effect_size": 0.74,
                "primary_association": {
                    "herb": "桂枝",
                    "syndrome": "营卫不和",
                    "p_value": 0.004,
                    "effect_size": 0.74,
                    "chi2": 8.17,
                    "sample_size": 24,
                    "contingency_table": {"a": 8, "b": 2, "c": 1, "d": 13},
                },
            },
            "data_mining_result": {
                "record_count": 24,
                "transaction_count": 24,
                "item_count": 8,
                "methods_executed": ["frequency_chi_square", "association_rules", "clustering"],
                "frequency_chi_square": {
                    "chi_square_top": [
                        {
                            "herb": "桂枝",
                            "syndrome": "营卫不和",
                            "chi2": 8.17,
                            "p_value": 0.004,
                            "effect_size": 0.74,
                        }
                    ],
                    "herb_frequency": [{"herb": "桂枝", "count": 10}],
                },
                "association_rules": {"rules": [{"rule_id": "r-1", "support": 0.42, "confidence": 0.8}]},
                "clustering": {"cluster_summary": [{"cluster": 0, "size": 24}]},
            },
        }
        research_artifact = {
            "hypothesis": [{"title": "桂枝汤调和营卫假设"}],
            "statistical_analysis": dict(analysis_results["statistical_analysis"]),
            "data_mining_result": {
                "record_count": 24,
                "transaction_count": 24,
                "item_count": 8,
                "methods_executed": ["frequency_chi_square", "association_rules", "clustering"],
                "frequency_chi_square": {
                    "chi_square_top": [
                        {
                            "herb": "桂枝",
                            "syndrome": "营卫不和",
                            "chi2": 8.17,
                            "p_value": 0.004,
                            "effect_size": 0.74,
                        }
                    ],
                    "herb_frequency": [{"herb": "桂枝", "count": 10}],
                },
                "association_rules": {"rules": [{"rule_id": "r-1", "support": 0.42, "confidence": 0.8}]},
                "clustering": {"cluster_summary": [{"cluster": 0, "size": 24}]},
            },
        }
        return analysis_results, research_artifact

    def run(self, payload, emit=None):
        topic = payload["topic"]
        protocol_inputs = {
            "study_type": payload.get("study_type"),
            "primary_outcome": payload.get("primary_outcome"),
            "intervention": payload.get("intervention"),
            "comparison": payload.get("comparison"),
        }
        analysis_results, research_artifact = self._build_publish_contract_payload()
        if emit is not None:
            emit("cycle_created", {"topic": topic, "cycle_id": "cycle-rest", "cycle_name": "demo", "scope": "test"})
            emit("phase_started", {"phase": "observe", "index": 1, "total": 1, "progress": 0.0})
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
                "cycle_id": "cycle-rest",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [
                    {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 1}},
                ],
                "pipeline_metadata": {"cycle_name": "demo", "scope": "test", "protocol_inputs": protocol_inputs},
                "analysis_results": analysis_results,
                "research_artifact": research_artifact,
            }
            emit("job_completed", {"status": "completed", "result": result})
            return _ResultWrapper(result)

        return _ResultWrapper(
            {
                "topic": topic,
                "cycle_id": "cycle-rest-sync",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [],
                "pipeline_metadata": {"cycle_name": "sync-demo", "scope": "test", "protocol_inputs": protocol_inputs},
                "analysis_results": analysis_results,
                "research_artifact": research_artifact,
            }
        )


class _ResultWrapper:
    def __init__(self, payload):
        self._payload = payload
        self.status = payload["status"]

    def to_dict(self):
        return self._payload


class TestRestApi(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.manager = ResearchJobManager(
            runner_factory=lambda config: FakeRunner(config),
            storage_dir=os.path.join(self.tempdir.name, "jobs"),
        )
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.pop("security", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

    def test_versioned_system_endpoints(self):
        root_liveness = self.client.get("/liveness")
        self.assertEqual(root_liveness.status_code, 200)
        self.assertEqual(root_liveness.json()["probe_type"], "liveness")

        root_readiness = self.client.get("/readiness")
        self.assertEqual(root_readiness.status_code, 200)
        self.assertEqual(root_readiness.json()["probe_type"], "readiness")

        health = self.client.get("/api/v1/system/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertIn("overall_health", health.json())
        self.assertIn("checks", health.json())
        self.assertIn("database_schema_drift", {item["name"] for item in health.json()["checks"]})

        liveness = self.client.get("/api/v1/system/liveness")
        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(liveness.json()["probe_type"], "liveness")

        readiness = self.client.get("/api/v1/system/readiness")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["probe_type"], "readiness")

        status = self.client.get("/api/v1/system/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["system_info"]["status"], "running")
        self.assertIn("health_report", status.json())
        self.assertIn("monitoring", status.json()["metadata"])

        modules = self.client.get("/api/v1/system/modules")
        self.assertEqual(modules.status_code, 200)
        self.assertGreaterEqual(modules.json()["count"], 1)

        metrics = self.client.get("/api/v1/system/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("jobs", metrics.json())
        self.assertIn("persistence", metrics.json())
        self.assertIn("host", metrics.json())
        self.assertIn("health", metrics.json())

        prometheus_metrics = self.client.get("/api/v1/system/metrics/prometheus")
        self.assertEqual(prometheus_metrics.status_code, 200)
        self.assertIn("tcm_system_health_score", prometheus_metrics.text)

    def test_openapi_contains_domain_dtos(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        schemas = payload["components"]["schemas"]
        self.assertIn("ResearchRunRequest", schemas)
        self.assertIn("ResearchJobAccepted", schemas)
        self.assertIn("NormalizeDocumentResponse", schemas)
        self.assertIn("AnalyzeDocumentResponse", schemas)
        self.assertIn("SystemExportResponse", schemas)

        run_request_props = schemas["ResearchRunRequest"]["properties"]
        self.assertIn("study_type", run_request_props)
        self.assertIn("primary_outcome", run_request_props)
        self.assertIn("intervention", run_request_props)
        self.assertIn("comparison", run_request_props)

        job_post = payload["paths"]["/api/v1/research/jobs"]["post"]
        schema_ref = job_post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        self.assertTrue(schema_ref.endswith("/ResearchRunRequest"))

    def test_collection_normalize_endpoint(self):
        response = self.client.post(
            "/api/v1/collection/documents/normalize",
            json={
                "text": "當歸補血湯主治血虛發熱。",
                "title": "古籍片段",
                "metadata": {"dynasty": "清"},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["standard_document"]["metadata"]["dynasty"], "清")
        self.assertIn("当归补血汤", payload["standard_document"]["text"])
        self.assertTrue(payload["normalization"]["success"])

    def test_analysis_preview_endpoint(self):
        response = self.client.post(
            "/api/v1/analysis/documents/preview",
            json={"text": "桂枝汤由桂枝、白芍、甘草组成，可治太阳中风。"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["analysis_summary"]["entity_count"], 1)
        self.assertIn("preview_tokens", payload["analysis_summary"])
        self.assertIn("entities", payload["analysis_result"])

    def test_versioned_research_job_lifecycle(self):
        create_response = self.client.post("/api/v1/research/jobs", json={"topic": "桂枝汤 REST 研究"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]
        self.assertIn("versioned_websocket_url", create_response.json())

        for _ in range(20):
            status_response = self.client.get(f"/api/v1/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(payload["status"], "completed")

        report_response = self.client.get(f"/api/v1/research/jobs/{job_id}/report?format=json")
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["cycle_id"], "cycle-rest")

    def test_versioned_run_accepts_explicit_protocol_inputs(self):
        response = self.client.post(
            "/api/v1/research/run",
            json={
                "topic": "黄芪颗粒治疗疲劳综合征",
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

    def test_versioned_run_omits_publish_mining_alias_fields(self):
        response = self.client.post(
            "/api/v1/research/run",
            json={"topic": "桂枝汤 publish 直达字段契约"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        analysis_results = payload["analysis_results"]
        research_artifact = payload["research_artifact"]

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
            analysis_results["statistical_analysis"]["primary_association"]["herb"],
            "桂枝",
        )
        self.assertEqual(
            analysis_results["statistical_analysis"]["primary_association"]["syndrome"],
            "营卫不和",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["herb"],
            "桂枝",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(analysis_results["data_mining_result"]["record_count"], 24)
        self.assertEqual(
            analysis_results["data_mining_result"]["methods_executed"],
            ["frequency_chi_square", "association_rules", "clustering"],
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["clustering"]["cluster_summary"][0]["cluster"],
            0,
        )

        self.assertEqual(
            research_artifact["statistical_analysis"]["primary_association"],
            analysis_results["statistical_analysis"]["primary_association"],
        )
        self.assertEqual(
            research_artifact["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["syndrome"],
            "营卫不和",
        )
        self.assertEqual(
            research_artifact["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(research_artifact["data_mining_result"]["record_count"], 24)
        self.assertEqual(
            research_artifact["data_mining_result"]["clustering"]["cluster_summary"][0]["size"],
            24,
        )

    def test_websocket_progress_stream_coexists_with_sse(self):
        create_response = self.client.post("/api/v1/research/jobs", json={"topic": "WebSocket 研究"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        received_events = []
        with self.client.websocket_connect(f"/api/v1/research/jobs/{job_id}/ws") as websocket:
            for _ in range(20):
                event = websocket.receive_json()
                received_events.append(event["event"])
                if event["event"] == "job_completed":
                    break

        self.assertIn("phase_started", received_events)
        self.assertIn("phase_completed", received_events)
        self.assertIn("job_completed", received_events)

    def test_system_export_and_persistence_endpoints(self):
        create_response = self.client.post("/api/v1/research/jobs", json={"topic": "持久化接口研究"})
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(f"/api/v1/research/jobs/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        export_response = self.client.post(
            "/api/v1/system/export",
            json={"output_name": "rest-api-export.json", "include_payload": True},
        )
        self.assertEqual(export_response.status_code, 200)
        export_payload = export_response.json()
        self.assertTrue(export_payload["exported"])
        self.assertTrue(export_payload["output_path"].endswith("rest-api-export.json"))
        self.assertIn("payload", export_payload)

        inline_export = self.client.get("/api/v1/system/export")
        self.assertEqual(inline_export.status_code, 200)
        self.assertIn("system_status", inline_export.json())

        persistence_summary = self.client.get("/api/v1/system/persistence/summary")
        self.assertEqual(persistence_summary.status_code, 200)
        self.assertGreaterEqual(persistence_summary.json()["stored_job_count"], 1)

        persisted_jobs = self.client.get("/api/v1/system/persistence/jobs?limit=5")
        self.assertEqual(persisted_jobs.status_code, 200)
        jobs_payload = persisted_jobs.json()
        self.assertTrue(any(item["job_id"] == job_id for item in jobs_payload["jobs"]))

        persisted_job = self.client.get(f"/api/v1/system/persistence/jobs/{job_id}")
        self.assertEqual(persisted_job.status_code, 200)
        persisted_payload = persisted_job.json()
        self.assertEqual(persisted_payload["job"]["job_id"], job_id)
        self.assertIsInstance(persisted_payload["events"], list)