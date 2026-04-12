import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.auth import get_current_user
from src.web.routes.dashboard import router as dashboard_router


class _StructuredStore:
    def list_sessions(self):
        return [
            {
                "cycle_id": "cycle-structured-1",
                "cycle_name": "结构化会话",
                "status": "completed",
                "current_phase": "reflect",
                "started_at": "2026-04-12T20:00:00",
                "research_objective": "桂枝汤研究",
                "analysis_summary": {"completed_phases": ["observe", "publish"]},
            }
        ]

    def get_session(self, cycle_id):
        if cycle_id != "cycle-structured-1":
            return None
        return {
            "cycle_id": cycle_id,
            "cycle_name": "结构化会话",
            "description": "结构化描述",
            "status": "completed",
            "current_phase": "reflect",
            "research_objective": "桂枝汤研究",
            "phase_executions": {
                "observe": {"result": {}},
                "publish": {"result": {"deliverables": [{"name": "paper.md"}]}},
            },
            "deliverables": [{"name": "paper.md"}],
            "updated_at": "2026-04-12T20:00:05",
        }


class TestDashboardCopy(unittest.TestCase):
    def _build_client(self):
        app = FastAPI()
        app.include_router(dashboard_router)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        return TestClient(app)

    def test_projects_page_empty_state_uses_run_jobs_copy(self):
        with patch("src.web.routes.dashboard._scan_research_sessions", return_value=[]), patch(
            "src.web.routes.dashboard._count_imrd_reports",
            return_value={"md": 0, "docx": 0, "total": 0},
        ):
            with self._build_client() as client:
                response = client.get("/api/projects")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("暂无研究任务", text)
        self.assertIn("POST /api/research/run", text)
        self.assertIn("POST /api/research/jobs", text)
        self.assertNotIn("/api/research/create", text)

    def test_recent_projects_empty_state_uses_run_jobs_copy(self):
        with patch("src.web.routes.dashboard._scan_research_sessions", return_value=[]):
            with self._build_client() as client:
                response = client.get("/api/projects/recent")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("POST /api/research/run", text)
        self.assertIn("POST /api/research/jobs", text)
        self.assertNotIn("/api/research/create", text)

    def test_dashboard_template_uses_recent_research_tasks_heading(self):
        template_path = Path("c:/Users/hgk/tcmautoresearch/src/web/templates/dashboard.html")
        content = template_path.read_text(encoding="utf-8")

        self.assertIn("最近研究任务", content)
        self.assertNotIn("最近研究课题", content)

    def test_recent_projects_prefers_structured_store_before_output_scan(self):
        with patch("src.web.routes.dashboard.get_legacy_research_store", return_value=_StructuredStore()), patch(
            "src.web.routes.dashboard.glob.glob",
            side_effect=AssertionError("should not scan output files"),
        ):
            with self._build_client() as client:
                response = client.get("/api/projects/recent")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("结构化会话", text)
        self.assertIn("📝 论文", text)


if __name__ == "__main__":
    unittest.main()