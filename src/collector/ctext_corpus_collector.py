"""
ctext.org 标准语料自动采集模块
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

from src.collector.corpus_bundle import build_document_version_metadata
from src.collector.ctext_whitelist import build_batch_manifest, load_whitelist
from src.common.http_client import HttpClient
from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


class CTextCorpusCollector(BaseModule):
    """基于 ctext API 的古籍语料采集器。"""

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("ctext_corpus_collector", config)
        self.api_base = self.config.get("api_base", "https://api.ctext.org")
        self.timeout_sec = float(self.config.get("timeout_sec", 20))
        self.retry_count = int(self.config.get("retry_count", 2))
        self.retry_backoff_sec = float(self.config.get("retry_backoff_sec", 0.8))
        self.request_interval_sec = float(self.config.get("request_interval_sec", 0.2))
        self.max_depth = int(self.config.get("max_depth", 5))
        self.default_output_dir = self.config.get("output_dir", os.path.join("data", "ctext"))
        self._http: Optional[HttpClient] = None

    def _do_initialize(self) -> bool:
        try:
            self._http = HttpClient(
                timeout=self.timeout_sec,
                max_retries=self.retry_count + 1,
                user_agent=self.config.get(
                    "user_agent",
                    "TCM-AutoResearch-CTextCollector/1.0",
                ),
            )
            self.logger.info("CText 采集器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"CText 采集器初始化失败: {e}")
            return False

    def _do_cleanup(self) -> bool:
        try:
            if self._http:
                self._http.close()
                self._http = None
            return True
        except Exception as e:
            self.logger.error(f"CText 采集器清理失败: {e}")
            return False

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        urns = context.get("ctext_urns", []) or []
        urls = context.get("ctext_urls", []) or []
        use_whitelist = bool(context.get("use_whitelist", False))
        whitelist_path = context.get("whitelist_path")
        whitelist_groups = context.get("whitelist_groups")
        recurse = bool(context.get("recurse", True))
        max_depth = int(context.get("max_depth", self.max_depth))
        output_dir = context.get("output_dir", self.default_output_dir)
        save_to_disk = bool(context.get("save_to_disk", True))

        whitelist_urns: List[str] = []
        whitelist_urls: List[str] = []
        whitelist_entries_by_urn: Dict[str, Dict[str, Any]] = {}
        whitelist_entries_by_url: Dict[str, Dict[str, Any]] = {}
        if use_whitelist:
            whitelist_manifest = self.generate_batch_collection_manifest(
                selected_groups=whitelist_groups,
                whitelist_path=whitelist_path,
                output_file=""
            )
            whitelist_entries = [entry for entry in whitelist_manifest.get("entries", []) if isinstance(entry, dict)]
            whitelist_urns = [entry.get("urn", "") for entry in whitelist_entries if entry.get("urn")]
            whitelist_urls = [entry.get("url", "") for entry in whitelist_entries if entry.get("url")]
            whitelist_entries_by_urn = {
                str(entry.get("urn") or "").strip(): entry
                for entry in whitelist_entries
                if str(entry.get("urn") or "").strip()
            }
            whitelist_entries_by_url = {
                str(entry.get("url") or "").strip(): entry
                for entry in whitelist_entries
                if str(entry.get("url") or "").strip()
            }

        if not urns and not urls and not whitelist_urns and not whitelist_urls:
            raise ValueError("请提供 ctext_urns 或 ctext_urls")

        resolved_url_pairs = self._resolve_urls_to_urn_pairs(urls + whitelist_urls)
        resolved_urns = [item["urn"] for item in resolved_url_pairs]
        for resolved in resolved_url_pairs:
            entry = whitelist_entries_by_url.get(str(resolved.get("url") or "").strip())
            resolved_urn = str(resolved.get("urn") or "").strip()
            if entry and resolved_urn and resolved_urn not in whitelist_entries_by_urn:
                whitelist_entries_by_urn[resolved_urn] = entry
        seed_urns = self._deduplicate_urns(urns + resolved_urns + whitelist_urns)

        visited: Set[str] = set()
        documents: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        for urn in seed_urns:
            try:
                seed_entry = whitelist_entries_by_urn.get(str(urn or "").strip())
                doc = self._collect_urn(
                    urn=urn,
                    recurse=recurse,
                    depth=0,
                    max_depth=max_depth,
                    visited=visited,
                    seed_entry=seed_entry,
                    root_metadata=dict(seed_entry.get("metadata") or {}) if isinstance(seed_entry, dict) else None,
                )
                documents.append(doc)
            except Exception as e:
                errors.append({"urn": urn, "error": str(e)})

        stats = self._build_stats(documents)
        result = {
            "source": "ctext",
            "collected_at": datetime.now().isoformat(),
            "seed_urns": seed_urns,
            "documents": documents,
            "stats": stats,
            "errors": errors
        }

        if save_to_disk:
            output_path = self._save_result(result, output_dir)
            result["output_file"] = output_path

        return result

    def check_api_status(self) -> Dict[str, Any]:
        """检查 ctext API 状态。"""
        return self._request_json("getstatus", {})

    def generate_batch_collection_manifest(
        self,
        selected_groups: Optional[List[str]] = None,
        whitelist_path: Optional[str] = None,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """根据白名单生成批量采集清单并可选落盘。"""
        whitelist = load_whitelist(whitelist_path)
        manifest = build_batch_manifest(whitelist, selected_groups)

        if output_file:
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        return manifest

    def _resolve_urls_to_urns(self, urls: List[str]) -> List[str]:
        return [item["urn"] for item in self._resolve_urls_to_urn_pairs(urls)]

    def _resolve_urls_to_urn_pairs(self, urls: List[str]) -> List[Dict[str, str]]:
        urns: List[str] = []
        resolved_pairs: List[Dict[str, str]] = []
        for url in urls:
            data = self._request_json("readlink", {"url": url})
            urn = data.get("urn")
            if urn:
                urns.append(urn)
                resolved_pairs.append({"url": url, "urn": urn})
            else:
                self.logger.warning(f"无法从 URL 解析 URN: {url}")
        return resolved_pairs

    def _collect_urn(
        self,
        urn: str,
        recurse: bool,
        depth: int,
        max_depth: int,
        visited: Set[str],
        seed_entry: Optional[Dict[str, Any]] = None,
        root_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = urn.strip()
        if not normalized:
            raise ValueError("检测到空 URN")

        if normalized in visited:
            return {
                "urn": normalized,
                "title": "",
                "fulltext": [],
                "text": "",
                "subsections": [],
                "children": [],
                "is_duplicate": True,
                "metadata": dict(root_metadata or {}),
            }

        visited.add(normalized)
        data = self._request_json("gettext", {"urn": normalized})

        title = str(data.get("title") or (seed_entry or {}).get("title") or "").strip()
        fulltext = data.get("fulltext", []) or []
        text_lines = [line for line in fulltext if isinstance(line, str)]
        node_metadata = self._build_ctext_node_metadata(
            normalized,
            title,
            depth=depth,
            seed_entry=seed_entry,
            root_metadata=root_metadata,
        )

        subsection_urns = self._extract_subsection_urns(data.get("subsections", []))
        children: List[Dict[str, Any]] = []
        child_root_metadata = dict(node_metadata if depth == 0 else (root_metadata or node_metadata))
        if recurse and depth < max_depth:
            for sub_urn in subsection_urns:
                try:
                    child = self._collect_urn(
                        urn=sub_urn,
                        recurse=True,
                        depth=depth + 1,
                        max_depth=max_depth,
                        visited=visited,
                        seed_entry=seed_entry,
                        root_metadata=child_root_metadata,
                    )
                    children.append(child)
                except Exception as e:
                    children.append({
                        "urn": sub_urn,
                        "title": "",
                        "fulltext": [],
                        "text": "",
                        "subsections": [],
                        "children": [],
                        "error": str(e),
                        "metadata": dict(child_root_metadata),
                    })

        return {
            "urn": normalized,
            "title": title,
            "fulltext": text_lines,
            "text": "\n".join(text_lines),
            "subsections": subsection_urns,
            "children": children,
            "metadata": node_metadata,
        }

    def _build_ctext_node_metadata(
        self,
        urn: str,
        title: str,
        *,
        depth: int,
        seed_entry: Optional[Dict[str, Any]],
        root_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        inherited_metadata = dict(root_metadata or {})
        seed_metadata = dict(seed_entry.get("metadata") or {}) if isinstance(seed_entry, dict) else {}
        metadata = dict(inherited_metadata)
        if depth == 0:
            metadata.update(seed_metadata)

        root_version_metadata = (
            inherited_metadata.get("version_metadata") if isinstance(inherited_metadata.get("version_metadata"), dict) else {}
        )
        effective_version_metadata = dict(root_version_metadata or {})
        if depth == 0 and isinstance(seed_metadata.get("version_metadata"), dict):
            effective_version_metadata.update(seed_metadata.get("version_metadata") or {})
        if depth > 0:
            for key in ("fragment_key", "work_fragment_key", "version_lineage_key", "witness_key"):
                effective_version_metadata.pop(key, None)
            effective_version_metadata["fragment_title"] = title
        if effective_version_metadata:
            metadata["version_metadata"] = effective_version_metadata

        metadata.setdefault("root_title", str(root_version_metadata.get("work_title") or inherited_metadata.get("root_title") or (seed_entry or {}).get("work_title") or (seed_entry or {}).get("title") or title).strip())
        metadata.setdefault("root_urn", str(root_version_metadata.get("source_ref") or inherited_metadata.get("root_urn") or (seed_entry or {}).get("urn") or urn).strip())
        metadata.setdefault("source_name", "ctext")
        metadata.setdefault("catalog_id", str((seed_entry or {}).get("catalog_id") or metadata.get("catalog_id") or urn).strip())
        metadata["fragment_title"] = title or str(metadata.get("fragment_title") or metadata.get("root_title") or "").strip()
        metadata["node_depth"] = depth
        if isinstance(seed_entry, dict):
            metadata.setdefault("seed_urn", seed_entry.get("urn"))
            metadata.setdefault("seed_title", seed_entry.get("title"))
            metadata.setdefault("seed_priority", seed_entry.get("priority"))

        return build_document_version_metadata(
            title=title or str((seed_entry or {}).get("title") or "").strip(),
            source_type="ctext",
            source_ref=urn,
            metadata=metadata,
        )

    def _extract_subsection_urns(self, subsections: Any) -> List[str]:
        urns: List[str] = []
        if not isinstance(subsections, list):
            return urns

        for item in subsections:
            if isinstance(item, str):
                urns.append(item)
                continue

            if isinstance(item, dict):
                if item.get("urn"):
                    urns.append(item["urn"])
                continue

        return self._deduplicate_urns(urns)

    def _request_json(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._http is None:
            raise RuntimeError("采集器未初始化，请先调用 initialize()")

        url = f"{self.api_base.rstrip('/')}/{endpoint}"
        data = self._http.get_json(url, params=params)
        if not isinstance(data, dict):
            raise ValueError("API 返回不是 JSON 对象")
        if "error" in data:
            raise RuntimeError(f"ctext API 错误: {data['error']}")
        if self.request_interval_sec > 0:
            time.sleep(self.request_interval_sec)
        return data

    def _deduplicate_urns(self, urns: List[str]) -> List[str]:
        seen: Set[str] = set()
        deduped: List[str] = []
        for urn in urns:
            value = (urn or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _save_result(self, result: Dict[str, Any], output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"ctext_corpus_{timestamp}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return output_path

    def _build_stats(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        chapter_count = 0
        line_count = 0
        char_count = 0

        stack = list(documents)
        while stack:
            node = stack.pop()
            chapter_count += 1

            lines = node.get("fulltext", []) or []
            line_count += len(lines)
            char_count += sum(len(line) for line in lines if isinstance(line, str))

            children = node.get("children", []) or []
            stack.extend(children)

        return {
            "document_count": len(documents),
            "chapter_count": chapter_count,
            "line_count": line_count,
            "char_count": char_count
        }
