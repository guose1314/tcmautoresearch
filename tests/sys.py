# tests/sys.py
"""
测试套件命令行入口
"""
import sys
import unittest


def main() -> int:
	"""发现并运行 tests/ 目录下全部测试，返回 exit code"""
	loader = unittest.TestLoader()
	suite = loader.discover(start_dir="tests", pattern="test_*.py")
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
	sys.exit(main())
