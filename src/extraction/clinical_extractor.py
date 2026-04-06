"""临床应用信息提取模块 — 从古籍文本中提取临床方案、医案、适应证/禁忌、用药方案等。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
# 临床信息专用正则
# ---------------------------------------------------------------------------

_RE_CASE_HEADER = re.compile(
    r"(?:医案|病案|案|验案|治验|例)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_PATIENT_INFO = re.compile(
    r"(?:患者|病人|某).*?[，,]\s*(?:年|岁|男|女)(.+?)(?:[。\n]|$)"
)
_RE_SYMPTOM_DESC = re.compile(
    r"(?:症见|症状|临床表现|见|表现为|诊见)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_DIAGNOSIS = re.compile(
    r"(?:诊断|辨证|证属|证型|辨为|诊为|属)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_TREATMENT_PLAN = re.compile(
    r"(?:治法|治则|治以|治宜|法当|宜)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_PRESCRIPTION = re.compile(
    r"(?:处方|方用|方药|投以|予以|拟方|用方|拟)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_OUTCOME = re.compile(
    r"(?:效果|疗效|转归|愈|效|服后|服\d+剂)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_ACUPOINT = re.compile(
    r"(?:取穴|配穴|穴位|选穴|针灸)[:：]?\s*(.+?)(?:[。\n]|$)"
)
_RE_COURSE = re.compile(
    r"(?:疗程|服\s*\d+\s*[剂日天次]|连服|连用)\s*(.+?)(?:[。\n]|$)"
)


# ---------------------------------------------------------------------------
# 医案结构
# ---------------------------------------------------------------------------

@dataclass
class ClinicalCase:
    """提取的医案/病案结构。"""
    case_id: str = ""
    patient_info: str = ""
    symptoms: List[str] = field(default_factory=list)
    diagnosis: str = ""
    treatment_principle: str = ""
    prescription: str = ""
    outcome: str = ""
    acupoints: List[str] = field(default_factory=list)
    source_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "patient_info": self.patient_info,
            "symptoms": self.symptoms,
            "diagnosis": self.diagnosis,
            "treatment_principle": self.treatment_principle,
            "prescription": self.prescription,
            "outcome": self.outcome,
            "acupoints": self.acupoints,
        }


def _build_clinical_rules() -> List[ExtractionRule]:
    return [
        ExtractionRule(
            rule_id="clin_symptom",
            name="临床症状",
            entity_type=ExtractedEntityType.SYMPTOM.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:症见|症状|临床表现|见|表现为|诊见)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=88,
            confidence_base=0.83,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="clin_diagnosis",
            name="辨证诊断",
            entity_type=ExtractedEntityType.SYNDROME.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:辨证|证属|证型|辨为|诊为|属)[:：]?\s*(.+?)(?:[。\n]|$)",
            priority=90,
            confidence_base=0.85,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="clin_treatment",
            name="治法治则",
            entity_type=ExtractedEntityType.EFFICACY.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:治法|治则|治以|治宜|法当|宜)[:：]?\s*(.+?)(?:[。\n]|$)",
            priority=85,
            confidence_base=0.82,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="clin_acupoint",
            name="穴位取穴",
            entity_type=ExtractedEntityType.ACUPOINT.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:取穴|配穴|穴位|选穴|针灸)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=80,
            confidence_base=0.82,
            group_index=1,
        ),
        ExtractionRule(
            rule_id="clin_prescription",
            name="处方用药",
            entity_type=ExtractedEntityType.FORMULA.value,
            rule_type=RuleType.REGEX,
            pattern=r"(?:处方|方用|方药|投以|予以|拟方|用方|拟)[:：]\s*(.+?)(?:[。\n]|$)",
            priority=86,
            confidence_base=0.84,
            group_index=1,
        ),
    ]


# ---------------------------------------------------------------------------
# 临床信息提取器
# ---------------------------------------------------------------------------

class ClinicalExtractor:
    """临床应用信息提取器。

    从古籍文本中提取:
    - 医案/病案结构（患者信息→症状→诊断→治法→处方→疗效）
    - 适应证 / 禁忌
    - 穴位处方
    - 治疗方案
    - 关系（诊断→处方、处方→疗效等）
    """

    MODULE_NAME = "clinical_extractor"

    def __init__(self, extra_rules: Optional[List[ExtractionRule]] = None) -> None:
        self._lexicon = get_lexicon()
        self._engine = ExtractionRuleEngine()
        self._engine.add_rules(_build_clinical_rules())
        if extra_rules:
            self._engine.add_rules(extra_rules)

    def extract(self, text: str) -> ExtractionResult:
        import time
        t0 = time.perf_counter()
        items: List[ExtractedItem] = []
        relations: List[ExtractionRelation] = []

        # 1) 规则引擎匹配
        engine_items = self._engine.apply_regex_rules(text)
        for item in engine_items:
            item.source_module = self.MODULE_NAME
        items.extend(engine_items)

        # 2) 医案结构化提取
        cases = self._extract_clinical_cases(text)

        # 3) 从医案中生成关系
        for case in cases:
            case_rels = self._case_to_relations(case)
            relations.extend(case_rels)

        # 4) 穴位词典匹配
        acupoint_items = self._extract_acupoints_from_lexicon(text)
        items.extend(acupoint_items)

        duration = time.perf_counter() - t0
        return ExtractionResult(
            module_name=self.MODULE_NAME,
            items=items,
            relations=relations,
            statistics={
                "total_items": len(items),
                "total_relations": len(relations),
                "clinical_cases": len(cases),
                "cases": [c.to_dict() for c in cases],
            },
            quality_scores=self._quality_scores(items, cases),
            duration_sec=duration,
        )

    # ------------------------------------------------------------------
    # 医案提取
    # ------------------------------------------------------------------

    def _extract_clinical_cases(self, text: str) -> List[ClinicalCase]:
        """尝试识别文本中的医案段落并结构化。"""
        cases: List[ClinicalCase] = []

        # 查找医案起始标记
        case_starts: List[int] = []
        for match in _RE_CASE_HEADER.finditer(text):
            case_starts.append(match.start())

        if not case_starts:
            # 无显式医案标记，尝试将整段文本作为单个隐式医案
            case = self._parse_single_case(text, "implicit_001")
            if case.diagnosis or case.prescription:
                cases.append(case)
            return cases

        # 按医案标记分段
        for i, start in enumerate(case_starts):
            end = case_starts[i + 1] if i + 1 < len(case_starts) else len(text)
            segment = text[start:end]
            case = self._parse_single_case(segment, f"case_{i + 1:03d}")
            cases.append(case)
        return cases

    def _parse_single_case(self, segment: str, case_id: str) -> ClinicalCase:
        case = ClinicalCase(case_id=case_id, source_text=segment[:200])

        m = _RE_PATIENT_INFO.search(segment)
        if m:
            case.patient_info = m.group(0).strip()[:80]

        for m in _RE_SYMPTOM_DESC.finditer(segment):
            case.symptoms.append(m.group(1).strip()[:100])

        m = _RE_DIAGNOSIS.search(segment)
        if m:
            case.diagnosis = m.group(1).strip()[:80]

        m = _RE_TREATMENT_PLAN.search(segment)
        if m:
            case.treatment_principle = m.group(1).strip()[:80]

        m = _RE_PRESCRIPTION.search(segment)
        if m:
            case.prescription = m.group(1).strip()[:200]

        m = _RE_OUTCOME.search(segment)
        if m:
            case.outcome = m.group(1).strip()[:100]

        for m in _RE_ACUPOINT.finditer(segment):
            case.acupoints.append(m.group(1).strip()[:50])

        return case

    # ------------------------------------------------------------------
    # 医案 → 关系
    # ------------------------------------------------------------------

    def _case_to_relations(self, case: ClinicalCase) -> List[ExtractionRelation]:
        relations: List[ExtractionRelation] = []
        if case.diagnosis and case.prescription:
            relations.append(ExtractionRelation(
                source=case.diagnosis,
                target=case.prescription,
                relation_type="diagnosed_and_prescribed",
                confidence=0.80,
                evidence_text=case.source_text[:60],
                source_module=self.MODULE_NAME,
            ))
        if case.prescription and case.outcome:
            relations.append(ExtractionRelation(
                source=case.prescription,
                target=case.outcome,
                relation_type="prescription_outcome",
                confidence=0.78,
                evidence_text=case.source_text[:60],
                source_module=self.MODULE_NAME,
            ))
        if case.diagnosis and case.treatment_principle:
            relations.append(ExtractionRelation(
                source=case.diagnosis,
                target=case.treatment_principle,
                relation_type="diagnosis_to_treatment",
                confidence=0.82,
                evidence_text=case.source_text[:60],
                source_module=self.MODULE_NAME,
            ))
        return relations

    # ------------------------------------------------------------------
    # 穴位提取
    # ------------------------------------------------------------------

    def _extract_acupoints_from_lexicon(self, text: str) -> List[ExtractedItem]:
        """基于穴位词典进行匹配（如果 lexicon 中有 acupoint 分类）。"""
        items: List[ExtractedItem] = []
        # 目前 lexicon 无 acupoint 分类，使用内置常见穴位列表
        common_acupoints = {
            "足三里", "合谷", "三阴交", "百会", "关元", "气海",
            "中脘", "内关", "太冲", "曲池", "天枢", "肺俞",
            "肾俞", "脾俞", "大椎", "命门", "神阙", "太溪",
            "血海", "阳陵泉", "阴陵泉", "丰隆", "列缺", "照海",
            "风池", "风府", "肩井", "委中", "承山", "涌泉",
        }
        for acupoint in common_acupoints:
            start = 0
            while True:
                pos = text.find(acupoint, start)
                if pos == -1:
                    break
                items.append(ExtractedItem(
                    name=acupoint,
                    entity_type=ExtractedEntityType.ACUPOINT.value,
                    confidence=0.88,
                    position=pos,
                    end_position=pos + len(acupoint),
                    length=len(acupoint),
                    source_module=self.MODULE_NAME,
                    rule_id="acupoint_dict",
                ))
                start = pos + len(acupoint)
        return items

    # ------------------------------------------------------------------
    # 质量
    # ------------------------------------------------------------------

    def _quality_scores(
        self,
        items: List[ExtractedItem],
        cases: List[ClinicalCase],
    ) -> Dict[str, float]:
        case_completeness = 0.0
        if cases:
            completeness_per_case = []
            for c in cases:
                fields = [c.diagnosis, c.prescription, c.treatment_principle]
                filled = sum(1 for f in fields if f)
                completeness_per_case.append(filled / len(fields))
            case_completeness = sum(completeness_per_case) / len(completeness_per_case)
        return {
            "avg_confidence": (
                sum(i.confidence for i in items) / len(items) if items else 0.0
            ),
            "case_completeness": case_completeness,
        }
