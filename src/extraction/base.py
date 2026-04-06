"""提取框架基底层 — 规则引擎、提取结果、基类抽取器。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 实体类型扩展枚举
# ---------------------------------------------------------------------------

class ExtractedEntityType(str, Enum):
    """扩展实体类型 — 在原有 6 类基础上新增临床/元数据类型。"""
    HERB = "herb"
    FORMULA = "formula"
    SYNDROME = "syndrome"
    EFFICACY = "efficacy"
    PROPERTY = "property"
    THEORY = "theory"
    DISEASE = "disease"
    SYMPTOM = "symptom"
    ACUPOINT = "acupoint"
    MERIDIAN = "meridian"
    DOSAGE = "dosage"
    PREPARATION = "preparation"       # 炮制/制备方法
    ADMINISTRATION = "administration"  # 用法（内服/外敷等）
    CONTRAINDICATION = "contraindication"
    INDICATION = "indication"
    PERSON = "person"          # 人物（作者/医家）
    DYNASTY = "dynasty"        # 朝代
    BOOK_TITLE = "book_title"  # 书名
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# 提取规则
# ---------------------------------------------------------------------------

class RuleType(str, Enum):
    REGEX = "regex"
    DICTIONARY = "dictionary"
    TEMPLATE = "template"
    LLM = "llm"
    CUSTOM = "custom"


@dataclass
class ExtractionRule:
    """可配置的提取规则。

    Attributes:
        rule_id: 唯一标识
        name: 规则名称
        entity_type: 目标实体类型
        rule_type: 规则类型
        pattern: 正则表达式（rule_type=regex 时必填）
        dictionary_key: 对应词典 key（rule_type=dictionary 时使用）
        template: 模板字符串（rule_type=template 时使用）
        priority: 优先级（越大越先匹配）
        confidence_base: 基础置信度
        enabled: 是否启用
        group_index: 正则捕获组索引
        post_process: 后处理函数名（可选）
        metadata: 附加属性
    """
    rule_id: str
    name: str
    entity_type: str
    rule_type: RuleType = RuleType.REGEX
    pattern: str = ""
    dictionary_key: str = ""
    template: str = ""
    priority: int = 0
    confidence_base: float = 0.80
    enabled: bool = True
    group_index: int = 0
    post_process: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compile_pattern(self) -> Optional[re.Pattern]:
        if self.rule_type == RuleType.REGEX and self.pattern:
            return re.compile(self.pattern, re.UNICODE)
        return None


# ---------------------------------------------------------------------------
# 提取结果
# ---------------------------------------------------------------------------

@dataclass
class ExtractedItem:
    """单条提取记录。"""
    name: str
    entity_type: str
    confidence: float = 0.80
    position: int = 0
    end_position: int = 0
    length: int = 0
    original_text: str = ""
    normalized_name: str = ""
    rule_id: str = ""
    source_module: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "entity_type": self.entity_type,
            "confidence": self.confidence,
            "position": self.position,
            "end_position": self.end_position,
            "length": self.length,
        }
        if self.original_text and self.original_text != self.name:
            d["original_text"] = self.original_text
        if self.normalized_name and self.normalized_name != self.name:
            d["normalized_name"] = self.normalized_name
        if self.rule_id:
            d["rule_id"] = self.rule_id
        if self.source_module:
            d["source_module"] = self.source_module
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class ExtractionRelation:
    """提取的关系记录。"""
    source: str
    target: str
    relation_type: str
    confidence: float = 0.80
    evidence_text: str = ""
    rule_id: str = ""
    source_module: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
        }
        if self.evidence_text:
            d["evidence_text"] = self.evidence_text
        if self.rule_id:
            d["rule_id"] = self.rule_id
        if self.source_module:
            d["source_module"] = self.source_module
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class ExtractionResult:
    """单模块提取结果。"""
    module_name: str
    items: List[ExtractedItem] = field(default_factory=list)
    relations: List[ExtractionRelation] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    quality_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_name": self.module_name,
            "items": [item.to_dict() for item in self.items],
            "relations": [rel.to_dict() for rel in self.relations],
            "statistics": self.statistics,
            "quality_scores": self.quality_scores,
            "warnings": self.warnings,
            "duration_sec": self.duration_sec,
        }


@dataclass
class PipelineResult:
    """整条管道的聚合结果。"""
    document_id: str = ""
    source_file: str = ""
    module_results: Dict[str, ExtractionResult] = field(default_factory=dict)
    all_items: List[ExtractedItem] = field(default_factory=list)
    all_relations: List[ExtractionRelation] = field(default_factory=list)
    overall_quality: Dict[str, Any] = field(default_factory=dict)
    total_duration_sec: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_file": self.source_file,
            "module_results": {k: v.to_dict() for k, v in self.module_results.items()},
            "all_items": [item.to_dict() for item in self.all_items],
            "all_relations": [rel.to_dict() for rel in self.all_relations],
            "overall_quality": self.overall_quality,
            "total_duration_sec": self.total_duration_sec,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# 规则引擎
# ---------------------------------------------------------------------------

class ExtractionRuleEngine:
    """可扩展规则引擎 — 管理和执行 ExtractionRule 集合。"""

    def __init__(self) -> None:
        self._rules: Dict[str, ExtractionRule] = {}
        self._compiled: Dict[str, re.Pattern] = {}
        self._custom_handlers: Dict[str, Callable] = {}

    def add_rule(self, rule: ExtractionRule) -> None:
        self._rules[rule.rule_id] = rule
        if rule.rule_type == RuleType.REGEX and rule.pattern:
            compiled = rule.compile_pattern()
            if compiled:
                self._compiled[rule.rule_id] = compiled

    def add_rules(self, rules: Sequence[ExtractionRule]) -> None:
        for rule in rules:
            self.add_rule(rule)

    def register_custom_handler(self, name: str, handler: Callable) -> None:
        self._custom_handlers[name] = handler

    def remove_rule(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)
        self._compiled.pop(rule_id, None)

    def get_rules(self, entity_type: Optional[str] = None,
                  rule_type: Optional[RuleType] = None) -> List[ExtractionRule]:
        rules = list(self._rules.values())
        if entity_type:
            rules = [r for r in rules if r.entity_type == entity_type]
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        return sorted(rules, key=lambda r: -r.priority)

    def apply_regex_rules(self, text: str,
                          entity_type: Optional[str] = None) -> List[ExtractedItem]:
        """对文本应用所有正则规则，返回提取结果。"""
        items: List[ExtractedItem] = []
        for rule in self.get_rules(entity_type=entity_type, rule_type=RuleType.REGEX):
            if not rule.enabled:
                continue
            compiled = self._compiled.get(rule.rule_id)
            if not compiled:
                continue
            for match in compiled.finditer(text):
                captured = match.group(rule.group_index) if rule.group_index <= len(match.groups()) else match.group(0)
                start, end = match.span(rule.group_index) if rule.group_index <= len(match.groups()) else match.span()
                item = ExtractedItem(
                    name=captured.strip(),
                    entity_type=rule.entity_type,
                    confidence=rule.confidence_base,
                    position=start,
                    end_position=end,
                    length=end - start,
                    original_text=match.group(0),
                    rule_id=rule.rule_id,
                )
                items.append(item)
        return items

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "entity_type": r.entity_type,
                "rule_type": r.rule_type.value,
                "pattern": r.pattern,
                "priority": r.priority,
                "confidence_base": r.confidence_base,
                "enabled": r.enabled,
            }
            for r in sorted(self._rules.values(), key=lambda r: -r.priority)
        ]
