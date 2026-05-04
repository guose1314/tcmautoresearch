"""研究模块流水线执行器。

提供模块链（DocumentPreprocessor → EntityExtractor → SemanticModeler →
ReasoningEngine → OutputGenerator）的构建、初始化、执行与清理能力。

此模块位于 ``src/research`` 层，是 observe 等阶段执行模块链的底层基础设施。
``src/cycle/cycle_runner`` 中的演示流程应通过此模块执行模块链，
而非反向让 research 层依赖 cycle 层。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Collection, Dict, List, NamedTuple, Optional

from src.research.compute_tier_router import ComputeTierRouter

logger = logging.getLogger(__name__)


# ── 质量评估 ──────────────────────────────────────────────────────────────

_MODULE_EXPECTED_KEYS: Dict[str, List[str]] = {
    "DocumentPreprocessor": ["processed_text", "metadata", "entities"],
    "EntityExtractor": ["entities", "entity_count", "metadata"],
    "SemanticModeler": ["semantic_graph", "relationships", "metadata"],
    "ReasoningEngine": ["reasoning_results", "conclusions", "evidence"],
    "OutputGenerator": ["output_data", "format", "metadata"],
}

_MODULE_CONTENT_KEYS: Dict[str, List[str]] = {
    "DocumentPreprocessor": ["processed_text"],
    "EntityExtractor": ["entities"],
    "SemanticModeler": ["semantic_graph", "relationships"],
    "ReasoningEngine": ["reasoning_results", "conclusions"],
    "OutputGenerator": ["output_data"],
}


def _compute_completeness(module_name: str, result: Dict[str, Any]) -> float:
    """字段覆盖率 = 结果中存在的预期字段数 / 预期字段总数。"""
    expected = _MODULE_EXPECTED_KEYS.get(module_name, ["status", "results", "metadata"])
    if not expected:
        return 0.0
    present = sum(1 for k in expected if result.get(k) is not None)
    return round(present / len(expected), 4)


def _compute_accuracy(module_name: str, result: Dict[str, Any]) -> float:
    """内容丰富度 — 核心字段非空且有实质内容的比例。"""
    content_keys = _MODULE_CONTENT_KEYS.get(module_name, ["results"])
    if not content_keys:
        return 0.0
    scores: List[float] = []
    for key in content_keys:
        value = result.get(key)
        if value is None:
            scores.append(0.0)
        elif isinstance(value, str):
            scores.append(min(1.0, len(value.strip()) / 100))
        elif isinstance(value, (list, tuple)):
            scores.append(min(1.0, len(value) / 5))
        elif isinstance(value, dict):
            scores.append(min(1.0, len(value) / 3))
        else:
            scores.append(0.5)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _compute_consistency(result: Dict[str, Any]) -> float:
    """内部一致性 — 检查 status 是否成功、无 error 字段、有 metadata。"""
    score = 0.0
    status = result.get("status", "")
    if status in ("completed", "success", "ok"):
        score += 0.4
    elif status:
        score += 0.2
    if not result.get("error"):
        score += 0.3
    if result.get("metadata") and isinstance(result["metadata"], dict):
        score += 0.3
    return round(min(1.0, score), 4)


def summarize_module_quality(
    module_name: str,
    result: Dict[str, Any],
    llm_engine: Any = None,
) -> Dict[str, float]:
    """从模块实际产出计算质量指标。

    三维指标 (0.0–1.0):
      - completeness: 预期字段覆盖率
      - accuracy: 核心产出内容丰富度
      - consistency: 状态/错误/元数据一致性

    当 *llm_engine* 可用且有 ``generate`` 方法时，追加 LLM 结构化评分
    ``llm_quality`` (方法学/证据强度/可重复性 的均值)。
    """
    completeness = _compute_completeness(module_name, result)
    accuracy = _compute_accuracy(module_name, result)
    consistency = _compute_consistency(result)

    metrics: Dict[str, float] = {
        "completeness": completeness,
        "accuracy": accuracy,
        "consistency": consistency,
    }

    if llm_engine is not None and hasattr(llm_engine, "generate"):
        # 动态算力分配：质量评分仅在规则层证据不足时调用 LLM
        tier_router = ComputeTierRouter()
        tier_decision = tier_router.decide(
            task_type="quality_scoring",
            evidence={
                "has_rule_result": True,  # 三维规则评分已完成
                "rule_confidence": (completeness + accuracy + consistency) / 3,
            },
        )
        if tier_decision.should_use_llm:
            llm_score = _llm_structured_quality(module_name, result, llm_engine)
            if llm_score is not None:
                metrics["llm_quality"] = llm_score

    return metrics


def _llm_structured_quality(
    module_name: str,
    result: Dict[str, Any],
    llm_engine: Any,
) -> Optional[float]:
    """调用 LLM 做方法学/证据强度/可重复性三维评分，返回均值或 None。"""
    from src.llm.llm_gateway import generate_with_gateway

    summary_parts = [f"模块: {module_name}", f"状态: {result.get('status', 'unknown')}"]
    for key in (
        "entities",
        "relationships",
        "reasoning_results",
        "conclusions",
        "processed_text",
    ):
        val = result.get(key)
        if isinstance(val, list):
            summary_parts.append(f"{key}: {len(val)} 项")
        elif isinstance(val, str) and len(val) > 20:
            summary_parts.append(f"{key}: {val[:200]}...")
        elif val is not None:
            summary_parts.append(f"{key}: {val}")
    summary = "\n".join(summary_parts)

    prompt = (
        "请评估以下中医研究模块产出的质量，从三个维度打分 (0.0–1.0)：\n"
        "1. methodological_rigor — 方法学严谨性\n"
        "2. evidence_strength — 证据强度（数据量、可信度）\n"
        "3. reproducibility — 可重复性（参数记录、流程完整度）\n\n"
        f"## 模块产出摘要\n{summary}\n\n"
        "请输出严格 JSON: "
        '{"methodological_rigor": 0.0, "evidence_strength": 0.0, "reproducibility": 0.0}'
    )
    system = "你是中医研究质量评审专家。只输出 JSON，不要其他文字。"

    try:
        gateway_result = generate_with_gateway(
            llm_engine,
            prompt,
            system,
            prompt_version="module_pipeline.structured_quality@v1",
            phase="quality",
            purpose="module_quality_scoring",
            task_type="quality_assessment",
            json_output=True,
            metadata={
                "prompt_name": "module_pipeline.structured_quality",
                "module_name": module_name,
                "response_format": "json",
            },
        )
        raw = gateway_result.text
        import json as _json

        parsed = _json.loads(raw)
        dims = [
            float(parsed.get("methodological_rigor", 0)),
            float(parsed.get("evidence_strength", 0)),
            float(parsed.get("reproducibility", 0)),
        ]
        dims = [max(0.0, min(1.0, d)) for d in dims]
        return round(sum(dims) / len(dims), 4)
    except Exception as exc:
        logger.warning("LLM 质量评分失败，仅使用规则评分: %s", exc)
        return None


# ── 模块构建与生命周期 ────────────────────────────────────────────────────


def build_real_modules() -> List[tuple[str, Any]]:
    """构建真实处理链路模块。

    .. deprecated::
        旧 5 模块链路径已被 ``ResearchPipeline`` + ``ModuleFactory`` 取代。
        默认主链不再调用此函数。
    """
    import warnings

    warnings.warn(
        "build_real_modules() 是旧 5 模块链路径，"
        "默认主链已迁移至 ResearchPipeline + ModuleFactory。",
        DeprecationWarning,
        stacklevel=2,
    )
    from src.analysis.entity_extractor import AdvancedEntityExtractor
    from src.analysis.preprocessor import DocumentPreprocessor
    from src.analysis.reasoning_engine import ReasoningEngine
    from src.analysis.semantic_graph import SemanticGraphService
    from src.generation.output_formatter import OutputGenerator

    return [
        ("DocumentPreprocessor", DocumentPreprocessor()),
        ("EntityExtractor", AdvancedEntityExtractor()),
        ("SemanticModeler", SemanticGraphService()),
        ("ReasoningEngine", ReasoningEngine()),
        ("OutputGenerator", OutputGenerator()),
    ]


def initialize_real_modules(modules: List[tuple[str, Any]]) -> None:
    """统一初始化模块，避免在每次迭代中重复初始化。"""
    for module_name, module in modules:
        logger.info("初始化真实模块: %s", module_name)
        initialized = module.initialize()
        if not initialized:
            raise RuntimeError(f"模块初始化失败: {module_name}")


def cleanup_real_modules(modules: List[tuple[str, Any]]) -> None:
    """统一清理模块资源。"""
    for module_name, module in modules:
        try:
            module.cleanup()
            logger.info("真实模块 %s 资源清理完成", module_name)
        except Exception as exc:
            logger.warning("真实模块 %s 清理异常: %s", module_name, exc)


class ModuleLifecycle(NamedTuple):
    """模块生命周期回调集合（build / initialize / cleanup）。"""

    build: Callable[[], List[tuple[str, Any]]]
    initialize: Callable[[List[tuple[str, Any]]], None]
    cleanup: Callable[[List[tuple[str, Any]]], None]


DEFAULT_MODULE_LIFECYCLE = ModuleLifecycle(
    build=build_real_modules,
    initialize=initialize_real_modules,
    cleanup=cleanup_real_modules,
)


# ── 流水线执行 ────────────────────────────────────────────────────────────


def execute_real_module_pipeline(
    input_data: Dict[str, Any],
    modules: Optional[List[tuple[str, Any]]] = None,
    manage_module_lifecycle: bool = False,
    optional_modules: Optional[Collection[str]] = None,
) -> List[Dict[str, Any]]:
    """顺序执行真实 src 模块。"""
    context = dict(input_data)
    module_results: List[Dict[str, Any]] = []
    module_chain = modules or build_real_modules()
    optional_module_names = {
        str(module_name) for module_name in (optional_modules or [])
    }

    if manage_module_lifecycle:
        initialize_real_modules(module_chain)

    try:
        for module_name, module in module_chain:
            logger.info("开始执行真实模块: %s", module_name)

            module_start_time = time.time()
            try:
                result = module.execute(context)
            except Exception as exc:
                execution_time = time.time() - module_start_time
                if module_name not in optional_module_names:
                    raise

                logger.warning(
                    "可选真实模块 %s 执行失败，继续后续链路: %s", module_name, exc
                )
                module_results.append(
                    {
                        "module": module_name,
                        "status": "failed_optional",
                        "execution_time": execution_time,
                        "timestamp": datetime.now().isoformat(),
                        "input_data": dict(context),
                        "output_data": {},
                        "quality_metrics": {},
                        "error": str(exc),
                    }
                )
                continue

            execution_time = time.time() - module_start_time
            context.update(result)

            module_results.append(
                {
                    "module": module_name,
                    "status": "completed",
                    "execution_time": execution_time,
                    "timestamp": datetime.now().isoformat(),
                    "input_data": dict(context),
                    "output_data": result,
                    "quality_metrics": summarize_module_quality(module_name, result),
                }
            )

            logger.info(
                "真实模块 %s 执行完成，耗时: %.2f秒", module_name, execution_time
            )

    finally:
        if manage_module_lifecycle:
            cleanup_real_modules(module_chain)

    return module_results
