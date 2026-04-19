"""Neo4j Cypher 文档与代码示例反模式扫描器.

扫描 .md 文件中的 ```cypher 代码块和 .py 文件中的 Cypher 字符串，
检测已知反模式（comma-separated MATCH 等）。

Usage:
    python tools/cypher_doc_lint.py [--root .]
    python tools/cypher_doc_lint.py --files docs/architecture.md STORAGE_QUERIES.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

# ── 反模式正则 ──────────────────────────────────────────────────────────
# 1. MATCH (a ...), (b ...) — 逗号分隔的断开 MATCH
_RE_COMMA_MATCH = re.compile(
    r"MATCH\s*\([^)]+\)\s*,\s*\(",
    re.IGNORECASE,
)

# 2. 旧版 CALL { WITH ... } 而非 CALL (var) { ... }
_RE_OLD_CALL = re.compile(
    r"CALL\s*\{\s*WITH\b",
    re.IGNORECASE,
)


@dataclass
class DocLintViolation:
    file: str
    line: int
    rule: str
    snippet: str


# ── Markdown cypher 代码块提取 ───────────────────────────────────────────

_RE_CYPHER_BLOCK = re.compile(
    r"```(?:cypher|cql)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_cypher_blocks(text: str) -> List[tuple[int, str]]:
    """返回 (起始行号, 代码块内容) 列表。"""
    blocks: List[tuple[int, str]] = []
    for m in _RE_CYPHER_BLOCK.finditer(text):
        start_line = text[:m.start()].count("\n") + 2  # +2: ``` 行本身 + 1-based
        blocks.append((start_line, m.group(1)))
    return blocks


# ── Python Cypher 字符串提取 ─────────────────────────────────────────────

_CYPHER_KW = re.compile(r"\b(MATCH|MERGE|CREATE|UNWIND)\b", re.IGNORECASE)


def _extract_python_cypher_strings(text: str) -> List[tuple[int, str]]:
    """粗略提取 Python 文件中包含 Cypher 关键字的字符串字面量。"""
    results: List[tuple[int, str]] = []
    lines = text.splitlines()
    in_triple = False
    triple_start = 0
    triple_buf: List[str] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if in_triple:
            triple_buf.append(line)
            if '"""' in stripped or "'''" in stripped:
                in_triple = False
                block = "\n".join(triple_buf)
                if _CYPHER_KW.search(block):
                    results.append((triple_start, block))
                triple_buf = []
            continue

        if ('"""' in stripped or "'''" in stripped):
            # Check if triple quote opens and doesn't close on same line
            delim = '"""' if '"""' in stripped else "'''"
            count = stripped.count(delim)
            if count == 1:
                in_triple = True
                triple_start = i
                triple_buf = [line]
                continue

        # Single-line string with Cypher keyword
        if _CYPHER_KW.search(line) and ('"' in line or "'" in line):
            results.append((i, line))

    return results


# ── 检测入口 ─────────────────────────────────────────────────────────────

_RULES = [
    ("comma_separated_match", _RE_COMMA_MATCH,
     "MATCH (a), (b) — 逗号分隔的断开 MATCH，会触发 cartesian product 通知"),
    ("deprecated_call_syntax", _RE_OLD_CALL,
     "CALL { WITH ... } — 旧版子查询语法，应使用 CALL (var) { ... }"),
]


def lint_text_blocks(filepath: str, blocks: List[tuple[int, str]]) -> List[DocLintViolation]:
    """对提取的代码块列表执行反模式检测。"""
    violations: List[DocLintViolation] = []
    for block_start, block_text in blocks:
        for rule_name, regex, description in _RULES:
            for m in regex.finditer(block_text):
                offset = block_text[:m.start()].count("\n")
                snippet = block_text[m.start():m.end()].strip()[:100]
                violations.append(DocLintViolation(
                    file=filepath,
                    line=block_start + offset,
                    rule=f"{rule_name}: {description}",
                    snippet=snippet,
                ))
    return violations


def lint_file(path: Path) -> List[DocLintViolation]:
    """扫描单个文件，返回违规列表。"""
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".md":
        blocks = _extract_cypher_blocks(content)
    elif suffix == ".py":
        blocks = _extract_python_cypher_strings(content)
    else:
        return []

    return lint_text_blocks(str(path), blocks)


def lint_repo(root: Path, files: List[str] | None = None) -> List[DocLintViolation]:
    """扫描仓库中所有文档和 Python 文件。"""
    all_violations: List[DocLintViolation] = []

    if files:
        targets = [root / f for f in files]
    else:
        targets = list(root.glob("**/*.md")) + list(root.glob("**/*.py"))
        # 排除 venv / node_modules / .git
        targets = [
            p for p in targets
            if not any(part.startswith(".") or part in ("venv", "venv310", "node_modules", "__pycache__")
                       for part in p.parts)
        ]

    for p in sorted(targets):
        if p.is_file():
            all_violations.extend(lint_file(p))

    return all_violations


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Neo4j Cypher 文档反模式扫描")
    parser.add_argument("--root", default=".", help="项目根目录")
    parser.add_argument("--files", nargs="*", default=None, help="指定扫描文件（相对于 root）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations = lint_repo(root, args.files)

    if not violations:
        print("[cypher-doc-lint] PASS — 无反模式检出")
        return 0

    print(f"[cypher-doc-lint] FAIL — 发现 {len(violations)} 处违规:")
    for v in violations:
        print(f"  {v.file}:{v.line}  [{v.rule}]")
        if v.snippet:
            print(f"    > {v.snippet}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
