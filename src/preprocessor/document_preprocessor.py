# src/preprocessor/document_preprocessor.py
"""
文档预处理模块 - 升级版本，集成古文分词和繁简转换
- jieba 分词（处理现代中文和古文）
- opencc 繁简转换（繁体 → 简体 | 简体 → 繁体）
- 智能换行处理、空白标准化
"""
import logging
import re
import warnings
from datetime import datetime
from typing import Any, Dict, List

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

class DocumentPreprocessor(BaseModule):
    """文档预处理模块 - 支持古文分词和繁简转换"""
    
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
                    self.logger.info(f"加载用户词典: {self.user_dict_path}")
            else:
                self.logger.warning("jieba 未安装，分词功能将不可用")
            
            # 初始化 opencc
            if HAS_OPENCC and OpenCC is not None and self.convert_mode:
                try:
                    self._opencc = OpenCC(self.convert_mode)
                    self.logger.info(f"OpenCC 初始化完成 (mode={self.convert_mode})")
                except Exception as e:
                    self.logger.warning(f"OpenCC 初始化失败: {e}，繁简转换将禁用")
                    self._opencc = None
            else:
                self.logger.info("OpenCC 未启用或未安装")
            
            self.logger.info("文档预处理器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"文档预处理器初始化失败: {e}")
            return False
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行文档预处理"""
        try:
            # 验证输入
            if not context.get("raw_text"):
                raise ValueError("缺少原始文本输入")
            
            raw_text = context["raw_text"]
            if not isinstance(raw_text, str):
                raise ValueError("raw_text 必须为字符串")
            if len(raw_text) > self.max_input_chars:
                raise ValueError(f"输入文本过大，超过限制 {self.max_input_chars} 字符")
            
            # 执行预处理
            processed_text = self._process_text(raw_text)
            metadata = self._extract_metadata(context)
            
            # 计算文本处理统计
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
                # 尝试分词，计算词数
                try:
                    segments = self.segment_text(processed_text)
                    metadata["token_count"] = len(list(segments))
                except Exception:
                    metadata["token_count"] = len(processed_text.split())
            
            # 构造输出
            output_data = {
                "processed_text": processed_text,
                "metadata": metadata,
                "processing_steps": processing_steps
            }
            
            return output_data
            
        except Exception as e:
            self.logger.error(f"文档预处理执行失败: {e}")
            raise
    
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
            self.logger.warning(f"繁简转换失败: {e}，返回原文本")
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
            self.logger.warning(f"分词失败: {e}，使用空格分割")
            return text.split()
    
    def segment_with_ancient_punctuation(self, text: str) -> List[str]:
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
        result = []
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
    
    def _do_cleanup(self) -> bool:
        """清理资源"""
        try:
            self.logger.info("文档预处理器资源清理完成")
            return True
        except Exception as e:
            self.logger.error(f"文档预处理器资源清理失败: {e}")
            return False
