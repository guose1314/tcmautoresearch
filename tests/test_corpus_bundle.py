"""tests/test_corpus_bundle.py — 2.5 CorpusBundle 单元测试"""

import os
import tempfile
import unittest

from src.corpus.corpus_bundle import (
    BUNDLE_SCHEMA_VERSION,
    CorpusBundle,
    CorpusDocument,
    extract_text_entries,
    is_corpus_bundle,
)
from src.corpus.local_collector import LocalCorpusCollector, _infer_title

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_ctext_result(docs=None):
    return {
        "source": "ctext",
        "collected_at": "2026-01-01T00:00:00",
        "seed_urns": ["ctp:analects"],
        "documents": docs or [
            {
                "urn": "ctp:analects:1",
                "title": "论语·学而",
                "text": "子曰：学而时习之",
                "children": [
                    {
                        "urn": "ctp:analects:1:1",
                        "title": "第一节",
                        "text": "不亦说乎",
                        "children": [],
                    }
                ],
            }
        ],
        "stats": {"document_count": 1, "chapter_count": 1, "line_count": 1, "char_count": 50},
        "errors": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CorpusDocument
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusDocument(unittest.TestCase):
    def test_round_trip(self):
        doc = CorpusDocument(
            doc_id="ctext_abc123",
            title="论语",
            text="学而时习之",
            source_type="ctext",
            source_ref="ctp:analects:1",
        )
        d = doc.to_dict()
        self.assertEqual(d["doc_id"], "ctext_abc123")
        self.assertIn("children", d)
        restored = CorpusDocument.from_dict(d)
        self.assertEqual(restored.title, "论语")
        self.assertEqual(restored.source_type, "ctext")

    def test_nested_children_round_trip(self):
        child = CorpusDocument(
            doc_id="ctext_child",
            title="第一节",
            text="不亦说乎",
            source_type="ctext",
            source_ref="ctp:analects:1:1",
        )
        parent = CorpusDocument(
            doc_id="ctext_parent",
            title="学而篇",
            text="",
            source_type="ctext",
            source_ref="ctp:analects:1",
            children=[child],
        )
        d = parent.to_dict()
        restored = CorpusDocument.from_dict(d)
        self.assertEqual(len(restored.children), 1)
        self.assertEqual(restored.children[0].title, "第一节")


# ─────────────────────────────────────────────────────────────────────────────
# CorpusBundle — from_ctext_result
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusBundleFromCtext(unittest.TestCase):
    def setUp(self):
        self.ctext_result = _make_ctext_result()

    def test_schema_version_present(self):
        bundle = CorpusBundle.from_ctext_result(self.ctext_result)
        d = bundle.to_dict()
        self.assertEqual(d["schema_version"], BUNDLE_SCHEMA_VERSION)

    def test_sources_is_ctext(self):
        bundle = CorpusBundle.from_ctext_result(self.ctext_result)
        self.assertEqual(bundle.sources, ["ctext"])

    def test_documents_converted(self):
        bundle = CorpusBundle.from_ctext_result(self.ctext_result)
        self.assertEqual(len(bundle.documents), 1)
        doc = bundle.documents[0]
        self.assertEqual(doc.source_type, "ctext")
        self.assertEqual(doc.source_ref, "ctp:analects:1")
        self.assertEqual(doc.title, "论语·学而")
        self.assertEqual(len(doc.children), 1)

    def test_old_stats_preserved(self):
        """backward-compat: 旧 document_count 字段应保留在 stats 中。"""
        bundle = CorpusBundle.from_ctext_result(self.ctext_result)
        d = bundle.to_dict()
        self.assertEqual(d["stats"]["document_count"], 1)
        self.assertEqual(d["stats"]["total_documents"], 1)

    def test_flat_documents_includes_leaf(self):
        bundle = CorpusBundle.from_ctext_result(self.ctext_result)
        flat = bundle.flat_documents()
        titles = [d.title for d in flat]
        self.assertIn("论语·学而", titles)
        self.assertIn("第一节", titles)


# ─────────────────────────────────────────────────────────────────────────────
# CorpusBundle — from_pdf_result
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusBundleFromPdf(unittest.TestCase):
    def _pdf_result(self, status="completed", error=""):
        return {
            "status": status,
            "pdf_path": "/tmp/test.pdf",
            "title": "Test Paper",
            "abstract": "This is an abstract.",
            "abstract_translated": "这是摘要。",
            "fragment_total": 2,
            "fragment_ok": 2,
            "fragment_results": [
                {"original": "Introduction text.", "translated": "引言文字。"},
                {"original": "Methods section.", "translated": "方法部分。"},
            ],
            "error": error,
        }

    def test_pdf_bundle_schema_version(self):
        bundle = CorpusBundle.from_pdf_result(self._pdf_result())
        d = bundle.to_dict()
        self.assertEqual(d["schema_version"], BUNDLE_SCHEMA_VERSION)
        self.assertEqual(d["sources"], ["pdf"])

    def test_pdf_text_extracted_from_fragments(self):
        bundle = CorpusBundle.from_pdf_result(self._pdf_result())
        self.assertEqual(len(bundle.documents), 1)
        doc = bundle.documents[0]
        self.assertIn("Introduction text.", doc.text)
        self.assertIn("Methods section.", doc.text)

    def test_pdf_error_results_in_empty_docs_and_error_entry(self):
        bundle = CorpusBundle.from_pdf_result(self._pdf_result(status="failed", error="parse error"))
        self.assertEqual(bundle.documents, [])
        self.assertEqual(len(bundle.errors), 1)
        self.assertIn("parse error", bundle.errors[0]["error"])


# ─────────────────────────────────────────────────────────────────────────────
# CorpusBundle — merge
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusBundleMerge(unittest.TestCase):
    def _local_bundle(self, n=2) -> CorpusBundle:
        docs = [
            CorpusDocument(
                doc_id=f"local_{i}",
                title=f"本草{i}",
                text=f"本草文字{i}" * 10,
                source_type="local",
                source_ref=f"/data/book{i}.txt",
            )
            for i in range(n)
        ]
        return CorpusBundle(
            bundle_id="local_bundle",
            sources=["local"],
            documents=docs,
            collected_at="2026-01-01T00:00:00",
            stats={"total_documents": n},
            errors=[],
        )

    def test_merge_two_bundles(self):
        ctext_bundle = CorpusBundle.from_ctext_result(_make_ctext_result())
        local_bundle = self._local_bundle(2)
        merged = CorpusBundle.merge([ctext_bundle, local_bundle])
        self.assertIn("ctext", merged.sources)
        self.assertIn("local", merged.sources)
        self.assertEqual(merged.stats["per_source"]["local"], 2)
        self.assertEqual(merged.schema_version, BUNDLE_SCHEMA_VERSION)

    def test_merge_deduplicates_doc_id(self):
        b1 = self._local_bundle(2)
        b2 = self._local_bundle(2)  # same doc_ids
        merged = CorpusBundle.merge([b1, b2])
        self.assertEqual(len(merged.documents), 2)

    def test_merge_deduplicates_cross_source_same_content(self):
        local_doc = CorpusDocument(
            doc_id="local_a",
            title="伤寒论·序",
            text="太阳病，发热恶寒，脉浮紧。",
            source_type="local",
            source_ref="C:/data/a.txt",
        )
        pdf_doc = CorpusDocument(
            doc_id="pdf_b",
            title="伤寒论 序",
            text="  太阳病，发热恶寒，脉浮紧。  ",
            source_type="pdf",
            source_ref="C:/paper/a.pdf",
        )
        b1 = CorpusBundle(
            bundle_id="b1",
            sources=["local"],
            documents=[local_doc],
            collected_at="2026-01-01T00:00:00",
            stats={"total_documents": 1},
            errors=[],
        )
        b2 = CorpusBundle(
            bundle_id="b2",
            sources=["pdf"],
            documents=[pdf_doc],
            collected_at="2026-01-01T00:00:01",
            stats={"total_documents": 1},
            errors=[],
        )
        merged = CorpusBundle.merge([b1, b2])
        self.assertEqual(len(merged.documents), 1)
        self.assertGreaterEqual(merged.stats.get("duplicate_documents", 0), 1)
        merged_doc = merged.documents[0]
        self.assertIn("merged_sources", merged_doc.metadata)
        self.assertGreaterEqual(len(merged_doc.metadata["merged_sources"]), 2)

    def test_merge_single_passthrough(self):
        b = self._local_bundle(1)
        result = CorpusBundle.merge([b])
        self.assertIs(result, b)

    def test_merge_empty_raises(self):
        with self.assertRaises(ValueError):
            CorpusBundle.merge([])

    def test_round_trip_dict(self):
        ctext_bundle = CorpusBundle.from_ctext_result(_make_ctext_result())
        d = ctext_bundle.to_dict()
        restored = CorpusBundle.from_dict(d)
        self.assertEqual(restored.bundle_id, ctext_bundle.bundle_id)
        self.assertEqual(len(restored.documents), len(ctext_bundle.documents))


# ─────────────────────────────────────────────────────────────────────────────
# is_corpus_bundle / extract_text_entries
# ─────────────────────────────────────────────────────────────────────────────

class TestIsCorpusBundle(unittest.TestCase):
    def test_new_format_detected(self):
        bundle = CorpusBundle.from_ctext_result(_make_ctext_result())
        self.assertTrue(is_corpus_bundle(bundle.to_dict()))

    def test_old_ctext_format_not_bundle(self):
        self.assertFalse(is_corpus_bundle(_make_ctext_result()))

    def test_none_not_bundle(self):
        self.assertFalse(is_corpus_bundle(None))

    def test_empty_dict_not_bundle(self):
        self.assertFalse(is_corpus_bundle({}))


class TestExtractTextEntries(unittest.TestCase):
    def test_extract_from_old_ctext(self):
        result = _make_ctext_result()
        entries = extract_text_entries(result)
        texts = [e["text"] for e in entries]
        self.assertIn("子曰：学而时习之", texts)
        self.assertIn("不亦说乎", texts)
        # 旧格式无 source_type 字段
        self.assertNotIn("source_type", entries[0])

    def test_extract_from_bundle(self):
        bundle = CorpusBundle.from_ctext_result(_make_ctext_result())
        entries = extract_text_entries(bundle.to_dict())
        texts = [e["text"] for e in entries]
        self.assertIn("子曰：学而时习之", texts)
        # 新格式含 source_type
        self.assertIn("source_type", entries[0])
        self.assertEqual(entries[0]["source_type"], "ctext")

    def test_extract_empty_docs(self):
        result = {"documents": []}
        entries = extract_text_entries(result)
        self.assertEqual(entries, [])


class TestCorpusBundleFromResult(unittest.TestCase):
    def test_from_result_ctext_auto_detect(self):
        bundle = CorpusBundle.from_result(_make_ctext_result())
        self.assertEqual(bundle.sources, ["ctext"])
        self.assertEqual(bundle.stats["total_documents"], 1)

    def test_from_result_generic_documents(self):
        raw = {
            "source": "external",
            "documents": [
                {
                    "title": "外部文献",
                    "text": "外部文本",
                    "url": "https://example.org/x",
                }
            ],
        }
        bundle = CorpusBundle.from_result(raw)
        self.assertEqual(bundle.sources, ["external"])
        self.assertEqual(len(bundle.documents), 1)
        self.assertEqual(bundle.documents[0].source_type, "external")

    def test_merge_results(self):
        ctext = _make_ctext_result()
        local = {
            "source": "local",
            "documents": [
                {
                    "path": "C:/data/local.txt",
                    "title": "本地文献",
                    "text": "本地文本",
                }
            ],
        }
        merged = CorpusBundle.merge_results([ctext, local])
        self.assertIn("ctext", merged.sources)
        self.assertIn("local", merged.sources)
        self.assertGreaterEqual(merged.stats["total_documents"], 2)


# ─────────────────────────────────────────────────────────────────────────────
# LocalCorpusCollector
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalCorpusCollector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 写一个 UTF-8 文件
        path_utf8 = os.path.join(self.tmp, "013-本草纲目-明-李时珍.txt")
        with open(path_utf8, "w", encoding="utf-8") as f:
            f.write("气味苦，微寒，无毒。主治诸热黄疸，肠澼泄痢，逐水。" * 5)
        # 写一个过短内容文件（应被跳过）
        path_short = os.path.join(self.tmp, "short.txt")
        with open(path_short, "w", encoding="utf-8") as f:
            f.write("短")

    def test_execute_returns_corpus_bundle(self):
        collector = LocalCorpusCollector({"data_dir": self.tmp, "min_text_length": 10})
        self.assertTrue(collector.initialize())
        result = collector.execute({"data_dir": self.tmp})
        self.assertTrue(is_corpus_bundle(result))
        self.assertEqual(result["sources"], ["local"])

    def test_collects_utf8_file(self):
        collector = LocalCorpusCollector({"data_dir": self.tmp, "min_text_length": 10})
        collector.initialize()
        result = collector.execute({"data_dir": self.tmp})
        self.assertEqual(result["stats"]["total_documents"], 1)
        doc_title = result["documents"][0]["title"]
        self.assertEqual(doc_title, "本草纲目-明-李时珍")

    def test_short_file_skipped(self):
        collector = LocalCorpusCollector({"data_dir": self.tmp, "min_text_length": 50})
        collector.initialize()
        result = collector.execute({"data_dir": self.tmp})
        titles = [d["title"] for d in result["documents"]]
        self.assertNotIn("short", titles)

    def test_infer_title_strips_prefix(self):
        self.assertEqual(_infer_title("013-本草纲目-明-李时珍.txt"), "本草纲目-明-李时珍")
        self.assertEqual(_infer_title("金匮要略.txt"), "金匮要略")

    def test_max_files_respected(self):
        # 写 5 个文件
        for i in range(5):
            p = os.path.join(self.tmp, f"file_{i:03d}.txt")
            with open(p, "w") as f:
                f.write("内容" * 30)
        collector = LocalCorpusCollector({"data_dir": self.tmp, "min_text_length": 1})
        collector.initialize()
        result = collector.execute({"data_dir": self.tmp, "max_files": 3})
        self.assertLessEqual(result["stats"]["total_documents"], 3)

    def test_invalid_dir_raises(self):
        collector = LocalCorpusCollector({"data_dir": "/nonexistent/path"})
        collector.initialize()
        with self.assertRaises(Exception):
            collector.execute({"data_dir": "/nonexistent/path"})


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline integration: local corpus observe
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineLocalCorpusObserve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for i in range(2):
            p = os.path.join(self.tmp, f"text_{i}.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("神农尝百草，日遇七十二毒。" * 10)

    def test_observe_phase_with_local_corpus(self):
        from src.research.research_pipeline import ResearchPhase, ResearchPipeline

        pipeline = ResearchPipeline(
            {
                "local_corpus": {
                    "enabled": True,
                    "data_dir": self.tmp,
                    "file_glob": "*.txt",
                    "max_files": 10,
                    "min_text_length": 10,
                }
            }
        )
        cycle = pipeline.create_research_cycle(
            cycle_name="local_observe",
            description="本地语料观察阶段测试",
            objective="验证本地语料接入",
            scope="本地文件",
            researchers=["tester"],
        )
        pipeline.start_research_cycle(cycle.cycle_id)
        result = pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {"run_literature_retrieval": False, "run_preprocess_and_extract": False},
        )

        self.assertEqual(result["phase"], "observe")
        corpus = result["corpus_collection"]
        self.assertTrue(is_corpus_bundle(corpus), "corpus_collection 应为 CorpusBundle 新格式")
        self.assertEqual(corpus["sources"], ["local"])
        self.assertEqual(corpus["stats"]["total_documents"], 2)
        self.assertEqual(result["metadata"]["data_source"], "local")
        self.assertTrue(result["metadata"]["auto_collected_corpus"])

    def test_observe_phase_ctext_still_works(self):
        """CText 旧路径不变，corpus_collection 仍能提取 stats.document_count。"""
        from unittest.mock import patch

        from src.research.research_pipeline import ResearchPhase, ResearchPipeline

        pipeline = ResearchPipeline(
            {
                "ctext_corpus": {
                    "enabled": True,
                    "whitelist": {"enabled": True, "path": "data/ctext_whitelist.json"}
                }
            }
        )
        cycle = pipeline.create_research_cycle(
            cycle_name="ctext_compat",
            description="旧格式兼容测试",
            objective="verify backward compat",
            scope="ctext",
            researchers=["tester"],
        )
        pipeline.start_research_cycle(cycle.cycle_id)

        mock_ctext_result = {
            "source": "ctext",
            "collected_at": "2026-01-01T00:00:00",
            "seed_urns": ["ctp:analects"],
            "documents": [{"urn": "ctp:1", "title": "论语", "text": "学而时习之", "children": []}],
            "stats": {"document_count": 1},
            "errors": [],
        }

        with patch("src.research.research_pipeline.CTextCorpusCollector.initialize", return_value=True), \
             patch("src.research.research_pipeline.CTextCorpusCollector.execute", return_value=mock_ctext_result), \
             patch("src.research.research_pipeline.CTextCorpusCollector.cleanup", return_value=True):
            result = pipeline.execute_research_phase(
                cycle.cycle_id,
                ResearchPhase.OBSERVE,
                {"run_literature_retrieval": False, "run_preprocess_and_extract": False},
            )

        corpus = result["corpus_collection"]
        # 新格式（CText 已被 wrap 为 CorpusBundle）
        self.assertTrue(is_corpus_bundle(corpus))
        # 旧 document_count 字段通过 **old_stats 保留在 stats 中
        self.assertEqual(corpus["stats"]["document_count"], 1)
        # auto_collected_ctext 仍为 True（bundle 含 ctext source）
        self.assertTrue(result["metadata"]["auto_collected_ctext"])
        self.assertIn("标准语料白名单", result["findings"][0])


if __name__ == "__main__":
    unittest.main()
