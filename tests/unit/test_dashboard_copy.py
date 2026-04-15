import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
            "observe_documents": [
                {
                    "urn": "doc:structured:1",
                    "title": "补血汤宋本",
                    "source_file": "c:/tmp/buxue-songben.txt",
                    "source_type": "local",
                }
            ],
            "observe_philology": {
                "source": "observe_philology",
                "terminology_standard_table_count": 1,
                "collation_entry_count": 1,
                "catalog_document_count": 1,
                "version_lineage_count": 1,
                "witness_count": 1,
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
                        "source_type_counts": {"local": 1},
                    },
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
                                    "urn": "doc:structured:1",
                                    "source_type": "local",
                                    "catalog_id": "local:catalog:1",
                                    "witness_key": "local:doc:structured:1",
                                }
                            ],
                        }
                    ],
                },
                "terminology_standard_table": [
                    {
                        "document_title": "补血汤宋本",
                        "document_urn": "doc:structured:1",
                        "canonical": "黄芪",
                        "label": "本草药名",
                        "status": "standardized",
                        "observed_forms": ["黃芪"],
                        "configured_variants": ["黃耆"],
                        "sources": ["normalizer_term_mapping"],
                        "notes": ["黃芪 统一为 黄芪（本草药名）"],
                    }
                ],
                "collation_entries": [
                    {
                        "document_title": "补血汤宋本",
                        "document_urn": "doc:structured:1",
                        "difference_type": "replace",
                        "base_text": "黃芪",
                        "witness_text": "黃耆",
                        "base_context": "宋本作黃芪",
                        "witness_context": "异本作黃耆",
                        "judgement": "术语异写",
                        "source": "auto_version_collation",
                    }
                ],
            },
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
        structured_store = _StructuredStore()
        with patch("src.web.routes.dashboard.list_research_sessions", return_value=structured_store.list_sessions()), patch(
            "src.web.routes.dashboard.get_research_session",
            side_effect=lambda app, cycle_id: structured_store.get_session(cycle_id),
        ), patch(
            "src.web.routes.dashboard.glob.glob",
            side_effect=AssertionError("should not scan output files"),
        ):
            with self._build_client() as client:
                response = client.get("/api/projects/recent")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("结构化会话", text)
        self.assertIn("📝 论文", text)
        self.assertIn("查看详情", text)
        self.assertIn("/api/projects/cycle-structured-1/detail?terminology_page=1&amp;collation_page=1&amp;drawer=1", text)

    def test_projects_page_renders_detail_panel_for_initial_session(self):
        structured_store = _StructuredStore()
        sessions = [
            {
                "cycle_id": "cycle-structured-1",
                "title": "结构化会话",
                "question": "桂枝汤研究",
                "status": "completed",
                "phases": ["observe", "publish"],
                "has_reports": True,
            }
        ]
        with patch("src.web.routes.dashboard._scan_research_sessions", return_value=sessions), patch(
            "src.web.routes.dashboard._count_imrd_reports",
            return_value={"md": 1, "docx": 0, "total": 1},
        ), patch(
            "src.web.routes.dashboard.get_research_session",
            side_effect=lambda app, cycle_id: structured_store.get_session(cycle_id),
        ):
            with self._build_client() as client:
                response = client.get("/api/projects")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("project-detail-panel", text)
        self.assertIn("目录学基线", text)
        self.assertIn("术语标准表", text)
        self.assertIn("校勘条目明细", text)
        self.assertIn("查看详情", text)

    def test_project_detail_endpoint_paginates_terminology_and_collation(self):
        session = {
            "cycle_id": "cycle-detail-1",
            "cycle_name": "细节研究",
            "research_objective": "桂枝汤文本校勘",
            "status": "completed",
            "current_phase": "reflect",
            "phase_executions": {"observe": {"result": {}}, "publish": {"result": {}}},
            "observe_philology": {
                "source": "observe_philology",
                "terminology_standard_table_count": 9,
                "collation_entry_count": 7,
                "annotation_report": {
                    "summary": {
                        "processed_document_count": 2,
                        "philology_notes": ["整理 9 条术语标准表记录", "输出 7 条可复用校勘条目"],
                    }
                },
                "terminology_standard_table": [
                    {
                        "document_title": f"文献{i}",
                        "document_urn": f"doc:term:{i}",
                        "canonical": f"术语{i}",
                        "label": "本草药名",
                        "status": "standardized",
                        "observed_forms": [f"异写{i}"],
                        "configured_variants": [f"变体{i}"],
                        "sources": ["lexicon_glossary"],
                        "notes": [f"注记{i}"],
                    }
                    for i in range(1, 10)
                ],
                "collation_entries": [
                    {
                        "document_title": f"文献{i}",
                        "document_urn": f"doc:collation:{i}",
                        "witness_title": f"异本{i}",
                        "difference_type": "replace",
                        "base_text": f"底本{i}",
                        "witness_text": f"异文{i}",
                        "base_context": f"base context {i}",
                        "witness_context": f"witness context {i}",
                        "judgement": "术语异写",
                        "source": "auto_version_collation",
                        "selection_strategy": "same_title",
                        "note": f"校勘说明{i}",
                    }
                    for i in range(1, 8)
                ],
            },
        }

        with patch("src.web.routes.dashboard.get_research_session", return_value=session):
            with self._build_client() as client:
                first_page = client.get("/api/projects/cycle-detail-1/detail")
                second_page = client.get("/api/projects/cycle-detail-1/detail?terminology_page=2&collation_page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertIn("术语1", first_page.text)
        self.assertNotIn("术语9", first_page.text)
        self.assertIn("异文1", first_page.text)
        self.assertNotIn("异文7", first_page.text)
        self.assertIn("第 1 / 2 页", first_page.text)

        self.assertEqual(second_page.status_code, 200)
        self.assertIn("术语9", second_page.text)
        self.assertIn("异文7", second_page.text)
        self.assertIn("第 2 / 2 页", second_page.text)

    def test_project_detail_endpoint_filters_by_document_title(self):
        session = {
            "cycle_id": "cycle-filter-1",
            "cycle_name": "筛选研究",
            "research_objective": "文献筛选测试",
            "status": "completed",
            "current_phase": "reflect",
            "phase_executions": {"observe": {"result": {}}, "publish": {"result": {}}},
            "observe_philology": {
                "annotation_report": {"summary": {"processed_document_count": 2}},
                "terminology_standard_table": [
                    {
                        "document_title": "宋本",
                        "document_urn": "doc:filter:1",
                        "canonical": "黄芪",
                        "label": "本草药名",
                        "status": "standardized",
                        "observed_forms": ["黃芪"],
                        "configured_variants": [],
                        "sources": ["lexicon_glossary"],
                        "notes": ["宋本注记"],
                    },
                    {
                        "document_title": "影印本",
                        "document_urn": "doc:filter:2",
                        "canonical": "当归",
                        "label": "本草药名",
                        "status": "standardized",
                        "observed_forms": ["當歸"],
                        "configured_variants": [],
                        "sources": ["lexicon_glossary"],
                        "notes": ["影印本注记"],
                    },
                ],
                "collation_entries": [
                    {
                        "document_title": "宋本",
                        "document_urn": "doc:filter:1",
                        "witness_title": "影印本",
                        "difference_type": "replace",
                        "base_text": "黃芪",
                        "witness_text": "黃耆",
                        "base_context": "宋本作黃芪",
                        "witness_context": "影印本作黃耆",
                        "judgement": "术语异写",
                        "source": "auto_version_collation",
                    }
                ],
            },
        }

        with patch("src.web.routes.dashboard.get_research_session", return_value=session):
            with self._build_client() as client:
                response = client.get("/api/projects/cycle-filter-1/detail?document_title=%E5%AE%8B%E6%9C%AC")

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("当前筛选：宋本", text)
        self.assertIn("黄芪", text)
        self.assertNotIn("当归", text)
        self.assertIn("跳到原始片段", text)

    def test_project_detail_endpoint_filters_by_catalog_query_params(self):
        session = {
            "cycle_id": "cycle-catalog-filter-1",
            "cycle_name": "目录筛选研究",
            "research_objective": "目录学筛选测试",
            "status": "completed",
            "current_phase": "reflect",
            "phase_executions": {"observe": {"result": {}}, "publish": {"result": {}}},
            "observe_philology": {
                "catalog_summary": {
                    "documents": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:catalog:1",
                            "source_type": "local",
                            "catalog_id": "catalog:1",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "witness:1",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                        },
                        {
                            "document_title": "十全大补汤影印本",
                            "document_urn": "doc:catalog:2",
                            "source_type": "scan",
                            "catalog_id": "catalog:2",
                            "work_title": "十全大补汤",
                            "fragment_title": "十全大补汤",
                            "work_fragment_key": "十全大补汤|十全大补汤",
                            "version_lineage_key": "十全大补汤|十全大补汤|清|佚名|影印本",
                            "witness_key": "witness:2",
                            "dynasty": "清",
                            "author": "佚名",
                            "edition": "影印本",
                        },
                    ]
                },
                "terminology_standard_table": [
                    {
                        "document_title": "补血汤宋本",
                        "document_urn": "doc:catalog:1",
                        "canonical": "黄芪",
                        "label": "本草药名",
                        "notes": ["黃芪 统一为 黄芪（本草药名）"],
                    },
                    {
                        "document_title": "十全大补汤影印本",
                        "document_urn": "doc:catalog:2",
                        "canonical": "当归",
                        "label": "本草药名",
                        "notes": ["當歸 统一为 当归（本草药名）"],
                    },
                ],
                "annotation_report": {"summary": {"processed_document_count": 2}},
            },
        }

        with patch("src.web.routes.dashboard.get_research_session", return_value=session):
            with self._build_client() as client:
                work_response = client.get("/api/projects/cycle-catalog-filter-1/detail?work_title=%E8%A1%A5%E8%A1%80%E6%B1%A4")
                lineage_response = client.get(
                    "/api/projects/cycle-catalog-filter-1/detail?version_lineage_key=%E5%8D%81%E5%85%A8%E5%A4%A7%E8%A1%A5%E6%B1%A4%7C%E5%8D%81%E5%85%A8%E5%A4%A7%E8%A1%A5%E6%B1%A4%7C%E6%B8%85%7C%E4%BD%9A%E5%90%8D%7C%E5%BD%B1%E5%8D%B0%E6%9C%AC"
                )
                witness_response = client.get("/api/projects/cycle-catalog-filter-1/detail?witness_key=witness%3A1")

        self.assertEqual(work_response.status_code, 200)
        self.assertIn("当前筛选：补血汤", work_response.text)
        self.assertIn("黄芪", work_response.text)
        self.assertNotIn("当归", work_response.text)

        self.assertEqual(lineage_response.status_code, 200)
        self.assertIn("当前筛选：十全大补汤", lineage_response.text)
        self.assertIn("当归", lineage_response.text)
        self.assertNotIn("黄芪", lineage_response.text)

        self.assertEqual(witness_response.status_code, 200)
        self.assertIn("当前筛选：补血汤宋本", witness_response.text)
        self.assertIn("黄芪", witness_response.text)
        self.assertNotIn("当归", witness_response.text)

    def test_fragment_preview_endpoint_uses_local_source_text_when_available(self):
        with TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "补血汤宋本.txt"
            source_path.write_text("前文。宋本作黃芪，补中益气。后文。", encoding="utf-8")
            session = {
                "cycle_id": "cycle-fragment-1",
                "observe_documents": [
                    {
                        "urn": "doc:fragment:1",
                        "title": "补血汤宋本",
                        "source_file": str(source_path),
                        "source_type": "local",
                    }
                ],
            }

            with patch("src.web.routes.dashboard.get_research_session", return_value=session):
                with self._build_client() as client:
                    response = client.get(
                        "/api/projects/cycle-fragment-1/fragment-preview"
                        "?document_urn=doc:fragment:1"
                        "&document_title=%E8%A1%A5%E8%A1%80%E6%B1%A4%E5%AE%8B%E6%9C%AC"
                        "&highlight=%E9%BB%83%E8%8A%AA"
                        "&context=%E5%AE%8B%E6%9C%AC%E4%BD%9C%E9%BB%83%E8%8A%AA"
                        "&role=base"
                    )

        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("原始文档片段", text)
        self.assertIn("补血汤宋本", text)
        self.assertIn("已定位本地源文献片段", text)
        self.assertIn("<mark", text)

    def test_dashboard_template_has_session_detail_drawer(self):
        template_path = Path("c:/Users/hgk/tcmautoresearch/src/web/templates/dashboard.html")
        content = template_path.read_text(encoding="utf-8")

        self.assertIn("session-detail-drawer", content)
        self.assertIn("openSessionDetailDrawer", content)
        self.assertIn("closeSessionDetailDrawer", content)
        self.assertIn("document-fragment-modal", content)
        self.assertIn("openDocumentFragmentModal", content)
        self.assertIn("closeDocumentFragmentModal", content)


if __name__ == "__main__":
    unittest.main()