"""信息统一化服务 — 术语标准化映射、元数据规范化、编码统一。"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.collector.corpus_bundle import CorpusBundle, CorpusDocument, is_corpus_bundle
from src.core.module_base import BaseModule
from src.knowledge.ontology_manager import get_default_ontology_manager

logger = logging.getLogger(__name__)

_WORD_BREAK_RE = re.compile(r"(\w)\n(\w)")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PUNCTUATION_MAP = {
    "\ufeff": "",
    "\u3000": " ",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "﹑": "、",
    "﹔": "；",
    "﹕": "：",
    "﹖": "？",
    "﹗": "！",
    "﹘": "-",
}
_DEFAULT_TERM_MAPPINGS = {
    "黃芪": "黄芪",
    "當歸": "当归",
    "當歸補血湯": "当归补血汤",
    "補血湯": "补血汤",
    "白朮": "白术",
    "蒼朮": "苍术",
    "茯苓": "茯苓",
    "甘艸": "甘草",
    "傷寒論": "伤寒论",
    "金匱要略": "金匮要略",
    "張仲景": "张仲景",
    "辨證": "辨证",
    "證候": "证候",
    "方證": "方证",
    "炮炙": "炮制",
}
_DEFAULT_METADATA_ALIASES = {
    "title": ["title", "name", "document_title"],
    "authors": ["authors", "author", "creator", "creator_name"],
    "year": ["year", "publish_year", "publication_year"],
    "publish_date": ["publish_date", "published", "publication_date", "date"],
    "dynasty": ["dynasty", "era", "period"],
    "source": ["source", "source_name", "origin"],
    "source_file": ["source_file", "file_path", "path", "source_ref"],
    "language": ["language", "lang"],
    "encoding": ["encoding", "charset", "encoding_detected"],
    "source_type": ["source_type", "file_type", "format"],
    "keywords": ["keywords", "keyword", "tags"],
    "abstract": ["abstract", "summary", "description"],
    "identifier": ["identifier", "id", "doc_id"],
}
_DEFAULT_SOURCE_TYPE_ALIASES = {
    "txt": "local",
    "text": "local",
    "md": "local",
    "markdown": "local",
    "docx": "local",
    "pdf": "pdf",
    "epub": "epub",
    "scan": "scan",
    "image": "scan",
    "png": "scan",
    "jpg": "scan",
    "jpeg": "scan",
    "tif": "scan",
    "tiff": "scan",
}
_TEXT_METADATA_FIELDS = {"title", "abstract", "dynasty", "source"}
_LIST_METADATA_FIELDS = {"authors", "keywords"}


@dataclass
class NormalizationResult:
    """归一化结果。"""

    success: bool
    normalized_text: str = ""
    term_mappings: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    normalization_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "normalized_text": self.normalized_text,
            "term_mappings": self.term_mappings,
            "metadata": self.metadata,
            "errors": self.errors,
            "normalization_steps": self.normalization_steps,
        }


class Normalizer(BaseModule):
    """信息统一化器 — 术语标准化映射、元数据规范化、编码统一。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("normalizer", config)
        self.convert_mode = str(self.config.get("convert_mode", "t2s")).strip()
        self.drop_empty_metadata = bool(self.config.get("drop_empty_metadata", True))
        self.normalize_entity_type_mentions = bool(
            self.config.get("normalize_entity_type_mentions", True)
        )
        self.default_language = str(self.config.get("default_language", "zh"))
        self.ontology_manager = get_default_ontology_manager()
        self.encoding_fallbacks = list(
            self.config.get("encoding_fallbacks") or ["utf-8", "utf-8-sig", "gb18030", "gbk"]
        )
        self.term_mappings = self._build_term_mapping(self.config.get("term_mappings") or {})
        self.metadata_aliases = self._build_metadata_alias_index(
            self.config.get("metadata_aliases") or {}
        )
        self.source_type_aliases = {
            **_DEFAULT_SOURCE_TYPE_ALIASES,
            **{str(k).strip().lower(): str(v).strip().lower() for k, v in (self.config.get("source_type_aliases") or {}).items()},
        }
        self._opencc: Any = None

    def _do_initialize(self) -> bool:
        if not self.convert_mode:
            self.logger.info("Normalizer 初始化完成: 繁简转换已禁用")
            return True

        try:
            opencc_module = importlib.import_module("opencc")
            self._opencc = opencc_module.OpenCC(self.convert_mode)
            self.logger.info("Normalizer 初始化完成: OpenCC mode=%s", self.convert_mode)
        except Exception as exc:
            self._opencc = None
            self.logger.warning("Normalizer OpenCC 初始化失败，回退原文: %s", exc)
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        bundle = context.get("bundle")
        if isinstance(bundle, dict) and is_corpus_bundle(bundle):
            return self.normalize_bundle(bundle).to_dict()
        if isinstance(bundle, CorpusBundle):
            return self.normalize_bundle(bundle).to_dict()

        if is_corpus_bundle(context):
            return self.normalize_bundle(context).to_dict()

        document = context.get("document")
        if isinstance(document, (CorpusDocument, dict)):
            result, normalized_document = self.normalize_document(document, context=context)
            payload = result.to_dict()
            payload["document"] = normalized_document.to_dict()
            return payload

        documents = context.get("documents")
        if isinstance(documents, list):
            normalized_documents: List[Dict[str, Any]] = []
            aggregated_mappings: Dict[str, str] = {}
            aggregated_errors: List[str] = []
            steps: List[str] = []
            for item in documents:
                result, normalized_document = self.normalize_document(item, context=context)
                normalized_documents.append(normalized_document.to_dict())
                aggregated_mappings.update(result.term_mappings)
                aggregated_errors.extend(result.errors)
                steps.extend(result.normalization_steps)
            return {
                "success": not aggregated_errors,
                "documents": normalized_documents,
                "term_mappings": aggregated_mappings,
                "errors": aggregated_errors,
                "normalization_steps": _unique_preserve_order(steps),
                "document_count": len(normalized_documents),
            }

        result = self.normalize_text_payload(context)
        return result.to_dict()

    def _do_cleanup(self) -> bool:
        self._opencc = None
        return True

    def normalize_text_payload(self, context: Dict[str, Any]) -> NormalizationResult:
        raw_text = context.get("raw_text", context.get("text", context.get("content")))
        if raw_text is None:
            raise ValueError("Normalizer 需要 raw_text、text、content、document 或 bundle 输入")

        normalized_text, detected_encoding, used_mappings, steps = self._normalize_text_value(raw_text)
        normalized_metadata = self._normalize_metadata(context, detected_encoding, used_mappings)
        normalized_metadata.setdefault("language", self.default_language)
        normalized_metadata.setdefault("encoding", detected_encoding)

        return NormalizationResult(
            success=True,
            normalized_text=normalized_text,
            term_mappings=used_mappings,
            metadata=normalized_metadata,
            normalization_steps=steps + ["metadata_normalization"],
        )

    def normalize_document(
        self,
        document: CorpusDocument | Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[NormalizationResult, CorpusDocument]:
        doc = document if isinstance(document, CorpusDocument) else CorpusDocument.from_dict(document)
        exec_context = context or {}

        normalized_text, detected_encoding, used_mappings, steps = self._normalize_text_value(doc.text)
        metadata_seed = {
            **doc.metadata,
            "title": doc.title,
            "source_type": doc.source_type,
            "source_file": doc.source_ref,
            "language": doc.language,
            "identifier": doc.doc_id,
        }
        normalized_metadata = self._normalize_metadata(metadata_seed, detected_encoding, used_mappings)
        normalized_title = str(normalized_metadata.get("title") or doc.title).strip()
        normalized_source_type = self._normalize_source_type(
            exec_context.get("source_type") or normalized_metadata.get("source_type") or doc.source_type
        )

        normalized_children: List[CorpusDocument] = []
        child_mappings: Dict[str, str] = {}
        child_steps: List[str] = []
        for child in doc.children:
            child_result, normalized_child = self.normalize_document(child, context=exec_context)
            normalized_children.append(normalized_child)
            child_mappings.update(child_result.term_mappings)
            child_steps.extend(child_result.normalization_steps)

        if child_mappings:
            used_mappings.update(child_mappings)
        normalized_metadata["normalization"] = {
            "applied_steps": _unique_preserve_order(steps + child_steps + ["metadata_normalization"]),
            "term_mappings": dict(used_mappings),
            "normalized_at": datetime.now().isoformat(),
        }
        normalized_metadata["encoding"] = detected_encoding
        normalized_metadata.setdefault("language", doc.language or self.default_language)
        normalized_metadata["source_type"] = normalized_source_type

        normalized_document = CorpusDocument(
            doc_id=doc.doc_id,
            title=normalized_title,
            text=normalized_text,
            source_type=normalized_source_type,
            source_ref=str(normalized_metadata.get("source_file") or doc.source_ref),
            language=str(normalized_metadata.get("language") or self.default_language),
            metadata=normalized_metadata,
            collected_at=doc.collected_at,
            children=normalized_children,
        )
        result = NormalizationResult(
            success=True,
            normalized_text=normalized_text,
            term_mappings=used_mappings,
            metadata=normalized_metadata,
            normalization_steps=_unique_preserve_order(steps + child_steps + ["metadata_normalization"]),
        )
        return result, normalized_document

    def normalize_bundle(
        self,
        bundle: CorpusBundle | Dict[str, Any],
    ) -> CorpusBundle:
        source_bundle = bundle if isinstance(bundle, CorpusBundle) else CorpusBundle.from_dict(bundle)
        normalized_documents: List[CorpusDocument] = []
        aggregated_mappings: Dict[str, str] = {}
        aggregated_steps: List[str] = []

        for document in source_bundle.documents:
            result, normalized_document = self.normalize_document(document)
            normalized_documents.append(normalized_document)
            aggregated_mappings.update(result.term_mappings)
            aggregated_steps.extend(result.normalization_steps)

        stats = dict(source_bundle.stats)
        stats["normalized_documents"] = len(normalized_documents)
        stats["normalization_steps"] = _unique_preserve_order(aggregated_steps)
        stats["term_mapping_count"] = len(aggregated_mappings)
        stats["total_chars"] = sum(len(doc.text) for doc in normalized_documents)

        errors = list(source_bundle.errors)
        errors.extend([])
        normalized_bundle = CorpusBundle(
            bundle_id=source_bundle.bundle_id,
            sources=source_bundle.sources,
            documents=normalized_documents,
            collected_at=source_bundle.collected_at,
            stats=stats,
            errors=errors,
            schema_version=source_bundle.schema_version,
        )
        return normalized_bundle

    def _normalize_text_value(
        self,
        raw_text: Any,
    ) -> Tuple[str, str, Dict[str, str], List[str]]:
        text, detected_encoding = self._decode_text(raw_text)
        steps = ["encoding_unification", "control_char_sanitization", "punctuation_normalization"]
        current = self._sanitize_text(text)
        current = self._normalize_punctuation(current)

        if self._opencc is not None:
            converted = self._convert_text(current)
            if converted != current:
                steps.append("script_conversion")
            current = converted

        if self.normalize_entity_type_mentions:
            normalized_mentions = self.ontology_manager.normalize_text_entity_type_mentions(current)
            if normalized_mentions != current:
                steps.append("entity_type_normalization")
            current = normalized_mentions

        current, used_mappings = self._apply_term_mappings(current)
        if used_mappings:
            steps.append("term_mapping")

        current = self._clean_line_breaks(current)
        current = self._normalize_whitespace(current)
        steps.extend(["line_break_normalization", "whitespace_normalization"])
        return current, detected_encoding, used_mappings, _unique_preserve_order(steps)

    def _normalize_metadata(
        self,
        payload: Dict[str, Any],
        detected_encoding: str,
        used_mappings: Dict[str, str],
    ) -> Dict[str, Any]:
        raw_metadata = dict(payload.get("metadata") or {})
        if payload is not raw_metadata:
            for key in self.metadata_aliases:
                if key in payload:
                    raw_metadata.setdefault(key, payload[key])
            for key in ("title", "authors", "author", "source_file", "source_type", "language", "encoding"):
                if key in payload:
                    raw_metadata.setdefault(key, payload[key])

        normalized: Dict[str, Any] = {}
        for key, value in raw_metadata.items():
            canonical_key = self._canonical_metadata_key(key)
            canonical_value = self._normalize_metadata_value(canonical_key, value)
            if self.drop_empty_metadata and canonical_value in (None, "", [], {}):
                continue
            if canonical_key in normalized:
                normalized[canonical_key] = self._merge_metadata_value(
                    normalized[canonical_key],
                    canonical_value,
                )
            else:
                normalized[canonical_key] = canonical_value

        normalized.setdefault("encoding", detected_encoding)
        normalized.setdefault("language", self.default_language)

        publish_date = str(normalized.get("publish_date", "")).strip()
        if publish_date and "year" not in normalized:
            year_match = re.search(r"(1\d{3}|20\d{2}|21\d{2})", publish_date)
            if year_match:
                normalized["year"] = year_match.group(1)

        if "source_type" in normalized:
            normalized["source_type"] = self._normalize_source_type(str(normalized["source_type"]))

        if used_mappings:
            normalized.setdefault("term_mappings", dict(used_mappings))
        return normalized

    def _canonical_metadata_key(self, key: str) -> str:
        normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")
        return self.metadata_aliases.get(normalized_key, normalized_key or "metadata")

    def _normalize_metadata_value(self, key: str, value: Any) -> Any:
        if value is None:
            return None
        if key in _LIST_METADATA_FIELDS:
            items = self._normalize_list_value(value)
            return items
        if isinstance(value, str):
            text, _detected_encoding, _mappings, _steps = self._normalize_text_value(value)
            if key == "source_type":
                return self._normalize_source_type(text)
            return text
        if isinstance(value, bytes):
            text, _detected_encoding, _mappings, _steps = self._normalize_text_value(value)
            return text
        if isinstance(value, list):
            return [self._normalize_metadata_value(key, item) for item in value if item not in (None, "")]
        if isinstance(value, dict):
            return {
                self._canonical_metadata_key(sub_key): self._normalize_metadata_value(sub_key, sub_value)
                for sub_key, sub_value in value.items()
                if sub_value not in (None, "")
            }
        return value

    def _normalize_list_value(self, value: Any) -> List[str]:
        if isinstance(value, str):
            raw_items = re.split(r"[,，;；/、\n]+", value)
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            raw_items = [value]

        items: List[str] = []
        for item in raw_items:
            if item is None:
                continue
            normalized, _encoding, _mappings, _steps = self._normalize_text_value(str(item))
            if normalized and normalized not in items:
                items.append(normalized)
        return items

    def _merge_metadata_value(self, left: Any, right: Any) -> Any:
        if isinstance(left, list) and isinstance(right, list):
            merged = list(left)
            for item in right:
                if item not in merged:
                    merged.append(item)
            return merged
        return right if right not in (None, "", [], {}) else left

    def _decode_text(self, raw_text: Any) -> Tuple[str, str]:
        if isinstance(raw_text, str):
            return raw_text, "utf-8"
        if isinstance(raw_text, bytes):
            detected = self._detect_encoding(raw_text)
            for encoding in _unique_preserve_order([detected] + self.encoding_fallbacks):
                try:
                    return raw_text.decode(encoding), encoding
                except (LookupError, UnicodeDecodeError):
                    continue
            return raw_text.decode("utf-8", errors="replace"), "utf-8-replace"
        return str(raw_text), "utf-8"

    def _detect_encoding(self, raw_bytes: bytes) -> str:
        try:
            chardet = importlib.import_module("chardet")
            detected = chardet.detect(raw_bytes) or {}
            encoding = str(detected.get("encoding") or "").strip().lower()
            if encoding:
                return encoding
        except Exception:
            pass
        return "utf-8"

    def _convert_text(self, text: str) -> str:
        if self._opencc is None:
            return text
        try:
            return str(self._opencc.convert(text))
        except Exception as exc:
            self.logger.warning("Normalizer 繁简转换失败，返回原文本: %s", exc)
            return text

    def _apply_term_mappings(self, text: str) -> Tuple[str, Dict[str, str]]:
        normalized = text
        used_mappings: Dict[str, str] = {}
        for alias, canonical in sorted(self.term_mappings.items(), key=lambda item: len(item[0]), reverse=True):
            if not alias:
                continue
            replaced = re.sub(re.escape(alias), canonical, normalized)
            if replaced != normalized:
                used_mappings[alias] = canonical
                normalized = replaced
        return normalized, used_mappings

    def _sanitize_text(self, text: str) -> str:
        return _CONTROL_CHARS_RE.sub("", text)

    def _normalize_punctuation(self, text: str) -> str:
        normalized = text
        for original, replacement in _PUNCTUATION_MAP.items():
            normalized = normalized.replace(original, replacement)
        return normalized

    def _clean_line_breaks(self, text: str) -> str:
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = _WORD_BREAK_RE.sub(r"\1\2", cleaned)
        cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
        cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
        return cleaned.strip()

    def _normalize_whitespace(self, text: str) -> str:
        lines = [re.sub(_MULTI_SPACE_RE, " ", line).strip() for line in text.split("\n")]
        return "\n".join(lines).strip()

    def _normalize_source_type(self, source_type: str) -> str:
        value = str(source_type or "").strip().lower()
        return self.source_type_aliases.get(value, value or "local")

    def _build_term_mapping(self, custom_mapping: Dict[str, Any]) -> Dict[str, str]:
        mapping = dict(_DEFAULT_TERM_MAPPINGS)
        for key, value in custom_mapping.items():
            mapping[str(key).strip()] = str(value).strip()
        for alias, canonical in self.ontology_manager.NODE_TYPE_ALIASES.items():
            mapping[alias] = canonical
        return mapping

    def _build_metadata_alias_index(self, custom_aliases: Dict[str, Any]) -> Dict[str, str]:
        alias_index: Dict[str, str] = {}
        for canonical, aliases in _DEFAULT_METADATA_ALIASES.items():
            alias_index[canonical] = canonical
            for alias in aliases:
                alias_index[str(alias).strip().lower()] = canonical

        for key, value in custom_aliases.items():
            if isinstance(value, (list, tuple, set)):
                canonical = str(key).strip().lower()
                alias_index[canonical] = canonical
                for alias in value:
                    alias_index[str(alias).strip().lower()] = canonical
            else:
                alias_index[str(key).strip().lower()] = str(value).strip().lower()
        return alias_index


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
