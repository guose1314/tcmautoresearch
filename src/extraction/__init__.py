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

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ExtractionPipeline": ("src.extraction.extraction_pipeline", "ExtractionPipeline"),
    "ExtractionResult": ("src.extraction.base", "ExtractionResult"),
    "ExtractionRule": ("src.extraction.base", "ExtractionRule"),
    "ExtractionRuleEngine": ("src.extraction.base", "ExtractionRuleEngine"),
    "ExtractedEntityType": ("src.extraction.base", "ExtractedEntityType"),
    "ExtractedItem": ("src.extraction.base", "ExtractedItem"),
    "ExtractionRelation": ("src.extraction.base", "ExtractionRelation"),
    "PipelineResult": ("src.extraction.base", "PipelineResult"),
    "RelationExtractor": ("src.extraction.relation_extractor", "RelationExtractor"),
    "RuleType": ("src.extraction.base", "RuleType"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")