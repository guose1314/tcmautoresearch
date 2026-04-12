from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic_modeling.tcm_relationships import (
    TCMRelationshipDefinitions,  # noqa: E402
)

DEFAULT_LEXICON_PATH = ROOT / "data" / "tcm_lexicon.jsonl"
DEFAULT_SYNONYMS_PATH = ROOT / "data" / "tcm_synonyms.jsonl"
KNOWLEDGE_BASE_DIR = ROOT / "src" / "data" / "knowledge_base"

CATEGORY_OUTPUT_NAMES = {
    "herbs": "herb",
    "formulas": "formula",
    "syndromes": "syndrome",
    "theory": "theory",
    "efficacy": "efficacy",
    "common": "common",
}

FORMULA_SUFFIX = r"(?:汤|散|丸|饮|膏|丹|方|煎|露|酒|片|茶|锭|珠|洗剂|合剂|颗粒)"
PURE_FORMULA_RE = re.compile(rf"^[一-龥]{{2,16}}{FORMULA_SUFFIX}$")
QUJI_LINE_RE = re.compile(rf"^[a-z0-9]{{3,4}}([一-龥]{{2,16}}{FORMULA_SUFFIX})\t")
SONG_HEAD_RE = re.compile(rf"^([一-龥]{{2,16}}{FORMULA_SUFFIX})(?:\s{{2,}}|\t|$)")
ENTRY_HEAD_RE = re.compile(rf"^([一-龥]{{2,16}}{FORMULA_SUFFIX})(?:\t|\s{{2,}}|$)")
SECTION_RE = re.compile(r"【([^】]+)】")
HERB_DOSAGE_RE = re.compile(
    r"([一-龥]{2,8})(?:（[^）]{0,8}）)?(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万半两]+)\s*"
    r"(?:克|g|kg|斤|两|钱|分|枚|粒|升|毫升|ml|合)"
)
SPECIAL_SYNDROME_TERMS = {
    "中风",
    "伤寒",
    "温病",
    "消渴",
    "霍乱",
    "胸痹",
    "痰饮",
    "虚劳",
    "崩漏",
    "带下",
    "遗精",
    "失眠",
    "腹痛",
    "咽痛",
    "头痛",
    "咳嗽",
    "呕吐",
    "泄泻",
    "痢疾",
    "痹证",
    "痿证",
    "淋证",
    "黄疸",
}
SYNDROME_MATCH_RE = re.compile(
    r"([一-龥]{2,12}(?:证|症|病|痹|痿|厥|痛|满|胀|热|寒|虚|瘀|饮|郁|闭|脱|痰|喘|咳|痢|泻|疟|淋|疳|疮|斑))"
)
TOKEN_SPLIT_RE = re.compile(r"[，、；;,。！？!\s\u3000/]+")
PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
LATIN_PREFIX_RE = re.compile(r"^[a-z0-9]{2,4}")
NON_CJK_RE = re.compile(r"[^一-龥]")

