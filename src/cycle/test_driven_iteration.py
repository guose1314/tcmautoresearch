# cycle/test_driven_iteration.py
"""
中医古籍全自动研究系统 - 专业学术测试驱动迭代
基于T/C IATCM 098-2023标准的测试驱动迭代管理
"""

import json
import logging
import os
import time
import traceback
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List

from src.core.phase_tracker import PhaseTrackerMixin

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """测试结果数据结构"""
    __test__ = False

    test_id: str
    test_name: str
    test_type: str
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    academic_relevance: float = 0.0

@dataclass
class TestDrivenIteration:
    """测试驱动迭代数据结构"""
    __test__ = False

    iteration_id: str
    cycle_number: int
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    test_results: List[TestResult] = field(default_factory=list)
    test_suite: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class TestDrivenIterationManager(PhaseTrackerMixin):
    """
    测试驱动迭代管理器
    
    本模块实现基于测试驱动的智能迭代优化，
    通过全面的测试验证确保每次迭代都符合学术标准，
    符合T/C IATCM 098-2023标准要求。
    
    主要功能：
    1. 测试套件管理与执行
    2. 自动化测试验证
    3. 学术质量评估
    4. 智能测试优化
    5. 知识沉淀与传承
    6. 持续改进机制
    """
    __test__ = False
    
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_pass_rate": float(self.config.get("minimum_stable_pass_rate", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d33.v1"),
        }
        self.test_suites = {}
        self.iteration_history: List[TestDrivenIteration] = []
        self.failed_iterations: List[TestDrivenIteration] = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.performance_metrics = {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "average_test_duration": 0.0,
            "total_test_execution_time": 0.0,
            "test_coverage_rate": 0.0,
            "quality_assurance_score": 0.0
        }
        self.iteration_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self.logger = logging.getLogger(__name__)
        
        # 初始化测试框架
        self._initialize_test_framework()
        
        self.logger.info("测试驱动迭代管理器初始化完成")

    def _initialize_phase_tracking(self, iteration: TestDrivenIteration) -> None:
        iteration.metadata["phase_history"] = []
        iteration.metadata["phase_timings"] = {}
        iteration.metadata["completed_phases"] = []
        iteration.metadata["failed_phase"] = None
        iteration.metadata["final_status"] = iteration.status
        iteration.metadata["last_completed_phase"] = None
        iteration.metadata["failed_operations"] = []

    def _record_failed_operation(
        self,
        container: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
    ) -> None:
        if not self.governance_config["persist_failed_operations"]:
            return
        container.append(
            {
                "operation": operation,
                "error": error,
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration, 6),
            }
        )

    def _start_manager_phase(self, phase_name: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self.governance_config["enable_phase_tracking"]:
            self.iteration_metadata["phase_history"].append(phase_entry)
        return phase_entry

    def _complete_manager_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        self.iteration_metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in self.iteration_metadata["completed_phases"]:
            self.iteration_metadata["completed_phases"].append(phase_name)
        self.iteration_metadata["last_completed_phase"] = phase_name
        self.iteration_metadata["final_status"] = "completed"

    def _fail_manager_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float, error: str) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        self.iteration_metadata["phase_timings"][phase_name] = round(duration, 6)
        self.iteration_metadata["failed_phase"] = phase_name
        self.iteration_metadata["final_status"] = "failed"
        self._record_failed_operation(self.failed_operations, phase_name, error, duration)

    def _execute_phase(
        self,
        iteration: TestDrivenIteration,
        phase_name: str,
        status: str,
        operation: Callable[[], Any],
    ) -> Any:
        phase_start = time.perf_counter()
        phase_entry: Dict[str, Any] = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
        }
        iteration.metadata["phase_history"].append(phase_entry)
        iteration.status = status

        try:
            result = operation()
        except Exception as exc:
            duration = time.perf_counter() - phase_start
            phase_entry["status"] = "failed"
            phase_entry["ended_at"] = datetime.now().isoformat()
            phase_entry["duration_seconds"] = round(duration, 6)
            phase_entry["error"] = str(exc)
            iteration.metadata["phase_timings"][phase_name] = round(duration, 6)
            iteration.metadata["failed_phase"] = phase_name
            iteration.metadata["final_status"] = "failed"
            self._record_failed_operation(iteration.metadata["failed_operations"], phase_name, str(exc), duration)
            self._record_failed_operation(self.failed_operations, phase_name, str(exc), duration)
            raise

        duration = time.perf_counter() - phase_start
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        iteration.metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in iteration.metadata["completed_phases"]:
            iteration.metadata["completed_phases"].append(phase_name)
        iteration.metadata["last_completed_phase"] = phase_name
        iteration.metadata["final_status"] = "completed"
        return result

    def _finalize_iteration(
        self,
        iteration: TestDrivenIteration,
        start_time: float,
        success: bool,
    ) -> None:
        iteration.status = "completed" if success else "failed"
        iteration.end_time = datetime.now().isoformat()
        iteration.duration = time.perf_counter() - start_time
        iteration.metadata["final_status"] = iteration.status

    def _build_analysis_summary(
        self,
        test_results: List[TestResult],
        validation_results: Dict[str, Any],
        academic_insights: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        confidence_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        failed_tests = [result for result in test_results if result.status == "failed"]
        pass_rate = float(validation_results.get("test_summary", {}).get("pass_rate", 0.0))
        overall_confidence = float(confidence_scores.get("overall", 0.0))
        minimum_pass_rate = self.governance_config["minimum_stable_pass_rate"]

        return {
            "total_tests": len(test_results),
            "failed_test_count": len(failed_tests),
            "pass_rate": pass_rate,
            "overall_confidence": overall_confidence,
            "academic_insight_count": len(academic_insights),
            "recommendation_count": len(recommendations),
            "iteration_status": "stable" if pass_rate >= minimum_pass_rate and not failed_tests else "needs_followup",
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.iteration_metadata.get("failed_phase"),
            "last_completed_phase": self.iteration_metadata.get("last_completed_phase"),
            "final_status": self.iteration_metadata.get("final_status", "initialized"),
        }

    def _serialize_test_result(self, test_result: TestResult) -> Dict[str, Any]:
        return self._serialize_value({
            "test_id": test_result.test_id,
            "test_name": test_result.test_name,
            "test_type": test_result.test_type,
            "status": test_result.status,
            "start_time": test_result.start_time,
            "end_time": test_result.end_time,
            "duration": test_result.duration,
            "result_data": test_result.result_data,
            "error_message": test_result.error_message,
            "warnings": test_result.warnings,
            "metrics": test_result.metrics,
            "confidence_score": test_result.confidence_score,
            "academic_relevance": test_result.academic_relevance,
        })

    def _serialize_iteration(self, iteration: TestDrivenIteration) -> Dict[str, Any]:
        return self._serialize_value({
            "iteration_id": iteration.iteration_id,
            "cycle_number": iteration.cycle_number,
            "status": iteration.status,
            "start_time": iteration.start_time,
            "end_time": iteration.end_time,
            "duration": iteration.duration,
            "test_results": [self._serialize_test_result(result) for result in iteration.test_results],
            "test_suite": iteration.test_suite,
            "validation_results": iteration.validation_results,
            "academic_insights": iteration.academic_insights,
            "recommendations": iteration.recommendations,
            "confidence_scores": iteration.confidence_scores,
            "metadata": iteration.metadata,
        })

    def _serialize_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        serialized_case = {key: value for key, value in test_case.items() if key != "function"}
        function_obj = test_case.get("function")
        serialized_case["function_name"] = getattr(function_obj, "__name__", "anonymous") if function_obj else "missing"
        return serialized_case

    def _serialize_test_suites(self) -> Dict[str, Any]:
        serialized_suites: Dict[str, Any] = {}
        for suite_name, suite_data in self.test_suites.items():
            serialized_suites[suite_name] = {
                **{key: value for key, value in suite_data.items() if key != "test_cases"},
                "test_cases": [self._serialize_test_case(test_case) for test_case in suite_data.get("test_cases", [])],
            }
        return serialized_suites

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "test_driven_iteration_report",
            "latest_iteration_id": self.iteration_history[-1].iteration_id if self.iteration_history else "",
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.iteration_metadata.get("final_status", "initialized"),
            "last_completed_phase": self.iteration_metadata.get("last_completed_phase"),
        }

    def _build_export_payload(self, output_path: str) -> Dict[str, Any]:
        return self._serialize_value({
            "report_metadata": {
                **self._build_report_metadata(),
                "output_path": output_path,
                "exported_file": os.path.basename(output_path),
            },
            "test_framework_info": {
                "framework_name": "测试驱动迭代框架",
                "version": "2.0.0",
                "generated_at": datetime.now().isoformat(),
                "performance_metrics": self.performance_metrics,
            },
            "test_suites": self._serialize_test_suites(),
            "iteration_history": [self._serialize_iteration(iteration) for iteration in self.iteration_history],
            "failed_iterations": [self._serialize_iteration(iteration) for iteration in self.failed_iterations],
            "failed_operations": self.failed_operations,
            "metadata": self.iteration_metadata,
            "test_performance_report": self.get_test_performance_report(),
        })
    
    def _initialize_test_framework(self):
        """初始化测试框架"""
        # 仅注册可用测试框架，避免在生产环境对 pytest 强依赖
        self.test_frameworks = {
            "unittest": unittest,
            "custom": self._custom_test_framework,
        }
        if pytest is not None:
            self.test_frameworks["pytest"] = pytest
        
        self.logger.info("测试框架初始化完成")
    
    def _custom_test_framework(self, test_function: Callable, context: Dict[str, Any]) -> Dict[str, Any]:
        """自定义测试框架"""
        start_time = time.time()
        try:
            # 执行测试函数
            result = test_function(context)
            
            duration = time.time() - start_time
            
            return {
                "success": True,
                "result": result,
                "duration": duration,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def add_test_suite(self, suite_name: str, test_cases: List[Dict[str, Any]], 
                      test_type: str = "automated") -> bool:
        """
        添加测试套件
        
        Args:
            suite_name (str): 套件名称
            test_cases (List[Dict[str, Any]]): 测试用例列表
            test_type (str): 测试类型
            
        Returns:
            bool: 添加是否成功
        """
        try:
            self.test_suites[suite_name] = {
                "suite_name": suite_name,
                "test_cases": test_cases,
                "test_type": test_type,
                "created_at": datetime.now().isoformat(),
                "test_count": len(test_cases)
            }
            
            self.logger.info(f"测试套件 {suite_name} 添加成功")
            return True
            
        except Exception as e:
            self.logger.error(f"测试套件 {suite_name} 添加失败: {e}")
            return False
    
    def run_test_driven_iteration(self, context: Dict[str, Any]) -> TestDrivenIteration:
        """
        执行测试驱动迭代
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            TestDrivenIteration: 测试驱动迭代结果
        """
        start_time = time.perf_counter()
        manager_phase_start = time.perf_counter()
        self.iteration_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "running",
            "last_completed_phase": None,
        }
        manager_phase_entry = self._start_manager_phase(
            "run_test_driven_iteration",
            {"context_keys": sorted(context.keys()), "suite_count": len(self.test_suites)},
        )
        
        iteration = TestDrivenIteration(
            iteration_id=f"test_iter_{int(time.time())}",
            cycle_number=len(self.iteration_history),
            status="pending",
            start_time=datetime.now().isoformat()
        )
        self._initialize_phase_tracking(iteration)
        
        try:
            test_results = self._execute_phase(
                iteration,
                "execute_tests",
                "executing_tests",
                lambda: self._execute_test_suites(context),
            )
            iteration.test_results = test_results
            
            validation_results = self._execute_phase(
                iteration,
                "validate_results",
                "validating_results",
                lambda: self._validate_test_results(test_results),
            )
            iteration.validation_results = validation_results

            self._analyze_and_update_iteration(iteration, test_results, validation_results)

            self._finalize_iteration(iteration, start_time, success=True)
            self._complete_manager_phase("run_test_driven_iteration", manager_phase_entry, manager_phase_start)
            self._sync_analysis_summary(iteration)
            self._update_performance_metrics(iteration)

            self._save_iteration_results(iteration)

            self.logger.info("测试驱动迭代完成")
            return iteration
            
        except Exception as e:
            self.iteration_metadata["failed_phase"] = iteration.metadata.get("failed_phase")
            self._fail_manager_phase("run_test_driven_iteration", manager_phase_entry, manager_phase_start, str(e))
            self._handle_iteration_failure(iteration, e, start_time)
            raise

    def _execute_test_suites(self, context: Dict[str, Any]) -> List[TestResult]:
        """执行测试套件"""
        self.logger.info("执行测试套件")
        test_results = []
        
        try:
            # 遍历所有测试套件
            for suite_name, suite_data in self.test_suites.items():
                test_cases = suite_data.get("test_cases", [])
                
                for i, test_case in enumerate(test_cases):
                    try:
                        test_result = self._execute_single_test(
                            suite_name, test_case, context, i
                        )
                        test_results.append(test_result)
                        
                    except Exception as e:
                        self.logger.error(f"测试用例执行失败: {e}")
                        test_result = TestResult(
                            test_id=f"{suite_name}_case_{i}",
                            test_name=test_case.get("name", f"test_case_{i}"),
                            test_type=test_case.get("type", "unknown"),
                            status="failed",
                            start_time=datetime.now().isoformat(),
                            error_message=str(e),
                            duration=0.0
                        )
                        test_results.append(test_result)
            
            self.logger.info("测试套件执行完成")
            return test_results
            
        except Exception as e:
            self.logger.error(f"测试套件执行失败: {e}")
            raise
    
    def _execute_single_test(self, suite_name: str, test_case: Dict[str, Any], 
                           context: Dict[str, Any], index: int) -> TestResult:
        """执行单个测试"""
        start_time = time.time()
        
        try:
            test_id = f"{suite_name}_case_{index}"
            test_name = test_case.get("name", f"test_case_{index}")
            test_type = test_case.get("type", "unknown")
            
            # 获取测试函数
            test_function = test_case.get("function")
            if not test_function:
                raise ValueError("缺少测试函数")
            
            # 执行测试
            framework = test_case.get("framework", "custom")
            if framework in self.test_frameworks:
                framework_func = self.test_frameworks[framework]
                test_result = framework_func(test_function, context)
            else:
                # 使用默认框架
                test_result = self._custom_test_framework(test_function, context)
            
            # 构造测试结果
            result = TestResult(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                status="passed" if test_result.get("success", False) else "failed",
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                duration=test_result.get("duration", 0.0),
                result_data=test_result,
                error_message=test_result.get("error", ""),
                metrics=test_case.get("metrics", {}),
                confidence_score=self._calculate_test_confidence(test_result),
                academic_relevance=self._calculate_academic_relevance(test_case)
            )
            
            self.logger.info(f"测试用例 {test_name} 执行完成")
            return result
            
        except Exception as e:
            self.logger.error(f"测试用例执行失败: {e}")
            return TestResult(
                test_id=f"{suite_name}_case_{index}",
                test_name=test_case.get("name", f"test_case_{index}"),
                test_type=test_case.get("type", "unknown"),
                status="failed",
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                duration=time.time() - start_time,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0
            )
    
    def _validate_test_results(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """验证测试结果"""
        self.logger.info("验证测试结果")
        start_time = time.time()
        
        try:
            # 统计测试结果
            passed_tests = [r for r in test_results if r.status == "passed"]
            failed_tests = [r for r in test_results if r.status == "failed"]
            
            # 计算测试覆盖率
            total_tests = len(test_results)
            passed_count = len(passed_tests)
            coverage_rate = passed_count / total_tests if total_tests > 0 else 0.0
            
            # 计算质量保证评分
            quality_assurance_score = self._calculate_quality_assurance_score(test_results)
            
            validation_results = {
                "total_tests": total_tests,
                "passed_tests": passed_count,
                "failed_tests": len(failed_tests),
                "coverage_rate": coverage_rate,
                "quality_assurance_score": quality_assurance_score,
                "validation_time": time.time() - start_time,
                "test_summary": {
                    "pass_rate": passed_count / total_tests if total_tests > 0 else 0.0,
                    "failure_rate": len(failed_tests) / total_tests if total_tests > 0 else 0.0
                }
            }
            
            self.logger.info("测试结果验证完成")
            return validation_results
            
        except Exception as e:
            self.logger.error(f"测试结果验证失败: {e}")
            raise
    
    def _analyze_test_results(
        self,
        test_results: List[TestResult],
        validation_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """分析测试结果"""
        self.logger.info("分析测试结果")
        start_time = time.time()

        try:
            academic_insights = self._generate_academic_insights(test_results, validation_results)
            recommendations = self._generate_recommendations(test_results, validation_results)
            confidence_scores = self._calculate_comprehensive_confidence(test_results, validation_results)

            analysis_results = {
                "academic_insights": academic_insights,
                "recommendations": recommendations,
                "confidence_scores": confidence_scores,
                "analysis_summary": self._build_analysis_summary(
                    test_results,
                    validation_results,
                    academic_insights,
                    recommendations,
                    confidence_scores,
                ),
                "analysis_time": time.time() - start_time,
            }

            self.logger.info("测试结果分析完成")
            return analysis_results

        except Exception as e:
            self.logger.error(f"测试结果分析失败: {e}")
            raise

    def _generate_academic_insights(
        self,
        test_results: List[TestResult],
        validation_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """生成学术洞察"""
        insights: List[Dict[str, Any]] = []
        pass_rate = validation_results.get("test_summary", {}).get("pass_rate", 0.0)

        if pass_rate >= 0.95:
            insights.append(
                {
                    "type": "test_quality",
                    "title": "高通过率测试洞察",
                    "description": f"测试通过率达到 {pass_rate:.2%}，表明系统质量优秀",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "test", "academic"],
                }
            )
        elif pass_rate >= 0.8:
            insights.append(
                {
                    "type": "test_moderate",
                    "title": "中等通过率测试洞察",
                    "description": f"测试通过率为 {pass_rate:.2%}，仍有改进空间",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "test", "academic"],
                }
            )

        failed_tests = [result for result in test_results if result.status == "failed"]
        if failed_tests:
            insights.append(
                {
                    "type": "test_failure",
                    "title": "测试失败分析洞察",
                    "description": f"发现 {len(failed_tests)} 个测试失败，需要重点关注",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["failure", "analysis", "academic"],
                    "failure_details": [
                        {
                            "test_name": result.test_name,
                            "error": result.error_message,
                            "confidence": result.confidence_score,
                        }
                        for result in failed_tests
                    ],
                }
            )

        return insights

    def _generate_recommendations(
        self,
        test_results: List[TestResult],
        validation_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations: List[Dict[str, Any]] = []
        coverage_rate = validation_results.get("coverage_rate", 0.0)
        failed_tests = [result for result in test_results if result.status == "failed"]
        quality_score = validation_results.get("quality_assurance_score", 0.0)

        if coverage_rate < 0.8:
            recommendations.append(
                {
                    "type": "test_coverage",
                    "title": "提升测试覆盖率的建议",
                    "description": "当前测试覆盖率较低，建议增加测试用例覆盖更多场景",
                    "priority": "high",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["test", "coverage", "improvement"],
                }
            )

        if failed_tests:
            recommendations.append(
                {
                    "type": "test_failure_fix",
                    "title": "修复测试失败问题的建议",
                    "description": "建议针对失败的测试用例进行专项修复和优化",
                    "priority": "high",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["failure", "fix", "improvement"],
                    "failed_test_count": len(failed_tests),
                }
            )

        if quality_score < 0.8:
            recommendations.append(
                {
                    "type": "quality_assurance",
                    "title": "提升质量保证水平的建议",
                    "description": "质量保证评分较低，建议加强质量控制机制",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "assurance", "improvement"],
                }
            )

        return recommendations

    def _analyze_and_update_iteration(
        self,
        iteration: TestDrivenIteration,
        test_results: List[TestResult],
        validation_results: Dict[str, Any],
    ) -> None:
        """分析测试结果并更新迭代状态"""
        analysis_results = self._execute_phase(
            iteration,
            "analyze_results",
            "analyzing_results",
            lambda: self._analyze_test_results(test_results, validation_results),
        )
        iteration.academic_insights = analysis_results.get("academic_insights", [])
        iteration.recommendations = analysis_results.get("recommendations", [])
        iteration.confidence_scores = analysis_results.get("confidence_scores", {})
        iteration.metadata["analysis_summary"] = analysis_results.get("analysis_summary", {})

    def _save_iteration_results(self, iteration: TestDrivenIteration) -> None:
        self.iteration_history.append(iteration)

    def _handle_iteration_failure(
        self,
        iteration: TestDrivenIteration,
        exception: Exception,
        start_time: float,
    ) -> None:
        self._finalize_iteration(iteration, start_time, success=False)
        iteration.validation_results = {"error": str(exception)}
        self._sync_analysis_summary(iteration)
        self.logger.error(f"测试驱动迭代失败: {exception}")
        self.logger.error(traceback.format_exc())
        self._update_performance_metrics(iteration)
        self._save_iteration_results(iteration)
        self.failed_iterations.append(iteration)

    def _sync_analysis_summary(self, iteration: TestDrivenIteration) -> None:
        analysis_summary = iteration.metadata.get("analysis_summary") or {}
        analysis_summary["failed_operation_count"] = len(self.failed_operations)
        analysis_summary["failed_phase"] = iteration.metadata.get("failed_phase") or self.iteration_metadata.get("failed_phase")
        analysis_summary["last_completed_phase"] = iteration.metadata.get("last_completed_phase")
        analysis_summary["final_status"] = iteration.status
        analysis_summary.setdefault(
            "iteration_status",
            "stable"
            if iteration.status == "completed"
            and float(iteration.validation_results.get("test_summary", {}).get("pass_rate", 0.0)) >= self.governance_config["minimum_stable_pass_rate"]
            else "needs_followup",
        )
        iteration.metadata["analysis_summary"] = analysis_summary
    
    def _calculate_comprehensive_confidence(self, test_results: List[TestResult], 
                                         validation_results: Dict[str, Any]) -> Dict[str, float]:
        """计算综合置信度"""
        confidence_scores = {
            "test_confidence": 0.0,
            "quality_confidence": 0.0,
            "academic_confidence": 0.0,
            "overall": 0.0
        }
        
        # 计算测试置信度
        if test_results:
            test_confidences = [r.confidence_score for r in test_results]
            confidence_scores["test_confidence"] = sum(test_confidences) / len(test_confidences) if test_confidences else 0.0
        
        # 计算质量置信度
        quality_score = validation_results.get("quality_assurance_score", 0.0)
        confidence_scores["quality_confidence"] = quality_score
        
        # 计算学术置信度
        academic_scores = [r.academic_relevance for r in test_results if hasattr(r, 'academic_relevance')]
        confidence_scores["academic_confidence"] = sum(academic_scores) / len(academic_scores) if academic_scores else 0.0
        
        # 计算综合置信度
        weights = {
            "test_confidence": 0.4,
            "quality_confidence": 0.3,
            "academic_confidence": 0.3
        }
        
        scores = []
        for metric, weight in weights.items():
            if metric in confidence_scores:
                scores.append(confidence_scores[metric] * weight)
        
        confidence_scores["overall"] = sum(scores) if scores else 0.0
        
        return confidence_scores
    
    def _calculate_test_confidence(self, test_result: Dict[str, Any]) -> float:
        """计算测试置信度"""
        # 基于测试结果的可靠性计算置信度
        if test_result.get("success", False):
            # 成功测试的置信度
            duration = test_result.get("duration", 0.0)
            # 基于执行时间计算置信度（时间越短通常越可靠）
            confidence = min(1.0, 1.0 - (duration / 10.0))  # 假设10秒为最长时间
            return confidence
        else:
            # 失败测试的置信度
            return 0.0
    
    def _calculate_academic_relevance(self, test_case: Dict[str, Any]) -> float:
        """计算学术相关性"""
        # 基于测试类型和标准相关性计算学术相关性
        test_type = test_case.get("type", "").lower()
        
        # 基于测试类型赋予权重
        type_weights = {
            "unit_test": 0.3,
            "integration_test": 0.5,
            "performance_test": 0.4,
            "regression_test": 0.6,
            "academic_test": 0.9,
            "validation_test": 0.8
        }
        
        if test_type in type_weights:
            return type_weights[test_type]

        return 0.5  # 默认相关性
    
    def _calculate_quality_assurance_score(self, test_results: List[TestResult]) -> float:
        """计算质量保证评分"""
        if not test_results:
            return 0.0
        
        # 基于通过率和置信度计算质量保证评分
        passed_tests = [r for r in test_results if r.status == "passed"]
        total_tests = len(test_results)
        
        if total_tests == 0:
            return 0.0
        
        # 通过率权重
        pass_rate = len(passed_tests) / total_tests
        
        # 平均置信度权重
        if passed_tests:
            avg_confidence = sum(r.confidence_score for r in passed_tests) / len(passed_tests)
        else:
            avg_confidence = 0.0
        
        # 综合质量评分（通过率占60%，置信度占40%）
        quality_score = (pass_rate * 0.6) + (avg_confidence * 0.4)
        
        return quality_score
    
    def _update_performance_metrics(self, iteration: TestDrivenIteration):
        """更新性能指标"""
        self.performance_metrics["total_iterations"] += 1
        if iteration.status == "completed":
            self.performance_metrics["successful_iterations"] += 1
        else:
            self.performance_metrics["failed_iterations"] += 1
        
        # 更新平均测试持续时间
        if self.performance_metrics["total_iterations"] > 0:
            self.performance_metrics["average_test_duration"] = (
                self.performance_metrics["total_test_execution_time"] + iteration.duration
            ) / self.performance_metrics["total_iterations"]
        
        # 更新总测试执行时间
        self.performance_metrics["total_test_execution_time"] += iteration.duration
    
    def get_test_performance_report(self) -> Dict[str, Any]:
        """获取测试性能报告"""
        if not self.iteration_history:
            return {"message": "还没有执行任何测试驱动迭代"}

        completed_iterations, failed_iterations = self._partition_iterations()
        avg_execution_time = self._average_execution_time(completed_iterations)
        avg_confidence_score = self._average_confidence_score(completed_iterations)
        analysis_summary = self._build_test_report_analysis_summary(
            len(failed_iterations),
            avg_confidence_score,
        )
        
        return {
            "total_iterations": len(self.iteration_history),
            "successful_iterations": len(completed_iterations),
            "failed_iterations": len(failed_iterations),
            "average_execution_time": avg_execution_time,
            "average_confidence_score": avg_confidence_score,
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "analysis_summary": analysis_summary,
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._serialize_value(self.iteration_metadata),
            "latest_results": [self._serialize_iteration(i) for i in self.iteration_history[-3:]] if self.iteration_history else [],
            "failed_iterations_details": [self._serialize_iteration(i) for i in failed_iterations],
            "report_metadata": self._build_report_metadata(),
        }

    def _partition_iterations(self) -> tuple[List[TestDrivenIteration], List[TestDrivenIteration]]:
        completed = [iteration for iteration in self.iteration_history if iteration.status == "completed"]
        failed = [iteration for iteration in self.iteration_history if iteration.status == "failed"]
        return completed, failed

    def _average_execution_time(self, completed_iterations: List[TestDrivenIteration]) -> float:
        if not completed_iterations:
            return 0.0
        return sum(iteration.duration for iteration in completed_iterations) / len(completed_iterations)

    def _average_confidence_score(self, completed_iterations: List[TestDrivenIteration]) -> float:
        confidence_scores = [
            iteration.confidence_scores.get("overall", 0.0)
            for iteration in completed_iterations
            if iteration.confidence_scores
        ]
        if not confidence_scores:
            return 0.0
        return sum(confidence_scores) / len(confidence_scores)

    def _build_test_report_analysis_summary(
        self,
        failed_iteration_count: int,
        avg_confidence_score: float,
    ) -> Dict[str, Any]:
        is_stable = (
            failed_iteration_count == 0
            and avg_confidence_score >= self.governance_config["minimum_stable_pass_rate"]
        )
        return {
            "status": "stable" if is_stable else "needs_followup",
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.iteration_metadata.get("failed_phase"),
            "last_completed_phase": self.iteration_metadata.get("last_completed_phase"),
            "final_status": self.iteration_metadata.get("final_status", "initialized"),
        }
    
    def export_test_data(self, output_path: str) -> bool:
        """导出测试数据"""
        try:
            test_data = self._build_export_payload(output_path)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"测试数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"测试数据导出失败: {e}")
            return False
    
    def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 清理数据结构
            self.test_suites.clear()
            self.iteration_history.clear()
            self.failed_iterations.clear()
            self.failed_operations.clear()
            self.iteration_metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "cleaned",
                "last_completed_phase": None,
            }
            self.performance_metrics = {
                "total_iterations": 0,
                "successful_iterations": 0,
                "failed_iterations": 0,
                "average_test_duration": 0.0,
                "total_test_execution_time": 0.0,
                "test_coverage_rate": 0.0,
                "quality_assurance_score": 0.0,
            }
            
            self.logger.info("测试驱动迭代管理器资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"测试驱动迭代管理器资源清理失败: {e}")
            return False
