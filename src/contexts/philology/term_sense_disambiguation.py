"""Term-sense disambiguation for high-frequency TCM philology terms."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

TERM_SENSE_DISAMBIGUATION_VERSION = "term-sense-disambiguation-v1"

_SPACE_RE = re.compile(r"\s+")
_KNOWN_DYNASTY_ALIASES = {
    "先秦": "pre_qin",
    "秦": "qin_han",
    "汉": "qin_han",
    "东汉": "qin_han",
    "西汉": "qin_han",
    "晋": "wei_jin",
    "唐": "tang_song",
    "宋": "tang_song",
    "金": "jin_yuan",
    "元": "jin_yuan",
    "明": "ming_qing",
    "清": "ming_qing",
}


@dataclass(frozen=True)
class TermSenseCandidate:
    sense_id: str
    label: str
    definition: str
    semantic_scope: str
    confidence: float
    basis: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    matched_cooccurring_terms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = TERM_SENSE_DISAMBIGUATION_VERSION
        return payload


class TermSenseDisambiguator:
    """Resolve or rank term senses without forcing ambiguous readings."""

    def __init__(
        self,
        seed_table: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
        *,
        min_resolved_confidence: float = 0.64,
        min_resolution_margin: float = 0.12,
        max_candidates: int = 4,
    ) -> None:
        self._seed_table = _normalize_seed_table(seed_table or DEFAULT_TERM_SENSES)
        self._min_resolved_confidence = _clamp(min_resolved_confidence)
        self._min_resolution_margin = max(0.0, min(1.0, float(min_resolution_margin)))
        self._max_candidates = max(1, int(max_candidates or 4))

    @property
    def supported_terms(self) -> List[str]:
        return sorted(self._seed_table.keys(), key=len, reverse=True)

    def default_category(self, term: str) -> str:
        senses = self._seed_table.get(_normalize_term(term)) or []
        if not senses:
            return "common"
        return str(senses[0].get("default_entity_type") or "theory")

    def disambiguate(
        self,
        entity_name: str,
        context_fragments: Optional[Sequence[Any] | str] = None,
        *,
        dynasty: Optional[str] = None,
        cooccurring_terms: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        term = _normalize_term(entity_name)
        senses = self._seed_table.get(term) or []
        if not senses:
            return {
                "contract_version": TERM_SENSE_DISAMBIGUATION_VERSION,
                "term": str(entity_name or "").strip(),
                "status": "unsupported_term",
                "sense_candidates": [],
            }

        context_text = _normalize_context(context_fragments)
        co_terms = _normalize_terms(cooccurring_terms)
        dynasty_bucket = _dynasty_bucket(dynasty)
        candidates = [
            self._score_sense(
                term,
                sense,
                context_text=context_text,
                cooccurring_terms=co_terms,
                dynasty_bucket=dynasty_bucket,
            )
            for sense in senses
        ]
        candidates.sort(key=lambda item: (-item.confidence, item.sense_id))
        limited = candidates[: self._max_candidates]
        resolved = self._resolve_top(limited)
        result: Dict[str, Any] = {
            "contract_version": TERM_SENSE_DISAMBIGUATION_VERSION,
            "term": term,
            "status": "resolved" if resolved is not None else "candidate",
            "confidence": limited[0].confidence if limited else 0.0,
            "sense_candidates": [item.to_dict() for item in limited],
        }
        if resolved is not None:
            result["sense_id"] = resolved.sense_id
            result["sense_label"] = resolved.label
            result["basis"] = list(resolved.basis)
        return result

    def annotate_entity(
        self,
        entity: Mapping[str, Any],
        context_fragments: Optional[Sequence[Any] | str] = None,
        *,
        dynasty: Optional[str] = None,
        cooccurring_terms: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(entity)
        name = str(
            payload.get("name") or payload.get("text") or payload.get("value") or ""
        ).strip()
        if not name:
            return payload
        result = self.disambiguate(
            name,
            context_fragments,
            dynasty=dynasty,
            cooccurring_terms=cooccurring_terms,
        )
        candidates = result.get("sense_candidates") or []
        if not candidates:
            return payload
        payload["sense_candidates"] = candidates
        metadata = dict(payload.get("metadata") or payload.get("entity_metadata") or {})
        metadata["sense_candidates"] = candidates
        if result.get("sense_id"):
            payload["sense_id"] = result["sense_id"]
            payload["sense_confidence"] = result.get("confidence", 0.0)
            payload["sense_basis"] = list(result.get("basis") or [])
            metadata["sense_id"] = result["sense_id"]
            metadata["sense_confidence"] = result.get("confidence", 0.0)
            metadata["sense_basis"] = list(result.get("basis") or [])
        payload["metadata"] = metadata
        return payload

    def disambiguate_entities(
        self,
        entities: Sequence[Mapping[str, Any]],
        context_text: str,
        *,
        dynasty: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        co_terms = [item.get("name") or item.get("text") for item in entities]
        return [
            self.annotate_entity(
                item,
                _context_window(context_text, item),
                dynasty=dynasty,
                cooccurring_terms=co_terms,
            )
            for item in entities
        ]

    def _resolve_top(
        self, candidates: Sequence[TermSenseCandidate]
    ) -> Optional[TermSenseCandidate]:
        if not candidates:
            return None
        top = candidates[0]
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        if top.confidence < self._min_resolved_confidence:
            return None
        if top.confidence - runner_up < self._min_resolution_margin:
            return None
        return top

    def _score_sense(
        self,
        term: str,
        sense: Mapping[str, Any],
        *,
        context_text: str,
        cooccurring_terms: Sequence[str],
        dynasty_bucket: str,
    ) -> TermSenseCandidate:
        keywords = _normalize_terms(sense.get("keywords") or [])
        co_hints = _normalize_terms(sense.get("cooccurring_terms") or [])
        dynasty_hints = _normalize_terms(sense.get("dynasty_buckets") or [])
        matched_keywords = [
            keyword for keyword in keywords if keyword and keyword in context_text
        ]
        matched_co_terms = [
            hint
            for hint in co_hints
            if hint in cooccurring_terms or hint in context_text
        ]

        score = 0.28
        score += min(0.36, len(matched_keywords) * 0.09)
        score += min(0.24, len(matched_co_terms) * 0.08)
        if dynasty_bucket and dynasty_bucket in dynasty_hints:
            score += 0.05
        if term and any(term in keyword for keyword in matched_keywords):
            score += 0.04

        basis: List[str] = []
        if matched_keywords:
            basis.append("上下文命中: " + "、".join(matched_keywords[:6]))
        if matched_co_terms:
            basis.append("共现术语命中: " + "、".join(matched_co_terms[:6]))
        if dynasty_bucket and dynasty_bucket in dynasty_hints:
            basis.append(f"年代提示匹配: {dynasty_bucket}")
        if not basis:
            basis.append("种子义项候选，缺少足够上下文证据")

        return TermSenseCandidate(
            sense_id=str(sense.get("sense_id") or "").strip(),
            label=str(sense.get("label") or "").strip(),
            definition=str(sense.get("definition") or "").strip(),
            semantic_scope=str(sense.get("semantic_scope") or "").strip(),
            confidence=round(_clamp(score), 4),
            basis=basis,
            matched_keywords=matched_keywords[:8],
            matched_cooccurring_terms=matched_co_terms[:8],
        )


DEFAULT_TERM_SENSES: Dict[str, List[Dict[str, Any]]] = {
    "风": [
        {
            "sense_id": "tcm.wind.external_pathogen",
            "label": "风邪",
            "definition": "六淫之一，常与寒、热、湿等合邪，见恶风、头痛、脉浮等表证语境。",
            "semantic_scope": "pathogen",
            "default_entity_type": "syndrome",
            "keywords": [
                "风寒",
                "风热",
                "恶风",
                "伤风",
                "中风",
                "头痛",
                "脉浮",
                "解表",
                "太阳",
            ],
            "cooccurring_terms": ["寒", "热", "湿", "表", "太阳", "桂枝汤"],
            "dynasty_buckets": ["pre_qin", "qin_han", "tang_song", "ming_qing"],
        },
        {
            "sense_id": "tcm.wind.internal_movement",
            "label": "内风",
            "definition": "多指肝风、动风等内生病机，常见眩晕、抽搐、痉厥、震颤等语境。",
            "semantic_scope": "pathogenesis",
            "default_entity_type": "syndrome",
            "keywords": [
                "肝风",
                "内风",
                "眩",
                "眩晕",
                "抽搐",
                "痉",
                "惊",
                "震颤",
                "动风",
            ],
            "cooccurring_terms": ["肝", "血", "虚", "痰", "热"],
        },
    ],
    "寒": [
        {
            "sense_id": "tcm.cold.external_pathogen",
            "label": "寒邪",
            "definition": "六淫寒邪，多见恶寒、无汗、脉紧、风寒、太阳表证等上下文。",
            "semantic_scope": "pathogen",
            "default_entity_type": "syndrome",
            "keywords": [
                "风寒",
                "恶寒",
                "无汗",
                "脉紧",
                "太阳",
                "伤寒",
                "寒邪",
                "表寒",
            ],
            "cooccurring_terms": ["风", "表", "太阳", "桂枝汤", "麻黄汤"],
            "dynasty_buckets": ["qin_han", "tang_song"],
        },
        {
            "sense_id": "tcm.cold.nature_property",
            "label": "寒性",
            "definition": "药物四气属性中的寒，多与性寒、苦寒、清热、药味功效同现。",
            "semantic_scope": "property",
            "default_entity_type": "property",
            "keywords": ["性寒", "大寒", "微寒", "苦寒", "清热", "寒凉", "味苦"],
            "cooccurring_terms": ["热", "味", "气", "清热", "黄芩", "石膏"],
        },
        {
            "sense_id": "tcm.cold.deficiency_cold_pattern",
            "label": "虚寒证",
            "definition": "寒象与虚象并见的证候语义，常与阳虚、脉迟、畏寒、四逆同现。",
            "semantic_scope": "pattern",
            "default_entity_type": "syndrome",
            "keywords": ["虚寒", "阳虚", "四逆", "畏寒", "脉迟", "少阴", "温中"],
            "cooccurring_terms": ["虚", "阳", "气", "附子", "干姜"],
        },
    ],
    "湿": [
        {
            "sense_id": "tcm.dampness.pathogen",
            "label": "湿邪",
            "definition": "六淫湿邪或湿浊病因，常与身重、困重、濡脉、湿热、寒湿同现。",
            "semantic_scope": "pathogen",
            "default_entity_type": "syndrome",
            "keywords": [
                "湿邪",
                "湿热",
                "寒湿",
                "身重",
                "困重",
                "濡",
                "苔腻",
                "利湿",
                "化湿",
            ],
            "cooccurring_terms": ["热", "寒", "脾", "痰", "水"],
        },
        {
            "sense_id": "tcm.dampness.fluid_retention",
            "label": "水湿停聚",
            "definition": "水液代谢失常所致湿滞、停饮语境，常与小便不利、水肿、痰饮同现。",
            "semantic_scope": "fluid_pathology",
            "default_entity_type": "syndrome",
            "keywords": ["水湿", "停饮", "小便不利", "水肿", "痰饮", "渗湿", "利水"],
            "cooccurring_terms": ["水", "饮", "痰", "脾", "肾"],
        },
    ],
    "热": [
        {
            "sense_id": "tcm.heat.pathogen_or_pattern",
            "label": "热邪/热证",
            "definition": "热邪或热证语义，常与发热、口渴、脉数、清热、湿热等同现。",
            "semantic_scope": "pathogen_pattern",
            "default_entity_type": "syndrome",
            "keywords": [
                "发热",
                "壮热",
                "潮热",
                "口渴",
                "脉数",
                "清热",
                "湿热",
                "热邪",
                "热证",
            ],
            "cooccurring_terms": ["寒", "湿", "火", "毒", "石膏", "黄连"],
        },
        {
            "sense_id": "tcm.heat.nature_property",
            "label": "热性",
            "definition": "药物四气属性中的热，多见性热、大热、温热、辛热等药性语境。",
            "semantic_scope": "property",
            "default_entity_type": "property",
            "keywords": ["性热", "大热", "微热", "温热", "辛热", "热药"],
            "cooccurring_terms": ["气", "味", "寒", "附子", "干姜"],
        },
    ],
    "虚": [
        {
            "sense_id": "tcm.deficiency.pattern",
            "label": "虚证",
            "definition": "正气不足或脏腑气血阴阳亏虚的证候语义。",
            "semantic_scope": "pattern",
            "default_entity_type": "syndrome",
            "keywords": [
                "虚证",
                "气虚",
                "血虚",
                "阴虚",
                "阳虚",
                "不足",
                "虚劳",
                "补虚",
                "脉虚",
            ],
            "cooccurring_terms": ["气", "血", "阴", "阳", "补", "实"],
        },
        {
            "sense_id": "lexical.empty_or_weak",
            "label": "空虚/不足泛义",
            "definition": "非严格证候的空、弱、不足等一般语义，需结合上下文候选保留。",
            "semantic_scope": "general_lexical",
            "default_entity_type": "common",
            "keywords": ["虚字", "虚名", "空虚", "虚处"],
            "cooccurring_terms": [],
        },
    ],
    "实": [
        {
            "sense_id": "tcm.excess.pattern",
            "label": "实证",
            "definition": "邪气盛、病势实的证候语义，常与实热、实寒、腹满拒按、泻实同现。",
            "semantic_scope": "pattern",
            "default_entity_type": "syndrome",
            "keywords": [
                "实证",
                "实热",
                "实寒",
                "邪实",
                "腹满",
                "拒按",
                "泻实",
                "脉实",
            ],
            "cooccurring_terms": ["虚", "热", "寒", "邪", "下"],
        },
        {
            "sense_id": "lexical.solid_or_actual",
            "label": "充实/实际泛义",
            "definition": "非证候的实在、充满、实际等一般语义。",
            "semantic_scope": "general_lexical",
            "default_entity_type": "common",
            "keywords": ["其实", "实为", "真实", "充实"],
            "cooccurring_terms": [],
        },
    ],
    "气": [
        {
            "sense_id": "tcm.qi.vital_function",
            "label": "气",
            "definition": "人体生命活动和脏腑功能之气，常与气虚、气滞、补气、行气同现。",
            "semantic_scope": "vital_substance",
            "default_entity_type": "theory",
            "keywords": [
                "气虚",
                "气滞",
                "补气",
                "行气",
                "宗气",
                "营气",
                "卫气",
                "气机",
            ],
            "cooccurring_terms": ["血", "虚", "实", "脾", "肺"],
        },
        {
            "sense_id": "tcm.qi.herbal_nature",
            "label": "药气/四气",
            "definition": "本草四气或气味语境中的气，如寒热温凉、气味厚薄。",
            "semantic_scope": "property",
            "default_entity_type": "property",
            "keywords": ["四气", "气味", "气厚", "气薄", "性温", "性寒", "味"],
            "cooccurring_terms": ["味", "寒", "热", "温", "凉"],
        },
    ],
    "血": [
        {
            "sense_id": "tcm.blood.substance",
            "label": "血",
            "definition": "人体血液与营养濡养之血，常与气血、血虚、养血、营血同现。",
            "semantic_scope": "vital_substance",
            "default_entity_type": "theory",
            "keywords": ["气血", "血虚", "养血", "营血", "补血", "血脉", "血分"],
            "cooccurring_terms": ["气", "虚", "营", "脉", "心", "肝"],
        },
        {
            "sense_id": "tcm.blood.pathology",
            "label": "血病/出血瘀血",
            "definition": "出血、瘀血、血热等病理语义，常与吐血、衄血、瘀血、活血同现。",
            "semantic_scope": "pathology",
            "default_entity_type": "syndrome",
            "keywords": [
                "吐血",
                "衄血",
                "便血",
                "瘀血",
                "活血",
                "血热",
                "血瘀",
                "止血",
            ],
            "cooccurring_terms": ["瘀", "热", "寒", "痛", "络"],
        },
    ],
    "经": [
        {
            "sense_id": "tcm.channel.meridian",
            "label": "经脉/经络",
            "definition": "经络、经脉或十二经系统语义，常与足太阳、手太阴、络、脉同现。",
            "semantic_scope": "channel",
            "default_entity_type": "theory",
            "keywords": ["经脉", "经络", "十二经", "足太阳", "手太阴", "经气", "络脉"],
            "cooccurring_terms": ["络", "脉", "气", "太阳", "少阳", "厥阴"],
        },
        {
            "sense_id": "philology.classic.canon",
            "label": "经典/经书",
            "definition": "文献类别或经典书名语义，如本经、内经、难经。",
            "semantic_scope": "bibliography",
            "default_entity_type": "common",
            "keywords": ["本经", "内经", "难经", "经曰", "经文", "经云"],
            "cooccurring_terms": ["素问", "灵枢", "本草", "条文"],
            "dynasty_buckets": ["pre_qin", "qin_han", "tang_song", "ming_qing"],
        },
        {
            "sense_id": "tcm.menses.menstruation",
            "label": "月经",
            "definition": "妇科月经语义，常与经水、经闭、经行、带下同现。",
            "semantic_scope": "gynecology",
            "default_entity_type": "syndrome",
            "keywords": ["月经", "经水", "经闭", "经行", "经期", "带下"],
            "cooccurring_terms": ["血", "妇人", "胞", "带下"],
        },
    ],
    "方": [
        {
            "sense_id": "tcm.formula.prescription",
            "label": "方剂/处方",
            "definition": "方剂、处方或治法组合，常与汤、丸、散、主治、组成同现。",
            "semantic_scope": "formula",
            "default_entity_type": "formula",
            "keywords": [
                "方剂",
                "处方",
                "方药",
                "主治",
                "组成",
                "汤",
                "丸",
                "散",
                "煎服",
            ],
            "cooccurring_terms": ["桂枝汤", "麻黄汤", "药", "证", "治"],
        },
        {
            "sense_id": "method.method_or_direction",
            "label": "方法/方位泛义",
            "definition": "方法、方向、方面等非方剂语义，缺少方药上下文时只保留候选。",
            "semantic_scope": "general_lexical",
            "default_entity_type": "common",
            "keywords": ["方法", "方面", "东方", "西方", "方可", "方寸"],
            "cooccurring_terms": [],
        },
    ],
}


def _normalize_seed_table(
    raw: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    table: Dict[str, List[Dict[str, Any]]] = {}
    for raw_term, senses in raw.items():
        term = _normalize_term(raw_term)
        if not term:
            continue
        normalized_senses = []
        for sense in senses or []:
            if not isinstance(sense, Mapping):
                continue
            payload = dict(sense)
            if str(payload.get("sense_id") or "").strip():
                normalized_senses.append(payload)
        if normalized_senses:
            table[term] = normalized_senses
    return table


def _normalize_context(value: Optional[Sequence[Any] | str]) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _SPACE_RE.sub("", value)
    parts = [str(item or "").strip() for item in value if str(item or "").strip()]
    return _SPACE_RE.sub("", "\n".join(parts))


def _normalize_terms(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return []
    terms: List[str] = []
    for value in values:
        text = _normalize_term(value)
        if text and text not in terms:
            terms.append(text)
    return terms


def _normalize_term(value: Any) -> str:
    return _SPACE_RE.sub("", str(value or "").strip())


def _dynasty_bucket(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "未知":
        return ""
    for dynasty, bucket in _KNOWN_DYNASTY_ALIASES.items():
        if dynasty in text:
            return bucket
    return text.lower()


def _context_window(
    context_text: str, entity: Mapping[str, Any], *, radius: int = 48
) -> str:
    try:
        start = max(0, int(entity.get("position") or 0) - radius)
        end = int(entity.get("end_position") or entity.get("position") or 0) + radius
    except (TypeError, ValueError):
        return context_text[: radius * 2]
    return context_text[start:end]


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(0.98, number))