FORMULA_STOP_FRAGMENTS = {
    "本方",
    "上方",
    "下方",
    "上述",
    "以上",
    "适用",
    "禁用",
    "应用",
    "试效",
    "代表方",
    "见上述",
    "可用",
    "不可",
}
FORMULA_STOPWORDS = {
    "一级方",
    "二级方",
    "三级方",
    "方剂",
    "用方",
    "上方",
    "下方",
}
HERB_STOP_FRAGMENTS = {
    "此药",
    "每服",
    "上药",
    "上味",
    "共为",
    "炼蜜",
    "打糊",
    "送下",
    "细末",
    "好酒",
    "滚水",
    "白水",
    "米汤",
    "煎汤",
}
HERB_STOPWORDS = {
    "各",
    "上",
    "另研",
    "后下",
    "另末",
    "同上",
    "听用",
    "一两",
    "二两",
    "三两",
    "四两",
    "五两",
}
EFFICACY_STOP_FRAGMENTS = {
    "主治",
    "条文",
    "临床应用",
    "用法用量",
    "备注",
    "现代",
    "研究",
    "用于",
    "治法",
}
EFFICACY_STOP_PREFIXES = (
    "能",
    "可",
    "专",
    "每",
)
EFFICACY_STOP_SUFFIXES = (
    "免疫",
    "体质",
    "睡眠",
    "气色",
    "食欲",
    "功能",
    "效果",
    "环境",
)
EFFICACY_STOP_EXACT = {
    "健食",
    "强心",
    "促进食欲",
    "增强免疫",
    "增强免疫力",
    "增强体质",
    "提高体质",
    "提高免疫力",
    "改善睡眠",
    "改善气色",
    "改善性功能",
    "改善肠道环境",
    "减肥瘦身",
    "美容养颜",
    "延年益寿",
    "抗衰老",
    "降血压",
    "降血糖",
    "降血脂",
}
EFFICACY_NOISE_FRAGMENTS = {
    "改善",
    "增强",
    "提高",
    "减肥",
    "美容",
    "延年",
    "抗衰",
    "促进",
    "睡眠",
    "气色",
    "肠道",
    "环境",
    "功能",
    "效果",
}
EFFICACY_NARRATIVE_FRAGMENTS = {
    "其",
    "客热",
}
EFFICACY_NARRATIVE_EXACT = {
    "开胸膈气结",
    "散胸中邪气",
    "泻胃火实热",
    "除膈上结热",
}
SYNDROME_STOP_FRAGMENTS = {
    "本方",
    "此药",
    "主治",
    "条文",
    "临床应用",
    "现代",
    "研究",
    "上焦",
    "中焦",
    "下焦",
    "以上",
    "上述",
}
SYNDROME_STOP_PREFIXES = (
    "一",
    "专",
    "此",
    "每",
    "凡",
    "诸",
)
SYNDROME_NOISE_FRAGMENTS = {
    "专治",
    "专疗",
    "专主",
    "细末",
    "后天之本",
    "之本",
    "之为",
}
SYNDROME_NOISE_CHARS = {"为", "之"}
SYNDROME_CLAUSE_MARKERS = ("或", "但", "属", "因", "等")
SYNDROME_MAX_LENGTH = 8
SYNDROME_CONTEXT_PREFIXES = (
    "其人",
    "其证",
    "病人",
    "法先",
    "因尔",
    "谓非",
    "时有",
    "日晚",
    "日晡",
    "至夜",
    "四时",
    "小儿",
    "产后",
    "久病",
    "久咳",
)
SYNDROME_SYMPTOM_PHRASES = (
    "头痛",
    "腹痛",
    "咽痛",
    "发热",
    "欲饮",
    "烦热",
    "烦渴",
    "恶寒",
    "胸中痛",
    "腹满",
    "胀满",
)
SYNDROME_SYMPTOM_KEEP_EXACT = {
    "头痛",
    "腹痛",
    "咽痛",
    "伤寒",
    "伤寒病",
}
SYNDROME_PATTERN_PREFIXES = (
    "气虚",
    "血虚",
    "阴虚",
    "阳虚",
    "肝郁",
    "肝阳",
    "肝火",
    "心肾",
    "肝脾",
    "肺肾",
    "脾肾",
    "气阴",
    "痰湿",
    "风寒",
    "风热",
    "湿热",
    "热毒",
    "寒凝",
    "心火",
    "胃火",
    "肝胆",
    "大肠",
    "膀胱",
    "脾胃",
    "中气",
    "肺失",
    "肾气",
)
EFFICACY_MAX_LENGTH = 6
MICANG_EFFICACY_MARKERS = ("能", "可", "善")

THEORY_SEEDS = {
    "阴阳",
    "气血",
    "脏腑",
    "经络",
    "表里",
    "寒热",
    "虚实",
    "升降浮沉",
    "君臣佐使",
    "营卫",
    "气机",
    "津液",
    "肺经",
    "脾经",
    "心经",
    "肝经",
    "肾经",
    "胃经",
    "胆经",
    "大肠经",
    "小肠经",
    "膀胱经",
    "心包经",
    "三焦经",
    "任脉",
    "督脉",
    "太阳经",
    "少阳经",
    "阳明经",
    "太阴经",
    "少阴经",
    "厥阴经",
    "四气",
    "五味",
}
COMMON_SEEDS = {
    "辨证",
    "配伍",
    "经方",
    "古方",
    "药对",
    "方证",
    "煎服",
    "加减",
}

