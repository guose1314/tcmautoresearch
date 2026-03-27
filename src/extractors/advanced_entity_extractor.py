# src/extractors/advanced_entity_extractor.py
"""
实体抽取模块 — 升级版本，集成扩展 TCM 词典
- 支持 6000+ 初始词汇（中药、方剂、证候、理论等）
- 支持加载 THUOCL / 外部词典扩展至 3 万+
- 多策略实体识别：词典匹配、正则模式、NER 模型（可选）
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from src.core.module_base import BaseModule
from src.data.tcm_lexicon import get_lexicon

logger = logging.getLogger(__name__)


class AdvancedEntityExtractor(BaseModule):
    """高级实体抽取模块 — 6000+ 中医词汇，支持扩展至 3 万+"""
    
    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("advanced_entity_extractor", config)
        
        # 加载 TCM 词典（全局单例）
        self.lexicon = get_lexicon()
        
        # 剂量单位模式
        self.dosage_patterns = [
            r'([一二三四五六七八九十百千万两钱分斤升枚颗粒克毫]+)\s*([克斤两钱])',
            r'(\d+)\s*([克斤两钱升毫分])',
            r'([一二三四五六七八九十百千万])\s*([克斤两钱升毫分])',
        ]
        
        # 支持加载外部词典（THUOCL 等）
        self.external_dict_paths: List[str] = []
        if config and "external_dicts" in config:
            self.external_dict_paths = config.get("external_dicts", [])
    
    def _do_initialize(self) -> bool:
        """初始化实体抽取器"""
        try:
            # 加载外部词典（如 THUOCL）
            for dict_path in self.external_dict_paths:
                if Path(dict_path).exists():
                    # 将路径作为词汇类型推断（可根据文件名）
                    self.lexicon.load_from_file(dict_path, word_type="common")
                    self.logger.info(f"加载外部词典: {dict_path}")
                else:
                    self.logger.warning(f"外部词典不存在: {dict_path}")
            
            vocab_size = self.lexicon.get_vocab_size()
            self.logger.info(f"实体抽取器初始化完成 (词汇总数: {vocab_size})")
            return True
        except Exception as e:
            self.logger.error(f"实体抽取器初始化失败: {e}")
            return False
    
    def _load_dictionaries(self):
        """加载专业词典 — 已由 TCMLexicon 处理"""
        pass  # 词典已在 __init__ 中通过 get_lexicon() 加载
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行实体抽取"""
        try:
            # 验证输入
            if not context.get("processed_text"):
                raise ValueError("缺少处理后的文本输入")
            
            # 执行实体抽取
            entities = self._extract_entities(context["processed_text"])
            
            # 构造输出
            output_data = {
                "entities": entities,
                "statistics": self._calculate_statistics(entities),
                "confidence_scores": self._calculate_confidence(entities)
            }
            
            return output_data
            
        except Exception as e:
            self.logger.error(f"实体抽取执行失败: {e}")
            raise
    
    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        使用最长匹配策略抽取实体。
        优先级：长词 > 短词，避免重复标注
        """
        entities = []
        matched_positions = set()  # 记录已匹配位置，避免重复
        
        # 对词典中的所有词进行最长匹配
        # 按词长从长到短排序，确保优先匹配长词
        all_words = sorted(self.lexicon.get_all_words(), key=len, reverse=True)
        
        for word in all_words:
            # 在文本中查找所有出现位置
            for start_pos in range(len(text) - len(word) + 1):
                if text[start_pos : start_pos + len(word)] == word:
                    end_pos = start_pos + len(word)
                    
                    # 检查是否与已匹配位置重叠
                    if any(pos in matched_positions for pos in range(start_pos, end_pos)):
                        continue
                    
                    # 获取词汇类型
                    word_type = self.lexicon.get_word_type(word)
                    
                    # 添加实体
                    entities.append({
                        "name": word,
                        "type": word_type or "unknown",
                        "confidence": self._calculate_word_confidence(word_type),
                        "position": start_pos,
                        "end_position": end_pos,
                        "length": len(word),
                    })
                    
                    # 标记已匹配位置
                    matched_positions.update(range(start_pos, end_pos))
        
        # 提取剂量实体
        dosages = self._extract_dosages(text)
        entities.extend(dosages)
        
        # 按位置排序
        entities.sort(key=lambda e: e.get("position", 0))
        
        return entities
    
    def _calculate_word_confidence(self, word_type: str | None) -> float:
        """根据词汇类型计算置信度"""
        confidence_map = {
            "herb": 0.95,
            "formula": 0.95,
            "syndrome": 0.90,
            "theory": 0.85,
            "efficacy": 0.85,
            "common": 0.80,
            None: 0.70,
        }
        return confidence_map.get(word_type, 0.70)
    
    def _extract_dosages(self, text: str) -> List[Dict[str, Any]]:
        """提取剂量信息"""
        dosages = []
        
        # 使用多种正则模式匹配剂量
        for pattern in self.dosage_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                amount = match.group(1) if len(match.groups()) > 0 else ""
                unit = match.group(2) if len(match.groups()) > 1 else ""
                start_pos, end_pos = match.span()
                dose_info = {
                    "name": f"{amount}{unit}",
                    "type": "dosage",
                    "amount": amount,
                    "unit": unit,
                    "confidence": 0.75,
                    "position": start_pos,
                    "end_position": end_pos,
                    "length": len(f"{amount}{unit}")
                }
                dosages.append(dose_info)
        
        return dosages
    
    def _calculate_statistics(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算统计信息"""
        stats = {
            "total_count": len(entities),
            "by_type": {},
            "coverage_rate": 0.0,
        }
        
        # 按类型分类
        type_counts = {}
        for entity in entities:
            entity_type = entity.get("type", "unknown")
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
        
        stats["by_type"] = type_counts
        
        return stats
    
    def _calculate_confidence(self, entities: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算置信度统计"""
        if not entities:
            return {"average_confidence": 0.0}
        
        total_confidence = sum(e.get("confidence", 0.5) for e in entities)
        avg_confidence = total_confidence / len(entities)
        
        return {
            "average_confidence": avg_confidence,
            "min_confidence": min(e.get("confidence", 0.5) for e in entities),
            "max_confidence": max(e.get("confidence", 0.5) for e in entities),
        }
    
    def load_external_lexicon(self, filepath: str, word_type: str = "common") -> int:
        """
        加载外部词典文件（如 THUOCL）。
        
        Args:
            filepath: 外部词典文件路径
            word_type: 词汇分类 (herb, formula, syndrome, theory, efficacy, common)
        
        Returns:
            加载的词汇数
        """
        count = self.lexicon.load_from_file(filepath, word_type)
        if count > 0:
            self.logger.info(f"已加载 {count} 个外部 {word_type} 词汇，词典总规模: {self.lexicon.get_vocab_size()}")
        return count
    
    def export_extracted_lexicon(self, filepath: str) -> None:
        """
        导出当前词典为 jieba 格式，方便分词使用。
        
        Args:
            filepath: 输出文件路径
        """
        self.lexicon.export_to_jieba_format(filepath, word_type="common")
        self.logger.info(f"已导出词典到 {filepath}")
    
    def _do_cleanup(self) -> bool:
        """清理资源"""
        try:
            self.logger.info("实体抽取器资源清理完成")
            return True
        except Exception as e:
            self.logger.error(f"实体抽取器资源清理失败: {e}")
            return False
