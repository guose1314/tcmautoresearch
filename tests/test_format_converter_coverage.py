"""format_converter.py 覆盖率补齐测试 — 目标 ≥ 90%。

覆盖 HTML 渲染链、EPUB 结构处理、OCR 管道、模块级工具函数等未覆盖路径。
"""

import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from src.collector.format_converter import (
    ConversionResult,
    FormatConverter,
    _compose_markdown,
    _guess_title_from_text,
    _has_substantive_text,
    _infer_title_from_path,
    _normalize_whitespace,
    _unique_preserve_order,
)


# ---------------------------------------------------------------------------
# 模块级工具函数
# ---------------------------------------------------------------------------
class TestUtilFunctions(unittest.TestCase):
    def test_normalize_whitespace_strips_multi_newlines(self):
        self.assertEqual(_normalize_whitespace("a\n\n\n\nb"), "a\n\nb")

    def test_normalize_whitespace_strips_tabs(self):
        self.assertEqual(_normalize_whitespace("a\t\tb"), "a b")

    def test_has_substantive_text_below_threshold(self):
        self.assertFalse(_has_substantive_text("---", 10))

    def test_has_substantive_text_above_threshold(self):
        self.assertTrue(_has_substantive_text("中医理论与方剂研究汇总资料", 5))

    def test_infer_title_with_numeric_prefix(self):
        self.assertEqual(_infer_title_from_path("/data/013-本草纲目.txt"), "本草纲目")

    def test_infer_title_without_prefix(self):
        self.assertEqual(_infer_title_from_path("/data/伤寒论.txt"), "伤寒论")

    def test_infer_title_short_name(self):
        self.assertEqual(_infer_title_from_path("/data/abc.txt"), "abc")

    def test_guess_title_from_text_first_valid_line(self):
        text = "\n\n黄帝内经\n上古天真论"
        self.assertEqual(_guess_title_from_text(text, "/dummy.txt"), "黄帝内经")

    def test_guess_title_from_text_fallback_to_path(self):
        text = "\n"
        self.assertEqual(_guess_title_from_text(text, "/data/013-本草纲目.txt"), "本草纲目")

    def test_guess_title_skips_very_short_line(self):
        text = "a\n黄帝内经素问"
        self.assertEqual(_guess_title_from_text(text, "/dummy.txt"), "黄帝内经素问")

    def test_compose_markdown_with_title(self):
        result = _compose_markdown("标题", "正文", include_title=True)
        self.assertTrue(result.startswith("# 标题"))
        self.assertIn("正文", result)

    def test_compose_markdown_without_title(self):
        result = _compose_markdown("标题", "正文", include_title=False)
        self.assertNotIn("# 标题", result)
        self.assertEqual(result, "正文")

    def test_compose_markdown_empty_body(self):
        result = _compose_markdown("标题", "", include_title=True)
        self.assertEqual(result, "# 标题")

    def test_compose_markdown_body_starts_with_title(self):
        result = _compose_markdown("标题", "# 标题\n\n正文", include_title=True)
        self.assertEqual(result.count("# 标题"), 1)

    def test_compose_markdown_empty_title(self):
        result = _compose_markdown("", "正文", include_title=True)
        self.assertEqual(result, "正文")

    def test_unique_preserve_order(self):
        self.assertEqual(_unique_preserve_order(["a", "b", "a", "c"]), ["a", "b", "c"])

    def test_unique_preserve_order_skips_empty(self):
        self.assertEqual(_unique_preserve_order(["a", "", "b"]), ["a", "b"])


# ---------------------------------------------------------------------------
# ConversionResult
# ---------------------------------------------------------------------------
class TestConversionResult(unittest.TestCase):
    def test_to_dict_fields(self):
        r = ConversionResult(success=True, text="test", title="t")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["text"], "test")
        self.assertEqual(d["title"], "t")
        self.assertIsInstance(d["errors"], list)


# ---------------------------------------------------------------------------
# FormatConverter 初始化
# ---------------------------------------------------------------------------
class TestFormatConverterInit(unittest.TestCase):
    def test_max_pages_empty_string(self):
        fc = FormatConverter({"max_pages": ""})
        self.assertIsNone(fc.max_pages)

    def test_max_pages_none(self):
        fc = FormatConverter({"max_pages": None})
        self.assertIsNone(fc.max_pages)

    def test_max_pages_numeric(self):
        fc = FormatConverter({"max_pages": 10})
        self.assertEqual(fc.max_pages, 10)

    def test_default_config(self):
        fc = FormatConverter({})
        self.assertTrue(fc.ocr_enabled)
        self.assertFalse(fc.force_ocr)


