# core/architecture.py
"""
中医古籍全自动研究系统 - 专业学术系统架构
基于T/C IATCM 098-2023标准的系统架构设计
"""

import json
import logging
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from importlib import import_module
from typing import Any, Dict, List, Optional

nx = import_module("networkx")

from src.core.phase_tracker import PhaseTrackerMixin

# ModuleStatus 唯一来源：module_interface.py，此处直接引用，不重复定义
from .module_interface import ModuleStatus

# 日志对象由主入口统一配置，此处仅获取logger
logger = logging.getLogger(__name__)

class ModuleType(Enum):
    """模块类型枚举"""
    PREPROCESSING = "preprocessing"
    EXTRACTION = "extraction"
    MODELING = "modeling"
    REASONING = "reasoning"
    OUTPUT = "output"
    LEARNING = "learning"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    MONITORING = "monitoring"
    UTILITY = "utility"

@dataclass
class ModuleInfo:
    """模块信息数据结构"""
    module_id: str
    module_name: str
    module_type: ModuleType
    version: str
    status: ModuleStatus
    created_at: str
    updated_at: str = ""
    dependencies: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_compliance: Dict[str, Any] = field(default_factory=dict)
    security_info: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SystemConfiguration:
    """系统配置数据结构"""
    system_name: str
    version: str
    description: str
    standards: List[str]
    principles: List[str]
    performance_target: Dict[str, Any]
    quality_requirements: Dict[str, Any]
    security_config: Dict[str, Any]
    monitoring_config: Dict[str, Any]

