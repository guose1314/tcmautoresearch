"""医学内容要素解析模块 — 从古籍文本中提取方剂组成、主治、功效、炮制、用法等。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.data.tcm_lexicon import get_lexicon
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
# 医学内容专用正则
# ---------------------------------------------------------------------------

_RE_FORMULA_COMPOSITION = re.compile(
    r"(?:组成|方药|药物组成|处方|方剂组成|用药)[:：]\s*(.+?)(?:[。\n]|$)"
)
_RE_FORMULA_INDICATION = re.compile(
    r"(?:主治|治|疗|主|功用|适用于|用治)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_FORMULA_EFFICACY = re.compile(
    r"(?:功效|功能|功用|效用|功能主治)[:：]\s*(.+?)(?:[。\n]|$)"
)
_RE_PREPARATION = re.compile(
    r"(?:炮制|制法|修治|修制|炮炙)[:：]\s*(.+?)(?:[。\n]|$)"
)
_RE_ADMINISTRATION = re.compile(
    r"(?:用法|服法|用法用量|服用方法)[:：]\s*(.+?)(?:[。\n]|$)"
)
_RE_CONTRAINDICATION = re.compile(
    r"(?:禁忌|忌|不宜|慎用|忌用|不可|勿)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_DOSAGE_BLOCK = re.compile(
    r"(?:用量|剂量|各?\s*\d+\s*[克两钱分升])"
)
_RE_HERB_DOSAGE = re.compile(
    r"([\u4e00-\u9fff]{2,6})\s*[（\(]?\s*(\d+(?:\.\d+)?)\s*([克两钱分升斤毫升])\s*[）\)]?"
)
_RE_HERB_ROLE = re.compile(
    r"(?:君药?|臣药?|佐药?|使药?)[:：]?\s*(.+?)(?:[，。；\n]|$)"
)


def _build_medical_content_rules() -> List[ExtractionRule]:
    return [
        ExtractionRule(
            rule_id="med_composition",
            name="方剂组成",
            entity_type=ExtractedEntityType.FORMULA.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:组成|方药|药物组成|处方)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=90,
            confidence_base=0.88,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="med_indication",
            name="主治病证",
            entity_type=ExtractedEntityType.INDICATION.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:主治|治|主)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=88,
            confidence_base=0.85,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="med_efficacy",
            name="功效描述",
            entity_type=ExtractedEntityType.EFFICACY.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:功效|功能|功用|效用|功能主治)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=85,
            confidence_base=0.87,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="med_preparation",
            name="炮制方法",
            entity_type=ExtractedEntityType.PREPARATION.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:炮制|制法|修治|修制|炮炙)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=80,
            confidence_base=0.85,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="med_administration",
            name="用法用量",
            entity_type=ExtractedEntityType.ADMINISTRATION.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:用法|服法|用法用量|服用方法)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=78,
            confidence_base=0.82,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="med_contraindication",
            name="禁忌事项",
            entity_type=ExtractedEntityType.CONTRAINDICATION.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:禁忌|忌|不宜|慎用|忌用)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=82,
            confidence_base=0.80,
            group_index=1,
        ),
    ]


# ---------------------------------------------------------------------------
# 医学内容提取器
# ---------------------------------------------------------------------------

class MedicalContentExtractor:
    """医学内容要素解析器。

    从古籍文本中提取:
    - 方剂组成（药材列表 + 剂量）
    - 主治病证 / 功效
    - 炮制方法
    - 用法用量
    - 禁忌
    - 实体之间的关系（方剂→中药、方剂→证候等）
    """

    MODULE_NAME = "medical_content_extractor"

    def __init__(self, extra_rules: Optional[List[ExtractionRule]] = None) -> None:
        self._lexicon = get_lexicon()
        self._engine = ExtractionRuleEngine()
        self._engine.add_rules(_build_medical_content_rules())
        if extra_rules:
            self._engine.add_rules(extra_rules)

    def extract(self, text: str, entities: Optional[List[Dict[str, Any]]] = None) -> ExtractionResult:
        """执行医学内容提取。

        Args:
            text: 预处理后的文本
            entities: 上游 entity_extractor 已识别的实体列表（可选）
        """
        import time
        t0 = time.perf_counter()
        items: List[ExtractedItem] = []
        relations: List[ExtractionRelation] = []

        # 1) 通过规则引擎做结构化段落提取
        engine_items = self._engine.apply_regex_rules(text)
        for item in engine_items:
            item.source_module = self.MODULE_NAME
        items.extend(engine_items)

        # 2) 提取药物-剂量配对
        dosage_items, dosage_rels = self._extract_herb_dosage_pairs(text)
        items.extend(dosage_items)
        relations.extend(dosage_rels)

        # 3) 提取方剂→药物组成关系
        composition_relations = self._extract_composition_relations(text, entities)
        relations.extend(composition_relations)

        # 4) 提取主治/功效关系
        therapeutic_relations = self._extract_therapeutic_relations(text, entities)
        relations.extend(therapeutic_relations)

        # 5) 提取君臣佐使角色
        role_items = self._extract_herb_roles(text)
        items.extend(role_items)

        duration = time.perf_counter() - t0
        stats = self._compute_stats(items, relations)

        return ExtractionResult(
            module_name=self.MODULE_NAME,
            items=items,
            relations=relations,
            statistics=stats,
            quality_scores=self._quality_scores(items, relations),
            duration_sec=duration,
        )

    # ------------------------------------------------------------------
    # 药物-剂量配对
    # ------------------------------------------------------------------

    def _extract_herb_dosage_pairs(
        self, text: str
    ) -> Tuple[List[ExtractedItem], List[ExtractionRelation]]:
        items: List[ExtractedItem] = []
        relations: List[ExtractionRelation] = []

        for match in _RE_HERB_DOSAGE.finditer(text):
            herb_name, amount, unit = match.groups()
            # 验证药名是否在词典中
            if not self._lexicon.contains(herb_name):
                continue
            canonical, _ = self._lexicon.resolve_synonym(herb_name)
            dosage_str = f"{amount}{unit}"
            start, end = match.span()

            items.append(ExtractedItem(
                name=canonical,
                entity_type=ExtractedEntityType.HERB.value,
                confidence=0.90,
                position=start,
                end_position=end,
                length=end - start,
                source_module=self.MODULE_NAME,
                rule_id="herb_dosage_pair",
                metadata={"dosage": dosage_str, "amount": amount, "unit": unit},
            ))
            relations.append(ExtractionRelation(
                source=canonical,
                target=dosage_str,
                relation_type="has_dosage",
                confidence=0.88,
                evidence_text=match.group(0),
                source_module=self.MODULE_NAME,
            ))
        return items, relations

    # ------------------------------------------------------------------
    # 方剂组成关系
    # ------------------------------------------------------------------

    def _extract_composition_relations(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]],
    ) -> List[ExtractionRelation]:
        """在组成段落中匹配方剂→药材关系。"""
        relations: List[ExtractionRelation] = []
        if not entities:
            return relations

        formula_names = {
            e["name"] for e in entities
            if e.get("type") in ("formula", "formulas")
        }
        herb_names = {
            e["name"] for e in entities
            if e.get("type") in ("herb", "herbs")
        }
        if not formula_names or not herb_names:
            return relations

        for match in _RE_FORMULA_COMPOSITION.finditer(text):
            composition_text = match.group(1)
            # 在组成段落中搜索方剂名出现在前文
            context_start = max(0, match.start() - 100)
            context = text[context_start:match.start()]
            found_formula = ""
            for fname in formula_names:
                if fname in context:
                    found_formula = fname
                    break
            if not found_formula:
                continue

            for hname in herb_names:
                if hname in composition_text:
                    relations.append(ExtractionRelation(
                        source=found_formula,
                        target=hname,
                        relation_type="contains",
                        confidence=0.88,
                        evidence_text=composition_text[:80],
                        source_module=self.MODULE_NAME,
                    ))
        return relations

    # ------------------------------------------------------------------
    # 主治/功效关系
    # ------------------------------------------------------------------

    def _extract_therapeutic_relations(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]],
    ) -> List[ExtractionRelation]:
        relations: List[ExtractionRelation] = []
        if not entities:
            return relations

        formula_names = {
            e["name"] for e in entities
            if e.get("type") in ("formula", "formulas")
        }
        syndrome_names = {
            e["name"] for e in entities
            if e.get("type") in ("syndrome", "syndromes")
        }

        for match in _RE_FORMULA_INDICATION.finditer(text):
            indication_text = match.group(1)
            context_start = max(0, match.start() - 100)
            context = text[context_start:match.start()]
            found_formula = ""
            for fname in formula_names:
                if fname in context or fname in indication_text:
                    found_formula = fname
                    break
            if not found_formula:
                continue
            for sname in syndrome_names:
                if sname in indication_text:
                    relations.append(ExtractionRelation(
                        source=found_formula,
                        target=sname,
                        relation_type="treats",
                        confidence=0.82,
                        evidence_text=indication_text[:80],
                        source_module=self.MODULE_NAME,
                    ))
        return relations

    # ------------------------------------------------------------------
    # 君臣佐使角色
    # ------------------------------------------------------------------

    def _extract_herb_roles(self, text: str) -> List[ExtractedItem]:
        """提取君臣佐使角色标注。"""
        items: List[ExtractedItem] = []
        role_map = {"君": "sovereign", "臣": "minister", "佐": "assistant", "使": "envoy"}
        for match in _RE_HERB_ROLE.finditer(text):
            role_prefix = text[match.start():match.start() + 1]
            role = role_map.get(role_prefix, "unknown")
            herb_text = match.group(1)
            # 尝试在词典中逐个匹配药名
            for word in sorted(self._lexicon.herbs, key=len, reverse=True):
                if word in herb_text:
                    items.append(ExtractedItem(
                        name=word,
                        entity_type=ExtractedEntityType.HERB.value,
                        confidence=0.85,
                        source_module=self.MODULE_NAME,
                        rule_id="herb_role",
                        metadata={"role": role},
                    ))
        return items

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def _compute_stats(
        self,
        items: List[ExtractedItem],
        relations: List[ExtractionRelation],
    ) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for item in items:
            by_type[item.entity_type] = by_type.get(item.entity_type, 0) + 1
        rel_by_type: Dict[str, int] = {}
        for rel in relations:
            rel_by_type[rel.relation_type] = rel_by_type.get(rel.relation_type, 0) + 1
        return {
            "total_items": len(items),
            "total_relations": len(relations),
            "items_by_type": by_type,
            "relations_by_type": rel_by_type,
        }

    def _quality_scores(
        self,
        items: List[ExtractedItem],
        relations: List[ExtractionRelation],
    ) -> Dict[str, float]:
        if not items:
            return {"avg_confidence": 0.0, "relation_density": 0.0}
        avg_conf = sum(i.confidence for i in items) / len(items)
        rel_density = len(relations) / max(len(items), 1)
        return {"avg_confidence": avg_conf, "relation_density": rel_density}
