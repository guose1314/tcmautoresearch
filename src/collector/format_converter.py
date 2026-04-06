"""格式转换服务 — PDF/EPUB/扫描件解析、OCR 识别、统一为内部 Markdown。"""

from __future__ import annotations

import importlib
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence
from xml.etree import ElementTree as ET

from src.collector.corpus_bundle import (
    CorpusBundle,
    CorpusDocument,
    _make_bundle_id,
    _make_doc_id,
)
from src.core.module_base import BaseModule

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency fallback
    BeautifulSoup = None

logger = logging.getLogger(__name__)

_DEFAULT_OCR_LANGUAGE = "chi_sim+eng"
_DEFAULT_OCR_DPI = 200
_DEFAULT_PAGE_TEXT_THRESHOLD = 40
_SUPPORTED_IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_SUPPORTED_EPUB_ITEM_EXTENSIONS = {".html", ".htm", ".xhtml", ".xml"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_CONTAINER_TAGS = {"p", "div", "section", "article", "chapter", "body"}
_INLINE_BOLD_TAGS = {"strong", "b"}
_INLINE_ITALIC_TAGS = {"em", "i"}


@dataclass
class ConversionResult:
    """格式转换结果。"""

    success: bool
    text: str = ""
    format_source: str = ""
    title: str = ""
    source_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "format_source": self.format_source,
            "title": self.title,
            "source_path": self.source_path,
            "metadata": self.metadata,
            "errors": self.errors,
        }


