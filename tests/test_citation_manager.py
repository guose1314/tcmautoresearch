import unittest

from src.output.citation_manager import CitationManager
from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestCitationManager(unittest.TestCase):
    def setUp(self):
        self.manager = CitationManager({"include_abstract": False})
        self.manager.initialize()

    def tearDown(self):
        self.manager.cleanup()

    def test_generate_bibtex_from_article_records(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "title": "Large Language Models for TCM Research",
                        "authors": ["Alice Smith", "Bob Chen"],
                        "year": 2024,
                        "journal": "Journal of TCM Informatics",
                        "doi": "10.1000/tcm.2024.1",
                        "url": "https://example.com/paper",
                        "abstract": "unused",
                    }
                ]
            }
        )
        self.assertEqual(result["citation_count"], 1)
        bibtex = result["bibtex"]
        self.assertIn("@article{Smith2024Large", bibtex)
        self.assertIn("author = {Smith, Alice and Chen, Bob}", bibtex)
        self.assertIn("journal = {Journal of TCM Informatics}", bibtex)
        self.assertIn("doi = {10.1000/tcm.2024.1}", bibtex)

    def test_duplicate_keys_gain_suffix(self):
        result = self.manager.execute(
            {
                "records": [
                    {"title": "TCM Study A", "authors": ["Alice Smith"], "year": 2024, "journal": "J1"},
                    {"title": "TCM Study B", "authors": ["Alice Smith"], "year": 2024, "journal": "J2"},
                ]
            }
        )
        keys = [entry["citation_key"] for entry in result["entries"]]
        self.assertEqual(keys[0], "Smith2024TCM")
        self.assertEqual(keys[1], "Smith2024TCMb")

    def test_chinese_author_and_arxiv_misc(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "title": "中医方剂知识图谱预印本",
                        "authors": "张三, 李四",
                        "publish_date": "2023-08-01",
                        "source": "arxiv",
                        "url": "https://arxiv.org/abs/1234.5678",
                    }
                ]
            }
        )
        entry = result["entries"][0]
        self.assertEqual(entry["entry_type"], "misc")
        self.assertEqual(entry["year"], "2023")
        self.assertIn("author = {张三 and 李四}", result["bibtex"])

    def test_normalize_record_field_fallbacks(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "name": "Fallback Title",
                        "author": "Ada Lovelace",
                        "published": "2022-02-01",
                        "venue": "Fallback Venue",
                        "link": "https://example.org/fallback",
                        "page": "12-18",
                        "issue": "9",
                    }
                ]
            }
        )
        entry = result["entries"][0]
        self.assertEqual(entry["title"], "Fallback Title")
        self.assertEqual(entry["journal"], "Fallback Venue")
        self.assertEqual(entry["url"], "https://example.org/fallback")
        self.assertEqual(entry["pages"], "12-18")
        self.assertEqual(entry["number"], "9")

    def test_generate_gbt7714_from_article_record(self):
        manager = CitationManager({"format": "GB/T 7714-2015"})
        manager.initialize()
        try:
            result = manager.execute(
                {
                    "records": [
                        {
                            "title": "Large Language Models for TCM Research",
                            "authors": ["Alice Smith", "Bob Chen"],
                            "year": 2024,
                            "journal": "Journal of TCM Informatics",
                            "volume": "12",
                            "number": "3",
                            "pages": "100-120",
                            "doi": "10.1000/tcm.2024.1",
                        }
                    ]
                }
            )
            self.assertEqual(result["format"], "GB/T 7714-2015")
            self.assertIn("[1]", result["gbt7714"])
            self.assertIn("[J]", result["gbt7714"])
            self.assertIn("DOI: 10.1000/tcm.2024.1", result["gbt7714"])
            self.assertEqual(result["formatted_references"], result["gbt7714"])
        finally:
            manager.cleanup()

    def test_generate_gbt7714_with_chinese_authors(self):
        manager = CitationManager({"format": "gbt"})
        manager.initialize()
        try:
            result = manager.execute(
                {
                    "records": [
                        {
                            "title": "中医方剂知识图谱预印本",
                            "authors": "张三, 李四",
                            "publish_date": "2023-08-01",
                            "source": "arxiv",
                            "url": "https://arxiv.org/abs/1234.5678",
                        }
                    ]
                }
            )
            self.assertIn("张三, 李四", result["gbt7714"])
            self.assertIn("[EB/OL]", result["gbt7714"])
        finally:
            manager.cleanup()


class TestCitationManagerPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.pipeline = ResearchPipeline({})

    def tearDown(self):
        self.pipeline.cleanup()

    def test_publish_phase_generates_bibtex_from_observe_literature(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-citation-cycle",
            description="publish citation test",
            objective="citation generation",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "literature_pipeline": {
                    "records": [
                        {
                            "title": "Semantic Retrieval for TCM Formulae",
                            "authors": ["Ada Lovelace", "张仲景"],
                            "year": 2025,
                            "journal": "TCM AI Review",
                            "doi": "10.1000/example.doi",
                            "url": "https://example.org/retrieval",
                        }
                    ]
                }
            }
        }

        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH, {})
        self.assertEqual(result["phase"], "publish")
        self.assertEqual(result["metadata"]["citation_count"], 1)
        self.assertIn("BibTeX 参考文献", result["deliverables"])
        self.assertIn("@article{Lovelace2025Semantic", result["bibtex"])

    def test_publish_phase_prefers_context_citation_records(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-context-citation-cycle",
            description="publish citation override test",
            objective="citation override",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.PUBLISH,
            {
                "citation_records": [
                    {
                        "title": "Custom Citation Record",
                        "authors": ["Grace Hopper"],
                        "year": 2026,
                        "journal": "Custom Journal",
                    }
                ]
            },
        )
        self.assertEqual(result["metadata"]["citation_count"], 1)
        self.assertIn("Custom Citation Record", result["bibtex"])

    def test_publish_phase_includes_gbt_output(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-gbt-citation-cycle",
            description="publish gbt citation test",
            objective="citation gbt",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.PUBLISH,
            {
                "citation_records": [
                    {
                        "title": "GB/T Citation Record",
                        "authors": ["Grace Hopper"],
                        "year": 2026,
                        "journal": "Custom Journal",
                    }
                ]
            },
        )
        self.assertIn("GB/T 7714 参考文献", result["deliverables"])
        self.assertIn("[1]", result["gbt7714"])


if __name__ == "__main__":
    unittest.main()