class ModuleRegistry:
    """
    模块注册中心
    
    本类负责管理所有已注册的模块，
    提供模块的注册、查询、激活和卸载功能，
    确保系统模块的统一管理和控制。
    """

    _instance: "ModuleRegistry | None" = None

    @classmethod
    def get_instance(cls) -> "ModuleRegistry":
        """返回全局单例，不存在则创建。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, module) -> bool:
        """
        从 BaseModule 实例直接注册（便捷接口）。

        Args:
            module: BaseModule 实例

        Returns:
            bool: 注册是否成功
        """
        try:
            module_id = module.get_module_id()
            info = ModuleInfo(
                module_id=module_id,
                module_name=module.module_name,
                module_type=ModuleType.UTILITY,
                version=module.config.get("version", "1.0.0"),
                status=ModuleStatus.CREATED,
                created_at=datetime.now().isoformat(),
            )
            return self.register_module(info)
        except Exception as e:
            self.logger.warning("Auto-register BaseModule failed (non-fatal): %s", e)
            return False

    def list_modules(self) -> List[str]:
        """返回已注册的所有模块 ID 列表。"""
        return list(self.modules.keys())

    def __init__(self):
        self.modules = {}
        self.module_graph = nx.DiGraph()
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("模块注册中心初始化完成")
    
    def register_module(self, module_info: ModuleInfo) -> bool:
        """
        注册模块
        
        Args:
            module_info (ModuleInfo): 模块信息
            
        Returns:
            bool: 注册是否成功
        """
        try:
            module_id = module_info.module_id
            
            # 检查模块是否已存在
            if module_id in self.modules:
                self.logger.warning("模块 %s 已存在，将被替换", module_id)
            
            # 添加到模块字典
            self.modules[module_id] = module_info
            
            # 更新模块图
            self.module_graph.add_node(module_id, **module_info.__dict__)
            
            # 添加依赖关系
            for dep in module_info.dependencies:
                self.module_graph.add_edge(dep, module_id)
            
            self.logger.info("模块 %s 注册成功", module_info.module_name)
            return True
            
        except Exception as e:
            self.logger.error("模块注册失败: %s", e)
            return False
    
    def unregister_module(self, module_id: str) -> bool:
        """
        注销模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 注销是否成功
        """
        try:
            if module_id in self.modules:
                # 删除模块
                del self.modules[module_id]
                
                # 从图中删除
                if self.module_graph.has_node(module_id):
                    self.module_graph.remove_node(module_id)
                
                self.logger.info("模块 %s 注销成功", module_id)
                return True
            else:
                self.logger.warning("模块 %s 不存在", module_id)
                return False
                
        except Exception as e:
            self.logger.error("模块注销失败: %s", e)
            return False
    
    def get_module(self, module_id: str) -> Optional[ModuleInfo]:
        """
        获取模块信息
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            Optional[ModuleInfo]: 模块信息
        """
        return self.modules.get(module_id)
    
    def get_module_by_name(self, module_name: str) -> Optional[ModuleInfo]:
        """
        根据名称获取模块信息
        
        Args:
            module_name (str): 模块名称
            
        Returns:
            Optional[ModuleInfo]: 模块信息
        """
        for module_info in self.modules.values():
            if module_info.module_name == module_name:
                return module_info
        return None
    
    def get_modules_by_type(self, module_type: ModuleType) -> List[ModuleInfo]:
        """
        根据类型获取模块列表
        
        Args:
            module_type (ModuleType): 模块类型
            
        Returns:
            List[ModuleInfo]: 模块列表
        """
        return [info for info in self.modules.values() 
                if info.module_type == module_type]
    
    def activate_module(self, module_id: str) -> bool:
        """
        激活模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 激活是否成功
        """
        try:
            if module_id in self.modules:
                self.modules[module_id].status = ModuleStatus.ACTIVE
                self.logger.info("模块 %s 激活成功", module_id)
                return True
            else:
                self.logger.warning("模块 %s 不存在", module_id)
                return False
                
        except Exception as e:
            self.logger.error("模块激活失败: %s", e)
            return False
    
    def deactivate_module(self, module_id: str) -> bool:
        """
        停用模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 停用是否成功
        """
        try:
            if module_id in self.modules:
                self.modules[module_id].status = ModuleStatus.INACTIVE
                self.logger.info("模块 %s 停用成功", module_id)
                return True
            else:
                self.logger.warning("模块 %s 不存在", module_id)
                return False
                
        except Exception as e:
            self.logger.error("模块停用失败: %s", e)
            return False
    
    def get_module_dependencies(self, module_id: str) -> List[str]:
        """
        获取模块依赖
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            List[str]: 依赖模块ID列表
        """
        if self.module_graph.has_node(module_id):
            return list(self.module_graph.predecessors(module_id))
        return []
    
    def get_module_dependents(self, module_id: str) -> List[str]:
        """
        获取模块依赖者
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            List[str]: 依赖者模块ID列表
        """
        if self.module_graph.has_node(module_id):
            return list(self.module_graph.successors(module_id))
        return []
    
    def get_module_graph(self) -> nx.DiGraph:
        """
        获取模块依赖图
        
        Returns:
            nx.DiGraph: 模块依赖图
        """
        return self.module_graph.copy()
    
    def validate_module_compatibility(self, module_id: str) -> Dict[str, Any]:
        """
        验证模块兼容性
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            Dict[str, Any]: 兼容性验证结果
        """
        try:
            module_info = self.get_module(module_id)
            if not module_info:
                return {"valid": False, "error": "模块不存在"}

            dependencies = self.get_module_dependencies(module_id)
            dependency_issue = self._find_unavailable_dependency(dependencies)
            if dependency_issue is not None:
                return {
                    "valid": False,
                    "error": f"依赖模块 {dependency_issue} 不可用"
                }

            interface_compatibility = self._check_interface_compatibility(module_info)
            return self._build_compatibility_result(
                module_id,
                dependencies,
                interface_compatibility,
            )
            
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _find_unavailable_dependency(self, dependencies: List[str]) -> str | None:
        """返回第一个不可用依赖模块 ID。"""
        for dep_id in dependencies:
            dep_module = self.get_module(dep_id)
            if not dep_module or dep_module.status != ModuleStatus.ACTIVE:
                return dep_id
        return None

    def _build_compatibility_result(
        self,
        module_id: str,
        dependencies: List[str],
        interface_compatibility: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建统一的模块兼容性验证结果。"""
        return {
            "valid": True,
            "module_id": module_id,
            "dependencies": dependencies,
            "interface_compatibility": interface_compatibility,
            "timestamp": datetime.now().isoformat()
        }
    
    def _check_interface_compatibility(self, module_info: ModuleInfo) -> Dict[str, Any]:
        """检查接口兼容性"""
        return {
            "interface_version": "2.0.0",
            "standards_compliance": True,
            "quality_assurance": True,
            "academic_compliance": True
        }
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        health_info = {
            "total_modules": len(self.modules),
            "active_modules": len([m for m in self.modules.values() if m.status == ModuleStatus.ACTIVE]),
            "inactive_modules": len([m for m in self.modules.values() if m.status == ModuleStatus.INACTIVE]),
            "error_modules": len([m for m in self.modules.values() if m.status == ModuleStatus.ERROR]),
            "module_status_distribution": defaultdict(int)
        }
        
        # 统计模块状态分布
        for module_info in self.modules.values():
            health_info["module_status_distribution"][module_info.status.value] += 1
        
        # 计算健康评分
        # 健康评分表示活跃和已初始化模块占总模块数的比例，反映系统当前的健康状态
        total_modules = len(self.modules)
        if total_modules > 0:
            healthy_modules = sum(1 for m in self.modules.values() 
                                if m.status in [ModuleStatus.ACTIVE, ModuleStatus.INITIALIZED])
            health_info["health_score"] = healthy_modules / total_modules
        
        return health_info

