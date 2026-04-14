"""
多源古籍通路、格式识别与跨站文本交叉验证
"""

import json
import mimetypes
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List

from src.collector.corpus_bundle import build_document_version_metadata

FORMAT_RULES = {
    "tei_xml": [".tei", ".tei.xml"],
    "xml": [".xml"],
    "html": [".html", ".htm"],
    "txt": [".txt"],
    "markdown": [".md", ".markdown"],
    "json": [".json"],
    "pdf": [".pdf"],
    "epub": [".epub"],
    "djvu": [".djvu"],
    "iiif_manifest": ["manifest.json"],
    "image_scan": [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"],
    "image_ocr": [".alto.xml"]
}


@dataclass
class SourceWitness:
    source_id: str
    title: str
    text: str
    metadata: Dict[str, Any]


def load_source_registry(path: str = "data/corpus_source_registry.json") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "sources" not in data:
        raise ValueError("source registry 格式无效")
    return data


def recognize_classical_format(
    file_name: str = "",
    content_type: str = "",
    sample_text: str = ""
) -> str:
    by_suffix = _recognize_by_suffix(file_name)
    if by_suffix:
        return by_suffix

    by_media_type = _recognize_by_media_type(file_name, content_type, sample_text)
    if by_media_type:
        return by_media_type

    by_sample_text = _recognize_by_sample_text(sample_text)
    if by_sample_text:
        return by_sample_text
    return "txt"


def _recognize_by_suffix(file_name: str) -> str:
    normalized = file_name.lower()
    for format_name, suffixes in FORMAT_RULES.items():
        for suffix in suffixes:
            if normalized.endswith(suffix):
                return format_name
    return ""


def _recognize_by_media_type(file_name: str, content_type: str, sample_text: str) -> str:
    guessed_type, _ = mimetypes.guess_type(file_name)
    media_type = (content_type or guessed_type or "").lower()
    if "html" in media_type:
        return "html"
    if "xml" in media_type:
        return "tei_xml" if "tei" in sample_text.lower() else "xml"
    if "pdf" in media_type:
        return "pdf"
    if "json" in media_type:
        return "json"
    return ""


def _recognize_by_sample_text(sample_text: str) -> str:
    stripped = sample_text.strip().lower()
    if stripped.startswith("<tei") or "<teiheader" in stripped:
        return "tei_xml"
    if stripped.startswith("<html") or "<body" in stripped:
        return "html"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    return ""


def build_source_collection_plan(
    book_title: str,
    path: str = "data/corpus_source_registry.json"
) -> Dict[str, Any]:
    registry = load_source_registry(path)
    sources = registry.get("sources", [])
    routes = []
    for source in sources:
        version_defaults = _extract_source_version_defaults(source)
        routes.append(
            {
                "source_id": source.get("id", ""),
                "source_name": source.get("name", ""),
                "base_url": source.get("base_url", ""),
                "collection_modes": source.get("collection_modes", []),
                "supported_formats": source.get("supported_formats", []),
                "implemented": source.get("implemented", False),
                "catalog_id": version_defaults.get("catalog_id", ""),
                "edition": version_defaults.get("edition", ""),
                "author": version_defaults.get("author", ""),
                "dynasty": version_defaults.get("dynasty", ""),
                "version_metadata_defaults": version_defaults,
                "recommended_query": book_title
            }
        )
    return {
        "title": book_title,
        "route_count": len(routes),
        "routes": routes
    }


def cross_validate_witnesses(
    witnesses: List[SourceWitness],
    similarity_threshold: float = 0.75
) -> Dict[str, Any]:
    if not witnesses:
        return {
            "witness_count": 0,
            "pairwise_scores": [],
            "consistency_score": 0.0,
            "high_consistency_pairs": [],
            "warnings": ["无可用见证文本"]
        }

    pairwise_scores: List[Dict[str, Any]] = []
    high_consistency_pairs: List[Dict[str, Any]] = []
    total_ratio = 0.0
    comparisons = 0

    for index, left in enumerate(witnesses):
        for right in witnesses[index + 1:]:
            ratio = SequenceMatcher(None, left.text, right.text).ratio()
            record = {
                "left": left.source_id,
                "right": right.source_id,
                "similarity": ratio
            }
            pairwise_scores.append(record)
            total_ratio += ratio
            comparisons += 1
            if ratio >= similarity_threshold:
                high_consistency_pairs.append(record)

    consistency_score = total_ratio / comparisons if comparisons else 1.0
    warnings = []
    if comparisons and consistency_score < similarity_threshold:
        warnings.append("跨站文本差异较大，建议人工复核版本与断句")

    return {
        "witness_count": len(witnesses),
        "pairwise_scores": pairwise_scores,
        "consistency_score": consistency_score,
        "high_consistency_pairs": high_consistency_pairs,
        "warnings": warnings
    }


def build_witnesses_from_records(records: List[Dict[str, Any]]) -> List[SourceWitness]:
    try:
        registry = load_source_registry()
        source_index = {
            str(source.get("id") or "").strip(): source
            for source in registry.get("sources", [])
            if isinstance(source, dict) and str(source.get("id") or "").strip()
        }
    except Exception:
        source_index = {}

    witnesses: List[SourceWitness] = []
    for record in records:
        text = record.get("text", "")
        if not text:
            continue
        source_id = str(record.get("source_id", "unknown") or "unknown").strip() or "unknown"
        source_defaults = _extract_source_version_defaults(source_index.get(source_id) or {})
        metadata = dict(source_defaults)
        record_metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        metadata.update(record_metadata)
        for field in ("catalog_id", "edition", "author", "dynasty", "work_title", "fragment_title"):
            if field in record and record.get(field) not in (None, ""):
                metadata[field] = record.get(field)
        source_ref = str(
            record.get("source_ref")
            or record.get("urn")
            or metadata.get("source_ref")
            or (source_index.get(source_id) or {}).get("base_url")
            or source_id
        ).strip()
        metadata = build_document_version_metadata(
            title=str(record.get("title") or "").strip(),
            source_type=source_id,
            source_ref=source_ref,
            metadata=metadata,
        )
        witnesses.append(
            SourceWitness(
                source_id=source_id,
                title=record.get("title", ""),
                text=text,
                metadata=metadata,
            )
        )
    return witnesses


def _extract_source_version_defaults(source: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(source.get("id") or "").strip()
    catalog_id = str(source.get("catalog_id") or source_id).strip()
    return {
        "catalog_id": catalog_id,
        "edition": str(source.get("edition") or "").strip(),
        "author": str(source.get("author") or "").strip(),
        "dynasty": str(source.get("dynasty") or "").strip(),
        "source_name": str(source.get("name") or source_id).strip(),
        "source_type": source_id,
    }
