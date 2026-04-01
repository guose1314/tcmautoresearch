# src/output/output_generator.py
"""
输出生成模块
- 将管道处理结果转化为结构化学术输出
- 对输入数据进行安全性处理（路径净化、非负数值、JSON 序列化）
- 支持可配置的实体上限、字符串长度上限和推荐条目上限
"""

import logging
import os
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

# 递归安全转换的最大深度
_MAX_JSON_DEPTH = 8


class OutputGenerator(BaseModule):
    """输出生成模块 — 结构化学术输出生成"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("output_generator", config)
        cfg = config or {}
        self.max_entities: int = int(cfg.get("max_entities", 50))
        self.max_string_length: int = int(cfg.get("max_string_length", 256))
        self.max_recommendations: int = int(cfg.get("max_recommendations", 5))

    # ------------------------------------------------------------------
    # BaseModule 抽象方法实现
    # ------------------------------------------------------------------

    def _do_initialize(self) -> bool:
        try:
            self.logger.info("输出生成模块初始化完成")
            return True
        except Exception as exc:
            self.logger.error(f"输出生成模块初始化失败: {exc}")
            return False

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        output_data = self._generate_output_format(context)
        return {"output_data": output_data}

    def _do_cleanup(self) -> bool:
        try:
            self.logger.info("输出生成模块资源清理完成")
            return True
        except Exception as exc:
            self.logger.error(f"输出生成模块资源清理失败: {exc}")
            return False

    # ------------------------------------------------------------------
    # 核心生成逻辑
    # ------------------------------------------------------------------

    def _generate_output_format(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        将管道上下文转换为结构化输出字典。

        安全处理：
        - source_file 仅保留文件名（去除目录路径）
        - 实体列表截断至 max_entities
        - statistics 中的计数值强制 >= 0
        - reasoning_results 递归转换为 JSON 安全值
        """
        # 1. 元数据 — 净化文件路径
        raw_source = context.get("source_file", "") or ""
        source = os.path.basename(raw_source)

        objective = str(context.get("objective", ""))[:self.max_string_length]

        # 2. 实体列表 — 截断至上限
        entities = list(context.get("entities", []))[: self.max_entities]

        # 3. 推理结果 — 递归 JSON 安全化
        reasoning_results = self._make_json_safe(
            context.get("reasoning_results", {})
        )

        # 4. 质量指标 — 统计计数强制非负
        stats: Dict[str, Any] = context.get("statistics") or {}
        formulas_found = max(0, _to_int(stats.get("formulas_count", 0)))
        herbs_identified = max(0, _to_int(stats.get("herbs_count", 0)))
        syndromes_recognized = max(0, _to_int(stats.get("syndromes_count", 0)))

        return {
            "metadata": {
                "source": source,
                "objective": objective,
            },
            "analysis_results": {
                "entities": entities,
                "reasoning_results": reasoning_results,
            },
            "quality_metrics": {
                "formulas_found": formulas_found,
                "herbs_identified": herbs_identified,
                "syndromes_recognized": syndromes_recognized,
            },
            "recommendations": self._build_recommendations(context),
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _make_json_safe(self, obj: Any, depth: int = 0) -> Any:
        """
        递归将对象转换为 JSON 可序列化形式。

        - 超过 _MAX_JSON_DEPTH 层时返回占位字符串
        - 非基础类型（str/int/float/bool/None）转 str 并截断
        - str 值截断至 max_string_length
        """
        if depth >= _MAX_JSON_DEPTH:
            return "<max_depth_exceeded>"

        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        if isinstance(obj, str):
            return obj[: self.max_string_length]
        if isinstance(obj, dict):
            return {k: self._make_json_safe(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._make_json_safe(item, depth + 1) for item in obj]
        # 其他不可序列化类型
        return str(obj)[: self.max_string_length]

    def _build_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """
        根据执行上下文生成改进建议列表，结果截断至 max_recommendations。
        """
        recs: List[str] = []
        entities = context.get("entities", [])
        confidence = float(context.get("confidence_score", 0.0))

        if confidence < 0.7:
            recs.append("建议提高实体识别置信度阈值，当前置信度偏低")

        if len(entities) > 50:
            recs.append("实体数量较多，建议增加过滤规则以提高准确性")

        if entities:
            recs.append("建议对抽取结果进行人工审核以确保质量")

        if not recs:
            recs.append("实体抽取结果良好，可进一步优化词典覆盖范围")

        return recs[: self.max_recommendations]


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    """安全地将任意值转换为整数，转换失败时返回 0"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
