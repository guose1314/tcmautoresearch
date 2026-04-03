"""本地文件语料采集器 — 读取本地目录中的文本文件（.txt 等）

支持编码自动检测：先尝试 UTF-8，失败则按 GB18030/GBK 回退。
输出符合 CorpusBundle schema（schema_version="1.0"），
可与 CText / PDF 来源通过 CorpusBundle.merge() 合并。
"""

from __future__ import annotations

import fnmatch
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.collector.corpus_bundle import (
    CorpusBundle,
    CorpusDocument,
    _make_bundle_id,
    _make_doc_id,
)
from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

# 默认编码尝试顺序（适应中医古籍文件的编码多样性）
_DEFAULT_ENCODING_FALLBACKS = ["utf-8", "gb18030", "gbk", "utf-8-sig"]
_DEFAULT_FILE_GLOB = "*.txt"
_DEFAULT_MAX_FILES = 50


class LocalCorpusCollector(BaseModule):
    """从本地目录采集文本文件，输出 CorpusBundle dict。

    配置项（config dict 字段）：

    * ``data_dir``: 扫描目录，默认 "data"
    * ``file_glob``: 文件通配符，默认 "*.txt"
    * ``max_files``: 最多采集文件数，默认 50
    * ``encoding_fallbacks``: 编码尝试列表，默认 UTF-8 → GB18030 → GBK
    * ``recursive``: 是否递归子目录，默认 False
    * ``min_text_length``: 低于此字符数的文件跳过，默认 50

    context（_do_execute 参数）优先级高于 config，可覆盖 data_dir 等。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("local_corpus_collector", config)
        self.data_dir: str = self.config.get("data_dir", "data")
        self.file_glob: str = self.config.get("file_glob", _DEFAULT_FILE_GLOB)
        self.max_files: int = int(self.config.get("max_files", _DEFAULT_MAX_FILES))
        self.encoding_fallbacks: List[str] = (
            self.config.get("encoding_fallbacks") or _DEFAULT_ENCODING_FALLBACKS
        )
        self.recursive: bool = bool(self.config.get("recursive", False))
        self.min_text_length: int = int(self.config.get("min_text_length", 50))

    def _do_initialize(self) -> bool:
        if not os.path.isdir(self.data_dir):
            self.logger.warning("LocalCorpusCollector: data_dir '%s' 不存在，初始化时仅警告", self.data_dir)
        return True

    def _do_cleanup(self) -> bool:
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        data_dir = context.get("data_dir", self.data_dir)
        file_glob = context.get("file_glob", self.file_glob)
        max_files = int(context.get("max_files", self.max_files))
        recursive = bool(context.get("recursive", self.recursive))
        exclude_patterns: List[str] = context.get("exclude_patterns") or []
        include_paths: List[str] = context.get("include_paths") or []

        if not os.path.isdir(data_dir):
            raise ValueError(f"LocalCorpusCollector: data_dir '{data_dir}' 不是有效目录")

        file_paths = self._scan_files(data_dir, file_glob, recursive)
        if include_paths:
            file_paths = [p for p in file_paths if p in include_paths]
        if exclude_patterns:
            file_paths = [
                p for p in file_paths
                if not any(fnmatch.fnmatch(os.path.basename(p), pat) for pat in exclude_patterns)
            ]
        file_paths = file_paths[:max_files]

        collected_at = datetime.now().isoformat()
        documents: List[CorpusDocument] = []
        errors: List[Dict[str, str]] = []

        for path in file_paths:
            try:
                text, encoding_used = self._read_text(path)
                if len(text) < self.min_text_length:
                    continue
                title = _infer_title(path)
                doc = CorpusDocument(
                    doc_id=_make_doc_id("local", path),
                    title=title,
                    text=text,
                    source_type="local",
                    source_ref=path,
                    language="zh",
                    metadata={
                        "file_name": os.path.basename(path),
                        "encoding": encoding_used,
                        "file_size": os.path.getsize(path),
                    },
                    collected_at=collected_at,
                )
                documents.append(doc)
            except Exception as exc:
                errors.append({"source_ref": path, "error": str(exc)})
                self.logger.warning("读取文件失败 '%s': %s", path, exc)

        stats = {
            "total_documents": len(documents),
            "total_chars": sum(len(d.text) for d in documents),
            "source_type": "local",
            "scanned_files": len(file_paths),
            "error_count": len(errors),
        }
        bundle_id = _make_bundle_id(["local"], collected_at)
        bundle = CorpusBundle(
            bundle_id=bundle_id,
            sources=["local"],
            documents=documents,
            collected_at=collected_at,
            stats=stats,
            errors=errors,
        )
        return bundle.to_dict()

    # ── 内部工具 ──────────────────────────────────────────────────────────── #

    def _scan_files(self, data_dir: str, file_glob: str, recursive: bool) -> List[str]:
        """扫描目录，返回匹配文件的绝对路径列表（按文件名排序）。"""
        matched: List[str] = []
        if recursive:
            for root, _dirs, files in os.walk(data_dir):
                for fname in files:
                    if fnmatch.fnmatch(fname, file_glob):
                        matched.append(os.path.join(root, fname))
        else:
            try:
                entries = os.listdir(data_dir)
            except OSError as e:
                raise ValueError(f"无法列出目录 '{data_dir}': {e}") from e
            for fname in entries:
                if fnmatch.fnmatch(fname, file_glob):
                    matched.append(os.path.join(data_dir, fname))
        matched.sort()
        return matched

    def _read_text(self, path: str) -> tuple[str, str]:
        """读取文件，返回 (text, encoding_used)。按 encoding_fallbacks 顺序尝试。"""
        for enc in self.encoding_fallbacks:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    return f.read().strip(), enc
            except (UnicodeDecodeError, LookupError):
                continue
        # 最后回退：忽略无法解码的字符
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip(), "utf-8-replace"


def _infer_title(path: str) -> str:
    """从文件名推断标题（去掉扩展名及前缀序号）。

    示例::

        "013-本草纲目-明-李时珍.txt" → "本草纲目-明-李时珍"
        "金匮要略.txt"               → "金匮要略"
    """
    name = os.path.splitext(os.path.basename(path))[0]
    # 去掉类似 "013-" 的数字前缀
    if len(name) > 4 and name[:3].isdigit() and name[3] == "-":
        name = name[4:]
    return name
