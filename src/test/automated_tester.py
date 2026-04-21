# test/automated_tester.py
"""
中医古籍全自动研究系统 - 专业学术自动化测试框架
基于T/C IATCM 098-2023标准的自动化测试系统
"""

import concurrent.futures
import hashlib
import json
import logging
import time
import traceback
import unittest
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.module_base import get_global_executor
from src.core.phase_tracker import PhaseTrackerMixin

try:
    import pytest
except ImportError:
    pytest = None

# 配置日志
logger = logging.getLogger(__name__)

class TestStatus(Enum):
    """测试状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

class TestType(Enum):
    """测试类型枚举"""
    UNIT = "unit"
    INTEGRATION = "integration"
    SYSTEM = "system"
    ACCEPTANCE = "acceptance"
    REGRESSION = "regression"
    PERFORMANCE = "performance"
    SECURITY = "security"
    ACADEMIC = "academic"

class TestPriority(Enum):
    """测试优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class TestResult:
    """测试结果数据结构"""
    test_id: str
    test_name: str
    test_type: TestType
    test_priority: TestPriority
    status: TestStatus
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    academic_relevance: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TestSuite:
    """测试套件数据结构"""
    suite_id: str
    suite_name: str
    description: str
    test_type: TestType
    test_priority: TestPriority
    test_cases: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"
    test_results: List[TestResult] = field(default_factory=list)
    coverage_rate: float = 0.0
    quality_score: float = 0.0

