# -*- coding: utf-8 -*-
"""统一管线协议 — 定义模块间数据传递的类型安全契约。"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineContext:
    """管线执行上下文，在各模块间传递。

    Attributes
    ----------
    request_id : str
        请求唯一标识，默认自动生成 UUID。
    user_id : str | None
        发起请求的用户标识。
    input_text : str
        用户输入的原始文本（研究问题/查询）。
    metadata : dict
        附加元信息（来源、时间戳等）。
    parameters : dict
        运行参数（模型选择、阈值等）。
    previous_results : dict
        上游模块产出的中间结果。
    quality_requirements : dict
        质量要求（最低置信度、覆盖率等）。
    """

    input_text: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    previous_results: Dict[str, Any] = field(default_factory=dict)
    quality_requirements: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转为普通字典，便于与现有 Dict[str, Any] 接口互操作。"""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "input_text": self.input_text,
            "metadata": self.metadata,
            "parameters": self.parameters,
            "previous_results": self.previous_results,
            "quality_requirements": self.quality_requirements,
        }


@dataclass
class ModuleResult:
    """模块执行结果的标准化封装。

    Attributes
    ----------
    success : bool
        模块是否执行成功。
    data : dict
        模块产出的核心数据。
    quality_metrics : dict
        质量指标（置信度、覆盖率等）。
    execution_time_ms : float
        执行耗时（毫秒）。
    errors : list[str]
        执行过程中的错误信息。
    warnings : list[str]
        执行过程中的警告信息。
    """

    success: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转为普通字典。"""
        return {
            "success": self.success,
            "data": self.data,
            "quality_metrics": self.quality_metrics,
            "execution_time_ms": self.execution_time_ms,
            "errors": self.errors,
            "warnings": self.warnings,
        }
