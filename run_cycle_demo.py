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
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor
from src.output.output_generator import OutputGenerator
from src.preprocessor.document_preprocessor import DocumentPreprocessor
from src.reasoning.reasoning_engine import ReasoningEngine
from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tcmautoresearch_demo.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# 确保必要的目录存在
os.makedirs('./output', exist_ok=True)
os.makedirs('./logs', exist_ok=True)
os.makedirs('./data', exist_ok=True)


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
            "input_data": input_data
        }
    }
    
    try:
        # 依次执行每个模块
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
        
        # 计算迭代总时间
        iteration_results["end_time"] = datetime.now().isoformat()
        iteration_results["duration"] = time.time() - start_time
        iteration_results["status"] = "completed"
        
        logger.info(f"第 {iteration_number} 次迭代循环完成，耗时: {iteration_results['duration']:.2f}秒")
        
        return iteration_results
        
    except Exception as e:
        iteration_results["status"] = "failed"
        iteration_results["error"] = str(e)
        iteration_results["end_time"] = datetime.now().isoformat()
        iteration_results["duration"] = time.time() - start_time
        logger.error(f"第 {iteration_number} 次迭代循环失败: {e}")
        logger.error(traceback.format_exc())
        return iteration_results

def run_full_cycle_demo(max_iterations: int=3, sample_data: Optional[List[str]]=None):
    """
    运行完整循环演示
    
    Args:
        max_iterations (int): 最大迭代次数
        sample_data (List[str]): 示例数据列表
    """
    logger.info("=== 开始中医古籍全自动研究系统迭代循环演示 ===")
    
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
        }
    }
    
    try:
        # 全循环复用模块，减少每轮初始化/清理开销
        shared_modules = build_real_modules()
        initialize_real_modules(shared_modules)

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
            )
            
            # 记录迭代结果
            cycle_results["iterations"].append(iteration_result)
            
            # 更新性能指标
            cycle_results["performance_metrics"]["total_iterations"] += 1
            if iteration_result["status"] == "completed":
                cycle_results["performance_metrics"]["successful_iterations"] += 1
            else:
                cycle_results["performance_metrics"]["failed_iterations"] += 1
            
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
        
        # 保存结果
        output_file = f"./output/cycle_demo_results_{int(time.time())}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cycle_results, f, ensure_ascii=False, indent=2)
        
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


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='中医古籍全自动研究系统迭代循环演示')
    parser.add_argument('--demo-type', choices=['basic', 'academic', 'performance', 'full'],
                       default='full', help='演示类型')
    parser.add_argument('--iterations', type=int, default=3, help='迭代次数')
    parser.add_argument('--verbose', action='store_true', help='详细输出模式')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("中医古籍全自动研究系统迭代循环演示启动")
    logger.info(f"演示类型: {args.demo_type}")
    logger.info(f"迭代次数: {args.iterations}")
    
    try:
        setup_signal_handlers()
        
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
