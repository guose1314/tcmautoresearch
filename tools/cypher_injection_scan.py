"""
Cypher injection scan for neo4j_driver.py.

Detects f-string formatted Cypher queries containing MATCH / CREATE / MERGE
where interpolation expressions are NOT wrapped in ``_safe_cypher_label()``.

Usage (standalone):
    python tools/cypher_injection_scan.py [--target src/storage/neo4j_driver.py]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

_CYPHER_KW = re.compile(r"\b(MATCH|CREATE|MERGE)\b", re.IGNORECASE)

_SAFE_FUNC = "_safe_cypher_label"

_NOSEC_COMMENT = re.compile(r"#\s*nosec\s*:\s*cypher", re.IGNORECASE)

DEFAULT_TARGET = "src/storage/neo4j_driver.py"


@dataclass
class Violation:
    file: str
    line: int
    snippet: str
    reason: str


def _expr_uses_safe_label(node: ast.expr) -> bool:
    """Return True when *node* is a call to ``_safe_cypher_label(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == _SAFE_FUNC:
        return True
    if isinstance(func, ast.Attribute) and func.attr == _SAFE_FUNC:
        return True
    return False


def scan_file(path: Path) -> List[Violation]:
    """Parse *path* via AST and return a list of violations."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Violation(file=str(path), line=exc.lineno or 0, snippet="", reason=f"SyntaxError: {exc}")]

    source_lines = source.splitlines()
    violations: List[Violation] = []

    # Build set of suppressed line numbers (lines with # nosec: cypher)
    suppressed_lines: set[int] = set()
    for idx, line in enumerate(source_lines, start=1):
        if _NOSEC_COMMENT.search(line):
            suppressed_lines.add(idx)

    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue

        # Collect literal text fragments to check for Cypher keywords
        literal_parts: list[str] = []
        unsafe_exprs: list[ast.FormattedValue] = []

        for value in node.values:
            if isinstance(value, ast.Constant):
                literal_parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                if not _expr_uses_safe_label(value.value):
                    unsafe_exprs.append(value)

        combined_text = "".join(literal_parts)
        if not _CYPHER_KW.search(combined_text):
            continue
        if not unsafe_exprs:
            continue

        lineno = getattr(node, "lineno", 0)
        if lineno in suppressed_lines:
            continue
        snippet = source_lines[lineno - 1].strip() if 0 < lineno <= len(source_lines) else ""
        violations.append(
            Violation(
                file=str(path),
                line=lineno,
                snippet=snippet,
                reason=(
                    f"f-string Cypher query contains interpolation without "
                    f"{_SAFE_FUNC}() — potential injection risk"
                ),
            )
        )

    return violations


def scan(root: Path, targets: List[str] | None = None) -> List[Violation]:
    """Scan one or more targets and return aggregated violations."""
    if targets is None:
        targets = [DEFAULT_TARGET]

    all_violations: List[Violation] = []
    for target in targets:
        target_path = root / target
        if not target_path.exists():
            all_violations.append(
                Violation(file=target, line=0, snippet="", reason=f"target file not found: {target}")
            )
            continue
        all_violations.extend(scan_file(target_path))
    return all_violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Cypher injection scan")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--target", nargs="*", default=None, help="Files to scan (relative to root)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations = scan(root, args.target)

    if not violations:
        print("[cypher-scan] PASS — no unsafe Cypher interpolation detected")
        return 0

    print(f"[cypher-scan] FAIL — {len(violations)} violation(s) detected:")
    for v in violations:
        print(f"  {v.file}:{v.line}: {v.reason}")
        if v.snippet:
            print(f"    > {v.snippet}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
