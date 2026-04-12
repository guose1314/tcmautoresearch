"""ResearchPipeline 与 cycle_runner 之间的桥接逻辑。"""

import logging
import time
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_ALL_PIPELINE_PHASES = ["observe", "hypothesis", "experiment", "experiment_execution", "analyze", "publish", "reflect"]


def run_pipeline_iteration(
    iteration_number: int,
    input_data: Dict[str, Any],
    run_research_session_fn: Callable[..., Dict[str, Any]],
    summarize_module_quality_fn: Callable[[str, Dict[str, Any]], Dict[str, float]],
    max_iterations: int = 5,
    governance_config: Optional[Dict[str, Any]] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """通过 7 阶段 ResearchPipeline 执行单次迭代。"""
    start_time = time.time()
    question = input_data.get("objective", "")
    if not question:
        raw = input_data.get("raw_text", "")
        question = (raw[:80] + "…") if len(raw) > 80 else raw
    question = question or "中医方剂组成规律分析"

    try:
        pipeline_config: Dict[str, Any] = deepcopy(runtime_config) if runtime_config else {}
        previous_feedback = input_data.get("previous_feedback")
        if previous_feedback:
            pipeline_config["previous_iteration_feedback"] = previous_feedback

        session_result = run_research_session_fn(
            question=question,
            config=pipeline_config,
            phase_names=list(_ALL_PIPELINE_PHASES),
        )
    except Exception as exc:
        logger.error("Pipeline iteration %d failed: %s", iteration_number, exc)
        now = datetime.now().isoformat()
        return {
            "iteration_id": f"iter_{iteration_number}",
            "iteration_number": iteration_number,
            "status": "failed",
            "error": str(exc),
            "start_time": now,
            "end_time": now,
            "duration": time.time() - start_time,
            "modules": [],
            "quality_metrics": {},
            "confidence_scores": {},
            "academic_insights": [],
            "recommendations": [],
            "metadata": {
                "max_iterations": max_iterations,
                "input_data": input_data,
                "pipeline_mode": True,
            },
            "failed_operations": [],
            "analysis_summary": {"module_count": 0, "failed_operation_count": 1},
        }

    duration = time.time() - start_time
    phase_results = session_result.get("phase_results", {})

    modules: List[Dict[str, Any]] = []
    for phase_name, phase_result in phase_results.items():
        output_data = phase_result if isinstance(phase_result, dict) else {}
        modules.append(
            {
                "module": phase_name,
                "status": "completed" if not output_data.get("error") else "failed",
                "execution_time": 0.0,
                "timestamp": datetime.now().isoformat(),
                "input_data": {},
                "output_data": output_data,
                "quality_metrics": summarize_module_quality_fn(phase_name, output_data),
            }
        )

    reflect_result = phase_results.get("reflect", {}) if isinstance(phase_results, dict) else {}
    quality_assessment = reflect_result.get("quality_assessment", {}) if isinstance(reflect_result, dict) else {}
    reflections = reflect_result.get("reflections", []) if isinstance(reflect_result, dict) else []
    academic_insights = [
        {
            "type": "quality_assessment",
            "title": f"第{iteration_number}次管道循环质量评估",
            "description": f"整体评分 {quality_assessment.get('overall_cycle_score', 0.0):.2f}",
            "confidence": quality_assessment.get("overall_cycle_score", 0.0),
            "timestamp": datetime.now().isoformat(),
        }
    ]
    for reflection in reflections[:3]:
        if isinstance(reflection, dict):
            academic_insights.append(
                {
                    "type": "reflection",
                    "title": reflection.get("topic", ""),
                    "description": reflection.get("reflection", ""),
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    improvement_plan = reflect_result.get("improvement_plan", []) if isinstance(reflect_result, dict) else []
    recommendations = [
        {
            "type": "improvement",
            "title": item,
            "description": item,
            "priority": "medium",
            "confidence": 0.80,
            "timestamp": datetime.now().isoformat(),
        }
        for item in improvement_plan[:5]
    ]

    return {
        "iteration_id": f"iter_{iteration_number}",
        "iteration_number": iteration_number,
        "status": session_result.get("status", "completed"),
        "start_time": datetime.now().isoformat(),
        "end_time": datetime.now().isoformat(),
        "duration": duration,
        "modules": modules,
        "quality_metrics": {},
        "confidence_scores": {},
        "academic_insights": academic_insights,
        "recommendations": recommendations,
        "metadata": {
            "max_iterations": max_iterations,
            "input_data": input_data,
            "pipeline_mode": True,
            "session_id": session_result.get("session_id", ""),
            "executed_phases": session_result.get("executed_phases", []),
            "last_completed_phase": "reflect" if "reflect" in phase_results else None,
        },
        "failed_operations": [],
        "analysis_summary": {
            "module_count": len(modules),
            "failed_operation_count": 0,
        },
    }
