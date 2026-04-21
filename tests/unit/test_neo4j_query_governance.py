"""tests/unit/test_neo4j_query_governance.py — Neo4j 查询规范治理测试。"""

import os
import unittest
from pathlib import Path

_WORKSPACE = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestCanonicalTemplatesStructure(unittest.TestCase):
    """neo4j_query_templates.py 结构完整性。"""

    def test_module_importable(self):
        from tools.neo4j_query_templates import (
            ANTI_PATTERNS,
            CANONICAL_READ_TEMPLATES,
            CANONICAL_WRITE_TEMPLATES,
            TROUBLESHOOTING_TEMPLATES,
        )
        self.assertIsInstance(CANONICAL_READ_TEMPLATES, dict)
        self.assertIsInstance(CANONICAL_WRITE_TEMPLATES, dict)
        self.assertIsInstance(ANTI_PATTERNS, list)
        self.assertIsInstance(TROUBLESHOOTING_TEMPLATES, dict)

    def test_read_templates_non_empty(self):
        from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES
        self.assertGreaterEqual(len(CANONICAL_READ_TEMPLATES), 2)

    def test_write_templates_non_empty(self):
        from tools.neo4j_query_templates import CANONICAL_WRITE_TEMPLATES
        self.assertGreaterEqual(len(CANONICAL_WRITE_TEMPLATES), 2)

    def test_philology_asset_graph_template_present(self):
        from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES

        self.assertIn("philology_asset_graph", CANONICAL_READ_TEMPLATES)
        template = CANONICAL_READ_TEMPLATES["philology_asset_graph"]
        self.assertIn("ATTESTS_TO", template["cypher"])
        self.assertIn("HAS_FRAGMENT_CANDIDATE", template["cypher"])
        self.assertIn("CAPTURED", template["cypher"])
        self.assertIn("legacy_unreviewed", template["cypher"])
        self.assertIn("review_status", template["cypher"])
        self.assertIn("work_title", template["cypher"])
        self.assertIn("version_lineage_key", template["cypher"])
        self.assertIn("witness_key", template["cypher"])

    def test_every_template_has_required_fields(self):
        from tools.neo4j_query_templates import (
            CANONICAL_READ_TEMPLATES,
            CANONICAL_WRITE_TEMPLATES,
        )
        required = {"description", "cypher", "rules"}
        for name, tpl in {**CANONICAL_READ_TEMPLATES, **CANONICAL_WRITE_TEMPLATES}.items():
            missing = required - tpl.keys()
            self.assertFalse(missing, f"模板 {name} 缺少字段: {missing}")

    def test_troubleshooting_templates_have_fix(self):
        from tools.neo4j_query_templates import TROUBLESHOOTING_TEMPLATES
        for name, entry in TROUBLESHOOTING_TEMPLATES.items():
            for key in ("symptom", "cause", "fix", "correct_example"):
                self.assertIn(key, entry, f"排障模板 {name} 缺少字段: {key}")

    def test_anti_patterns_have_regex(self):
        from tools.neo4j_query_templates import ANTI_PATTERNS
        for ap in ANTI_PATTERNS:
            self.assertTrue(hasattr(ap.regex, "search"),
                            f"反模式 {ap.name} 的 regex 不可调用")


class TestValidateCypherSnippet(unittest.TestCase):
    """validate_cypher_snippet 反模式检测。"""

    def test_clean_split_match_passes(self):
        from tools.neo4j_query_templates import validate_cypher_snippet
        good = (
            "MATCH (a:Label {id: $id})\n"
            "MATCH (b:Label {id: $other})\n"
            "MERGE (a)-[r:REL]->(b)"
        )
        self.assertEqual(validate_cypher_snippet(good), [])

    def test_comma_match_detected(self):
        from tools.neo4j_query_templates import validate_cypher_snippet
        bad = "MATCH (a:Label {id: $id}), (b:Label {id: $other}) MERGE (a)-[r:REL]->(b)"
        violations = validate_cypher_snippet(bad)
        self.assertGreater(len(violations), 0)
        self.assertEqual(violations[0].pattern_name, "comma_separated_match")

    def test_empty_text_passes(self):
        from tools.neo4j_query_templates import validate_cypher_snippet
        self.assertEqual(validate_cypher_snippet(""), [])


class TestCypherDocLint(unittest.TestCase):
    """cypher_doc_lint.py 文档扫描能力。"""

    def test_module_importable(self):
        from tools.cypher_doc_lint import lint_file, lint_repo
        self.assertTrue(callable(lint_file))
        self.assertTrue(callable(lint_repo))

    def test_lint_clean_markdown(self):
        """干净的 Markdown 应无违规。"""
        from tools.cypher_doc_lint import lint_text_blocks
        blocks = [(1, (
            "MATCH (a:Label {id: $id})\n"
            "MATCH (b:Label {id: $other})\n"
            "MERGE (a)-[r:REL]->(b)"
        ))]
        violations = lint_text_blocks("test.md", blocks)
        self.assertEqual(violations, [])

    def test_lint_detects_comma_match(self):
        from tools.cypher_doc_lint import lint_text_blocks
        blocks = [(1, "MATCH (a:A {id: 1}), (b:B {id: 2}) MERGE (a)-[:R]->(b)")]
        violations = lint_text_blocks("test.md", blocks)
        self.assertGreater(len(violations), 0)
        self.assertIn("comma_separated_match", violations[0].rule)

    def test_lint_detects_old_call_syntax(self):
        from tools.cypher_doc_lint import lint_text_blocks
        blocks = [(1, "CALL { WITH start MATCH (start)--(n) RETURN n }")]
        violations = lint_text_blocks("test.md", blocks)
        self.assertGreater(len(violations), 0)
        self.assertIn("deprecated_call_syntax", violations[0].rule)


class TestRepoDocCompliance(unittest.TestCase):
    """仓库中现有文档和代码的 Cypher 示例必须全部合规。"""

    def test_all_md_files_pass_lint(self):
        """所有 .md 文件中的 Cypher 代码块不含已知反模式。"""
        from tools.cypher_doc_lint import lint_file
        md_files = list(_WORKSPACE.glob("*.md")) + list(_WORKSPACE.glob("docs/**/*.md"))
        all_violations = []
        for f in md_files:
            all_violations.extend(lint_file(f))
        self.assertEqual(
            all_violations, [],
            f"文档 Cypher 反模式: {[(v.file, v.line, v.rule) for v in all_violations]}"
        )

    def test_neo4j_driver_passes_lint(self):
        """neo4j_driver.py 中的 Cypher 字符串不含反模式。"""
        from tools.cypher_doc_lint import lint_file
        driver = _WORKSPACE / "src" / "storage" / "neo4j_driver.py"
        if driver.exists():
            violations = lint_file(driver)
            self.assertEqual(
                violations, [],
                f"neo4j_driver.py 违规: {[(v.line, v.rule) for v in violations]}"
            )

    def test_canonical_templates_self_validate(self):
        """规范模板自身必须通过反模式检测。"""
        from tools.neo4j_query_templates import (
            CANONICAL_READ_TEMPLATES,
            CANONICAL_WRITE_TEMPLATES,
            validate_cypher_snippet,
        )
        for name, tpl in {**CANONICAL_READ_TEMPLATES, **CANONICAL_WRITE_TEMPLATES}.items():
            violations = validate_cypher_snippet(tpl["cypher"])
            self.assertEqual(
                violations, [],
                f"规范模板 {name} 自身未通过检测: {[v.pattern_name for v in violations]}"
            )


if __name__ == "__main__":
    unittest.main()
