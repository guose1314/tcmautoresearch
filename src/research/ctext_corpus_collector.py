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

from src.core.module_base import BaseModule
from src.research.ctext_whitelist import build_batch_manifest, load_whitelist

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
        self.session: Optional[requests.Session] = None

    def _do_initialize(self) -> bool:
        try:
            self.session = requests.Session()
            self.logger.info("CText 采集器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"CText 采集器初始化失败: {e}")
            return False

    def _do_cleanup(self) -> bool:
        try:
            if self.session:
                self.session.close()
                self.session = None
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
        if use_whitelist:
            whitelist_manifest = self.generate_batch_collection_manifest(
                selected_groups=whitelist_groups,
                whitelist_path=whitelist_path,
                output_file=""
            )
            whitelist_urns = [entry.get("urn", "") for entry in whitelist_manifest.get("entries", []) if entry.get("urn")]
            whitelist_urls = [entry.get("url", "") for entry in whitelist_manifest.get("entries", []) if entry.get("url")]

        if not urns and not urls and not whitelist_urns and not whitelist_urls:
            raise ValueError("请提供 ctext_urns 或 ctext_urls")

        resolved_urns = self._resolve_urls_to_urns(urls + whitelist_urls)
        seed_urns = self._deduplicate_urns(urns + resolved_urns + whitelist_urns)

        visited: Set[str] = set()
        documents: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        for urn in seed_urns:
            try:
                doc = self._collect_urn(urn=urn, recurse=recurse, depth=0, max_depth=max_depth, visited=visited)
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
        urns: List[str] = []
        for url in urls:
            data = self._request_json("readlink", {"url": url})
            urn = data.get("urn")
            if urn:
                urns.append(urn)
            else:
                self.logger.warning(f"无法从 URL 解析 URN: {url}")
        return urns

    def _collect_urn(
        self,
        urn: str,
        recurse: bool,
        depth: int,
        max_depth: int,
        visited: Set[str]
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
                "is_duplicate": True
            }

        visited.add(normalized)
        data = self._request_json("gettext", {"urn": normalized})

        title = data.get("title", "")
        fulltext = data.get("fulltext", []) or []
        text_lines = [line for line in fulltext if isinstance(line, str)]

        subsection_urns = self._extract_subsection_urns(data.get("subsections", []))
        children: List[Dict[str, Any]] = []
        if recurse and depth < max_depth:
            for sub_urn in subsection_urns:
                try:
                    child = self._collect_urn(
                        urn=sub_urn,
                        recurse=True,
                        depth=depth + 1,
                        max_depth=max_depth,
                        visited=visited
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
                        "error": str(e)
                    })

        return {
            "urn": normalized,
            "title": title,
            "fulltext": text_lines,
            "text": "\n".join(text_lines),
            "subsections": subsection_urns,
            "children": children
        }

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
        if self.session is None:
            raise RuntimeError("采集器未初始化，请先调用 initialize()")

        url = f"{self.api_base.rstrip('/')}/{endpoint}"
        last_error: Optional[Exception] = None

        for attempt in range(self.retry_count + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_sec)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("API 返回不是 JSON 对象")
                if "error" in data:
                    raise RuntimeError(f"ctext API 错误: {data['error']}")
                if self.request_interval_sec > 0:
                    time.sleep(self.request_interval_sec)
                return data
            except Exception as e:
                last_error = e
                if attempt < self.retry_count:
                    backoff = self.retry_backoff_sec * (attempt + 1)
                    time.sleep(backoff)

        raise RuntimeError(f"请求 ctext API 失败: {endpoint}, params={params}, error={last_error}")

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
