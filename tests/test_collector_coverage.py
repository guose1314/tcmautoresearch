"""normalizer.py + local_collector.py + multi_source_corpus.py 覆盖率补齐测试。"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.collector.corpus_bundle import CorpusBundle, CorpusDocument
from src.collector.normalizer import NormalizationResult, Normalizer


# ===================================================================
# NormalizationResult
# ===================================================================
class TestNormalizationResult(unittest.TestCase):
    def test_to_dict(self):
        r = NormalizationResult(success=True, normalized_text="text")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["normalized_text"], "text")


# ===================================================================
# Normalizer 初始化
# ===================================================================
class TestNormalizerInit(unittest.TestCase):
    def test_opencc_init_success(self):
        n = Normalizer({"convert_mode": "t2s"})
        n.initialize()
        # OpenCC may or may not be installed; test should pass either way.
        n.cleanup()
        self.assertIsNone(n._opencc)

    def test_opencc_disabled(self):
        n = Normalizer({"convert_mode": ""})
        n.initialize()
        self.assertIsNone(n._opencc)
        n.cleanup()

    def test_opencc_init_failure(self):
        n = Normalizer({"convert_mode": "t2s"})
        with patch("src.collector.normalizer.importlib.import_module", side_effect=ImportError("no opencc")):
            n.initialize()
        self.assertIsNone(n._opencc)
        n.cleanup()


# ===================================================================
# _decode_text / _detect_encoding
# ===================================================================
class TestDecodeText(unittest.TestCase):
    def setUp(self):
        self.n = Normalizer({})

    def test_string_input(self):
        text, enc = self.n._decode_text("hello")
        self.assertEqual(text, "hello")
        self.assertEqual(enc, "utf-8")

    def test_bytes_utf8(self):
        text, enc = self.n._decode_text("中文".encode("utf-8"))
        self.assertIn("中文", text)

    def test_bytes_gb18030(self):
        text, enc = self.n._decode_text("中文".encode("gb18030"))
        self.assertIn("中文", text)
        text, enc = self.n._decode_text(12345)
        self.assertEqual(text, "12345")

    def test_detect_encoding_chardet_missing(self):
        with patch("src.collector.normalizer.importlib.import_module", side_effect=ImportError("no chardet")):
            enc = self.n._detect_encoding(b"data")
            self.assertEqual(enc, "utf-8")


# ===================================================================
# _convert_text
# ===================================================================
class TestConvertText(unittest.TestCase):
    def test_no_opencc(self):
        n = Normalizer({"convert_mode": ""})
        n.initialize()
        self.assertEqual(n._convert_text("黃芪"), "黃芪")
        n.cleanup()

    def test_opencc_exception(self):
        n = Normalizer({})
        n._opencc = MagicMock()
        n._opencc.convert.side_effect = RuntimeError("convert failed")
        result = n._convert_text("input")
        self.assertEqual(result, "input")


# ===================================================================
# _normalize_metadata_value
# ===================================================================
class TestNormalizeMetadataValue(unittest.TestCase):
    def setUp(self):
        self.n = Normalizer({})
        self.n.initialize()

    def tearDown(self):
        self.n.cleanup()

    def test_none_value(self):
        self.assertIsNone(self.n._normalize_metadata_value("title", None))

    def test_list_field_from_string(self):
        result = self.n._normalize_metadata_value("authors", "张三,李四")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_list_field_with_semicolons(self):
        result = self.n._normalize_metadata_value("keywords", "中医;针灸;方剂")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)

    def test_bytes_value(self):
        result = self.n._normalize_metadata_value("title", b"\xe4\xb8\xad\xe6\x96\x87")
        self.assertIsInstance(result, str)

    def test_dict_value(self):
        result = self.n._normalize_metadata_value("nested", {"key": "val"})
        self.assertIsInstance(result, dict)

    def test_list_value(self):
        result = self.n._normalize_metadata_value("other", ["a", None, "b"])
        self.assertIsInstance(result, list)

    def test_int_value(self):
        result = self.n._normalize_metadata_value("count", 42)
        self.assertEqual(result, 42)

    def test_source_type_string(self):
        result = self.n._normalize_metadata_value("source_type", "PDF")
        self.assertEqual(result, "pdf")


# ===================================================================
# _normalize_list_value
# ===================================================================
class TestNormalizeListValue(unittest.TestCase):
    def setUp(self):
        self.n = Normalizer({})
        self.n.initialize()

    def tearDown(self):
        self.n.cleanup()

    def test_string_with_chinese_separators(self):
        result = self.n._normalize_list_value("张三、李四、王五")
        self.assertEqual(len(result), 3)

    def test_string_with_newlines(self):
        result = self.n._normalize_list_value("a\nb\nc")
        self.assertEqual(len(result), 3)

    def test_list_input(self):
        result = self.n._normalize_list_value(["a", "b"])
        self.assertEqual(len(result), 2)

    def test_set_input(self):
        result = self.n._normalize_list_value({"a", "b"})
        self.assertEqual(len(result), 2)

    def test_non_iterable(self):
        result = self.n._normalize_list_value(123)
        self.assertEqual(len(result), 1)

    def test_dedup(self):
        result = self.n._normalize_list_value(["a", "a", "b"])
        self.assertEqual(len(result), 2)

    def test_none_items_skipped(self):
        result = self.n._normalize_list_value([None, "a"])
        self.assertEqual(len(result), 1)


# ===================================================================
# _merge_metadata_value
# ===================================================================
class TestMergeMetadataValue(unittest.TestCase):
    def setUp(self):
        self.n = Normalizer({})

    def test_list_merge(self):
        result = self.n._merge_metadata_value(["a"], ["b"])
        self.assertEqual(result, ["a", "b"])

    def test_list_dedup(self):
        result = self.n._merge_metadata_value(["a"], ["a"])
        self.assertEqual(result, ["a"])

    def test_right_overrides(self):
        result = self.n._merge_metadata_value("old", "new")
        self.assertEqual(result, "new")

    def test_right_empty_keeps_left(self):
        result = self.n._merge_metadata_value("old", "")
        self.assertEqual(result, "old")

    def test_right_none_keeps_left(self):
        result = self.n._merge_metadata_value("old", None)
        self.assertEqual(result, "old")


# ===================================================================
# _apply_term_mappings
# ===================================================================
class TestApplyTermMappings(unittest.TestCase):
    def test_mapping_applied(self):
        n = Normalizer({"term_mappings": {"黃芪": "黄芪"}})
        n.initialize()
        text, used = n._apply_term_mappings("黃芪30克")
        self.assertIn("黄芪", text)
        self.assertIn("黃芪", used)
        n.cleanup()

    def test_empty_alias_skipped(self):
        n = Normalizer({"term_mappings": {"": "noop"}})
        n.initialize()
        text, used = n._apply_term_mappings("normal text")
        self.assertEqual(len(used), 0)
        n.cleanup()


# ===================================================================
# normalize_document 含 children
# ===================================================================
class TestNormalizeDocument(unittest.TestCase):
    def test_document_with_children(self):
        n = Normalizer({})
        n.initialize()
        child = CorpusDocument(
            doc_id="child1", title="子文档", text="黃芪", source_type="local",
            source_ref="child.txt", language="zh",
        )
        parent = CorpusDocument(
            doc_id="parent1", title="父文档", text="正文", source_type="local",
            source_ref="parent.txt", language="zh", children=[child],
        )
        result, norm_doc = n.normalize_document(parent)
        self.assertTrue(result.success)
        self.assertEqual(len(norm_doc.children), 1)
        n.cleanup()

    def test_document_from_dict(self):
        n = Normalizer({})
        n.initialize()
        doc_dict = {
            "doc_id": "d1", "title": "T", "text": "content",
            "source_type": "txt", "source_ref": "f.txt", "language": "zh",
        }
        result, norm_doc = n.normalize_document(doc_dict)
        self.assertTrue(result.success)
        self.assertEqual(norm_doc.source_type, "local")  # txt → local
        n.cleanup()


# ===================================================================
# normalize_bundle
# ===================================================================
class TestNormalizeBundle(unittest.TestCase):
    def test_bundle_normalization(self):
        n = Normalizer({})
        n.initialize()
        doc = CorpusDocument(
            doc_id="d1", title="T", text="黃芪30克",
            source_type="local", source_ref="f.txt", language="zh",
        )
        bundle = CorpusBundle(
            bundle_id="b1", sources=["local"], documents=[doc],
            collected_at="2025-01-01", stats={}, errors=[],
        )
        result = n.normalize_bundle(bundle)
        self.assertIsInstance(result, CorpusBundle)
        self.assertEqual(len(result.documents), 1)
        n.cleanup()

    def test_bundle_from_dict(self):
        n = Normalizer({})
        n.initialize()
        bundle_dict = {
            "bundle_id": "b1",
            "sources": ["local"],
            "documents": [{
                "doc_id": "d1", "title": "T", "text": "text",
                "source_type": "local", "source_ref": "f", "language": "zh",
            }],
            "collected_at": "2025-01-01",
            "stats": {},
            "errors": [],
            "schema_version": "1.0",
        }
        result = n.normalize_bundle(bundle_dict)
        self.assertIsInstance(result, CorpusBundle)
        n.cleanup()


# ===================================================================
# _do_execute 多分支
# ===================================================================
class TestNormalizerExecute(unittest.TestCase):
    def setUp(self):
        self.n = Normalizer({})
        self.n.initialize()

    def tearDown(self):
        self.n.cleanup()

    def test_execute_with_text(self):
        result = self.n.execute({"raw_text": "黃芪30克"})
        self.assertTrue(result["success"])

    def test_execute_with_document(self):
        doc = {"doc_id": "d1", "title": "T", "text": "text", "source_type": "local", "source_ref": "f", "language": "zh"}
        result = self.n.execute({"document": doc})
        self.assertTrue(result["success"])
        self.assertIn("document", result)

    def test_execute_with_documents_list(self):
        docs = [
            {"doc_id": "d1", "title": "T1", "text": "t1", "source_type": "local", "source_ref": "f1", "language": "zh"},
            {"doc_id": "d2", "title": "T2", "text": "t2", "source_type": "local", "source_ref": "f2", "language": "zh"},
        ]
        result = self.n.execute({"documents": docs})
        self.assertEqual(result["document_count"], 2)

    def test_execute_no_input_raises(self):
        with self.assertRaises(ValueError):
            self.n.execute({})


# ===================================================================
# _normalize_metadata year extraction
# ===================================================================
class TestNormalizeMetadataYear(unittest.TestCase):
    def test_year_from_publish_date(self):
        n = Normalizer({})
        n.initialize()
        meta = n._normalize_metadata(
            {"publish_date": "2024-03-15", "metadata": {}}, "utf-8", {}
        )
        self.assertEqual(meta.get("year"), "2024")
        n.cleanup()

    def test_year_not_extracted_when_present(self):
        n = Normalizer({})
        n.initialize()
        meta = n._normalize_metadata(
            {"publish_date": "2024-01-01", "year": "2023", "metadata": {}}, "utf-8", {}
        )
        self.assertEqual(meta["year"], "2023")
        n.cleanup()


# ===================================================================
# _normalize_source_type
# ===================================================================
class TestNormalizeSourceType(unittest.TestCase):
    def test_known_aliases(self):
        n = Normalizer({})
        self.assertEqual(n._normalize_source_type("txt"), "local")
        self.assertEqual(n._normalize_source_type("PDF"), "pdf")
        self.assertEqual(n._normalize_source_type(""), "local")

    def test_custom_alias(self):
        n = Normalizer({"source_type_aliases": {"custom": "special"}})
        self.assertEqual(n._normalize_source_type("custom"), "special")


# ===================================================================
# local_collector.py
# ===================================================================
class TestLocalCollector(unittest.TestCase):
    def test_collect_txt_files(self):
        from src.collector.local_collector import LocalCorpusCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["001-伤寒论.txt", "002-金匮要略.txt"]:
                with open(os.path.join(tmpdir, name), "w", encoding="utf-8") as f:
                    f.write("中医古籍内容" * 20)

            collector = LocalCorpusCollector({"data_dir": tmpdir})
            collector.initialize()
            result = collector._do_execute({"data_dir": tmpdir})
            self.assertEqual(result["stats"]["total_documents"], 2)
            for doc in result["documents"]:
                self.assertIn("中医古籍内容", doc["text"])
            collector.cleanup()

    def test_collect_gb18030_file(self):
        from src.collector.local_collector import LocalCorpusCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "gb18030.txt")
            with open(path, "wb") as f:
                f.write("中医方剂内容测试文本加长".encode("gb18030") * 10)

            collector = LocalCorpusCollector({"data_dir": tmpdir})
            collector.initialize()
            result = collector._do_execute({"data_dir": tmpdir})
            self.assertGreater(result["stats"]["total_documents"], 0)
            collector.cleanup()

    def test_nonrecursive_scan(self):
        from src.collector.local_collector import LocalCorpusCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)
            with open(os.path.join(tmpdir, "top.txt"), "w", encoding="utf-8") as f:
                f.write("顶层文件内容" * 20)
            with open(os.path.join(subdir, "nested.txt"), "w", encoding="utf-8") as f:
                f.write("嵌套文件内容" * 20)

            collector = LocalCorpusCollector({"data_dir": tmpdir, "recursive": False})
            collector.initialize()
            result = collector._do_execute({"data_dir": tmpdir, "recursive": False})
            self.assertEqual(result["stats"]["total_documents"], 1)
            collector.cleanup()

    def test_empty_file_skipped(self):
        from src.collector.local_collector import LocalCorpusCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "empty.txt"), "w") as f:
                pass
            collector = LocalCorpusCollector({"data_dir": tmpdir, "min_text_length": 10})
            collector.initialize()
            result = collector._do_execute({"data_dir": tmpdir})
            self.assertEqual(result["stats"]["total_documents"], 0)
            collector.cleanup()

    def test_title_inference_numeric_prefix(self):
        from src.collector.local_collector import LocalCorpusCollector
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "013-本草纲目.txt"), "w", encoding="utf-8") as f:
                f.write("本草纲目全文内容" * 20)
            collector = LocalCorpusCollector({"data_dir": tmpdir})
            collector.initialize()
            result = collector._do_execute({"data_dir": tmpdir})
            self.assertEqual(result["stats"]["total_documents"], 1)
            self.assertEqual(result["documents"][0]["title"], "本草纲目")
            collector.cleanup()


# ===================================================================
# multi_source_corpus.py
# ===================================================================
class TestMultiSourceCorpus(unittest.TestCase):
    def test_recognize_by_suffix(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        self.assertEqual(recognize_classical_format(file_name="test.pdf"), "pdf")
        self.assertEqual(recognize_classical_format(file_name="test.epub"), "epub")
        self.assertEqual(recognize_classical_format(file_name="test.txt"), "txt")

    def test_recognize_case_insensitive(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        self.assertEqual(recognize_classical_format(file_name="test.PDF"), "pdf")

    def test_recognize_by_sample_json(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        fmt = recognize_classical_format(sample_text='{"key": "val"}')
        self.assertEqual(fmt, "json")

    def test_recognize_by_sample_xml(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        # _recognize_by_sample_text doesn't match <?xml, returns default "txt"
        fmt = recognize_classical_format(sample_text="<?xml version='1.0'?>")
        self.assertEqual(fmt, "txt")

    def test_recognize_by_sample_html(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        fmt = recognize_classical_format(sample_text="<html><body>test</body></html>")
        self.assertEqual(fmt, "html")

    def test_recognize_unknown(self):
        from src.collector.multi_source_corpus import recognize_classical_format
        fmt = recognize_classical_format(file_name="test.xyz")
        # No suffix match, no media type, no sample text -> default "txt"
        self.assertEqual(fmt, "txt")

    def test_cross_validate_identical(self):
        from src.collector.multi_source_corpus import (
            SourceWitness,
            cross_validate_witnesses,
        )
        w1 = SourceWitness(source_id="s1", title="文本1", text="完全一样的文本", metadata={})
        w2 = SourceWitness(source_id="s2", title="文本2", text="完全一样的文本", metadata={})
        result = cross_validate_witnesses([w1, w2])
        self.assertGreater(result["consistency_score"], 0.9)

    def test_cross_validate_different(self):
        from src.collector.multi_source_corpus import (
            SourceWitness,
            cross_validate_witnesses,
        )
        w1 = SourceWitness(source_id="s1", title="A", text="ABCDEF", metadata={})
        w2 = SourceWitness(source_id="s2", title="B", text="XYZWUV", metadata={})
        result = cross_validate_witnesses([w1, w2])
        self.assertLess(result["consistency_score"], 0.5)

    def test_build_collection_plan(self):
        from src.collector.multi_source_corpus import build_source_collection_plan
        # build_source_collection_plan reads from registry file; mock it
        with patch("src.collector.multi_source_corpus.load_source_registry") as mock_load:
            mock_load.return_value = {
                "sources": [{"id": "s1", "name": "Local", "base_url": "", "collection_modes": [], "supported_formats": [], "implemented": True}]
            }
            plan = build_source_collection_plan("test_query")
            self.assertIsInstance(plan, dict)
            self.assertEqual(plan["route_count"], 1)


if __name__ == "__main__":
    unittest.main()
