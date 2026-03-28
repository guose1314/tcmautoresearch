"""
Arxiv 快速助手集成测试

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
from pathlib import Path


class TestArxivQuickHelperIntegration(unittest.TestCase):
    """Arxiv 快速助手集成测试套件"""
    
    def test_1_module_imports(self):
        """测试 1: 验证模块导入"""
        # 直接导入
        from src.research.arxiv_quick_helper import (
            ArxivQuickHelperResult,
            run_arxiv_quick_helper,
        )
        self.assertIsNotNone(ArxivQuickHelperResult)
        self.assertIsNotNone(run_arxiv_quick_helper)
        
        # 通过 __init__.py 导入
        from src.research import ArxivQuickHelperResult, run_arxiv_quick_helper
        self.assertIsNotNone(ArxivQuickHelperResult)
        self.assertIsNotNone(run_arxiv_quick_helper)
        
        print("✅ 测试 1 通过: 模块导入成功")
    
    def test_2_dataclass_instantiation(self):
        """测试 2: 验证数据类实例化"""
        from src.research.arxiv_quick_helper import ArxivQuickHelperResult
        
        result = ArxivQuickHelperResult(
            status="success",
            arxiv_id="2301.00234",
            url="https://arxiv.org/abs/2301.00234",
            title="Test Paper Title",
            authors="Author One, Author Two",
            publish_date="2023-01-15",
            abstract_en="This is a test abstract.",
            abstract_zh="这是一个测试摘要。",
            pdf_path="/path/to/paper.pdf",
            pdf_size_mb=5.5,
        )
        
        self.assertEqual(result.status, "success")
        self.assertEqual(result.arxiv_id, "2301.00234")
        self.assertEqual(result.title, "Test Paper Title")
        self.assertIn("abstract_en", result.to_dict())
        self.assertIn("abstract_zh", result.to_dict())
        markdown_output = result.to_markdown()
        self.assertIn("快速助手", markdown_output)
        self.assertIn("中文摘要", markdown_output)
        
        print("✅ 测试 2 通过: 数据类实例化成功")
    
    def test_3_workflow_function_signature(self):
        """测试 3: 验证工作流函数签名"""
        import inspect

        from run_cycle_demo import run_arxiv_quick_helper_workflow
        
        sig = inspect.signature(run_arxiv_quick_helper_workflow)
        params = list(sig.parameters.keys())
        
        expected_params = [
            'arxiv_url',
            'output_dir',
            'target_lang',
            'enable_translation',
            'persist_storage',
            'pg_url',
            'neo4j_uri',
            'neo4j_user',
            'neo4j_password',
        ]
        
        for param in expected_params:
            self.assertIn(param, params, f"缺少参数: {param}")
        
        print(f"✅ 测试 3 通过: 工作流函数签名验证成功 ({len(params)} 个参数)")
    
    def test_4_cli_parameters_registered(self):
        """测试 4: 验证 CLI 参数注册"""
        result = subprocess.run(
            [sys.executable, "run_cycle_demo.py", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)) or "."
        )
        
        help_text = result.stdout + result.stderr
        
        expected_params = [
            '--enable-arxiv-helper',
            '--arxiv-helper-url',
            '--arxiv-helper-dir',
            '--arxiv-helper-lang',
            '--arxiv-helper-no-translation',
            '--arxiv-helper-persist-storage',
        ]
        
        param_count = 0
        for param in expected_params:
            if param in help_text:
                param_count += 1
            else:
                self.fail(f"CLI 参数未注册: {param}")
        
        print(f"✅ 测试 4 通过: 所有 {param_count} 个 CLI 参数已注册")
    
    def test_5_utility_functions(self):
        """测试 5: 验证工具函数"""
        from src.research.arxiv_quick_helper import (
            ArxivQuickHelperResult,
            _normalize_arxiv_id,
        )
        
        # 测试 ID 规范化
        test_cases = [
            ("2301.00234", "2301.00234"),
            ("https://arxiv.org/abs/2301.00234", "2301.00234"),
            ("https://arxiv.org/pdf/2301.00234.pdf", "2301.00234"),
            ("2301.00234v2", "2301.00234"),  # 移除版本号
        ]
        
        for input_val, expected in test_cases:
            result = _normalize_arxiv_id(input_val)
            self.assertEqual(result, expected, f"ID 规范化失败: {input_val} -> {result}")
        
        # 测试结果转字典
        result_obj = ArxivQuickHelperResult(
            arxiv_id="2301.00234",
            title="Test"
        )
        result_dict = result_obj.to_dict()
        self.assertIsInstance(result_dict, dict)
        self.assertIn('arxiv_id', result_dict)
        
        print("✅ 测试 5 通过: 工具函数执行成功")
    
    def test_6_markdown_output_generation(self):
        """测试 6: 验证 Markdown 输出生成"""
        from src.research.arxiv_quick_helper import ArxivQuickHelperResult
        
        result = ArxivQuickHelperResult(
            status="success",
            arxiv_id="2301.00234",
            url="https://arxiv.org/abs/2301.00234",
            title="Test Paper",
            authors="Author One",
            publish_date="2023-01-15",
            abstract_en="English abstract",
            abstract_zh="中文摘要",
            pdf_path="/path/to/paper.pdf",
            pdf_size_mb=5.5,
        )
        
        markdown = result.to_markdown()
        
        self.assertIn("Arxiv 快速助手", markdown)
        self.assertIn("2301.00234", markdown)
        self.assertIn("Test Paper", markdown)
        self.assertIn("中文摘要", markdown)
        
        print("✅ 测试 6 通过: Markdown 输出生成成功")


if __name__ == '__main__':
    # 运行测试
    suite = unittest.TestLoader().loadTestsFromTestCase(TestArxivQuickHelperIntegration)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 测试总结
    print("\n" + "="*60)
    if result.wasSuccessful():
        print(f"✅ 所有 {result.testsRun} 个集成测试通过")
        sys.exit(0)
    else:
        print(f"❌ {len(result.failures)} 个测试失败，{len(result.errors)} 个测试错误")
        sys.exit(1)
