from __future__ import annotations

import unittest

from tools.run_card_g_minimal_regression import (
    E2E_TESTS,
    REGRESSION_GROUPS,
    build_manifest,
    build_pytest_command,
    iter_regression_tests,
    missing_tests,
)


class CardGMinimalRegressionTest(unittest.TestCase):
    def test_manifest_covers_cards_a_to_f(self) -> None:
        self.assertEqual(
            list(REGRESSION_GROUPS),
            [
                "card_a_terminology",
                "card_b_topic_discovery",
                "card_c_textual_criticism",
                "card_d_tcm_reasoning",
                "card_e_expert_review_governance",
                "card_f_graph_rag_typed_retrieval",
            ],
        )
        tests = iter_regression_tests()
        self.assertIn("tests/unit/test_transaction_terminology_resolution.py", tests)
        self.assertIn("tests/unit/test_observe_topic_discovery.py", tests)
        self.assertIn("tests/unit/test_textual_criticism_phase_wiring.py", tests)
        self.assertIn("tests/unit/test_tcm_reasoning_phase_wiring.py", tests)
        self.assertIn("tests/integration_tests/test_expert_review_roundtrip.py", tests)
        self.assertIn("tests/integration_tests/test_graph_rag_traceability.py", tests)
        self.assertEqual(missing_tests(tests), [])

    def test_e2e_is_opt_in(self) -> None:
        without_e2e = iter_regression_tests()
        with_e2e = iter_regression_tests(include_e2e=True)
        self.assertNotIn(E2E_TESTS[0], without_e2e)
        self.assertIn(E2E_TESTS[0], with_e2e)

    def test_pytest_command_keeps_minimal_defaults(self) -> None:
        command = build_pytest_command(strict_known_failures=True)
        self.assertEqual(command[1:3], ["-m", "pytest"])
        self.assertIn("-q", command)
        self.assertIn("--tb=short", command)
        self.assertIn("--strict-known-failures", command)
        self.assertIn("tests/unit/test_graph_rag.py", command)

    def test_manifest_is_printable_contract(self) -> None:
        manifest = build_manifest(include_e2e=True)
        self.assertEqual(manifest["contract"], "card-g-minimal-regression-v1")
        self.assertTrue(manifest["include_e2e"])
        self.assertEqual(manifest["e2e_tests"], list(E2E_TESTS))
        self.assertEqual(manifest["test_count"], len(manifest["tests"]))


if __name__ == "__main__":
    unittest.main()
