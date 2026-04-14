import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.auth import get_current_user
from src.web.routes.analysis import router as analysis_router
from src.web.routes.research import router as research_router


def _fake_create_session(app, **kwargs):
    app.state.created_payload = deepcopy(kwargs)
    return {
        "cycle_id": "cycle-1",
        "cycle_name": kwargs["cycle_name"],
        "research_objective": kwargs["objective"],
        "status": "pending",
        "current_phase": "observe",
    }


def _fake_get_session(app, cycle_id):
    if cycle_id != "cycle-1":
        return None
    return {
        "cycle_id": "cycle-1",
        "cycle_name": "测试研究",
        "phase_executions": {
            "observe": {
                "result": {
                    "semantic_graph": {
                        "nodes": [{"id": "node-1"}],
                        "edges": [{"source": "node-1", "target": "node-2"}],
                    },
                    "graph_statistics": {"nodes_count": 1},
                }
            }
        },
    }


def _fake_list_sessions(app):
    return [
        {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "status": "active",
            "current_phase": "analyze",
            "started_at": None,
            "research_objective": "测试目标",
            "analysis_summary": {},
        }
    ]


def _fake_execute_phase(app, cycle_id, phase_name, **kwargs):
    app.state.executed_payload = {
        "cycle_id": cycle_id,
        "phase_name": phase_name,
        **deepcopy(kwargs),
    }
    return {
        "cycle": {"cycle_id": cycle_id, "status": "active", "current_phase": "analyze"},
        "phase_result": {"phase": phase_name, "status": "completed"},
    }


def _fake_get_observe_graph(app, cycle_id):
    if cycle_id != "cycle-1":
        return None
    return {
        "nodes": [{"id": "node-1"}],
        "edges": [{"source": "node-1", "target": "node-2"}],
        "statistics": {"nodes_count": 1},
    }


class TestResearchRouteContract(unittest.TestCase):
    def _build_app(self, router):
        app = FastAPI()
        app.state.config = {}
        app.state.created_payload = None
        app.state.executed_payload = None
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        return app

    def test_research_routes_keep_contract(self):
        app = self._build_app(research_router)

        with patch("src.web.routes.research.create_research_session", side_effect=_fake_create_session), patch(
            "src.web.routes.research.get_research_session",
            side_effect=_fake_get_session,
        ), patch(
            "src.web.routes.research.list_research_sessions",
            side_effect=_fake_list_sessions,
        ), patch(
            "src.web.routes.research.execute_research_session_phase",
            side_effect=_fake_execute_phase,
        ):
            with TestClient(app) as client:
                create_response = client.post(
                    "/api/research/create",
                    json={
                        "cycle_name": "测试研究",
                        "description": "测试描述",
                        "objective": "测试目标",
                        "scope": "方剂",
                    },
                )
                self.assertEqual(create_response.status_code, 201)
                self.assertEqual(create_response.json()["cycle"]["cycle_id"], "cycle-1")
                self.assertEqual(app.state.created_payload["objective"], "测试目标")

                detail_response = client.get("/api/research/cycle-1")
                self.assertEqual(detail_response.status_code, 200)
                self.assertEqual(detail_response.json()["cycle"]["cycle_id"], "cycle-1")

                execute_response = client.post(
                    "/api/research/cycle-1/execute",
                    json={"phase": "analyze", "phase_context": {"top_k": 5}},
                )
                self.assertEqual(execute_response.status_code, 200)
                self.assertEqual(execute_response.json()["result"]["phase"], "analyze")
                self.assertEqual(app.state.executed_payload["phase_name"], "analyze")
                self.assertEqual(app.state.executed_payload["phase_context"]["top_k"], 5)
                self.assertIsNotNone(app.state.executed_payload["emit"])

                list_response = client.get("/api/research/list")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(list_response.json()["total"], 1)

    def test_analysis_graph_route_reads_same_contract(self):
        app = self._build_app(analysis_router)

        with patch("src.web.routes.analysis.get_research_session", side_effect=_fake_get_session), patch(
            "src.web.routes.analysis.get_research_observe_graph",
            side_effect=_fake_get_observe_graph,
        ):
            with TestClient(app) as client:
                response = client.get("/api/analysis/graph/cycle-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["research_id"], "cycle-1")
        self.assertEqual(payload["graph"]["statistics"]["nodes_count"], 1)


if __name__ == "__main__":
    unittest.main()