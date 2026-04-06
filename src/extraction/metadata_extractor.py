"""文献元数据提取模块 — 从古籍文本中自动识别标题、作者、朝代、出处等元信息。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.extraction.base import (
    ExtractedEntityType,
    ExtractedItem,
    ExtractionRelation,
    ExtractionResult,
    ExtractionRule,
    ExtractionRuleEngine,
    RuleType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 预置正则规则
# ---------------------------------------------------------------------------

_DYNASTY_LIST = (
    "先秦|秦|西汉|东汉|汉|三国|魏|晋|西晋|东晋|南北朝|南朝|北朝|隋|唐|五代|五代十国|"
    "北宋|南宋|宋|辽|金|元|明|清|民国|近代|现代|当代"
)

# 常见古籍文件名/标题元数据模式
_RE_FILENAME_META = re.compile(
    rf"^(?:(\d{{3}})-)?(.+?)[-—–]({_DYNASTY_LIST})[-—–](.+?)(?:\.txt)?$"
)
_RE_TITLE_LINE = re.compile(
    r"^(?:《(.+?)》|【(.+?)】|〈(.+?)〉|「(.+?)」|(.{2,30}?))\s*$"
)
_RE_AUTHOR_LINE = re.compile(
    r"(?:作者|著者|撰|编|辑|纂|录|述)[:：]?\s*(.{1,20})"
)
_RE_DYNASTY_INLINE = re.compile(
    rf"(?:朝代|时代|年代|时期)[:：]?\s*({_DYNASTY_LIST})"
)
_RE_DYNASTY_BRACKET = re.compile(
    rf"[（\(〔【]\s*({_DYNASTY_LIST})\s*[）\)〕】]"
)
_RE_PREFACE_AUTHOR = re.compile(
    rf"({_DYNASTY_LIST})\s*[·・]?\s*(.{{1,10}}?)\s*(?:撰|著|编|辑|纂|述|录)"
)
_RE_VOLUME_MARKER = re.compile(r"[卷篇章节]([一二三四五六七八九十百千\d]+)")
_RE_YEAR_PATTERN = re.compile(r"(?:公元|约)?\s*(\d{{3,4}})\s*年")


def _build_default_metadata_rules() -> List[ExtractionRule]:
    """构建默认元数据提取规则集。"""
    return [
        ExtractionRule(
            rule_id="meta_dynasty_bracket",
            name="朝代(括号)",
            entity_type=ExtractedEntityType.DYNASTY.value,
            rule_type=RuleType.REGEX,
            pattern=rf"[（\(〔【]\s*({_DYNASTY_LIST})\s*[）\)〕】]",
            priority=90,
            confidence_base=0.92,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="meta_dynasty_inline",
            name="朝代(行内)",
            entity_type=ExtractedEntityType.DYNASTY.value,
            rule_type=RuleType.REGEX,
            pattern=rf"(?:朝代|时代|年代|时期)[:：]?\s*({_DYNASTY_LIST})",
            priority=85,
            confidence_base=0.88,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="meta_author_label",
            name="作者(标签)",
            entity_type=ExtractedEntityType.PERSON.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:作者|著者|撰者)[:：]\s*(.{1,20}?)(?:\s|$|[，。,.])",
            priority=88,
            confidence_base=0.90,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="meta_preface_author",
            name="作者(序/朝代·人名)",
            entity_type=ExtractedEntityType.PERSON.value,
            rule_type=RuleType.REGEX,
            pattern=rf"({_DYNASTY_LIST})\s*[·・]?\s*(.{{1,10}}?)\s*(?:撰|著|编|辑|纂|述|录)",
            priority=80,
            confidence_base=0.85,
            group_index=2,
        ),
        ExtractionRule(
            rule_id="meta_book_title_bracket",
            name="书名(书名号)",
            entity_type=ExtractedEntityType.BOOK_TITLE.value,
            rule_type=RuleType.REGEX,
            pattern=r"《(.+?)》",
            priority=92,
            confidence_base=0.95,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="meta_volume",
            name="卷次",
            entity_type=ExtractedEntityType.GENERIC.value,
            rule_type=RuleType.REGEX,
            pattern=r"([卷篇章节])([一二三四五六七八九十百千\d]+)",
            priority=60,
            confidence_base=0.85,
            group_index=0,
        ),
        ExtractionRule(
            rule_id="meta_year",
            name="年代数字",
            entity_type=ExtractedEntityType.DYNASTY.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:公元|约)?\s*(\d{3,4})\s*年",
            priority=70,
            confidence_base=0.80,
            group_index=1,
        ),
    ]


# ---------------------------------------------------------------------------
# 元数据提取器
# ---------------------------------------------------------------------------

class MetadataExtractor:
    """文献元数据提取器。

    职责:
    - 从文本正文和文件名中提取标题、作者、朝代、年代、出处等
    - 支持正则 + 规则引擎双驱动
    - 输出 ExtractionResult
    """

    MODULE_NAME = "metadata_extractor"

    def __init__(self, extra_rules: Optional[List[ExtractionRule]] = None) -> None:
        self._engine = ExtractionRuleEngine()
        self._engine.add_rules(_build_default_metadata_rules())
        if extra_rules:
            self._engine.add_rules(extra_rules)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def extract(
        self,
        text: str,
        source_file: str = "",
        max_scan_chars: int = 3000,
    ) -> ExtractionResult:
        """执行元数据提取。

        Args:
            text: 预处理后的文本
            source_file: 源文件名/路径（可选，用于文件名元数据推断）
            max_scan_chars: 仅扫描前 N 个字符进行元数据搜索
        """
        import time
        t0 = time.perf_counter()
        items: List[ExtractedItem] = []
        relations: List[ExtractionRelation] = []

        # 1) 从文件名推断元数据
        file_meta = self._extract_from_filename(source_file)
        items.extend(file_meta)

        # 2) 扫描文本前部
        scan_text = text[:max_scan_chars] if len(text) > max_scan_chars else text

        # 3) 通过规则引擎匹配
        engine_items = self._engine.apply_regex_rules(scan_text)
        for item in engine_items:
            item.source_module = self.MODULE_NAME
        items.extend(engine_items)

        # 4) 去重合并
        items = self._deduplicate(items)

        # 5) 构建作者-书名关系
        relations.extend(self._build_author_book_relations(items))

        duration = time.perf_counter() - t0
        stats = self._compute_stats(items)

        return ExtractionResult(
            module_name=self.MODULE_NAME,
            items=items,
            relations=relations,
            statistics=stats,
            quality_scores={"metadata_coverage": self._coverage_score(items)},
            duration_sec=duration,
        )

    # ------------------------------------------------------------------
    # 文件名推断
    # ------------------------------------------------------------------

    def _extract_from_filename(self, source_file: str) -> List[ExtractedItem]:
        """从文件名中推断标题、朝代、作者。

        支持格式: ``013-本草纲目-明-李时珍.txt``
        """
        if not source_file:
            return []
        import os
        basename = os.path.splitext(os.path.basename(source_file))[0]
        match = _RE_FILENAME_META.match(basename)
        if not match:
            return []

        _, title, dynasty, author = match.groups()
        items: List[ExtractedItem] = []
        if title:
            items.append(ExtractedItem(
                name=title.strip(),
                entity_type=ExtractedEntityType.BOOK_TITLE.value,
                confidence=0.95,
                source_module=self.MODULE_NAME,
                rule_id="filename_title",
            ))
        if dynasty:
            items.append(ExtractedItem(
                name=dynasty.strip(),
                entity_type=ExtractedEntityType.DYNASTY.value,
                confidence=0.95,
                source_module=self.MODULE_NAME,
                rule_id="filename_dynasty",
            ))
        if author:
            items.append(ExtractedItem(
                name=author.strip(),
                entity_type=ExtractedEntityType.PERSON.value,
                confidence=0.95,
                source_module=self.MODULE_NAME,
                rule_id="filename_author",
            ))
        return items

    # ------------------------------------------------------------------
    # 去重
    # ------------------------------------------------------------------

    def _deduplicate(self, items: List[ExtractedItem]) -> List[ExtractedItem]:
        """按 (name, entity_type) 去重，保留置信度最高的。"""
        best: Dict[str, ExtractedItem] = {}
        for item in items:
            key = f"{item.entity_type}:{item.name}"
            if key not in best or item.confidence > best[key].confidence:
                best[key] = item
        return list(best.values())

    # ------------------------------------------------------------------
    # 关系构建
    # ------------------------------------------------------------------

    def _build_author_book_relations(
        self, items: List[ExtractedItem]
    ) -> List[ExtractionRelation]:
        """作者 → 著作 关系。"""
        authors = [i for i in items if i.entity_type == ExtractedEntityType.PERSON.value]
        books = [i for i in items if i.entity_type == ExtractedEntityType.BOOK_TITLE.value]
        relations: List[ExtractionRelation] = []
        for author in authors:
            for book in books:
                relations.append(ExtractionRelation(
                    source=author.name,
                    target=book.name,
                    relation_type="authored",
                    confidence=min(author.confidence, book.confidence),
                    source_module=self.MODULE_NAME,
                ))
        return relations

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def _compute_stats(self, items: List[ExtractedItem]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for item in items:
            by_type[item.entity_type] = by_type.get(item.entity_type, 0) + 1
        return {"total_items": len(items), "by_type": by_type}

    def _coverage_score(self, items: List[ExtractedItem]) -> float:
        """元数据覆盖率: 0~1, 基于是否提取到标题/作者/朝代。"""
        found_types = {item.entity_type for item in items}
        expected = {
            ExtractedEntityType.BOOK_TITLE.value,
            ExtractedEntityType.PERSON.value,
            ExtractedEntityType.DYNASTY.value,
        }
        return len(found_types & expected) / len(expected) if expected else 0.0
