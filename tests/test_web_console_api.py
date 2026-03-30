"""tests/test_web_console_api.py — 3.4 FastAPI + SSE 接口测试"""

import json
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
                "phases": [
                    {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 2}},
                    {"phase": "analyze", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"key_findings": ["A"]}},
                ],
                "pipeline_metadata": {"cycle_name": "demo"},
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
                "pipeline_metadata": {"cycle_name": "sync-demo"},
            }
        )


class _ResultWrapper:
    def __init__(self, payload):
        self._payload = payload
        self.status = payload["status"]

    def to_dict(self):
        return self._payload


class TestWebConsoleApi(unittest.TestCase):
    def setUp(self):
        manager = ResearchJobManager(runner_factory=lambda config: FakeRunner(config))
        self.client = TestClient(create_app(job_manager=manager))

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_sync_run_endpoint(self):
        response = self.client.post("/api/research/run", json={"topic": "四君子汤研究"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["pipeline_metadata"]["cycle_name"], "sync-demo")

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

    def test_job_not_found(self):
        response = self.client.get("/api/research/jobs/not-found")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()