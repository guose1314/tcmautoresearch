#!/usr/bin/env python3
"""
PDF 论文全文翻译插件 - 集成测试
验证：导入 + 工作流函数 + CLI 集成
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """测试 1: 验证模块导入"""
    print("=" * 60)
    print("测试 1: 模块导入")
    print("=" * 60)
    
    try:
        from src.research.pdf_translation import (
            PdfTranslationResult,
            run_pdf_full_text_translation,
        )
        assert PdfTranslationResult is not None
        assert callable(run_pdf_full_text_translation)
        print("✅ 直接导入成功")
    except Exception as e:
        print(f"❌ 直接导入失败: {e}")
        raise AssertionError("直接导入失败") from e
    
    try:
        from src.research import (
            PdfTranslationResult as exported_result_class,
        )
        from src.research import (
            run_pdf_full_text_translation as exported_run_pdf,
        )
        assert exported_result_class is not None
        assert callable(exported_run_pdf)
        print("✅ 从 research/__init__.py 导出成功")
    except Exception as e:
        print(f"❌ 导出导入失败: {e}")
        raise AssertionError("research/__init__.py 导出失败") from e


def test_result_class():
    """测试 2: 验证结果数据类"""
    print("\n" + "=" * 60)
    print("测试 2: PdfTranslationResult 数据类")
    print("=" * 60)
    
    from src.research.pdf_translation import PdfTranslationResult
    
    result = PdfTranslationResult(
        status="completed",
        pdf_path="/path/to/test.pdf",
        title="Test Paper",
        abstract="Test abstract",
        abstract_translated="测试摘要",
        fragment_total=10,
        fragment_ok=10,
        char_count=5000,
        output_markdown="/tmp/report.md",
        output_html="/tmp/report.html",
        output_json="/tmp/result.json",
        summary="All done",
    )
    
    print(f"✅ 数据类实例化成功")
    print(f"   状态: {result.status}")
    print(f"   标题: {result.title}")
    print(f"   片段: {result.fragment_ok}/{result.fragment_total}")
    print(f"   字数: {result.char_count}")
    
    # 验证字段
    assert result.status == "completed"
    assert result.fragment_total == 10
    print(f"✅ 字段验证通过")


def test_workflow_function():
    """测试 3: 验证工作流函数"""
    print("\n" + "=" * 60)
    print("测试 3: 工作流函数签名")
    print("=" * 60)
    
    import inspect

    from run_cycle_demo import run_pdf_translation_workflow
    
    sig = inspect.signature(run_pdf_translation_workflow)
    params = list(sig.parameters.keys())
    
    print(f"✅ 工作流函数签名:")
    for i, param in enumerate(params, 1):
        print(f"   {i}. {param}")
    
    # 验证参数
    expected_params = [
        'pdf_path', 'target_language', 'output_dir', 'additional_prompt',
        'max_tokens_per_fragment', 'max_workers', 'use_llm', 'persist_storage',
        'pg_url', 'neo4j_uri', 'neo4j_user', 'neo4j_password'
    ]
    
    if params == expected_params:
        print(f"✅ 参数列表完整")
    else:
        print(f"⚠️  参数不完全匹配")

    assert params == expected_params


def test_cli_integration():
    """测试 4: 验证 CLI 集成"""
    print("\n" + "=" * 60)
    print("测试 4: CLI 参数集成")
    print("=" * 60)
    
    import subprocess
    
    # 执行 --help，检查 PDF 相关参数
    result = subprocess.run(
        [sys.executable, "run_cycle_demo.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    help_text = result.stdout + result.stderr
    
    pdf_params = [
        '--enable-pdf-translation',
        '--pdf-input',
        '--pdf-target-lang',
        '--pdf-output-dir',
        '--pdf-additional-prompt',
        '--pdf-max-tokens-per-fragment',
        '--pdf-max-workers',
        '--pdf-no-llm',
        '--pdf-persist-storage',
    ]
    
    found_count = 0
    for param in pdf_params:
        if param in help_text:
            print(f"✅ {param} 已注册")
            found_count += 1
        else:
            print(f"❌ {param} 未找到")
    
    if found_count == len(pdf_params):
        print(f"\n✅ 所有 {len(pdf_params)} 个 CLI 参数已集成")
    else:
        print(f"\n⚠️  仅找到 {found_count}/{len(pdf_params)} 个参数")

    assert found_count == len(pdf_params)


def test_utils():
    """测试 5: 验证内部工具函数"""
    print("\n" + "=" * 60)
    print("测试 5: 内部工具函数")
    print("=" * 60)
    
    from src.research.pdf_translation import (
        _build_pdf_translate_prompt,
        _split_pdf_content,
    )
    
    # 测试内容拆分
    test_text = "Para 1.\n\nPara 2.\n\nPara 3 " * 100
    fragments = _split_pdf_content(test_text, max_tokens=100)
    print(f"✅ 内容拆分: {len(test_text)} 字符 → {len(fragments)} 片段")
    
    # 测试 prompt 构造
    user, system = _build_pdf_translate_prompt("test fragment", "Chinese", "extra note")
    print(f"✅ Prompt 构造:")
    print(f"   User 长度: {len(user)}")
    print(f"   System 长度: {len(system)}")
    
    if "Chinese" in user and "test fragment" in user:
        print(f"✅ Prompt 内容正确")

    assert "Chinese" in user and "test fragment" in user


def main_test():
    """主测试函数"""
    print("\nPDF 论文全文翻译插件 — 集成测试\n")
    
    tests = [
        ("模块导入", test_imports),
        ("结果数据类", test_result_class),
        ("工作流函数", test_workflow_function),
        ("CLI 集成", test_cli_integration),
        ("工具函数", test_utils),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            test_func()
            results[name] = True
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    return all(results.values())


if __name__ == "__main__":
    success = main_test()
    sys.exit(0 if success else 1)
