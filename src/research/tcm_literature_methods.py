# src/research/tcm_literature_methods.py
"""
中医文献研究方法模块（TCM Literature Research Methods）。

实现六种核心中医文献研究法：
  1. 文献梳理法  — 文献的时间轴与主题维度系统整理
  2. 文献计量法  — 词频、引用频次、共现网络分析
  3. 古籍校勘法  — 异文比对与文本批评
  4. 训诂学方法  — 古典术语语义解读
  5. 版本对勘法  — 多版本系统比对
  6. 综合研究法  — 多方法综合归纳

所有方法遵循统一接口：``analyze(corpus: dict) -> dict``

用法::

    from src.research.tcm_literature_methods import LiteratureSortingMethod

    method = LiteratureSortingMethod()
    result = method.analyze({"documents": [{"dynasty": "明", "title": "本草纲目", "content": "..."}]})
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 训诂基础词库（古典术语解释） ────────────────────────────────────────────
_EXEGESIS_DICT: Dict[str, str] = {
    "气": "中医基本概念，指人体生命活动的基本物质与动力",
    "血": "营养全身的红色液体，与气相互依存",
    "阴": "对立统一的阴极，代表寒、静、降、里等属性",
    "阳": "对立统一的阳极，代表热、动、升、表等属性",
    "精": "构成人体和维持生命活动的基本物质，包括先天之精和后天之精",
    "神": "广义指生命活动的外在表现，狭义指精神思维活动",
    "津液": "人体内一切正常水液的总称",
    "经络": "运行气血、联系脏腑肢节的通道",
    "脏腑": "内脏的总称，包括五脏六腑",
    "五脏": "心、肝、脾、肺、肾的总称",
    "六腑": "胆、胃、小肠、大肠、膀胱、三焦的总称",
    "证": "对疾病某一阶段病理本质的概括",
    "症": "疾病的临床表现",
    "病机": "疾病发生、发展与变化的机理",
    "治则": "治疗疾病的总原则",
    "君臣佐使": "方剂组成的配伍原则",
    "升降浮沉": "药物作用趋向的四种性质",
    "四气五味": "药物的寒热温凉与酸苦甘辛咸",
    "归经": "药物对脏腑经络的选择性作用",
    "七情": "喜怒忧思悲恐惊七种情志变化",
    "六淫": "风寒暑湿燥火六种外感病邪",
    "本草": "记载药物的古籍，后泛指中药学",
    "方剂": "由多味中药按君臣佐使原则组合的处方",
    "辨证论治": "根据证候进行辨别并制定治疗方案的中医诊疗体系",
    "扶正祛邪": "扶助正气、祛除邪气的治疗原则",
    "标本": "标指现象，本指本质；标本兼治是中医治疗理念",
    "阴阳": "万物对立统一的两种基本属性",
    "五行": "木火土金水五种元素及其相生相克关系",
}


class TCMLiteratureMethod(ABC):
    """中医文献研究方法基类。

    所有具体研究方法均继承此类并实现 ``analyze`` 方法。

    Attributes:
        method_name: 方法中文名称。
        method_code: 方法英文标识符。
    """

    method_name: str = "未命名方法"
    method_code: str = "unnamed"

    @abstractmethod
    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """对给定语料执行本研究方法的分析。

        Args:
            corpus: 语料字典，至少包含以下键之一：
                - ``texts`` (List[str])       — 文本列表
                - ``documents`` (List[dict]) — 结构化文档列表
                - ``text`` (str)             — 单一文本

        Returns:
            包含分析结果的字典，必包含键 ``method``、``status``、``result``。
        """

    def _get_texts(self, corpus: Dict[str, Any]) -> List[str]:
        """从语料中统一提取文本列表。"""
        if "texts" in corpus:
            return [str(t) for t in corpus["texts"] if t]
        if "documents" in corpus:
            return [str(d.get("content") or d.get("text") or d) for d in corpus["documents"]]
        if "text" in corpus:
            return [str(corpus["text"])]
        return []

    def _base_result(self, status: str = "success") -> Dict[str, Any]:
        """构建基础结果字典。"""
        return {
            "method": self.method_name,
            "method_code": self.method_code,
            "status": status,
            "result": {},
        }


# ─────────────────────────────────────────────────────────────────────────────
# 1. 文献梳理法
# ─────────────────────────────────────────────────────────────────────────────

class LiteratureSortingMethod(TCMLiteratureMethod):
    """文献梳理法：对中医文献进行时间轴与主题维度的系统整理。

    功能：
    - 按朝代对文献分组排列，呈现医学思想演变脉络
    - 提取主题标签（关键词），识别核心研究议题
    - 建立文献演变时间线
    """

    method_name = "文献梳理法"
    method_code = "literature_sorting"

    # 朝代排序权重（数值越小越早）
    _DYNASTY_ORDER: Dict[str, int] = {
        "先秦": 0, "秦": 1, "汉": 2, "魏晋": 3, "南北朝": 4,
        "隋": 5, "唐": 6, "宋": 7, "金": 8, "元": 9,
        "明": 10, "清": 11, "民国": 12, "现代": 13,
    }
    # 未知朝代置于末位
    _UNKNOWN_DYNASTY_ORDER: int = 99

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行文献梳理分析。

        Args:
            corpus: 语料字典，支持 ``documents`` 列表（含 dynasty/title 字段）。

        Returns:
            包含朝代分组、主题标签和文献演变脉络的分析结果。
        """
        out = self._base_result()
        try:
            docs = corpus.get("documents", [])
            texts = self._get_texts(corpus)

            # 按朝代分组
            dynasty_groups: Dict[str, List[Any]] = {}
            for doc in docs:
                dynasty = doc.get("dynasty", "未知朝代") if isinstance(doc, dict) else "未知朝代"
                dynasty_groups.setdefault(dynasty, []).append(doc)

            # 已知朝代按权重排序，未知放末
            sorted_dynasties = sorted(
                dynasty_groups.keys(),
                key=lambda d: self._DYNASTY_ORDER.get(d, self._UNKNOWN_DYNASTY_ORDER),
            )

            # 主题关键词提取（简单词频）
            all_text = " ".join(texts)
            theme_keywords = self._extract_theme_keywords(all_text)

            # 演变脉络描述
            evolution_timeline = [
                {"dynasty": d, "doc_count": len(dynasty_groups[d])}
                for d in sorted_dynasties
            ]

            out["result"] = {
                "dynasty_groups": {d: len(dynasty_groups[d]) for d in sorted_dynasties},
                "evolution_timeline": evolution_timeline,
                "theme_keywords": theme_keywords,
                "total_documents": len(docs) or len(texts),
            }
            logger.info("文献梳理法完成，共处理文献 %d 篇", out["result"]["total_documents"])
        except Exception as exc:
            logger.error("文献梳理法执行失败: %s", exc)
            out["status"] = "error"
            out["error"] = str(exc)
        return out

    def _extract_theme_keywords(self, text: str, top_n: int = 20) -> List[str]:
        """提取主题关键词（基于字/词频）。"""
        # 提取双字词以上的词组
        words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        counter = Counter(words)
        # 过滤单字虚词
        stop = {"的", "之", "而", "以", "其", "也", "者", "于", "为", "与", "及", "乃", "则"}
        return [w for w, _ in counter.most_common(top_n + len(stop)) if w not in stop][:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# 2. 文献计量法
# ─────────────────────────────────────────────────────────────────────────────

class BibliometricsMethod(TCMLiteratureMethod):
    """文献计量法：对中医文献进行定量统计分析。

    功能：
    - 词频统计（高频药物/证候/方剂词汇）
    - 文献引用频次分析
    - 药物/证候共现网络构建
    - 高频术语排名
    """

    method_name = "文献计量法"
    method_code = "bibliometrics"

    # 中医核心词汇种子词（用于聚焦统计）
    _TCM_SEED_TERMS = [
        "人参", "黄芪", "当归", "甘草", "白术", "茯苓", "川芎", "熟地",
        "附子", "干姜", "桂枝", "麻黄", "柴胡", "黄连", "黄芩", "大黄",
        "气虚", "血虚", "阴虚", "阳虚", "痰湿", "湿热", "气滞", "血瘀",
        "补气", "补血", "滋阴", "温阳", "清热", "化痰", "活血", "行气",
    ]

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行文献计量分析。

        Args:
            corpus: 语料字典。

        Returns:
            包含词频统计、共现网络等计量结果的字典。
        """
        out = self._base_result()
        try:
            texts = self._get_texts(corpus)
            all_text = "".join(texts)

            # 词频统计
            word_freq = self._count_term_frequency(all_text)
            # 共现矩阵（双词共现）
            cooccurrence = self._build_cooccurrence(texts)
            # 文献来源统计
            docs = corpus.get("documents", [])
            source_stats = self._count_sources(docs)

            out["result"] = {
                "total_chars": len(all_text),
                "total_documents": len(docs) or len(texts),
                "top_terms": word_freq[:30],
                "cooccurrence_pairs": cooccurrence[:20],
                "source_distribution": source_stats,
                "seed_term_hits": {
                    term: all_text.count(term)
                    for term in self._TCM_SEED_TERMS
                    if all_text.count(term) > 0
                },
            }
            logger.info("文献计量法完成，分析文本 %d 字符", len(all_text))
        except Exception as exc:
            logger.error("文献计量法执行失败: %s", exc)
            out["status"] = "error"
            out["error"] = str(exc)
        return out

    def _count_term_frequency(self, text: str, top_n: int = 50) -> List[Dict[str, Any]]:
        """统计中医术语词频。"""
        # 提取双字及以上词组
        words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
        counter = Counter(words)
        return [{"term": w, "count": c} for w, c in counter.most_common(top_n)]

    def _build_cooccurrence(self, texts: List[str], window: int = 50) -> List[Dict[str, Any]]:
        """构建滑动窗口共现对。"""
        from typing import Tuple
        pairs: Counter[Tuple[str, str]] = Counter()
        seed_set = set(self._TCM_SEED_TERMS)
        for text in texts:
            for i in range(0, len(text) - window, window // 2):
                chunk = text[i: i + window]
                found = [t for t in seed_set if t in chunk]
                for j in range(len(found)):
                    for k in range(j + 1, len(found)):
                        pair: Tuple[str, str] = tuple(sorted([found[j], found[k]]))  # type: ignore[assignment]
                        pairs[pair] += 1
        return [
            {"term_a": a, "term_b": b, "count": c}
            for (a, b), c in pairs.most_common(20)
        ]

    def _count_sources(self, docs: List[Any]) -> Dict[str, int]:
        """统计文献来源分布。"""
        sources: Counter = Counter()
        for doc in docs:
            if isinstance(doc, dict):
                src = doc.get("source") or doc.get("title") or "未知来源"
                sources[str(src)] += 1
        return dict(sources.most_common(20))


# ─────────────────────────────────────────────────────────────────────────────
# 3. 古籍校勘法
# ─────────────────────────────────────────────────────────────────────────────

class TextualCriticismMethod(TCMLiteratureMethod):
    """古籍校勘法：对中医古籍进行异文比对与文本批评。

    功能：
    - 异文（variant text）检测与比对
    - 脱文（missing text）标识
    - 衍文（extraneous text）识别
    - 不同版本文本差异统计
    """

    method_name = "古籍校勘法"
    method_code = "textual_criticism"

    # 常见异体字对照表（繁体/异写 → 规范字）
    _VARIANT_CHARS: Dict[str, str] = {
        "藥": "药", "醫": "医", "傳": "传", "証": "证", "癥": "症",
        "藏": "脏", "炙": "炙", "湯": "汤", "丸": "丸", "散": "散",
        "術": "术", "氣": "气", "陽": "阳", "陰": "阴", "經": "经",
        "絡": "络", "熱": "热", "寒": "寒", "虛": "虚", "實": "实",
    }

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行古籍校勘分析。

        Args:
            corpus: 语料字典，``documents`` 中应含 ``version`` 字段标识版本。

        Returns:
            包含异文列表、版本差异统计、校勘建议的结果字典。
        """
        out = self._base_result()
        try:
            docs = corpus.get("documents", [])
            texts = self._get_texts(corpus)

            # 异体字统计
            variant_hits = self._detect_variant_chars("\n".join(texts))
            # 版本差异（若多文档）
            version_diffs = self._compare_versions(docs)
            # 疑难字识别
            uncertain_chars = self._find_uncertain_passages(texts)

            out["result"] = {
                "variant_char_hits": variant_hits,
                "version_comparisons": version_diffs,
                "uncertain_passages": uncertain_chars[:10],
                "total_versions": len({d.get("version", "") for d in docs if isinstance(d, dict) and d.get("version")}),
                "collation_summary": self._build_collation_summary(variant_hits, version_diffs),
            }
            logger.info("古籍校勘法完成，检出异体字 %d 处", len(variant_hits))
        except Exception as exc:
            logger.error("古籍校勘法执行失败: %s", exc)
            out["status"] = "error"
            out["error"] = str(exc)
        return out

    def _detect_variant_chars(self, text: str) -> List[Dict[str, str]]:
        """检测文本中的异体字。"""
        hits = []
        for variant, standard in self._VARIANT_CHARS.items():
            positions = [m.start() for m in re.finditer(re.escape(variant), text)]
            if positions:
                hits.append({
                    "variant": variant,
                    "standard": standard,
                    "occurrences": len(positions),
                    "context": text[max(0, positions[0] - 5): positions[0] + 10],
                })
        return hits

    def _compare_versions(self, docs: List[Any]) -> List[Dict[str, Any]]:
        """比对不同版本文献的差异。"""
        versions: Dict[str, str] = {}
        for doc in docs:
            if isinstance(doc, dict):
                ver = doc.get("version") or doc.get("edition", "")
                content = doc.get("content") or doc.get("text", "")
                if ver and content:
                    versions[str(ver)] = str(content)

        if len(versions) < 2:
            return []

        diffs = []
        ver_list = list(versions.items())
        for i in range(len(ver_list)):
            for j in range(i + 1, len(ver_list)):
                name_a, text_a = ver_list[i]
                name_b, text_b = ver_list[j]
                # 简单字符差异计数
                diff_count = sum(1 for a, b in zip(text_a, text_b) if a != b)
                diffs.append({
                    "version_a": name_a,
                    "version_b": name_b,
                    "char_diff_count": diff_count,
                    "len_diff": abs(len(text_a) - len(text_b)),
                })
        return diffs

    def _find_uncertain_passages(self, texts: List[str]) -> List[str]:
        """识别疑难段落（含脱文/衍文标记）。"""
        uncertain = []
        # 匹配括号内注释、□□等缺字符号
        patterns = [r'□+', r'\[.{1,10}\]', r'（缺[^）]*）', r'【.{1,15}】']
        for text in texts:
            for pat in patterns:
                for m in re.finditer(pat, text):
                    ctx = text[max(0, m.start() - 10): m.end() + 10]
                    uncertain.append(ctx.strip())
        return uncertain

    def _build_collation_summary(
        self, variant_hits: List[Dict[str, str]], version_diffs: List[Dict[str, Any]]
    ) -> str:
        """生成校勘摘要说明。"""
        parts = []
        if variant_hits:
            parts.append(f"发现 {len(variant_hits)} 种异体字，需规范化处理")
        if version_diffs:
            max_diff = max(version_diffs, key=lambda d: d.get("char_diff_count", 0))
            parts.append(
                f"版本差异最大出现在 {max_diff['version_a']} 与 {max_diff['version_b']} 之间"
            )
        return "；".join(parts) if parts else "未检出明显校勘问题"


# ─────────────────────────────────────────────────────────────────────────────
# 4. 训诂学方法
# ─────────────────────────────────────────────────────────────────────────────

class ExegesisMethod(TCMLiteratureMethod):
    """训诂学方法：对中医古典术语进行语义解读与注释。

    功能：
    - 识别文本中的中医古典术语
    - 提供术语训诂解释（基于内置词库或 LLM）
    - 分析术语语义演变
    - 输出注释化文本
    """

    method_name = "训诂学方法"
    method_code = "exegesis"

    def __init__(self, extra_dict: Optional[Dict[str, str]] = None) -> None:
        self._exegesis_dict = dict(_EXEGESIS_DICT)
        if extra_dict:
            self._exegesis_dict.update(extra_dict)

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行训诂分析。

        Args:
            corpus: 语料字典。

        Returns:
            包含术语注释、语义标注结果的字典。
        """
        out = self._base_result()
        try:
            texts = self._get_texts(corpus)
            all_text = "".join(texts)

            # 识别已知术语
            identified = self._identify_terms(all_text)
            # 未识别术语（候选扩充词）
            candidates = self._find_unknown_terms(all_text, identified)
            # 注释化文本
            annotated = self._annotate_text(texts[0] if texts else "", identified)

            out["result"] = {
                "identified_terms": identified,
                "unknown_term_candidates": candidates[:20],
                "annotated_sample": annotated[:500],
                "coverage_rate": (
                    len(identified) / max(len(self._exegesis_dict), 1) * 100
                ),
            }
            logger.info("训诂学方法完成，识别术语 %d 个", len(identified))
        except Exception as exc:
            logger.error("训诂学方法执行失败: %s", exc)
            out["status"] = "error"
            out["error"] = str(exc)
        return out

    def _identify_terms(self, text: str) -> List[Dict[str, str]]:
        """在文本中识别已知训诂术语。"""
        found = []
        for term, explanation in self._exegesis_dict.items():
            if term in text:
                count = text.count(term)
                found.append({"term": term, "explanation": explanation, "count": count})
        return sorted(found, key=lambda x: x["count"], reverse=True)

    def _find_unknown_terms(
        self, text: str, identified: List[Dict[str, str]]
    ) -> List[str]:
        """寻找尚无训诂解释的中医候选术语。"""
        known = {d["term"] for d in identified}
        # 提取四字以内连续汉字词组
        candidates = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        counter = Counter(candidates)
        # 高频且未在词库中的词
        return [w for w, _ in counter.most_common(50) if w not in known]

    def _annotate_text(self, text: str, terms: List[Dict[str, str]]) -> str:
        """在文本后追加简短术语注释。"""
        notes = [f"【{d['term']}】{d['explanation']}" for d in terms[:5]]
        if not notes:
            return text
        return text + "\n\n--- 训诂注释 ---\n" + "\n".join(notes)


# ─────────────────────────────────────────────────────────────────────────────
# 5. 版本对勘法
# ─────────────────────────────────────────────────────────────────────────────

class VersionCollationMethod(TCMLiteratureMethod):
    """版本对勘法：对同一文献的多个版本进行系统比对。

    功能：
    - 版本谱系（stemma）构建
    - 逐段逐句差异标注
    - 底本选取建议
    - 版本流传路径分析
    """

    method_name = "版本对勘法"
    method_code = "version_collation"

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行版本对勘分析。

        Args:
            corpus: 语料字典，``documents`` 中应含 ``version``/``edition`` 字段。

        Returns:
            包含版本谱系、差异统计、底本建议的结果字典。
        """
        out = self._base_result()
        try:
            docs = corpus.get("documents", [])
            versions = self._extract_versions(docs)

            if len(versions) < 2:
                out["result"] = {
                    "message": "版本对勘需要至少两个版本文本",
                    "available_versions": list(versions.keys()),
                }
                return out

            # 逐版本对比
            comparisons = self._pairwise_compare(versions)
            # 版本谱系（简化：按差异度聚类）
            stemma = self._build_stemma(comparisons)
            # 底本建议（选文本最长/差异最少的版本）
            primary_text = self._suggest_primary(versions, comparisons)

            out["result"] = {
                "versions_found": list(versions.keys()),
                "pairwise_comparisons": comparisons,
                "stemma": stemma,
                "suggested_primary_text": primary_text,
                "total_versions": len(versions),
            }
            logger.info("版本对勘法完成，共比对 %d 个版本", len(versions))
        except Exception as exc:
            logger.error("版本对勘法执行失败: %s", exc)
            out["status"] = "error"
            out["error"] = str(exc)
        return out

    def _extract_versions(self, docs: List[Any]) -> Dict[str, str]:
        """从文档列表提取版本字典 {版本名: 内容}。"""
        versions: Dict[str, str] = {}
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            ver = doc.get("version") or doc.get("edition") or doc.get("title", "")
            content = doc.get("content") or doc.get("text", "")
            if ver and content:
                versions[str(ver)] = str(content)
        return versions

    def _pairwise_compare(self, versions: Dict[str, str]) -> List[Dict[str, Any]]:
        """两两版本比对，计算差异指标。"""
        results = []
        ver_list = list(versions.items())
        for i in range(len(ver_list)):
            for j in range(i + 1, len(ver_list)):
                name_a, text_a = ver_list[i]
                name_b, text_b = ver_list[j]
                sim = self._jaccard_similarity(text_a, text_b)
                results.append({
                    "version_a": name_a,
                    "version_b": name_b,
                    "jaccard_similarity": round(sim, 4),
                    "len_a": len(text_a),
                    "len_b": len(text_b),
                    "len_diff": abs(len(text_a) - len(text_b)),
                })
        return sorted(results, key=lambda x: x["jaccard_similarity"], reverse=True)

    def _jaccard_similarity(self, a: str, b: str) -> float:
        """基于字符级 bigram 的 Jaccard 相似度。"""
        bigrams_a = {a[i: i + 2] for i in range(len(a) - 1)}
        bigrams_b = {b[i: i + 2] for i in range(len(b) - 1)}
        if not bigrams_a or not bigrams_b:
            return 0.0
        intersection = len(bigrams_a & bigrams_b)
        union = len(bigrams_a | bigrams_b)
        return intersection / union if union else 0.0

    def _build_stemma(self, comparisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建简化版本谱系（相似度 > 0.8 的版本视为同源）。"""
        clusters: List[List[str]] = []
        for comp in comparisons:
            if comp["jaccard_similarity"] >= 0.8:
                a, b = comp["version_a"], comp["version_b"]
                # 查找已有簇
                merged = False
                for cluster in clusters:
                    if a in cluster or b in cluster:
                        cluster.extend([a, b])
                        merged = True
                        break
                if not merged:
                    clusters.append([a, b])
        return [{"cluster": list(set(c))} for c in clusters]

    def _suggest_primary(
        self, versions: Dict[str, str], comparisons: List[Dict[str, Any]]
    ) -> str:
        """建议底本：优先选文本最长的版本（通常保存最完整）。"""
        if not versions:
            return ""
        return max(versions.items(), key=lambda kv: len(kv[1]))[0]


# ─────────────────────────────────────────────────────────────────────────────
# 6. 综合研究法
# ─────────────────────────────────────────────────────────────────────────────

class IntegratedLiteratureMethod(TCMLiteratureMethod):
    """综合研究法：整合多种文献研究方法的综合分析引擎。

    功能：
    - 依次调用文献梳理、计量、训诂等方法
    - 汇总各方法结果，生成整合性研究报告
    - 提取核心研究结论与研究空白
    - 输出结构化科研摘要
    """

    method_name = "综合研究法"
    method_code = "integrated_literature"

    def __init__(self) -> None:
        self._sub_methods: List[TCMLiteratureMethod] = [
            LiteratureSortingMethod(),
            BibliometricsMethod(),
            ExegesisMethod(),
        ]

    def analyze(self, corpus: Dict[str, Any]) -> Dict[str, Any]:
        """执行综合文献研究分析。

        Args:
            corpus: 语料字典。

        Returns:
            汇总所有子方法结果的综合分析字典。
        """
        out = self._base_result()
        sub_results: Dict[str, Any] = {}
        errors: List[str] = []

        for method in self._sub_methods:
            try:
                sub_results[method.method_code] = method.analyze(corpus)
                logger.debug("子方法 %s 完成", method.method_name)
            except Exception as exc:
                errors.append(f"{method.method_name}: {exc}")
                logger.warning("子方法 %s 执行失败: %s", method.method_name, exc)

        # 汇总核心结论
        texts = self._get_texts(corpus)
        summary = self._synthesize_conclusions(sub_results, texts)

        out["result"] = {
            "sub_method_results": sub_results,
            "integrated_summary": summary,
            "research_gaps": self._identify_gaps(sub_results),
            "errors": errors,
        }
        logger.info("综合研究法完成，运行子方法 %d 个", len(self._sub_methods))
        return out

    def _synthesize_conclusions(
        self, sub_results: Dict[str, Any], texts: List[str]
    ) -> Dict[str, Any]:
        """综合各子方法输出，归纳核心结论。"""
        sorting = sub_results.get("literature_sorting", {}).get("result", {})
        biblio = sub_results.get("bibliometrics", {}).get("result", {})
        exegesis = sub_results.get("exegesis", {}).get("result", {})

        top_terms = [d["term"] for d in biblio.get("top_terms", [])[:5]]
        key_concepts = [d["term"] for d in exegesis.get("identified_terms", [])[:5]]
        dynasties = list(sorting.get("dynasty_groups", {}).keys())

        return {
            "document_span": dynasties,
            "core_terms": top_terms,
            "key_concepts": key_concepts,
            "total_chars": sum(len(t) for t in texts),
            "analysis_confidence": "medium" if texts else "low",
        }

    def _identify_gaps(self, sub_results: Dict[str, Any]) -> List[str]:
        """从各子方法结果识别研究空白。"""
        gaps = []
        biblio = sub_results.get("bibliometrics", {}).get("result", {})
        if biblio.get("total_documents", 0) < 5:
            gaps.append("文献数量不足，建议扩大文献收集范围")
        if not sub_results.get("exegesis", {}).get("result", {}).get("identified_terms"):
            gaps.append("未识别到核心中医术语，建议检查语料质量")
        return gaps


# ─────────────────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────────────────

def create_method(method_code: str) -> TCMLiteratureMethod:
    """工厂函数：根据方法代码创建对应的研究方法实例。

    Args:
        method_code: 方法标识符，如 ``"literature_sorting"``。

    Returns:
        TCMLiteratureMethod 子类实例。

    Raises:
        ValueError: 若方法代码未注册。
    """
    registry: Dict[str, type] = {
        "literature_sorting": LiteratureSortingMethod,
        "bibliometrics": BibliometricsMethod,
        "textual_criticism": TextualCriticismMethod,
        "exegesis": ExegesisMethod,
        "version_collation": VersionCollationMethod,
        "integrated_literature": IntegratedLiteratureMethod,
    }
    cls = registry.get(method_code)
    if cls is None:
        raise ValueError(
            f"未知方法代码 '{method_code}'，可用: {list(registry.keys())}"
        )
    return cls()


__all__ = [
    "TCMLiteratureMethod",
    "LiteratureSortingMethod",
    "BibliometricsMethod",
    "TextualCriticismMethod",
    "ExegesisMethod",
    "VersionCollationMethod",
    "IntegratedLiteratureMethod",
    "create_method",
]
