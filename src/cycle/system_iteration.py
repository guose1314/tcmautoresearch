# cycle/system_iteration.py
"""
中医古籍全自动研究系统 - 专业学术系统级迭代循环
基于T/C IATCM 098-2023标准的系统级迭代管理
"""

import json
import logging
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional

nx = import_module("networkx")
import numpy as np

from src.core.phase_tracker import PhaseTrackerMixin
from src.cycle.iteration_cycle import _get_tester

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class SystemIterationResult:
    """系统迭代结果数据结构"""
    iteration_id: str
    cycle_number: int
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    module_results: Dict[str, Any] = field(default_factory=dict)
    system_metrics: Dict[str, Any] = field(default_factory=dict)
    system_insights: List[Dict[str, Any]] = field(default_factory=list)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    quality_assessment: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class SystemIterationCycle(PhaseTrackerMixin):
    """
    系统级迭代循环管理器
    
    本模块负责整个系统的迭代优化，协调各个模块的协同工作，
    确保系统在学术标准下持续改进，符合T/C IATCM 098-2023要求。
    
    主要功能：
    1. 系统级迭代流程管理
    2. 模块间协同优化
    3. 系统整体质量控制
    4. 学术洞察发现
    5. 系统性能监控与优化
    6. 知识沉淀与传承
    """
    
    def __init__(self, system_config: Optional[Dict[str, Any]] = None):
        self.config = system_config or {}
        self.system_iterations: List[SystemIterationResult] = []
        self.failed_iterations: List[SystemIterationResult] = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.system_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_quality": float(self.config.get("minimum_stable_quality", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d42.v1"),
        }
        self.performance_metrics = {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "average_duration": 0.0,
            "total_processing_time": 0.0,
            "system_quality_score": 0.0,
            "system_confidence_score": 0.0
        }
        self.knowledge_graph = nx.MultiDiGraph()
        self.module_cycles = {}
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("系统级迭代循环管理器初始化完成")

    def _initialize_phase_tracking(self, iteration_result: SystemIterationResult) -> None:
        iteration_result.metadata["phase_history"] = []
        iteration_result.metadata["phase_timings"] = {}
        iteration_result.metadata["completed_phases"] = []
        iteration_result.metadata["failed_phase"] = None
        iteration_result.metadata["final_status"] = iteration_result.status
        iteration_result.metadata["last_completed_phase"] = None
        iteration_result.metadata["failed_operations"] = []

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(self.system_metadata)

    def _start_system_phase(self, phase_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self.governance_config.get("enable_phase_tracking", True):
            self.system_metadata["phase_history"].append(phase_entry)
        return phase_entry

    def _complete_system_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        self.system_metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in self.system_metadata["completed_phases"]:
            self.system_metadata["completed_phases"].append(phase_name)
        self.system_metadata["last_completed_phase"] = phase_name
        self.system_metadata["final_status"] = "completed"

    def _fail_system_phase(
        self,
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
        error: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        self.system_metadata["phase_timings"][phase_name] = round(duration, 6)
        self.system_metadata["failed_phase"] = phase_name
        self.system_metadata["final_status"] = "failed"
        self._record_failed_operation(self.failed_operations, phase_name, error, duration, details)

    def _record_failed_operation(
        self,
        container: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.governance_config.get("persist_failed_operations", True):
            return
        failure_entry = {
            "operation": operation,
            "error": error,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration, 6),
        }
        if details:
            failure_entry["details"] = self._serialize_value(details)
        container.append(failure_entry)

    def _execute_phase(
        self,
        iteration_result: SystemIterationResult,
        phase_name: str,
        status: str,
        operation: Callable[[], Any],
    ) -> Any:
        phase_start = time.perf_counter()
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
        }
        iteration_result.metadata["phase_history"].append(phase_entry)
        iteration_result.status = status

        try:
            result = operation()
        except Exception as exc:
            duration = time.perf_counter() - phase_start
            phase_entry["status"] = "failed"
            phase_entry["ended_at"] = datetime.now().isoformat()
            phase_entry["duration_seconds"] = round(duration, 6)
            phase_entry["error"] = str(exc)
            iteration_result.metadata["phase_timings"][phase_name] = round(duration, 6)
            iteration_result.metadata["failed_phase"] = phase_name
            iteration_result.metadata["final_status"] = "failed"
            failure_details = {
                "iteration_id": iteration_result.iteration_id,
                "cycle_number": iteration_result.cycle_number,
                "status": status,
            }
            self._record_failed_operation(iteration_result.metadata["failed_operations"], phase_name, str(exc), duration, failure_details)
            self._record_failed_operation(self.failed_operations, phase_name, str(exc), duration, failure_details)
            raise

        duration = time.perf_counter() - phase_start
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        iteration_result.metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in iteration_result.metadata["completed_phases"]:
            iteration_result.metadata["completed_phases"].append(phase_name)
        iteration_result.metadata["last_completed_phase"] = phase_name
        iteration_result.metadata["final_status"] = "completed"
        return result

    def _finalize_iteration_result(
        self,
        iteration_result: SystemIterationResult,
        start_time: float,
        success: bool,
    ) -> None:
        iteration_result.status = "completed" if success else "failed"
        iteration_result.end_time = datetime.now().isoformat()
        iteration_result.duration = time.perf_counter() - start_time
        iteration_result.metadata["final_status"] = iteration_result.status

    def _sync_analysis_summary(self, iteration_result: SystemIterationResult) -> None:
        analysis_summary = iteration_result.metadata.get("analysis_summary") or {}
        analysis_summary["failed_operation_count"] = len(self.failed_operations)
        analysis_summary["failed_phase"] = iteration_result.metadata.get("failed_phase") or self.system_metadata.get("failed_phase")
        analysis_summary["last_completed_phase"] = iteration_result.metadata.get("last_completed_phase") or self.system_metadata.get("last_completed_phase")
        analysis_summary["final_status"] = iteration_result.status
        analysis_summary.setdefault(
            "status",
            "stable"
            if iteration_result.status == "completed"
            and float(iteration_result.quality_assessment.get("overall_quality", 0.0)) >= self.governance_config["minimum_stable_quality"]
            else "needs_followup",
        )
        iteration_result.metadata["analysis_summary"] = analysis_summary
    
    def execute_system_iteration(self, context: Dict[str, Any]) -> SystemIterationResult:
        """
        执行系统级迭代
        
        Args:
            context (Dict[str, Any]): 系统执行上下文
            
        Returns:
            SystemIterationResult: 系统迭代结果
        """
        start_time = time.perf_counter()
        self.system_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "running",
            "last_completed_phase": None,
        }
        system_phase_entry = self._start_system_phase("execute_system_iteration", {"context_keys": sorted((context or {}).keys())})
        
        iteration_result = SystemIterationResult(
            iteration_id=f"sys_iter_{int(time.time())}",
            cycle_number=len(self.system_iterations),
            status="pending",
            start_time=datetime.now().isoformat()
        )
        self._initialize_phase_tracking(iteration_result)
        
        try:
            module_results = self._execute_phase(
                iteration_result,
                "execute_modules",
                "executing_modules",
                lambda: self._execute_module_iterations(context),
            )
            iteration_result.module_results = module_results
            
            system_test_results = self._execute_phase(
                iteration_result,
                "test_system",
                "testing_system",
                lambda: self._test_system_level(context, module_results),
            )
            iteration_result.system_metrics = system_test_results
            
            analysis_results = self._execute_phase(
                iteration_result,
                "analyze_system",
                "analyzing_system",
                lambda: self._analyze_system_results(context, module_results, system_test_results),
            )
            iteration_result.system_insights = analysis_results.get("system_insights", [])
            iteration_result.academic_insights = analysis_results.get("academic_insights", [])
            iteration_result.quality_assessment = analysis_results.get("quality_metrics", {})
            iteration_result.confidence_scores = analysis_results.get("confidence_scores", {})
            iteration_result.recommendations = analysis_results.get("recommendations", [])
            iteration_result.metadata["analysis_summary"] = analysis_results.get("analysis_summary", {})
            
            self._finalize_iteration_result(iteration_result, start_time, success=True)
            self._complete_system_phase("execute_system_iteration", system_phase_entry, start_time)
            self._sync_analysis_summary(iteration_result)
            
            self._update_performance_metrics(iteration_result)
            
            self.system_iterations.append(iteration_result)
            
            self.logger.info("系统级迭代完成")
            return iteration_result
            
        except Exception as e:
            self._finalize_iteration_result(iteration_result, start_time, success=False)
            self._fail_system_phase(
                "execute_system_iteration",
                system_phase_entry,
                start_time,
                str(e),
                {
                    "iteration_id": iteration_result.iteration_id,
                    "cycle_number": iteration_result.cycle_number,
                    "failed_phase": iteration_result.metadata.get("failed_phase"),
                },
            )
            self._sync_analysis_summary(iteration_result)
            self._update_performance_metrics(iteration_result)
            self.system_iterations.append(iteration_result)
            self.failed_iterations.append(iteration_result)
            self.logger.error(f"系统级迭代失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def _execute_module_iterations(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行模块迭代"""
        self.logger.info("执行模块迭代")
        module_results = {}
        
        try:
            # 获取系统中的模块列表
            modules = context.get("modules", [])
            if not modules:
                # 如果没有指定模块，则使用默认模块
                modules = ["document_preprocessing", "entity_extraction", 
                          "semantic_modeling", "reasoning_engine", 
                          "output_generation", "self_learning"]
            
            # 依次执行每个模块的迭代
            for module_name in modules:
                try:
                    # 如果已经有模块迭代循环，使用现有实例
                    if module_name in self.module_cycles:
                        module_cycle = self.module_cycles[module_name]
                    else:
                        # 创建新的模块迭代循环，传播 mock_mode
                        from .module_iteration import ModuleIterationCycle
                        module_config = {"mock_mode": context.get("mock_mode", self.config.get("mock_mode", False))}
                        module_cycle = ModuleIterationCycle(module_name, module_config)
                        self.module_cycles[module_name] = module_cycle
                    
                    # 执行模块迭代
                    module_context = {
                        "module": module_name,
                        "input_data": context.get("input_data", {}),
                        "metadata": context.get("metadata", {}),
                        "mock_mode": context.get("mock_mode", self.config.get("mock_mode", False)),
                    }
                    
                    result = module_cycle.execute_module_iteration(module_context)
                    module_results[module_name] = result.__dict__
                    
                except Exception as e:
                    self.logger.error(f"模块 {module_name} 迭代失败: {e}")
                    module_results[module_name] = {
                        "error": str(e),
                        "status": "failed",
                        "timestamp": datetime.now().isoformat()
                    }
            
            self.logger.info("模块迭代完成")
            return module_results
            
        except Exception as e:
            self.logger.error(f"模块迭代执行失败: {e}")
            raise
    
    def _test_system_level(self, context: Dict[str, Any], 
                          module_results: Dict[str, Any]) -> Dict[str, Any]:
        """系统级测试"""
        self.logger.info("执行系统级测试")
        start_time = time.time()
        
        try:
            mock_mode = self.config.get("mock_mode", False) or context.get("mock_mode", False)

            if mock_mode:
                system_test_results = {
                    "system_health": "healthy",
                    "performance_score": 0.85,
                    "resource_usage": {
                        "cpu": 0.65,
                        "memory": 0.72,
                        "disk": 0.45
                    },
                    "throughput": 12.5,
                    "latency": 0.25,
                    "reliability": 0.98,
                    "quality_assurance": {
                        "academic_compliance": True,
                        "standard_compliance": True,
                        "quality_metrics": {
                            "completeness": 0.92,
                            "accuracy": 0.88,
                            "consistency": 0.95
                        }
                    },
                    "test_time": time.time() - start_time
                }
            else:
                tester = _get_tester()
                tester_context = {
                    "module_results": module_results,
                    "system_level": True,
                }
                raw_results = tester.run_all_tests(context=tester_context)

                overall = raw_results.get("overall_summary", {})
                execution_time = raw_results.get("execution_time", 0.0)
                total_tests = overall.get("total_tests", 0)
                total_passed = overall.get("total_passed", 0)
                pass_rate = total_passed / total_tests if total_tests > 0 else 0.0

                system_test_results = {
                    "system_health": "healthy" if pass_rate >= 0.8 else "degraded",
                    "performance_score": pass_rate,
                    "resource_usage": {
                        "cpu": overall.get("cpu_usage", 0.0),
                        "memory": overall.get("memory_usage", 0.0),
                        "disk": overall.get("disk_usage", 0.0),
                    },
                    "throughput": total_tests / execution_time if execution_time > 0 else 0.0,
                    "latency": execution_time / total_tests if total_tests > 0 else 0.0,
                    "reliability": pass_rate,
                    "quality_assurance": {
                        "academic_compliance": pass_rate >= 0.8,
                        "standard_compliance": pass_rate >= 0.7,
                        "quality_metrics": {
                            "completeness": pass_rate,
                            "accuracy": pass_rate,
                            "consistency": pass_rate,
                        }
                    },
                    "test_time": time.time() - start_time,
                    "raw_results": raw_results,
                }
            
            self.logger.info("系统级测试完成")
            return system_test_results
            
        except Exception as e:
            self.logger.error(f"系统级测试失败: {e}")
            raise
    
    def _analyze_system_results(self, context: Dict[str, Any], 
                              module_results: Dict[str, Any],
                              system_test_results: Dict[str, Any]) -> Dict[str, Any]:
        """分析系统结果"""
        self.logger.info("分析系统结果")
        start_time = time.time()
        
        try:
            quality_metrics = self._calculate_system_quality_metrics(module_results, system_test_results)
            system_insights = self._generate_system_insights(module_results, system_test_results)
            academic_insights = self._generate_academic_insights(module_results, system_test_results)
            recommendations = self._generate_system_recommendations(module_results, system_test_results)
            confidence_scores = self._calculate_system_confidence_scores(module_results, system_test_results)
            analysis_payload = {
                "quality_metrics": quality_metrics,
                "system_insights": system_insights,
                "academic_insights": academic_insights,
                "recommendations": recommendations,
                "confidence_scores": confidence_scores,
            }
            analysis_results = self._build_analysis_results(
                module_results,
                analysis_payload,
                start_time,
            )
            
            self.logger.info("系统结果分析完成")
            return analysis_results
            
        except Exception as e:
            self.logger.error(f"系统结果分析失败: {e}")
            raise

    def _build_analysis_results(
        self,
        module_results: Dict[str, Any],
        analysis_payload: Dict[str, Any],
        start_time: float,
    ) -> Dict[str, Any]:
        return {
            "quality_metrics": analysis_payload["quality_metrics"],
            "system_insights": analysis_payload["system_insights"],
            "academic_insights": analysis_payload["academic_insights"],
            "recommendations": analysis_payload["recommendations"],
            "confidence_scores": analysis_payload["confidence_scores"],
            "analysis_summary": self._build_analysis_summary(
                module_results,
                analysis_payload["quality_metrics"],
                analysis_payload["recommendations"],
                analysis_payload["academic_insights"],
            ),
            "analysis_time": round(time.time() - start_time, 6),
        }

    def _build_analysis_summary(
        self,
        module_results: Dict[str, Any],
        quality_metrics: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        academic_insights: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        failed_modules = self._get_failed_modules(module_results)
        overall_quality = float(quality_metrics.get("overall_quality", 0.0))
        failure_threshold = int(self.config.get("failed_module_attention_threshold", 1))
        minimum_stable_quality = float(self.config.get("minimum_stable_quality", 0.85))

        return {
            "module_count": len(module_results),
            "failed_module_count": len(failed_modules),
            "failed_modules": failed_modules,
            "overall_quality": overall_quality,
            "system_status": "attention_required" if len(failed_modules) >= failure_threshold or overall_quality < minimum_stable_quality else "stable",
            "status": "needs_followup" if self.failed_operations or len(failed_modules) >= failure_threshold or overall_quality < minimum_stable_quality else "stable",
            "recommendation_count": len(recommendations),
            "academic_insight_count": len(academic_insights),
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.system_metadata.get("failed_phase"),
            "last_completed_phase": self.system_metadata.get("last_completed_phase"),
            "final_status": self.system_metadata.get("final_status", "initialized"),
        }

    def _build_system_analysis_summary(self) -> Dict[str, Any]:
        total_iterations = len(self.system_iterations)
        completed_iterations = sum(1 for item in self.system_iterations if item.status == "completed")
        failed_iterations = sum(1 for item in self.system_iterations if item.status == "failed")
        stable = (
            total_iterations > 0
            and failed_iterations == 0
            and self.performance_metrics.get("system_quality_score", 0.0) >= self.governance_config["minimum_stable_quality"]
        )
        status = "idle"
        if self.failed_operations:
            status = "needs_followup"
        elif total_iterations > 0:
            status = "stable" if stable else "degraded"

        return {
            "status": status,
            "total_iterations": total_iterations,
            "completed_iterations": completed_iterations,
            "failed_iterations": failed_iterations,
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.system_metadata.get("failed_phase"),
            "last_completed_phase": self.system_metadata.get("last_completed_phase"),
            "final_status": self.system_metadata.get("final_status", "initialized"),
        }
    
    def _calculate_system_quality_metrics(self, module_results: Dict[str, Any], 
                                        system_test_results: Dict[str, Any]) -> Dict[str, Any]:
        """计算系统质量指标"""
        # 基于模块结果和系统测试结果计算质量指标
        quality_metrics = {
            "module_completeness": 0.0,
            "module_accuracy": 0.0,
            "module_consistency": 0.0,
            "system_performance": system_test_results.get("performance_score", 0.0),
            "system_reliability": system_test_results.get("reliability", 0.0),
            "overall_quality": 0.0
        }
        
        # 计算模块平均质量
        module_quality_scores = []
        for result in module_results.values():
            if "quality_assessment" in result:
                quality = result["quality_assessment"].get("overall_quality", 0.0)
                module_quality_scores.append(quality)
        
        if module_quality_scores:
            quality_metrics["module_completeness"] = np.mean(module_quality_scores)
            quality_metrics["module_accuracy"] = np.mean(module_quality_scores)
            quality_metrics["module_consistency"] = np.mean(module_quality_scores)
        
        # 计算综合质量评分
        weights = {
            "module_completeness": 0.3,
            "module_accuracy": 0.3,
            "module_consistency": 0.1,
            "system_performance": 0.15,
            "system_reliability": 0.15
        }
        
        quality_scores = []
        for metric, weight in weights.items():
            if metric in quality_metrics:
                quality_scores.append(quality_metrics[metric] * weight)
        
        quality_metrics["overall_quality"] = sum(quality_scores) if quality_scores else 0.0
        
        return quality_metrics
    
    def _generate_system_insights(self, module_results: Dict[str, Any], 
                                system_test_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成系统洞察"""
        insights = []
        
        # 基于模块结果生成洞察
        module_names = list(module_results.keys())
        if module_names:
            insight = {
                "type": "module_integration",
                "title": "模块协同效果洞察",
                "description": f"系统中 {len(module_names)} 个模块协同工作，整体表现良好",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat(),
                "tags": ["module", "integration", "system"]
            }
            insights.append(insight)
        
        # 基于系统测试结果生成洞察
        if system_test_results.get("system_health") == "healthy":
            insight = {
                "type": "system_health",
                "title": "系统健康度洞察",
                "description": "系统运行健康，性能稳定",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat(),
                "tags": ["health", "performance", "system"]
            }
            insights.append(insight)

        failed_modules = self._get_failed_modules(module_results)
        if failed_modules:
            insights.append(
                {
                    "type": "system_risk",
                    "title": "系统级风险洞察",
                    "description": f"发现 {len(failed_modules)} 个失败模块，需要优先处理：{', '.join(failed_modules)}",
                    "confidence": 0.88,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["risk", "integration", "system"],
                }
            )
        
        return insights

    def _generate_academic_insights(
        self,
        module_results: Dict[str, Any],
        system_test_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """生成学术一致性洞察"""
        insights: List[Dict[str, Any]] = []
        quality_assurance = system_test_results.get("quality_assurance", {})
        quality_metrics = quality_assurance.get("quality_metrics", {})
        academic_compliance = bool(quality_assurance.get("academic_compliance", False))
        overall_quality = self._calculate_system_quality_metrics(module_results, system_test_results).get("overall_quality", 0.0)

        if academic_compliance:
            insights.append(
                {
                    "type": "academic_compliance",
                    "title": "学术合规性洞察",
                    "description": "系统级结果满足学术合规要求，可进入后续复核流程",
                    "confidence": 0.92,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "compliance", "system"],
                }
            )

        if quality_metrics:
            insights.append(
                {
                    "type": "academic_quality",
                    "title": "学术质量洞察",
                    "description": (
                        f"系统质量指标完整度={quality_metrics.get('completeness', 0.0):.2f}, "
                        f"准确性={quality_metrics.get('accuracy', 0.0):.2f}, "
                        f"一致性={quality_metrics.get('consistency', 0.0):.2f}"
                    ),
                    "confidence": 0.87,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "quality", "metrics"],
                }
            )

        if overall_quality < float(self.config.get("academic_insight_min_quality", 0.85)):
            insights.append(
                {
                    "type": "academic_gap",
                    "title": "学术质量缺口洞察",
                    "description": "系统整体质量尚未达到学术沉淀阈值，建议补充系统级回归与证据归档",
                    "confidence": 0.83,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "gap", "quality"],
                }
            )

        return insights
    
    def _generate_system_recommendations(self, module_results: Dict[str, Any], 
                                       system_test_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成系统改进建议"""
        recommendations = []
        
        # 基于系统性能生成建议
        performance_score = system_test_results.get("performance_score", 0.0)
        if performance_score < 0.8:
            recommendation = {
                "type": "performance_improvement",
                "title": "提升系统性能的建议",
                "description": "建议优化系统资源配置以提升处理性能",
                "priority": "high",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat(),
                "tags": ["performance", "optimization", "system"]
            }
            recommendations.append(recommendation)
        
        # 基于模块结果生成建议
        if len(module_results) > 5:
            recommendation = {
                "type": "scalability_improvement",
                "title": "系统扩展性优化建议",
                "description": "系统模块数量较多，建议优化模块间通信机制",
                "priority": "medium",
                "confidence": 0.75,
                "timestamp": datetime.now().isoformat(),
                "tags": ["scalability", "optimization", "system"]
            }
            recommendations.append(recommendation)

        failed_modules = self._get_failed_modules(module_results)
        if failed_modules:
            recommendations.append(
                {
                    "type": "failed_module_followup",
                    "title": "失败模块跟进建议",
                    "description": f"建议为失败模块建立专项回归清单：{', '.join(failed_modules)}",
                    "priority": "high",
                    "confidence": 0.9,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["followup", "reliability", "system"],
                }
            )
        
        return recommendations[: int(self.config.get("max_system_recommendations", 5))]

    def _get_failed_modules(self, module_results: Dict[str, Any]) -> List[str]:
        return [
            module_name
            for module_name, result in module_results.items()
            if str(result.get("status", "")).lower() == "failed" or "error" in result
        ]
    
    def _calculate_system_confidence_scores(self, module_results: Dict[str, Any], 
                                          system_test_results: Dict[str, Any]) -> Dict[str, float]:
        """计算系统置信度评分"""
        confidence_scores = {
            "module_confidence": 0.0,
            "system_confidence": system_test_results.get("reliability", 0.0),
            "overall": 0.0
        }
        
        # 计算模块平均置信度
        module_confidence_scores = []
        for result in module_results.values():
            if "confidence_scores" in result:
                confidence = result["confidence_scores"].get("overall", 0.0)
                module_confidence_scores.append(confidence)
        
        if module_confidence_scores:
            confidence_scores["module_confidence"] = np.mean(module_confidence_scores)
        
        # 计算综合置信度
        weights = {
            "module_confidence": 0.5,
            "system_confidence": 0.5
        }
        
        scores = []
        for metric, weight in weights.items():
            if metric in confidence_scores:
                scores.append(confidence_scores[metric] * weight)
        
        confidence_scores["overall"] = sum(scores) if scores else 0.0
        
        return confidence_scores
    
    def _update_performance_metrics(self, iteration_result: SystemIterationResult):
        """更新性能指标"""
        self.performance_metrics["total_iterations"] += 1
        if iteration_result.status == "completed":
            self.performance_metrics["successful_iterations"] += 1
        else:
            self.performance_metrics["failed_iterations"] += 1
        
        # 更新平均持续时间
        if self.performance_metrics["total_iterations"] > 0:
            self.performance_metrics["average_duration"] = (
                self.performance_metrics["total_processing_time"] + iteration_result.duration
            ) / self.performance_metrics["total_iterations"]
        
        # 更新总处理时间
        self.performance_metrics["total_processing_time"] += iteration_result.duration
        
        # 更新系统质量评分
        quality_score = iteration_result.quality_assessment.get("overall_quality", 0.0)
        if quality_score:
            self.performance_metrics["system_quality_score"] = (
                self.performance_metrics["system_quality_score"] * (self.performance_metrics["total_iterations"] - 1) + 
                quality_score
            ) / self.performance_metrics["total_iterations"]
    
    def get_system_performance_report(self) -> Dict[str, Any]:
        """获取系统性能报告"""
        if not self.system_iterations:
            return {"message": "还没有执行任何系统迭代"}
        
        completed_iterations = [i for i in self.system_iterations if i.status == "completed"]
        failed_iterations = [i for i in self.system_iterations if i.status == "failed"]
        
        # 计算平均性能指标
        execution_times = [i.duration for i in completed_iterations]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        quality_scores = [i.quality_assessment.get("overall_quality", 0.0) for i in completed_iterations]
        avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        confidence_scores = [i.confidence_scores.get("overall", 0.0) for i in completed_iterations]
        avg_confidence_score = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        return {
            "total_iterations": len(self.system_iterations),
            "successful_iterations": len(completed_iterations),
            "failed_iterations": len(failed_iterations),
            "average_execution_time": avg_execution_time,
            "average_quality_score": avg_quality_score,
            "average_confidence_score": avg_confidence_score,
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "latest_results": [self._serialize_system_iteration_result(i) for i in self.system_iterations[-3:]] if self.system_iterations else [],
            "failed_iterations_details": [self._serialize_system_iteration_result(i) for i in failed_iterations],
            "analysis_summary": self._build_system_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_system_report_metadata(),
        }

    def _build_system_report_metadata(self) -> Dict[str, Any]:
        runtime_metadata = self._build_runtime_metadata()
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "system_iteration_report",
            "latest_iteration_id": self.system_iterations[-1].iteration_id if self.system_iterations else "",
            "completed_phases": list(runtime_metadata.get("completed_phases", [])),
            "failed_phase": runtime_metadata.get("failed_phase"),
            "failed_operation_count": len(self.failed_operations),
            "final_status": runtime_metadata.get("final_status", "initialized"),
            "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        }

    def _serialize_system_iteration_result(self, iteration_result: SystemIterationResult) -> Dict[str, Any]:
        return {
            "iteration_id": iteration_result.iteration_id,
            "cycle_number": iteration_result.cycle_number,
            "status": iteration_result.status,
            "start_time": iteration_result.start_time,
            "end_time": iteration_result.end_time,
            "duration": iteration_result.duration,
            "module_results": self._serialize_value(iteration_result.module_results),
            "system_metrics": self._serialize_value(iteration_result.system_metrics),
            "system_insights": self._serialize_value(iteration_result.system_insights),
            "academic_insights": self._serialize_value(iteration_result.academic_insights),
            "recommendations": self._serialize_value(iteration_result.recommendations),
            "quality_assessment": self._serialize_value(iteration_result.quality_assessment),
            "confidence_scores": self._serialize_value(iteration_result.confidence_scores),
            "metadata": self._serialize_value(iteration_result.metadata),
        }

    def _build_system_export_payload(self, output_path: str) -> Dict[str, Any]:
        return {
            "report_metadata": {
                **self._build_system_report_metadata(),
                "output_path": output_path,
                "exported_file": os.path.basename(output_path),
            },
            "system_info": {
                "system_name": "中医古籍全自动研究系统",
                "version": "2.0.0",
                "generated_at": datetime.now().isoformat(),
                "performance_metrics": self._serialize_value(self.performance_metrics),
            },
            "system_report": self.get_system_performance_report(),
            "system_iterations": [self._serialize_system_iteration_result(i) for i in self.system_iterations],
            "failed_iterations": [self._serialize_system_iteration_result(i) for i in self.failed_iterations],
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "knowledge_graph": self._serialize_value(self.get_system_knowledge_graph()),
            "module_cycles": self._serialize_value({name: cycle.get_module_performance_report() for name, cycle in self.module_cycles.items()}),
        }
    
    def get_system_knowledge_graph(self) -> Dict[str, Any]:
        """获取系统知识图谱"""
        try:
            # 构建系统知识图谱数据
            graph_data = {
                "nodes": [
                    {
                        "id": f"iteration_{i}",
                        "data": {
                            "iteration": i,
                            "status": h.status,
                            "duration": h.duration,
                            "quality_score": h.quality_assessment.get("overall_quality", 0.0),
                            "confidence_score": h.confidence_scores.get("overall", 0.0)
                        }
                    } for i, h in enumerate(self.system_iterations)
                ],
                "edges": [
                    {
                        "source": f"iteration_{i}",
                        "target": f"iteration_{i+1}",
                        "relationship": "sequential"
                    } for i in range(len(self.system_iterations)-1)
                ] if len(self.system_iterations) > 1 else [],
                "graph_properties": {
                    "nodes_count": len(self.system_iterations),
                    "edges_count": len(self.system_iterations) - 1 if len(self.system_iterations) > 1 else 0,
                    "density": len(self.system_iterations) - 1 if len(self.system_iterations) > 1 else 0,
                    "connected_components": 1
                }
            }
            
            return graph_data
            
        except Exception as e:
            self.logger.error(f"系统知识图谱构建失败: {e}")
            return {"error": str(e)}
    
    def export_system_data(self, output_path: str) -> bool:
        """导出系统数据"""
        start_time = time.perf_counter()
        phase_entry = self._start_system_phase("export_system_data", {"output_path": output_path})
        try:
            system_data = self._build_system_export_payload(output_path)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(system_data, f, ensure_ascii=False, indent=2)
            self._complete_system_phase("export_system_data", phase_entry, start_time)
            
            self.logger.info(f"系统数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_system_phase("export_system_data", phase_entry, start_time, str(e))
            self.logger.error(f"系统数据导出失败: {e}")
            return False
    
    def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 清理数据结构
            self.system_iterations.clear()
            self.failed_iterations.clear()
            self.failed_operations.clear()
            self.knowledge_graph.clear()
            self.performance_metrics = {
                "total_iterations": 0,
                "successful_iterations": 0,
                "failed_iterations": 0,
                "average_duration": 0.0,
                "total_processing_time": 0.0,
                "system_quality_score": 0.0,
                "system_confidence_score": 0.0
            }
            
            # 清理模块循环
            for cycle in self.module_cycles.values():
                cycle.cleanup()
            self.module_cycles.clear()
            self.system_metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "cleaned",
                "last_completed_phase": None,
            }
            
            self.logger.info("系统级迭代循环资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"系统级迭代循环资源清理失败: {e}")
            return False
