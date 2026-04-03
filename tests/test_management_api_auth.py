"""Management API key protection tests."""

import os
import tempfile
import time
import unittest
from typing import Any, cast

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from src.api.app import create_app
from web_console.job_manager import ResearchJobManager


class FakeRunner:
    def __init__(self, _config=None):
        self._config = _config or {}

    def run(self, payload, emit=None):
        topic = payload["topic"]
        if emit is not None:
            emit("cycle_created", {"topic": topic, "cycle_id": "cycle-auth", "cycle_name": "demo", "scope": "test"})
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
                "cycle_id": "cycle-auth",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [
                    {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 1}},
                ],
                "pipeline_metadata": {"cycle_name": "demo", "scope": "test"},
            }
            emit("job_completed", {"status": "completed", "result": result})
            return _ResultWrapper(result)

        return _ResultWrapper(
            {
                "topic": topic,
                "cycle_id": "cycle-auth-sync",
                "status": "completed",
                "started_at": "2026-03-30T00:00:00",
                "completed_at": "2026-03-30T00:00:01",
                "total_duration_sec": 1.0,
                "phases": [],
                "pipeline_metadata": {"cycle_name": "sync-demo", "scope": "test"},
            }
        )


class _ResultWrapper:
    def __init__(self, payload):
        self._payload = payload
        self.status = payload["status"]

    def to_dict(self):
        return self._payload


class TestManagementApiAuth(unittest.TestCase):
    def setUp(self):
        self.api_key = "test-management-key"
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.manager = ResearchJobManager(
            runner_factory=lambda config: cast(Any, FakeRunner(config)),
            storage_dir=os.path.join(self.tempdir.name, "jobs"),
        )
        app = create_app(job_manager=self.manager)
        app.state.settings.secrets.setdefault("security", {})["management_api_key"] = self.api_key
        self.client = TestClient(app)

    def tearDown(self):
        self.manager.close()
        self.tempdir.cleanup()

    def test_protected_http_endpoints_require_management_api_key(self):
        response = self.client.get("/api/v1/system/status")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Bearer", response.headers.get("www-authenticate", ""))

        ok = self.client.get("/api/v1/system/status", headers={"X-API-Key": self.api_key})
        self.assertEqual(ok.status_code, 200)

    def test_bearer_token_and_query_param_auth_are_accepted(self):
        create_response = self.client.post(
            "/api/v1/research/jobs",
            json={"topic": "鉴权测试研究"},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        for _ in range(20):
            status_response = self.client.get(
                f"/api/v1/research/jobs/{job_id}",
                headers={"X-API-Key": self.api_key},
            )
            payload = status_response.json()
            if payload["status"] in {"completed", "partial", "failed"}:
                break
            time.sleep(0.01)

        events_response = self.client.get(f"/api/v1/research/jobs/{job_id}/events?api_key={self.api_key}")
        self.assertEqual(events_response.status_code, 200)
        self.assertIn("text/event-stream", events_response.headers["content-type"])

    def test_websocket_requires_key_and_accepts_query_param(self):
        create_response = self.client.post(
            "/api/v1/research/jobs",
            json={"topic": "WebSocket 鉴权测试"},
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(create_response.status_code, 202)
        job_id = create_response.json()["job_id"]

        with self.assertRaises(WebSocketDisconnect) as missing_key:
            with self.client.websocket_connect(f"/api/v1/research/jobs/{job_id}/ws"):
                pass
        self.assertEqual(missing_key.exception.code, 4401)

        received_events = []
        with self.client.websocket_connect(f"/api/v1/research/jobs/{job_id}/ws?api_key={self.api_key}") as websocket:
            for _ in range(20):
                event = websocket.receive_json()
                received_events.append(event["event"])
                if event["event"] == "job_completed":
                    break

        self.assertIn("phase_started", received_events)
        self.assertIn("job_completed", received_events)


if __name__ == "__main__":
    unittest.main()
