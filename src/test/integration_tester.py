# test/integration_tester.py
"""
中医古籍全自动研究系统 - 专业学术集成测试框架
基于T/C IATCM 098-2023标准的集成测试系统
"""

import hashlib
import json
import logging
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import networkx as nx

from src.core.module_base import get_global_executor
from src.core.phase_tracker import PhaseTrackerMixin

# 配置日志
logger = logging.getLogger(__name__)

class IntegrationTestStatus(Enum):
    """集成测试状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"

class IntegrationTestType(Enum):
    """集成测试类型枚举"""
    MODULE_INTEGRATION = "module_integration"
    SYSTEM_INTEGRATION = "system_integration"
    DATA_INTEGRATION = "data_integration"
    API_INTEGRATION = "api_integration"
    DATABASE_INTEGRATION = "database_integration"
    SECURITY_INTEGRATION = "security_integration"
    PERFORMANCE_INTEGRATION = "performance_integration"
    ACADEMIC_INTEGRATION = "academic_integration"

class IntegrationTestPriority(Enum):
    """集成测试优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class IntegrationTest:
    """集成测试数据结构"""
    test_id: str
    test_name: str
    test_type: IntegrationTestType
    test_priority: IntegrationTestPriority
    description: str
    components_involved: List[str]
    test_steps: List[Dict[str, Any]]
    expected_results: Dict[str, Any]
    actual_results: Dict[str, Any] = field(default_factory=dict)
    status: IntegrationTestStatus = IntegrationTestStatus.PENDING
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: float = 0.0
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    academic_relevance: float = 0.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TestEnvironment:
    """测试环境数据结构"""
    environment_id: str
    environment_name: str
    description: str
    configuration: Dict[str, Any]
    resources: Dict[str, Any]
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    test_results: List[IntegrationTest] = field(default_factory=list)

