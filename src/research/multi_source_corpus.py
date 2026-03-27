"""
多源古籍通路、格式识别与跨站文本交叉验证
"""

import json
import mimetypes
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List

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
    normalized = file_name.lower()
    for format_name, suffixes in FORMAT_RULES.items():
        for suffix in suffixes:
            if normalized.endswith(suffix):
                return format_name

    guessed_type, _ = mimetypes.guess_type(file_name)
    media_type = (content_type or guessed_type or "").lower()
    if "html" in media_type:
        return "html"
    if "xml" in media_type and "tei" in sample_text.lower():
        return "tei_xml"
    if "xml" in media_type:
        return "xml"
    if "pdf" in media_type:
        return "pdf"
    if "json" in media_type:
        return "json"

    stripped = sample_text.strip().lower()
    if stripped.startswith("<tei") or "<teiheader" in stripped:
        return "tei_xml"
    if stripped.startswith("<html") or "<body" in stripped:
        return "html"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"

    return "txt"


def build_source_collection_plan(
    book_title: str,
    path: str = "data/corpus_source_registry.json"
) -> Dict[str, Any]:
    registry = load_source_registry(path)
    sources = registry.get("sources", [])
    routes = []
    for source in sources:
        routes.append(
            {
                "source_id": source.get("id", ""),
                "source_name": source.get("name", ""),
                "base_url": source.get("base_url", ""),
                "collection_modes": source.get("collection_modes", []),
                "supported_formats": source.get("supported_formats", []),
                "implemented": source.get("implemented", False),
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
    witnesses: List[SourceWitness] = []
    for record in records:
        text = record.get("text", "")
        if not text:
            continue
        witnesses.append(
            SourceWitness(
                source_id=record.get("source_id", "unknown"),
                title=record.get("title", ""),
                text=text,
                metadata=record.get("metadata", {})
            )
        )
    return witnesses