MERIDIAN_MAP = {
    "lung": "肺经",
    "spleen": "脾经",
    "heart": "心经",
    "liver": "肝经",
    "kidney": "肾经",
    "stomach": "胃经",
    "gallbladder": "胆经",
    "large_intestine": "大肠经",
    "small_intestine": "小肠经",
    "bladder": "膀胱经",
    "pericardium": "心包经",
    "triple_burner": "三焦经",
    "all": "诸经",
}

EFFICACY_TRANSLATIONS = {
    "cool_blood": "凉血",
    "relieve_pain": "止痛",
}


@dataclass(slots=True)
class BuildAccumulator:
    herbs: Set[str] = field(default_factory=set)
    formulas: Set[str] = field(default_factory=set)
    syndromes: Set[str] = field(default_factory=set)
    theory: Set[str] = field(default_factory=set)
    efficacy: Set[str] = field(default_factory=set)
    common: Set[str] = field(default_factory=set)
    synonyms: Set[tuple[str, str, str]] = field(default_factory=set)
    source_counts: Counter[str] = field(default_factory=Counter)
    source_files: Dict[str, str] = field(default_factory=dict)
    term_sources: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.term_sources:
            return
        self.term_sources = {category: {} for category in CATEGORY_OUTPUT_NAMES}

    def add_term(self, category: str, term: str, source: str) -> None:
        normalized = normalize_term(category, term)
        if not normalized:
            return
        sources_by_term = self.term_sources.setdefault(category, {})
        sources_by_term.setdefault(normalized, set()).add(source)
        collection = getattr(self, category)
        if normalized not in collection:
            collection.add(normalized)
            self.source_counts[f"{category}:{source}"] += 1

    def add_terms(self, category: str, terms: Iterable[str], source: str) -> None:
        for term in terms:
            self.add_term(category, term, source)

    def add_synonym(self, alias: str, canonical: str, category: str) -> None:
        alias_term = normalize_term(category, alias)
        canonical_term = normalize_term(category, canonical)
        if not alias_term or not canonical_term or alias_term == canonical_term:
            return
        self.synonyms.add((alias_term, canonical_term, category))

    def summary(self) -> Dict[str, int]:
        return {
            "herb": len(self.herbs),
            "formula": len(self.formulas),
            "syndrome": len(self.syndromes),
            "theory": len(self.theory),
            "efficacy": len(self.efficacy),
            "common": len(self.common),
            "total": sum(
                len(items)
                for items in (
                    self.herbs,
                    self.formulas,
                    self.syndromes,
                    self.theory,
                    self.efficacy,
                    self.common,
                )
            ),
            "synonyms": len(self.synonyms),
        }


def clean_text(value: str) -> str:
    return str(value).replace("\ufeff", "").replace("\u3000", " ").strip()


def normalize_formula(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = LATIN_PREFIX_RE.sub("", cleaned)
    cleaned = PAREN_RE.sub("", cleaned)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r\"'“”‘’")
    cleaned = cleaned.replace(" ", "")
    if cleaned in FORMULA_STOPWORDS:
        return ""
    if any(fragment in cleaned for fragment in FORMULA_STOP_FRAGMENTS):
        return ""
    if not PURE_FORMULA_RE.fullmatch(cleaned):
        return ""
    if len(cleaned) < 2 or len(cleaned) > 16:
        return ""
    return cleaned


