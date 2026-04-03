"""
Google Scholar 统合小助手集成测试

验证：
1. 模块导入
2. 数据类实例化
3. 工作流函数签名
4. CLI 参数注册
5. 工具函数执行
"""

import os
import subprocess
import sys
import unittest


class TestGoogleScholarHelperIntegration(unittest.TestCase):
    def test_1_module_imports(self):
        from src.research.google_scholar_helper import (
            GoogleScholarHelperResult,
            run_google_scholar_related_works,
        )
        self.assertIsNotNone(GoogleScholarHelperResult)
        self.assertIsNotNone(run_google_scholar_related_works)

        from src.research import (
            GoogleScholarHelperResult as ExportedGoogleScholarHelperResult,
        )
        from src.research import (
            run_google_scholar_related_works as exported_run_google_scholar_related_works,
        )
        self.assertIsNotNone(ExportedGoogleScholarHelperResult)
        self.assertIsNotNone(exported_run_google_scholar_related_works)

        print("✅ 测试 1 通过: 模块导入成功")

    def test_2_dataclass_instantiation(self):
        from src.research.google_scholar_helper import GoogleScholarHelperResult

        result = GoogleScholarHelperResult(
            status="success",
            query_url="https://scholar.google.com/scholar?q=transformer",
            total_papers=3,
            papers=[{"title": "paper a"}],
            related_works_md="## 相关工作\n\n...",
            output_markdown="/tmp/a.md",
            output_json="/tmp/a.json",
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.total_papers, 3)
        self.assertIn("query_url", result.to_dict())
        print("✅ 测试 2 通过: 数据类实例化成功")

    def test_3_workflow_function_signature(self):
        import inspect

        from run_cycle_demo import run_google_scholar_helper_workflow

        sig = inspect.signature(run_google_scholar_helper_workflow)
        params = list(sig.parameters.keys())
        expected_params = [
            "scholar_url",
            "output_dir",
            "topic_hint",
            "target_lang",
            "max_papers",
            "use_llm",
            "additional_prompt",
            "persist_storage",
            "pg_url",
            "neo4j_uri",
            "neo4j_user",
            "neo4j_password",
        ]
        for p in expected_params:
            self.assertIn(p, params)
        print(f"✅ 测试 3 通过: 工作流函数签名验证成功 ({len(params)} 个参数)")

    def test_4_cli_parameters_registered(self):
        result = subprocess.run(
            [sys.executable, "run_cycle_demo.py", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
        )

        help_text = result.stdout + result.stderr
        expected = [
            "--enable-scholar-helper",
            "--scholar-url",
            "--scholar-output-dir",
            "--scholar-topic-hint",
            "--scholar-target-lang",
            "--scholar-max-papers",
            "--scholar-no-llm",
            "--scholar-additional-prompt",
            "--scholar-persist-storage",
        ]
        found = 0
        for item in expected:
            if item in help_text:
                found += 1
            else:
                self.fail(f"CLI 参数未注册: {item}")
        print(f"✅ 测试 4 通过: 所有 {found} 个 CLI 参数已注册")

    def test_5_utility_functions(self):
        from src.research.google_scholar_helper import (
            _extract_year,
            _format_author_year_citation,
        )

        self.assertEqual(_extract_year("A. Author - NeurIPS 2024"), "2024")
        self.assertEqual(_extract_year("No year"), "")
        self.assertEqual(
            _format_author_year_citation("A. Vaswani, N. Shazeer - NeurIPS, 2017", "2017", 1),
            "(Vaswani, 2017)",
        )
        print("✅ 测试 5 通过: 工具函数执行成功")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGoogleScholarHelperIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"✅ 所有 {result.testsRun} 个集成测试通过")
        sys.exit(0)
    else:
        print(f"❌ {len(result.failures)} 个测试失败，{len(result.errors)} 个测试错误")
        sys.exit(1)
