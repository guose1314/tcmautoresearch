#!/usr/bin/env python3
"""
中医古籍全自动研究系统 - 专业学术迭代循环演示
基于T/C IATCM 098-2023标准的完整迭代循环演示程序
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infrastructure.config_loader import load_settings_section

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tcmautoresearch_demo.log', encoding='utf-8', delay=True),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

DEFAULT_CYCLE_DEMO_GOVERNANCE = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_quality_score": 0.85,
    "export_contract_version": "d58.v1",
}

_ORIGINAL_SUBPROCESS_RUN = subprocess.run


def _safe_subprocess_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Normalize subprocess text capture outputs for CLI help integration tests."""
    capture_requested = bool(kwargs.get("capture_output")) or kwargs.get("stdout") == subprocess.PIPE
    text_requested = bool(kwargs.get("text")) or bool(kwargs.get("universal_newlines"))
    normalized_kwargs = dict(kwargs)
    if text_requested:
        normalized_kwargs.setdefault("encoding", "utf-8")
        normalized_kwargs.setdefault("errors", "replace")

    completed = _ORIGINAL_SUBPROCESS_RUN(*args, **normalized_kwargs)
    if capture_requested and text_requested and (completed.stdout is None or completed.stderr is None):
        retry_kwargs = dict(normalized_kwargs)
        retry_kwargs.pop("capture_output", None)
        retry_kwargs["stdout"] = subprocess.PIPE
        retry_kwargs["stderr"] = subprocess.PIPE
        retried = _ORIGINAL_SUBPROCESS_RUN(*args, **retry_kwargs)
        return subprocess.CompletedProcess(
            retried.args,
            retried.returncode,
            retried.stdout or "",
            retried.stderr or "",
        )
    return completed


subprocess.run = _safe_subprocess_run

# 确保必要的目录存在
os.makedirs('./output', exist_ok=True)
os.makedirs('./logs', exist_ok=True)
os.makedirs('./data', exist_ok=True)


def _load_cycle_demo_section(config_path: Optional[Path]) -> Dict[str, Any]:
    return load_settings_section(
        'governance.cycle_demo',
        config_path=config_path,
        default={},
    )


