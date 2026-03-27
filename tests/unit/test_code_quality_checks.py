import tempfile
import unittest
from pathlib import Path

from tools.code_quality_checks import check_file, run_checks


class TestCodeQualityChecks(unittest.TestCase):
    def test_check_file_detects_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "bad.py"
            file_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
            issues = check_file(file_path)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].severity, "ERROR")

    def test_check_file_detects_bare_except_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "warn.py"
            file_path.write_text(
                "def sample():\n"
                "    try:\n"
                "        return 1\n"
                "    except:\n"
                "        return 0\n",
                encoding="utf-8",
            )
            issues = check_file(file_path)
            self.assertTrue(any(issue.message.startswith("Bare except") for issue in issues))

    def test_run_checks_scans_project_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir(parents=True)
            (root / "src" / "ok.py").write_text("def ok():\n    return True\n", encoding="utf-8")
            issues = run_checks(root)
            self.assertEqual(len([i for i in issues if i.severity == "ERROR"]), 0)


if __name__ == "__main__":
    unittest.main()