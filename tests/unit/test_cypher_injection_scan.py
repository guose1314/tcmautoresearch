"""Unit tests for tools/cypher_injection_scan.py."""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.cypher_injection_scan import Violation, scan, scan_file


class TestScanFile(unittest.TestCase):
    """AST-level scan for unsafe Cypher f-string interpolation."""

    def _write(self, tmp_path: Path, code: str) -> Path:
        p = tmp_path / "target.py"
        p.write_text(textwrap.dedent(code), encoding="utf-8")
        return p

    def _tmp(self) -> Path:
        import tempfile
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    # ------------------------------------------------------------------
    # Safe cases — should produce zero violations
    # ------------------------------------------------------------------

    def test_safe_cypher_label_no_violation(self):
        """f-string with _safe_cypher_label() wrapping all interpolations."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            def _safe_cypher_label(x): return x
            label = "Herb"
            query = f"MATCH (n:{_safe_cypher_label(label)} {{id: $id}}) RETURN n"
        ''')
        self.assertEqual(scan_file(p), [])

    def test_plain_string_no_violation(self):
        """Regular string (non-f-string) with MATCH — no violation."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            query = "MATCH (n) DETACH DELETE n"
        ''')
        self.assertEqual(scan_file(p), [])

    def test_fstring_without_cypher_keywords(self):
        """f-string without MATCH/CREATE/MERGE — no violation."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            msg = f"Hello {name}"
        ''')
        self.assertEqual(scan_file(p), [])

    def test_fstring_cypher_keyword_no_interpolation(self):
        """f-string with MATCH but no interpolation — no violation."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            query = f"MATCH (n) RETURN n"
        ''')
        self.assertEqual(scan_file(p), [])

    def test_multiline_safe(self):
        """Multiline f-string with _safe_cypher_label — safe."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            def _safe_cypher_label(x): return x
            label = "Herb"
            query = f"""
            MERGE (n:{_safe_cypher_label(label)} {{id: $id}})
            SET n += $properties
            RETURN n
            """
        ''')
        self.assertEqual(scan_file(p), [])

    # ------------------------------------------------------------------
    # Unsafe cases — should produce violations
    # ------------------------------------------------------------------

    def test_unsafe_fstring_match(self):
        """f-string interpolating label directly — VIOLATION."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            label = "Herb"
            query = f"MATCH (n:{label} {{id: $id}}) RETURN n"
        ''')
        violations = scan_file(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("injection", violations[0].reason.lower())

    def test_unsafe_fstring_create(self):
        """f-string with CREATE and bare interpolation — VIOLATION."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            label = "Herb"
            query = f"CREATE (n:{label}) RETURN n"
        ''')
        violations = scan_file(p)
        self.assertEqual(len(violations), 1)

    def test_unsafe_fstring_merge(self):
        """f-string with MERGE and bare interpolation — VIOLATION."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            label = "Herb"
            query = f"MERGE (n:{label} {{id: $id}}) SET n.name = $name"
        ''')
        violations = scan_file(p)
        self.assertEqual(len(violations), 1)

    def test_unsafe_multiline(self):
        """Multiline f-string with unsafe interpolation — VIOLATION."""
        tmp = self._tmp()
        p = self._write(tmp, '''\
            label = "Herb"
            query = f"""
            MATCH (n:{label})
            RETURN n
            """
        ''')
        violations = scan_file(p)
        self.assertEqual(len(violations), 1)


class TestScan(unittest.TestCase):
    """Integration-level tests for the ``scan()`` entry point."""

    def _tmp(self) -> Path:
        import tempfile
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def test_missing_target(self):
        """Non-existent target file yields a violation."""
        tmp = self._tmp()
        violations = scan(tmp, ["nonexistent.py"])
        self.assertEqual(len(violations), 1)
        self.assertIn("not found", violations[0].reason)

    def test_real_neo4j_driver_passes(self):
        """Current neo4j_driver.py should produce zero violations."""
        root = Path(__file__).resolve().parents[2]
        target = root / "src" / "storage" / "neo4j_driver.py"
        if not target.exists():
            self.skipTest("neo4j_driver.py not present")
        violations = scan(root)
        self.assertEqual(violations, [], f"Unexpected violations: {violations}")


if __name__ == "__main__":
    unittest.main()