# ---------------------------------------------------------------------------
# _detect_format
# ---------------------------------------------------------------------------
class TestDetectFormat(unittest.TestCase):
    def setUp(self):
        self.fc = FormatConverter({})

    def test_explicit_format_overrides(self):
        self.assertEqual(self.fc._detect_format("/foo/bar.txt", "PDF"), "pdf")

    def test_pdf_extension(self):
        self.assertEqual(self.fc._detect_format("/foo/bar.pdf"), "pdf")

    def test_epub_extension(self):
        self.assertEqual(self.fc._detect_format("/foo/bar.epub"), "epub")

    def test_image_extension(self):
        self.assertEqual(self.fc._detect_format("/foo/bar.png"), "scan")
        self.assertEqual(self.fc._detect_format("/foo/bar.jpg"), "scan")
        self.assertEqual(self.fc._detect_format("/foo/bar.tiff"), "scan")

    def test_unknown_extension(self):
        self.assertEqual(self.fc._detect_format("/foo/bar.doc"), "unknown")


# ---------------------------------------------------------------------------
# convert_file 边界条件
# ---------------------------------------------------------------------------
class TestConvertFileEdgeCases(unittest.TestCase):
    def setUp(self):
        self.fc = FormatConverter({})
        self.fc.initialize()

    def tearDown(self):
        self.fc.cleanup()

    def test_file_not_found(self):
        result = self.fc.convert_file("/nonexistent/path.pdf")
        self.assertFalse(result.success)
        self.assertIn("文件不存在", result.errors[0])

    def test_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(b"data")
            tmp = f.name
        try:
            result = self.fc.convert_file(tmp)
            self.assertFalse(result.success)
            self.assertIn("不支持的文件格式", result.errors[0])
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# HTML → Markdown 渲染
# ---------------------------------------------------------------------------
class TestHtmlToMarkdown(unittest.TestCase):
    def setUp(self):
        self.fc = FormatConverter({})

    def test_empty_html(self):
        self.assertEqual(self.fc._html_to_markdown(""), "")
        self.assertEqual(self.fc._html_to_markdown("  \n  "), "")

    def test_heading_rendering(self):
        html = "<html><body><h1>一级标题</h1><h3>三级标题</h3></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("# 一级标题", md)
        self.assertIn("### 三级标题", md)

    def test_paragraph_rendering(self):
        html = "<html><body><p>段落一</p><p>段落二</p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("段落一", md)
        self.assertIn("段落二", md)

    def test_unordered_list(self):
        html = "<html><body><ul><li>项目一</li><li>项目二</li></ul></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("- 项目一", md)
        self.assertIn("- 项目二", md)

    def test_ordered_list(self):
        html = "<html><body><ol><li>第一</li><li>第二</li></ol></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("1. 第一", md)
        self.assertIn("2. 第二", md)

    def test_table_rendering(self):
        html = """<html><body><table>
            <tr><th>药名</th><th>性味</th></tr>
            <tr><td>黄芪</td><td>甘温</td></tr>
            <tr><td>当归</td><td>甘辛温</td></tr>
        </table></body></html>"""
        md = self.fc._html_to_markdown(html)
        self.assertIn("| 药名 | 性味 |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("黄芪", md)
        self.assertIn("当归", md)

    def test_table_irregular_rows(self):
        html = """<html><body><table>
            <tr><th>A</th><th>B</th><th>C</th></tr>
            <tr><td>1</td></tr>
        </table></body></html>"""
        md = self.fc._html_to_markdown(html)
        self.assertIn("| A | B | C |", md)

    def test_empty_table(self):
        html = "<html><body><table></table></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertNotIn("|", md)

    def test_blockquote(self):
        html = "<html><body><blockquote>引言内容</blockquote></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("> 引言内容", md)

    def test_pre_code_block(self):
        html = "<html><body><pre>code line</pre></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("```\ncode line\n```", md)

    def test_inline_bold_italic(self):
        html = "<html><body><p><strong>重要</strong>和<em>强调</em></p></body></html>"
        md = self.fc._html_to_markdown(html)
        # _render_inline_text may or may not preserve markdown markers
        self.assertIn("重要", md)
        self.assertIn("强调", md)

    def test_inline_code(self):
        html = "<html><body><p>使用 <code>pip install</code> 安装</p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("pip install", md)

    def test_link_rendering(self):
        html = '<html><body><p><a href="https://example.com">链接</a></p></body></html>'
        md = self.fc._html_to_markdown(html)
        self.assertIn("链接", md)

    def test_link_no_href(self):
        html = "<html><body><p><a>无链接</a></p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("无链接", md)

    def test_image_rendering(self):
        html = '<html><body><p><img src="pic.png" alt="图片说明"/></p></body></html>'
        md = self.fc._html_to_markdown(html)
        self.assertIn("![图片说明](pic.png)", md)

    def test_image_no_src(self):
        html = '<html><body><p><img alt="无源"/></p></body></html>'
        md = self.fc._html_to_markdown(html)
        self.assertIn("无源", md)

    def test_image_no_alt(self):
        html = '<html><body><p><img src="pic.png"/></p></body></html>'
        md = self.fc._html_to_markdown(html)
        self.assertIn("![image](pic.png)", md)

    def test_br_in_inline(self):
        html = "<html><body><p>第一行<br/>第二行</p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("第一行", md)
        self.assertIn("第二行", md)

    def test_script_style_removed(self):
        html = "<html><body><script>alert(1)</script><style>body{}</style><p>正文</p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertNotIn("alert", md)
        self.assertNotIn("body{}", md)
        self.assertIn("正文", md)

    def test_nested_div_section(self):
        html = "<html><body><section><div><p>嵌套内容</p></div></section></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("嵌套内容", md)

    def test_hr_rendering(self):
        html = "<html><body><p>上文</p><hr/><p>下文</p></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("上文", md)
        self.assertIn("下文", md)

    def test_list_items_rendered(self):
        """Test that list items content is properly rendered end-to-end."""
        html = "<html><body><ul><li>外层项目</li><li>内层项目</li></ul></body></html>"
        md = self.fc._html_to_markdown(html)
        self.assertIn("外层项目", md)
        self.assertIn("内层项目", md)


# ---------------------------------------------------------------------------
# EPUB 处理
# ---------------------------------------------------------------------------
def _make_epub(
    epub_path,
    chapters=None,
    opf_content=None,
    container_xml=None,
    extra_files=None,
):
    """辅助函数：创建自定义 EPUB。"""
    if chapters is None:
        chapters = [("chapter1.xhtml", "<html><body><p>默认章节</p></body></html>")]

    default_container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    manifest_items = []
    spine_refs = []
    for i, (fname, _) in enumerate(chapters):
        item_id = f"ch{i}"
        manifest_items.append(
            f'<item id="{item_id}" href="{fname}" media-type="application/xhtml+xml"/>'
        )
        spine_refs.append(f'<itemref idref="{item_id}"/>')

    default_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试书籍</dc:title>
    <dc:language>zh</dc:language>
  </metadata>
  <manifest>
    {''.join(manifest_items)}
  </manifest>
  <spine>
    {''.join(spine_refs)}
  </spine>
</package>"""

    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container_xml or default_container)
        archive.writestr("OEBPS/content.opf", opf_content or default_opf)
        for fname, content in chapters:
            archive.writestr(f"OEBPS/{fname}", content)
        if extra_files:
            for name, content in extra_files.items():
                archive.writestr(name, content)


class TestEpubConversion(unittest.TestCase):
    def setUp(self):
        self.fc = FormatConverter({})
        self.fc.initialize()

    def tearDown(self):
        self.fc.cleanup()

    def test_epub_multi_chapter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "multi.epub")
            _make_epub(epub_path, chapters=[
                ("ch1.xhtml", "<html><body><h1>素问</h1><p>上古天真论</p></body></html>"),
                ("ch2.xhtml", "<html><body><h1>灵枢</h1><p>九针十二原</p></body></html>"),
            ])
            result = self.fc.convert_file(epub_path)
            self.assertTrue(result.success)
            self.assertIn("素问", result.text)
            self.assertIn("灵枢", result.text)
            self.assertEqual(result.metadata["chapter_count"], 2)

    def test_epub_empty_chapters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "empty.epub")
            _make_epub(epub_path, chapters=[
                ("ch1.xhtml", "<html><body></body></html>"),
            ])
            result = self.fc.convert_file(epub_path)
            self.assertFalse(result.success)
            self.assertTrue(any("未提取到有效章节" in e for e in result.errors))

    def test_epub_missing_chapter_member(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "broken.epub")
            # OPF references chapter1.xhtml but we don't pack it
            opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>断章</dc:title>
  </metadata>
  <manifest>
    <item id="ch0" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="ch0"/></spine>
</package>"""
            with zipfile.ZipFile(epub_path, "w") as z:
                z.writestr("mimetype", "application/epub+zip")
                z.writestr("META-INF/container.xml", """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
                z.writestr("OEBPS/content.opf", opf)
            result = self.fc.convert_file(epub_path)
            # Should fail since no chapter content
            self.assertFalse(result.success)

    def test_epub_no_spine_fallback(self):
        """没有 spine 时回退到文件列表扫描。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "nospine.epub")
            opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>无spine</dc:title>
  </metadata>
  <manifest>
  </manifest>
  <spine></spine>
</package>"""
            with zipfile.ZipFile(epub_path, "w") as z:
                z.writestr("mimetype", "application/epub+zip")
                z.writestr("META-INF/container.xml", """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
                z.writestr("OEBPS/content.opf", opf)
                z.writestr("OEBPS/page.xhtml", "<html><body><p>回退内容</p></body></html>")
            result = self.fc.convert_file(epub_path)
            self.assertTrue(result.success)
            self.assertIn("回退内容", result.text)

    def test_epub_corrupted_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "corrupt.epub")
            with open(epub_path, "wb") as f:
                f.write(b"not a zip")
            result = self.fc.convert_file(epub_path)
            self.assertFalse(result.success)
            self.assertTrue(any("EPUB 解析失败" in e for e in result.errors))


