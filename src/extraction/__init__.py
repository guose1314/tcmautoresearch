"""src/extraction — 文献提取模块集合。

提供完整的古籍文献信息提取管道:
- base: 提取框架基底层（规则引擎、数据结构）
- metadata_extractor: 文献元数据提取（标题/作者/朝代）
- medical_content_extractor: 医学内容要素解析（方剂组成/主治/功效）
- clinical_extractor: 临床应用信息提取（医案/穴位/治法）
- academic_value_assessor: 学术价值评估
- quality_checker: 质量校验与报告
- extraction_pipeline: 统一提取管道（编排所有模块）
- relation_extractor: 语义关系抽取（原有）
"""

from src.extraction.base import (
    ExtractedEntityType,
    ExtractedItem,
    ExtractionRelation,
    ExtractionResult,
    ExtractionRule,
    ExtractionRuleEngine,
    PipelineResult,
    RuleType,
)
from src.extraction.extraction_pipeline import ExtractionPipeline
from src.extraction.relation_extractor import RelationExtractor

__all__ = [
    "ExtractionPipeline",
    "ExtractionResult",
    "ExtractionRule",
    "ExtractionRuleEngine",
    "ExtractedEntityType",
    "ExtractedItem",
    "ExtractionRelation",
    "PipelineResult",
    "RelationExtractor",
    "RuleType",
]