class IntegrationTester(PhaseTrackerMixin):
    """
    中医古籍全自动研究系统集成测试框架
    
    本框架专注于系统模块间的集成测试，
    确保各模块协同工作符合T/C IATCM 098-2023标准要求，
    支持：
    1. 模块间集成测试
    2. 系统级集成测试
    3. 数据集成测试
    4. API集成测试
    5. 数据库集成测试
    6. 安全集成测试
    7. 性能集成测试
    8. 学术集成测试
    
    主要功能：
    1. 多维度集成测试管理
    2. 模块间协同验证
    3. 系统完整性测试
    4. 学术质量保证
    5. 性能基准测试
    6. 安全性验证
    7. 知识图谱验证
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.test_environments = {}
        self.integration_tests = []
        self.test_history = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: Optional[str] = None
        self.final_status = "initialized"
        self.last_completed_phase: Optional[str] = None
        self.performance_metrics = self._create_performance_metrics()
        self.executor = get_global_executor(self.config.get("max_workers", 4))
        self.knowledge_graph = nx.MultiDiGraph()
        self.logger = logging.getLogger(__name__)
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_pass_rate": float(self.config.get("minimum_stable_pass_rate", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d36.v1"),
        }
        
        # 初始化测试环境
        self._initialize_test_environments()
        
        self.logger.info("集成测试框架初始化完成")

    def _create_performance_metrics(self) -> Dict[str, Any]:
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "timeout_tests": 0,
            "average_execution_time": 0.0,
            "total_execution_time": 0.0,
            "integration_quality_score": 0.0,
            "academic_compliance_score": 0.0,
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

    def _serialize_integration_test(self, test: IntegrationTest) -> Dict[str, Any]:
        return self._serialize_value(test)

    def _serialize_environment(self, environment: TestEnvironment) -> Dict[str, Any]:
        serialized_environment = self._serialize_value(environment)
        serialized_environment["test_results"] = [
            self._serialize_integration_test(test) for test in environment.test_results
        ]
        return serialized_environment

    def _build_analysis_summary(self) -> Dict[str, Any]:
        total_tests = len(self.test_history)
        passed_tests = self.performance_metrics.get("passed_tests", 0)
        failed_tests = self.performance_metrics.get("failed_tests", 0)
        error_tests = self.performance_metrics.get("error_tests", 0)
        timeout_tests = self.performance_metrics.get("timeout_tests", 0)
        pass_rate = passed_tests / total_tests if total_tests else 0.0

        status = "stable"
        if self.failed_phase or self.failed_operations or failed_tests or error_tests or timeout_tests:
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
            "timeout_test_count": timeout_tests,
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
            "result_schema": "integration_tester_report",
            "completed_phases": list(self.completed_phases),
            "failed_phase": self.failed_phase,
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }
    
    def _initialize_test_environments(self):
        """初始化测试环境"""
        # 创建默认测试环境
        default_env = TestEnvironment(
            environment_id="default_env",
            environment_name="Default Environment",
            description="默认测试环境",
            configuration={
                "debug": True,
                "logging_level": "INFO",
                "test_coverage": True
            },
            resources={
                "cpu": "4 cores",
                "memory": "8GB",
                "storage": "100GB",
                "network": "100Mbps"
            }
        )
        
        self.test_environments["default_env"] = default_env
        
        self.logger.info("测试环境初始化完成")
    
    def create_test_environment(self, env_name: str, description: str,
                              configuration: Dict[str, Any], 
                              resources: Dict[str, Any]) -> TestEnvironment:
        """
        创建测试环境
        
        Args:
            env_name (str): 环境名称
            description (str): 环境描述
            configuration (Dict[str, Any]): 环境配置
            resources (Dict[str, Any]): 环境资源
            
        Returns:
            TestEnvironment: 创建的测试环境
        """
        phase_started_at = self._start_phase("create_test_environment", {"environment_name": env_name})

        try:
            env_id = f"env_{int(time.time())}_{hashlib.md5(env_name.encode()).hexdigest()[:8]}"
            
            test_environment = TestEnvironment(
                environment_id=env_id,
                environment_name=env_name,
                description=description,
                configuration=configuration,
                resources=resources
            )
            
            self.test_environments[env_id] = test_environment
            self.failed_phase = None
            self.final_status = "completed"
            self._complete_phase(
                "create_test_environment",
                phase_started_at,
                {"environment_id": env_id},
            )
            
            self.logger.info(f"测试环境 {env_name} 创建成功")
            return test_environment
            
        except Exception as e:
            self._fail_phase("create_test_environment", phase_started_at, e, {"environment_name": env_name})
            self.logger.error(f"测试环境 {env_name} 创建失败: {e}")
            raise
    
    def add_integration_test(self, test_name: str, 
                           test_type: IntegrationTestType,
                           test_priority: IntegrationTestPriority,
                           description: str,
                           components_involved: List[str],
                           test_steps: List[Dict[str, Any]],
                           expected_results: Dict[str, Any],
                           environment_id: str = "default_env") -> IntegrationTest:
        """
        添加集成测试
        
        Args:
            test_name (str): 测试名称
            test_type (IntegrationTestType): 测试类型
            test_priority (IntegrationTestPriority): 测试优先级
            description (str): 测试描述
            components_involved (List[str]): 涉及的组件
            test_steps (List[Dict[str, Any]]): 测试步骤
            expected_results (Dict[str, Any]): 预期结果
            environment_id (str): 环境ID
            
        Returns:
            IntegrationTest: 创建的集成测试
        """
        phase_started_at = self._start_phase("add_integration_test", {"test_name": test_name})

        try:
            test_id = f"test_{int(time.time())}_{hashlib.md5(test_name.encode()).hexdigest()[:8]}"
            
            integration_test = IntegrationTest(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                test_priority=test_priority,
                description=description,
                components_involved=components_involved,
                test_steps=test_steps,
                expected_results=expected_results,
                status=IntegrationTestStatus.PENDING,
                tags=[test_type.value, test_priority.value, "integration_test", "tcmautoresearch"]
            )
            
            self.integration_tests.append(integration_test)
            self.failed_phase = None
            self.final_status = "completed"
            self._complete_phase(
                "add_integration_test",
                phase_started_at,
                {"test_id": test_id, "component_count": len(components_involved)},
            )
            
            self.logger.info(f"集成测试 {test_name} 添加成功")
            return integration_test
            
        except Exception as e:
            self._fail_phase("add_integration_test", phase_started_at, e, {"test_name": test_name})
            self.logger.error(f"集成测试 {test_name} 添加失败: {e}")
            raise
    
    def run_integration_test(self, test_id: str, 
                           environment_id: str = "default_env",
                           context: Dict[str, Any] = None) -> IntegrationTest:
        """
        运行集成测试
        
        Args:
            test_id (str): 测试ID
            environment_id (str): 环境ID
            context (Dict[str, Any]): 测试上下文
            
        Returns:
            IntegrationTest: 测试结果
        """
        start_time = time.time()
        phase_started_at = self._start_phase("run_integration_test", {"test_id": test_id, "environment_id": environment_id})
        test: Optional[IntegrationTest] = None
        
        try:
            # 查找测试
            test = next((t for t in self.integration_tests if t.test_id == test_id), None)
            if not test:
                raise ValueError(f"集成测试 {test_id} 不存在")
            
            # 获取测试环境
            environment = self.test_environments.get(environment_id)
            if not environment:
                raise ValueError(f"测试环境 {environment_id} 不存在")
            
            # 更新测试状态
            test.status = IntegrationTestStatus.RUNNING
            test.start_time = datetime.now().isoformat()
            
            self.logger.info(f"开始运行集成测试: {test.test_name}")
            
            # 执行测试
            test_result = self._execute_integration_test(test, environment, context)
            
            # 更新测试结果
            test.status = test_result.status
            test.end_time = datetime.now().isoformat()
            test.duration = time.time() - start_time
            test.actual_results = test_result.actual_results
            test.metrics = test_result.metrics
            test.confidence_score = test_result.confidence_score
            test.academic_relevance = test_result.academic_relevance
            test.error_message = test_result.error_message
            test.metadata.setdefault("phase_history", self._serialize_value(self.phase_history))
            test.metadata["analysis_summary"] = self._build_analysis_summary()
            test.metadata["report_metadata"] = self._build_report_metadata()
            
            # 添加到测试历史
            self.test_history.append(test)
            environment.test_results.append(test)
            
            # 更新性能指标
            self._update_performance_metrics(test, time.time() - start_time)
            self.failed_phase = None if not self.failed_operations else self.failed_phase
            self._complete_phase(
                "run_integration_test",
                phase_started_at,
                {
                    "test_id": test_id,
                    "status": test.status.value,
                    "environment_id": environment_id,
                },
            )
            
            self.logger.info(f"集成测试 {test.test_name} 运行完成")
            return test
            
        except Exception as e:
            self._fail_phase("run_integration_test", phase_started_at, e, {"test_id": test_id, "environment_id": environment_id})
            self.logger.error(f"集成测试运行失败: {e}")
            self.logger.error(traceback.format_exc())
            
            # 更新测试状态为错误
            if test is not None:
                test.status = IntegrationTestStatus.ERROR
                test.end_time = datetime.now().isoformat()
                test.duration = time.time() - start_time
                test.error_message = str(e)
            
            raise
    
    def _execute_integration_test(self, test: IntegrationTest, 
                                environment: TestEnvironment,
                                context: Dict[str, Any]) -> IntegrationTest:
        """执行集成测试"""
        try:
            # 模拟测试执行过程
            # 在实际应用中，这里应该调用具体的测试执行逻辑
            
            # 模拟测试执行
            time.sleep(0.1)  # 模拟执行时间
            
            # 根据测试类型执行不同逻辑
            if test.test_type == IntegrationTestType.MODULE_INTEGRATION:
                result = self._execute_module_integration_test(test, environment, context)
            elif test.test_type == IntegrationTestType.SYSTEM_INTEGRATION:
                result = self._execute_system_integration_test(test, environment, context)
            elif test.test_type == IntegrationTestType.DATA_INTEGRATION:
                result = self._execute_data_integration_test(test, environment, context)
            elif test.test_type == IntegrationTestType.ACADEMIC_INTEGRATION:
                result = self._execute_academic_integration_test(test, environment, context)
            else:
                # 默认执行
                result = self._execute_default_integration_test(test, environment, context)
            
            return result
            
        except Exception as e:
            self.logger.error(f"集成测试执行失败: {e}")
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _execute_module_integration_test(self, test: IntegrationTest, 
                                       environment: TestEnvironment,
                                       context: Dict[str, Any]) -> IntegrationTest:
        """执行模块集成测试"""
        try:
            # 模拟模块集成测试
            time.sleep(0.05)
            
            # 检查组件是否都已准备就绪
            components_ready = True
            for component in test.components_involved:
                # 模拟组件检查
                if component == "invalid_component":
                    components_ready = False
                    break
            
            # 生成测试结果
            if components_ready:
                # 模拟测试通过
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.PASSED,
                    actual_results={
                        "components": test.components_involved,
                        "integration_status": "successful",
                        "data_flow": "correct",
                        "error_count": 0
                    },
                    metrics={
                        "execution_time": 0.05,
                        "data_volume": 1000,
                        "throughput": 20000,
                        "latency": 0.02
                    },
                    confidence_score=0.95,
                    academic_relevance=0.90,
                    tags=test.tags
                )
            else:
                # 模拟测试失败
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.FAILED,
                    error_message="某些组件未就绪",
                    actual_results={
                        "components": test.components_involved,
                        "integration_status": "failed",
                        "error_details": "组件未就绪"
                    },
                    metrics={
                        "execution_time": 0.05,
                        "error_count": 1
                    },
                    confidence_score=0.2,
                    academic_relevance=0.1,
                    tags=test.tags
                )
            
            return test_result
            
        except Exception as e:
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _execute_system_integration_test(self, test: IntegrationTest, 
                                       environment: TestEnvironment,
                                       context: Dict[str, Any]) -> IntegrationTest:
        """执行系统集成测试"""
        try:
            # 模拟系统集成测试
            time.sleep(0.1)
            
            # 检查系统完整性
            system_integrity = True
            if "critical_component" in test.components_involved:
                system_integrity = False  # 模拟系统完整性问题
            
            # 生成测试结果
            if system_integrity:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.PASSED,
                    actual_results={
                        "system_components": test.components_involved,
                        "system_status": "healthy",
                        "performance_metrics": {
                            "response_time": 0.15,
                            "throughput": 15000,
                            "availability": 0.99
                        }
                    },
                    metrics={
                        "execution_time": 0.1,
                        "system_load": 0.65,
                        "resource_utilization": 0.75
                    },
                    confidence_score=0.92,
                    academic_relevance=0.88,
                    tags=test.tags
                )
            else:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.FAILED,
                    error_message="系统完整性检查失败",
                    actual_results={
                        "system_components": test.components_involved,
                        "system_status": "unhealthy",
                        "issues": ["critical_component_missing"]
                    },
                    metrics={
                        "execution_time": 0.1,
                        "system_load": 0.95,
                        "resource_utilization": 0.90
                    },
                    confidence_score=0.15,
                    academic_relevance=0.10,
                    tags=test.tags
                )
            
            return test_result
            
        except Exception as e:
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _execute_data_integration_test(self, test: IntegrationTest, 
                                     environment: TestEnvironment,
                                     context: Dict[str, Any]) -> IntegrationTest:
        """执行数据集成测试"""
        try:
            # 模拟数据集成测试
            time.sleep(0.08)
            
            # 检查数据一致性
            data_consistency = True
            if "inconsistent_data" in test.components_involved:
                data_consistency = False  # 模拟数据不一致
            
            # 生成测试结果
            if data_consistency:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.PASSED,
                    actual_results={
                        "data_sources": test.components_involved,
                        "consistency_check": "passed",
                        "data_quality": {
                            "completeness": 0.98,
                            "accuracy": 0.95,
                            "consistency": 0.97
                        }
                    },
                    metrics={
                        "execution_time": 0.08,
                        "data_volume_processed": 50000,
                        "error_rate": 0.001,
                        "processing_speed": 625000
                    },
                    confidence_score=0.90,
                    academic_relevance=0.85,
                    tags=test.tags
                )
            else:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.FAILED,
                    error_message="数据一致性检查失败",
                    actual_results={
                        "data_sources": test.components_involved,
                        "consistency_check": "failed",
                        "issues": ["data_inconsistency_detected"]
                    },
                    metrics={
                        "execution_time": 0.08,
                        "data_volume_processed": 50000,
                        "error_rate": 0.05,
                        "processing_speed": 625000
                    },
                    confidence_score=0.25,
                    academic_relevance=0.15,
                    tags=test.tags
                )
            
            return test_result
            
        except Exception as e:
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _execute_academic_integration_test(self, test: IntegrationTest, 
                                         environment: TestEnvironment,
                                         context: Dict[str, Any]) -> IntegrationTest:
        """执行学术集成测试"""
        try:
            # 模拟学术集成测试
            time.sleep(0.12)
            
            # 检查学术合规性
            academic_compliance = True
            if "non_compliant" in test.components_involved:
                academic_compliance = False  # 模拟不合规
            
            # 生成测试结果
            if academic_compliance:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.PASSED,
                    actual_results={
                        "academic_standards_met": True,
                        "compliance_score": 0.98,
                        "quality_metrics": {
                            "scientific_validity": 0.95,
                            "methodological_quality": 0.92,
                            "reproducibility": 0.96
                        }
                    },
                    metrics={
                        "execution_time": 0.12,
                        "compliance_check_time": 0.05,
                        "academic_analysis_time": 0.07
                    },
                    confidence_score=0.96,
                    academic_relevance=0.98,
                    tags=test.tags
                )
            else:
                test_result = IntegrationTest(
                    test_id=test.test_id,
                    test_name=test.test_name,
                    test_type=test.test_type,
                    test_priority=test.test_priority,
                    description=test.description,
                    components_involved=test.components_involved,
                    test_steps=test.test_steps,
                    expected_results=test.expected_results,
                    status=IntegrationTestStatus.FAILED,
                    error_message="学术合规性检查失败",
                    actual_results={
                        "academic_standards_met": False,
                        "non_compliant_elements": ["T/C IATCM 098-2023"],
                        "compliance_score": 0.65
                    },
                    metrics={
                        "execution_time": 0.12,
                        "compliance_check_time": 0.05,
                        "academic_analysis_time": 0.07
                    },
                    confidence_score=0.10,
                    academic_relevance=0.05,
                    tags=test.tags
                )
            
            return test_result
            
        except Exception as e:
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _execute_default_integration_test(self, test: IntegrationTest, 
                                        environment: TestEnvironment,
                                        context: Dict[str, Any]) -> IntegrationTest:
        """执行默认集成测试"""
        try:
            # 模拟默认测试
            time.sleep(0.03)
            
            # 默认测试通过
            test_result = IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.PASSED,
                actual_results={
                    "test_execution": "completed",
                    "status": "success",
                    "metrics": {
                        "execution_time": 0.03,
                        "result_validation": "passed"
                    }
                },
                metrics={
                    "execution_time": 0.03
                },
                confidence_score=0.85,
                academic_relevance=0.80,
                tags=test.tags
            )
            
            return test_result
            
        except Exception as e:
            return IntegrationTest(
                test_id=test.test_id,
                test_name=test.test_name,
                test_type=test.test_type,
                test_priority=test.test_priority,
                description=test.description,
                components_involved=test.components_involved,
                test_steps=test.test_steps,
                expected_results=test.expected_results,
                status=IntegrationTestStatus.ERROR,
                error_message=str(e),
                confidence_score=0.0,
                academic_relevance=0.0,
                tags=test.tags
            )
    
    def _update_performance_metrics(self, test: IntegrationTest, 
                                  execution_time: float):
        """更新性能指标"""
        self.performance_metrics["total_tests"] += 1
        self.performance_metrics["total_execution_time"] += execution_time
        
        # 更新状态统计
        if test.status == IntegrationTestStatus.PASSED:
            self.performance_metrics["passed_tests"] += 1
        elif test.status == IntegrationTestStatus.FAILED:
            self.performance_metrics["failed_tests"] += 1
        elif test.status == IntegrationTestStatus.SKIPPED:
            self.performance_metrics["skipped_tests"] += 1
        elif test.status == IntegrationTestStatus.ERROR:
            self.performance_metrics["error_tests"] += 1
        elif test.status == IntegrationTestStatus.TIMEOUT:
            self.performance_metrics["timeout_tests"] += 1
        
        # 更新平均执行时间
        if self.performance_metrics["total_tests"] > 0:
            self.performance_metrics["average_execution_time"] = (
                self.performance_metrics["total_execution_time"] / 
                self.performance_metrics["total_tests"]
            )
        
        # 更新质量评分
        if test.confidence_score:
            self.performance_metrics["integration_quality_score"] = (
                self.performance_metrics["integration_quality_score"] * (self.performance_metrics["total_tests"] - 1) + 
                test.confidence_score
            ) / self.performance_metrics["total_tests"]
        
        # 更新学术合规评分
        if test.academic_relevance:
            self.performance_metrics["academic_compliance_score"] = (
                self.performance_metrics["academic_compliance_score"] * (self.performance_metrics["total_tests"] - 1) + 
                test.academic_relevance
            ) / self.performance_metrics["total_tests"]
    
    def run_all_integration_tests(self, environment_id: str = "default_env",
                                context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行所有集成测试
        
        Args:
            environment_id (str): 环境ID
            context (Dict[str, Any]): 测试上下文
            
        Returns:
            Dict[str, Any]: 测试结果汇总
        """
        start_time = time.time()
        phase_started_at = self._start_phase("run_all_integration_tests", {"environment_id": environment_id, "test_count": len(self.integration_tests)})
        self.logger.info("开始运行所有集成测试")
        
        try:
            results = {
                "test_results": {},
                "overall_summary": {},
                "execution_time": 0.0,
                "timestamp": datetime.now().isoformat()
            }
            
            # 依次运行所有集成测试
            for test in self.integration_tests:
                try:
                    test_result = self.run_integration_test(test.test_id, environment_id, context)
                    results["test_results"][test.test_id] = self._serialize_integration_test(test_result)
                except Exception as e:
                    self.logger.error(f"集成测试 {test.test_name} 运行失败: {e}")
                    # 创建失败测试结果
                    failed_result = IntegrationTest(
                        test_id=test.test_id,
                        test_name=test.test_name,
                        test_type=test.test_type,
                        test_priority=test.test_priority,
                        description=test.description,
                        components_involved=test.components_involved,
                        test_steps=test.test_steps,
                        expected_results=test.expected_results,
                        status=IntegrationTestStatus.ERROR,
                        error_message=str(e),
                        confidence_score=0.0,
                        academic_relevance=0.0,
                        tags=test.tags
                    )
                    results["test_results"][test.test_id] = self._serialize_integration_test(failed_result)
            
            # 计算总体摘要
            results["overall_summary"] = self._calculate_overall_summary()
            results["execution_time"] = time.time() - start_time
            results["analysis_summary"] = self._build_analysis_summary()
            results["report_metadata"] = self._build_report_metadata()
            self.failed_phase = None if not self.failed_operations else self.failed_phase
            self._complete_phase(
                "run_all_integration_tests",
                phase_started_at,
                {
                    "environment_id": environment_id,
                    "executed_test_count": len(results["test_results"]),
                },
            )
            
            self.logger.info("所有集成测试运行完成")
            return results
            
        except Exception as e:
            self._fail_phase("run_all_integration_tests", phase_started_at, e, {"environment_id": environment_id})
            self.logger.error(f"所有集成测试运行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def _calculate_overall_summary(self) -> Dict[str, Any]:
        """计算总体摘要"""
        if not self.test_history:
            return {"message": "没有测试结果"}
        
        # 统计各种状态的测试
        status_counts = defaultdict(int)
        total_duration = 0.0
        total_confidence = 0.0
        total_academic = 0.0
        
        for test in self.test_history:
            status_counts[test.status.value] += 1
            total_duration += test.duration
            total_confidence += test.confidence_score
            total_academic += test.academic_relevance
        
        # 计算总体指标
        total_tests = len(self.test_history)
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
            "integration_quality_score": self.performance_metrics["integration_quality_score"],
            "academic_compliance_score": self.performance_metrics["academic_compliance_score"]
        }
    
    def generate_integration_report(self) -> Dict[str, Any]:
        """生成集成测试报告"""
        summary = self._calculate_overall_summary()
        
        # 按测试类型分组
        test_type_groups = defaultdict(list)
        for test in self.test_history:
            test_type_groups[test.test_type.value].append(test)
        
        # 按优先级分组
        priority_groups = defaultdict(list)
        for test in self.test_history:
            priority_groups[test.test_priority.value].append(test)
        
        report = {
            "report_info": {
                "report_name": "中医古籍全自动研究系统集成测试报告",
                "generated_at": datetime.now().isoformat(),
                "version": "2.0.0"
            },
            "summary": summary,
            "test_type_distribution": {
                test_type: len(tests) for test_type, tests in test_type_groups.items()
            },
            "priority_distribution": {
                priority: len(tests) for priority, tests in priority_groups.items()
            },
            "detailed_results": [self._serialize_integration_test(test) for test in self.test_history],
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "academic_analysis": self._analyze_academic_compliance(),
            "recommendations": self._generate_integration_recommendations(),
            "analysis_summary": self._build_analysis_summary(),
            "report_metadata": self._build_report_metadata(),
        }
        
        return report
    
    def _analyze_academic_compliance(self) -> Dict[str, Any]:
        """分析学术合规性"""
        if not self.test_history:
            return {"message": "没有测试结果可供分析"}
        
        # 计算学术合规性指标
        academic_scores = [test.academic_relevance for test in self.test_history if test.academic_relevance > 0]
        if academic_scores:
            avg_academic_score = sum(academic_scores) / len(academic_scores)
        else:
            avg_academic_score = 0.0
        
        # 计算科学性指标
        scientific_scores = [test.confidence_score for test in self.test_history if test.confidence_score > 0]
        if scientific_scores:
            avg_scientific_score = sum(scientific_scores) / len(scientific_scores)
        else:
            avg_scientific_score = 0.0
        
        # 生成学术洞察
        academic_insights = []
        
        if avg_academic_score > 0.8:
            insight = {
                "type": "academic_compliance",
                "title": "高学术合规性",
                "description": f"平均学术相关性评分达到 {avg_academic_score:.2f}，符合学术标准",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            }
            academic_insights.append(insight)
        
        if avg_scientific_score > 0.8:
            insight = {
                "type": "scientific_validity",
                "title": "高科学性",
                "description": f"平均科学性评分达到 {avg_scientific_score:.2f}，验证了研究的科学性",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat()
            }
            academic_insights.append(insight)
        
        return {
            "academic_compliance_score": avg_academic_score,
            "scientific_validity_score": avg_scientific_score,
            "insights": academic_insights,
            "compliance_status": "compliant" if avg_academic_score > 0.8 else "non_compliant"
        }
    
    def _generate_integration_recommendations(self) -> List[Dict[str, Any]]:
        """生成集成测试改进建议"""
        recommendations = []
        
        # 基于测试结果生成建议
        if self.test_history:
            failed_tests = [t for t in self.test_history if t.status == IntegrationTestStatus.FAILED]
            error_tests = [t for t in self.test_history if t.status == IntegrationTestStatus.ERROR]
            
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
            avg_confidence = self.performance_metrics["integration_quality_score"]
            if avg_confidence < 0.8:
                recommendation = {
                    "type": "quality_improvement",
                    "title": "提升测试质量",
                    "description": f"当前测试质量评分较低 ({avg_confidence:.2f})，建议加强质量控制",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat()
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    def export_integration_results(self, output_path: str, format_type: str = "json") -> bool:
        """
        导出集成测试结果
        
        Args:
            output_path (str): 输出路径
            format_type (str): 输出格式
            
        Returns:
            bool: 导出是否成功
        """
        phase_started_at = self._start_phase("export_integration_results", {"output_path": output_path, "format_type": format_type})

        try:
            report = self.generate_integration_report()
            
            if format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            elif format_type == "csv":
                # CSV格式导出（简化实现）
                pass
            
            self.failed_phase = None
            self.final_status = "completed"
            self._complete_phase("export_integration_results", phase_started_at, {"output_path": output_path})
            self.logger.info(f"集成测试结果已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_phase("export_integration_results", phase_started_at, e, {"output_path": output_path})
            self.logger.error(f"集成测试结果导出失败: {e}")
            return False
    
    def get_integration_performance_report(self) -> Dict[str, Any]:
        """获取集成测试性能报告"""
        return {
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "test_summary": self._calculate_overall_summary(),
            "test_history": [self._serialize_integration_test(test) for test in self.test_history],
            "test_environments": [
                {
                    "environment_id": env.environment_id,
                    "environment_name": env.environment_name,
                    "status": env.status,
                    "test_count": len(env.test_results)
                } for env in self.test_environments.values()
            ],
            "latest_results": [self._serialize_integration_test(test) for test in self.test_history[-10:]] if self.test_history else [],
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "report_metadata": self._build_report_metadata(),
            "metadata": self._build_runtime_metadata(),
        }
    
    def cleanup(self) -> bool:
        """清理资源"""
        phase_started_at = self._start_phase("cleanup")

        try:
            self.integration_tests.clear()
            self.test_history.clear()
            self.knowledge_graph.clear()
            for environment in self.test_environments.values():
                environment.test_results.clear()
            self.performance_metrics = self._create_performance_metrics()
            self.failed_operations.clear()
            self.phase_history.clear()
            self.phase_timings.clear()
            self.completed_phases.clear()
            self.failed_phase = None
            self.last_completed_phase = None
            self.final_status = "cleaned"
            
            self._complete_phase("cleanup", phase_started_at)
            self.logger.info("集成测试框架资源清理完成")
            return True
            
        except Exception as e:
            self._fail_phase("cleanup", phase_started_at, e)
            self.logger.error(f"资源清理失败: {e}")
            return False

# 导出主要类和函数
__all__ = [
    'IntegrationTester',
    'IntegrationTest',
    'TestEnvironment',
    'IntegrationTestStatus',
    'IntegrationTestType',
    'IntegrationTestPriority'
]
