import unittest

from src.generation.llm_context_adapter import LLMContextAdapter


def _phase_result(phase: str, results: dict | None = None, metadata: dict | None = None):
    return {
        "phase": phase,
        "status": "completed",
        "results": results or {},
        "artifacts": [],
        "metadata": metadata or {},
        "error": None,
    }


class TestLLMContextAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = LLMContextAdapter()

    def test_adapt_context_reads_modules_from_phase_result_payload(self):
        adapted = self.adapter.adapt_context(
            _phase_result(
                "analyze",
                {
                    "network_pharmacology_systems_biology": {
                        "桂枝汤": {"targets": ["TNF", "IL6"], "pathways": ["NF-kB"]}
                    },
                    "complexity_nonlinear_dynamics": {
                        "桂枝汤": {"entropy": 0.42}
                    },
                    "formula_comparisons": [
                        {
                            "formula_a": "桂枝汤",
                            "formula_b": "桂麻各半汤",
                            "similarity": 0.87,
                        }
                    ],
                },
            )
        )

        llm_context = adapted.get("llm_analysis_context") or {}
        analysis_modules = llm_context.get("analysis_modules") or {}
        self.assertEqual(
            analysis_modules.get("network_pharmacology", {}).get("桂枝汤", {}).get("targets"),
            ["TNF", "IL6"],
        )
        self.assertEqual(
            analysis_modules.get("complexity_dynamics", {}).get("桂枝汤", {}).get("entropy"),
            0.42,
        )
        self.assertEqual(
            analysis_modules.get("formula_comparisons", [{}])[0].get("formula_b"),
            "桂麻各半汤",
        )
        self.assertIn("network_pharmacology", llm_context.get("populated_modules") or [])
        self.assertEqual(
            adapted.get("analysis_results", {}).get("llm_analysis_context", {}).get("contract_version"),
            "llm-analysis-context-v1",
        )

    def test_adapt_context_reads_session_phase_results_publish_and_analyze_payloads(self):
        adapted = self.adapter.adapt_context(
            {
                "analysis_results": {},
                "research_artifact": {},
                "phase_results": {
                    "analyze": _phase_result(
                        "analyze",
                        {
                            "network_pharmacology_systems_biology": {
                                "桂枝汤": {"targets": ["TNF", "IL6"]}
                            }
                        },
                    ),
                    "publish": _phase_result(
                        "publish",
                        {
                            "analysis_results": {
                                "summary_analysis": {
                                    "core_findings": ["桂枝汤网络靶点与营卫调和路径高度相关"]
                                }
                            },
                            "research_artifact": {
                                "research_perspectives": {
                                    "桂枝汤": {
                                        "integrated": {
                                            "summary": "多源证据支持桂枝汤的营卫调和机制"
                                        }
                                    }
                                }
                            },
                        },
                    ),
                },
            }
        )

        analysis_modules = adapted.get("analysis_modules") or {}
        self.assertEqual(
            analysis_modules.get("network_pharmacology", {}).get("桂枝汤", {}).get("targets"),
            ["TNF", "IL6"],
        )
        self.assertEqual(
            analysis_modules.get("summary_analysis", {}).get("core_findings"),
            ["桂枝汤网络靶点与营卫调和路径高度相关"],
        )
        self.assertEqual(
            analysis_modules.get("research_perspectives", {}).get("桂枝汤", {}).get("integrated", {}).get("summary"),
            "多源证据支持桂枝汤的营卫调和机制",
        )


if __name__ == "__main__":
    unittest.main()