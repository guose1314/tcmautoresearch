# src/infra/lexicon_service.py
"""
LexiconService — 从外部 JSONL 文件加载 TCM 词典

职责
----
* 持有 ``data/tcm_lexicon.jsonl`` 的路径（可通过环境变量或参数覆盖）。
* 将 JSONL 词条解析为按 category 分组的 ``Set[str]``。
* 提供与旧 ``TCMLexicon`` 完全兼容的属性和方法，使上层代码无需改写。
* 支持运行时追加词条（``add_words``）和加载外部词典文件。
* 支持 JSONL 热加载：当源文件变化时自动刷新内存词典。

JSONL 格式（每行一个 JSON 对象）::

    {"term": "人参", "category": "herb"}
    {"term": "四君子汤", "category": "formula"}
    ...

合法 category 值: herb / formula / syndrome / theory / efficacy / common
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 默认 JSONL 路径（相对于项目根目录；可被环境变量 TCM_LEXICON_PATH 覆盖）
_DEFAULT_JSONL = Path(__file__).resolve().parents[2] / "data" / "tcm_lexicon.jsonl"
_DEFAULT_SYNONYMS_JSONL = Path(__file__).resolve().parents[2] / "data" / "tcm_synonyms.jsonl"

# 合法分类 → TCMLexicon 属性名映射
_CATEGORY_TO_ATTR: dict[str, str] = {
    "herb": "herbs",
    "formula": "formulas",
    "syndrome": "syndromes",
    "theory": "theory",
    "efficacy": "efficacy",
    "common": "common_words",
}
_ATTR_TO_CATEGORY: dict[str, str] = {value: key for key, value in _CATEGORY_TO_ATTR.items()}


class LexiconService:
    """
    TCM 词典服务 — 数据源为 ``data/tcm_lexicon.jsonl``。

    完全替代原 ``TCMLexicon``，属性和方法签名保持向后兼容：
    ``herbs / formulas / syndromes / theory / efficacy / common_words``
    均为 ``Set[str]``，其他方法名称不变。
    """

    def __init__(self, jsonl_path: Optional[str | Path] = None):
        path_str = os.environ.get("TCM_LEXICON_PATH") or jsonl_path
        self._jsonl_path: Path = Path(path_str) if path_str else _DEFAULT_JSONL
        synonyms_str = os.environ.get("TCM_SYNONYMS_PATH")
        self._synonyms_path: Path = Path(synonyms_str) if synonyms_str else _DEFAULT_SYNONYMS_JSONL

        # 分类词集（与旧 TCMLexicon 属性名完全一致）
        self.herbs: Set[str] = set()
        self.formulas: Set[str] = set()
        self.syndromes: Set[str] = set()
        self.theory: Set[str] = set()
        self.efficacy: Set[str] = set()
        self.common_words: Set[str] = set()

        # 同义词映射: alias → (canonical, category)
        self._synonym_map: Dict[str, Tuple[str, str]] = {}

        self._all_words: Optional[Set[str]] = None  # 延迟聚合缓存
        self._source_signature: Optional[Tuple[int, int, str]] = None  # (mtime_ns, file_size, sha1)
        self._last_check_ts: float = 0.0
        self._reload_check_interval_sec: float = 0.5

        self._load_jsonl(reset=True)

    # ── 内部加载 ─────────────────────────────────────────────────────────

    def _load_jsonl(self, *, reset: bool = False) -> None:
        """读取 JSONL 文件，将每条记录按 category 分配到对应集合。"""
        if reset:
            self._clear_all_collections()

        if not self._jsonl_path.exists():
            logger.warning(
                "TCM 词典文件不存在: %s，词典将保持空。"
                "（可通过环境变量 TCM_LEXICON_PATH 指定路径）",
                self._jsonl_path,
            )
            self._source_signature = None
            self._all_words = None
            return

        staged = {
            "herbs": set(),
            "formulas": set(),
            "syndromes": set(),
            "theory": set(),
            "efficacy": set(),
            "common_words": set(),
        }

        loaded = 0
        skipped = 0
        with open(self._jsonl_path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    obj = json.loads(raw)
                    term = str(obj.get("term", "")).strip()
                    category = str(obj.get("category", "")).strip()
                    if not term or category not in _CATEGORY_TO_ATTR:
                        skipped += 1
                        continue
                    attr = _CATEGORY_TO_ATTR[category]
                    staged[attr].add(term)
                    loaded += 1
                except json.JSONDecodeError as exc:
                    logger.warning("第 %d 行 JSON 解析失败（已跳过）: %s", lineno, exc)
                    skipped += 1

        self.herbs = staged["herbs"]
        self.formulas = staged["formulas"]
        self.syndromes = staged["syndromes"]
        self.theory = staged["theory"]
        self.efficacy = staged["efficacy"]
        self.common_words = staged["common_words"]
        self._all_words = None
        self._source_signature = self._get_source_signature()

        logger.info(
            "TCM 词典加载完成: %d 词条（跳过 %d），来源 %s",
            loaded, skipped, self._jsonl_path,
        )
        self._load_synonyms()

    def _load_synonyms(self) -> None:
        """加载同义词映射文件 (tcm_synonyms.jsonl)。"""
        self._synonym_map.clear()
        if not self._synonyms_path.exists():
            return
        loaded = 0
        try:
            with open(self._synonyms_path, encoding="utf-8") as fh:
                for lineno, raw in enumerate(fh, 1):
                    raw = raw.strip()
                    if not raw or raw.startswith("#"):
                        continue
                    try:
                        obj = json.loads(raw)
                        alias = str(obj.get("alias", "")).strip()
                        canonical = str(obj.get("canonical", "")).strip()
                        category = str(obj.get("category", "")).strip()
                        if alias and canonical and category in _CATEGORY_TO_ATTR:
                            self._synonym_map[alias] = (canonical, category)
                            loaded += 1
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            logger.warning("同义词文件加载失败 (%s): %s", self._synonyms_path, exc)
        if loaded:
            self._all_words = None
            logger.info("同义词映射加载完成: %d 条，来源 %s", loaded, self._synonyms_path)

    def _clear_all_collections(self) -> None:
        self.herbs.clear()
        self.formulas.clear()
        self.syndromes.clear()
        self.theory.clear()
        self.efficacy.clear()
        self.common_words.clear()
        self._all_words = None

    def _get_source_signature(self) -> Optional[Tuple[int, int, str]]:
        if not self._jsonl_path.exists():
            return None
        stat = self._jsonl_path.stat()
        digest = hashlib.sha1(self._jsonl_path.read_bytes()).hexdigest()
        return int(stat.st_mtime_ns), int(stat.st_size), digest

    def refresh_if_needed(self, *, force: bool = False) -> bool:
        """检测 JSONL 是否变化，若变化则热加载。返回是否发生重载。"""
        now = time.monotonic()
        if not force and (now - self._last_check_ts) < self._reload_check_interval_sec:
            return False
        self._last_check_ts = now

        current_sig = self._get_source_signature()
        if not force and current_sig == self._source_signature:
            return False

        logger.info("检测到词典文件变化，触发热加载: %s", self._jsonl_path)
        self._load_jsonl(reset=True)
        return True

    def reload(self) -> None:
        """显式重载词典。"""
        self.refresh_if_needed(force=True)

    # ── 词典查询接口（与旧 TCMLexicon 完全兼容）────────────────────────

    def get_vocab_size(self) -> int:
        """返回全部词汇总数（各分类集合大小之和）。"""
        self.refresh_if_needed()
        return (
            len(self.herbs)
            + len(self.formulas)
            + len(self.syndromes)
            + len(self.theory)
            + len(self.efficacy)
            + len(self.common_words)
        )

    def get_all_words(self) -> Set[str]:
        """返回所有词汇的并集（含同义词别名，结果被缓存）。"""
        self.refresh_if_needed()
        if self._all_words is None:
            self._all_words = (
                self.herbs
                | self.formulas
                | self.syndromes
                | self.theory
                | self.efficacy
                | self.common_words
                | set(self._synonym_map.keys())
            )
        return self._all_words

    def contains(self, word: str) -> bool:
        """词典中是否包含该词。"""
        return word in self.get_all_words()

    def get_word_type(self, word: str) -> Optional[str]:
        """返回词的分类名（同义词自动解析到标准词），未找到时返回 ``None``。"""
        self.refresh_if_needed()
        for category, attr in _CATEGORY_TO_ATTR.items():
            if word in getattr(self, attr):
                return category
        # 同义词回退
        entry = self._synonym_map.get(word)
        if entry is not None:
            return entry[1]  # category
        return None

    def resolve_synonym(self, word: str) -> Tuple[str, Optional[str]]:
        """将别名解析为标准名 + 分类。若非同义词则返回原词 + 分类（可能为 None）。"""
        entry = self._synonym_map.get(word)
        if entry is not None:
            return entry  # (canonical, category)
        return word, self.get_word_type(word)

    def lookup(self, word: str) -> Optional[Dict[str, str]]:
        """查询词汇，返回类型与属性字典；未找到时返回 ``None``。

        Returns
        -------
        dict
            ``{"word": word, "type": category, "category": category}``
        None
            词典中不存在该词时返回 ``None``。
        """
        category = self.get_word_type(word)
        if category is None:
            return None
        return {"word": word, "type": category, "category": category}

    def get_word_info(self, word: str) -> Optional[Dict[str, str]]:
        """兼容旧接口：返回词条信息。"""
        return self.lookup(word)

    def get_words_by_type(self, word_type: str) -> List[str]:
        """兼容旧接口：按类型获取词汇列表。"""
        self.refresh_if_needed()
        attr = _CATEGORY_TO_ATTR.get(word_type, word_type)
        words = getattr(self, attr, set())
        if isinstance(words, set):
            return list(words)
        return []

    def get_types(self) -> List[str]:
        """兼容旧接口：返回可用类型列表。"""
        return list(_CATEGORY_TO_ATTR.keys())

    # ── 词典写操作 ───────────────────────────────────────────────────────

    def add_words(self, word_type: str, words: List[str]) -> None:
        """
        运行时向指定分类追加词汇（只影响内存，不写回 JSONL 文件）。

        Parameters
        ----------
        word_type :
            分类名，可为 category 原始值（如 ``"herb"``）或旧属性名（如 ``"herbs"``）。
        words :
            要追加的词列表。
        """
        # 同时支持 "herb" 和 "herbs" 两种写法
        attr = _CATEGORY_TO_ATTR.get(word_type, word_type)
        target: Optional[Set[str]] = getattr(self, attr, None)
        if target is None:
            logger.warning("未知 word_type: %s，忽略追加。", word_type)
            return
        target.update(words)
        self._all_words = None  # 清除并集缓存

    def load_from_file(self, filepath: str, word_type: str = "common") -> int:
        """
        从外部文本文件追加词汇（每行一个词；支持带空格的多列格式，取第一列）。

        与旧 ``TCMLexicon.load_from_file`` 签名完全相同。
        """
        loaded_count = 0
        p = Path(filepath)
        if not p.exists():
            logger.warning("外部词典文件不存在: %s", filepath)
            return 0
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    word = line.split()[0]
                    self.add_words(word_type, [word])
                    loaded_count += 1
            logger.info("从 %s 加载了 %d 个 %s 词汇", filepath, loaded_count, word_type)
        except Exception as exc:
            logger.error("加载词典文件失败 (%s): %s", filepath, exc)
        return loaded_count

    def load_from_jieba_user_dict(self, filepath: str) -> int:
        """兼容接口：等同于 ``load_from_file(filepath, word_type='common')``。"""
        return self.load_from_file(filepath, word_type="common")

    def export_to_jieba_format(self, filepath: str, word_type: str = "common") -> None:
        """将指定分类词汇导出为 jieba 用户词典格式（词 词频 词性）。"""
        attr = _CATEGORY_TO_ATTR.get(word_type, word_type)
        word_set: Set[str] = getattr(self, attr, set())
        try:
            with open(filepath, "w", encoding="utf-8") as fh:
                for word in sorted(word_set):
                    fh.write(f"{word} 1000 n\n")
            logger.info("导出 %d 个 %s 词汇到 %s", len(word_set), word_type, filepath)
        except Exception as exc:
            logger.error("导出词典失败: %s", exc)


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_global_service: Optional[LexiconService] = None


def get_lexicon() -> LexiconService:
    """
    返回全局 ``LexiconService`` 单例。

    首次调用时从 ``data/tcm_lexicon.jsonl`` 加载数据；后续调用直接返回已有实例。
    可通过环境变量 ``TCM_LEXICON_PATH`` 覆盖 JSONL 路径（在首次调用前设置方生效）。
    """
    global _global_service
    if _global_service is None:
        _global_service = LexiconService()
    return _global_service


def reset_lexicon() -> None:
    """清除全局单例（主要供测试使用）。"""
    global _global_service
    _global_service = None