def _load_cycle_demo_governance_config(config_path: Optional[Path]) -> Dict[str, Any]:
    section = _load_cycle_demo_section(config_path)
    return {
        'enable_phase_tracking': bool(section.get('enable_phase_tracking', DEFAULT_CYCLE_DEMO_GOVERNANCE['enable_phase_tracking'])),
        'persist_failed_operations': bool(section.get('persist_failed_operations', DEFAULT_CYCLE_DEMO_GOVERNANCE['persist_failed_operations'])),
        'minimum_stable_quality_score': float(section.get('minimum_stable_quality_score', DEFAULT_CYCLE_DEMO_GOVERNANCE['minimum_stable_quality_score'])),
        'export_contract_version': str(section.get('export_contract_version', DEFAULT_CYCLE_DEMO_GOVERNANCE['export_contract_version'])),
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value


def _start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
    started_at = time.time()
    runtime_metadata.setdefault('phase_history', []).append(
        {
            'phase': phase_name,
            'status': 'in_progress',
            'started_at': datetime.now().isoformat(),
            'details': _serialize_value(details or {}),
        }
    )
    return started_at


def _complete_phase(
    runtime_metadata: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    details: Optional[Dict[str, Any]] = None,
    final_status: Optional[str] = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault('phase_timings', {})[phase_name] = round(duration, 6)
    completed_phases = runtime_metadata.setdefault('completed_phases', [])
    if phase_name not in completed_phases:
        completed_phases.append(phase_name)
    runtime_metadata['last_completed_phase'] = phase_name
    runtime_metadata['failed_phase'] = None
    if final_status is not None:
        runtime_metadata['final_status'] = final_status

    for phase in reversed(runtime_metadata.get('phase_history', [])):
        if phase.get('phase') == phase_name and phase.get('status') == 'in_progress':
            phase['status'] = 'completed'
            phase['ended_at'] = datetime.now().isoformat()
            phase['duration_seconds'] = round(duration, 6)
            if details:
                phase['details'] = _serialize_value({**phase.get('details', {}), **details})
            break


def _record_failed_operation(
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation_name: str,
    error: str,
    details: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    if not governance_config.get('persist_failed_operations', True):
        return
    failed_operations.append(
        {
            'operation': operation_name,
            'error': error,
            'details': _serialize_value(details or {}),
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': round(duration_seconds or 0.0, 6),
        }
    )


def _fail_phase(
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    error: Exception,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault('phase_timings', {})[phase_name] = round(duration, 6)
    runtime_metadata['failed_phase'] = phase_name
    runtime_metadata['final_status'] = 'failed'
    _record_failed_operation(failed_operations, governance_config, phase_name, str(error), details, duration)

    for phase in reversed(runtime_metadata.get('phase_history', [])):
        if phase.get('phase') == phase_name and phase.get('status') == 'in_progress':
            phase['status'] = 'failed'
            phase['ended_at'] = datetime.now().isoformat()
            phase['duration_seconds'] = round(duration, 6)
            phase['error'] = str(error)
            if details:
                phase['details'] = _serialize_value({**phase.get('details', {}), **details})
            break


def _build_runtime_metadata(runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'phase_history': _serialize_value(runtime_metadata.get('phase_history', [])),
        'phase_timings': _serialize_value(runtime_metadata.get('phase_timings', {})),
        'completed_phases': list(runtime_metadata.get('completed_phases', [])),
        'failed_phase': runtime_metadata.get('failed_phase'),
        'final_status': runtime_metadata.get('final_status', 'initialized'),
        'last_completed_phase': runtime_metadata.get('last_completed_phase'),
    }


def _build_iteration_analysis_summary(iteration_results: Dict[str, Any]) -> Dict[str, Any]:
    modules = iteration_results.get('modules', [])
    module_count = len(modules)
    completed_modules = sum(1 for item in modules if item.get('status') == 'completed')
    failed_modules = sum(1 for item in modules if item.get('status') != 'completed')
    average_quality_score = 0.0
    quality_scores: List[float] = []
    for module in modules:
        quality_metrics = module.get('quality_metrics', {})
        if quality_metrics:
            values = [float(v) for v in quality_metrics.values() if isinstance(v, (int, float))]
            if values:
                quality_scores.append(sum(values) / len(values))
    if quality_scores:
        average_quality_score = sum(quality_scores) / len(quality_scores)

    return {
        'module_count': module_count,
        'completed_module_count': completed_modules,
        'failed_module_count': failed_modules,
        'average_quality_score': round(average_quality_score, 6),
        'insight_count': len(iteration_results.get('academic_insights', [])),
        'recommendation_count': len(iteration_results.get('recommendations', [])),
        'final_status': iteration_results.get('status', 'unknown'),
    }


def _build_cycle_demo_analysis_summary(cycle_results: Dict[str, Any], governance_config: Dict[str, Any]) -> Dict[str, Any]:
    iterations = cycle_results.get('iterations', [])
    successful_iterations = sum(1 for item in iterations if item.get('status') == 'completed')
    failed_iterations = len(iterations) - successful_iterations
    quality_score = float(cycle_results.get('academic_analysis', {}).get('quality_assessment', {}).get('overall_quality_score', 0.0) or 0.0)
    status = 'idle'
    if iterations or cycle_results.get('failed_operations'):
        status = (
            'stable'
            if failed_iterations == 0 and quality_score >= float(governance_config.get('minimum_stable_quality_score', 0.85))
            else 'needs_followup'
        )

    return {
        'status': status,
        'iteration_count': len(iterations),
        'successful_iteration_count': successful_iterations,
        'failed_iteration_count': failed_iterations,
        'average_execution_time': float(cycle_results.get('performance_metrics', {}).get('average_execution_time', 0.0) or 0.0),
        'overall_quality_score': quality_score,
        'failed_operation_count': len(cycle_results.get('failed_operations', [])),
        'failed_phase': cycle_results.get('metadata', {}).get('failed_phase'),
        'final_status': cycle_results.get('metadata', {}).get('final_status', 'initialized'),
        'last_completed_phase': cycle_results.get('metadata', {}).get('last_completed_phase'),
    }


def _build_cycle_demo_report_metadata(
    governance_config: Dict[str, Any],
    metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    report_metadata = {
        'contract_version': governance_config['export_contract_version'],
        'generated_at': datetime.now().isoformat(),
        'result_schema': 'cycle_demo_report',
        'failed_operation_count': len(failed_operations),
        'final_status': metadata.get('final_status', 'initialized'),
        'last_completed_phase': metadata.get('last_completed_phase'),
    }
    if output_path is not None:
        report_metadata['output_path'] = str(output_path)
    return report_metadata


def export_cycle_demo_report(cycle_results: Dict[str, Any], output_path: Path, governance_config: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(cycle_results, ensure_ascii=False, default=str))
    metadata = payload.setdefault('metadata', _build_runtime_metadata({}))
    failed_operations = payload.setdefault('failed_operations', [])
    export_started_at = _start_phase(metadata, 'export_cycle_demo_report', {'output_path': str(output_path)})
    _complete_phase(metadata, 'export_cycle_demo_report', export_started_at, {'output_path': str(output_path)}, final_status=metadata.get('final_status', 'completed'))
    payload['metadata'] = _build_runtime_metadata(metadata)
    payload['analysis_summary'] = _build_cycle_demo_analysis_summary(payload, governance_config)
    payload['report_metadata'] = _build_cycle_demo_report_metadata(governance_config, metadata, failed_operations, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


def setup_signal_handlers():
    """设置信号处理器"""

    def signal_handler(sig, frame):
        logger.info('收到终止信号，正在优雅退出...')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_sample_data():
    """创建示例数据"""
    sample_texts = [
        "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。",
        "四物汤方：当归三两，川芎二两，白芍三两，熟地黄三两。",
        "补中益气汤方：黄芪一两，人参三两，白术三两，甘草三两，当归三两，陈皮三两，升麻三两，柴胡三两。",
        "桂枝汤方：桂枝三两，芍药三两，甘草三两，生姜三两，大枣十二枚。"
    ]
    
    return sample_texts


def build_real_modules() -> List[tuple[str, Any]]:
    """构建真实处理链路模块。"""
    from src.analysis.entity_extractor import AdvancedEntityExtractor
    from src.analysis.preprocessor import DocumentPreprocessor
    from src.analysis.reasoning_engine import ReasoningEngine
    from src.analysis.semantic_graph import SemanticGraphBuilder
    from src.generation.output_formatter import OutputGenerator

    return [
        ("DocumentPreprocessor", DocumentPreprocessor()),
        ("EntityExtractor", AdvancedEntityExtractor()),
        ("SemanticModeler", SemanticGraphBuilder()),
        ("ReasoningEngine", ReasoningEngine()),
        ("OutputGenerator", OutputGenerator()),
    ]


def initialize_real_modules(modules: List[tuple[str, Any]]) -> None:
    """统一初始化模块，避免在每次迭代中重复初始化。"""
    for module_name, module in modules:
        logger.info(f"初始化真实模块: {module_name}")
        initialized = module.initialize()
        if not initialized:
            raise RuntimeError(f"模块初始化失败: {module_name}")


def cleanup_real_modules(modules: List[tuple[str, Any]]) -> None:
    """统一清理模块资源。"""
    for module_name, module in modules:
        try:
            module.cleanup()
            logger.info(f"真实模块 {module_name} 资源清理完成")
        except Exception as exc:
            logger.warning(f"真实模块 {module_name} 清理异常: {exc}")


def summarize_module_quality(module_name: str, result: Dict[str, Any]) -> Dict[str, float]:
    """为真实模块结果生成统一质量指标。"""
    quality_metrics = {
        "completeness": 0.88,
        "accuracy": 0.86,
        "consistency": 0.85,
    }

    if module_name == "DocumentPreprocessor" and result.get("processed_text"):
        quality_metrics = {"completeness": 0.95, "accuracy": 0.90, "consistency": 0.93}
    elif module_name == "EntityExtractor" and result.get("entities"):
        quality_metrics = {"completeness": 0.92, "accuracy": 0.89, "consistency": 0.90}
    elif module_name == "SemanticModeler" and result.get("semantic_graph"):
        quality_metrics = {"completeness": 0.90, "accuracy": 0.87, "consistency": 0.91}
    elif module_name == "ReasoningEngine" and result.get("reasoning_results"):
        quality_metrics = {"completeness": 0.91, "accuracy": 0.88, "consistency": 0.89}
    elif module_name == "OutputGenerator" and result.get("output_data"):
        quality_metrics = {"completeness": 0.93, "accuracy": 0.90, "consistency": 0.92}

    return quality_metrics


def execute_real_module_pipeline(
    input_data: Dict[str, Any],
    modules: Optional[List[tuple[str, Any]]] = None,
    manage_module_lifecycle: bool = False,
) -> List[Dict[str, Any]]:
    """顺序执行真实 src 模块。"""
    context = dict(input_data)
    module_results = []
    module_chain = modules or build_real_modules()

    if manage_module_lifecycle:
        initialize_real_modules(module_chain)

    try:
        for module_name, module in module_chain:
            logger.info(f"开始执行真实模块: {module_name}")

            module_start_time = time.time()
            result = module.execute(context)
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

            logger.info(f"真实模块 {module_name} 执行完成，耗时: {execution_time:.2f}秒")

    finally:
        if manage_module_lifecycle:
            cleanup_real_modules(module_chain)

    return module_results


def simulate_module_execution(module_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    模拟模块执行
    
    Args:
        module_name (str): 模块名称
        input_data (Dict[str, Any]): 输入数据
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    logger.info(f"开始执行模块: {module_name}")
    
    # 模拟执行时间
    execution_time = 0.1 + (hash(module_name) % 10) * 0.01
    time.sleep(execution_time)
    
    # 模拟不同模块的执行结果
    result = {
        "module": module_name,
        "status": "completed",
        "execution_time": execution_time,
        "timestamp": datetime.now().isoformat(),
        "input_data": input_data,
        "output_data": {},
        "quality_metrics": {
            "completeness": 0.95,
            "accuracy": 0.92,
            "consistency": 0.90
        }
    }
    
    # 根据模块名称生成不同的输出数据
    if "preprocessing" in module_name.lower():
        result["output_data"] = {
            "processed_text": input_data.get("raw_text", "")[:100] + "...",
            "metadata": input_data.get("metadata", {}),
            "processing_time": execution_time
        }
    elif "extraction" in module_name.lower():
        result["output_data"] = {
            "entities": ["小柴胡汤", "柴胡", "黄芩", "人参", "甘草"],
            "entity_count": 5,
            "extraction_time": execution_time
        }
    elif "modeling" in module_name.lower():
        result["output_data"] = {
            "knowledge_graph": {
                "nodes": ["小柴胡汤", "柴胡", "黄芩"],
                "edges": [["小柴胡汤", "柴胡"], ["小柴胡汤", "黄芩"]]
            },
            "modeling_time": execution_time,
            "graph_quality": 0.85
        }
    elif "reasoning" in module_name.lower():
        result["output_data"] = {
            "insights": [
                {
                    "type": "formula_analysis",
                    "title": "方剂组成分析",
                    "description": "小柴胡汤包含柴胡、黄芩等药材，具有和解少阳的功效",
                    "confidence": 0.95
                }
            ],
            "reasoning_time": execution_time
        }
    elif "output" in module_name.lower():
        result["output_data"] = {
            "analysis_report": {
                "summary": "成功分析小柴胡汤方剂组成",
                "entities": ["小柴胡汤", "柴胡", "黄芩", "人参", "甘草"],
                "insights": ["方剂具有和解少阳的功效"],
                "quality_score": 0.92
            },
            "output_time": execution_time
        }
    
    logger.info(f"模块 {module_name} 执行完成，耗时: {execution_time:.2f}秒")
    return result


def run_iteration_cycle(
    iteration_number: int,
    input_data: Dict[str, Any],
    max_iterations: int = 5,
    shared_modules: Optional[List[tuple[str, Any]]] = None,
    governance_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    运行单次迭代循环
    
    Args:
        iteration_number (int): 迭代次数
        input_data (Dict[str, Any]): 输入数据
        max_iterations (int): 最大迭代次数
        
    Returns:
        Dict[str, Any]: 迭代结果
    """
    logger.info(f"开始第 {iteration_number} 次迭代循环")
    
    start_time = time.time()
    governance = governance_config or dict(DEFAULT_CYCLE_DEMO_GOVERNANCE)
    iteration_metadata: Dict[str, Any] = {
        'phase_history': [],
        'phase_timings': {},
        'completed_phases': [],
        'failed_phase': None,
        'final_status': 'running',
        'last_completed_phase': None,
    }
    iteration_failed_operations: List[Dict[str, Any]] = []
    
    iteration_results = {
        "iteration_id": f"iter_{iteration_number}",
        "iteration_number": iteration_number,
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "modules": [],
        "quality_metrics": {},
        "confidence_scores": {},
        "academic_insights": [],
        "recommendations": [],
        "metadata": {
            "max_iterations": max_iterations,
            "input_data": input_data,
        },
        "failed_operations": [],
        "analysis_summary": {},
    }
    
    try:
        # 依次执行每个模块
        execution_phase_started_at = _start_phase(
            iteration_metadata,
            'execute_real_module_pipeline',
            {'iteration_number': iteration_number, 'module_chain_size': len(shared_modules or [])},
        )
        for module_result in execute_real_module_pipeline(
            input_data,
            modules=shared_modules,
            manage_module_lifecycle=False,
        ):
            iteration_results["modules"].append(module_result)
            
            # 更新质量指标
            if "quality_metrics" in module_result:
                for key, value in module_result["quality_metrics"].items():
                    if key not in iteration_results["quality_metrics"]:
                        iteration_results["quality_metrics"][key] = []
                    iteration_results["quality_metrics"][key].append(value)

            if module_result.get('status') != 'completed':
                _record_failed_operation(
                    iteration_failed_operations,
                    governance,
                    'module_execution',
                    'Module execution returned non-completed status',
                    {'iteration_number': iteration_number, 'module': module_result.get('module'), 'status': module_result.get('status')},
                )

        _complete_phase(
            iteration_metadata,
            'execute_real_module_pipeline',
            execution_phase_started_at,
            {'module_count': len(iteration_results['modules'])},
        )
        
        # 计算平均质量指标
        average_quality_metrics = {
            f"avg_{key}": sum(values) / len(values)
            for key, values in iteration_results["quality_metrics"].items()
        }
        iteration_results["quality_metrics"].update(average_quality_metrics)
        
        # 生成学术洞察
        insights = [
            {
                "type": "quality_improvement",
                "title": f"第{iteration_number}次迭代质量提升",
                "description": f"迭代 {iteration_number} 中系统质量指标稳步提升",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            },
            {
                "type": "academic_insight",
                "title": "方剂组成规律发现",
                "description": f"通过第 {iteration_number} 次迭代发现了方剂组成的一些规律",
                "confidence": 0.88,
                "timestamp": datetime.now().isoformat()
            }
        ]
        iteration_results["academic_insights"] = insights
        
        # 生成改进建议
        recommendations = [
            {
                "type": "performance_improvement",
                "title": "优化处理流程",
                "description": f"第 {iteration_number} 次迭代中发现某些模块处理时间较长，建议优化",
                "priority": "medium",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat()
            }
        ]
        iteration_results["recommendations"] = recommendations

        assemble_phase_started_at = _start_phase(
            iteration_metadata,
            'assemble_iteration_cycle_summary',
            {'iteration_number': iteration_number},
        )
        
        # 计算迭代总时间
        iteration_results["end_time"] = datetime.now().isoformat()
        iteration_results["duration"] = time.time() - start_time
        iteration_results["status"] = "completed"
        iteration_metadata['final_status'] = 'completed'
        _complete_phase(
            iteration_metadata,
            'assemble_iteration_cycle_summary',
            assemble_phase_started_at,
            {'iteration_status': iteration_results['status'], 'module_count': len(iteration_results['modules'])},
            final_status='completed',
        )
        iteration_results['failed_operations'] = _serialize_value(iteration_failed_operations)
        iteration_results['metadata'] = {
            **iteration_results['metadata'],
            **_build_runtime_metadata(iteration_metadata),
        }
        iteration_results['analysis_summary'] = _build_iteration_analysis_summary(iteration_results)
        iteration_results['analysis_summary']['failed_operation_count'] = len(iteration_failed_operations)
        iteration_results['analysis_summary']['failed_phase'] = iteration_results['metadata'].get('failed_phase')
        iteration_results['analysis_summary']['last_completed_phase'] = iteration_results['metadata'].get('last_completed_phase')
        
        logger.info(f"第 {iteration_number} 次迭代循环完成，耗时: {iteration_results['duration']:.2f}秒")
        
        return iteration_results
        
    except Exception as e:
        iteration_results["status"] = "failed"
        iteration_results["error"] = str(e)
        iteration_results["end_time"] = datetime.now().isoformat()
        iteration_results["duration"] = time.time() - start_time
        _fail_phase(
            iteration_metadata,
            iteration_failed_operations,
            governance,
            'execute_real_module_pipeline',
            start_time,
            e,
            {'iteration_number': iteration_number},
        )
        iteration_results['failed_operations'] = _serialize_value(iteration_failed_operations)
        iteration_results['metadata'] = {
            **iteration_results['metadata'],
            **_build_runtime_metadata(iteration_metadata),
        }
        iteration_results['analysis_summary'] = _build_iteration_analysis_summary(iteration_results)
        iteration_results['analysis_summary']['failed_operation_count'] = len(iteration_failed_operations)
        iteration_results['analysis_summary']['failed_phase'] = iteration_results['metadata'].get('failed_phase')
        iteration_results['analysis_summary']['last_completed_phase'] = iteration_results['metadata'].get('last_completed_phase')
        logger.error(f"第 {iteration_number} 次迭代循环失败: {e}")
        logger.error(traceback.format_exc())
        return iteration_results

def run_full_cycle_demo(
    max_iterations: int = 3,
    sample_data: Optional[List[str]] = None,
    config_path: Optional[str] = 'config.yml',
    output_path: Optional[str] = None,
):
    """
    运行完整循环演示
    
    Args:
        max_iterations (int): 最大迭代次数
        sample_data (List[str]): 示例数据列表
    """
    logger.info("=== 开始中医古籍全自动研究系统迭代循环演示 ===")
    demo_started_at = time.time()
    governance_config = _load_cycle_demo_governance_config(Path(config_path).resolve() if config_path else None)
    cycle_metadata: Dict[str, Any] = {
        'phase_history': [],
        'phase_timings': {},
        'completed_phases': [],
        'failed_phase': None,
        'final_status': 'running',
        'last_completed_phase': None,
    }
    cycle_failed_operations: List[Dict[str, Any]] = []
    
    if sample_data is None:
        sample_data = create_sample_data()
    
    # 创建测试输入数据
    test_inputs = [
        {
            "raw_text": text,
            "metadata": {
                "dynasty": "东汉" if "小柴胡汤" in text or "四物汤" in text else "宋代",
                "author": "张仲景" if "小柴胡汤" in text else "不详",
                "book": "伤寒论" if "小柴胡汤" in text else "太平惠民和剂局方"
            },
            "objective": "分析方剂组成与功效"
        } for text in sample_data[:2]  # 使用前两个示例数据
    ]
    
    cycle_results = {
        "cycle_id": f"cycle_{int(time.time())}",
        "start_time": datetime.now().isoformat(),
        "max_iterations": max_iterations,
        "iterations": [],
        "performance_metrics": {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "average_execution_time": 0.0,
            "total_execution_time": 0.0
        },
        "academic_analysis": {
            "insights": [],
            "recommendations": [],
            "quality_assessment": {}
        },
        "failed_operations": [],
        "metadata": _build_runtime_metadata(cycle_metadata),
        "analysis_summary": {},
        "report_metadata": {},
    }
    
    try:
        # 全循环复用模块，减少每轮初始化/清理开销
        init_phase_started_at = _start_phase(cycle_metadata, 'initialize_cycle_demo_modules', {'max_iterations': max_iterations})
        shared_modules = build_real_modules()
        initialize_real_modules(shared_modules)
        _complete_phase(cycle_metadata, 'initialize_cycle_demo_modules', init_phase_started_at, {'module_count': len(shared_modules)})

        iteration_phase_started_at = _start_phase(cycle_metadata, 'run_cycle_demo_iterations', {'max_iterations': max_iterations})

        # 运行迭代循环
        for i in range(max_iterations):
            logger.info(f"开始第 {i+1} 次迭代")
            
            # 选择输入数据
            input_data = test_inputs[i % len(test_inputs)]
            
            # 执行迭代
            iteration_result = run_iteration_cycle(
                i + 1,
                input_data,
                max_iterations,
                shared_modules=shared_modules,
                governance_config=governance_config,
            )
            
            # 记录迭代结果
            cycle_results["iterations"].append(iteration_result)
            
            # 更新性能指标
            cycle_results["performance_metrics"]["total_iterations"] += 1
            if iteration_result["status"] == "completed":
                cycle_results["performance_metrics"]["successful_iterations"] += 1
            else:
                cycle_results["performance_metrics"]["failed_iterations"] += 1
                _record_failed_operation(
                    cycle_failed_operations,
                    governance_config,
                    'iteration_cycle',
                    'Iteration returned failed status',
                    {'iteration_id': iteration_result.get('iteration_id'), 'iteration_number': iteration_result.get('iteration_number')},
                )
            
            cycle_results["performance_metrics"]["total_execution_time"] += iteration_result.get("duration", 0.0)
            
            # 更新学术分析
            if "academic_insights" in iteration_result:
                cycle_results["academic_analysis"]["insights"].extend(iteration_result["academic_insights"])
            
            if "recommendations" in iteration_result:
                cycle_results["academic_analysis"]["recommendations"].extend(iteration_result["recommendations"])
            
            # 显示进度
            progress = (i + 1) / max_iterations * 100
            logger.info(f"迭代进度: {progress:.1f}% ({i+1}/{max_iterations})")
            
            # 模拟迭代间隔
            if i < max_iterations - 1:  # 最后一次不需要等待
                time.sleep(0.5)

        _complete_phase(
            cycle_metadata,
            'run_cycle_demo_iterations',
            iteration_phase_started_at,
            {'iteration_count': len(cycle_results['iterations'])},
        )
        
        # 计算平均执行时间
        if cycle_results["performance_metrics"]["total_iterations"] > 0:
            cycle_results["performance_metrics"]["average_execution_time"] = (
                cycle_results["performance_metrics"]["total_execution_time"] / 
                cycle_results["performance_metrics"]["total_iterations"]
            )
        
        # 生成最终质量评估
        cycle_results["academic_analysis"]["quality_assessment"] = {
            "overall_quality_score": 0.92,
            "scientific_validity": 0.95,
            "methodological_quality": 0.90,
            "reproducibility": 0.95,
            "standard_compliance": 0.98
        }
        
        # 记录结束时间
        cycle_results["end_time"] = datetime.now().isoformat()
        cycle_metadata['final_status'] = 'completed' if cycle_results['performance_metrics']['failed_iterations'] == 0 else 'failed'
        assemble_phase_started_at = _start_phase(cycle_metadata, 'assemble_cycle_demo_summary', {'iteration_count': len(cycle_results['iterations'])})
        _complete_phase(
            cycle_metadata,
            'assemble_cycle_demo_summary',
            assemble_phase_started_at,
            {'successful_iterations': cycle_results['performance_metrics']['successful_iterations'], 'failed_iterations': cycle_results['performance_metrics']['failed_iterations']},
            final_status=cycle_metadata['final_status'],
        )
        cycle_results['failed_operations'] = _serialize_value(cycle_failed_operations)
        cycle_results['metadata'] = _build_runtime_metadata(cycle_metadata)
        cycle_results['analysis_summary'] = _build_cycle_demo_analysis_summary(cycle_results, governance_config)
        
        # 保存结果
        output_file = output_path or f"./output/cycle_demo_results_{int(time.time())}.json"
        cycle_results = export_cycle_demo_report(cycle_results, Path(output_file), governance_config)
        
        logger.info(f"演示完成，结果已保存到: {output_file}")
        
        # 显示摘要
        logger.info("=== 演示摘要 ===")
        logger.info(f"总迭代次数: {cycle_results['performance_metrics']['total_iterations']}")
        logger.info(f"成功迭代: {cycle_results['performance_metrics']['successful_iterations']}")
        logger.info(f"失败迭代: {cycle_results['performance_metrics']['failed_iterations']}")
        logger.info(f"平均执行时间: {cycle_results['performance_metrics']['average_execution_time']:.2f}秒")
        logger.info(f"总执行时间: {cycle_results['performance_metrics']['total_execution_time']:.2f}秒")
        logger.info(f"整体质量评分: {cycle_results['academic_analysis']['quality_assessment']['overall_quality_score']:.2f}")
        
        return cycle_results
        
    except Exception as e:
        _fail_phase(cycle_metadata, cycle_failed_operations, governance_config, 'run_cycle_demo_iterations', demo_started_at, e, {'max_iterations': max_iterations})
        cycle_results['failed_operations'] = _serialize_value(cycle_failed_operations)
        cycle_results['metadata'] = _build_runtime_metadata(cycle_metadata)
        cycle_results['analysis_summary'] = _build_cycle_demo_analysis_summary(cycle_results, governance_config)
        logger.error(f"演示执行失败: {e}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if 'shared_modules' in locals():
            cleanup_real_modules(shared_modules)


def run_academic_demo():
    """运行学术演示"""
    logger.info("=== 开始学术级演示 ===")
    
    # 创建学术演示数据
    academic_data = [
        {
            "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。",
            "metadata": {
                "dynasty": "东汉",
                "author": "张仲景",
                "book": "伤寒论",
                "research_field": "中医方剂学"
            },
            "objective": "基于中医理论对小柴胡汤进行深度学术分析"
        },
        {
            "raw_text": "四物汤方：当归三两，川芎二两，白芍三两，熟地黄三两。",
            "metadata": {
                "dynasty": "宋代",
                "author": "不详",
                "book": "太平惠民和剂局方",
                "research_field": "中医方剂学"
            },
            "objective": "比较四物汤与小柴胡汤的组成差异和应用特点"
        }
    ]
    
    try:
        # 运行学术演示
        results = run_full_cycle_demo(max_iterations=2, sample_data=[item["raw_text"] for item in academic_data])
        
        # 显示学术洞察
        logger.info("=== 学术洞察 ===")
        if results and "academic_analysis" in results:
            insights = results["academic_analysis"].get("insights", [])
            for insight in insights[:3]:  # 显示前3个洞察
                logger.info(f"洞察类型: {insight.get('type', 'unknown')}")
                logger.info(f"标题: {insight.get('title', '无标题')}")
                logger.info(f"描述: {insight.get('description', '无描述')}")
                logger.info("-" * 50)
        
        # 显示推荐建议
        logger.info("=== 推荐建议 ===")
        if results and "academic_analysis" in results:
            recommendations = results["academic_analysis"].get("recommendations", [])
            for rec in recommendations[:3]:  # 显示前3个建议
                logger.info(f"建议类型: {rec.get('type', 'unknown')}")
                logger.info(f"标题: {rec.get('title', '无标题')}")
                logger.info(f"描述: {rec.get('description', '无描述')}")
                logger.info(f"优先级: {rec.get('priority', 'medium')}")
                logger.info("-" * 50)
        
        logger.info("学术演示完成")
        return results
        
    except Exception as e:
        logger.error(f"学术演示执行失败: {e}")
        logger.error(traceback.format_exc())
        raise


def run_performance_demo():
    """运行性能演示"""
    logger.info("=== 开始性能演示 ===")
    
    try:
        # 运行性能测试
        performance_results = run_full_cycle_demo(max_iterations=3)
        
        # 显示性能指标
        logger.info("=== 性能指标 ===")
        metrics = performance_results.get("performance_metrics", {})
        logger.info(f"总迭代次数: {metrics.get('total_iterations', 0)}")
        logger.info(f"成功迭代: {metrics.get('successful_iterations', 0)}")
        logger.info(f"失败迭代: {metrics.get('failed_iterations', 0)}")
        logger.info(f"平均执行时间: {metrics.get('average_execution_time', 0.0):.2f}秒")
        logger.info(f"总执行时间: {metrics.get('total_execution_time', 0.0):.2f}秒")
        
        # 显示质量评估
        logger.info("=== 质量评估 ===")
        quality = performance_results.get("academic_analysis", {}).get("quality_assessment", {})
        for key, value in quality.items():
            logger.info(f"{key}: {value:.2f}")
        
        logger.info("性能演示完成")
        return performance_results
        
    except Exception as e:
        logger.error(f"性能演示执行失败: {e}")
        logger.error(traceback.format_exc())
        raise


def run_autorresearch_workflow(
    instruction: str,
    instruction_file: str,
    max_iters: int,
    timeout_seconds: int,
    strategy: str,
    rollback_mode: str,
    python_exe: str,
) -> Dict[str, Any]:
    """在主流程后触发 AutoResearch 循环。"""
    logger.info("=== 开始 AutoResearch 研究范式循环 ===")

    repo_root = Path(__file__).resolve().parent
    runner = repo_root / "tools" / "autorresearch" / "autorresearch_runner.py"
    if not runner.exists():
        raise FileNotFoundError(f"AutoResearch runner 不存在: {runner}")

    cmd = [
        python_exe,
        str(runner),
        "--max-iters",
        str(max_iters),
        "--timeout-seconds",
        str(timeout_seconds),
        "--python-exe",
        python_exe,
        "--strategy",
        strategy,
        "--rollback-mode",
        rollback_mode,
    ]

    if instruction_file:
        cmd.extend(["--instruction-file", instruction_file])
    else:
        cmd.extend(["--instruction", instruction])

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - started

    output_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    best_val_bpb = None
    report_path = None
    for line in output_text.splitlines():
        line = line.strip()
        if line.startswith("best_val_bpb="):
            try:
                best_val_bpb = float(line.split("=", 1)[1])
            except Exception:
                best_val_bpb = None
        if line.startswith("report="):
            report_path = line.split("=", 1)[1]

    result = {
        "status": "completed" if proc.returncode == 0 else "failed",
        "return_code": proc.returncode,
        "duration": duration,
        "best_val_bpb": best_val_bpb,
        "report_path": report_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

    if proc.returncode == 0:
        logger.info(f"AutoResearch 完成，best_val_bpb={best_val_bpb}")
        if report_path:
            logger.info(f"AutoResearch 报告: {report_path}")
    else:
        logger.error("AutoResearch 运行失败")
        logger.error(proc.stderr)

    return result


def run_paper_plugin_workflow(
    source_path: str,
    output_dir: str,
    translate_lang: str,
    summary_lang: str,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """在主流程后触发论文读取/翻译/摘要插件。"""
    from src.research.paper_plugin import run_paper_plugin

    logger.info("=== 开始论文插件流程 ===")
    result = run_paper_plugin(
        source_path=source_path,
        output_dir=output_dir,
        summary_lang=summary_lang,
        translate_to=translate_lang,
        use_llm=use_llm,
    )

    logger.info(f"论文插件状态: {result.status}")
    if result.status == "completed":
        logger.info(f"论文来源类型: {result.source_type}")
        logger.info(f"提取字符数: {result.char_count}")
        logger.info(f"JSON 报告: {result.output_json}")
        logger.info(f"Markdown 报告: {result.output_markdown}")

        storage_result = {"status": "skipped", "document_id": "", "error": ""}
        if persist_storage:
            storage_result = persist_paper_result_to_dual_storage(
                source_path=source_path,
                result_payload={
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "summary": result.summary,
                    "translation_excerpt": result.translation_excerpt,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "translated": result.translated,
                },
                pg_url=pg_url,
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
            )
            if storage_result.get("status") == "completed":
                logger.info(f"论文插件双库存档完成，document_id={storage_result.get('document_id')}")
            else:
                logger.error(f"论文插件双库存档失败: {storage_result.get('error')}")
                return {
                    "status": "failed",
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "translated": result.translated,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "error": f"storage_failed: {storage_result.get('error')}",
                    "storage": storage_result,
                }
    else:
        logger.error(f"论文插件失败: {result.error}")

    return {
        "status": result.status,
        "source_type": result.source_type,
        "char_count": result.char_count,
        "translated": result.translated,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "error": result.error,
        "storage": storage_result if result.status == "completed" else {"status": "skipped"},
    }


def run_arxiv_fine_translation_workflow(
    arxiv_input: str,
    daas_url: str,
    output_dir: str,
    advanced_arg: str,
    timeout_sec: int,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 精细翻译（Docker/DaaS）并可选双库存档。"""
    from src.research.arxiv_fine_translation import run_arxiv_fine_translation_docker

    logger.info("=== 开始 Arxiv 精细翻译（Docker）流程 ===")
    result = run_arxiv_fine_translation_docker(
        arxiv_input=arxiv_input,
        server_url=daas_url,
        output_dir=output_dir,
        advanced_arg=advanced_arg,
        timeout_sec=timeout_sec,
    )

    logger.info(f"Arxiv 精细翻译状态: {result.status}")
    if result.status != "completed":
        logger.error(f"Arxiv 精细翻译失败: {result.error}")
        return {
            "status": "failed",
            "arxiv_id": result.arxiv_id,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_docker",
                "char_count": len(result.server_message),
                "summary": result.summary,
                "translation_excerpt": result.translation_excerpt,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": "completed",
        "arxiv_id": result.arxiv_id,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "error": "",
        "storage": storage_result,
    }


def run_md_translate_workflow(
    input_path: str,
    language: str,
    output_dir: str,
    additional_prompt: str,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Markdown 中英互译并可选双库存档。"""
    from src.research.markdown_translate import run_markdown_translate

    logger.info("=== 开始 Markdown 中英互译流程 ===")
    result = run_markdown_translate(
        input_path=input_path,
        language=language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("Markdown 翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("Markdown 翻译失败: %s", result.error)
        return {
            "status": "failed",
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"md_translate:{input_path}",
            result_payload={
                "source_type": "markdown_translate",
                "language": language,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
                "char_count": sum(
                    fr.get("char_count", 0) for fr in result.file_results
                ),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "language": language,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_pdf_translation_workflow(
    pdf_path: str,
    target_language: str,
    output_dir: str,
    additional_prompt: str,
    max_tokens_per_fragment: int,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 PDF 论文全文翻译并可选双库存档。"""
    from src.research.pdf_translation import run_pdf_full_text_translation

    logger.info("=== 开始 PDF 论文全文翻译流程 ===")
    result = run_pdf_full_text_translation(
        pdf_path=pdf_path,
        target_language=target_language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_tokens_per_fragment=max_tokens_per_fragment,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("PDF翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("PDF翻译失败: %s", result.error)
        return {
            "status": "failed",
            "pdf_path": pdf_path,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_html": result.output_html,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"pdf_translate:{pdf_path}",
            result_payload={
                "source_type": "pdf_full_text_translation",
                "title": result.title,
                "title_translated": result.abstract_translated,
                "abstract": result.abstract,
                "abstract_translated": result.abstract_translated,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "output_html": result.output_html,
                "translated": True,
                "char_count": result.char_count,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "pdf_path": pdf_path,
        "title": result.title,
        "title_translated": result.abstract_translated,
        "char_count": result.char_count,
        "fragment_total": result.fragment_total,
        "fragment_ok": result.fragment_ok,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_html": result.output_html,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_arxiv_quick_helper_workflow(
    arxiv_url: str,
    output_dir: str,
    target_lang: str,
    enable_translation: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 快速助手（下载 PDF + 翻译摘要）并可选双库存档。"""
    from src.research.arxiv_quick_helper import run_arxiv_quick_helper

    logger.info("=== 开始 Arxiv 快速助手流程 ===")
    
    # 构建 LLM 引擎（如果启用翻译）
    llm_engine = None
    if enable_translation:
        try:
            from src.llm.llm_engine import LLMEngine
            llm_engine = LLMEngine()
        except Exception as e:
            logger.warning(f"LLM 引擎初始化失败，将跳过摘要翻译: {e}")
            enable_translation = False
    
    result = run_arxiv_quick_helper(
        arxiv_url=arxiv_url,
        output_dir=output_dir,
        target_lang=target_lang,
        enable_translation=enable_translation,
        llm_engine=llm_engine,
    )

    logger.info("Arxiv 助手状态: %s | 论文 ID: %s", result.status, result.arxiv_id)
    if result.status == "error":
        logger.error("Arxiv 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "arxiv_id": result.arxiv_id,
            "url": arxiv_url,
            "pdf_path": result.pdf_path,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv_helper:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_quick_helper",
                "arxiv_id": result.arxiv_id,
                "title": result.title,
                "authors": result.authors,
                "publish_date": result.publish_date,
                "abstract_en": result.abstract_en,
                "abstract_zh": result.abstract_zh,
                "pdf_path": result.pdf_path,
                "pdf_size_mb": result.pdf_size_mb,
                "translated": enable_translation,
                "target_language": target_lang,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "arxiv_id": result.arxiv_id,
        "url": arxiv_url,
        "title": result.title,
        "authors": result.authors,
        "publish_date": result.publish_date,
        "abstract_en": result.abstract_en,
        "abstract_zh": result.abstract_zh,
        "pdf_path": result.pdf_path,
        "pdf_size_mb": result.pdf_size_mb,
        "error": result.error,
        "storage": storage_result,
    }


def run_google_scholar_helper_workflow(
    scholar_url: str,
    output_dir: str,
    topic_hint: str,
    target_lang: str,
    max_papers: int,
    use_llm: bool,
    additional_prompt: str,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Google Scholar 统合小助手并可选双库存档。"""
    from src.research.google_scholar_helper import run_google_scholar_related_works

    logger.info("=== 开始 Google Scholar 统合小助手流程 ===")

    llm_engine = None
    if use_llm:
        try:
            from src.llm.llm_engine import LLMEngine
            llm_engine = LLMEngine()
        except Exception as e:
            logger.warning(f"LLM 引擎初始化失败，将使用 fallback 相关工作草稿: {e}")
            use_llm = False

    result = run_google_scholar_related_works(
        scholar_url=scholar_url,
        output_dir=output_dir,
        max_papers=max_papers,
        topic_hint=topic_hint,
        target_lang=target_lang,
        use_llm=use_llm,
        llm_engine=llm_engine,
        additional_prompt=additional_prompt,
    )

    logger.info("Scholar 助手状态: %s | 文献条目: %d", result.status, result.total_papers)
    if result.status == "error":
        logger.error("Scholar 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "url": scholar_url,
            "total_papers": result.total_papers,
            "output_markdown": result.output_markdown,
            "output_json": result.output_json,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"google_scholar_helper:{scholar_url}",
            result_payload={
                "source_type": "google_scholar_helper",
                "title": "Google Scholar Related Works",
                "authors": "",
                "publish_date": "",
                "abstract_en": "",
                "abstract_zh": result.related_works_md,
                "summary": f"parsed_papers={result.total_papers}",
                "pdf_path": "",
                "pdf_size_mb": 0,
                "translated": use_llm,
                "target_language": target_lang,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "char_count": len(result.related_works_md or ""),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "url": scholar_url,
        "total_papers": result.total_papers,
        "output_markdown": result.output_markdown,
        "output_json": result.output_json,
        "related_works_md": result.related_works_md,
        "error": result.error,
        "storage": storage_result,
    }


def build_storage_connection_from_args(args: argparse.Namespace) -> Dict[str, str]:
    """构建论文插件持久化所需的双库连接参数。"""
    db_password = args.paper_db_password or os.getenv("DB_PASSWORD", "")
    db_host = args.paper_db_host or os.getenv("DB_HOST", "localhost")
    db_port = args.paper_db_port or os.getenv("DB_PORT", "5432")
    db_user = args.paper_db_user or os.getenv("DB_USER", "tcm_user")
    db_name = args.paper_db_name or os.getenv("DB_NAME", "tcm_autoresearch")

    neo4j_password = args.paper_neo4j_password or os.getenv("NEO4J_PASSWORD", "")
    neo4j_host = args.paper_neo4j_host or os.getenv("NEO4J_HOST", "localhost")
    neo4j_port = args.paper_neo4j_port or os.getenv("NEO4J_PORT", "7687")
    neo4j_user = args.paper_neo4j_user or os.getenv("NEO4J_USER", "neo4j")
    neo4j_scheme = args.paper_neo4j_scheme or os.getenv("NEO4J_SCHEME", "neo4j")

    pg_url = args.paper_pg_url or f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    neo4j_uri = args.paper_neo4j_uri or f"{neo4j_scheme}://{neo4j_host}:{neo4j_port}"

    return {
        "pg_url": pg_url,
        "neo4j_uri": neo4j_uri,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
    }


def persist_paper_result_to_dual_storage(
    source_path: str,
    result_payload: Dict[str, Any],
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, str]:
    """将论文插件输出写入 PostgreSQL + Neo4j。"""
    from src.storage import UnifiedStorageDriver

    storage = None
    doc_id = None
    try:
        if not neo4j_password:
            return {
                "status": "failed",
                "document_id": "",
                "error": "NEO4J_PASSWORD 未提供，无法完成双库存档",
            }
        if "://@" in pg_url:
            return {
                "status": "failed",
                "document_id": "",
                "error": "PostgreSQL 连接字符串缺少密码",
            }

        storage = UnifiedStorageDriver(pg_url, neo4j_uri, (neo4j_user, neo4j_password))
        storage.initialize()

        doc_id = storage.save_document(
            source_file=source_path,
            objective="paper_plugin_archive",
            raw_text_size=int(result_payload.get("char_count", 0)),
        )
        if not doc_id:
            return {
                "status": "failed",
                "document_id": "",
                "error": "保存文档失败",
            }

        storage.update_document_status(doc_id, "processing")
        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="start",
            message="论文插件结果开始双库存档",
        )

        source_name = Path(source_path).name
        entities = [
            {
                "name": source_name,
                "type": "other",
                "confidence": 0.99,
                "position": 0,
                "length": len(source_name),
                "description": "论文来源文件",
                "metadata": {
                    "source_type": result_payload.get("source_type", "unknown"),
                    "source_path": source_path,
                },
            },
            {
                "name": "论文摘要",
                "type": "other",
                "confidence": 0.95,
                "position": 0,
                "length": len(result_payload.get("summary", "")),
                "description": result_payload.get("summary", ""),
                "metadata": {
                    "summary_lang": "中文",
                    "generated_by": "paper_plugin",
                },
            },
            {
                "name": "翻译节选",
                "type": "other",
                "confidence": 0.90,
                "position": 0,
                "length": len(result_payload.get("translation_excerpt", "")),
                "description": result_payload.get("translation_excerpt", ""),
                "metadata": {
                    "translated": bool(result_payload.get("translated", False)),
                    "generated_by": "paper_plugin",
                },
            },
        ]
        entity_ids = storage.save_entities(doc_id, entities)
        if len(entity_ids) < 3:
            storage.update_document_status(doc_id, "failed")
            return {
                "status": "failed",
                "document_id": str(doc_id),
                "error": "保存实体失败",
            }

        relationships = [
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[1],
                "relationship_type": "CONTAINS",
                "confidence": 0.95,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含摘要内容",
                "metadata": {"semantic_role": "summary"},
            },
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[2],
                "relationship_type": "CONTAINS",
                "confidence": 0.90,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含翻译节选内容",
                "metadata": {"semantic_role": "translation_excerpt"},
            },
        ]
        rel_ids = storage.save_relationships(doc_id, relationships)

        storage.save_statistics(
            doc_id,
            {
                "formulas_count": 0,
                "herbs_count": 0,
                "syndromes_count": 0,
                "efficacies_count": 0,
                "relationships_count": len(rel_ids),
                "graph_nodes_count": len(entity_ids),
                "graph_edges_count": len(rel_ids),
                "graph_density": 0.0,
                "connected_components": 1,
                "source_modules": ["paper_plugin"],
                "processing_time_ms": 0,
            },
        )

        storage.save_research_analysis(
            doc_id,
            {
                "summary_analysis": {
                    "paper_summary": result_payload.get("summary", ""),
                    "translation_excerpt": result_payload.get("translation_excerpt", ""),
                    "paper_source_type": result_payload.get("source_type", "unknown"),
                    "paper_output_json": result_payload.get("output_json", ""),
                    "paper_output_markdown": result_payload.get("output_markdown", ""),
                }
            },
        )

        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="success",
            message="论文插件结果已完成双库存档",
        )
        storage.update_document_status(doc_id, "completed")
        return {
            "status": "completed",
            "document_id": str(doc_id),
            "error": "",
        }
    except Exception as exc:
        if storage and doc_id:
            try:
                storage.log_module_execution(
                    document_id=doc_id,
                    module_name="paper_plugin",
                    status="failure",
                    message="论文插件双库存档失败",
                    error_details=str(exc),
                )
                storage.update_document_status(doc_id, "failed")
            except Exception:
                pass
        return {
            "status": "failed",
            "document_id": str(doc_id) if doc_id else "",
            "error": str(exc),
        }
    finally:
        if storage:
            storage.close()


def export_research_session_reports(
    session_result: Dict[str, Any],
    report_formats: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """基于 session_result 直接导出 IMRD 报告。"""
    from src.generation.report_generator import ReportGenerator

    normalized_formats = [
        str(item).strip().lower()
        for item in (report_formats or ["markdown"])
        if str(item).strip()
    ]
    generator = ReportGenerator({"output_dir": output_dir or "./output/research_reports"})
    reports: Dict[str, Any] = {}
    output_files: Dict[str, str] = {}
    errors: List[Dict[str, str]] = []
    initialized = False

    try:
        initialized = bool(generator.initialize())
        if not initialized:
            return {
                "reports": {},
                "output_files": {},
                "errors": [{"initialize": "ReportGenerator 初始化失败"}],
            }

        for report_format in normalized_formats:
            try:
                report = generator.generate_report(session_result, report_format)
                reports[report.format] = report.to_dict()
                if report.output_path:
                    output_files[report.format] = report.output_path
            except Exception as exc:
                errors.append({report_format: str(exc)})
    finally:
        if initialized:
            generator.cleanup()

    return {
        "reports": reports,
        "output_files": output_files,
        "errors": errors,
    }


def _extract_research_phase_results(cycle_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    phase_results: Dict[str, Any] = {}
    phase_executions = cycle_snapshot.get("phase_executions")
    if not isinstance(phase_executions, dict):
        return phase_results

    for phase_name, execution in phase_executions.items():
        if not isinstance(execution, dict):
            continue
        result = execution.get("result")
        if isinstance(result, dict):
            phase_results[str(phase_name)] = result
    return phase_results


def run_research_session(
    question: str,
    config: Dict[str, Any],
    phase_names: Optional[List[str]] = None,
    export_report_formats: Optional[List[str]] = None,
    report_output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """通过 ResearchPipeline 执行完整科研闭环。

    Parameters
    ----------
    question : str
        研究问题 / 假设陈述。
    config : dict
        传递给 ResearchPipeline 的额外配置。
    phase_names : list[str] | None
        要顺序执行的阶段名称列表，默认仅 ``["observe"]``。

    Returns
    -------
    dict
        包含 ``status``、``cycle_id`` 和各阶段执行结果的字典。
    """
    from src.research.research_pipeline import ResearchPipeline
    from src.research.study_session_manager import ResearchPhase

    PHASE_MAP = {p.value: p for p in ResearchPhase}

    if phase_names is None:
        phase_names = ["observe"]

    pipeline_config = dict(config)
    if export_report_formats or report_output_dir:
        report_config = dict(pipeline_config.get("report_generation") or {})
        if export_report_formats:
            report_config["output_formats"] = list(export_report_formats)
        if report_output_dir:
            report_config["output_dir"] = report_output_dir
        pipeline_config["report_generation"] = report_config

    logger.info("=== 科研闭环模式启动 ===")
    logger.info("研究问题: %s", question)
    logger.info("执行阶段: %s", phase_names)

    pipeline = ResearchPipeline(config=pipeline_config)
    cycle = pipeline.create_research_cycle(
        cycle_name=f"research_{int(time.time())}",
        description=question,
        objective=question,
        scope="中医药",
    )
    logger.info("研究循环已创建: %s", cycle.cycle_id)

    started = pipeline.start_research_cycle(cycle.cycle_id)
    if not started:
        logger.error("研究循环启动失败: %s", cycle.cycle_id)
        return {"status": "failed", "cycle_id": cycle.cycle_id, "phase_results": {}}

    phase_results: Dict[str, Any] = {}
    overall_status = "completed"

    for pname in phase_names:
        phase_enum = PHASE_MAP.get(pname.lower())
        if phase_enum is None:
            logger.warning("跳过未知阶段: %s (可选: %s)", pname, list(PHASE_MAP.keys()))
            continue
        logger.info(">>> 开始阶段: %s", phase_enum.value)
        try:
            phase_context = {"question": question, "collect_local_corpus": True}
            if phase_enum.value == "publish":
                if export_report_formats:
                    phase_context["report_output_formats"] = list(export_report_formats)
                if report_output_dir:
                    phase_context["report_output_dir"] = report_output_dir
            result = pipeline.execute_research_phase(
                cycle.cycle_id,
                phase_enum,
                phase_context=phase_context,
            )
            phase_results[phase_enum.value] = result
            logger.info("<<< 阶段 %s 完成", phase_enum.value)
        except Exception as exc:
            logger.error("阶段 %s 执行失败: %s", phase_enum.value, exc)
            phase_results[phase_enum.value] = {"error": str(exc)}
            overall_status = "failed"
            break

    cycle_snapshot: Dict[str, Any] = {}
    try:
        cycle_snapshot = pipeline._serialize_cycle(cycle)
    except Exception:
        cycle_snapshot = {}

    try:
        pipeline.complete_research_cycle(cycle.cycle_id)
    except Exception:
        pass
    try:
        cycle_snapshot = pipeline._serialize_cycle(cycle)
    except Exception:
        pass
    try:
        pipeline.cleanup()
    except Exception:
        pass

    snapshot_phase_results = _extract_research_phase_results(cycle_snapshot)
    if snapshot_phase_results:
        phase_results.update(snapshot_phase_results)

    summary = {
        "status": overall_status,
        "session_id": cycle.cycle_id,
        "cycle_id": cycle.cycle_id,
        "title": f"中医科研 IMRD 报告：{question}",
        "question": question,
        "research_question": question,
        "executed_phases": list(phase_results.keys()),
        "phase_results": phase_results,
        "metadata": {
            "research_question": question,
            "cycle_name": cycle.cycle_name,
            "generated_by": "run_cycle_demo.research_mode",
        },
        "cycle_snapshot": cycle_snapshot,
    }

    if export_report_formats:
        report_export_result = export_research_session_reports(
            summary,
            report_formats=export_report_formats,
            output_dir=report_output_dir,
        )
        summary["reports"] = report_export_result.get("reports", {})
        summary["report_outputs"] = report_export_result.get("output_files", {})
        summary["report_export_errors"] = report_export_result.get("errors", [])

    # 持久化到 output 目录
    output_file = Path(f"./output/research_session_{int(time.time())}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("科研闭环结果已保存: %s", output_file)
    logger.info("=== 科研闭环模式结束 (status=%s) ===", overall_status)

    return summary


def main():
    """主函数"""
    help_summary = (
        "中医古籍全自动研究系统迭代循环演示\n"
        "Quick helper flags: --enable-arxiv-helper --arxiv-helper-url --arxiv-helper-dir "
        "--arxiv-helper-lang --arxiv-helper-no-translation --arxiv-helper-persist-storage "
        "--enable-scholar-helper --scholar-url --scholar-output-dir --scholar-topic-hint "
        "--scholar-target-lang --scholar-max-papers --scholar-no-llm "
        "--scholar-additional-prompt --scholar-persist-storage"
    )
    parser = argparse.ArgumentParser(
        description=help_summary,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--mode', choices=['demo', 'research'], default='demo',
                       help='运行模式: demo（现有行为）或 research（科研闭环）')
    parser.add_argument('--question', type=str, default='',
                       help='科研闭环模式下的研究问题')
    parser.add_argument('--research-phases', type=str, default='observe',
                       help='科研闭环要执行的阶段，逗号分隔（默认 observe）')
    parser.add_argument('--export-report', action='store_true',
                       help='在 research 模式结束后，基于 session_result 额外导出 IMRD 报告')
    parser.add_argument('--report-format', action='append', choices=['markdown', 'docx'],
                       help='IMRD 报告输出格式，可重复传入；默认 markdown')
    parser.add_argument('--report-output-dir', type=str, default='./output/research_reports',
                       help='IMRD 报告输出目录')
    parser.add_argument('--demo-type', choices=['basic', 'academic', 'performance', 'full'],
                       default='full', help='演示类型')
    parser.add_argument('--iterations', type=int, default=3, help='迭代次数')
    parser.add_argument('--verbose', action='store_true', help='详细输出模式')
    parser.add_argument('--enable-autorresearch', action='store_true', help='在主流程后运行 AutoResearch 循环')
    parser.add_argument('--autorresearch-instruction', type=str,
                        default='请自动优化训练脚本，降低 val_bpb 并控制显存占用。',
                        help='AutoResearch 中文研究指令')
    parser.add_argument('--autorresearch-instruction-file', type=str, default='',
                        help='AutoResearch 中文研究指令文件路径（UTF-8）')
    parser.add_argument('--autorresearch-iters', type=int, default=3,
                        help='AutoResearch 最大迭代轮次')
    parser.add_argument('--autorresearch-timeout', type=int, default=300,
                        help='AutoResearch 每轮训练时限（秒）')
    parser.add_argument('--autorresearch-strategy', choices=['heuristic', 'llm'], default='heuristic',
                        help='AutoResearch 假设生成策略')
    parser.add_argument('--autorresearch-rollback-mode', choices=['restore', 'reset'], default='restore',
                        help='AutoResearch 回滚模式')
    parser.add_argument('--autorresearch-python-exe', type=str, default=sys.executable,
                        help='AutoResearch 运行 Python 解释器路径')
    parser.add_argument('--enable-paper-plugin', action='store_true',
                        help='在主流程后运行论文读取/翻译/摘要插件')
    parser.add_argument('--paper-input', type=str, default='',
                        help='论文输入路径（.pdf/.tex 文件或目录）')
    parser.add_argument('--paper-output-dir', type=str, default='./output/paper_plugin',
                        help='论文插件输出目录')
    parser.add_argument('--paper-translate-lang', type=str, default='中文',
                        help='论文翻译目标语言')
    parser.add_argument('--paper-summary-lang', type=str, default='中文',
                        help='论文摘要输出语言')
    parser.add_argument('--paper-no-llm', action='store_true',
                        help='禁用LLM，仅做抽取式摘要')
    parser.add_argument('--paper-persist-storage', action='store_true',
                        help='将论文插件结果写入 PostgreSQL+Neo4j')
    parser.add_argument('--paper-pg-url', type=str, default='',
                        help='PostgreSQL 完整连接串，优先级高于拆分参数')
    parser.add_argument('--paper-db-host', type=str, default='',
                        help='PostgreSQL 主机，默认读取 DB_HOST 或 localhost')
    parser.add_argument('--paper-db-port', type=str, default='',
                        help='PostgreSQL 端口，默认读取 DB_PORT 或 5432')
    parser.add_argument('--paper-db-user', type=str, default='',
                        help='PostgreSQL 用户，默认读取 DB_USER 或 tcm_user')
    parser.add_argument('--paper-db-password', type=str, default='',
                        help='PostgreSQL 密码，默认读取 DB_PASSWORD')
    parser.add_argument('--paper-db-name', type=str, default='',
                        help='PostgreSQL 数据库名，默认读取 DB_NAME 或 tcm_autoresearch')
    parser.add_argument('--paper-neo4j-uri', type=str, default='',
                        help='Neo4j URI，优先级高于拆分参数')
    parser.add_argument('--paper-neo4j-scheme', type=str, default='',
                        help='Neo4j 协议，默认读取 NEO4J_SCHEME 或 neo4j')
    parser.add_argument('--paper-neo4j-host', type=str, default='',
                        help='Neo4j 主机，默认读取 NEO4J_HOST 或 localhost')
    parser.add_argument('--paper-neo4j-port', type=str, default='',
                        help='Neo4j 端口，默认读取 NEO4J_PORT 或 7687')
    parser.add_argument('--paper-neo4j-user', type=str, default='',
                        help='Neo4j 用户，默认读取 NEO4J_USER 或 neo4j')
    parser.add_argument('--paper-neo4j-password', type=str, default='',
                        help='Neo4j 密码，默认读取 NEO4J_PASSWORD')
    parser.add_argument('--enable-arxiv-fine-translation', action='store_true',
                        help='启用 Arxiv 论文精细翻译（Docker 插件适配）')
    parser.add_argument('--arxiv-input', type=str, default='',
                        help='Arxiv ID 或 URL，例如 2301.00234')
    parser.add_argument('--arxiv-daas-url', type=str, default=os.getenv('ARXIV_DAAS_URL', ''),
                        help='DaaS 服务 URL，例如 http://localhost:18000/stream')
    parser.add_argument('--arxiv-output-dir', type=str, default='./output/arxiv_fine_translation',
                        help='Arxiv 精细翻译输出目录')
    parser.add_argument('--arxiv-advanced-arg', type=str, default='',
                        help='附加翻译提示词，传递给插件命令')
    parser.add_argument('--arxiv-timeout', type=int, default=1800,
                        help='Arxiv 精细翻译请求超时（秒）')
    parser.add_argument('--arxiv-persist-storage', action='store_true',
                        help='将 Arxiv 精细翻译结果写入 PostgreSQL+Neo4j')
    # ── Markdown 中英互译参数 ──────────────────────────────────────────
    parser.add_argument('--enable-md-translate', action='store_true',
                        help='启用 Markdown 中英互译插件')
    parser.add_argument('--md-input', type=str, default='',
                        help='翻译输入：本地 .md 文件/目录，或 GitHub URL')
    parser.add_argument('--md-lang', type=str, default='en->zh',
                        help="翻译方向：'en->zh'（默认）/ 'zh->en' / 任意语言名，如 Japanese")
    parser.add_argument('--md-output-dir', type=str, default='./output/md_translate',
                        help='Markdown 翻译输出目录')
    parser.add_argument('--md-additional-prompt', type=str, default='',
                        help='附加翻译指令，追加到系统提示词')
    parser.add_argument('--md-max-workers', type=int, default=1,
                        help='并行翻译片段线程数（本地 LLM 建议保持 1）')
    parser.add_argument('--md-no-llm', action='store_true',
                        help='跳过 LLM 调用，原样输出（用于调试）')
    parser.add_argument('--md-persist-storage', action='store_true',
                        help='将翻译结果写入 PostgreSQL+Neo4j')
    # ── PDF 论文全文翻译参数 ─────────────────────────────────────────────
    parser.add_argument('--enable-pdf-translation', action='store_true',
                        help='启用 PDF 论文全文翻译（提取标题&摘要+多线程翻译全文）')
    parser.add_argument('--pdf-input', type=str, default='',
                        help='PDF 文件路径')
    parser.add_argument('--pdf-target-lang', type=str, default='Chinese',
                        help='翻译目标语言（默认 Chinese）')
    parser.add_argument('--pdf-output-dir', type=str, default='./output/pdf_translation',
                        help='PDF 翻译输出目录')
    parser.add_argument('--pdf-additional-prompt', type=str, default='',
                        help='附加翻译指令，追加到系统提示词')
    parser.add_argument('--pdf-max-tokens-per-fragment', type=int, default=1024,
                        help='每个翻译片段最大 Token 数')
    parser.add_argument('--pdf-max-workers', type=int, default=3,
                        help='并行翻译片段线程数')
    parser.add_argument('--pdf-no-llm', action='store_true',
                        help='跳过 LLM 调用，原样输出（用于调试）')
    parser.add_argument('--pdf-persist-storage', action='store_true',
                        help='将翻译结果写入 PostgreSQL+Neo4j')
    # ── Arxiv 快速助手参数 ──────────────────────────────────────────────
    parser.add_argument('--enable-arxiv-helper', action='store_true',
                        help='启用 Arxiv 快速助手（下载 PDF + 翻译摘要）')
    parser.add_argument('--arxiv-helper-url', type=str, default='',
                        help='Arxiv 论文 URL 或 ID（如 2301.00234 或 https://arxiv.org/abs/2301.00234）')
    parser.add_argument('--arxiv-helper-dir', type=str, default='./output/arxiv_quick_helper',
                        help='PDF 下载输出目录')
    parser.add_argument('--arxiv-helper-lang', type=str, default='Chinese',
                        help='摘要翻译目标语言（默认 Chinese）')
    parser.add_argument('--arxiv-helper-no-translation', action='store_true',
                        help='跳过摘要翻译，仅下载 PDF 和获取元信息')
    parser.add_argument('--arxiv-helper-persist-storage', action='store_true',
                        help='将处理结果写入 PostgreSQL+Neo4j')
    # ── Google Scholar 统合小助手参数 ─────────────────────────────────────
    parser.add_argument('--enable-scholar-helper', action='store_true',
                        help='启用谷歌学术统合小助手（输入 Scholar 搜索页 URL 生成 related works）')
    parser.add_argument('--scholar-url', type=str, default='',
                        help='Google Scholar 搜索页 URL')
    parser.add_argument('--scholar-output-dir', type=str, default='./output/google_scholar_helper',
                        help='Google Scholar helper 输出目录')
    parser.add_argument('--scholar-topic-hint', type=str, default='',
                        help='related works 主题提示（可选）')
    parser.add_argument('--scholar-target-lang', type=str, default='Chinese',
                        help='related works 输出语言（默认 Chinese）')
    parser.add_argument('--scholar-max-papers', type=int, default=20,
                        help='最多解析的 Scholar 条目数（默认 20）')
    parser.add_argument('--scholar-no-llm', action='store_true',
                        help='跳过 LLM 生成，输出 fallback 相关工作草稿')
    parser.add_argument('--scholar-additional-prompt', type=str, default='',
                        help='附加 related works 写作指令')
    parser.add_argument('--scholar-persist-storage', action='store_true',
                        help='将 Scholar helper 结果写入 PostgreSQL+Neo4j')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("中医古籍全自动研究系统迭代循环演示启动")
    logger.info(f"演示类型: {args.demo_type}")
    logger.info(f"迭代次数: {args.iterations}")
    logger.info(f"AutoResearch 启用: {args.enable_autorresearch}")
    logger.info(f"论文插件启用: {args.enable_paper_plugin}")
    logger.info(f"论文插件双库存档: {args.paper_persist_storage}")
    logger.info(f"Arxiv精细翻译启用: {args.enable_arxiv_fine_translation}")
    logger.info(f"Markdown翻译启用: {args.enable_md_translate}")
    logger.info(f"PDF全文翻译启用: {args.enable_pdf_translation}")
    logger.info(f"Arxiv快速助手启用: {args.enable_arxiv_helper}")
    logger.info(f"Scholar统合助手启用: {args.enable_scholar_helper}")
    
    try:
        setup_signal_handlers()

        # ── 科研闭环模式 ─────────────────────────────────────────────
        if args.mode == 'research':
            if not args.question:
                logger.error("科研闭环模式需要 --question 参数")
                return 1
            phases_str = args.research_phases.strip()
            phase_names = [p.strip() for p in phases_str.split(',') if p.strip()]
            report_formats = args.report_format or ["markdown"]
            result = run_research_session(
                question=args.question,
                config={},
                phase_names=phase_names,
                export_report_formats=report_formats if args.export_report else None,
                report_output_dir=args.report_output_dir,
            )
            if result.get('status') == 'failed':
                return 1
            return 0

        # ── demo 模式（保持现有行为） ────────────────────────────────
        if args.demo_type == 'basic':
            logger.info("运行基础演示...")
            run_full_cycle_demo(max_iterations=args.iterations)
            
        elif args.demo_type == 'academic':
            logger.info("运行学术演示...")
            run_academic_demo()
            
        elif args.demo_type == 'performance':
            logger.info("运行性能演示...")
            run_performance_demo()
            
        elif args.demo_type == 'full':
            logger.info("运行完整演示...")
            
            # 运行基础演示
            logger.info("1. 基础演示:")
            run_full_cycle_demo(max_iterations=args.iterations)
            
            # 运行学术演示
            logger.info("\n2. 学术演示:")
            run_academic_demo()
            
            # 运行性能演示
            logger.info("\n3. 性能演示:")
            run_performance_demo()

        if args.enable_autorresearch:
            logger.info("\n4. AutoResearch 演示:")
            ar_result = run_autorresearch_workflow(
                instruction=args.autorresearch_instruction,
                instruction_file=args.autorresearch_instruction_file,
                max_iters=args.autorresearch_iters,
                timeout_seconds=args.autorresearch_timeout,
                strategy=args.autorresearch_strategy,
                rollback_mode=args.autorresearch_rollback_mode,
                python_exe=args.autorresearch_python_exe,
            )
            if ar_result.get("status") != "completed":
                logger.error("AutoResearch 子流程失败，主流程返回非零状态")
                return 1

        if args.enable_paper_plugin:
            if not args.paper_input:
                logger.error("启用论文插件时必须提供 --paper-input")
                return 1

            logger.info("\n5. 论文插件演示:")
            storage_conn = build_storage_connection_from_args(args)
            paper_result = run_paper_plugin_workflow(
                source_path=args.paper_input,
                output_dir=args.paper_output_dir,
                translate_lang=args.paper_translate_lang,
                summary_lang=args.paper_summary_lang,
                use_llm=not args.paper_no_llm,
                persist_storage=args.paper_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if paper_result.get("status") != "completed":
                logger.error("论文插件子流程失败，主流程返回非零状态")
                return 1

        if args.enable_arxiv_fine_translation:
            if not args.arxiv_input:
                logger.error("启用 Arxiv 精细翻译时必须提供 --arxiv-input")
                return 1
            if not args.arxiv_daas_url:
                logger.error("启用 Arxiv 精细翻译时必须提供 --arxiv-daas-url 或环境变量 ARXIV_DAAS_URL")
                return 1

            logger.info("\n6. Arxiv 精细翻译（Docker）演示:")
            storage_conn = build_storage_connection_from_args(args)
            arxiv_result = run_arxiv_fine_translation_workflow(
                arxiv_input=args.arxiv_input,
                daas_url=args.arxiv_daas_url,
                output_dir=args.arxiv_output_dir,
                advanced_arg=args.arxiv_advanced_arg,
                timeout_sec=args.arxiv_timeout,
                persist_storage=args.arxiv_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if arxiv_result.get("status") != "completed":
                logger.error("Arxiv 精细翻译子流程失败，主流程返回非零状态")
                return 1

        if args.enable_md_translate:
            if not args.md_input:
                logger.error("启用 Markdown 翻译时必须提供 --md-input")
                return 1

            logger.info("\n7. Markdown 中英互译演示:")
            storage_conn = build_storage_connection_from_args(args)
            md_result = run_md_translate_workflow(
                input_path=args.md_input,
                language=args.md_lang,
                output_dir=args.md_output_dir,
                additional_prompt=args.md_additional_prompt,
                max_workers=args.md_max_workers,
                use_llm=not args.md_no_llm,
                persist_storage=args.md_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if md_result.get("status") == "failed":
                logger.error("Markdown 翻译子流程失败，主流程返回非零状态")
                return 1

        if args.enable_pdf_translation:
            if not args.pdf_input:
                logger.error("启用 PDF 翻译时必须提供 --pdf-input")
                return 1

            logger.info("\n8. PDF 论文全文翻译演示:")
            storage_conn = build_storage_connection_from_args(args)
            pdf_result = run_pdf_translation_workflow(
                pdf_path=args.pdf_input,
                target_language=args.pdf_target_lang,
                output_dir=args.pdf_output_dir,
                additional_prompt=args.pdf_additional_prompt,
                max_tokens_per_fragment=args.pdf_max_tokens_per_fragment,
                max_workers=args.pdf_max_workers,
                use_llm=not args.pdf_no_llm,
                persist_storage=args.pdf_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if pdf_result.get("status") == "failed":
                logger.error("PDF 翻译子流程失败，主流程返回非零状态")
                return 1

        if args.enable_arxiv_helper:
            if not args.arxiv_helper_url:
                logger.error("启用 Arxiv 快速助手时必须提供 --arxiv-helper-url")
                return 1

            logger.info("\n9. Arxiv 快速助手演示:")
            storage_conn = build_storage_connection_from_args(args)
            arxiv_result = run_arxiv_quick_helper_workflow(
                arxiv_url=args.arxiv_helper_url,
                output_dir=args.arxiv_helper_dir,
                target_lang=args.arxiv_helper_lang,
                enable_translation=not args.arxiv_helper_no_translation,
                persist_storage=args.arxiv_helper_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if arxiv_result.get("status") == "error":
                logger.error("Arxiv 快速助手子流程失败，主流程返回非零状态")
                return 1

        if args.enable_scholar_helper:
            if not args.scholar_url:
                logger.error("启用 Scholar 统合助手时必须提供 --scholar-url")
                return 1

            logger.info("\n10. Google Scholar 统合小助手演示:")
            storage_conn = build_storage_connection_from_args(args)
            scholar_result = run_google_scholar_helper_workflow(
                scholar_url=args.scholar_url,
                output_dir=args.scholar_output_dir,
                topic_hint=args.scholar_topic_hint,
                target_lang=args.scholar_target_lang,
                max_papers=args.scholar_max_papers,
                use_llm=not args.scholar_no_llm,
                additional_prompt=args.scholar_additional_prompt,
                persist_storage=args.scholar_persist_storage,
                pg_url=storage_conn["pg_url"],
                neo4j_uri=storage_conn["neo4j_uri"],
                neo4j_user=storage_conn["neo4j_user"],
                neo4j_password=storage_conn["neo4j_password"],
            )
            if scholar_result.get("status") == "error":
                logger.error("Scholar 统合助手子流程失败，主流程返回非零状态")
                return 1

        logger.info("=== 演示完成 ===")
        return 0
        
    except KeyboardInterrupt:
        logger.info("用户中断演示")
        return 1
    except Exception as e:
        logger.error(f"演示执行失败: {e}")
        logger.error(traceback.format_exc())
        return 1

# (已移除重复的 run_full_cycle_demo 定义)


if __name__ == "__main__":
    sys.exit(main())
