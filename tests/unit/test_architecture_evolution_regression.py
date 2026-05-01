from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.run_architecture_evolution_regression import (
    E2E_TESTS,
    REGRESSION_GROUPS,
    REQUIRED_REGRESSION_GROUPS,
    build_manifest,
    build_pytest_command,
    iter_regression_tests,
    missing_tests,
)


class ArchitectureEvolutionRegressionTest(unittest.TestCase):
    def test_manifest_contains_required_architecture_groups(self) -> None:
        self.assertEqual(tuple(REGRESSION_GROUPS), REQUIRED_REGRESSION_GROUPS)
        manifest = build_manifest()
        groups = manifest["groups"]

        for group_name in REQUIRED_REGRESSION_GROUPS:
            self.assertIn(group_name, groups)
            self.assertTrue(groups[group_name]["tests"])

        self.assertEqual(groups["llm_gateway"]["label"], "LLMGateway")
        self.assertEqual(groups["graph_rag"]["label"], "GraphRAG")
        self.assertEqual(groups["outbox"]["label"], "Outbox")
        self.assertEqual(groups["ontology"]["label"], "Ontology")
        self.assertEqual(groups["learning_insight"]["label"], "LearningInsight")
        self.assertEqual(groups["observe_philology"]["label"], "Observe 文献学")
        self.assertEqual(
            groups["publish_citation_grounding"]["label"],
            "Publish citation grounding",
        )
        self.assertEqual(groups["architecture_guard"]["label"], "Architecture guard")

    def test_regression_tests_exist_and_e2e_is_opt_in(self) -> None:
        tests = iter_regression_tests()

        self.assertIn("tests/unit/test_llm_gateway_contract.py", tests)
        self.assertIn("tests/unit/test_graph_rag.py", tests)
        self.assertIn("tests/unit/test_outbox.py", tests)
        self.assertIn("tests/unit/test_ontology_registry.py", tests)
        self.assertIn("tests/unit/test_learning_insight_repo.py", tests)
        self.assertIn("tests/unit/test_philology_service.py", tests)
        self.assertIn("tests/unit/test_citation_grounding_evaluator.py", tests)
        self.assertIn("tests/unit/test_architecture_regression_guard.py", tests)
        self.assertEqual(missing_tests(tests), [])

        self.assertNotIn(E2E_TESTS[0], tests)
        self.assertIn(E2E_TESTS[0], iter_regression_tests(include_e2e=True))

    def test_pytest_command_supports_required_switches(self) -> None:
        command = build_pytest_command(
            include_e2e=True,
            strict_known_failures=True,
            extra_pytest_args=("-k", "graph"),
        )

        self.assertEqual(command[1:3], ["-m", "pytest"])
        self.assertIn(E2E_TESTS[0], command)
        self.assertIn("--strict-known-failures", command)
        self.assertEqual(command[-2:], ["-k", "graph"])

    def test_vscode_task_has_clear_label(self) -> None:
        tasks_path = Path(__file__).resolve().parents[2] / ".vscode" / "tasks.json"
        payload = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks = {task["label"]: task for task in payload["tasks"]}

        self.assertIn("architecture evolution regression", tasks)
        task = tasks["architecture evolution regression"]
        self.assertEqual(task["group"], "test")
        self.assertIn("tools/run_architecture_evolution_regression.py", task["args"])


if __name__ == "__main__":
    unittest.main()
