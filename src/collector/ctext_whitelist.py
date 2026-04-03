"""
ctext 标准语料白名单配置与批量清单构建工具
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

DEFAULT_CTEXT_WHITELIST: Dict[str, Any] = {
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


def load_whitelist(path: Optional[str] = None) -> Dict[str, Any]:
    """加载白名单配置，优先使用外部 JSON 文件。"""
    if not path:
        return DEFAULT_CTEXT_WHITELIST

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "groups" not in data:
        raise ValueError("白名单配置格式无效，缺少 groups")

    return data


def build_batch_manifest(
    whitelist: Dict[str, Any],
    selected_groups: Optional[List[str]] = None
) -> Dict[str, Any]:
    """根据白名单生成批量采集清单。"""
    groups = whitelist.get("groups", {})
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
        "whitelist_version": whitelist.get("version", "unknown"),
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
        "priority": item.get("priority", "medium")
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