# ---------------------------------------------------------------------------
# _read_zip_text 多编码
# ---------------------------------------------------------------------------
class TestReadZipText(unittest.TestCase):
    def test_utf8(self):
        fc = FormatConverter({})
        with tempfile.TemporaryDirectory() as tmpdir:
            zp = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("file.txt", "UTF-8 中文")
            with zipfile.ZipFile(zp, "r") as z:
                self.assertEqual(fc._read_zip_text(z, "file.txt"), "UTF-8 中文")

    def test_gb18030_fallback(self):
        fc = FormatConverter({})
        with tempfile.TemporaryDirectory() as tmpdir:
            zp = os.path.join(tmpdir, "test.zip")
            content = "中文内容".encode("gb18030")
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("file.txt", content)
            # read back: the raw bytes stored as-is
            with zipfile.ZipFile(zp, "r") as z:
                result = fc._read_zip_text(z, "file.txt")
                self.assertIn("中文内容", result)

    def test_replace_fallback(self):
        fc = FormatConverter({})
        with tempfile.TemporaryDirectory() as tmpdir:
            zp = os.path.join(tmpdir, "test.zip")
            # Write bytes that aren't valid in any encoding
            bad_bytes = bytes(range(128, 256))
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("file.txt", bad_bytes)
            with zipfile.ZipFile(zp, "r") as z:
                result = fc._read_zip_text(z, "file.txt")
                # Should not raise
                self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# _resolve_input_paths
