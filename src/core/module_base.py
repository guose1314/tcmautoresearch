# core/module_base.py
"""
中医古籍全自动研究系统 - 专业学术模块基类
基于T/C IATCM 098-2023标准的模块基类实现
"""

import asyncio
import json
import logging
import time
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.phase_tracker import PhaseTrackerMixin

# 全局线程池管理
_global_executor = None
_global_executor_max_workers = None

def get_global_executor(max_workers=4):
    global _global_executor, _global_executor_max_workers
    executor_shutdown = bool(getattr(_global_executor, "_shutdown", False))
    if _global_executor is None or executor_shutdown or _global_executor_max_workers != max_workers:
        if _global_executor is not None:
            _global_executor.shutdown(wait=True)
        _global_executor = ThreadPoolExecutor(max_workers=max_workers)
        _global_executor_max_workers = max_workers
    return _global_executor

# 配置日志
logger = logging.getLogger(__name__)

class BaseModule(PhaseTrackerMixin, ABC):
    """
    模块基类
    
    本基类为所有模块提供通用功能和生命周期管理，
    确保模块的一致性和可维护性，符合T/C IATCM 098-2023标准要求。
    
    主要功能：
    1. 生命周期管理
    2. 性能监控
    3. 错误处理
    4. 资源管理
    5. 学术质量保证
    6. 并发支持
    """
    
    def __init__(self, module_name: str, config: Dict[str, Any] | None = None):
        self.module_name = module_name
        self.config = config or {}
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_success_rate": float(self.config.get("minimum_stable_success_rate", 0.8)),
            "export_contract_version": self.config.get("export_contract_version", "d46.v1"),
        }
        self.logger = logging.getLogger(f"{__name__}.{module_name}")
        self.initialized = False
        self.status = "created"
        self.metrics = {
            "execution_count": 0,
            "total_execution_time": 0.0,
            "last_execution_time": 0.0,
            "last_success": False,
            "quality_score": 0.0,
            "performance_score": 0.0,
            "academic_relevance": 0.0,
            "resource_utilization": 0.0
        }
        self.module_start_time = None
        # 使用全局线程池，避免每个模块实例都创建线程池
        self.executor = get_global_executor(self.config.get("max_workers", 4))
        self.performance_history = []
        self.academic_insights = []
        self.recommendations = []
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: Optional[str] = None
        self.failed_operations: List[Dict[str, Any]] = []
        self.final_status = self.status
        self.last_completed_phase: Optional[str] = None
        
        self.logger.info(f"模块 {module_name} 基类初始化完成")

    def _build_analysis_summary(self) -> Dict[str, Any]:
        total_executions = len(self.performance_history)
        success_count = sum(1 for item in self.performance_history if item.get("success"))
        success_rate = success_count / total_executions if total_executions else 0.0

        status = "idle"
        if total_executions or self.failed_operations:
            status = (
                "stable"
                if self.failed_phase is None
                and success_rate >= self.governance_config["minimum_stable_success_rate"]
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
            "result_schema": "base_module_report",
            "module_name": self.module_name,
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_export_payload(self, output_path: str) -> Dict[str, Any]:
        return {
            "report_metadata": {
                **self._build_report_metadata(),
                "output_path": output_path,
            },
            "module_info": self._serialize_value(self.get_module_info()),
            "performance_report": self._serialize_value(self.get_performance_report()),
            "metrics_history": self._serialize_value(self.performance_history),
            "academic_insights": self._serialize_value(self.academic_insights),
            "recommendations": self._serialize_value(self.recommendations),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
        }
    
    def initialize(self, config: Dict[str, Any] | None = None) -> bool:
        """
        初始化模块
        
        Args:
            config (Dict[str, Any]): 模块配置
            
        Returns:
            bool: 初始化是否成功
        """
        start_time = time.time()
        phase_started_at = self._start_phase("initialize", {"config_keys": sorted((config or {}).keys())})
        self.logger.info(f"开始初始化模块: {self.module_name}")
        
        try:
            # 更新配置
            if config:
                self.config.update(config)
            
            # 执行具体初始化逻辑
            if self._do_initialize():
                self.initialized = True
                self.status = "initialized"
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
            self.status = "error"
            self._fail_phase(
                "initialize",
                phase_started_at,
                e,
                {"config_keys": sorted((config or {}).keys())},
            )
            self.logger.error(f"模块 {self.module_name} 初始化失败: {e}")
            self.logger.error(traceback.format_exc())
            
        return False
    
    @abstractmethod
    def _do_initialize(self) -> bool:
        """
        具体初始化逻辑，子类必须实现
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行模块功能
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        if not self.initialized:
            raise RuntimeError(f"模块 {self.module_name} 未初始化")
        
        start_time = time.time()
        phase_started_at = self._start_phase(
            "execute",
            {"module_name": self.module_name, "context_keys": sorted(context.keys())},
        )
        self.module_start_time = start_time
        self.logger.info(f"开始执行模块: {self.module_name}")
        
        try:
            # 执行具体执行逻辑
            result = self._do_execute(context)
            
            # 更新指标
            execution_time = time.time() - start_time
            self._update_metrics(result, execution_time)
            self.metrics["last_success"] = True
            
            # 记录执行历史
            self._record_execution_history(result, execution_time)
            
            # 生成学术洞察
            self._generate_academic_insights(result)
            
            # 生成改进建议
            self._generate_recommendations(result)
            self.final_status = "completed"
            self._complete_phase(
                "execute",
                phase_started_at,
                {"context_keys": sorted(context.keys())},
                final_status="completed",
            )
            
            self.logger.info(f"模块 {self.module_name} 执行成功，耗时: {execution_time:.2f}s")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"模块 {self.module_name} 执行失败: {e}")
            self.logger.error(traceback.format_exc())
            
            # 更新错误指标
            self.metrics["last_execution_time"] = execution_time
            self.metrics["last_success"] = False
            
            # 记录错误执行历史
            self._record_execution_history({"error": str(e)}, execution_time)
            self._fail_phase(
                "execute",
                phase_started_at,
                e,
                {"module_name": self.module_name, "context_keys": sorted(context.keys())},
            )
            
            raise
    
    @abstractmethod
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        具体执行逻辑，子类必须实现
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        pass
    
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
                self.initialized = False
                self.status = "cleaned"
                self.metrics["last_execution_time"] = time.time() - start_time
                self.metrics["execution_count"] = 0
                self.metrics["total_execution_time"] = 0.0
                self.metrics["last_success"] = False
                self.metrics["quality_score"] = 0.0
                self.metrics["performance_score"] = 0.0
                self.metrics["academic_relevance"] = 0.0
                self.metrics["resource_utilization"] = 0.0
                self.performance_history.clear()
                self.academic_insights.clear()
                self.recommendations.clear()
                self.phase_history.clear()
                self.phase_timings.clear()
                self.completed_phases.clear()
                self.failed_operations.clear()
                self.failed_phase = None
                self.last_completed_phase = None
                self.final_status = "cleaned"
                self.logger.info(f"模块 {self.module_name} 资源清理完成")
                
                # 不关闭全局线程池
                # self.executor.shutdown(wait=True)
                return True
                
        except Exception as e:
            self.status = "error"
            self._fail_phase("cleanup", phase_started_at, e, {"module_name": self.module_name})
            self.logger.error(f"模块 {self.module_name} 资源清理失败: {e}")
            self.logger.error(traceback.format_exc())
            
        return False
    
    @abstractmethod
    def _do_cleanup(self) -> bool:
        """
        具体清理逻辑，子类必须实现
        
        Returns:
            bool: 清理是否成功
        """
        pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取模块指标
        
        Returns:
            Dict[str, Any]: 模块指标
        """
        return {
            "module_name": self.module_name,
            "status": self.status,
            "initialized": self.initialized,
            "metrics": self._serialize_value(self.metrics),
            "last_execution_time": self.metrics["last_execution_time"],
            "last_success": self.metrics["last_success"],
            "quality_score": self.metrics["quality_score"],
            "performance_score": self.metrics["performance_score"],
            "academic_relevance": self.metrics["academic_relevance"],
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
            "status": self.status,
            "initialized": self.initialized,
            "config": self._serialize_value(self.config),
            "metrics": self._serialize_value(self.metrics),
            "performance_history": self._serialize_value(self.performance_history[-10:]),  # 最近10次
            "academic_insights": self._serialize_value(self.academic_insights[-5:]),  # 最近5个洞察
            "recommendations": self._serialize_value(self.recommendations[-5:]),  # 最近5个建议
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "last_execution": self.module_start_time
        }
    
    def _update_metrics(self, result: Dict[str, Any], execution_time: float):
        """
        更新性能指标
        
        Args:
            result (Dict[str, Any]): 执行结果
            execution_time (float): 执行时间
        """
        self.metrics["execution_count"] += 1
        self.metrics["total_execution_time"] += execution_time
        self.metrics["last_execution_time"] = execution_time
        
        # 更新成功状态
        self.metrics["last_success"] = result.get("success", False) if isinstance(result, dict) else False
        
        # 更新质量评分
        if isinstance(result, dict):
            quality_score = result.get("quality_score")
            if quality_score is not None:
                self.metrics["quality_score"] = (
                    self.metrics["quality_score"] * (self.metrics["execution_count"] - 1) + 
                    quality_score
                ) / self.metrics["execution_count"]
            
            # 更新性能评分
            performance_score = result.get("performance_score")
            if performance_score is not None:
                self.metrics["performance_score"] = (
                    self.metrics["performance_score"] * (self.metrics["execution_count"] - 1) + 
                    performance_score
                ) / self.metrics["execution_count"]
            
            # 更新学术相关性
            academic_relevance = result.get("academic_relevance")
            if academic_relevance is not None:
                self.metrics["academic_relevance"] = (
                    self.metrics["academic_relevance"] * (self.metrics["execution_count"] - 1) + 
                    academic_relevance
                ) / self.metrics["execution_count"]
    
    def _record_execution_history(self, result: Dict[str, Any], execution_time: float):
        """
        记录执行历史
        
        Args:
            result (Dict[str, Any]): 执行结果
            execution_time (float): 执行时间
        """
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "module": self.module_name,
            "execution_time": execution_time,
            "success": result.get("success", False) if isinstance(result, dict) else False,
            "result_summary": str(result)[:100] + "..." if len(str(result)) > 100 else str(result)
        }
        
        self.performance_history.append(history_entry)
        
        # 保持历史记录数量
        if len(self.performance_history) > 100:
            self.performance_history.pop(0)
    
    def _generate_academic_insights(self, result: Dict[str, Any]):
        """
        生成学术洞察
        
        Args:
            result (Dict[str, Any]): 执行结果
        """
        # 基于执行结果生成学术洞察
        if isinstance(result, dict):
            quality_score = result.get("quality_score", 0.0)
            academic_relevance = result.get("academic_relevance", 0.0)
            
            if quality_score >= 0.9:
                insight = {
                    "type": "high_quality",
                    "title": f"{self.module_name}高质量执行洞察",
                    "description": f"模块执行质量评分达到 {quality_score:.2f}，符合学术研究要求",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "academic", "insight"]
                }
                self.academic_insights.append(insight)
            
            if academic_relevance >= 0.85:
                insight = {
                    "type": "academic_value",
                    "title": f"{self.module_name}学术价值洞察",
                    "description": f"模块学术相关性评分达到 {academic_relevance:.2f}，具有重要研究价值",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "value", "insight"]
                }
                self.academic_insights.append(insight)
    
    def _generate_recommendations(self, result: Dict[str, Any]):
        """
        生成改进建议
        
        Args:
            result (Dict[str, Any]): 执行结果
        """
        # 基于执行结果生成改进建议
        if isinstance(result, dict):
            quality_score = result.get("quality_score", 0.0)
            performance_score = result.get("performance_score", 0.0)
            
            if quality_score < 0.8:
                recommendation = {
                    "type": "quality_improvement",
                    "title": f"提升{self.module_name}质量的建议",
                    "description": f"模块质量评分较低 ({quality_score:.2f})，建议优化处理逻辑",
                    "priority": "medium",
                    "confidence": 0.80,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "improvement", "recommendation"]
                }
                self.recommendations.append(recommendation)
            
            if performance_score < 0.7:
                recommendation = {
                    "type": "performance_optimization",
                    "title": f"优化{self.module_name}性能的建议",
                    "description": f"模块性能评分较低 ({performance_score:.2f})，建议优化执行效率",
                    "priority": "high",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["performance", "optimization", "recommendation"]
                }
                self.recommendations.append(recommendation)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        获取性能报告
        
        Returns:
            Dict[str, Any]: 性能报告
        """
        if not self.performance_history:
            return {
                "message": "没有执行历史记录",
                "analysis_summary": self._build_analysis_summary(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
                "report_metadata": self._build_report_metadata(),
            }
        
        # 计算平均性能指标
        execution_times = [h["execution_time"] for h in self.performance_history]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
        
        # 统计成功/失败次数
        success_count = sum(1 for h in self.performance_history if h["success"])
        total_count = len(self.performance_history)
        success_rate = success_count / total_count if total_count > 0 else 0.0
        
        return {
            "module_name": self.module_name,
            "total_executions": total_count,
            "successful_executions": success_count,
            "failed_executions": total_count - success_count,
            "success_rate": success_rate,
            "average_execution_time": avg_execution_time,
            "metrics": self._serialize_value(self.metrics),
            "performance_history": self._serialize_value(self.performance_history[-10:]),  # 最近10次
            "academic_insights": self._serialize_value(self.academic_insights[-5:]),  # 最近5个洞察
            "recommendations": self._serialize_value(self.recommendations[-5:]),  # 最近5个建议
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def export_module_data(self, output_path: str) -> bool:
        """
        导出模块数据
        
        Args:
            output_path (str): 输出路径
            
        Returns:
            bool: 导出是否成功
        """
        phase_started_at = self._start_phase("export_module_data", {"output_path": output_path})

        try:
            self.final_status = "completed"
            self._complete_phase(
                "export_module_data",
                phase_started_at,
                {"output_path": output_path},
                final_status="completed",
            )
            module_data = self._build_export_payload(output_path)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(module_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"模块数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_phase("export_module_data", phase_started_at, e, {"output_path": output_path})
            self.logger.error(f"模块数据导出失败: {e}")
            return False
    
    def get_module_health(self) -> Dict[str, Any]:
        """
        获取模块健康状态
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        return {
            "module_name": self.module_name,
            "status": self.status,
            "initialized": self.initialized,
            "health_score": self._calculate_health_score(),
            "performance_metrics": self._serialize_value(self.metrics),
            "resource_usage": self._get_resource_usage(),
            "quality_assessment": self._get_quality_assessment(),
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def _calculate_health_score(self) -> float:
        """计算健康评分"""
        # 基于多个指标计算健康评分
        score_components = []
        
        # 成功率
        if self.metrics["execution_count"] > 0 and self.performance_history:
            success_count = sum(1 for h in self.performance_history if h.get("success", False))
            success_rate = success_count / len(self.performance_history)
        else:
            success_rate = 0.0
        score_components.append(success_rate * 0.4)
        
        # 平均执行时间（越快越好，但需要在合理范围内）
        avg_time = self.metrics["total_execution_time"] / max(1, self.metrics["execution_count"])
        time_score = max(0.0, 1.0 - (avg_time / 10.0))  # 假设10秒为最长时间
        score_components.append(time_score * 0.3)
        
        # 质量评分
        quality_score = self.metrics["quality_score"]
        score_components.append(quality_score * 0.3)
        
        return sum(score_components) if score_components else 0.0
    
    def _get_resource_usage(self) -> Dict[str, Any]:
        """获取资源使用情况"""
        return {
            # 直接访问 _threads 属于内部实现，增加异常处理以防未来变更
            "thread_count": self._get_thread_count(),
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "network_usage": 0.0,
        }

    def _get_thread_count(self) -> int:
        """获取线程池当前线程数"""
        return len(self.executor._threads) if hasattr(self.executor, "_threads") else 0
    
    def _get_quality_assessment(self) -> Dict[str, Any]:
        """获取质量评估"""
        return {
            "quality_score": self.metrics["quality_score"],
            "performance_score": self.metrics["performance_score"],
            "academic_relevance": self.metrics["academic_relevance"],
            "compliance_score": 0.95,  # 简化实现
            "overall_quality": (
                self.metrics["quality_score"] * 0.4 +
                self.metrics["performance_score"] * 0.3 +
                self.metrics["academic_relevance"] * 0.3
            )
        }

# 异步模块基类
class AsyncBaseModule(BaseModule):
    """
    异步模块基类
    
    支持异步执行的模块基类，适用于需要异步处理的场景。
    """
    
    async def async_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步执行模块功能
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        if not self.initialized:
            raise RuntimeError(f"模块 {self.module_name} 未初始化")
        
        start_time = time.time()
        phase_started_at = self._start_phase(
            "async_execute",
            {"module_name": self.module_name, "context_keys": sorted(context.keys())},
        )
        self.module_start_time = start_time
        self.logger.info(f"开始异步执行模块: {self.module_name}")
        
        try:
            # 异步执行具体逻辑
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, self._do_execute, context
            )
            
            # 更新指标
            execution_time = time.time() - start_time
            self._update_metrics(result, execution_time)
            
            # 记录执行历史
            self._record_execution_history(result, execution_time)
            
            # 生成学术洞察
            self._generate_academic_insights(result)
            
            # 生成改进建议
            self._generate_recommendations(result)
            self.final_status = "completed"
            self._complete_phase(
                "async_execute",
                phase_started_at,
                {"context_keys": sorted(context.keys())},
                final_status="completed",
            )
            
            self.logger.info(f"模块 {self.module_name} 异步执行成功，耗时: {execution_time:.2f}s")
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"模块 {self.module_name} 异步执行失败: {e}")
            self.logger.error(traceback.format_exc())
            
            # 更新错误指标
            self.metrics["last_execution_time"] = execution_time
            self.metrics["last_success"] = False
            
            # 记录错误执行历史
            self._record_execution_history({"error": str(e)}, execution_time)
            self._fail_phase(
                "async_execute",
                phase_started_at,
                e,
                {"module_name": self.module_name, "context_keys": sorted(context.keys())},
            )
            
            raise

# 导出主要类和函数
__all__ = [
    'BaseModule',
    'AsyncBaseModule'
]
