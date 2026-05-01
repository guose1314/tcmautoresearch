"""Run the staged minimal regression set for architecture evolution work.

Usage::

    python tools/run_architecture_evolution_regression.py
    python tools/run_architecture_evolution_regression.py --print-only
    python tools/run_architecture_evolution_regression.py --include-e2e
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[1]


class RegressionGroup(TypedDict):
    label: str
    tests: tuple[str, ...]


REQUIRED_REGRESSION_GROUPS: tuple[str, ...] = (
    "llm_gateway",
    "graph_rag",
    "outbox",
    "ontology",
    "learning_insight",
    "observe_philology",
    "publish_citation_grounding",
    "architecture_guard",
)

REGRESSION_GROUPS: "OrderedDict[str, RegressionGroup]" = OrderedDict(
    [
        (
            "llm_gateway",
            {
                "label": "LLMGateway",
                "tests": ("tests/unit/test_llm_gateway_contract.py",),
            },
        ),
        (
            "graph_rag",
            {
                "label": "GraphRAG",
                "tests": (
                    "tests/unit/test_graph_rag.py",
                    "tests/integration_tests/test_graph_rag_traceability.py",
                ),
            },
        ),
        (
            "outbox",
            {
                "label": "Outbox",
                "tests": ("tests/unit/test_outbox.py",),
            },
        ),
        (
            "ontology",
            {
                "label": "Ontology",
                "tests": ("tests/unit/test_ontology_registry.py",),
            },
        ),
        (
            "learning_insight",
            {
                "label": "LearningInsight",
                "tests": ("tests/unit/test_learning_insight_repo.py",),
            },
        ),
        (
            "observe_philology",
            {
                "label": "Observe 文献学",
                "tests": (
                    "tests/unit/test_philology_service.py",
                    "tests/unit/test_philology_graph_projection.py",
                    "tests/test_evidence_chain_artifact.py",
                ),
            },
        ),
        (
            "publish_citation_grounding",
            {
                "label": "Publish citation grounding",
                "tests": (
                    "tests/unit/test_citation_grounding_evaluator.py",
                    "tests/evaluation/test_research_gold_set.py",
                ),
            },
        ),
        (
            "architecture_guard",
            {
                "label": "Architecture guard",
                "tests": ("tests/unit/test_architecture_regression_guard.py",),
            },
        ),
    ]
)

E2E_TESTS: tuple[str, ...] = ("tests/e2e/test_seven_phase_pipeline.py",)
DEFAULT_PYTEST_ARGS: tuple[str, ...] = ("-q", "--tb=short")


def iter_regression_tests(*, include_e2e: bool = False) -> List[str]:
    tests: List[str] = []
    seen: set[str] = set()
    groups: Iterable[RegressionGroup] = REGRESSION_GROUPS.values()
    for group in groups:
        for path in group["tests"]:
            if path not in seen:
                seen.add(path)
                tests.append(path)
    if include_e2e:
        for path in E2E_TESTS:
            if path not in seen:
                seen.add(path)
                tests.append(path)
    return tests


def missing_tests(paths: Sequence[str], *, repo_root: Path = REPO_ROOT) -> List[str]:
    return [path for path in paths if not (repo_root / path).exists()]


def build_pytest_command(
    *,
    include_e2e: bool = False,
    strict_known_failures: bool = False,
    extra_pytest_args: Sequence[str] = (),
) -> List[str]:
    command = [sys.executable, "-m", "pytest"]
    command.extend(iter_regression_tests(include_e2e=include_e2e))
    command.extend(DEFAULT_PYTEST_ARGS)
    if strict_known_failures:
        command.append("--strict-known-failures")
    command.extend(extra_pytest_args)
    return command


def build_manifest(*, include_e2e: bool = False) -> Mapping[str, object]:
    tests = iter_regression_tests(include_e2e=include_e2e)
    return {
        "contract": "architecture-evolution-regression-v1",
        "required_groups": list(REQUIRED_REGRESSION_GROUPS),
        "groups": {
            key: {"label": value["label"], "tests": list(value["tests"])}
            for key, value in REGRESSION_GROUPS.items()
        },
        "include_e2e": include_e2e,
        "e2e_tests": list(E2E_TESTS if include_e2e else ()),
        "test_count": len(tests),
        "tests": tests,
        "pytest_args": list(DEFAULT_PYTEST_ARGS),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-e2e",
        action="store_true",
        help="Also run the seven-phase e2e pipeline regression.",
    )
    parser.add_argument(
        "--strict-known-failures",
        action="store_true",
        help="Pass --strict-known-failures through to pytest.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the manifest and pytest command without executing it.",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="Extra pytest argument; repeat for multiple arguments.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    tests = iter_regression_tests(include_e2e=args.include_e2e)
    missing = missing_tests(tests)
    if missing:
        print(
            json.dumps(
                {"error": "missing_regression_tests", "missing": missing},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    command = build_pytest_command(
        include_e2e=args.include_e2e,
        strict_known_failures=args.strict_known_failures,
        extra_pytest_args=args.pytest_arg,
    )
    payload = dict(build_manifest(include_e2e=args.include_e2e))
    payload["command"] = command
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.print_only:
        return 0
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