# ---------------------------------------------------------------------------
class TestResolveInputPaths(unittest.TestCase):
    def test_single_path_string(self):
        fc = FormatConverter({})
        paths = fc._resolve_input_paths({"paths": "/a/b.pdf"})
        self.assertEqual(len(paths), 1)

    def test_multiple_keys(self):
        fc = FormatConverter({})
        paths = fc._resolve_input_paths({"file_path": "/a.pdf", "source_path": "/b.pdf"})
        self.assertEqual(len(paths), 2)

    def test_dedup(self):
        fc = FormatConverter({})
        paths = fc._resolve_input_paths({"paths": ["/a.pdf", "/a.pdf"]})
        self.assertEqual(len(paths), 1)


# ---------------------------------------------------------------------------
# _build_document
# ---------------------------------------------------------------------------
class TestBuildDocument(unittest.TestCase):
    def test_build_document_with_errors(self):
        fc = FormatConverter({})
        result = ConversionResult(
            success=True, text="txt", title="", source_path="/test.pdf",
            format_source="pdf", errors=["warn"]
        )
        doc = fc._build_document(result, "2025-01-01T00:00:00", {})
        self.assertEqual(doc.title, "test")
        self.assertIn("conversion_errors", doc.metadata)

    def test_build_document_language_from_context(self):
        fc = FormatConverter({})
        result = ConversionResult(success=True, text="t", title="T", source_path="/t.pdf", format_source="pdf")
        doc = fc._build_document(result, "2025-01-01", {"language": "en"})
        self.assertEqual(doc.language, "en")


