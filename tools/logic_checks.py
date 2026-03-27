"""
Project logic checks.

This script provides lightweight static guards for common regression risks:
1) Hardcoded absolute sys.path inserts in scripts.
2) Duplicate top-level class/function definitions within one module.
3) Duplicate string entries in __all__ exports.

Usage:
    python tools/logic_checks.py
    python tools/logic_checks.py --root .
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class Issue:
    severity: str  # ERROR or WARN
    file_path: Path
    line: int
    message: str


def iter_target_files(root: Path) -> Iterable[Path]:
    """Return Python files we want to guard by default."""
    folders = [root / "src", root / "tests", root / "integration_tests"]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            if path.is_file():
                yield path

    # Top-level quick scripts such as test_*.py and run_*.py
    for pattern in ("test_*.py", "run_*.py"):
        for path in root.glob(pattern):
            if path.is_file():
                yield path


def _is_absolute_literal_path(path_value: str) -> bool:
    if path_value.startswith("/"):
        return True
    return re.match(r"^[A-Za-z]:[\\/]", path_value) is not None


def _is_sys_path_insert_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "insert":
        return False
    path_attr = func.value
    if not isinstance(path_attr, ast.Attribute) or path_attr.attr != "path":
        return False
    return isinstance(path_attr.value, ast.Name) and path_attr.value.id == "sys"


def check_hardcoded_sys_path(file_path: Path, tree: ast.AST) -> List[Issue]:
    issues: List[Issue] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_sys_path_insert_call(node):
            continue

        if len(node.args) < 2:
            continue
        path_node = node.args[1]
        if isinstance(path_node, ast.Constant) and isinstance(path_node.value, str):
            if _is_absolute_literal_path(path_node.value):
                issues.append(
                    Issue(
                        severity="ERROR",
                        file_path=file_path,
                        line=getattr(node, "lineno", 1),
                        message="Hardcoded absolute sys.path insert detected; use Path(__file__) based root.",
                    )
                )
        elif isinstance(path_node, ast.JoinedStr):
            # Conservative guard for obvious f-strings that begin with absolute root.
            text_parts = [v.value for v in path_node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            joined = "".join(text_parts)
            if joined and _is_absolute_literal_path(joined):
                issues.append(
                    Issue(
                        severity="ERROR",
                        file_path=file_path,
                        line=getattr(node, "lineno", 1),
                        message="Hardcoded absolute sys.path insert detected; use Path(__file__) based root.",
                    )
                )

    return issues


def check_file(file_path: Path) -> List[Issue]:
    text = file_path.read_text(encoding="utf-8")
    issues = []

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        issues.append(
            Issue(
                severity="ERROR",
                file_path=file_path,
                line=exc.lineno or 1,
                message="Syntax error: {msg}".format(msg=exc.msg),
            )
        )
        return issues

    issues.extend(check_hardcoded_sys_path(file_path, tree))
    issues.extend(check_duplicate_top_level_defs(file_path, tree))
    issues.extend(check_duplicate_all_entries(file_path, tree))
    return issues


def _node_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    return None


def check_duplicate_top_level_defs(file_path: Path, tree: ast.AST) -> List[Issue]:
    issues: List[Issue] = []
    seen = {}
    for node in getattr(tree, "body", []):
        name = _node_name(node)
        if not name:
            continue

        if name in seen:
            first_line = seen[name]
            issues.append(
                Issue(
                    severity="ERROR",
                    file_path=file_path,
                    line=getattr(node, "lineno", 1),
                    message=(
                        "Duplicate top-level definition '{name}' found "
                        "(first defined at line {first_line})."
                    ).format(name=name, first_line=first_line),
                )
            )
        else:
            seen[name] = getattr(node, "lineno", 1)
    return issues


def _extract_all_strings(assign_node: ast.Assign) -> List[str]:
    values: List[str] = []
    value = assign_node.value
    if isinstance(value, (ast.List, ast.Tuple)):
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
    return values


def check_duplicate_all_entries(file_path: Path, tree: ast.AST) -> List[Issue]:
    issues: List[Issue] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue

        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "__all__" not in targets:
            continue

        items = _extract_all_strings(node)
        seen = set()
        duplicates = []
        for item in items:
            if item in seen:
                duplicates.append(item)
            seen.add(item)

        if duplicates:
            issues.append(
                Issue(
                    severity="WARN",
                    file_path=file_path,
                    line=getattr(node, "lineno", 1),
                    message="Duplicate __all__ exports: {items}".format(items=sorted(set(duplicates))),
                )
            )
    return issues



def run_checks(root: Path) -> List[Issue]:
    issues: List[Issue] = []
    visited = set()
    for file_path in iter_target_files(root):
        resolved = file_path.resolve()
        if resolved in visited:
            continue
        visited.add(resolved)
        issues.extend(check_file(file_path))
    return sorted(issues, key=lambda x: (x.severity != "ERROR", str(x.file_path), x.line))


def print_report(issues: List[Issue], root: Path) -> None:
    if not issues:
        print("[logic-check] PASS: no issues found")
        return

    print("[logic-check] Found {count} issues".format(count=len(issues)))
    for issue in issues:
        try:
            display = issue.file_path.resolve().relative_to(root.resolve())
        except Exception:
            display = issue.file_path
        print("[{sev}] {path}:{line} - {msg}".format(
            sev=issue.severity,
            path=display,
            line=issue.line,
            msg=issue.message,
        ))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run project logic checks")
    parser.add_argument("--root", default=".", help="Project root path")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    issues = run_checks(root)
    print_report(issues, root)

    has_error = any(issue.severity == "ERROR" for issue in issues)
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
