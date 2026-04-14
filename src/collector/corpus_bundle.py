"""统一语料 Bundle 模块 — 2.5 多来源 CorpusBundle

将 CText / Local 文件 / PDF 三类来源的原始采集结果
规范化到同一 CorpusDocument / CorpusBundle schema。

新旧格式并行：
  * CorpusBundle.to_dict() 输出带 schema_version="1.0" 的新格式
  * is_corpus_bundle() 判别函数让下游（_extract_corpus_text_entries 等）
    可同时处理旧 CText dict 和新 CorpusBundle dict，互不干扰。
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Schema version — 判别新旧格式的唯一标识
# ─────────────────────────────────────────────────────────────────────────────
BUNDLE_SCHEMA_VERSION = "1.0"
_DYNASTY_LIST = (
    "先秦|秦|西汉|东汉|汉|三国|魏|晋|西晋|东晋|南北朝|南朝|北朝|隋|唐|五代|五代十国|"
    "北宋|南宋|宋|辽|金|元|明|清|民国|近代|现代|当代"
)
_RE_FILENAME_VERSION_META = re.compile(
    rf"^(?:(\d{{3}})-)?(.+?)[-—–]({_DYNASTY_LIST})[-—–](.+?)(?:\.[^.]+)?$"
)
_LINEAGE_NORMALIZE_RE = re.compile(r"[\s《》\[\]【】()（）:：\-_.、，,.;；/\\]+")


def build_document_version_metadata(
    title: str,
    source_type: str,
    source_ref: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """补全文档级显式版本元数据。"""
    enriched_metadata = dict(metadata or {})
    existing_version_metadata = enriched_metadata.get("version_metadata")
    version_metadata = dict(existing_version_metadata) if isinstance(existing_version_metadata, dict) else {}

    filename_title, filename_dynasty, filename_author = _infer_filename_version_fields(source_ref or title)
    authors = enriched_metadata.get("authors")
    primary_author = ""
    if isinstance(authors, list) and authors:
        primary_author = str(authors[0] or "").strip()

    work_title = _first_nonempty(
        version_metadata.get("work_title"),
        enriched_metadata.get("work_title"),
        enriched_metadata.get("root_title"),
        filename_title,
        title,
    )
    work_title = str(work_title or "").strip()
    fragment_title = _first_nonempty(
        version_metadata.get("fragment_title"),
        enriched_metadata.get("fragment_title"),
        enriched_metadata.get("section_title"),
        work_title,
    )
    fragment_title = str(fragment_title or work_title).strip()

    work_key = _first_nonempty(
        version_metadata.get("work_key"),
        enriched_metadata.get("work_key"),
    )
    work_key = str(work_key or _normalize_lineage_token(work_title)).strip()

    fragment_key = _first_nonempty(
        version_metadata.get("fragment_key"),
        enriched_metadata.get("fragment_key"),
    )
    fragment_key = str(fragment_key or _normalize_lineage_token(fragment_title or work_title)).strip() or work_key

    work_fragment_key = _first_nonempty(
        version_metadata.get("work_fragment_key"),
        enriched_metadata.get("work_fragment_key"),
    )
    work_fragment_key = str(work_fragment_key or _build_work_fragment_key(work_key, fragment_key)).strip()

    dynasty = _first_nonempty(
        version_metadata.get("dynasty"),
        enriched_metadata.get("dynasty"),
        enriched_metadata.get("era"),
        enriched_metadata.get("period"),
        filename_dynasty,
    )
    author = _first_nonempty(
        version_metadata.get("author"),
        enriched_metadata.get("author"),
        enriched_metadata.get("creator"),
        enriched_metadata.get("creator_name"),
        primary_author,
        filename_author,
    )
    edition = _first_nonempty(
        version_metadata.get("edition"),
        enriched_metadata.get("edition"),
        enriched_metadata.get("version"),
        enriched_metadata.get("print_edition"),
        enriched_metadata.get("witness_label"),
        enriched_metadata.get("source_edition"),
    )
    catalog_id = _first_nonempty(
        version_metadata.get("catalog_id"),
        enriched_metadata.get("catalog_id"),
        enriched_metadata.get("source_catalog_id"),
        enriched_metadata.get("catalog_ref"),
    )
    if not catalog_id:
        catalog_id = source_ref
    source_name = _first_nonempty(
        version_metadata.get("source_name"),
        enriched_metadata.get("source_name"),
        enriched_metadata.get("source"),
        source_type,
    )

    version_lineage_key = _first_nonempty(
        version_metadata.get("version_lineage_key"),
        enriched_metadata.get("version_lineage_key"),
        enriched_metadata.get("lineage_key"),
        enriched_metadata.get("version_family"),
    )
    if not version_lineage_key:
        version_lineage_key = _build_version_lineage_key(work_fragment_key, dynasty, author, edition)

    witness_key = _first_nonempty(
        version_metadata.get("witness_key"),
        enriched_metadata.get("witness_key"),
        enriched_metadata.get("witness_id"),
    )
    witness_namespace = str(catalog_id or source_type or "").strip() or str(source_type or "").strip()
    witness_key = str(witness_key or f"{witness_namespace}:{source_ref or work_fragment_key}").strip()

    lineage_source = version_metadata.get("lineage_source")
    if not lineage_source:
        if existing_version_metadata or any(
            enriched_metadata.get(key)
            for key in ("version_lineage_key", "lineage_key", "version_family", "work_key", "fragment_key", "edition")
        ):
            lineage_source = "explicit_metadata"
        elif filename_title or filename_dynasty or filename_author:
            lineage_source = "filename_inference"
        elif enriched_metadata.get("root_title") or enriched_metadata.get("root_urn"):
            lineage_source = "root_context"
        else:
            lineage_source = "title_fallback"

    version_metadata = {
        **version_metadata,
        "work_title": work_title,
        "work_key": work_key,
        "fragment_title": fragment_title,
        "fragment_key": fragment_key,
        "work_fragment_key": work_fragment_key,
        "version_lineage_key": str(version_lineage_key),
        "dynasty": str(dynasty or "").strip(),
        "author": str(author or "").strip(),
        "edition": str(edition or "").strip(),
        "catalog_id": str(catalog_id or "").strip(),
        "source_name": str(source_name or source_type).strip(),
        "source_type": str(source_type or "").strip(),
        "source_ref": str(source_ref or "").strip(),
        "witness_key": witness_key,
        "lineage_source": lineage_source,
    }

    if enriched_metadata.get("root_title"):
        version_metadata["root_title"] = str(enriched_metadata.get("root_title") or "").strip()
    if enriched_metadata.get("root_urn"):
        version_metadata["root_urn"] = str(enriched_metadata.get("root_urn") or "").strip()

    enriched_metadata["version_metadata"] = version_metadata
    for key in ("work_title", "work_key", "fragment_title", "fragment_key", "work_fragment_key", "version_lineage_key"):
        enriched_metadata.setdefault(key, version_metadata[key])
    if version_metadata.get("dynasty"):
        enriched_metadata.setdefault("dynasty", version_metadata["dynasty"])
    if version_metadata.get("author"):
        enriched_metadata.setdefault("author", version_metadata["author"])
    if version_metadata.get("edition"):
        enriched_metadata.setdefault("edition", version_metadata["edition"])
    if version_metadata.get("catalog_id"):
        enriched_metadata.setdefault("catalog_id", version_metadata["catalog_id"])
    return enriched_metadata


# ─────────────────────────────────────────────────────────────────────────────
# CorpusDocument — 每一篇文档的统一表示
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorpusDocument:
    """统一文档模型，对齐 CText / 本地文件 / PDF 三类来源。"""

    doc_id: str
    """唯一文档标识（由 source_type + source_ref 的 hash 生成）"""

    title: str
    """文档标题"""

    text: str
    """正文内容（已去首尾空白）"""

    source_type: str
    """来源类型: 'ctext' | 'local' | 'pdf'"""

    source_ref: str
    """来源引用：CText URN / 本地文件路径 / PDF 文件路径"""

    language: str = "zh"
    """主语言代码"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """来源特定元数据（不影响 schema 核心字段）"""

    collected_at: str = ""
    """采集时间戳（ISO 8601）"""

    children: List["CorpusDocument"] = field(default_factory=list)
    """子文档（仅 CText 层级结构使用）"""

    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "text": self.text,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "language": self.language,
            "metadata": self.metadata,
            "collected_at": self.collected_at,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CorpusDocument":
        children = [cls.from_dict(c) for c in (d.get("children") or [])]
        return cls(
            doc_id=d.get("doc_id", ""),
            title=d.get("title", ""),
            text=d.get("text", ""),
            source_type=d.get("source_type", "unknown"),
            source_ref=d.get("source_ref", ""),
            language=d.get("language", "zh"),
            metadata=d.get("metadata") or {},
            collected_at=d.get("collected_at", ""),
            children=children,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CorpusBundle — 多来源采集结果的统一容器
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorpusBundle:
    """多来源语料束，含 schema_version 以区分新旧格式。"""

    bundle_id: str
    sources: List[str]
    """参与合并的来源类型列表，如 ['ctext', 'local']"""

    documents: List[CorpusDocument]
    collected_at: str
    stats: Dict[str, Any]
    errors: List[Dict[str, str]]
    schema_version: str = BUNDLE_SCHEMA_VERSION

    # ── 序列化 ──────────────────────────────────────────────────────────── #

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的 dict，含 schema_version 标记。"""
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "sources": self.sources,
            "collected_at": self.collected_at,
            "stats": self.stats,
            "errors": self.errors,
            "documents": [doc.to_dict() for doc in self.documents],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CorpusBundle":
        docs = [CorpusDocument.from_dict(x) for x in (d.get("documents") or [])]
        return cls(
            bundle_id=d.get("bundle_id", ""),
            sources=d.get("sources") or [],
            documents=docs,
            collected_at=d.get("collected_at", ""),
            stats=d.get("stats") or {},
            errors=d.get("errors") or [],
            schema_version=d.get("schema_version", BUNDLE_SCHEMA_VERSION),
        )

    # ── 平铺 ─────────────────────────────────────────────────────────────── #

    def flat_documents(self) -> List[CorpusDocument]:
        """递归展开层级结构，返回所有叶节点 / 有 text 的节点。"""
        result: List[CorpusDocument] = []
        stack = list(self.documents)
        while stack:
            node = stack.pop(0)
            if node.text.strip():
                result.append(node)
            stack.extend(node.children)
        return result

    # ── 工厂：从旧格式转换 ────────────────────────────────────────────────── #

    @classmethod
    def from_ctext_result(cls, result: Dict[str, Any]) -> "CorpusBundle":
        """将 CTextCorpusCollector._do_execute() 的原始输出转换为 CorpusBundle。

        旧格式结构::

            {
                "source": "ctext",
                "collected_at": "...",
                "seed_urns": [...],
                "documents": [{"urn": ..., "title": ..., "text": ..., "children": [...]}],
                "stats": {...},
                "errors": [...],
            }
        """
        collected_at = result.get("collected_at", datetime.now().isoformat())
        raw_errors: List[Dict[str, str]] = [
            {"source_ref": e.get("urn", ""), "error": e.get("error", str(e))}
            for e in (result.get("errors") or [])
        ]

        def _convert_node(
            node: Dict[str, Any],
            *,
            root_title: str,
            root_urn: str,
            depth: int,
        ) -> CorpusDocument:
            urn = node.get("urn", "")
            doc_id = _make_doc_id("ctext", urn)
            title = node.get("title", "")
            current_root_title = root_title or title
            current_root_urn = root_urn or urn
            raw_node_metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
            node_metadata_payload = dict(raw_node_metadata)
            node_metadata_payload.setdefault("seed_urn", urn in (result.get("seed_urns") or []))
            node_metadata_payload.setdefault("output_file", result.get("output_file", ""))
            node_metadata_payload.setdefault("root_title", current_root_title)
            node_metadata_payload.setdefault("root_urn", current_root_urn)
            node_metadata_payload["fragment_title"] = title or current_root_title
            node_metadata_payload["node_depth"] = depth
            node_metadata_payload.setdefault("source_name", "ctext")
            node_metadata = build_document_version_metadata(
                title=title,
                source_type="ctext",
                source_ref=urn,
                metadata=node_metadata_payload,
            )
            children = [
                _convert_node(
                    c,
                    root_title=current_root_title,
                    root_urn=current_root_urn,
                    depth=depth + 1,
                )
                for c in (node.get("children") or [])
            ]
            return CorpusDocument(
                doc_id=doc_id,
                title=title,
                text=(node.get("text") or "").strip(),
                source_type="ctext",
                source_ref=urn,
                language="zh",
                metadata=node_metadata,
                collected_at=collected_at,
                children=children,
            )

        documents = [
            _convert_node(
                d,
                root_title=d.get("title", ""),
                root_urn=d.get("urn", ""),
                depth=0,
            )
            for d in (result.get("documents") or [])
        ]
        old_stats = result.get("stats") or {}
        stats = {
            "total_documents": len(documents),
            "total_chars": sum(
                _count_chars(doc) for doc in documents
            ),
            "source_type": "ctext",
            # 保留旧统计字段以便兼容
            **old_stats,
        }
        bundle_id = _make_bundle_id(["ctext"], collected_at)
        return cls(
            bundle_id=bundle_id,
            sources=["ctext"],
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=raw_errors,
        )

    @classmethod
    def from_local_result(cls, result: Dict[str, Any]) -> "CorpusBundle":
        """将 LocalCorpusCollector._do_execute() 的输出转换为 CorpusBundle。

        LocalCorpusCollector 已直接输出 CorpusBundle dict；此方法提供
        统一入口以供外部调用（等价于 CorpusBundle.from_dict()）。
        """
        if is_corpus_bundle(result):
            return cls.from_dict(result)
        # 兼容更早期的本地采集格式（若有）
        collected_at = result.get("collected_at", datetime.now().isoformat())
        documents = [
            CorpusDocument(
                doc_id=_make_doc_id("local", d.get("path", "")),
                title=d.get("title", os.path.basename(d.get("path", ""))),
                text=(d.get("text") or "").strip(),
                source_type="local",
                source_ref=d.get("path", ""),
                language=d.get("language", "zh"),
                metadata=build_document_version_metadata(
                    title=d.get("title", os.path.basename(d.get("path", ""))),
                    source_type="local",
                    source_ref=d.get("path", ""),
                    metadata=d.get("metadata") or {},
                ),
                collected_at=collected_at,
            )
            for d in (result.get("files") or result.get("documents") or [])
        ]
        stats = {
            "total_documents": len(documents),
            "total_chars": sum(len(d.text) for d in documents),
            "source_type": "local",
        }
        bundle_id = _make_bundle_id(["local"], collected_at)
        return cls(
            bundle_id=bundle_id,
            sources=["local"],
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=result.get("errors") or [],
        )

    @classmethod
    def from_pdf_result(cls, result: Dict[str, Any]) -> "CorpusBundle":
        """将 PdfTranslationResult 的 dict 转换为 CorpusBundle。

        PdfTranslationResult 字段::

            status, pdf_path, title, abstract, abstract_translated,
            fragment_results, summary, error, ...
        """
        if is_corpus_bundle(result):
            return cls.from_dict(result)

        collected_at = datetime.now().isoformat()
        pdf_path = result.get("pdf_path", "")
        title = result.get("title", os.path.basename(pdf_path))
        errors: List[Dict[str, str]] = []
        documents: List[CorpusDocument] = []

        if result.get("error"):
            errors.append({"source_ref": pdf_path, "error": result["error"]})
        else:
            # 正文：fragment_results 列表中每个元素含 original / translated
            fragments = result.get("fragment_results") or []
            combined_text = "\n".join(
                f.get("original", "") for f in fragments if f.get("original")
            ).strip()
            if not combined_text:
                # 回退到 abstract
                combined_text = result.get("abstract", "")

            doc = CorpusDocument(
                doc_id=_make_doc_id("pdf", pdf_path),
                title=title,
                text=combined_text,
                source_type="pdf",
                source_ref=pdf_path,
                language="en",  # PDF 通常为英文
                metadata=build_document_version_metadata(
                    title=title,
                    source_type="pdf",
                    source_ref=pdf_path,
                    metadata={
                        "abstract": result.get("abstract", ""),
                        "abstract_translated": result.get("abstract_translated", ""),
                        "fragment_count": len(fragments),
                        "output_markdown": result.get("output_markdown", ""),
                        "status": result.get("status", ""),
                        "source_name": "pdf",
                    },
                ),
                collected_at=collected_at,
            )
            documents.append(doc)

        stats = {
            "total_documents": len(documents),
            "total_chars": sum(len(d.text) for d in documents),
            "source_type": "pdf",
        }
        bundle_id = _make_bundle_id(["pdf"], collected_at)
        return cls(
            bundle_id=bundle_id,
            sources=["pdf"],
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=errors,
        )

    @classmethod
    def from_result(
        cls,
        result: Dict[str, Any],
        source_hint: Optional[str] = None,
    ) -> "CorpusBundle":
        """将任意来源采集结果归一化为 CorpusBundle。

        兼容：
        - 已是 CorpusBundle dict
        - CText 原始格式
        - Local 早期格式
        - PDF 翻译结果格式
        - 通用 documents/files 列表格式（保守回退）
        """
        if is_corpus_bundle(result):
            return cls.from_dict(result)

        hint = (source_hint or str(result.get("source") or "")).lower().strip()
        if hint == "ctext" or result.get("seed_urns") or _looks_like_ctext_documents(result.get("documents") or []):
            return cls.from_ctext_result(result)

        if hint == "pdf" or result.get("pdf_path") or result.get("fragment_results"):
            return cls.from_pdf_result(result)

        if hint == "local" or result.get("files"):
            return cls.from_local_result(result)

        return cls._from_generic_documents_result(result, source_hint=hint or "generic")

    @classmethod
    def merge_results(cls, results: List[Dict[str, Any]]) -> "CorpusBundle":
        """将多来源原始结果直接归一化并合并。"""
        bundles = [cls.from_result(item) for item in results if isinstance(item, dict)]
        if not bundles:
            raise ValueError("merge_results() 需要至少一个有效结果")
        return cls.merge(bundles)

    @classmethod
    def _from_generic_documents_result(
        cls,
        result: Dict[str, Any],
        source_hint: str = "generic",
    ) -> "CorpusBundle":
        collected_at = result.get("collected_at", datetime.now().isoformat())
        raw_documents = result.get("documents") or result.get("files") or []
        documents: List[CorpusDocument] = []
        for idx, item in enumerate(raw_documents):
            if not isinstance(item, dict):
                continue
            source_ref = str(
                item.get("source_ref")
                or item.get("path")
                or item.get("urn")
                or item.get("url")
                or f"{source_hint}:{idx}"
            )
            title = str(item.get("title") or os.path.basename(source_ref) or f"doc_{idx}")
            text = str(item.get("text") or item.get("content") or "").strip()
            raw_meta = item.get("metadata")
            metadata: Dict[str, Any]
            if isinstance(raw_meta, dict):
                metadata = dict(raw_meta)
            else:
                metadata = {}
            documents.append(
                CorpusDocument(
                    doc_id=_make_doc_id(source_hint, source_ref),
                    title=title,
                    text=text,
                    source_type=source_hint,
                    source_ref=source_ref,
                    language=str(item.get("language") or "zh"),
                    metadata=build_document_version_metadata(
                        title=title,
                        source_type=source_hint,
                        source_ref=source_ref,
                        metadata=metadata,
                    ),
                    collected_at=collected_at,
                )
            )

        stats = {
            "total_documents": len(documents),
            "total_chars": sum(len(doc.text) for doc in documents),
            "source_type": source_hint,
        }
        return cls(
            bundle_id=_make_bundle_id([source_hint], collected_at),
            sources=[source_hint],
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=result.get("errors") or [],
        )

    # ── 合并 ─────────────────────────────────────────────────────────────── #

    @staticmethod
    def merge(bundles: List["CorpusBundle"]) -> "CorpusBundle":
        """将多个 CorpusBundle 合并为一个。bundle_id 由合并后内容生成。"""
        if not bundles:
            raise ValueError("merge() 需要至少一个 CorpusBundle")
        if len(bundles) == 1:
            return bundles[0]

        collected_at = datetime.now().isoformat()
        all_sources: List[str] = []
        all_docs: List[CorpusDocument] = []
        all_errors: List[Dict[str, str]] = []

        for bundle in bundles:
            for src in bundle.sources:
                if src not in all_sources:
                    all_sources.append(src)
            all_docs.extend(bundle.documents)
            all_errors.extend(bundle.errors)

        deduped, duplicate_count = _dedupe_documents(all_docs)

        stats = {
            "total_documents": len(deduped),
            "total_chars": sum(_count_chars(d) for d in deduped),
            "source_types": all_sources,
            "duplicate_documents": duplicate_count,
            "per_source": {
                src: sum(1 for d in deduped if d.source_type == src)
                for src in all_sources
            },
        }
        bundle_id = _make_bundle_id(all_sources, collected_at)
        return CorpusBundle(
            bundle_id=bundle_id,
            sources=all_sources,
            documents=deduped,
            collected_at=collected_at,
            stats=stats,
            errors=all_errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 格式判别 & 文本提取
# ─────────────────────────────────────────────────────────────────────────────

def is_corpus_bundle(d: Any) -> bool:
    """判断 dict 是否为新 CorpusBundle 格式（含 schema_version 标记）。"""
    return isinstance(d, dict) and d.get("schema_version") == BUNDLE_SCHEMA_VERSION


def extract_text_entries(corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """统一文本条目提取入口 — 同时兼容新旧格式。

    新格式（CorpusBundle）: schema_version="1.0"
    旧格式（CText raw dict）: 含 "documents" 列表，每项含 urn/title/text/children

    返回值格式::

        [{"urn": ..., "title": ..., "text": ...}, ...]
    """
    if is_corpus_bundle(corpus_result):
        return _extract_entries_from_bundle(corpus_result)
    return _extract_entries_from_ctext(corpus_result)


def _extract_entries_from_bundle(corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
    bundle = CorpusBundle.from_dict(corpus_result)
    entries = []
    for doc in bundle.flat_documents():
        metadata = build_document_version_metadata(
            title=doc.title,
            source_type=doc.source_type,
            source_ref=doc.source_ref,
            metadata=doc.metadata,
        )
        entries.append({
            "urn": doc.source_ref,
            "title": doc.title,
            "text": doc.text,
            "source_type": doc.source_type,
            "doc_id": doc.doc_id,
            "metadata": metadata,
            "version_metadata": metadata.get("version_metadata", {}),
        })
    return entries


def _extract_entries_from_ctext(corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """旧 CText dict 格式的文本提取（保留原有树遍历逻辑）。"""
    entries: List[Dict[str, str]] = []
    stack = list(corpus_result.get("documents", []))
    while stack:
        node = stack.pop(0)
        text = (node.get("text") or "").strip()
        if text:
            raw_metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
            metadata = build_document_version_metadata(
                title=node.get("title", ""),
                source_type=str(node.get("source_type") or corpus_result.get("source") or "ctext"),
                source_ref=node.get("urn", ""),
                metadata=raw_metadata,
            )
            entry = {
                "urn": node.get("urn", ""),
                "title": node.get("title", ""),
                "text": text,
                "metadata": metadata,
                "version_metadata": metadata.get("version_metadata", {}),
            }
            source_type = str(node.get("source_type") or corpus_result.get("source") or "").strip()
            if source_type and source_type != "ctext":
                entry["source_type"] = source_type
            entries.append(entry)
        stack.extend(node.get("children", []) or [])
    return entries


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value.strip()
            continue
        if value not in (None, [], {}, ()):
            return value
    return ""


def _infer_filename_version_fields(source_ref: str) -> Tuple[str, str, str]:
    candidate = os.path.splitext(os.path.basename(source_ref or ""))[0]
    if not candidate:
        return "", "", ""

    match = _RE_FILENAME_VERSION_META.match(candidate)
    if not match:
        return "", "", ""

    _, work_title, dynasty, author = match.groups()
    return str(work_title or "").strip(), str(dynasty or "").strip(), str(author or "").strip()


def _normalize_lineage_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return _LINEAGE_NORMALIZE_RE.sub("", token)


def _build_work_fragment_key(work_key: str, fragment_key: str) -> str:
    normalized_work_key = _normalize_lineage_token(work_key)
    normalized_fragment_key = _normalize_lineage_token(fragment_key) or normalized_work_key
    return "|".join(part for part in [normalized_work_key, normalized_fragment_key] if part)


def _build_version_lineage_key(work_fragment_key: str, dynasty: Any, author: Any, edition: Any) -> str:
    components = [
        _normalize_lineage_token(work_fragment_key),
        _normalize_lineage_token(dynasty),
        _normalize_lineage_token(author),
        _normalize_lineage_token(edition),
    ]
    return "|".join(component for component in components if component)


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_doc_id(source_type: str, ref: str) -> str:
    digest = hashlib.md5(f"{source_type}:{ref}".encode()).hexdigest()[:12]
    return f"{source_type}_{digest}"


def _make_bundle_id(sources: List[str], ts: str) -> str:
    key = "|".join(sorted(sources)) + "|" + ts
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"bundle_{digest}"


def _count_chars(doc: CorpusDocument) -> int:
    total = len(doc.text)
    for child in doc.children:
        total += _count_chars(child)
    return total


def _looks_like_ctext_documents(documents: List[Any]) -> bool:
    if not isinstance(documents, list) or not documents:
        return False
    first = documents[0]
    return isinstance(first, dict) and ("urn" in first or "children" in first)


def _normalize_title(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip()).lower()


def _normalize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    return compact.lower()


def _semantic_dedup_key(doc: CorpusDocument) -> str:
    norm_text = _normalize_text(doc.text)
    if norm_text:
        text_hash = hashlib.md5(norm_text.encode()).hexdigest()[:16]
        return f"text:{text_hash}"

    source_name = os.path.basename((doc.source_ref or "").replace("\\", "/")).lower()
    if source_name:
        return f"ref:{source_name}"
    return f"doc:{doc.doc_id}"


def _doc_quality(doc: CorpusDocument) -> Tuple[int, int, int]:
    return (len(doc.text or ""), len(doc.metadata or {}), len(doc.children or []))


def _merge_doc_provenance(preferred: CorpusDocument, duplicate: CorpusDocument) -> CorpusDocument:
    merged_sources = preferred.metadata.get("merged_sources") if isinstance(preferred.metadata, dict) else None
    if not isinstance(merged_sources, list):
        merged_sources = [
            {
                "source_type": preferred.source_type,
                "source_ref": preferred.source_ref,
                "doc_id": preferred.doc_id,
            }
        ]
    merged_sources.append(
        {
            "source_type": duplicate.source_type,
            "source_ref": duplicate.source_ref,
            "doc_id": duplicate.doc_id,
        }
    )
    preferred.metadata = dict(preferred.metadata or {})
    preferred.metadata["merged_sources"] = merged_sources
    return preferred


def _dedupe_documents(documents: List[CorpusDocument]) -> Tuple[List[CorpusDocument], int]:
    by_doc_id: Dict[str, CorpusDocument] = {}
    duplicate_count = 0
    for doc in documents:
        existing = by_doc_id.get(doc.doc_id)
        if existing is None:
            by_doc_id[doc.doc_id] = doc
        else:
            duplicate_count += 1
            if _doc_quality(doc) > _doc_quality(existing):
                by_doc_id[doc.doc_id] = _merge_doc_provenance(doc, existing)
            else:
                by_doc_id[doc.doc_id] = _merge_doc_provenance(existing, doc)

    semantic_map: Dict[str, CorpusDocument] = {}
    for doc in by_doc_id.values():
        key = _semantic_dedup_key(doc)
        existing = semantic_map.get(key)
        if existing is None:
            semantic_map[key] = doc
            continue

        duplicate_count += 1
        if _doc_quality(doc) > _doc_quality(existing):
            semantic_map[key] = _merge_doc_provenance(doc, existing)
        else:
            semantic_map[key] = _merge_doc_provenance(existing, doc)

    return list(semantic_map.values()), duplicate_count
