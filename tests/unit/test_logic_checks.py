import ast
import unittest
from pathlib import Path

from tools.logic_checks import (
    check_duplicate_all_entries,
    check_duplicate_top_level_defs,
    check_hardcoded_sys_path,
)


class TestLogicChecks(unittest.TestCase):
    def test_hardcoded_sys_path_is_error(self):
        src = "import sys\nsys.path.insert(0, '/tmp/project')\n"
        issues = check_hardcoded_sys_path(Path("sample.py"), ast.parse(src))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "ERROR")

    def test_duplicate_top_level_defs_is_error(self):
        src = "class A:\n    pass\n\nclass A:\n    pass\n"
        tree = ast.parse(src)
        issues = check_duplicate_top_level_defs(Path("dup.py"), tree)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "ERROR")

    def test_duplicate_all_entries_is_warn(self):
        src = "__all__ = ['A', 'B', 'A']\n"
        tree = ast.parse(src)
        issues = check_duplicate_all_entries(Path("all.py"), tree)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "WARN")


if __name__ == "__main__":
    unittest.main()