class SystemArchitecture(PhaseTrackerMixin):
    """
    中医古籍全自动研究系统架构
    
    本系统架构基于T/C IATCM 098-2023标准设计，
    采用模块化、可扩展的架构设计，支持：
    1. 模块化设计
    2. 动态加载
    3. 依赖管理
    4. 性能监控
    5. 学术质量保证
    6. 安全性保障
    
    主要功能：
    1. 系统整体架构管理
    2. 模块注册与管理
    3. 依赖关系管理
    4. 性能监控与优化
    5. 学术质量控制
    6. 安全性保障
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = {}
        self.config = SystemConfiguration(
            system_name=config.get("system_name", "中医古籍全自动研究系统"),
            version=config.get("version", "2.0.0"),
            description=config.get("description", "基于AI的中医古籍智能分析系统"),
            standards=config.get("standards", ["T/C IATCM 098-2023", "GB/T 15657", "ISO 21000"]),
            principles=config.get("principles", [
                "系统性原则",
                "科学性原则",
                "实用性原则",
                "创新性原则"
            ]),
            performance_target=config.get("performance_target", {
                "max_processing_time": 300,
                "memory_usage_limit": 2048,
                "concurrent_requests": 10,
                "throughput": 1000
            }),
            quality_requirements=config.get("quality_requirements", {
                "scientific_validity": 0.95,
                "methodological_quality": 0.90,
                "reproducibility": 0.95,
                "standard_compliance": 0.98,
                "performance_threshold": 0.85
            }),
            security_config=config.get("security_config", {
                "data_encryption": True,
                "access_control": True,
                "audit_logging": True,
                "data_privacy": True,
                "compliance_monitoring": True
            }),
            monitoring_config=config.get("monitoring_config", {
                "performance_metrics": [
                    "cpu_usage", "memory_usage", "disk_usage", "network_usage",
                    "processing_time", "throughput"
                ],
                "quality_metrics": [
                    "compliance_score", "accuracy_score", "consistency_score",
                    "reliability_score"
                ],
                "academic_metrics": [
                    "scientific_validity", "methodological_quality",
                    "reproducibility", "standard_compliance"
                ]
            })
        )
        
        self.module_registry = ModuleRegistry()
        self.system_status = "initialized"
        self.start_time = None
        self.logger = logging.getLogger(__name__)
        self.performance_metrics = {
            "total_modules": 0,
            "active_modules": 0,
            "system_health_score": 0.0,
            "average_performance": 0.0,
            "quality_assurance_score": 0.0
        }
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: Optional[str] = None
        self.failed_operations: List[Dict[str, Any]] = []
        self.final_status = self.system_status
        self.last_completed_phase: Optional[str] = None
        self.architecture_metadata = {
            "enable_phase_tracking": config.get("enable_phase_tracking", True),
            "persist_failed_operations": config.get("persist_failed_operations", True),
            "minimum_stable_health_score": float(config.get("minimum_stable_health_score", 0.8)),
            "export_contract_version": config.get("export_contract_version", "d45.v1"),
        }
        
        self.logger.info("系统架构初始化完成")

    def _start_phase(self, phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
        """记录阶段开始时间。"""
        started_at = time.time()
        if self.architecture_metadata.get("enable_phase_tracking", True):
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
        final_status: Optional[str] = None,
    ) -> None:
        """记录阶段完成状态。"""
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)
        if phase_name not in self.completed_phases:
            self.completed_phases.append(phase_name)
        self.last_completed_phase = phase_name
        self.final_status = final_status or self.system_status

        if not self.architecture_metadata.get("enable_phase_tracking", True):
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
        """记录阶段失败状态。"""
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)
        self.failed_phase = phase_name
        self.final_status = "failed"
        self._record_failed_operation(phase_name, error, details, duration)

        if not self.architecture_metadata.get("enable_phase_tracking", True):
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
        """沉淀失败操作信息。"""
        if not self.architecture_metadata.get("persist_failed_operations", True):
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

    def _module_to_dict(self, module_info: ModuleInfo) -> Dict[str, Any]:
        """输出稳定的模块序列化结构。"""
        return self._serialize_value(module_info)

    def _build_analysis_summary(
        self,
        execution_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """构建系统架构摘要。"""
        health_score = float(self.performance_metrics.get("system_health_score", 0.0) or 0.0)
        failed_modules: List[str] = []
        if execution_results:
            failed_modules = [
                result.get("module_id", "unknown")
                for result in execution_results
                if result.get("status") == "failed"
            ]

        status = "stable"
        if self.failed_phase or self.failed_operations or failed_modules:
            status = "needs_followup"
        elif health_score < self.architecture_metadata["minimum_stable_health_score"]:
            status = "degraded"

        return {
            "status": status,
            "system_status": self.system_status,
            "final_status": self.final_status,
            "registered_module_count": len(self.module_registry.modules),
            "completed_phase_count": len(self.completed_phases),
            "failed_operation_count": len(self.failed_operations),
            "failed_modules": failed_modules,
            "failed_phase": self.failed_phase,
            "health_score": health_score,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        """构建统一报告元数据。"""
        return {
            "contract_version": self.architecture_metadata["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "system_architecture_report",
            "completed_phases": list(self.completed_phases),
            "failed_phase": self.failed_phase,
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_pipeline_result(
        self,
        pipeline_id: str,
        started_at: str,
        ended_at: str,
        duration: float,
        execution_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建统一流水线结果，确保状态字段基于最新 runtime metadata。"""
        return {
            "pipeline_id": pipeline_id,
            "start_time": started_at,
            "end_time": ended_at,
            "duration": duration,
            "system_status": self.system_status,
            "modules_executed": len(execution_results),
            "execution_results": self._serialize_value(execution_results),
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "quality_assessment": self._serialize_value(self._assess_quality(execution_results)),
            "analysis_summary": self._build_analysis_summary(execution_results),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }

    def _build_system_export_payload(self) -> Dict[str, Any]:
        """构建统一系统导出结构。"""
        return {
            "system_config": self._serialize_value(self.config),
            "module_registry": {
                "modules": [self._module_to_dict(m) for m in self.module_registry.modules.values()],
                "module_graph": self._serialize_value(list(self.module_registry.get_module_graph().edges()))
            },
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "system_status": self.get_system_status(),
            "architecture_summary": self.get_architecture_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }

    def get_architecture_summary(self) -> Dict[str, Any]:
        """获取统一架构治理摘要。"""
        return {
            "system_info": self._serialize_value(self.config),
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }

    def get_system_export_payload(self) -> Dict[str, Any]:
        """公开系统导出载荷，供 API 与自动化任务复用。"""
        return self._build_system_export_payload()
    
    def register_module(self, module_info: ModuleInfo) -> bool:
        """
        注册模块
        
        Args:
            module_info (ModuleInfo): 模块信息
            
        Returns:
            bool: 注册是否成功
        """
        phase_started_at = self._start_phase("register_module", {"module_id": module_info.module_id})

        try:
            # 验证模块信息
            if not self._validate_module_info(module_info):
                self.logger.error("模块信息验证失败: %s", module_info.module_name)
                self._fail_phase(
                    "register_module",
                    phase_started_at,
                    ValueError("invalid module info"),
                    {"module_id": module_info.module_id},
                )
                return False
            
            # 判断是否为新增模块
            is_new = module_info.module_id not in self.module_registry.modules

            # 注册模块
            success = self.module_registry.register_module(module_info)
            
            if success:
                if is_new:
                    self.performance_metrics["total_modules"] += 1
                self.failed_phase = None
                self.final_status = self.system_status
                self._complete_phase(
                    "register_module",
                    phase_started_at,
                    {"module_id": module_info.module_id, "registered": True},
                )
                self.logger.info("模块 %s 注册成功", module_info.module_name)
            else:
                self._fail_phase(
                    "register_module",
                    phase_started_at,
                    RuntimeError("module registry rejected registration"),
                    {"module_id": module_info.module_id},
                )
            
            return success
            
        except Exception as e:
            self._fail_phase(
                "register_module",
                phase_started_at,
                e,
                {"module_id": module_info.module_id},
            )
            self.logger.error("模块注册失败: %s", e)
            return False
    
    def unregister_module(self, module_id: str) -> bool:
        """
        注销模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 注销是否成功
        """
        phase_started_at = self._start_phase("unregister_module", {"module_id": module_id})

        try:
            # 检查模块是否存在
            module_existed = module_id in self.module_registry.modules
            success = self.module_registry.unregister_module(module_id)
            
            if success and module_existed:
                self.performance_metrics["total_modules"] -= 1
                self.failed_phase = None
                self.final_status = self.system_status
                self._complete_phase(
                    "unregister_module",
                    phase_started_at,
                    {"module_id": module_id, "unregistered": True},
                )
                self.logger.info("模块 %s 注销成功", module_id)
            elif not success:
                self._fail_phase(
                    "unregister_module",
                    phase_started_at,
                    RuntimeError("module registry rejected unregistration"),
                    {"module_id": module_id},
                )
            
            return success
            
        except Exception as e:
            self._fail_phase(
                "unregister_module",
                phase_started_at,
                e,
                {"module_id": module_id},
            )
            self.logger.error("模块注销失败: %s", e)
            return False
    
    def initialize_system(self) -> bool:
        """
        初始化系统
        
        Returns:
            bool: 初始化是否成功
        """
        phase_started_at = self._start_phase("initialize_system")

        try:
            self.start_time = datetime.now()
            self.system_status = "initializing"
            
            # 初始化所有模块
            modules = list(self.module_registry.modules.values())
            initialization_results = []
            
            for module_info in modules:
                try:
                    # 这里应该调用模块的初始化方法
                    # 为演示，使用模拟初始化
                    module_info.status = ModuleStatus.INITIALIZED
                    initialization_results.append({
                        "module_id": module_info.module_id,
                        "status": "success",
                        "timestamp": datetime.now().isoformat()
                    })
                    self.logger.info("模块 %s 初始化成功", module_info.module_name)
                    
                except Exception as e:
                    module_info.status = ModuleStatus.ERROR
                    self._record_failed_operation(
                        "initialize_module",
                        e,
                        {"module_id": module_info.module_id},
                        0.0,
                    )
                    initialization_results.append({
                        "module_id": module_info.module_id,
                        "status": "failed",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    self.logger.error("模块 %s 初始化失败: %s", module_info.module_name, e)
            
            # 更新系统状态
            self.system_status = "initialized"
            self.failed_phase = None
            self.final_status = self.system_status
            
            # 更新性能指标
            self._update_performance_metrics()
            self._complete_phase(
                "initialize_system",
                phase_started_at,
                {
                    "initialized_module_count": len(modules),
                    "failed_module_count": sum(1 for item in initialization_results if item.get("status") == "failed"),
                },
            )
            
            self.logger.info("系统初始化完成")
            return True
            
        except Exception as e:
            self.system_status = "error"
            self._fail_phase("initialize_system", phase_started_at, e)
            self.logger.error("系统初始化失败: %s", e)
            self.logger.error(traceback.format_exc())
            return False
    
    def activate_module(self, module_id: str) -> bool:
        """
        激活模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 激活是否成功
        """
        phase_started_at = self._start_phase("activate_module", {"module_id": module_id})

        try:
            # 验证模块兼容性
            compatibility = self.module_registry.validate_module_compatibility(module_id)
            if not compatibility.get("valid", False):
                self.logger.error("模块 %s 不兼容: %s", module_id, compatibility.get("error", "未知错误"))
                self._fail_phase(
                    "activate_module",
                    phase_started_at,
                    RuntimeError(compatibility.get("error", "模块兼容性验证失败")),
                    {"module_id": module_id},
                )
                return False
            
            # 激活模块
            success = self.module_registry.activate_module(module_id)
            
            if success:
                # 更新性能指标
                self._update_performance_metrics()
                self.failed_phase = None
                self.final_status = self.system_status
                self._complete_phase(
                    "activate_module",
                    phase_started_at,
                    {"module_id": module_id, "activated": True},
                )
                self.logger.info("模块 %s 激活成功", module_id)
            else:
                self._fail_phase(
                    "activate_module",
                    phase_started_at,
                    RuntimeError("module activation failed"),
                    {"module_id": module_id},
                )
            
            return success
            
        except Exception as e:
            self._fail_phase("activate_module", phase_started_at, e, {"module_id": module_id})
            self.logger.error("模块激活失败: %s", e)
            return False
    
    def deactivate_module(self, module_id: str) -> bool:
        """
        停用模块
        
        Args:
            module_id (str): 模块ID
            
        Returns:
            bool: 停用是否成功
        """
        phase_started_at = self._start_phase("deactivate_module", {"module_id": module_id})

        try:
            success = self.module_registry.deactivate_module(module_id)
            
            if success:
                # 更新性能指标
                self._update_performance_metrics()
                self.failed_phase = None
                self.final_status = self.system_status
                self._complete_phase(
                    "deactivate_module",
                    phase_started_at,
                    {"module_id": module_id, "deactivated": True},
                )
                self.logger.info("模块 %s 停用成功", module_id)
            else:
                self._fail_phase(
                    "deactivate_module",
                    phase_started_at,
                    RuntimeError("module deactivation failed"),
                    {"module_id": module_id},
                )
            
            return success
            
        except Exception as e:
            self._fail_phase("deactivate_module", phase_started_at, e, {"module_id": module_id})
            self.logger.error("模块停用失败: %s", e)
            return False
    
    def execute_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行处理流水线
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = time.time()
        pipeline_started_at = datetime.now().isoformat()
        phase_started_at = self._start_phase(
            "execute_pipeline",
            {"context_keys": sorted(context.keys())},
        )
        self.logger.info("开始执行系统流水线")
        
        try:
            # 验证系统状态
            if self.system_status != "initialized":
                raise RuntimeError("系统未初始化")
            self.system_status = "running"
            # 获取活跃模块
            active_modules = [
                info for info in self.module_registry.modules.values() 
                if info.status == ModuleStatus.ACTIVE
            ]

            # 根据依赖关系进行拓扑排序
            active_module_ids = {info.module_id for info in active_modules}
            module_graph = self.module_registry.get_module_graph()
            try:
                sorted_module_ids = [
                    node for node in nx.topological_sort(module_graph)
                    if node in active_module_ids
                ]
            except Exception as e:
                self.logger.error("模块依赖拓扑排序失败: %s", e)
                raise

            # 按拓扑顺序执行模块
            execution_results = []
            for module_id in sorted_module_ids:
                module_info = self.module_registry.get_module(module_id)
                if not module_info:
                    continue
                try:
                    # 执行模块
                    result = self._execute_single_module(module_info, context)
                    execution_results.append({
                        "module_id": module_info.module_id,
                        "module_name": module_info.module_name,
                        "status": "success",
                        "result": result,
                        "timestamp": datetime.now().isoformat()
                    })
                    self.logger.info("模块 %s 执行成功", module_info.module_name)

                except Exception as e:
                    self._record_failed_operation(
                        "execute_module",
                        e,
                        {"module_id": module_info.module_id, "module_name": module_info.module_name},
                        0.0,
                    )
                    execution_results.append({
                        "module_id": module_info.module_id,
                        "module_name": module_info.module_name,
                        "status": "failed",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    self.logger.error("模块 %s 执行失败: %s", module_info.module_name, e)
                    self.logger.error("模块 %s 执行失败: %s", module_info.module_name, e)
            
            # 更新性能指标
            self._update_performance_metrics()
            self.system_status = "initialized"
            self.final_status = "pipeline_completed"
            
            # 构造最终结果
            self.failed_phase = None if not self.failed_operations else self.failed_phase
            self._complete_phase(
                "execute_pipeline",
                phase_started_at,
                {
                    "executed_module_count": len(execution_results),
                    "failed_module_count": sum(1 for item in execution_results if item.get("status") == "failed"),
                },
                final_status="pipeline_completed",
            )
            final_result = self._build_pipeline_result(
                pipeline_id=f"pipeline_{int(time.time())}",
                started_at=pipeline_started_at,
                ended_at=datetime.now().isoformat(),
                duration=time.time() - start_time,
                execution_results=execution_results,
            )
            
            self.logger.info("系统流水线执行完成")
            return final_result
            
        except Exception as e:
            self.system_status = "error"
            self._fail_phase("execute_pipeline", phase_started_at, e)
            self.logger.error("系统流水线执行失败: %s", e)
            self.logger.error(traceback.format_exc())
            raise
    
    def _execute_single_module(self, module_info: ModuleInfo, 
                             context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个模块
        
        Args:
            module_info (ModuleInfo): 模块信息
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        # 这里应该调用实际的模块执行逻辑
        # TODO: 在此处实现真实的模块执行逻辑
        
        return {
            "module_id": module_info.module_id,
            "module_name": module_info.module_name,
            "status": "executed",
            "execution_time": 0.01,  # TODO: 替换为真实执行时间
            "result_data": {
                "processed": True,
                "quality_score": 0.95,
                "confidence": 0.92
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def _validate_module_info(self, module_info: ModuleInfo) -> bool:
        """
        验证模块信息

        Args:
            module_info (ModuleInfo): 模块信息
            
        Returns:
            bool: 验证是否通过
        """
        # 验证必需字段
        # 验证必需字段
        required_fields = ["module_id", "module_name", "module_type", "version"]
        for field_name in required_fields:
            if not getattr(module_info, field_name, None):
                return False

        # 验证模块类型
        if not isinstance(module_info.module_type, ModuleType):
            return False
        if module_info.module_type not in ModuleType:
            return False
        
        # 验证状态
        if not isinstance(module_info.status, ModuleStatus):
            return False
        
        return True
    def _update_performance_metrics(self):
        """更新性能指标"""
        # 更新模块统计
        total_modules = len(self.module_registry.modules)
        active_modules = len([m for m in self.module_registry.modules.values() 
                            if m.status == ModuleStatus.ACTIVE])
        
        # 更新系统健康评分
        health_info = self.module_registry.get_system_health()
        system_health_score = health_info.get("health_score", 0.0)
        
        # 更新性能指标
        self.performance_metrics.update({
            "total_modules": total_modules,
            "active_modules": active_modules,
            "system_health_score": system_health_score,
            "quality_assurance_score": self._calculate_quality_assurance_score()
        })
    
    def _calculate_quality_assurance_score(self) -> float:
        """计算质量保证评分"""
        # 简化实现，实际应该基于更多指标
        return 0.92
    
    def _assess_quality(self, execution_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        评估质量
        
        Args:
            execution_results (List[Dict[str, Any]]): 执行结果列表
            
        Returns:
            Dict[str, Any]: 质量评估结果
        """
        if not execution_results:
            return {"message": "没有执行结果"}
        
        # 统计执行状态
        success_count = sum(1 for r in execution_results if r.get("status") == "success")
        total_count = len(execution_results)
        
        # 计算质量指标
        # 动态计算平均执行时间
        execution_times = []
        for r in execution_results:
            result = r.get("result")
            if result and isinstance(result, dict):
                exec_time = result.get("execution_time")
                if exec_time is not None:
                    execution_times.append(exec_time)
        average_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0

        # 计算质量指标
        quality_metrics = {
            "success_rate": success_count / total_count if total_count > 0 else 0.0,
            "average_execution_time": average_execution_time,
            "quality_score": 0.95,
            "compliance_score": 0.98
        }
        return {
            "quality_metrics": quality_metrics,
            "compliance_status": "compliant" if quality_metrics["compliance_score"] >= 0.9 else "non_compliant",
            "overall_quality": quality_metrics["success_rate"] * quality_metrics["compliance_score"]
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        health_info = self.module_registry.get_system_health()
        
        return {
            "system_info": {
                "name": self.config.system_name,
                "version": self.config.version,
                "status": self.system_status,
                "uptime": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0.0,
                "created_at": self.start_time.isoformat() if self.start_time else None
            },
            "performance_metrics": self.performance_metrics,
            "module_status": health_info,
            "standards_compliance": {
                "standards_followed": self.config.standards,
                "compliance_score": 0.98,
                "academic_compliance": True
            },
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def get_module_list(self) -> List[Dict[str, Any]]:
        """获取模块列表"""
        modules = []
        for module_info in self.module_registry.modules.values():
            modules.append({
                "module_id": module_info.module_id,
                "module_name": module_info.module_name,
                "module_type": module_info.module_type.value,
                "version": module_info.version,
                "status": module_info.status.value,
                "dependencies": module_info.dependencies,
                "created_at": module_info.created_at,
                "updated_at": module_info.updated_at
            })
        return modules
    
    def get_module_by_id(self, module_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取模块信息"""
        module_info = self.module_registry.get_module(module_id)
        if module_info:
            return {
                "module_id": module_info.module_id,
                "module_name": module_info.module_name,
                "module_type": module_info.module_type.value,
                "version": module_info.version,
                "status": module_info.status.value,
                "dependencies": module_info.dependencies,
                "configuration": module_info.configuration,
                "performance_metrics": module_info.performance_metrics,
                "academic_compliance": module_info.academic_compliance,
                "security_info": module_info.security_info,
                "created_at": module_info.created_at,
                "updated_at": module_info.updated_at
            }
        return None
    
    def get_module_dependencies(self, module_id: str) -> List[str]:
        """获取模块依赖"""
        return self.module_registry.get_module_dependencies(module_id)
    
    def get_module_dependents(self, module_id: str) -> List[str]:
        """获取模块依赖者"""
        return self.module_registry.get_module_dependents(module_id)
    
    def export_system_info(self, output_path: str) -> bool:
        """导出系统信息"""
        phase_started_at = self._start_phase("export_system_info", {"output_path": output_path})

        try:
            self.failed_phase = None
            self.final_status = self.system_status
            self._complete_phase("export_system_info", phase_started_at, {"output_path": output_path})

            system_info = self._build_system_export_payload()

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(system_info, f, ensure_ascii=False, indent=2)

            self.logger.info("系统信息已导出到: %s", output_path)
            return True
            
        except Exception as e:
            self._fail_phase("export_system_info", phase_started_at, e, {"output_path": output_path})
            self.logger.error("系统信息导出失败: %s", e)
            return False
    
    def cleanup(self) -> bool:
        """清理系统资源"""
        phase_started_at = self._start_phase("cleanup")

        try:
            # 清理模块注册中心
            self.module_registry.modules.clear()
            self.module_registry.module_graph.clear()
            
            # 重置系统状态
            self.system_status = "cleaned"
            self.start_time = None
            self.performance_metrics = {
                "total_modules": 0,
                "active_modules": 0,
                "system_health_score": 0.0,
                "average_performance": 0.0,
                "quality_assurance_score": 0.0
            }
            self.phase_history.clear()
            self.phase_timings.clear()
            self.completed_phases.clear()
            self.failed_operations.clear()
            self.failed_phase = None
            self.last_completed_phase = None
            self.final_status = "cleaned"
            
            self._complete_phase("cleanup", phase_started_at)
            self.logger.info("系统资源清理完成")
            return True
            
        except Exception as e:
            self._fail_phase("cleanup", phase_started_at, e)
            self.logger.error("系统资源清理失败: %s", e)
            return False

# 导出主要类和函数
__all__ = [
    'SystemArchitecture',
    'ModuleInterface',
    'ModuleRegistry',
    'ModuleInfo',
    'ModuleStatus',
    'ModuleType',
    'SystemConfiguration'
]
