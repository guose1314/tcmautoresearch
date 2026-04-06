"""统一提取管道 — 编排所有提取模块，支持批量处理和增量更新。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from src.extraction.base import (
    ExtractedItem,
    ExtractionRelation,
    ExtractionResult,
    PipelineResult,
)

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """文献提取管道。

    编排流程:
    1. 预处理 → 2. 实体提取 → 3. 元数据提取 → 4. 医学内容解析
    → 5. 临床信息提取 → 6. 关系抽取 → 7. 学术评估 → 8. 质量校验

    每个模块可独立启用/禁用，支持自定义规则注入。
    """

    def __init__(
        self,
        enable_metadata: bool = True,
        enable_medical_content: bool = True,
        enable_clinical: bool = True,
        enable_relation: bool = True,
        enable_academic_assessment: bool = True,
        enable_quality_check: bool = True,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._config = config or {}
        self._enable = {
            "metadata": enable_metadata,
            "medical_content": enable_medical_content,
            "clinical": enable_clinical,
            "relation": enable_relation,
            "academic_assessment": enable_academic_assessment,
            "quality_check": enable_quality_check,
        }

        # 延迟初始化，避免循环导入
        self._preprocessor: Any = None
        self._entity_extractor: Any = None
        self._metadata_extractor: Any = None
        self._medical_extractor: Any = None
        self._clinical_extractor: Any = None
        self._relation_extractor: Any = None
        self._academic_assessor: Any = None
        self._quality_checker: Any = None

    # ------------------------------------------------------------------
    # 延迟初始化
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        if self._preprocessor is not None:
            return

        from src.analysis.entity_extractor import AdvancedEntityExtractor
        from src.analysis.preprocessor import DocumentPreprocessor
        from src.extraction.academic_value_assessor import AcademicValueAssessor
        from src.extraction.clinical_extractor import ClinicalExtractor
        from src.extraction.medical_content_extractor import MedicalContentExtractor
        from src.extraction.metadata_extractor import MetadataExtractor
        from src.extraction.quality_checker import QualityChecker
        from src.extraction.relation_extractor import RelationExtractor

        preproc_cfg = self._config.get("preprocessor", {})
        entity_cfg = self._config.get("entity_extractor", {})

        self._preprocessor = DocumentPreprocessor(preproc_cfg)
        self._preprocessor.initialize()

        self._entity_extractor = AdvancedEntityExtractor(entity_cfg)
        self._entity_extractor.initialize()

        self._metadata_extractor = MetadataExtractor()
        self._medical_extractor = MedicalContentExtractor()
        self._clinical_extractor = ClinicalExtractor()
        self._relation_extractor = RelationExtractor()
        self._academic_assessor = AcademicValueAssessor()
        self._quality_checker = QualityChecker()

    # ------------------------------------------------------------------
    # 单文档处理
    # ------------------------------------------------------------------

    def process_document(
        self,
        raw_text: str,
        source_file: str = "",
        document_id: str = "",
    ) -> PipelineResult:
        """全流程处理单篇文档。"""
        self._ensure_initialized()
        t0 = time.perf_counter()
        doc_id = document_id or str(uuid.uuid4())[:8]

        result = PipelineResult(document_id=doc_id, source_file=source_file)

        try:
            # 1. 预处理
            preprocessed = self._preprocessor.execute({"raw_text": raw_text})
            processed_text = str(preprocessed.get("processed_text") or raw_text)
            text_length = len(processed_text)

            # 2. 实体提取（核心）
            entity_output = self._entity_extractor.execute({"processed_text": processed_text})
            entities_raw: List[Dict[str, Any]] = entity_output.get("entities", [])
            core_items = [
                ExtractedItem(
                    name=e.get("name", ""),
                    entity_type=e.get("type", "generic"),
                    confidence=e.get("confidence", 0.7),
                    position=e.get("position", 0),
                    end_position=e.get("end_position", 0),
                    length=e.get("length", 0),
                    original_text=e.get("original_name", ""),
                    source_module="entity_extractor",
                )
                for e in entities_raw
            ]
            result.module_results["entity_extractor"] = ExtractionResult(
                module_name="entity_extractor",
                items=core_items,
                statistics=entity_output.get("statistics", {}),
                quality_scores=entity_output.get("confidence_scores", {}),
            )
            result.all_items.extend(core_items)

            # 3. 元数据提取
            if self._enable["metadata"]:
                meta_result = self._metadata_extractor.extract(
                    processed_text, source_file=source_file,
                )
                result.module_results["metadata"] = meta_result
                result.all_items.extend(meta_result.items)
                result.all_relations.extend(meta_result.relations)

            # 4. 医学内容提取
            if self._enable["medical_content"]:
                med_result = self._medical_extractor.extract(
                    processed_text, entities=entities_raw,
                )
                result.module_results["medical_content"] = med_result
                result.all_items.extend(med_result.items)
                result.all_relations.extend(med_result.relations)

            # 5. 临床信息提取
            if self._enable["clinical"]:
                clin_result = self._clinical_extractor.extract(processed_text)
                result.module_results["clinical"] = clin_result
                result.all_items.extend(clin_result.items)
                result.all_relations.extend(clin_result.relations)

            # 6. 关系抽取
            if self._enable["relation"]:
                relation_edges = self._relation_extractor.extract(entities_raw)
                rel_items_converted = [
                    ExtractionRelation(
                        source=str(edge.get("source", "")),
                        target=str(edge.get("target", "")),
                        relation_type=str(edge.get("attributes", {}).get("relationship_type", "unknown")),
                        confidence=float(edge.get("attributes", {}).get("confidence", 0.7)),
                        source_module="relation_extractor",
                    )
                    for edge in relation_edges
                ]
                result.module_results["relation"] = ExtractionResult(
                    module_name="relation_extractor",
                    relations=rel_items_converted,
                    statistics={"edge_count": len(rel_items_converted)},
                )
                result.all_relations.extend(rel_items_converted)

            # 7. 学术价值评估
            if self._enable["academic_assessment"]:
                dynasty = self._detect_dynasty(result.all_items)
                acad_result = self._academic_assessor.assess_as_result(
                    result.all_items, result.all_relations,
                    text_length=text_length, dynasty=dynasty,
                )
                result.module_results["academic_assessment"] = acad_result

            # 8. 质量校验
            if self._enable["quality_check"]:
                quality_report = self._quality_checker.check(result, text_length=text_length)
                result.overall_quality = {
                    "score": quality_report.overall_score,
                    "grade": quality_report.grade,
                    **quality_report.completeness,
                    **quality_report.coverage,
                }
                result.module_results["quality_check"] = ExtractionResult(
                    module_name="quality_checker",
                    statistics=quality_report.to_dict(),
                    quality_scores={"overall": quality_report.overall_score},
                )

        except Exception as exc:
            logger.error("ExtractionPipeline error for %s: %s", source_file, exc, exc_info=True)
            result.errors.append(str(exc))

        result.total_duration_sec = time.perf_counter() - t0
        return result

    # ------------------------------------------------------------------
    # 批量处理
    # ------------------------------------------------------------------

    def process_batch(
        self,
        documents: Sequence[Dict[str, Any]],
    ) -> List[PipelineResult]:
        """批量处理多篇文档。

        每条 document 至少包含 ``raw_text``，可选 ``source_file``, ``document_id``。
        """
        results: List[PipelineResult] = []
        for i, doc in enumerate(documents):
            raw_text = doc.get("raw_text", "")
            if not raw_text:
                continue
            source_file = doc.get("source_file", f"batch_{i:04d}")
            document_id = doc.get("document_id", "")
            result = self.process_document(raw_text, source_file=source_file, document_id=document_id)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------

    def process_incremental(
        self,
        raw_text: str,
        previous_result: PipelineResult,
        source_file: str = "",
    ) -> PipelineResult:
        """增量更新: 在已有结果基础上重新运行变更的模块即可合并。"""
        new_result = self.process_document(raw_text, source_file=source_file,
                                           document_id=previous_result.document_id)
        # 保留之前的模块结果（若新结果中没有该模块则沿用旧的）
        for mod_name, old_res in previous_result.module_results.items():
            if mod_name not in new_result.module_results:
                new_result.module_results[mod_name] = old_res
        return new_result

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _detect_dynasty(self, items: List[ExtractedItem]) -> str:
        for item in items:
            if item.entity_type == "dynasty":
                return item.name
        return ""

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    @staticmethod
    def result_to_json(result: PipelineResult) -> Dict[str, Any]:
        return result.to_dict()

    @staticmethod
    def result_to_csv_rows(result: PipelineResult) -> List[Dict[str, str]]:
        """将结果展平为 CSV 行（一行一个实体）。"""
        rows: List[Dict[str, str]] = []
        for item in result.all_items:
            rows.append({
                "document_id": result.document_id,
                "source_file": result.source_file,
                "entity_name": item.name,
                "entity_type": item.entity_type,
                "confidence": str(item.confidence),
                "position": str(item.position),
                "length": str(item.length),
                "rule_id": item.rule_id,
                "source_module": item.source_module,
            })
        return rows
