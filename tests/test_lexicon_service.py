# tests/test_lexicon_service.py
"""
LexiconService 单元测试

覆盖要点
--------
* 从 JSONL 文件正常加载词条
* 各 category 分配到正确属性
* 跳过坏行 / 未知 category
* contains() / get_word_type() / get_vocab_size()
* add_words() 运行时追加（同时支持 "herb" 和 "herbs" 写法）
* load_from_file() 加载外部文本词典
* 全局单例 get_lexicon() 和 reset_lexicon()
* 文件不存在时优雅降级（词典为空，不报错）
* 向后兼容：从 src.data.tcm_lexicon 导入 TCMLexicon / get_lexicon 仍有效
* TCM_LEXICON_PATH 环境变量覆盖
* 正式 data/tcm_lexicon.jsonl 加载可用（集成校验）
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infra.lexicon_service import (  # noqa: E402
    LexiconService,
    get_lexicon,
    reset_lexicon,
)

# ─────────────────────────────────────────────────────────────────────────────
# 测试辅助
# ─────────────────────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _make_jsonl(records: list[dict], tmp_dir: str | None = None) -> Path:
    d = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp())
    p = d / "test_lexicon.jsonl"
    _write_jsonl(p, records)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 基础加载
# ─────────────────────────────────────────────────────────────────────────────

class TestLoad(unittest.TestCase):
    def test_load_all_categories(self):
        path = _make_jsonl([
            {"term": "人参", "category": "herb"},
            {"term": "四君子汤", "category": "formula"},
            {"term": "气虚证", "category": "syndrome"},
            {"term": "阴阳", "category": "theory"},
            {"term": "补气", "category": "efficacy"},
            {"term": "温", "category": "common"},
        ])
        svc = LexiconService(path)
        self.assertIn("人参", svc.herbs)
        self.assertIn("四君子汤", svc.formulas)
        self.assertIn("气虚证", svc.syndromes)
        self.assertIn("阴阳", svc.theory)
        self.assertIn("补气", svc.efficacy)
        self.assertIn("温", svc.common_words)
        self.assertEqual(svc.get_vocab_size(), 6)

    def test_skip_unknown_category(self):
        path = _make_jsonl([
            {"term": "人参", "category": "herb"},
            {"term": "???", "category": "unknown_cat"},
        ])
        svc = LexiconService(path)
        self.assertEqual(svc.get_vocab_size(), 1)

    def test_skip_empty_term(self):
        path = _make_jsonl([
            {"term": "", "category": "herb"},
            {"term": "  ", "category": "herb"},
            {"term": "黄芪", "category": "herb"},
        ])
        svc = LexiconService(path)
        self.assertEqual(svc.get_vocab_size(), 1)

    def test_skip_blank_lines_and_comments(self):
        tmp = Path(tempfile.mkdtemp()) / "lex.jsonl"
        tmp.write_text(
            '\n'
            '# comment\n'
            '{"term": "甘草", "category": "herb"}\n',
            encoding="utf-8",
        )
        svc = LexiconService(tmp)
        self.assertEqual(svc.get_vocab_size(), 1)

    def test_skip_malformed_json(self):
        tmp = Path(tempfile.mkdtemp()) / "lex.jsonl"
        tmp.write_text(
            '{"term": "人参", "category": "herb"}\n'
            'NOT JSON\n'
            '{"term": "黄芪", "category": "herb"}\n',
            encoding="utf-8",
        )
        svc = LexiconService(tmp)
        self.assertEqual(svc.get_vocab_size(), 2)

    def test_file_not_found_graceful(self):
        svc = LexiconService("/nonexistent/path/lexicon.jsonl")
        self.assertEqual(svc.get_vocab_size(), 0)
        self.assertFalse(svc.contains("人参"))


# ─────────────────────────────────────────────────────────────────────────────
# 查询接口
# ─────────────────────────────────────────────────────────────────────────────

class TestQuery(unittest.TestCase):
    def setUp(self):
        path = _make_jsonl([
            {"term": "人参", "category": "herb"},
            {"term": "四君子汤", "category": "formula"},
        ])
        self.svc = LexiconService(path)

    def test_contains_true(self):
        self.assertTrue(self.svc.contains("人参"))

    def test_contains_false(self):
        self.assertFalse(self.svc.contains("不存在的词"))

    def test_get_word_type_herb(self):
        self.assertEqual(self.svc.get_word_type("人参"), "herb")

    def test_get_word_type_formula(self):
        self.assertEqual(self.svc.get_word_type("四君子汤"), "formula")

    def test_get_word_type_none(self):
        self.assertIsNone(self.svc.get_word_type("xyz"))

    def test_get_all_words_union(self):
        all_w = self.svc.get_all_words()
        self.assertIn("人参", all_w)
        self.assertIn("四君子汤", all_w)

    def test_get_all_words_cached(self):
        w1 = self.svc.get_all_words()
        w2 = self.svc.get_all_words()
        self.assertIs(w1, w2)  # 同一对象（缓存）

    def test_get_vocab_size(self):
        self.assertEqual(self.svc.get_vocab_size(), 2)


# ─────────────────────────────────────────────────────────────────────────────
# add_words — 运行时追加
# ─────────────────────────────────────────────────────────────────────────────

class TestAddWords(unittest.TestCase):
    def setUp(self):
        path = _make_jsonl([{"term": "人参", "category": "herb"}])
        self.svc = LexiconService(path)

    def test_add_by_category_name(self):
        self.svc.add_words("herb", ["黄芪"])
        self.assertIn("黄芪", self.svc.herbs)

    def test_add_by_attr_name(self):
        """支持 'herbs' 这种旧写法。"""
        self.svc.add_words("herbs", ["当归"])
        self.assertIn("当归", self.svc.herbs)

    def test_add_invalidates_cache(self):
        _ = self.svc.get_all_words()  # 触发缓存建立
        self.svc.add_words("herb", ["新词"])
        # 缓存应已清除
        self.assertIsNone(self.svc._all_words)
        self.assertIn("新词", self.svc.get_all_words())

    def test_add_unknown_type_no_error(self):
        self.svc.add_words("nonexistent_type", ["词"])  # 不应抛异常

    def test_add_vocab_size_increases(self):
        before = self.svc.get_vocab_size()
        self.svc.add_words("formula", ["补中益气汤"])
        self.assertEqual(self.svc.get_vocab_size(), before + 1)


# ─────────────────────────────────────────────────────────────────────────────
# load_from_file
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadFromFile(unittest.TestCase):
    def setUp(self):
        path = _make_jsonl([])
        self.svc = LexiconService(path)

    def _write_txt(self, words: list[str]) -> str:
        tmp = tempfile.mktemp(suffix=".txt")
        with open(tmp, "w", encoding="utf-8") as fh:
            for w in words:
                fh.write(w + "\n")
        return tmp

    def test_load_plain_text(self):
        fp = self._write_txt(["附子", "半夏", "南星"])
        count = self.svc.load_from_file(fp, word_type="herb")
        self.assertEqual(count, 3)
        self.assertIn("附子", self.svc.herbs)

    def test_load_multicolumn_takes_first(self):
        tmp = tempfile.mktemp(suffix=".txt")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("黄连 1000 n\n")
            fh.write("黄芩 900 n\n")
        count = self.svc.load_from_file(tmp, word_type="herb")
        self.assertEqual(count, 2)
        self.assertIn("黄连", self.svc.herbs)

    def test_load_nonexistent_returns_zero(self):
        count = self.svc.load_from_file("/no/such/file.txt")
        self.assertEqual(count, 0)

    def test_load_from_jieba_user_dict_alias(self):
        fp = self._write_txt(["白术"])
        count = self.svc.load_from_jieba_user_dict(fp)
        self.assertEqual(count, 1)
        self.assertIn("白术", self.svc.common_words)


# ─────────────────────────────────────────────────────────────────────────────
# 全局单例 get_lexicon / reset_lexicon
# ─────────────────────────────────────────────────────────────────────────────

class TestGlobalSingleton(unittest.TestCase):
    def tearDown(self):
        reset_lexicon()

    def test_get_lexicon_returns_same_instance(self):
        a = get_lexicon()
        b = get_lexicon()
        self.assertIs(a, b)

    def test_reset_creates_new_instance(self):
        a = get_lexicon()
        reset_lexicon()
        b = get_lexicon()
        self.assertIsNot(a, b)


# ─────────────────────────────────────────────────────────────────────────────
# 环境变量覆盖
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvOverride(unittest.TestCase):
    def setUp(self):
        reset_lexicon()

    def tearDown(self):
        os.environ.pop("TCM_LEXICON_PATH", None)
        reset_lexicon()

    def test_env_var_overrides_path(self):
        path = _make_jsonl([{"term": "云茯苓", "category": "herb"}])
        os.environ["TCM_LEXICON_PATH"] = str(path)
        svc = LexiconService()  # 不传路径，从环境变量读
        self.assertIn("云茯苓", svc.herbs)
        self.assertNotIn("人参", svc.herbs)  # 默认词典未加载


# ─────────────────────────────────────────────────────────────────────────────
# 热加载
# ─────────────────────────────────────────────────────────────────────────────

class TestHotReload(unittest.TestCase):
    def test_reload_method_refreshes_from_jsonl(self):
        tmp_dir = tempfile.mkdtemp()
        path = _make_jsonl([
            {"term": "人参", "category": "herb"},
        ], tmp_dir=tmp_dir)
        svc = LexiconService(path)
        self.assertTrue(svc.contains("人参"))
        self.assertFalse(svc.contains("黄芪"))

        _write_jsonl(path, [
            {"term": "黄芪", "category": "herb"},
        ])
        svc.reload()
        self.assertFalse(svc.contains("人参"))
        self.assertTrue(svc.contains("黄芪"))

    def test_query_triggers_auto_hot_reload(self):
        tmp_dir = tempfile.mkdtemp()
        path = _make_jsonl([
            {"term": "四君子汤", "category": "formula"},
        ], tmp_dir=tmp_dir)
        svc = LexiconService(path)
        # 关闭检查间隔，确保测试不受时间窗口影响
        svc._reload_check_interval_sec = 0.0

        self.assertTrue(svc.contains("四君子汤"))
        _write_jsonl(path, [
            {"term": "六君子汤", "category": "formula"},
        ])

        # contains 内部会触发 refresh_if_needed
        self.assertFalse(svc.contains("四君子汤"))
        self.assertTrue(svc.contains("六君子汤"))


# ─────────────────────────────────────────────────────────────────────────────
# 向后兼容：从旧路径导入仍有效
# ─────────────────────────────────────────────────────────────────────────────

class TestBackwardCompat(unittest.TestCase):
    def test_import_from_tcm_lexicon_module(self):
        from src.data.tcm_lexicon import TCMLexicon
        from src.data.tcm_lexicon import get_lexicon as old_get
        lex = old_get()
        self.assertIsInstance(lex, TCMLexicon)
        self.assertGreater(lex.get_vocab_size(), 0)

    def test_tcmlexicon_is_lexicon_service(self):
        from src.data.tcm_lexicon import TCMLexicon
        self.assertIs(TCMLexicon, LexiconService)


# ─────────────────────────────────────────────────────────────────────────────
# 集成校验：正式 data/tcm_lexicon.jsonl
# ─────────────────────────────────────────────────────────────────────────────

class TestOfficialJSONL(unittest.TestCase):
    """验证项目自带的 data/tcm_lexicon.jsonl 内容完整性。"""

    @classmethod
    def setUpClass(cls):
        cls.svc = LexiconService()  # 加载项目默认 JSONL

    def test_vocab_size_at_least_600(self):
        self.assertGreaterEqual(self.svc.get_vocab_size(), 600)

    def test_herbs_not_empty(self):
        self.assertGreater(len(self.svc.herbs), 0)

    def test_formulas_not_empty(self):
        self.assertGreater(len(self.svc.formulas), 0)

    def test_syndromes_not_empty(self):
        self.assertGreater(len(self.svc.syndromes), 0)

    def test_theory_not_empty(self):
        self.assertGreater(len(self.svc.theory), 0)

    def test_efficacy_not_empty(self):
        self.assertGreater(len(self.svc.efficacy), 0)

    def test_known_herb_present(self):
        self.assertTrue(self.svc.contains("人参"))

    def test_known_formula_present(self):
        self.assertTrue(self.svc.contains("四君子汤"))

    def test_word_type_herb(self):
        self.assertEqual(self.svc.get_word_type("人参"), "herb")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