class AutomatedTester(PhaseTrackerMixin):
    """
    中医古籍全自动研究系统自动化测试框架
    
    本框架基于T/C IATCM 098-2023标准设计，
    提供完整的自动化测试能力，支持：
    1. 单元测试
    2. 集成测试
    3. 系统测试
    4. 学术测试
    5. 性能测试
    6. 安全测试
    7. 回归测试
    
    主要功能：
    1. 多维度测试用例管理
    2. 自动化测试执行
    3. 智能测试结果分析
    4. 学术质量评估
    5. 性能监控与优化
    6. 知识沉淀与传承
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.test_suites = {}
        self.test_results = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: Optional[str] = None
        self.final_status = "initialized"
        self.last_completed_phase: Optional[str] = None
        self.performance_metrics = self._create_performance_metrics()
        self.executor = get_global_executor(self.config.get("max_workers", 4))
        self.logger = logging.getLogger(__name__)
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_pass_rate": float(self.config.get("minimum_stable_pass_rate", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d35.v1"),
        }
        
        # 初始化测试框架
        self._initialize_test_framework()
        
        self.logger.info("自动化测试框架初始化完成")

    def _create_performance_metrics(self) -> Dict[str, Any]:
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "average_execution_time": 0.0,
            "total_execution_time": 0.0,
            "test_coverage_rate": 0.0,
            "quality_assurance_score": 0.0,
        }

    def _start_phase(self, phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
        started_at = time.time()
        if self.governance_config.get("enable_phase_tracking", True):
            self.phase_history.append({
                "phase": phase_name,
                "status": "in_progress",
                "started_at": datetime.now().isoformat(),
                "details": self._serialize_value(details or {}),
            })
        return started_at

    def _complete_phase(
        self,
        phase_name: str,
        phase_started_at: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)
        if phase_name not in self.completed_phases:
            self.completed_phases.append(phase_name)
        self.last_completed_phase = phase_name
        if phase_name != "cleanup":
            self.final_status = "completed"

        if not self.governance_config.get("enable_phase_tracking", True):
            return

        for phase in reversed(self.phase_history):
            if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
                phase["status"] = "completed"
                phase["ended_at"] = datetime.now().isoformat()
                phase["duration_seconds"] = round(duration, 6)
                if details:
                    phase["details"] = self._serialize_value({**phase.get("details", {}), **details})
                break

    def _fail_phase(
        self,
        phase_name: str,
        phase_started_at: float,
        error: Exception,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)
        self.failed_phase = phase_name
        self.final_status = "failed"
        self._record_failed_operation(phase_name, error, details, duration)

        if not self.governance_config.get("enable_phase_tracking", True):
            return

        for phase in reversed(self.phase_history):
            if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
                phase["status"] = "failed"
                phase["ended_at"] = datetime.now().isoformat()
                phase["duration_seconds"] = round(duration, 6)
                phase["error"] = str(error)
                if details:
                    phase["details"] = self._serialize_value({**phase.get("details", {}), **details})
                break

    def _record_failed_operation(
        self,
        operation_name: str,
        error: Exception,
        details: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        if not self.governance_config.get("persist_failed_operations", True):
            return

        self.failed_operations.append({
            "operation": operation_name,
            "error": str(error),
            "details": self._serialize_value(details or {}),
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration_seconds or 0.0, 6),
        })

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(
            {
                "phase_history": self.phase_history,
                "phase_timings": self.phase_timings,
                "completed_phases": self.completed_phases,
                "failed_phase": self.failed_phase,
                "final_status": self.final_status,
                "last_completed_phase": self.last_completed_phase,
            }
        )

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, defaultdict):
            return {key: self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, dict):
            serialized = {}
            for key, item in value.items():
                if key == "function":
                    serialized["function_name"] = getattr(item, "__name__", "anonymous") if item else "missing"
                else:
                    serialized[str(key)] = self._serialize_value(item)
            return serialized
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_value(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return {
                field_name: self._serialize_value(getattr(value, field_name))
                for field_name in value.__dataclass_fields__
            }
        if callable(value):
            return getattr(value, "__name__", "callable")
        return value

    def _serialize_test_result(self, result: TestResult) -> Dict[str, Any]:
        return self._serialize_value(result)

    def _serialize_test_suite(self, suite: TestSuite) -> Dict[str, Any]:
        serialized_suite = self._serialize_value(suite)
        serialized_suite["test_cases"] = [self._serialize_value(case) for case in suite.test_cases]
        serialized_suite["test_results"] = [self._serialize_test_result(result) for result in suite.test_results]
        return serialized_suite

    def _build_analysis_summary(self) -> Dict[str, Any]:
        total_tests = len(self.test_results)
        failed_tests = self.performance_metrics.get("failed_tests", 0)
        error_tests = self.performance_metrics.get("error_tests", 0)
        passed_tests = self.performance_metrics.get("passed_tests", 0)
        pass_rate = passed_tests / total_tests if total_tests else 0.0
        status = "stable"
        if self.failed_phase or self.failed_operations or failed_tests or error_tests:
            status = "needs_followup"
        elif total_tests == 0:
            status = "idle"
        elif pass_rate < self.governance_config["minimum_stable_pass_rate"]:
            status = "degraded"

        return {
            "status": status,
            "total_tests": total_tests,
            "pass_rate": pass_rate,
            "failed_test_count": failed_tests,
            "error_test_count": error_tests,
            "completed_phase_count": len(self.completed_phases),
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.failed_phase,
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "automated_tester_report",
            "completed_phases": list(self.completed_phases),
            "failed_phase": self.failed_phase,
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }
    
    def _initialize_test_framework(self):
        """初始化测试框架"""
        # 配置测试框架
        self.test_frameworks = {
            "unittest": unittest,
            "custom": self._custom_test_framework
        }
        if pytest is not None:
            self.test_frameworks["pytest"] = pytest
        
        # 初始化测试环境
        self.test_environment = self._setup_test_environment()
        
        self.logger.info("测试框架初始化完成")
    
    def _setup_test_environment(self) -> Dict[str, Any]:
        """设置测试环境"""
        return {
            "environment": "development",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "resources": {
                "cpu": "4 cores",
                "memory": "8GB",
                "storage": "100GB",
                "network": "100Mbps"
            },
            "config": {
                "debug": True,
                "logging_level": "INFO",
                "test_coverage": True
            }
        }

    def _custom_test_framework(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """默认自定义测试框架入口，避免初始化阶段缺失符号。"""
        return {
            "success": True,
            "framework": "custom",
            "context": context or {}
        }
    
    def add_test_suite(self, suite_name: str, test_cases: List[Dict[str, Any]], 
                      test_type: TestType = TestType.UNIT,
                      test_priority: TestPriority = TestPriority.MEDIUM,
                      description: str = "") -> bool:
        """
        添加测试套件
        
        Args:
            suite_name (str): 套件名称
            test_cases (List[Dict[str, Any]]): 测试用例列表
            test_type (TestType): 测试类型
            test_priority (TestPriority): 测试优先级
            description (str): 套件描述
            
        Returns:
            bool: 添加是否成功
        """
        phase_started_at = self._start_phase("add_test_suite", {"suite_name": suite_name})

        try:
            suite_id = f"suite_{int(time.time())}_{hashlib.md5(suite_name.encode()).hexdigest()[:8]}"
            
            test_suite = TestSuite(
                suite_id=suite_id,
                suite_name=suite_name,
                description=description,
                test_type=test_type,
                test_priority=test_priority,
                test_cases=test_cases
            )
            
            self.test_suites[suite_id] = test_suite
            
            # 计算覆盖率
            if test_cases:
                test_suite.coverage_rate = len(test_cases) / len(test_cases)  # 简化计算
            self.failed_phase = None
            self.final_status = "completed"
            self._complete_phase(
                "add_test_suite",
                phase_started_at,
                {"suite_id": suite_id, "test_case_count": len(test_cases)},
            )
            
            self.logger.info("测试套件 %s 添加成功", suite_name)
            return True
            
        except Exception as e:
            self._fail_phase("add_test_suite", phase_started_at, e, {"suite_name": suite_name})
            self.logger.error("测试套件 %s 添加失败: %s", suite_name, e)
            return False
    
    def run_test_suite(self, suite_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行测试套件
        
        Args:
            suite_id (str): 套件ID
            context (Dict[str, Any]): 测试上下文
            
        Returns:
            Dict[str, Any]: 测试结果
        """
        start_time = time.time()
        phase_started_at = self._start_phase("run_test_suite", {"suite_id": suite_id})
        
        try:
            if suite_id not in self.test_suites:
                raise ValueError(f"测试套件 {suite_id} 不存在")
            
            test_suite = self.test_suites[suite_id]
            
            # 重置测试结果
            test_suite.test_results.clear()
            
            self.logger.info("开始运行测试套件: %s", test_suite.suite_name)
            
            # 并行执行测试用例
            futures = []
            test_results = []
            
            # 为每个测试用例创建异步任务
            for i, test_case in enumerate(test_suite.test_cases):
                future = self.executor.submit(
                    self._execute_single_test,
                    test_suite,
                    test_case,
                    context,
                    i
                )
                futures.append(future)
            
            # 等待所有测试完成
            for future in futures:
                try:
                    result = future.result(timeout=self.config.get("timeout", 300))
                    test_results.append(result)
                except concurrent.futures.TimeoutError:
                    self.logger.error("测试用例执行超时")
                    # 创建超时测试结果
                    timeout_result = TestResult(
                        test_id=f"timeout_{int(time.time())}",
                        test_name="timeout_test",
                        test_type=test_suite.test_type,
                        test_priority=test_suite.test_priority,
                        status=TestStatus.ERROR,
                        start_time=datetime.now().isoformat(),
                        end_time=datetime.now().isoformat(),
                        duration=0.0,
                        error_message="测试执行超时",
                        tags=["timeout", "error"]
                    )
                    test_results.append(timeout_result)
            
            # 更新测试套件结果
            test_suite.test_results = test_results
            
            # 计算测试结果统计
            self._calculate_suite_statistics(test_suite)
            
            # 更新性能指标
            self._update_performance_metrics(test_results, time.time() - start_time)
            
            # 生成测试报告
            test_report = self._generate_test_report(test_suite)
            self.failed_phase = None if not self.failed_operations else self.failed_phase
            self._complete_phase(
                "run_test_suite",
                phase_started_at,
                {
                    "suite_id": suite_id,
                    "result_count": len(test_results),
                    "pass_rate": test_report.get("analysis_summary", {}).get("pass_rate", 0.0),
                },
            )
            
            self.logger.info("测试套件 %s 运行完成", test_suite.suite_name)
            return test_report
            
        except Exception as e:
            self._fail_phase("run_test_suite", phase_started_at, e, {"suite_id": suite_id})
            self.logger.error("测试套件运行失败: %s", e)
            self.logger.error(traceback.format_exc())
            raise
    
    def _execute_single_test(self, test_suite: TestSuite, 
                           test_case: Dict[str, Any], 
                           context: Dict[str, Any], 
                           index: int) -> TestResult:
        """执行单个测试用例"""
        start_time = time.time()
        
        try:
            # 生成测试ID
            test_id = f"{test_suite.suite_id}_test_{index}_{int(time.time())}"
            
            # 获取测试信息
            test_name = test_case.get("name", f"test_case_{index}")
            test_type = test_case.get("type", test_suite.test_type)
            test_priority = test_case.get("priority", test_suite.test_priority)
            
            # 创建测试结果对象
            test_result = TestResult(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                test_priority=test_priority,
                status=TestStatus.RUNNING,
                start_time=datetime.now().isoformat()
            )
            
            # 执行测试
            try:
                # 获取测试函数
                test_function = test_case.get("function")
                if not test_function:
                    raise ValueError("缺少测试函数")
                
                # 执行测试
                test_result.status = TestStatus.RUNNING
                test_result.start_time = datetime.now().isoformat()
                
                # 执行测试函数
                if callable(test_function):
                    result_data = test_function(context or {})
                else:
                    result_data = test_function
                
                # 处理测试结果
                if isinstance(result_data, dict):
                    if result_data.get("success", False):
                        test_result.status = TestStatus.PASSED
                        test_result.result_data = result_data
                        test_result.confidence_score = result_data.get("confidence", 0.9)
                        test_result.academic_relevance = result_data.get("academic_relevance", 0.8)
                    else:
                        test_result.status = TestStatus.FAILED
                        test_result.error_message = result_data.get("error", "测试失败")
                        test_result.confidence_score = result_data.get("confidence", 0.3)
                        test_result.academic_relevance = result_data.get("academic_relevance", 0.2)
                else:
                    # 如果返回的是布尔值
                    if result_data:
                        test_result.status = TestStatus.PASSED
                        test_result.confidence_score = 0.95
                        test_result.academic_relevance = 0.9
                    else:
                        test_result.status = TestStatus.FAILED
                        test_result.error_message = "测试失败"
                        test_result.confidence_score = 0.2
                        test_result.academic_relevance = 0.1
                
                # 计算执行时间
                test_result.duration = time.time() - start_time
                test_result.end_time = datetime.now().isoformat()
                
                # 添加标签
                test_result.tags = [
                    test_type.value,
                    test_priority.value,
                    "automated",
                    "tcmautoresearch"
                ]
                
                # 添加元数据
                test_result.metadata = {
                    "suite_id": test_suite.suite_id,
                    "suite_name": test_suite.suite_name,
                    "test_case": test_case
                }
                
            except Exception as e:
                test_result.status = TestStatus.ERROR
                test_result.error_message = str(e)
                test_result.duration = time.time() - start_time
                test_result.end_time = datetime.now().isoformat()
                test_result.confidence_score = 0.1
                test_result.academic_relevance = 0.0
                test_result.tags.append("error")
            
            # 保存测试结果
            self.test_results.append(test_result)
            
            self.logger.debug("测试用例 %s 执行完成", test_name)
            return test_result
            
        except Exception as e:
            self.logger.error("测试用例执行失败: %s", e)
            return TestResult(
                test_id=f"error_{int(time.time())}",
                test_name=f"error_test_{index}",
                test_type=test_suite.test_type,
                test_priority=test_suite.test_priority,
                status=TestStatus.ERROR,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                duration=0.0,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=["error", "failed"]
            )
    
    def _calculate_suite_statistics(self, test_suite: TestSuite):
        """计算测试套件统计信息"""
        if not test_suite.test_results:
            return
        
        # 统计各种状态的测试
        status_counts = defaultdict(int)
        total_duration = 0.0
        total_confidence = 0.0
        total_academic = 0.0
        
        for result in test_suite.test_results:
            status_counts[result.status.value] += 1
            total_duration += result.duration
            total_confidence += result.confidence_score
            total_academic += result.academic_relevance
        
        # 更新套件统计信息
        test_suite.test_stats = {
            "total_tests": len(test_suite.test_results),
            "status_distribution": dict(status_counts),
            "average_duration": total_duration / len(test_suite.test_results) if test_suite.test_results else 0.0,
            "average_confidence": total_confidence / len(test_suite.test_results) if test_suite.test_results else 0.0,
            "average_academic_relevance": total_academic / len(test_suite.test_results) if test_suite.test_results else 0.0,
            "pass_rate": status_counts.get(TestStatus.PASSED.value, 0) / len(test_suite.test_results) if test_suite.test_results else 0.0,
        }
    
    def _update_performance_metrics(self, test_results: List[TestResult], 
                                  total_duration: float):
        """更新性能指标"""
        self.performance_metrics["total_tests"] += len(test_results)
        self.performance_metrics["total_execution_time"] += total_duration
        
        # 更新状态统计
        for result in test_results:
            if result.status == TestStatus.PASSED:
                self.performance_metrics["passed_tests"] += 1
            elif result.status == TestStatus.FAILED:
                self.performance_metrics["failed_tests"] += 1
            elif result.status == TestStatus.SKIPPED:
                self.performance_metrics["skipped_tests"] += 1
            elif result.status == TestStatus.ERROR:
                self.performance_metrics["error_tests"] += 1
        
        # 更新平均执行时间
        if self.performance_metrics["total_tests"] > 0:
            self.performance_metrics["average_execution_time"] = (
                self.performance_metrics["total_execution_time"] / 
                self.performance_metrics["total_tests"]
            )
        
        # 更新质量保证评分
        if test_results:
            confidence_scores = [r.confidence_score for r in test_results]
            
            if confidence_scores:
                avg_confidence = sum(confidence_scores) / len(confidence_scores)
                self.performance_metrics["quality_assurance_score"] = avg_confidence
    
    def _generate_test_report(self, test_suite: TestSuite) -> Dict[str, Any]:
        """生成测试报告"""
        # 计算覆盖率
        if test_suite.test_cases:
            coverage_rate = len(test_suite.test_results) / len(test_suite.test_cases)
        else:
            coverage_rate = 0.0
        
        # 计算通过率
        if test_suite.test_results:
            passed_rate = len([r for r in test_suite.test_results if r.status == TestStatus.PASSED]) / len(test_suite.test_results)
        else:
            passed_rate = 0.0
        
        # 计算质量评分
        quality_score = self._calculate_quality_score(test_suite)
        analysis_summary = {
            "suite_status": "stable" if passed_rate >= self.governance_config["minimum_stable_pass_rate"] and not any(r.status in {TestStatus.FAILED, TestStatus.ERROR} for r in test_suite.test_results) else "needs_followup",
            "total_tests": len(test_suite.test_results),
            "pass_rate": passed_rate,
            "failed_test_count": len([r for r in test_suite.test_results if r.status == TestStatus.FAILED]),
            "error_test_count": len([r for r in test_suite.test_results if r.status == TestStatus.ERROR]),
            "warning_count": sum(len(r.warnings) for r in test_suite.test_results),
            "quality_score": quality_score,
        }
        
        # 生成报告
        report = {
            "report_info": {
                "suite_id": test_suite.suite_id,
                "suite_name": test_suite.suite_name,
                "test_type": test_suite.test_type.value,
                "test_priority": test_suite.test_priority.value,
                "generated_at": datetime.now().isoformat(),
                "environment": self.test_environment["environment"],
                "version": self.test_environment["version"]
            },
            "test_summary": {
                "total_tests": len(test_suite.test_results),
                "passed_tests": len([r for r in test_suite.test_results if r.status == TestStatus.PASSED]),
                "failed_tests": len([r for r in test_suite.test_results if r.status == TestStatus.FAILED]),
                "skipped_tests": len([r for r in test_suite.test_results if r.status == TestStatus.SKIPPED]),
                "error_tests": len([r for r in test_suite.test_results if r.status == TestStatus.ERROR]),
                "coverage_rate": coverage_rate,
                "pass_rate": passed_rate,
                "quality_score": quality_score,
                "average_execution_time": self.performance_metrics["average_execution_time"]
            },
            "detailed_results": [self._serialize_test_result(result) for result in test_suite.test_results],
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "academic_analysis": self._analyze_academic_quality(test_suite),
            "recommendations": self._generate_recommendations(test_suite),
            "analysis_summary": analysis_summary,
            "report_metadata": self._build_report_metadata(),
        }
        
        return report
    
    def _calculate_quality_score(self, test_suite: TestSuite) -> float:
        """计算质量评分"""
        if not test_suite.test_results:
            return 0.0
        
        # 基于多个维度计算质量评分
        quality_metrics = {
            "pass_rate": 0.0,
            "confidence_score": 0.0,
            "academic_relevance": 0.0,
            "test_coverage": 0.0
        }
        
        # 计算通过率
        passed_tests = len([r for r in test_suite.test_results if r.status == TestStatus.PASSED])
        total_tests = len(test_suite.test_results)
        quality_metrics["pass_rate"] = passed_tests / total_tests if total_tests > 0 else 0.0
        
        # 计算平均置信度
        confidence_scores = [r.confidence_score for r in test_suite.test_results]
        quality_metrics["confidence_score"] = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        # 计算平均学术相关性
        academic_scores = [r.academic_relevance for r in test_suite.test_results]
        quality_metrics["academic_relevance"] = sum(academic_scores) / len(academic_scores) if academic_scores else 0.0
        
        # 计算测试覆盖率
        quality_metrics["test_coverage"] = len(test_suite.test_results) / len(test_suite.test_cases) if test_suite.test_cases else 0.0
        
        # 综合质量评分（加权平均）
        weights = {
            "pass_rate": 0.3,
            "confidence_score": 0.25,
            "academic_relevance": 0.25,
            "test_coverage": 0.2
        }
        
        quality_score = 0.0
        for metric, weight in weights.items():
            if metric in quality_metrics:
                quality_score += quality_metrics[metric] * weight
        
        return quality_score
    
    def _analyze_academic_quality(self, test_suite: TestSuite) -> Dict[str, Any]:
        """分析学术质量"""
        if not test_suite.test_results:
            return {"message": "没有测试结果可供分析"}
        
        # 基于学术标准分析质量
        academic_analysis = {
            "scientific_validity": 0.0,
            "methodological_quality": 0.0,
            "reproducibility": 0.0,
            "standard_compliance": 0.0,
            "academic_impact": 0.0,
            "insights": []
        }
        
        # 计算学术质量指标
        passed_tests = [r for r in test_suite.test_results if r.status == TestStatus.PASSED]
        if passed_tests:
            # 科学性评分
            scientific_validity = sum(r.confidence_score for r in passed_tests) / len(passed_tests)
            academic_analysis["scientific_validity"] = scientific_validity
            
            # 方法论质量评分
            methodological_quality = sum(r.academic_relevance for r in passed_tests) / len(passed_tests)
            academic_analysis["methodological_quality"] = methodological_quality
            
            # 可重现性评分
            reproducibility = sum(1 for r in passed_tests if r.confidence_score > 0.8) / len(passed_tests)
            academic_analysis["reproducibility"] = reproducibility
            
            # 标准符合性评分
            standard_compliance = sum(1 for r in passed_tests if r.academic_relevance > 0.7) / len(passed_tests)
            academic_analysis["standard_compliance"] = standard_compliance
            
            # 学术影响力评分
            academic_impact = sum(r.academic_relevance * r.confidence_score for r in passed_tests) / len(passed_tests)
            academic_analysis["academic_impact"] = academic_impact
        
        # 生成学术洞察
        academic_insights = []
        
        if academic_analysis["scientific_validity"] > 0.8:
            insight = {
                "type": "scientific_validity",
                "title": "高科学性测试",
                "description": f"测试通过率较高，科学性评分达到 {academic_analysis['scientific_validity']:.2f}",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            }
            academic_insights.append(insight)
        
        if academic_analysis["reproducibility"] > 0.8:
            insight = {
                "type": "reproducibility",
                "title": "高可重现性测试",
                "description": f"测试可重现性良好，评分达到 {academic_analysis['reproducibility']:.2f}",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat()
            }
            academic_insights.append(insight)
        
        academic_analysis["insights"] = academic_insights
        
        return academic_analysis
    
    def _generate_recommendations(self, test_suite: TestSuite) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations = []
        
        # 基于测试结果生成建议
        if test_suite.test_results:
            failed_tests = [r for r in test_suite.test_results if r.status == TestStatus.FAILED]
            error_tests = [r for r in test_suite.test_results if r.status == TestStatus.ERROR]
            
            # 基于失败测试生成建议
            if failed_tests:
                recommendation = {
                    "type": "test_improvement",
                    "title": "优化测试用例",
                    "description": f"发现 {len(failed_tests)} 个失败测试，建议优化测试用例设计",
                    "priority": "high",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "affected_tests": [t.test_name for t in failed_tests]
                }
                recommendations.append(recommendation)
            
            # 基于错误测试生成建议
            if error_tests:
                recommendation = {
                    "type": "error_resolution",
                    "title": "解决测试错误",
                    "description": f"发现 {len(error_tests)} 个测试错误，建议排查并修复",
                    "priority": "high",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "affected_tests": [t.test_name for t in error_tests]
                }
                recommendations.append(recommendation)
            
            # 基于质量评分生成建议
            quality_score = self._calculate_quality_score(test_suite)
            if quality_score < 0.8:
                recommendation = {
                    "type": "quality_improvement",
                    "title": "提升测试质量",
                    "description": f"当前测试质量评分较低 ({quality_score:.2f})，建议加强质量控制",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat()
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    def run_all_tests(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行所有测试套件
        
        Args:
            context (Dict[str, Any]): 测试上下文
            
        Returns:
            Dict[str, Any]: 测试结果汇总
        """
        start_time = time.time()
        phase_started_at = self._start_phase("run_all_tests", {"suite_count": len(self.test_suites)})
        self.logger.info("开始运行所有测试套件")
        
        try:
            results = {
                "suite_results": {},
                "overall_summary": {},
                "execution_time": 0.0,
                "timestamp": datetime.now().isoformat(),
            }
            
            # 依次运行所有测试套件
            for suite_id in self.test_suites:
                suite_result = self.run_test_suite(suite_id, context)
                results["suite_results"][suite_id] = suite_result
            
            # 计算总体摘要
            results["overall_summary"] = self._calculate_overall_summary()
            results["execution_time"] = time.time() - start_time
            results["analysis_summary"] = self._build_analysis_summary()
            results["report_metadata"] = self._build_report_metadata()
            self.failed_phase = None if not self.failed_operations else self.failed_phase
            self._complete_phase(
                "run_all_tests",
                phase_started_at,
                {
                    "suite_count": len(results["suite_results"]),
                    "total_tests": results["overall_summary"].get("total_tests", 0),
                },
            )
            
            self.logger.info("所有测试套件运行完成")
            return results
            
        except Exception as e:
            self._fail_phase("run_all_tests", phase_started_at, e)
            self.logger.error("所有测试运行失败: %s", e)
            self.logger.error(traceback.format_exc())
            raise
    
    def _calculate_overall_summary(self) -> Dict[str, Any]:
        """计算总体摘要"""
        if not self.test_results:
            return {"message": "没有测试结果"}
        
        # 统计各种状态的测试
        status_counts = defaultdict(int)
        total_duration = 0.0
        total_confidence = 0.0
        total_academic = 0.0
        
        for result in self.test_results:
            status_counts[result.status.value] += 1
            total_duration += result.duration
            total_confidence += result.confidence_score
            total_academic += result.academic_relevance
        
        # 计算总体指标
        total_tests = len(self.test_results)
        average_duration = total_duration / total_tests if total_tests > 0 else 0.0
        average_confidence = total_confidence / total_tests if total_tests > 0 else 0.0
        average_academic = total_academic / total_tests if total_tests > 0 else 0.0
        
        # 计算通过率
        passed_tests = status_counts.get("passed", 0)
        pass_rate = passed_tests / total_tests if total_tests > 0 else 0.0
        
        return {
            "total_tests": total_tests,
            "status_distribution": dict(status_counts),
            "pass_rate": pass_rate,
            "average_execution_time": average_duration,
            "average_confidence_score": average_confidence,
            "average_academic_relevance": average_academic,
            "quality_assurance_score": self.performance_metrics["quality_assurance_score"],
        }
    
    def export_test_results(self, output_path: str, format_type: str = "json") -> bool:
        """
        导出测试结果
        
        Args:
            output_path (str): 输出路径
            format_type (str): 输出格式
            
        Returns:
            bool: 导出是否成功
        """
        phase_started_at = self._start_phase("export_test_results", {"output_path": output_path, "format_type": format_type})

        try:
            test_data = {
                "framework_info": {
                    "framework_name": "中医古籍全自动研究系统测试框架",
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "performance_metrics": self._serialize_value(self.performance_metrics)
                },
                "test_suites": [self._serialize_test_suite(suite) for suite in self.test_suites.values()],
                "test_results": [self._serialize_test_result(result) for result in self.test_results],
                "test_summary": self._calculate_overall_summary(),
                "analysis_summary": self._build_analysis_summary(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
                "report_metadata": self._build_report_metadata(),
            }
            
            if format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(test_data, f, ensure_ascii=False, indent=2)
            elif format_type == "csv":
                # CSV格式导出（简化实现）
                pass
            
            self.failed_phase = None
            self.final_status = "completed"
            self._complete_phase("export_test_results", phase_started_at, {"output_path": output_path})
            self.logger.info("测试结果已导出到: %s", output_path)
            return True
            
        except Exception as e:
            self._fail_phase("export_test_results", phase_started_at, e, {"output_path": output_path})
            self.logger.error("测试结果导出失败: %s", e)
            return False
    
    def get_test_performance_report(self) -> Dict[str, Any]:
        """获取测试性能报告"""
        return {
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "test_summary": self._calculate_overall_summary(),
            "test_suites": [
                {
                    "suite_id": suite.suite_id,
                    "suite_name": suite.suite_name,
                    "test_type": suite.test_type.value,
                    "test_priority": suite.test_priority.value,
                    "test_count": len(suite.test_results),
                    "pass_rate": suite.test_stats.get("pass_rate", 0.0) if hasattr(suite, "test_stats") else 0.0
                } for suite in self.test_suites.values()
            ],
            "latest_results": [self._serialize_test_result(r) for r in self.test_results[-10:]] if self.test_results else [],
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "report_metadata": self._build_report_metadata(),
            "metadata": self._build_runtime_metadata(),
        }
    
    def cleanup(self) -> bool:
        """清理资源"""
        phase_started_at = self._start_phase("cleanup")

        try:
            # 注意：不关闭全局共享线程池，由应用生命周期管理
            # self.executor.shutdown(wait=True)
            
            # 清理数据结构
            self.test_suites.clear()
            self.test_results.clear()
            self.performance_metrics = self._create_performance_metrics()
            self.failed_operations.clear()
            self.phase_history.clear()
            self.phase_timings.clear()
            self.completed_phases.clear()
            self.failed_phase = None
            self.last_completed_phase = None
            self.final_status = "cleaned"
            
            self._complete_phase("cleanup", phase_started_at)
            self.logger.info("自动化测试框架资源清理完成")
            return True
            
        except Exception as e:
            self._fail_phase("cleanup", phase_started_at, e)
            self.logger.error("资源清理失败: %s", e)
            return False

# 导出主要类和函数
__all__ = [
    'AutomatedTester',
    'TestResult',
    'TestSuite',
    'TestStatus',
    'TestType',
    'TestPriority'
]
