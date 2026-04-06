import unittest

from src.api.research_utils import normalize_research_request


class TestResearchUtils(unittest.TestCase):
    def test_normalize_research_request_injects_phase_defaults(self):
        normalized = normalize_research_request({"topic": "桂枝汤研究"})

        observe_ctx = normalized["phase_contexts"]["observe"]
        self.assertTrue(observe_ctx["use_local_corpus"])
        self.assertTrue(observe_ctx["collect_local_corpus"])
        self.assertEqual(observe_ctx["data_source"], "local")
        self.assertTrue(observe_ctx["run_preprocess_and_extract"])
        self.assertFalse(observe_ctx["run_literature_retrieval"])
        self.assertFalse(observe_ctx["use_ctext_whitelist"])
        self.assertTrue(str(observe_ctx["local_data_dir"]).endswith("data"))

        publish_ctx = normalized["phase_contexts"]["publish"]
        self.assertFalse(publish_ctx["allow_pipeline_citation_fallback"])

    def test_normalize_research_request_allows_override(self):
        normalized = normalize_research_request(
            {
                "topic": "麻黄汤研究",
                "phase_contexts": {
                    "observe": {
                        "use_local_corpus": False,
                        "run_literature_retrieval": True,
                    },
                    "publish": {
                        "allow_pipeline_citation_fallback": True,
                    },
                },
            }
        )

        observe_ctx = normalized["phase_contexts"]["observe"]
        self.assertFalse(observe_ctx["use_local_corpus"])
        self.assertTrue(observe_ctx["run_literature_retrieval"])
        # Defaults still remain available when only partial observe overrides are supplied.
        self.assertIn("local_data_dir", observe_ctx)

        publish_ctx = normalized["phase_contexts"]["publish"]
        self.assertTrue(publish_ctx["allow_pipeline_citation_fallback"])


if __name__ == "__main__":
    unittest.main()