class FormatConverter(BaseModule):
    """将 PDF、EPUB 和扫描件统一转换为内部 Markdown 文档。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("format_converter", config)
        self.ocr_enabled = bool(self.config.get("ocr_enabled", True))
        self.force_ocr = bool(self.config.get("force_ocr", False))
        self.ocr_language = str(self.config.get("ocr_language", _DEFAULT_OCR_LANGUAGE))
        self.ocr_dpi = int(self.config.get("ocr_dpi", _DEFAULT_OCR_DPI))
        self.ocr_config = str(self.config.get("ocr_config", "")).strip()
        self.tesseract_cmd = str(self.config.get("tesseract_cmd", "")).strip()
        self.pdf_text_threshold = int(
            self.config.get("pdf_text_threshold", _DEFAULT_PAGE_TEXT_THRESHOLD)
        )
        self.pdf_include_page_markers = bool(
            self.config.get("pdf_include_page_markers", True)
        )
        self.include_title_heading = bool(self.config.get("include_title_heading", True))
        self.default_language = str(self.config.get("default_language", "zh"))
        raw_max_pages = self.config.get("max_pages")
        self.max_pages = int(raw_max_pages) if raw_max_pages not in (None, "") else None

    def _do_initialize(self) -> bool:
        self.logger.info(
            "FormatConverter 初始化完成: ocr_enabled=%s, ocr_language=%s",
            self.ocr_enabled,
            self.ocr_language,
        )
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        file_paths = self._resolve_input_paths(context)
        if not file_paths:
            raise ValueError("FormatConverter 需要提供 file_path/source_path/path 或 paths")

        collected_at = datetime.now().isoformat()
        documents: List[CorpusDocument] = []
        errors: List[Dict[str, str]] = []

        for file_path in file_paths:
            result = self.convert_file(file_path, context)
            if not result.success:
                message = "; ".join(result.errors) or "转换失败"
                errors.append(
                    {
                        "source_ref": result.source_path or os.path.abspath(file_path),
                        "error": message,
                        "format_source": result.format_source or self._detect_format(file_path),
                    }
                )
                self.logger.warning("格式转换失败 '%s': %s", file_path, message)
                continue

            documents.append(self._build_document(result, collected_at, context))

        sources = _unique_preserve_order(doc.source_type for doc in documents)
        source_breakdown: Dict[str, int] = {}
        for doc in documents:
            source_breakdown[doc.source_type] = source_breakdown.get(doc.source_type, 0) + 1

        stats = {
            "total_documents": len(documents),
            "total_chars": sum(len(doc.text) for doc in documents),
            "converted_files": len(documents),
            "requested_files": len(file_paths),
            "failed_files": len(errors),
            "error_count": len(errors),
            "source_breakdown": source_breakdown,
            "output_format": "markdown",
        }
        bundle = CorpusBundle(
            bundle_id=_make_bundle_id(sources or ["format_converter"], collected_at),
            sources=sources,
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=errors,
        )
        return bundle.to_dict()

    def _do_cleanup(self) -> bool:
        return True

    def convert_file(
        self,
        file_path: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ConversionResult:
        """转换单个文件并返回结构化结果。"""
        exec_context = context or {}
        normalized_path = os.path.abspath(file_path)
        if not os.path.exists(normalized_path):
            return ConversionResult(
                success=False,
                format_source=self._detect_format(normalized_path),
                source_path=normalized_path,
                errors=[f"文件不存在: {normalized_path}"],
            )

        format_source = self._detect_format(normalized_path, exec_context.get("format"))
        if format_source == "pdf":
            return self._convert_pdf(normalized_path, exec_context)
        if format_source == "epub":
            return self._convert_epub(normalized_path)
        if format_source == "scan":
            return self._convert_scan_image(normalized_path, exec_context)

        return ConversionResult(
            success=False,
            format_source=format_source,
            source_path=normalized_path,
            errors=[f"不支持的文件格式: {os.path.splitext(normalized_path)[1] or 'unknown'}"],
        )

    def _build_document(
        self,
        result: ConversionResult,
        collected_at: str,
        context: Dict[str, Any],
    ) -> CorpusDocument:
        metadata = dict(result.metadata)
        metadata["format_source"] = result.format_source
        metadata["converted_to"] = "markdown"
        if result.errors:
            metadata["conversion_errors"] = list(result.errors)

        language = (
            context.get("language")
            or metadata.get("language")
            or self.default_language
        )
        return CorpusDocument(
            doc_id=_make_doc_id(result.format_source, result.source_path),
            title=result.title or _infer_title_from_path(result.source_path),
            text=result.text.strip(),
            source_type=result.format_source,
            source_ref=result.source_path,
            language=str(language),
            metadata=metadata,
            collected_at=collected_at,
        )

    def _resolve_input_paths(self, context: Dict[str, Any]) -> List[str]:
        raw_paths = context.get("paths") or context.get("input_paths") or []
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]

        candidates = list(raw_paths)
        for key in ("file_path", "source_path", "input_path", "path"):
            value = context.get(key)
            if value:
                candidates.append(value)

        normalized: List[str] = []
        seen = set()
        for item in candidates:
            absolute = os.path.abspath(str(item))
            if absolute in seen:
                continue
            seen.add(absolute)
            normalized.append(absolute)
        return normalized

    def _detect_format(self, file_path: str, explicit_format: Optional[str] = None) -> str:
        if explicit_format:
            return str(explicit_format).lower()

        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix == ".epub":
            return "epub"
        if suffix in _SUPPORTED_IMAGE_EXTENSIONS:
            return "scan"
        return "unknown"

    def _pdf_import_error_result(self, file_path: str) -> ConversionResult:
        return ConversionResult(
            success=False,
            format_source="pdf",
            source_path=file_path,
            errors=["缺少 PyMuPDF 依赖，请安装 pymupdf"],
        )

    def _resolve_pdf_options(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raw_max_pages = context.get("max_pages", self.max_pages)
        max_pages = int(raw_max_pages) if raw_max_pages not in (None, "") else None
        return {
            "max_pages": max_pages,
            "include_page_markers": bool(
                context.get("pdf_include_page_markers", self.pdf_include_page_markers)
            ),
            "force_ocr": bool(context.get("force_ocr", self.force_ocr)),
            "ocr_enabled": bool(context.get("ocr_enabled", self.ocr_enabled)),
            "page_text_threshold": int(
                context.get("pdf_text_threshold", self.pdf_text_threshold)
            ),
        }

    def _extract_pdf_page_content(
        self,
        page: Any,
        page_number: int,
        context: Dict[str, Any],
        pdf_options: Dict[str, Any],
    ) -> tuple[str, str, Optional[str], bool]:
        page_text = _normalize_whitespace(page.get_text("text"))
        if page_text and not pdf_options["force_ocr"] and _has_substantive_text(
            page_text,
            pdf_options["page_text_threshold"],
        ):
            return page_text, page_text, None, False

        if not pdf_options["ocr_enabled"]:
            return "", page_text, f"第 {page_number} 页未提取到文本，且 OCR 未启用", False

        try:
            content = self._ocr_pdf_page(page, context)
        except Exception as exc:  # pragma: no cover - exercised via failure fallback
            return "", page_text, f"第 {page_number} 页 OCR 失败: {exc}", False

        return content, page_text, None, bool(content)

    def _append_pdf_page_section(
        self,
        page_sections: List[str],
        content: str,
        page_number: int,
        pdf_options: Dict[str, Any],
        page_limit: int,
    ) -> None:
        if not content:
            return

        if pdf_options["include_page_markers"] and page_limit > 1:
            page_sections.append(f"## 第 {page_number} 页\n\n{content}")
            return

        page_sections.append(content)

    def _extract_pdf_body(
        self,
        document: Any,
        file_path: str,
        context: Dict[str, Any],
        pdf_options: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> tuple[str, str, List[str], List[int]]:
        page_sections: List[str] = []
        errors: List[str] = []
        used_ocr_pages: List[int] = []
        title = _normalize_whitespace((document.metadata or {}).get("title", ""))
        page_limit = len(document) if pdf_options["max_pages"] is None else min(len(document), pdf_options["max_pages"])
        metadata["processed_pages"] = page_limit

        for index in range(page_limit):
            page_number = index + 1
            content, page_text, error, used_ocr = self._extract_pdf_page_content(
                document[index],
                page_number,
                context,
                pdf_options,
            )
            if error:
                errors.append(error)
            if used_ocr:
                used_ocr_pages.append(page_number)
            if not title and page_text:
                title = _guess_title_from_text(page_text, file_path)
            self._append_pdf_page_section(page_sections, content, page_number, pdf_options, page_limit)

        body = "\n\n".join(section for section in page_sections if section).strip()
        return title, body, errors, used_ocr_pages

    def _build_pdf_empty_result(
        self,
        file_path: str,
        title: str,
        metadata: Dict[str, Any],
        errors: List[str],
        used_ocr_pages: List[int],
    ) -> ConversionResult:
        errors.append("PDF 未提取到有效文本，请检查是否为扫描件并确认 OCR 依赖可用")
        return ConversionResult(
            success=False,
            format_source="pdf",
            title=title or _infer_title_from_path(file_path),
            source_path=file_path,
            metadata={
                **metadata,
                "used_ocr_pages": used_ocr_pages,
                "language": self.default_language,
            },
            errors=errors,
        )

    def _build_pdf_success_result(
        self,
        file_path: str,
        title: str,
        body: str,
        metadata: Dict[str, Any],
        errors: List[str],
    ) -> ConversionResult:
        return ConversionResult(
            success=True,
            format_source="pdf",
            title=title or _infer_title_from_path(file_path),
            source_path=file_path,
            text=_compose_markdown(
                title or _infer_title_from_path(file_path),
                body,
                include_title=self.include_title_heading,
            ),
            metadata=metadata,
            errors=errors,
        )

    def _convert_pdf(self, file_path: str, context: Dict[str, Any]) -> ConversionResult:
        try:
            fitz = importlib.import_module("fitz")
        except ImportError:
            return self._pdf_import_error_result(file_path)

        pdf_options = self._resolve_pdf_options(context)
        metadata: Dict[str, Any] = {
            "file_name": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
            "extractor": "pymupdf",
        }

        try:
            with fitz.open(file_path) as document:
                metadata["page_count"] = len(document)
                title, body, errors, used_ocr_pages = self._extract_pdf_body(
                    document,
                    file_path,
                    context,
                    pdf_options,
                    metadata,
                )
        except Exception as exc:
            return ConversionResult(
                success=False,
                format_source="pdf",
                source_path=file_path,
                errors=[f"PDF 解析失败: {exc}"],
            )

        if not body:
            return self._build_pdf_empty_result(
                file_path,
                title,
                metadata,
                errors,
                used_ocr_pages,
            )

        metadata["used_ocr_pages"] = used_ocr_pages
        metadata["used_ocr"] = bool(used_ocr_pages)
        metadata["language"] = self.default_language
        return self._build_pdf_success_result(file_path, title, body, metadata, errors)

    def _convert_epub(self, file_path: str) -> ConversionResult:
        chapters: List[str] = []
        metadata: Dict[str, Any] = {
            "file_name": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
            "extractor": "epub-zip",
        }
        errors: List[str] = []

        try:
            with zipfile.ZipFile(file_path, "r") as archive:
                opf_path = self._find_epub_opf_path(archive)
                package_root = ET.fromstring(archive.read(opf_path))
                title = self._extract_epub_metadata(package_root, "title") or _infer_title_from_path(file_path)
                language = self._extract_epub_metadata(package_root, "language") or self.default_language
                creator = self._extract_epub_metadata(package_root, "creator")
                ordered_members = self._resolve_epub_content_members(archive, opf_path, package_root)

                for member in ordered_members:
                    try:
                        chapter_html = self._read_zip_text(archive, member)
                    except KeyError:
                        errors.append(f"EPUB 章节缺失: {member}")
                        continue

                    chapter_markdown = self._html_to_markdown(chapter_html)
                    if chapter_markdown:
                        chapters.append(chapter_markdown)

                body = "\n\n---\n\n".join(chapters).strip()
                metadata.update(
                    {
                        "chapter_count": len(chapters),
                        "opf_path": opf_path,
                        "creator": creator,
                        "language": language,
                    }
                )

                if not body:
                    errors.append("EPUB 未提取到有效章节内容")
                    return ConversionResult(
                        success=False,
                        format_source="epub",
                        title=title,
                        source_path=file_path,
                        metadata=metadata,
                        errors=errors,
                    )

                return ConversionResult(
                    success=True,
                    format_source="epub",
                    title=title,
                    source_path=file_path,
                    text=_compose_markdown(
                        title,
                        body,
                        include_title=self.include_title_heading,
                    ),
                    metadata=metadata,
                    errors=errors,
                )
        except Exception as exc:
            return ConversionResult(
                success=False,
                format_source="epub",
                title=_infer_title_from_path(file_path),
                source_path=file_path,
                metadata=metadata,
                errors=[f"EPUB 解析失败: {exc}"],
            )

    def _convert_scan_image(
        self,
        file_path: str,
        context: Dict[str, Any],
    ) -> ConversionResult:
        if not bool(context.get("ocr_enabled", self.ocr_enabled)):
            return ConversionResult(
                success=False,
                format_source="scan",
                title=_infer_title_from_path(file_path),
                source_path=file_path,
                errors=["扫描件识别依赖 OCR，请启用 ocr_enabled"],
            )

        try:
            text, metadata = self._ocr_image_file(file_path, context)
        except Exception as exc:
            return ConversionResult(
                success=False,
                format_source="scan",
                title=_infer_title_from_path(file_path),
                source_path=file_path,
                errors=[f"扫描件 OCR 失败: {exc}"],
            )

        if not text.strip():
            return ConversionResult(
                success=False,
                format_source="scan",
                title=_infer_title_from_path(file_path),
                source_path=file_path,
                metadata=metadata,
                errors=["扫描件 OCR 未识别到有效文本"],
            )

        metadata.setdefault("language", self.default_language)
        metadata["ocr_enabled"] = True
        metadata.setdefault("file_name", os.path.basename(file_path))
        metadata.setdefault("file_size", os.path.getsize(file_path))
        return ConversionResult(
            success=True,
            format_source="scan",
            title=_infer_title_from_path(file_path),
            source_path=file_path,
            text=_compose_markdown(
                _infer_title_from_path(file_path),
                _normalize_whitespace(text),
                include_title=self.include_title_heading,
            ),
            metadata=metadata,
        )

    def _ocr_pdf_page(self, page: Any, context: Dict[str, Any]) -> str:
        try:
            fitz = importlib.import_module("fitz")
            from PIL import Image
        except ImportError as exc:
            raise ImportError("PDF OCR 需要同时安装 pymupdf 和 Pillow") from exc

        matrix = fitz.Matrix(self.ocr_dpi / 72.0, self.ocr_dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "RGB" if pixmap.n < 4 else "RGBA"
        image = Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
        return self._ocr_pil_image(image, context)

    def _ocr_image_file(
        self,
        file_path: str,
        context: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise ImportError("扫描件 OCR 需要安装 Pillow") from exc

        with Image.open(file_path) as image:
            metadata = {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "language": self.default_language,
            }
            return self._ocr_pil_image(image, context), metadata

    def _ocr_pil_image(self, image: Any, context: Dict[str, Any]) -> str:
        try:
            pytesseract = importlib.import_module("pytesseract")
            from PIL import ImageOps
        except ImportError as exc:
            raise ImportError("OCR 需要安装 pytesseract 和 Pillow") from exc

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        prepared = ImageOps.autocontrast(image.convert("L"))
        ocr_language = str(context.get("ocr_language", self.ocr_language))
        extra_config = str(context.get("ocr_config", self.ocr_config)).strip()
        return _normalize_whitespace(
            pytesseract.image_to_string(prepared, lang=ocr_language, config=extra_config)
        )

    def _find_epub_opf_path(self, archive: zipfile.ZipFile) -> str:
        container_xml = archive.read("META-INF/container.xml")
        root = ET.fromstring(container_xml)
        for elem in root.iter():
            if elem.tag.endswith("rootfile"):
                full_path = elem.attrib.get("full-path")
                if full_path:
                    return full_path
        raise ValueError("EPUB 缺少 META-INF/container.xml rootfile 定义")

    def _extract_epub_metadata(self, package_root: ET.Element, field_name: str) -> str:
        for elem in package_root.iter():
            if elem.tag.endswith(field_name):
                return _normalize_whitespace("".join(elem.itertext()))
        return ""

    def _build_epub_manifest_members(
        self,
        package_root: ET.Element,
        opf_dir: PurePosixPath,
    ) -> tuple[Dict[str, str], List[str]]:
        manifest: Dict[str, str] = {}
        html_members: List[str] = []
        for elem in package_root.iter():
            if not elem.tag.endswith("item"):
                continue
            item_id = elem.attrib.get("id", "")
            href = elem.attrib.get("href", "")
            media_type = elem.attrib.get("media-type", "")
            if not href:
                continue
            member = str((opf_dir / PurePosixPath(href)).as_posix())
            manifest[item_id] = member
            if self._is_epub_html_member(href, media_type):
                html_members.append(member)
        return manifest, html_members

    def _is_epub_html_member(self, href: str, media_type: str) -> bool:
        return media_type in {"application/xhtml+xml", "text/html"} or Path(href).suffix.lower() in _SUPPORTED_EPUB_ITEM_EXTENSIONS

    def _resolve_epub_spine_members(
        self,
        package_root: ET.Element,
        manifest: Dict[str, str],
        html_members: List[str],
    ) -> List[str]:
        ordered: List[str] = []
        for elem in package_root.iter():
            if not elem.tag.endswith("itemref"):
                continue
            member = manifest.get(elem.attrib.get("idref", ""))
            if member and member in html_members and member not in ordered:
                ordered.append(member)
        return ordered

    def _append_missing_epub_members(
        self,
        ordered: List[str],
        html_members: List[str],
    ) -> None:
        for member in html_members:
            if member not in ordered:
                ordered.append(member)

    def _fallback_epub_members(self, archive: zipfile.ZipFile) -> List[str]:
        fallback: List[str] = []
        for name in archive.namelist():
            if Path(name).suffix.lower() in _SUPPORTED_EPUB_ITEM_EXTENSIONS:
                fallback.append(name)
        return sorted(fallback)

    def _resolve_epub_content_members(
        self,
        archive: zipfile.ZipFile,
        opf_path: str,
        package_root: ET.Element,
    ) -> List[str]:
        opf_dir = PurePosixPath(opf_path).parent
        manifest, html_members = self._build_epub_manifest_members(package_root, opf_dir)
        ordered = self._resolve_epub_spine_members(package_root, manifest, html_members)
        self._append_missing_epub_members(ordered, html_members)

        if ordered:
            return ordered
        return self._fallback_epub_members(archive)

    def _read_zip_text(self, archive: zipfile.ZipFile, member: str) -> str:
        raw = archive.read(member)
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _html_to_markdown(self, html: str) -> str:
        if not html.strip():
            return ""

        if BeautifulSoup is None:  # pragma: no cover - fallback path only
            return _normalize_whitespace(re.sub(r"<[^>]+>", " ", html))

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()

        body = soup.body or soup
        blocks = self._render_block_nodes(list(body.children), list_level=0)
        text = "\n\n".join(block for block in blocks if block).strip()
        return re.sub(r"\n{3,}", "\n\n", text)

    def _render_block_node(self, node: Any, list_level: int) -> Any:
        if getattr(node, "name", None) is None:
            return _normalize_whitespace(str(node))

        name = node.name.lower()
        if name in _HEADING_TAGS:
            return self._render_heading_block(node)
        if name in {"ul", "ol"}:
            return self._render_list(node, ordered=(name == "ol"), list_level=list_level + 1)
        if name == "blockquote":
            return self._render_blockquote(node)
        if name == "pre":
            return self._render_preformatted_block(node)
        if name == "table":
            return self._render_table(node)
        if name in _CONTAINER_TAGS:
            return self._render_container_block(node, list_level)
        return self._render_inline_text(node)

    def _render_heading_block(self, node: Any) -> str:
        heading = self._render_inline_text(node)
        if not heading:
            return ""
        return f"{'#' * int(node.name[1])} {heading}"

    def _render_blockquote(self, node: Any) -> str:
        quote = self._render_inline_text(node)
        if not quote:
            return ""
        return "\n".join(f"> {line}" for line in quote.splitlines())

    def _render_preformatted_block(self, node: Any) -> str:
        code = node.get_text("\n", strip=True)
        if not code:
            return ""
        return f"```\n{code}\n```"

    def _render_container_block(self, node: Any, list_level: int) -> Any:
        nested_blocks = self._render_block_nodes(list(node.children), list_level=list_level)
        if nested_blocks:
            return nested_blocks
        return self._render_inline_text(node)

    def _render_block_nodes(self, nodes: Sequence[Any], list_level: int) -> List[str]:
        blocks: List[str] = []
        for node in nodes:
            rendered = self._render_block_node(node, list_level)
            if isinstance(rendered, list):
                blocks.extend(rendered)
                continue
            if rendered:
                blocks.append(rendered)
        return [block for block in blocks if block.strip()]

    def _render_list(self, node: Any, ordered: bool, list_level: int) -> List[str]:
        rendered: List[str] = []
        index = 1
        indent = "  " * max(list_level - 1, 0)

        for child in node.children:
            if getattr(child, "name", "").lower() != "li":
                continue
            item_text = self._render_inline_text(child)
            if not item_text:
                continue
            prefix = f"{index}. " if ordered else "- "
            rendered.append(f"{indent}{prefix}{item_text}")
            index += 1

        return rendered

    def _render_table(self, node: Any) -> str:
        rows: List[List[str]] = []
        for row in node.find_all("tr"):
            cells = [self._render_inline_text(cell) for cell in row.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        header = rows[0]
        divider = ["---"] * len(header)
        lines = [f"| {' | '.join(header)} |", f"| {' | '.join(divider)} |"]
        for row in rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            lines.append(f"| {' | '.join(padded[:len(header)])} |")
        return "\n".join(lines)

    def _render_inline_child(self, child: Any) -> Optional[str]:
        if getattr(child, "name", None) is None:
            return str(child)

        name = child.name.lower()
        if name == "br":
            return "\n"

        content = self._render_inline_text(child)
        if not content and name != "img":
            return None

        if name in _INLINE_BOLD_TAGS:
            return f"**{content}**"
        if name in _INLINE_ITALIC_TAGS:
            return f"*{content}*"
        if name == "code":
            return f"`{content}`"
        if name == "a":
            return self._render_inline_anchor(child, content)
        if name == "img":
            return self._render_inline_image(child)
        return content

    def _render_inline_anchor(self, child: Any, content: str) -> str:
        href = child.get("href", "").strip()
        label = content or href
        return f"[{label}]({href})" if href else label

    def _render_inline_image(self, child: Any) -> str:
        alt = child.get("alt", "image").strip() or "image"
        src = child.get("src", "").strip()
        return f"![{alt}]({src})" if src else alt

    def _render_inline_text(self, node: Any) -> str:
        if getattr(node, "name", None) is None:
            return _normalize_whitespace(str(node))

        parts: List[str] = []
        for child in node.children:
            rendered = self._render_inline_child(child)
            if rendered is not None:
                parts.append(rendered)

        return _normalize_whitespace("".join(parts))


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_whitespace(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _has_substantive_text(text: str, threshold: int) -> bool:
    content = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text)
    return len(content) >= threshold


def _infer_title_from_path(file_path: str) -> str:
    name = os.path.splitext(os.path.basename(file_path))[0]
    if len(name) > 4 and name[:3].isdigit() and name[3] == "-":
        return name[4:]
    return name


def _guess_title_from_text(text: str, file_path: str) -> str:
    for line in text.splitlines()[:10]:
        candidate = _normalize_whitespace(line)
        if 2 <= len(candidate) <= 120:
            return candidate
    return _infer_title_from_path(file_path)


def _compose_markdown(title: str, body: str, include_title: bool) -> str:
    normalized_body = body.strip()
    if not include_title or not title:
        return normalized_body
    title_heading = f"# {title}"
    if normalized_body.startswith(title_heading):
        return normalized_body
    if not normalized_body:
        return title_heading
    return f"{title_heading}\n\n{normalized_body}"
