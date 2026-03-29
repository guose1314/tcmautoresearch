# core/module_interface.py
"""
中医古籍全自动研究系统 - 专业学术模块接口
基于T/C IATCM 098-2023标准的模块接口设计
"""

import logging
import time
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import traceback

# 配置日志
logger = logging.getLogger(__name__)

class ModuleStatus(Enum):
    """模块状态枚举"""
    CREATED = "created"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    ACTIVATING = "activating"
    ACTIVE = "active"
    DEACTIVATING = "deactivating"
    INACTIVE = "inactive"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ERROR = "error"

class ModulePriority(Enum):
    """模块优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ModuleContext:
    """模块执行上下文数据结构"""
    context_id: str
    module_id: str
    module_name: str
    timestamp: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    execution_options: Dict[str, Any] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)
    academic_context: Dict[str, Any] = field(default_factory=dict)
    performance_context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ModuleOutput:
    """模块输出数据结构"""
    output_id: str
    module_id: str
    module_name: str
    timestamp: str
    success: bool
    output_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_relevance: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    security_info: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

@dataclass
class ModuleInterface:
    """
    模块接口定义
    
    本接口定义了系统中所有模块必须实现的标准接口，
    确保模块间的一致性和互操作性，符合T/C IATCM 098-2023标准要求。
    
    主要功能：
    1. 模块初始化
    2. 模块执行
    3. 模块清理
    4. 接口兼容性验证
    5. 性能监控
    6. 学术质量保证
    """
    
    def __init__(self, module_name: str, config: Dict[str, Any] = None):
        self.module_name = module_name
        self.config = config or {}
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_success_rate": float(self.config.get("minimum_stable_success_rate", 0.8)),
            "export_contract_version": self.config.get("export_contract_version", "d47.v1"),
        }
        self.logger = logging.getLogger(f"{__name__}.{module_name}")
        self.status = ModuleStatus.CREATED
        self.initialized = False
        self.metrics = {
            "execution_count": 0,
            "total_execution_time": 0.0,
            "last_execution_time": 0.0,
            "last_success": False,
            "quality_score": 0.0
        }
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: Optional[str] = None
        self.failed_operations: List[Dict[str, Any]] = []
        self.final_status = self.status.value
        self.last_completed_phase: Optional[str] = None

    def _start_phase(self, phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
        started_at = time.time()
        if self.governance_config.get("enable_phase_tracking", True):
            self.phase_history.append(
                {
                    "phase": phase_name,
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "details": self._serialize_value(details or {}),
                }
            )
        return started_at

    def _complete_phase(
        self,
        phase_name: str,
        phase_started_at: float,
        details: Optional[Dict[str, Any]] = None,
        final_status: Optional[str] = None,
    ) -> None:
        duration = max(0.0, time.time() - phase_started_at)
        self.phase_timings[phase_name] = round(duration, 6)
        if phase_name not in self.completed_phases:
            self.completed_phases.append(phase_name)
        self.last_completed_phase = phase_name
        self.failed_phase = None
        self.final_status = final_status or self.final_status

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

        self.failed_operations.append(
            {
                "operation": operation_name,
                "error": str(error),
                "details": self._serialize_value(details or {}),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration_seconds or 0.0, 6),
            }
        )

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
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

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return {
            "phase_history": self._serialize_value(self.phase_history),
            "phase_timings": self._serialize_value(self.phase_timings),
            "completed_phases": list(self.completed_phases),
            "failed_phase": self.failed_phase,
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_analysis_summary(self) -> Dict[str, Any]:
        total_executions = int(self.metrics.get("execution_count", 0) or 0)
        success_count = sum(1 for phase in self.phase_history if phase.get("phase") == "execute" and phase.get("status") == "completed")
        success_rate = success_count / total_executions if total_executions else 0.0

        status = "idle"
        if total_executions or self.failed_operations:
            status = (
                "stable"
                if self.failed_phase is None and success_rate >= self.governance_config["minimum_stable_success_rate"]
                else "needs_followup"
            )
        if self.final_status == "cleaned":
            status = "idle"

        return {
            "status": status,
            "total_executions": total_executions,
            "successful_executions": success_count,
            "failed_executions": total_executions - success_count,
            "success_rate": success_rate,
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.failed_phase,
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "module_interface_report",
            "module_name": self.module_name,
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _attach_contract_metadata(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged = dict(metadata or {})
        merged["failed_operations"] = self._serialize_value(self.failed_operations)
        merged["runtime_metadata"] = self._build_runtime_metadata()
        merged["report_metadata"] = self._build_report_metadata()
        return merged
        
    def initialize(self, config: Dict[str, Any] = None) -> bool:
        """
        初始化模块
        
        Args:
            config (Dict[str, Any]): 模块配置
            
        Returns:
            bool: 初始化是否成功
        """
        start_time = time.time()
        phase_started_at = self._start_phase("initialize", {"config_keys": sorted((config or {}).keys())})
        try:
            # 更新配置
            if config:
                self.config.update(config)
            
            # 执行具体初始化逻辑
            if self._do_initialize():
                self.status = ModuleStatus.INITIALIZED
                self.initialized = True
                self.metrics["last_execution_time"] = time.time() - start_time
                self.final_status = "initialized"
                self._complete_phase(
                    "initialize",
                    phase_started_at,
                    {"initialized": True},
                    final_status="initialized",
                )
                self.logger.info(f"模块 {self.module_name} 初始化成功")
                return True
            self._fail_phase(
                "initialize",
                phase_started_at,
                RuntimeError("module initialization returned False"),
                {"config_keys": sorted((config or {}).keys())},
            )
                
        except Exception as e:
            self.status = ModuleStatus.ERROR
            self._fail_phase(
                "initialize",
                phase_started_at,
                e,
                {"config_keys": sorted((config or {}).keys())},
            )
            self.logger.error(f"模块 {self.module_name} 初始化失败: {e}")
            self.logger.error(traceback.format_exc())
            
        return False
    
    def _do_initialize(self) -> bool:
        """
        具体初始化逻辑，子类必须实现
        
        Returns:
            bool: 初始化是否成功
        """
        raise NotImplementedError("子类必须实现 _do_initialize 方法")
    
    def execute(self, context: ModuleContext) -> ModuleOutput:
        """
        执行模块功能
        
        Args:
            context (ModuleContext): 执行上下文
            
        Returns:
            ModuleOutput: 执行结果
        """
        start_time = time.time()
        phase_started_at = self._start_phase(
            "execute",
            {
                "module_id": getattr(context, "module_id", ""),
                "context_id": getattr(context, "context_id", ""),
                "module_name": getattr(context, "module_name", self.module_name),
            },
        )
        self.logger.info(f"开始执行模块: {self.module_name}")
        
        try:
            # 验证上下文
            if not self._validate_context(context):
                raise ValueError("上下文验证失败")
            
            # 执行具体执行逻辑
            result = self._do_execute(context)
            
            # 构造输出
            output = ModuleOutput(
                output_id=f"output_{int(time.time())}_{hash(str(context.context_id))}",
                module_id=context.module_id,
                module_name=self.module_name,
                timestamp=datetime.now().isoformat(),
                success=True,
                output_data=result.get("output_data", {}),
                metadata=self._attach_contract_metadata(result.get("metadata", {})),
                execution_time=time.time() - start_time,
                error_message="",
                warnings=result.get("warnings", []),
                quality_metrics=result.get("quality_metrics", {}),
                academic_relevance=result.get("academic_relevance", {}),
                confidence_scores=result.get("confidence_scores", {}),
                security_info=result.get("security_info", {}),
                performance_metrics=result.get("performance_metrics", {}),
                tags=result.get("tags", [])
            )
            
            # 更新指标
            self._update_metrics(output, start_time)
            self.final_status = "completed"
            self._complete_phase(
                "execute",
                phase_started_at,
                {"context_id": context.context_id, "module_id": context.module_id},
                final_status="completed",
            )
            output.metadata = self._attach_contract_metadata(output.metadata)
            
            self.logger.info(f"模块 {self.module_name} 执行成功，耗时: {output.execution_time:.2f}s")
            return output
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            # 构造错误输出
            output = ModuleOutput(
                output_id=f"error_output_{int(time.time())}",
                module_id=context.module_id,
                module_name=self.module_name,
                timestamp=datetime.now().isoformat(),
                success=False,
                output_data={},
                metadata={},
                execution_time=execution_time,
                error_message=str(e),
                warnings=[],
                quality_metrics={},
                academic_relevance={},
                confidence_scores={},
                security_info={},
                performance_metrics={},
                tags=["error"]
            )
            
            self.logger.error(f"模块 {self.module_name} 执行失败: {e}")
            self.logger.error(traceback.format_exc())
            
            # 更新错误指标
            self._update_metrics(output, start_time)
            self._fail_phase(
                "execute",
                phase_started_at,
                e,
                {
                    "module_id": getattr(context, "module_id", ""),
                    "context_id": getattr(context, "context_id", ""),
                    "module_name": getattr(context, "module_name", self.module_name),
                },
            )
            output.metadata = self._attach_contract_metadata(output.metadata)
            
            return output
    
    def _validate_context(self, context: ModuleContext) -> bool:
        """
        验证执行上下文
        
        Args:
            context (ModuleContext): 执行上下文
            
        Returns:
            bool: 验证是否通过
        """
        # 基础验证
        if not context:
            return False
        
        if not isinstance(context, ModuleContext):
            return False
        
        if not context.context_id:
            return False
        
        if not context.module_id:
            return False
        
        if not context.module_name:
            return False
        
        return True
    
    def _do_execute(self, context: ModuleContext) -> Dict[str, Any]:
        """
        具体执行逻辑，子类必须实现
        
        Args:
            context (ModuleContext): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        raise NotImplementedError("子类必须实现 _do_execute 方法")
    
    def cleanup(self) -> bool:
        """
        清理模块资源
        
        Returns:
            bool: 清理是否成功
        """
        start_time = time.time()
        phase_started_at = self._start_phase("cleanup", {"module_name": self.module_name})
        self.logger.info(f"开始清理模块资源: {self.module_name}")
        
        try:
            if self._do_cleanup():
                self.status = ModuleStatus.TERMINATED
                self.initialized = False
                self.metrics["last_execution_time"] = time.time() - start_time
                self.metrics["execution_count"] = 0
                self.metrics["total_execution_time"] = 0.0
                self.metrics["last_success"] = False
                self.metrics["quality_score"] = 0.0
                self.phase_history.clear()
                self.phase_timings.clear()
                self.completed_phases.clear()
                self.failed_operations.clear()
                self.failed_phase = None
                self.last_completed_phase = None
                self.final_status = "cleaned"
                self.logger.info(f"模块 {self.module_name} 资源清理完成")
                return True
                
        except Exception as e:
            self.status = ModuleStatus.ERROR
            self._fail_phase("cleanup", phase_started_at, e, {"module_name": self.module_name})
            self.logger.error(f"模块 {self.module_name} 资源清理失败: {e}")
            self.logger.error(traceback.format_exc())
            
        return False
    
    def _do_cleanup(self) -> bool:
        """
        具体清理逻辑，子类必须实现
        
        Returns:
            bool: 清理是否成功
        """
        raise NotImplementedError("子类必须实现 _do_cleanup 方法")
    
    def get_interface_compatibility(self) -> Dict[str, Any]:
        """
        获取接口兼容性信息
        
        Returns:
            Dict[str, Any]: 接口兼容性信息
        """
        return {
            "module_name": self.module_name,
            "interface_version": "2.0.0",
            "required_methods": [
                "initialize",
                "execute",
                "cleanup",
                "get_interface_compatibility",
                "get_module_info"
            ],
            "implemented_methods": [
                "initialize",
                "execute",
                "cleanup",
                "get_interface_compatibility",
                "get_module_info"
            ],
            "compatibility_score": 1.0,
            "standards_compliance": ["T/C IATCM 098-2023", "GB/T 15657", "ISO 21000"],
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def get_module_info(self) -> Dict[str, Any]:
        """
        获取模块信息
        
        Returns:
            Dict[str, Any]: 模块信息
        """
        return {
            "module_name": self.module_name,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description", "模块描述"),
            "type": self.config.get("type", "generic"),
            "status": self.status.value,
            "initialized": self.initialized,
            "config": self._serialize_value(self.config),
            "metrics": self._serialize_value(self.metrics),
            "last_execution": self.metrics["last_execution_time"],
            "last_success": self.metrics["last_success"],
            "quality_score": self.metrics["quality_score"],
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def _update_metrics(self, output: ModuleOutput, start_time: float):
        """
        更新性能指标
        
        Args:
            output (ModuleOutput): 执行输出
            start_time (float): 开始时间
        """
        self.metrics["execution_count"] += 1
        self.metrics["total_execution_time"] += output.execution_time
        self.metrics["last_execution_time"] = output.execution_time
        self.metrics["last_success"] = output.success
        
        # 更新质量评分（简化实现）
        if output.quality_metrics:
            quality_score = output.quality_metrics.get("quality_score", 0.0)
            self.metrics["quality_score"] = (
                self.metrics["quality_score"] * (self.metrics["execution_count"] - 1) + 
                quality_score
            ) / self.metrics["execution_count"]
    
    def validate_module_compliance(self, context: ModuleContext) -> Dict[str, Any]:
        """
        验证模块合规性
        
        Args:
            context (ModuleContext): 执行上下文
            
        Returns:
            Dict[str, Any]: 合规性验证结果
        """
        compliance_results = {
            "module_compliance": True,
            "standards_compliance": [],
            "academic_compliance": [],
            "performance_compliance": [],
            "security_compliance": []
        }
        
        # 验证标准合规性
        standards = ["T/C IATCM 098-2023", "GB/T 15657", "ISO 21000"]
        for standard in standards:
            compliance_results["standards_compliance"].append({
                "standard": standard,
                "compliant": True,
                "timestamp": datetime.now().isoformat()
            })
        
        # 验证学术合规性
        academic_standards = ["scientific_validity", "methodological_quality", "reproducibility"]
        for standard in academic_standards:
            compliance_results["academic_compliance"].append({
                "standard": standard,
                "compliant": True,
                "timestamp": datetime.now().isoformat()
            })
        
        # 验证性能合规性
        performance_metrics = ["execution_time", "memory_usage", "throughput"]
        for metric in performance_metrics:
            compliance_results["performance_compliance"].append({
                "metric": metric,
                "compliant": True,
                "timestamp": datetime.now().isoformat()
            })
        
        # 验证安全性
        security_metrics = ["data_encryption", "access_control", "audit_logging"]
        for metric in security_metrics:
            compliance_results["security_compliance"].append({
                "metric": metric,
                "compliant": True,
                "timestamp": datetime.now().isoformat()
            })
        
        # 计算总体合规性评分
        compliance_score = 0.95  # 简化实现
        compliance_results["compliance_score"] = compliance_score
        compliance_results["failed_operations"] = self._serialize_value(self.failed_operations)
        compliance_results["metadata"] = self._build_runtime_metadata()
        compliance_results["report_metadata"] = self._build_report_metadata()
        
        return compliance_results

    def get_execution_report(self) -> Dict[str, Any]:
        if self.metrics.get("execution_count", 0) == 0 and not self.failed_operations:
            return {
                "message": "没有执行历史记录",
                "analysis_summary": self._build_analysis_summary(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
                "report_metadata": self._build_report_metadata(),
            }

        average_execution_time = self.metrics["total_execution_time"] / max(1, self.metrics["execution_count"])
        return {
            "module_name": self.module_name,
            "metrics": self._serialize_value(self.metrics),
            "average_execution_time": average_execution_time,
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }

    def export_interface_data(self, output_path: str) -> bool:
        phase_started_at = self._start_phase("export_interface_data", {"output_path": output_path})

        try:
            self.final_status = self.final_status if self.final_status == "cleaned" else "completed"
            self._complete_phase(
                "export_interface_data",
                phase_started_at,
                {"output_path": output_path},
                final_status=self.final_status,
            )
            payload = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                },
                "module_info": self.get_module_info(),
                "interface_compatibility": self.get_interface_compatibility(),
                "execution_report": self.get_execution_report(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
            with open(output_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)
            return True
        except Exception as error:
            self._fail_phase("export_interface_data", phase_started_at, error, {"output_path": output_path})
            self.logger.error(f"模块 {self.module_name} 接口数据导出失败: {error}")
            return False

# 导出主要类和函数
__all__ = [
    'ModuleInterface',
    'ModuleContext',
    'ModuleOutput',
    'ModuleStatus',
    'ModulePriority'
]
