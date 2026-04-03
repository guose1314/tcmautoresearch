# tests/test_tcm_lexicon.py
"""
TCMLexicon / src.data.tcm_lexicon 测试

覆盖场景
--------
1. 初始化 — 导入路径、类型、词汇量
2. 查询   — contains / get_word_type / lookup
3. 加载外部词典 — load_from_file / load_external_lexicon
4. get_vocab_size — 精确计数 + 追加后增量
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestInit(unittest.TestCase):
    """场景 1：初始化"""

    def test_import_get_lexicon(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        self.assertIsNotNone(lex)

    def test_tcmlexicon_alias_is_lexicon_service(self):
        from src.data.tcm_lexicon import TCMLexicon
        from src.infra.lexicon_service import LexiconService
        self.assertIs(TCMLexicon, LexiconService)

    def test_get_lexicon_returns_tcmlexicon_instance(self):
        from src.data.tcm_lexicon import TCMLexicon, get_lexicon
        lex = get_lexicon()
        self.assertIsInstance(lex, TCMLexicon)

    def test_singleton_same_object(self):
        from src.data.tcm_lexicon import get_lexicon
        a = get_lexicon()
        b = get_lexicon()
        self.assertIs(a, b)

    def test_has_required_attributes(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        for attr in ("herbs", "formulas", "syndromes", "theory", "efficacy", "common_words"):
            self.assertTrue(hasattr(lex, attr), f"missing attribute: {attr}")


class TestQuery(unittest.TestCase):
    """场景 2：查询"""

    @classmethod
    def setUpClass(cls):
        from src.data.tcm_lexicon import get_lexicon
        cls.lex = get_lexicon()

    def test_contains_known_herb(self):
        # 人参是任何合理 TCM 词典都应包含的词
        if self.lex.herbs:
            sample = next(iter(self.lex.herbs))
            self.assertTrue(self.lex.contains(sample))

    def test_contains_absent_word(self):
        self.assertFalse(self.lex.contains("__不存在的词__xyz__"))

    def test_get_word_type_herb(self):
        if not self.lex.herbs:
            self.skipTest("herbs set is empty")
        sample = next(iter(self.lex.herbs))
        self.assertEqual(self.lex.get_word_type(sample), "herb")

    def test_get_word_type_formula(self):
        if not self.lex.formulas:
            self.skipTest("formulas set is empty")
        sample = next(iter(self.lex.formulas))
        self.assertEqual(self.lex.get_word_type(sample), "formula")

    def test_get_word_type_none_for_unknown(self):
        self.assertIsNone(self.lex.get_word_type("__不存在__xyz__"))

    def test_lookup_returns_dict_for_known(self):
        if not self.lex.herbs:
            self.skipTest("herbs set is empty")
        sample = next(iter(self.lex.herbs))
        result = self.lex.lookup(sample)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["word"], sample)
        self.assertIn("type", result)
        self.assertIn("category", result)
        self.assertEqual(result["type"], result["category"])

    def test_lookup_returns_none_for_unknown(self):
        result = self.lex.lookup("__不存在__xyz__")
        self.assertIsNone(result)

    def test_lookup_category_matches_get_word_type(self):
        lex = self.lex
        if not lex.formulas:
            self.skipTest("formulas set is empty")
        sample = next(iter(lex.formulas))
        self.assertEqual(lex.lookup(sample)["category"], lex.get_word_type(sample))

    def test_lookup_via_module_helper(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        if not lex.syndromes:
            self.skipTest("syndromes set is empty")
        sample = next(iter(lex.syndromes))
        result = lex.lookup(sample)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "syndrome")


class TestLoadExternalLexicon(unittest.TestCase):
    """场景 3：加载外部词典"""

    def setUp(self):
        # 每个测试独立重置词典单例，避免词条积累影响计数
        from src.infra.lexicon_service import reset_lexicon
        reset_lexicon()

    def tearDown(self):
        from src.infra.lexicon_service import reset_lexicon
        reset_lexicon()

    def _write_word_file(self, words: list[str], tmpdir: str) -> str:
        p = Path(tmpdir) / "ext_dict.txt"
        p.write_text("\n".join(words), encoding="utf-8")
        return str(p)

    def test_load_from_file_returns_count(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        with tempfile.TemporaryDirectory() as d:
            path = self._write_word_file(["独活", "羌活", "防风", "荆芥"], d)
            loaded = lex.load_from_file(path, word_type="herb")
        self.assertEqual(loaded, 4)

    def test_load_from_file_increases_vocab(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        before = lex.get_vocab_size()
        with tempfile.TemporaryDirectory() as d:
            path = self._write_word_file(
                ["__测试词A__", "__测试词B__", "__测试词C__"], d
            )
            lex.load_from_file(path, word_type="common")
        after = lex.get_vocab_size()
        self.assertGreater(after, before)

    def test_load_external_lexicon_helper(self):
        from src.data.tcm_lexicon import get_lexicon, load_external_lexicon
        lex = get_lexicon()
        with tempfile.TemporaryDirectory() as d:
            path = self._write_word_file(["桔梗", "紫菀", "百部"], d)
            count = load_external_lexicon(path, word_type="herb")
        self.assertEqual(count, 3)
        self.assertTrue(lex.contains("桔梗"))

    def test_load_from_nonexistent_file_returns_zero(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        result = lex.load_from_file("/nonexistent/__does_not_exist__.txt", word_type="herb")
        self.assertEqual(result, 0)

    def test_load_file_with_comments_and_blanks(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dict.txt"
            p.write_text("# 这是注释\n\n白术\n茯苓\n", encoding="utf-8")
            count = lex.load_from_file(str(p), word_type="herb")
        self.assertEqual(count, 2)

    def test_add_runtime_terms_returns_stats(self):
        from src.data.tcm_lexicon import add_runtime_terms
        stats = add_runtime_terms("formula", ["桂枝汤_test", "麻黄汤_test"])
        self.assertEqual(stats["word_type"], "formula")
        self.assertEqual(stats["input_count"], 2)
        self.assertGreaterEqual(stats["added_delta"], 0)
        self.assertIn("before_vocab_size", stats)
        self.assertIn("after_vocab_size", stats)


class TestGetVocabSize(unittest.TestCase):
    """场景 4：get_vocab_size"""

    def test_vocab_size_at_least_100(self):
        """验收标准：词汇量 >= 100（JSONL 实际有 635 条）。"""
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        self.assertGreaterEqual(lex.get_vocab_size(), 100)

    def test_vocab_size_equals_sum_of_categories(self):
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        total = (
            len(lex.herbs)
            + len(lex.formulas)
            + len(lex.syndromes)
            + len(lex.theory)
            + len(lex.efficacy)
            + len(lex.common_words)
        )
        self.assertEqual(lex.get_vocab_size(), total)

    def test_vocab_size_increases_after_add(self):
        from src.infra.lexicon_service import reset_lexicon
        reset_lexicon()
        from src.data.tcm_lexicon import get_lexicon
        lex = get_lexicon()
        before = lex.get_vocab_size()
        # 追加一个不存在的词
        unique_word = "__唯一测试词__xyz__9999__"
        lex.add_words("common", [unique_word])
        self.assertEqual(lex.get_vocab_size(), before + 1)
        reset_lexicon()

    def test_get_lexicon_stats_helper(self):
        from src.data.tcm_lexicon import get_lexicon_stats
        stats = get_lexicon_stats()
        self.assertIn("total", stats)
        self.assertIn("herbs", stats)
        self.assertIn("formulas", stats)
        self.assertGreaterEqual(stats["total"], 100)
        self.assertEqual(
            stats["total"],
            stats["herbs"] + stats["formulas"] + stats["syndromes"]
            + stats["theory"] + stats["efficacy"] + stats["common_words"],
        )


if __name__ == "__main__":
    unittest.main()
