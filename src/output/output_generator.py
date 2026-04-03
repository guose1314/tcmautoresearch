# src/output/output_generator.py
"""
研究成果输出生成模块。

将管线各阶段结果（实体、语义图、推理等）整合为结构化的 JSON 安全输出。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


class OutputGenerator(BaseModule):
    """研究成果输出生成器 — 将分析结果整合为标准化输出。"""

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("output_generator", config)
        self.max_entities: int = self.config.get("max_entities", 500)
        self.max_string_length: int = self.config.get("max_string_length", 1024)
        self.max_recommendations: int = self.config.get("max_recommendations", 10)
        self._max_json_depth: int = self.config.get("max_json_depth", 8)

    # ------------------------------------------------------------------
    # BaseModule lifecycle
    # ------------------------------------------------------------------
    def _do_initialize(self) -> bool:
        try:
            self.logger.info("OutputGenerator 初始化完成")
            return True
        except Exception as exc:
            self.logger.error("OutputGenerator 初始化失败: %s", exc)
            return False

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            output_data = self._generate_output_format(context)
            return {"output_data": output_data}
        except Exception as exc:
            self.logger.error("输出生成失败: %s", exc)
            raise

    def _do_cleanup(self) -> bool:
        try:
            self.logger.info("OutputGenerator 资源清理完成")
            return True
        except Exception as exc:
            self.logger.error("OutputGenerator 清理失败: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 核心生成逻辑
    # ------------------------------------------------------------------
    def _generate_output_format(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """将管线上下文整合为标准化输出字典。"""
        entities = context.get("entities", [])
        if len(entities) > self.max_entities:
            entities = entities[: self.max_entities]

        statistics = context.get("statistics", {})
        reasoning = context.get("reasoning_results", {})

        quality_metrics = {
            "formulas_found": max(0, int(statistics.get("formulas_count", 0))),
            "herbs_identified": max(0, int(statistics.get("herbs_count", 0))),
            "syndromes_recognized": max(0, int(statistics.get("syndromes_count", 0))),
        }

        recommendations = self._build_recommendations(context)

        output = {
            "metadata": self._build_metadata(context),
            "analysis_results": self._make_json_safe(
                {
                    "entities": entities,
                    "reasoning_results": reasoning,
                }
            ),
            "quality_metrics": quality_metrics,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
        }
        return output

    # ------------------------------------------------------------------
    def _build_metadata(self, context: Dict[str, Any]) -> Dict[str, Any]:
        source_file = context.get("source_file", "")
        safe_source = os.path.basename(source_file) if source_file else ""

        objective = context.get("objective", "")
        if len(objective) > self.max_string_length:
            objective = objective[: self.max_string_length]

        return {
            "source": safe_source,
            "objective": objective,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_recommendations(self, context: Dict[str, Any]) -> List[str]:
        recs: List[str] = []
        entities = context.get("entities", [])
        confidence = context.get("confidence_score", 0.0)

        if len(entities) > 50:
            recs.append("实体数量较多，建议进一步筛选高置信度实体。")
        if isinstance(confidence, (int, float)) and confidence < 0.7:
            recs.append("整体置信度偏低，建议增加数据源以提高准确性。")
        if not recs:
            recs.append("分析结果正常，可继续下一阶段研究。")

        return recs[: self.max_recommendations]

    # ------------------------------------------------------------------
    def _make_json_safe(self, obj: Any, _depth: int = 0) -> Any:
        """递归将对象转换为 JSON 可序列化形式。"""
        if _depth > self._max_json_depth:
            return "[DEPTH_LIMIT]"

        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, str):
            return obj[: self.max_string_length]
        if isinstance(obj, dict):
            return {
                str(k): self._make_json_safe(v, _depth + 1)
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [self._make_json_safe(item, _depth + 1) for item in obj]

        # 不可直接序列化的对象 → 字符串化
        text = repr(obj)
        return text[: self.max_string_length]