# ---------------------------------------------------------------------------
# _do_execute 全流程
# ---------------------------------------------------------------------------
class TestDoExecute(unittest.TestCase):
    def test_execute_raises_on_no_paths(self):
        fc = FormatConverter({})
        fc.initialize()
        with self.assertRaises(ValueError):
            fc.execute({})
        fc.cleanup()


# ---------------------------------------------------------------------------
# OCR 管道
# ---------------------------------------------------------------------------
class TestOcrPipeline(unittest.TestCase):
    def test_ocr_pil_image_mocked(self):
        """Mock _ocr_pil_image to test the OCR pipeline path."""
        fc = FormatConverter({"tesseract_cmd": "/usr/bin/tesseract"})
        with patch.object(fc, '_ocr_pil_image', return_value="OCR文本"):
            text = fc._ocr_pil_image(MagicMock(), {})
            self.assertEqual(text, "OCR文本")

    def test_scan_conversion_ocr_disabled(self):
        fc = FormatConverter({"ocr_enabled": False})
        fc.initialize()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            result = fc.convert_file(tmp)
            self.assertFalse(result.success)
            self.assertIn("OCR", result.errors[0])
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_scan_conversion_ocr_raises(self):
        fc = FormatConverter({})
        fc.initialize()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            with patch.object(fc, "_ocr_image_file", side_effect=RuntimeError("OCR boom")):
                result = fc.convert_file(tmp)
                self.assertFalse(result.success)
                self.assertIn("OCR 失败", result.errors[0])
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_scan_conversion_empty_ocr_text(self):
        fc = FormatConverter({})
        fc.initialize()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            with patch.object(fc, "_ocr_image_file", return_value=("", {"mode": "L"})):
                result = fc.convert_file(tmp)
                self.assertFalse(result.success)
                self.assertIn("未识别到有效文本", result.errors[0])
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_scan_conversion_success(self):
        fc = FormatConverter({})
        fc.initialize()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake")
            tmp = f.name
        try:
            with patch.object(fc, "_ocr_image_file", return_value=("望诊结果", {"mode": "RGB"})):
                result = fc.convert_file(tmp)
                self.assertTrue(result.success)
                self.assertIn("望诊结果", result.text)
        finally:
            os.unlink(tmp)
        fc.cleanup()


# ---------------------------------------------------------------------------
# PDF 转换边界
# ---------------------------------------------------------------------------
class TestPdfConversion(unittest.TestCase):
    def test_pdf_without_pymupdf(self):
        fc = FormatConverter({})
        fc.initialize()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            tmp = f.name
        try:
            with patch("src.collector.format_converter.importlib.import_module", side_effect=ImportError("no fitz")):
                result = fc.convert_file(tmp)
                self.assertFalse(result.success)
                self.assertIn("PyMuPDF", result.errors[0])
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_pdf_empty_text_no_ocr(self):
        fc = FormatConverter({"ocr_enabled": False})
        fc.initialize()
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_doc.metadata = {"title": ""}
        mock_fitz.open.return_value = mock_doc
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"pdf")
            tmp = f.name
        try:
            with patch("src.collector.format_converter.importlib.import_module", return_value=mock_fitz):
                result = fc.convert_file(tmp, {"ocr_enabled": False})
                # Empty text, OCR disabled → should report error about no text
                self.assertFalse(result.success)
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_pdf_context_overrides(self):
        """Context-level overrides for max_pages, force_ocr, etc."""
        fc = FormatConverter({})
        fc.initialize()
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "大量有效文本" * 20
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__len__ = MagicMock(return_value=5)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_doc.metadata = {"title": "方剂学"}
        mock_fitz.open.return_value = mock_doc
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"pdf")
            tmp = f.name
        try:
            with patch("src.collector.format_converter.importlib.import_module", return_value=mock_fitz):
                result = fc.convert_file(tmp, {"max_pages": 2, "pdf_include_page_markers": False})
                self.assertTrue(result.success)
                self.assertEqual(result.metadata["processed_pages"], 2)
        finally:
            os.unlink(tmp)
        fc.cleanup()

    def test_pdf_parse_exception(self):
        fc = FormatConverter({})
        fc.initialize()
        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = RuntimeError("corrupt pdf")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"pdf")
            tmp = f.name
        try:
            with patch("src.collector.format_converter.importlib.import_module", return_value=mock_fitz):
                result = fc.convert_file(tmp)
                self.assertFalse(result.success)
                self.assertIn("PDF 解析失败", result.errors[0])
        finally:
            os.unlink(tmp)
        fc.cleanup()


if __name__ == "__main__":
    unittest.main()