def normalize_herb(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = PAREN_RE.sub("", cleaned)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r")
    cleaned = cleaned.replace(" ", "")
    if len(cleaned) < 2 or len(cleaned) > 8:
        return ""
    if cleaned in HERB_STOPWORDS:
        return ""
    if any(fragment in cleaned for fragment in HERB_STOP_FRAGMENTS):
        return ""
    if NON_CJK_RE.search(cleaned):
        return ""
    return cleaned


def normalize_syndrome(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = PAREN_RE.sub("", cleaned)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r")
    cleaned = cleaned.replace(" ", "")
    if len(cleaned) < 2 or len(cleaned) > SYNDROME_MAX_LENGTH:
        return ""
    if cleaned.startswith(SYNDROME_CONTEXT_PREFIXES):
        return ""
    if cleaned.startswith("不") and len(cleaned) > 2:
        return ""
    if cleaned.startswith(SYNDROME_STOP_PREFIXES):
        return ""
    if cleaned.startswith("伤寒") and cleaned not in SYNDROME_SYMPTOM_KEEP_EXACT and len(cleaned) > 2:
        return ""
    if any(fragment in cleaned for fragment in SYNDROME_STOP_FRAGMENTS):
        return ""
    if any(fragment in cleaned for fragment in SYNDROME_NOISE_FRAGMENTS):
        return ""
    if any(char in cleaned for char in SYNDROME_NOISE_CHARS):
        return ""
    if any(marker in cleaned for marker in SYNDROME_CLAUSE_MARKERS):
        return ""
    if cleaned in {"偏头痛", "神经性头痛"}:
        return ""
    if any(fragment in cleaned for fragment in SYNDROME_SYMPTOM_PHRASES):
        if cleaned not in SYNDROME_SYMPTOM_KEEP_EXACT:
            if not cleaned.endswith(("证", "症", "病", "痹", "痿", "淋", "疾", "疸")):
                if not cleaned.startswith(SYNDROME_PATTERN_PREFIXES):
                    return ""
    if "而" in cleaned:
        return ""
    if NON_CJK_RE.search(cleaned):
        return ""
    if len(cleaned) >= 4 and cleaned.startswith(SYNDROME_PATTERN_PREFIXES):
        return cleaned
    if cleaned in SPECIAL_SYNDROME_TERMS or SYNDROME_MATCH_RE.fullmatch(cleaned):
        return cleaned
    return ""


def normalize_efficacy(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = PAREN_RE.sub("", cleaned)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r")
    cleaned = cleaned.replace(" ", "")
    cleaned = EFFICACY_TRANSLATIONS.get(cleaned, cleaned)
    if len(cleaned) < 2 or len(cleaned) > EFFICACY_MAX_LENGTH:
        return ""
    if cleaned in EFFICACY_STOP_EXACT:
        return ""
    if cleaned.startswith(EFFICACY_STOP_PREFIXES):
        return ""
    if any(fragment in cleaned for fragment in EFFICACY_STOP_FRAGMENTS):
        return ""
    if any(fragment in cleaned for fragment in EFFICACY_NOISE_FRAGMENTS):
        return ""
    if cleaned in EFFICACY_NARRATIVE_EXACT:
        return ""
    if any(fragment in cleaned for fragment in EFFICACY_NARRATIVE_FRAGMENTS):
        return ""
    if cleaned.endswith(EFFICACY_STOP_SUFFIXES):
        return ""
    if any(char in cleaned for char in SYNDROME_NOISE_CHARS):
        return ""
    if NON_CJK_RE.search(cleaned):
        return ""
    if cleaned[0] not in {"补", "健", "清", "解", "温", "散", "祛", "活", "止", "养", "益", "固", "利", "燥", "化", "平", "调", "润", "消", "理", "开", "通", "和", "泻", "敛", "安", "熄", "回", "舒", "生", "除", "降", "升"}:
        return ""
    return cleaned


def normalize_theory(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r")
    cleaned = cleaned.replace(" ", "")
    if len(cleaned) < 2 or len(cleaned) > 12:
        return ""
    if NON_CJK_RE.search(cleaned):
        return ""
    return cleaned


def normalize_common(term: str) -> str:
    cleaned = clean_text(term)
    cleaned = cleaned.strip(" 、，；;。,【】[]()（）:：\t\n\r")
    cleaned = cleaned.replace(" ", "")
    if len(cleaned) < 2 or len(cleaned) > 8:
        return ""
    if NON_CJK_RE.search(cleaned):
        return ""
    return cleaned


def normalize_term(category: str, term: str) -> str:
    if category == "formulas":
        return normalize_formula(term)
    if category == "herbs":
        return normalize_herb(term)
    if category == "syndromes":
        return normalize_syndrome(term)
    if category == "efficacy":
        return normalize_efficacy(term)
    if category == "theory":
        return normalize_theory(term)
    if category == "common":
        return normalize_common(term)
    raise ValueError(f"unsupported category: {category}")


def split_text_terms(text: str) -> List[str]:
    return [item for item in TOKEN_SPLIT_RE.split(clean_text(text)) if item]


def discover_corpus_files(root: Path) -> Dict[str, Path]:
    targets = {
        "quji": "方剂趣记大典(379种).txt",
        "song": "方剂歌诀(含组成药物及其克数).txt",
        "entry": "伤寒论方剂(113种).txt",
        "micang": "秘藏膏丹丸散方剂-清-.txt",
    }
    discovered: Dict[str, Path] = {}
    for key, name in targets.items():
        candidates: List[Path] = []
        for search_root in (root / "data", root / "output"):
            if not search_root.exists():
                continue
            candidates.extend(search_root.rglob(name))
        if not candidates:
            continue
        candidates.sort(key=lambda path: (0 if "data" in path.parts else 1, len(path.parts), str(path)))
        discovered[key] = candidates[0]
    return discovered


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16", "utf-16-le"):
        try:
            return path.read_bytes().decode(encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")


def build_from_knowledge(acc: BuildAccumulator) -> None:
    formula_archive = json.loads((KNOWLEDGE_BASE_DIR / "formula_archive.json").read_text(encoding="utf-8"))
    formula_structures = json.loads((KNOWLEDGE_BASE_DIR / "formula_structures.json").read_text(encoding="utf-8"))
    herb_properties = json.loads((KNOWLEDGE_BASE_DIR / "herb_properties.json").read_text(encoding="utf-8"))

    acc.add_terms("theory", THEORY_SEEDS, "theory_seeds")
    acc.add_terms("common", COMMON_SEEDS, "common_seeds")

    for formula_name, payload in formula_archive.items():
        acc.add_term("formulas", formula_name, "formula_archive")
        for alias in payload.get("variant_names") or []:
            acc.add_term("formulas", alias, "formula_archive_variant")
            acc.add_synonym(alias, formula_name, "formulas")
        for indication in payload.get("core_indications") or []:
            acc.add_term("syndromes", indication, "formula_archive_indication")

    for formula_name, payload in formula_structures.items():
        acc.add_term("formulas", formula_name, "formula_structures")
        for role in ("sovereign", "minister", "assistant", "envoy"):
            for item in payload.get(role) or []:
                if isinstance(item, dict):
                    acc.add_term("herbs", item.get("name", ""), f"formula_structures_{role}")

    for herb_name, payload in herb_properties.items():
        acc.add_term("herbs", herb_name, "herb_properties")
        acc.add_terms(
            "efficacy",
            split_text_terms(str(payload.get("primary_efficacy") or "").replace("、", " ")),
            "herb_properties_primary_efficacy",
        )
        acc.add_terms(
            "efficacy",
            [str(item) for item in (payload.get("secondary_efficacy") or [])],
            "herb_properties_secondary_efficacy",
        )
        for meridian in payload.get("meridians") or []:
            mapped = MERIDIAN_MAP.get(str(meridian), str(meridian))
            acc.add_term("theory", mapped, "herb_properties_meridian")
        for flavor in payload.get("flavors") or []:
            acc.add_term("theory", str(flavor), "herb_properties_flavor")
        temperature = payload.get("temperature")
        if temperature:
            acc.add_term("theory", str(temperature), "herb_properties_temperature")

    for formula_name, composition in TCMRelationshipDefinitions.FORMULA_COMPOSITIONS.items():
        acc.add_term("formulas", formula_name, "relationship_formulas")
        for herbs in composition.values():
            acc.add_terms("herbs", herbs, "relationship_formula_components")

    for herb_name, efficacy_terms in TCMRelationshipDefinitions.HERB_EFFICACY_MAP.items():
        acc.add_term("herbs", herb_name, "relationship_herbs")
        acc.add_terms("efficacy", efficacy_terms, "relationship_efficacy")

    for prop_map in TCMRelationshipDefinitions.HERB_PROPERTIES.values():
        for value in prop_map.values():
            if isinstance(value, str):
                for item in split_text_terms(value.replace("、", " ").replace("、", " ")):
                    acc.add_term("theory", item, "relationship_properties")


def extract_herbs_from_segment(segment: str) -> Set[str]:
    herbs: Set[str] = set()
    for match in HERB_DOSAGE_RE.finditer(segment):
        herb = normalize_herb(match.group(1))
        if herb:
            herbs.add(herb)
    return herbs


def extract_efficacy_from_segment(segment: str) -> Set[str]:
    candidates: Set[str] = set()
    for item in split_text_terms(segment.replace("、", " ")):
        efficacy = normalize_efficacy(item)
        if efficacy:
            candidates.add(efficacy)
    return candidates


def extract_syndromes_from_segment(segment: str) -> Set[str]:
    candidates: Set[str] = set()
    cleaned = clean_text(segment)
    for match in SYNDROME_MATCH_RE.finditer(cleaned):
        syndrome = normalize_syndrome(match.group(1))
        if syndrome:
            candidates.add(syndrome)
    for special in SPECIAL_SYNDROME_TERMS:
        if special in cleaned:
            syndrome = normalize_syndrome(special)
            if syndrome:
                candidates.add(syndrome)
    return candidates


def extract_micang_efficacy_segment(line: str) -> str:
    segment = clean_text(line)
    if not segment:
        return ""
    if segment.startswith("此药"):
        segment = segment[2:]
    if "专治" in segment:
        segment = segment.split("专治", 1)[0]
    for marker in MICANG_EFFICACY_MARKERS:
        if marker in segment:
            return segment.split(marker, 1)[1]
    return ""


def parse_formula_quick_index(path: Path, acc: BuildAccumulator) -> None:
    acc.source_files["quji"] = str(path)
    for raw_line in read_text(path).splitlines():
        line = clean_text(raw_line)
        match = QUJI_LINE_RE.match(line)
        if not match:
            continue
        acc.add_term("formulas", match.group(1), "quji")


def parse_formula_song(path: Path, acc: BuildAccumulator) -> None:
    acc.source_files["song"] = str(path)
    current_formula = ""
    for raw_line in read_text(path).splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        match = SONG_HEAD_RE.match(line)
        if match:
            current_formula = normalize_formula(match.group(1))
            if current_formula:
                acc.add_term("formulas", current_formula, "song")
                remainder = line[match.end() :].strip()
                if remainder:
                    acc.add_terms("efficacy", extract_efficacy_from_segment(remainder), "song_efficacy")
            continue
        if current_formula:
            acc.add_terms("herbs", extract_herbs_from_segment(line), "song_herbs")


def parse_formula_entries(path: Path, acc: BuildAccumulator) -> None:
    acc.source_files["entry"] = str(path)
    for raw_line in read_text(path).splitlines():
        line = clean_text(raw_line)
        if not line:
            continue
        head_match = ENTRY_HEAD_RE.match(line)
        if not head_match:
            continue
        formula_name = normalize_formula(head_match.group(1))
        if not formula_name:
            continue
        acc.add_term("formulas", formula_name, "entry")

        body = line[head_match.end() :].strip()
        if not body:
            continue

        alias_match = re.search(r"【别名】(.*?)(?:【|$)", body)
        if alias_match:
            for alias in split_text_terms(alias_match.group(1)):
                acc.add_term("formulas", alias, "entry_alias")
                acc.add_synonym(alias, formula_name, "formulas")

        comp_match = re.search(r"【药物组成】(.*?)(?:【功效】|【主治】|【条文】|【用法用量】|$)", body)
        if comp_match:
            acc.add_terms("herbs", extract_herbs_from_segment(comp_match.group(1)), "entry_herbs")

        efficacy_match = re.search(r"【功效】(.*?)(?:【条文】|【主治】|【用法用量】|$)", body)
        if efficacy_match:
            acc.add_terms("efficacy", extract_efficacy_from_segment(efficacy_match.group(1)), "entry_efficacy")

        treat_match = re.search(r"【主治】(.*?)(?:【用法用量】|【用药禁忌】|【临床应用】|【各家论述】|$)", body)
        if treat_match:
            acc.add_terms("syndromes", extract_syndromes_from_segment(treat_match.group(1)), "entry_syndrome")


def parse_secret_formula_compendium(
    path: Path,
    acc: BuildAccumulator,
    *,
    include_clinical_terms: bool = False,
) -> None:
    acc.source_files["micang"] = str(path)
    lines = [clean_text(line) for line in read_text(path).splitlines() if clean_text(line)]
    current_formula = ""
    collecting_ingredients = False
    for line in lines:
        formula_candidate = normalize_formula(line)
        if formula_candidate:
            current_formula = formula_candidate
            collecting_ingredients = True
            acc.add_term("formulas", current_formula, "micang")
            continue

        if not current_formula:
            continue

        if collecting_ingredients:
            herbs = extract_herbs_from_segment(line)
            if herbs:
                acc.add_terms("herbs", herbs, "micang_herbs")
                continue
            if line.startswith("此药") or "专治" in line or "能" in line:
                collecting_ingredients = False

        if not include_clinical_terms:
            continue

        if "专治" in line:
            acc.add_terms(
                "syndromes",
                extract_syndromes_from_segment(line.split("专治", 1)[1]),
                "micang_syndrome",
            )

        efficacy_segment = extract_micang_efficacy_segment(line)
        if efficacy_segment:
            acc.add_terms("efficacy", extract_efficacy_from_segment(efficacy_segment), "micang_efficacy")


def write_jsonl_records(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_records(acc: BuildAccumulator) -> List[dict]:
    ordered_categories = [
        (CATEGORY_OUTPUT_NAMES["herbs"], sorted(acc.herbs)),
        (CATEGORY_OUTPUT_NAMES["formulas"], sorted(acc.formulas)),
        (CATEGORY_OUTPUT_NAMES["syndromes"], sorted(acc.syndromes)),
        (CATEGORY_OUTPUT_NAMES["theory"], sorted(acc.theory)),
        (CATEGORY_OUTPUT_NAMES["efficacy"], sorted(acc.efficacy)),
        (CATEGORY_OUTPUT_NAMES["common"], sorted(acc.common)),
    ]
    records: List[dict] = []
    for category, terms in ordered_categories:
        records.extend({"term": term, "category": category} for term in terms)
    return records


def build_synonym_records(acc: BuildAccumulator) -> List[dict]:
    records = []
    for alias, canonical, category in sorted(acc.synonyms, key=lambda item: (item[2], item[1], item[0])):
        records.append({"alias": alias, "canonical": canonical, "category": category.rstrip("s")})
    return records


def build_audit_payload(acc: BuildAccumulator) -> Dict[str, List[dict]]:
    payload: Dict[str, List[dict]] = {}
    for attr_name, output_name in CATEGORY_OUTPUT_NAMES.items():
        rows: List[dict] = []
        for term in sorted(getattr(acc, attr_name)):
            rows.append(
                {
                    "term": term,
                    "category": output_name,
                    "sources": sorted(acc.term_sources.get(attr_name, {}).get(term, set())),
                }
            )
        payload[output_name] = rows
    return payload


def write_audit_artifacts(audit_dir: Path, acc: BuildAccumulator, summary: Dict[str, object]) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for category, rows in build_audit_payload(acc).items():
        (audit_dir / f"{category}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_lexicon(root: Path, *, include_micang_clinical_terms: bool = False) -> BuildAccumulator:
    acc = BuildAccumulator()
    build_from_knowledge(acc)

    corpus_files = discover_corpus_files(root)
    if "quji" in corpus_files:
        parse_formula_quick_index(corpus_files["quji"], acc)
    if "song" in corpus_files:
        parse_formula_song(corpus_files["song"], acc)
    if "entry" in corpus_files:
        parse_formula_entries(corpus_files["entry"], acc)
    if "micang" in corpus_files:
        parse_secret_formula_compendium(
            corpus_files["micang"],
            acc,
            include_clinical_terms=include_micang_clinical_terms,
        )

    return acc


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the default TCM lexicon JSONL files from workspace data.")
    parser.add_argument("--lexicon-path", default=str(DEFAULT_LEXICON_PATH), help="Output path for tcm_lexicon.jsonl")
    parser.add_argument("--synonyms-path", default=str(DEFAULT_SYNONYMS_PATH), help="Output path for tcm_synonyms.jsonl")
    parser.add_argument("--audit-dir", default="", help="Optional directory for per-category audit JSON with source provenance")
    parser.add_argument(
        "--include-micang-clinical-terms",
        action="store_true",
        help="Also extract syndrome/efficacy terms from the noisy micang corpus source",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print summary without writing files")
    args = parser.parse_args()

    acc = build_lexicon(ROOT, include_micang_clinical_terms=args.include_micang_clinical_terms)
    lexicon_records = build_records(acc)
    synonym_records = build_synonym_records(acc)
    summary = {
        "counts": acc.summary(),
        "source_files": acc.source_files,
        "source_additions": dict(sorted(acc.source_counts.items())),
        "build_flags": {
            "include_micang_clinical_terms": bool(args.include_micang_clinical_terms),
        },
    }

    if not args.dry_run:
        write_jsonl_records(Path(args.lexicon_path), lexicon_records)
        write_jsonl_records(Path(args.synonyms_path), synonym_records)

    if args.audit_dir:
        write_audit_artifacts(Path(args.audit_dir), acc, summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())