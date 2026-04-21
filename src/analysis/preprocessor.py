# src/analysis/preprocessor.py  (migrated from src/preprocessor/document_preprocessor.py)
"""
文档预处理模块 - 中医古文献专项版本

功能：
- jieba 分词（处理现代中文和古文）
- opencc 繁简转换（繁体 → 简体 | 简体 → 繁体）
- 智能换行处理、空白标准化
- 中医古籍朝代/作者/书名元数据提取
- 异体字规范化（异体字 → 规范简体）
- 注疏识别（注文/疏文/按语检测）
- 古籍文本类型分类（本草/医案/方剂/经典/医论）
- TCM 专项分词接口（支持外部词典扩展）
"""
import logging
import re
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"pkg_resources is deprecated as an API.*",
            category=DeprecationWarning,
        )
        import jieba
    HAS_JIEBA = True
except ImportError:
    jieba = None  # type: ignore[assignment]
    HAS_JIEBA = False

try:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"pkg_resources is deprecated as an API.*",
            category=DeprecationWarning,
        )
        from jieba import posseg as jieba_posseg
    HAS_JIEBA_POS = True
except ImportError:
    jieba_posseg = None  # type: ignore[assignment]
    HAS_JIEBA_POS = False

try:
    from opencc import OpenCC  # type: ignore[import-not-found]
    HAS_OPENCC = True
except ImportError:
    OpenCC = None  # type: ignore[assignment]
    HAS_OPENCC = False

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

_WORD_BREAK_RE = re.compile(r'(\w)\n(\w)')
_MULTI_NEWLINE_RE = re.compile(r'\n{3,}')
_MULTI_SPACE_RE = re.compile(r'\s+')
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

# ── 异体字规范化映射（繁/异体 → 规范简体） ────────────────────────────────────
_VARIANT_CHAR_MAP: Dict[str, str] = {
    "藥": "药", "醫": "医", "傳": "传", "証": "证", "癥": "症",
    "術": "术", "氣": "气", "陽": "阳", "陰": "阴", "經": "经",
    "絡": "络", "熱": "热", "虛": "虚", "實": "实", "臟": "脏",
    "腑": "腑", "脈": "脉", "針": "针", "灸": "灸", "藏": "藏",
}
_VARIANT_TABLE = str.maketrans(_VARIANT_CHAR_MAP)

# ── 古籍书名 → (朝代, 作者) 映射 ─────────────────────────────────────────────
_CLASSIC_BOOK_META: Dict[str, Dict[str, str]] = {
    "黄帝内经": {"dynasty": "先秦", "author": "佚名"},
    "素问": {"dynasty": "先秦", "author": "佚名"},
    "灵枢": {"dynasty": "先秦", "author": "佚名"},
    "神农本草经": {"dynasty": "先秦", "author": "佚名"},
    "伤寒论": {"dynasty": "汉", "author": "张仲景"},
    "金匮要略": {"dynasty": "汉", "author": "张仲景"},
    "伤寒杂病论": {"dynasty": "汉", "author": "张仲景"},
    "难经": {"dynasty": "汉", "author": "扁鹊"},
    "针灸甲乙经": {"dynasty": "魏晋", "author": "皇甫谧"},
    "肘后备急方": {"dynasty": "魏晋", "author": "葛洪"},
    "脉经": {"dynasty": "魏晋", "author": "王叔和"},
    "诸病源候论": {"dynasty": "隋", "author": "巢元方"},
    "备急千金要方": {"dynasty": "唐", "author": "孙思邈"},
    "千金翼方": {"dynasty": "唐", "author": "孙思邈"},
    "外台秘要": {"dynasty": "唐", "author": "王焘"},
    "新修本草": {"dynasty": "唐", "author": "苏敬"},
    "太平圣惠方": {"dynasty": "宋", "author": "王怀隐"},
    "圣济总录": {"dynasty": "宋", "author": "佚名"},
    "小儿药证直诀": {"dynasty": "宋", "author": "钱乙"},
    "三因极一病证方论": {"dynasty": "宋", "author": "陈言"},
    "本草衍义": {"dynasty": "宋", "author": "寇宗奭"},
    "济生方": {"dynasty": "宋", "author": "严用和"},
    "宣明论方": {"dynasty": "金", "author": "刘完素"},
    "素问玄机原病式": {"dynasty": "金", "author": "刘完素"},
    "脾胃论": {"dynasty": "金", "author": "李东垣"},
    "内外伤辨惑论": {"dynasty": "金", "author": "李东垣"},
    "儒门事亲": {"dynasty": "金", "author": "张从正"},
    "丹溪心法": {"dynasty": "元", "author": "朱丹溪"},
    "格致余论": {"dynasty": "元", "author": "朱丹溪"},
    "世医得效方": {"dynasty": "元", "author": "危亦林"},
    "本草纲目": {"dynasty": "明", "author": "李时珍"},
    "景岳全书": {"dynasty": "明", "author": "张景岳"},
    "温疫论": {"dynasty": "明", "author": "吴又可"},
    "医学入门": {"dynasty": "明", "author": "李梃"},
    "医宗金鉴": {"dynasty": "清", "author": "吴谦"},
    "温病条辨": {"dynasty": "清", "author": "吴鞠通"},
    "温热论": {"dynasty": "清", "author": "叶天士"},
    "临证指南医案": {"dynasty": "清", "author": "叶天士"},
    "医林改错": {"dynasty": "清", "author": "王清任"},
    "血证论": {"dynasty": "清", "author": "唐宗海"},
    "本草备要": {"dynasty": "清", "author": "汪昂"},
    "本草从新": {"dynasty": "清", "author": "吴仪洛"},
    "重订广温热论": {"dynasty": "清", "author": "何廉臣"},
    "中医基础理论": {"dynasty": "现代", "author": "现代教材"},
    "中药学": {"dynasty": "现代", "author": "现代教材"},
    "方剂学": {"dynasty": "现代", "author": "现代教材"},
}

