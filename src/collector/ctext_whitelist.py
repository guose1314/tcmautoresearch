"""
ctext 标准语料白名单配置与批量清单构建工具
"""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.collector.corpus_bundle import build_document_version_metadata

_DEFAULT_CTEXT_WHITELIST_PATH = Path(__file__).resolve().parents[2] / "data" / "ctext_whitelist.json"

_FALLBACK_CTEXT_WHITELIST: Dict[str, Any] = {
    "version": "1.1.0",
    "updated_at": "2026-03-27",
    "groups": {
        "four_books": {
            "name": "四书",
            "items": [
                {"title": "论语", "urn": "ctp:analects", "priority": "high"},
                {"title": "孟子", "urn": "ctp:mengzi", "priority": "high"},
                {"title": "大学", "urn": "ctp:great-learning", "priority": "medium"},
                {"title": "中庸", "urn": "ctp:doctrine-of-the-mean", "priority": "medium"}
            ]
        },
        "five_classics": {
            "name": "五经",
            "items": [
                {"title": "诗经", "urn": "ctp:book-of-poetry", "priority": "medium"},
                {"title": "尚书", "urn": "ctp:book-of-documents", "priority": "medium"},
                {"title": "礼记", "urn": "ctp:book-of-rites", "priority": "medium"},
                {"title": "周易", "urn": "ctp:book-of-changes", "priority": "medium"},
                {"title": "春秋左传", "urn": "ctp:zuo-zhuan", "priority": "low"}
            ]
        },
        "tcm_classics": {
            "name": "中医经典",
            "items": [
                {
                    "title": "黄帝内经·上古天真论",
                    "urn": "ctp:huangdi-neijing/shang-gu-tian-zhen-lun",
                    "url": "https://ctext.org/huangdi-neijing/shang-gu-tian-zhen-lun",
                    "priority": "high"
                },
                {
                    "title": "黄帝内经·四气调神大论",
                    "urn": "ctp:huangdi-neijing/si-qi-diao-shen-da-lun",
                    "url": "https://ctext.org/huangdi-neijing/si-qi-diao-shen-da-lun",
                    "priority": "high"
                },
                {
                    "title": "伤寒论·辨脉法",
                    "urn": "ctp:shang-han-lun/bian-mai-fa",
                    "url": "https://ctext.org/shang-han-lun/bian-mai-fa",
                    "priority": "high"
                },
                {
                    "title": "伤寒论·平脉法",
                    "urn": "ctp:shang-han-lun/ping-mai-fa",
                    "url": "https://ctext.org/shang-han-lun/ping-mai-fa",
                    "priority": "high"
                }
            ]
        }
    }
}


def _normalize_whitelist_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    urn = str(item.get("urn") or "").strip()
    url = str(item.get("url") or "").strip()
    source_ref = urn or url
    if not source_ref:
        return None

    metadata = build_document_version_metadata(
        title=title,
        source_type="ctext",
        source_ref=source_ref,
        metadata={
            **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
            "work_title": item.get("work_title"),
            "fragment_title": item.get("fragment_title") or title,
            "edition": item.get("edition"),
            "author": item.get("author"),
            "dynasty": item.get("dynasty"),
            "catalog_id": item.get("catalog_id") or urn or url,
            "source_name": item.get("source_name") or "ctext",
            "source_type": "ctext",
        },
    )
    version_metadata = dict(metadata.get("version_metadata") or {})

    return {
        **item,
        "title": title,
        "urn": urn,
        "url": url,
        "priority": item.get("priority", "medium"),
        "source_type": "ctext",
        "catalog_id": str(version_metadata.get("catalog_id") or "").strip(),
        "edition": str(version_metadata.get("edition") or "").strip(),
        "author": str(version_metadata.get("author") or "").strip(),
        "dynasty": str(version_metadata.get("dynasty") or "").strip(),
        "work_title": str(version_metadata.get("work_title") or title).strip(),
        "fragment_title": str(version_metadata.get("fragment_title") or title).strip(),
        "metadata": metadata,
        "version_metadata": version_metadata,
    }


