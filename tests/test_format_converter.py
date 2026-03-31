import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from src.collector import FormatConverter

try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency for local env
    fitz = None


def _create_minimal_epub(epub_path: str) -> None:
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>黄帝内经</dc:title>
    <dc:creator>佚名</dc:creator>
    <dc:language>zh</dc:language>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
  </spine>
</package>
""",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>第一章</h1>
    <p>上古天真论。</p>
  </body>
</html>
""",
        )


@unittest.skipIf(fitz is None, "PyMuPDF 未安装")
class TestFormatConverterPdf(unittest.TestCase):
    def setUp(self):
        self.converter = FormatConverter({"pdf_include_page_markers": True})
        self.assertTrue(self.converter.initialize())

    def tearDown(self):
        self.converter.cleanup()

    def test_convert_pdf_to_markdown_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "shanghan.pdf")
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "伤寒论\n辨太阳病脉证并治")
            page2 = document.new_page()
            page2.insert_text((72, 72), "桂枝汤主之。")
            document.save(pdf_path)
            document.close()

            result = self.converter.execute({"file_path": pdf_path})

            self.assertEqual(result["sources"], ["pdf"])
            self.assertEqual(result["stats"]["total_documents"], 1)
            doc = result["documents"][0]
            self.assertEqual(doc["source_type"], "pdf")
            self.assertIn("# 伤寒论", doc["text"])
            self.assertIn("## 第 1 页", doc["text"])
            self.assertIn("桂枝汤主之", doc["text"])


class TestFormatConverterEpub(unittest.TestCase):
    def setUp(self):
        self.converter = FormatConverter({})
        self.assertTrue(self.converter.initialize())

    def tearDown(self):
        self.converter.cleanup()

    def test_convert_epub_to_markdown_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "huangdi.epub")
            _create_minimal_epub(epub_path)

            result = self.converter.execute({"file_path": epub_path})

            self.assertEqual(result["sources"], ["epub"])
            self.assertEqual(result["stats"]["total_documents"], 1)
            doc = result["documents"][0]
            self.assertEqual(doc["source_type"], "epub")
            self.assertEqual(doc["title"], "黄帝内经")
            self.assertIn("# 黄帝内经", doc["text"])
            self.assertIn("# 第一章", doc["text"])
            self.assertIn("上古天真论", doc["text"])

    def test_batch_conversion_keeps_partial_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            epub_path = os.path.join(tmpdir, "huangdi.epub")
            _create_minimal_epub(epub_path)
            missing_path = os.path.join(tmpdir, "missing.pdf")

            result = self.converter.execute({"paths": [epub_path, missing_path]})

            self.assertEqual(result["stats"]["total_documents"], 1)
            self.assertEqual(result["stats"]["error_count"], 1)
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("文件不存在", result["errors"][0]["error"])


class TestFormatConverterScan(unittest.TestCase):
    def setUp(self):
        self.converter = FormatConverter({})
        self.assertTrue(self.converter.initialize())

    def tearDown(self):
        self.converter.cleanup()

    def test_convert_scan_uses_ocr_pipeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scan_path = os.path.join(tmpdir, "tongue.png")
            with open(scan_path, "wb") as handle:
                handle.write(b"placeholder")

            with patch.object(
                FormatConverter,
                "_ocr_image_file",
                return_value=("望闻问切", {"width": 32, "height": 32, "mode": "RGB"}),
            ):
                result = self.converter.execute({"file_path": scan_path})

            self.assertEqual(result["sources"], ["scan"])
            doc = result["documents"][0]
            self.assertEqual(doc["source_type"], "scan")
            self.assertIn("望闻问切", doc["text"])


if __name__ == "__main__":
    unittest.main()