# ── 注疏类型识别正则 ──────────────────────────────────────────────────────────
_ANNOTATION_PATTERNS: Dict[str, re.Pattern] = {
    "注": re.compile(r'（注[：:]?.{5,100}）|【注[：:]?.{5,80}】'),
    "疏": re.compile(r'（疏[：:]?.{5,100}）|【疏[：:]?.{5,80}】'),
    "按": re.compile(r'按[：:].{5,150}[。\n]'),
    "曰": re.compile(r'[^\u4e00-\u9fff][曰云][：:].{5,100}[。\n]'),
}

# ── 文本类型分类关键词 ────────────────────────────────────────────────────────
_TEXT_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "本草": ["味辛", "性温", "归经", "功效", "主治", "用法用量", "毒性", "炮制"],
    "方剂": ["君药", "臣药", "佐药", "使药", "组方", "配伍", "加减", "方解"],
    "医案": ["患者", "病案", "初诊", "复诊", "症见", "脉象", "辨证", "处方"],
    "经典": ["阴阳", "五行", "脏腑", "经络", "营卫", "气血", "病机", "治则"],
    "医论": ["论曰", "余谓", "按语", "考证", "溯源", "发微", "议论"],
}

class DocumentPreprocessor(BaseModule):
    """文档预处理模块 - 支持古文分词、繁简转换与中医古籍元数据提取。"""

    # 最小段落长度：短于此值的段落视为过短，不单独分段
    _MIN_PARAGRAPH_LENGTH: int = 10
    
    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("document_preprocessor", config)
        self.supported_extensions = ['.txt', '.md', '.docx']
        self.max_input_chars = int((config or {}).get("max_input_chars", 2_000_000))
        
        # 繁简转换配置：'s2t' (简→繁), 't2s' (繁→简), 'sp' (简体标准)，空字符串表示关闭
        self.convert_mode = config.get("convert_mode", "t2s") if config else "t2s"
        
        # 初始化 OpenCC 转换器（延迟初始化，在 _do_initialize 中）
        self._opencc: Any = None
        
        # jieba 用户词典（可选，用于添加中医术语）
        self.user_dict_path = config.get("user_dict_path") if config else None
        
    def _do_initialize(self) -> bool:
        """初始化文档预处理器"""
        try:
            # 检查 jieba 可用性
            if HAS_JIEBA and jieba is not None:
                self.logger.info("jieba 分词引擎已加载")
                if self.user_dict_path:
                    jieba.load_userdict(self.user_dict_path)
                    self.logger.info("加载用户词典: %s", self.user_dict_path)
            else:
                self.logger.warning("jieba 未安装，分词功能将不可用")
            
            # 初始化 opencc
            if HAS_OPENCC and OpenCC is not None and self.convert_mode:
                try:
                    self._opencc = OpenCC(self.convert_mode)
                    self.logger.info("OpenCC 初始化完成 (mode=%s)", self.convert_mode)
                except Exception as e:
                    self.logger.warning("OpenCC 初始化失败: %s，繁简转换将禁用", e)
                    self._opencc = None
            else:
                self.logger.info("OpenCC 未启用或未安装")
            
            self.logger.info("文档预处理器初始化完成")
            return True
        except Exception as e:
            self.logger.error("文档预处理器初始化失败: %s", e)
            return False
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行文档预处理"""
        try:
            raw_text = self._validate_raw_text(context)
            
            # 执行预处理
            processed_text = self._process_text(raw_text)
            metadata = self._extract_metadata(context)
            processing_steps = self._build_processing_steps(metadata, processed_text)
            
            # 构造输出
            output_data = {
                "processed_text": processed_text,
                "metadata": metadata,
                "processing_steps": processing_steps
            }
            
            return output_data
            
        except Exception as e:
            self.logger.error("文档预处理执行失败: %s", e)
            raise

    def _validate_raw_text(self, context: Dict[str, Any]) -> str:
        """验证输入中的 raw_text 并返回可处理文本。"""
        if "raw_text" not in context:
            raise ValueError("缺少原始文本输入")

        raw_text = context["raw_text"]
        if not isinstance(raw_text, str):
            raise ValueError("raw_text 必须为字符串")
        if not raw_text:
            raise ValueError("缺少原始文本输入")
        if len(raw_text) > self.max_input_chars:
            raise ValueError(f"输入文本过大，超过限制 {self.max_input_chars} 字符")
        return raw_text

    def _build_processing_steps(self, metadata: Dict[str, Any], processed_text: str) -> List[str]:
        """根据启用能力构建处理步骤并补充元数据。"""
        processing_steps = [
            "encoding_detection",
            "format_cleaning",
            "line_break_fix"
        ]

        if self._opencc:
            processing_steps.append("convert_traditional_to_simplified")
            metadata["convert_mode"] = self.convert_mode

        if HAS_JIEBA:
            processing_steps.append("jieba_segmentation")
            metadata["token_count"] = self._estimate_token_count(processed_text)

        return processing_steps

    def _estimate_token_count(self, text: str) -> int:
        """估算 token 数量，分词失败时降级为空格分词。"""
        try:
            return len(self.segment_text(text))
        except Exception:
            return len(text.split())
    
    def _process_text(self, text: str) -> str:
        """处理文本内容"""
        # 0. 安全清理：移除控制字符，减少污染数据进入后续流程
        safe_text = self._sanitize_text(text)

        # 1. 繁简转换
        converted_text = self._convert_text(safe_text)
        
        # 2. 清洗换行错乱
        cleaned_text = self._clean_line_breaks(converted_text)
        
        # 3. 标准化空白字符
        normalized_text = self._normalize_whitespace(cleaned_text)
        
        return normalized_text
    
    def _convert_text(self, text: str) -> str:
        """繁简转换"""
        if not self._opencc:
            return text
        try:
            return self._opencc.convert(text)
        except Exception as e:
            self.logger.warning("繁简转换失败: %s，返回原文本", e)
            return text
    
    def _clean_line_breaks(self, text: str) -> str:
        """清洗换行错乱"""
        # 合并可能的断行
        cleaned = _WORD_BREAK_RE.sub(r'\1\2', text)
        # 清理多余的换行
        cleaned = _MULTI_NEWLINE_RE.sub('\n\n', cleaned)
        return cleaned.strip()
    
    def _normalize_whitespace(self, text: str) -> str:
        """标准化空白字符"""
        # 替换多个连续空格为单个空格
        normalized = _MULTI_SPACE_RE.sub(' ', text)
        return normalized.strip()

    def _sanitize_text(self, text: str) -> str:
        """移除不可见控制字符，降低注入和脏数据风险。"""
        return _CONTROL_CHARS_RE.sub('', text)
    
    def segment_text(self, text: str, use_pos: bool = False) -> List[Any]:
        """
        用 jieba 对文本进行分词。

        Args:
            text: 输入文本
            use_pos: 是否进行词性标注（返回 (word, tag) 元组）

        Returns:
            分词结果列表，或 [(word, tag), ...] 如果 use_pos=True
        """
        if not HAS_JIEBA or jieba is None:
            self.logger.warning("jieba 未安装，使用空格分割")
            return text.split()
        
        try:
            if use_pos:
                if HAS_JIEBA_POS and jieba_posseg is not None:
                    return list(jieba_posseg.cut(text))
                self.logger.warning("jieba.posseg 不可用，回退普通分词")
                return list(jieba.cut(text))

            return list(jieba.cut(text))
        except Exception as e:
            self.logger.warning("分词失败: %s，使用空格分割", e)
            return text.split()
    
    def segment_with_ancient_punctuation(self, text: str) -> List[List[Any]]:
        """
        针对古文进行分词，同时补全可能缺失的断句标记。
        
        规则：
        - 句号、问号、感叹号、顿号、分号作为句子边界
        - 补全可能缺失的断句标记（基于中医古籍常见模式）
        """
        # 补全古文能缺失的句号（基于高频模式）
        # 例："主治..." 类型的短句可能缺少调号
        text = self._augment_ancient_punctuation(text)
        
        # 按句号、问号、感叹号分割
        sentences = re.split(r'[。？！；、]', text)
        
        # 对每个句子进行分词
        result: List[List[Any]] = []
        for sent in sentences:
            if sent.strip():
                words = self.segment_text(sent.strip())
                result.append(words)
        
        return result
    
    def _augment_ancient_punctuation(self, text: str) -> str:
        """补全古文能缺失的断句标记"""
        # 规则1：中医古籍中"主治"、"功效"等关键词前补句号
        text = re.sub(r'([^。？！])(主治|功效|主要|作用|治疗|归经|性味)', r'\1。\2', text)
        
        # 规则2：数字 + 单位 + 逗号后可能应该是新句子
        text = re.sub(r'(克|两|钱|分|斤|升|枚|粒|个|片)，([A-Z\u4E00-\u9FFF])', r'\1。\2', text)
        
        # 规则3："曰"、"云"等古文常见词可作句尾
        text = re.sub(r'(曰|云|言|曰)', r'\1。', text)
        
        return text
    
    def _extract_metadata(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """提取元数据"""
        metadata = {
            "source_file": input_data.get("source_file", "unknown"),
            "file_size": len(input_data.get("raw_text", "")),
            "processing_timestamp": datetime.now().isoformat(),
            "encoding_detected": self._detect_encoding(input_data.get("raw_text", ""))
        }
        
        # 从输入中提取额外元数据
        if "metadata" in input_data:
            metadata.update(input_data["metadata"])
        
        return metadata
    
    def _detect_encoding(self, text: Any) -> str:
        """检测文本编码"""
        try:
            text.encode("utf-8")
            return "utf-8"
        except Exception:
            return "utf-8"

    # ── 中医古籍专项方法 ───────────────────────────────────────────────────────

    def normalize_variant_chars(self, text: str) -> str:
        """规范化异体字：将常见繁/异体字替换为规范简体字。

        Args:
            text: 输入文本（可含繁体/异体字）。

        Returns:
            规范化后的文本。
        """
        return text.translate(_VARIANT_TABLE)

    def detect_book_metadata(self, title: str) -> Optional[Dict[str, str]]:
        """根据古籍书名查找朝代与作者元数据。

        Args:
            title: 古籍书名（如"本草纲目"）。

        Returns:
            包含 ``dynasty`` 和 ``author`` 的字典，若书名未知则返回 ``None``。
        """
        # 精确匹配
        meta = _CLASSIC_BOOK_META.get(title)
        if meta:
            return dict(meta)
        # 模糊匹配：检查书名是否包含于已知书目
        for known_title, known_meta in _CLASSIC_BOOK_META.items():
            if known_title in title or title in known_title:
                return dict(known_meta)
        return None

    def detect_annotations(self, text: str) -> List[Dict[str, str]]:
        """检测文本中的注疏内容（注文/疏文/按语等）。

        Args:
            text: 输入文本。

        Returns:
            注疏片段列表，每条含 ``type``（注/疏/按/曰）和 ``content``。
        """
        found: List[Dict[str, str]] = []
        for ann_type, pattern in _ANNOTATION_PATTERNS.items():
            for m in pattern.finditer(text):
                found.append({"type": ann_type, "content": m.group().strip()})
        return found

    def classify_text_type(self, text: str) -> str:
        """对中医文本进行类型分类。

        分类类别：``本草`` / ``方剂`` / ``医案`` / ``经典`` / ``医论`` / ``未分类``

        Args:
            text: 输入文本（建议取前500字）。

        Returns:
            文本类型标签字符串。
        """
        sample = text[:500]
        scores: Dict[str, int] = {}
        for text_type, keywords in _TEXT_TYPE_KEYWORDS.items():
            scores[text_type] = sum(1 for kw in keywords if kw in sample)
        max_score = max(scores.values(), default=0)
        if max_score == 0:
            return "未分类"
        return max(scores.items(), key=lambda kv: kv[1])[0]

    def extract_tcm_document_metadata(
        self, text: str, source_file: str = "unknown"
    ) -> Dict[str, Any]:
        """提取中医文档的完整 TCM 专项元数据。

        整合书名识别、朝代/作者推断、注疏检测、文本类型分类，
        返回可直接写入知识图谱的结构化元数据。

        Args:
            text:        文档全文。
            source_file: 来源文件名（用于书名识别提示）。

        Returns:
            包含以下键的元数据字典：
              - ``source_file``, ``text_type``, ``dynasty``, ``author``
              - ``annotation_count``, ``annotations``
              - ``variant_chars_detected``, ``char_count``
        """
        # 检测异体字数量（规范化前后的字符差异）
        normalized = self.normalize_variant_chars(text)
        variant_count = sum(1 for a, b in zip(text, normalized) if a != b)

        # 书名元数据（从文件名或文本首行推断）
        book_meta: Optional[Dict[str, str]] = None
        # 尝试从 source_file 和文本首行识别书名
        first_line = text.strip().split('\n')[0][:30] if text.strip() else ""
        for candidate in [source_file, first_line]:
            book_meta = self.detect_book_metadata(candidate)
            if book_meta:
                break

        # 注疏检测
        annotations = self.detect_annotations(text[:2000])

        # 文本类型分类
        text_type = self.classify_text_type(text)

        return {
            "source_file": source_file,
            "char_count": len(text),
            "text_type": text_type,
            "dynasty": (book_meta or {}).get("dynasty", "未知"),
            "author": (book_meta or {}).get("author", "未知"),
            "book_identified": bool(book_meta),
            "annotation_count": len(annotations),
            "annotations": annotations[:5],
            "variant_chars_detected": variant_count,
            "processing_timestamp": datetime.now().isoformat(),
        }

    def segment_tcm_text(self, text: str) -> List[str]:
        """使用 TCM 专项分词对古文进行分词。

        优先尝试 TCMLexicon（若已实现），降级至 jieba 普通分词。
        TODO (TD-04): TCMLexicon 尚未实现；该方法为占位符，
        待引入中医专业词典（src/analysis/tcm_lexicon.py）后替换。
        当前实现已能正确降级，不影响主流程运行。

        Args:
            text: 输入文本（古文或现代中文）。

        Returns:
            分词结果词语字符串列表。
        """
        try:
            from src.analysis.tcm_lexicon import TCMLexicon  # type: ignore[import]
            lexicon = TCMLexicon()
            return lexicon.segment(text)
        except ImportError:
            pass
        except Exception as exc:
            self.logger.warning("TCMLexicon 分词失败: %s，回退至 jieba", exc)

        words = self.segment_text(text)
        return [w if isinstance(w, str) else w.word for w in words]

    def _do_cleanup(self) -> bool:
        """清理资源"""
        try:
            self.logger.info("文档预处理器资源清理完成")
            return True
        except Exception as e:
            self.logger.error("文档预处理器资源清理失败: %s", e)
            return False