def _normalize_whitelist(whitelist: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(whitelist)
    groups = normalized.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError("白名单配置格式无效，缺少 groups")

    for group in groups.values():
        if not isinstance(group, dict):
            continue
        normalized_items: List[Dict[str, Any]] = []
        for item in group.get("items", []) if isinstance(group.get("items"), list) else []:
            normalized_item = _normalize_whitelist_item(item)
            if normalized_item is not None:
                normalized_items.append(normalized_item)
        group["items"] = normalized_items
    return normalized


def _load_default_whitelist() -> Dict[str, Any]:
    try:
        with _DEFAULT_CTEXT_WHITELIST_PATH.open("r", encoding="utf-8") as f:
            return _normalize_whitelist(json.load(f))
    except Exception:
        return _normalize_whitelist(_FALLBACK_CTEXT_WHITELIST)


DEFAULT_CTEXT_WHITELIST: Dict[str, Any] = _load_default_whitelist()


def load_whitelist(path: Optional[str] = None) -> Dict[str, Any]:
    """加载白名单配置，优先使用外部 JSON 文件。"""
    if not path:
        return deepcopy(DEFAULT_CTEXT_WHITELIST)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _normalize_whitelist(data)


def build_batch_manifest(
    whitelist: Dict[str, Any],
    selected_groups: Optional[List[str]] = None
) -> Dict[str, Any]:
    """根据白名单生成批量采集清单。"""
    normalized_whitelist = _normalize_whitelist(whitelist)
    groups = normalized_whitelist.get("groups", {})
    if not isinstance(groups, dict):
        raise ValueError("白名单 groups 必须为对象")

    target_groups = selected_groups or list(groups.keys())
    seen_urns: Set[str] = set()
    seen_urls: Set[str] = set()
    entries: List[Dict[str, Any]] = []

    for group_key, group_name, item in _iter_group_items(groups, target_groups):
        entry = _build_manifest_entry(group_key, group_name, item)
        if not entry:
            continue

        urn = entry.get("urn", "")
        url = entry.get("url", "")
        if _is_duplicate_entry(urn, url, seen_urns, seen_urls):
            continue

        _track_seen_values(urn, url, seen_urns, seen_urls)
        entries.append(entry)

    return {
        "generated_at": datetime.now().isoformat(),
        "whitelist_version": normalized_whitelist.get("version", "unknown"),
        "selected_groups": target_groups,
        "count": len(entries),
        "entries": entries
    }


def _iter_group_items(
    groups: Dict[str, Any],
    target_groups: List[str],
) -> List[tuple[str, str, Any]]:
    items: List[tuple[str, str, Any]] = []
    for group_key in target_groups:
        group_info = groups.get(group_key, {})
        group_name = group_info.get("name", group_key)
        group_items = group_info.get("items", [])
        if not isinstance(group_items, list):
            continue
        for item in group_items:
            items.append((group_key, group_name, item))
    return items


def _build_manifest_entry(group_key: str, group_name: str, item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    urn = (item.get("urn") or "").strip()
    url = (item.get("url") or "").strip()
    if not (urn or url):
        return None

    return {
        "group": group_key,
        "group_name": group_name,
        "title": item.get("title", ""),
        "urn": urn,
        "url": url,
        "priority": item.get("priority", "medium"),
        "source_type": item.get("source_type", "ctext"),
        "catalog_id": item.get("catalog_id", ""),
        "edition": item.get("edition", ""),
        "author": item.get("author", ""),
        "dynasty": item.get("dynasty", ""),
        "work_title": item.get("work_title", item.get("title", "")),
        "fragment_title": item.get("fragment_title", item.get("title", "")),
        "metadata": dict(item.get("metadata") or {}),
        "version_metadata": dict(item.get("version_metadata") or {}),
    }


def _is_duplicate_entry(
    urn: str,
    url: str,
    seen_urns: Set[str],
    seen_urls: Set[str],
) -> bool:
    if urn and urn in seen_urns:
        return True
    if url and url in seen_urls:
        return True
    return False


def _track_seen_values(
    urn: str,
    url: str,
    seen_urns: Set[str],
    seen_urls: Set[str],
) -> None:
    if urn:
        seen_urns.add(urn)
    if url:
        seen_urls.add(url)
