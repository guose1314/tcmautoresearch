"""
Code quality checks.

This tool provides lightweight static checks focused on maintainability:
1) Syntax validity
2) Function size and complexity
3) Bare except usage

Usage:
    python tools/code_quality_checks.py
    python tools/code_quality_checks.py --root .
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

BRANCH_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    ast.Match,
    ast.comprehension,
)


@dataclass(frozen=True)
class QualityThresholds:
    max_function_lines: int = 120
    max_parameters: int = 7
    max_branching_nodes: int = 12


DEFAULT_THRESHOLDS = QualityThresholds()


@dataclass
class Issue:
    severity: str  # ERROR or WARN
    file_path: Path
    line: int
    message: str


def iter_target_files(root: Path) -> Iterable[Path]:
    folders = [root / "src", root / "tools", root / "tests", root / "integration_tests"]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            if path.is_file():
                yield path

    for pattern in ("test_*.py", "run_*.py"):
        for path in root.glob(pattern):
            if path.is_file():
                yield path


def _node_end_lineno(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int):
        return end
    return getattr(node, "lineno", 1)


def _count_branching_nodes(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, BRANCH_NODE_TYPES))


def _warn(file_path: Path, line: int, message: str) -> Issue:
    return Issue(
        severity="WARN",
        file_path=file_path,
        line=line,
        message=message,
    )


def _check_function_metrics(
    file_path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    thresholds: QualityThresholds,
) -> List[Issue]:
    issues: List[Issue] = []
    line_start = getattr(node, "lineno", 1)
    line_end = _node_end_lineno(node)
    line_span = max(1, line_end - line_start + 1)
    arg_count = len(getattr(node.args, "args", [])) + len(getattr(node.args, "kwonlyargs", []))
    branch_count = _count_branching_nodes(node)

    if line_span > thresholds.max_function_lines:
        issues.append(
            _warn(
                file_path,
                line_start,
                "Function '{name}' is too long ({span} lines > {limit}).".format(
                    name=node.name,
                    span=line_span,
                    limit=thresholds.max_function_lines,
                ),
            )
        )

    if arg_count > thresholds.max_parameters:
        issues.append(
            _warn(
                file_path,
                line_start,
                "Function '{name}' has too many parameters ({count} > {limit}).".format(
                    name=node.name,
                    count=arg_count,
                    limit=thresholds.max_parameters,
                ),
            )
        )

    if branch_count > thresholds.max_branching_nodes:
        issues.append(
            _warn(
                file_path,
                line_start,
                "Function '{name}' complexity is high ({count} branching nodes > {limit}).".format(
                    name=node.name,
                    count=branch_count,
                    limit=thresholds.max_branching_nodes,
                ),
            )
        )
    return issues


def check_file(file_path: Path, thresholds: QualityThresholds = DEFAULT_THRESHOLDS) -> List[Issue]:
    issues: List[Issue] = []
    text = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            Issue(
                severity="ERROR",
                file_path=file_path,
                line=exc.lineno or 1,
                message="Syntax error: {msg}".format(msg=exc.msg),
            )
        ]

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(_warn(file_path, getattr(node, "lineno", 1), "Bare except detected; catch specific exceptions where possible."))

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            issues.extend(_check_function_metrics(file_path, node, thresholds))

    return issues


def run_checks(root: Path, thresholds: QualityThresholds = DEFAULT_THRESHOLDS) -> List[Issue]:
    issues: List[Issue] = []
    for path in iter_target_files(root):
        issues.extend(check_file(path, thresholds=thresholds))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Run code quality checks")
    parser.add_argument("--root", default=".", help="Project root path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    issues = run_checks(root)

    error_count = sum(1 for issue in issues if issue.severity == "ERROR")
    warning_count = len(issues) - error_count

    print("[code-quality] errors={errors} warnings={warnings}".format(errors=error_count, warnings=warning_count))
    for issue in issues:
        rel_path = issue.file_path.relative_to(root) if issue.file_path.is_absolute() else issue.file_path
        print(
            "- {severity} {path}:{line} {message}".format(
                severity=issue.severity,
                path=str(rel_path).replace("\\", "/"),
                line=issue.line,
                message=issue.message,
            )
        )

    # Warnings are non-blocking; syntax errors block.
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())