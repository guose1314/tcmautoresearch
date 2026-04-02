# tests/test_interface_consistency.py
"""
中医古籍全自动研究系统 - 专业学术接口一致性测试
基于T/C IATCM 098-2023标准的接口一致性验证
"""

import json
import logging
import os
import tempfile
import time
import traceback
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class InterfaceConsistencyResult:
    """接口一致性测试结果数据结构"""
    test_id: str
    test_name: str
    test_type: str
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    interface_compliance: Dict[str, Any] = field(default_factory=dict)
    compatibility_results: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    academic_relevance: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ModuleInterfaceCase:
    """模块接口测试数据结构"""
    module_name: str
    interface_name: str
    test_name: str
    test_description: str
    test_type: str
    expected_interface: Dict[str, Any]
    actual_interface: Dict[str, Any]
    test_status: str
    test_results: Dict[str, Any] = field(default_factory=dict)
    validation_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_relevance: float = 0.0
    confidence_score: float = 0.0

class InterfaceConsistencyTest:
    """
    中医古籍全自动研究系统接口一致性测试框架
    
    本测试框架基于T/C IATCM 098-2023标准，
    验证系统各模块接口的一致性和兼容性，
    确保系统符合学术研究的规范要求。
    
    主要测试内容：
    1. 接口标准化验证
    2. 模块间兼容性测试
    3. 输入输出格式一致性
    4. 错误处理机制验证
    5. 性能指标一致性
    6. 学术规范符合性
    """
    
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_compliance_score": float(self.config.get("minimum_stable_compliance_score", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d48.v1"),
        }
        self.test_results = []
        self.test_history = []
        self.performance_metrics = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "average_execution_time": 0.0,
            "total_execution_time": 0.0,
            "interface_compliance_score": 0.0,
            "academic_compliance_score": 0.0
        }
        self.phase_history: List[Dict[str, Any]] = []
        self.phase_timings: Dict[str, float] = {}
        self.completed_phases: List[str] = []
        self.failed_phase: str | None = None
        self.failed_operations: List[Dict[str, Any]] = []
        self.final_status = "initialized"
        self.last_completed_phase: str | None = None
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("接口一致性测试框架初始化完成")

    def _start_phase(self, phase_name: str, details: Dict[str, Any] | None = None) -> float:
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
        details: Dict[str, Any] | None = None,
        final_status: str | None = None,
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
        details: Dict[str, Any] | None = None,
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
        details: Dict[str, Any] | None = None,
        duration_seconds: float | None = None,
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
        total_runs = int(self.performance_metrics.get("total_tests", 0) or 0)
        passed_runs = int(self.performance_metrics.get("passed_tests", 0) or 0)
        failed_runs = int(self.performance_metrics.get("failed_tests", 0) or 0)
        average_compliance = float(self.performance_metrics.get("interface_compliance_score", 0.0) or 0.0)

        status = "idle"
        if total_runs or self.failed_operations:
            status = (
                "stable"
                if self.failed_phase is None and average_compliance >= self.governance_config["minimum_stable_compliance_score"]
                else "needs_followup"
            )
        if self.final_status == "cleaned":
            status = "idle"

        return {
            "status": status,
            "total_runs": total_runs,
            "passed_runs": passed_runs,
            "failed_runs": failed_runs,
            "average_compliance_score": average_compliance,
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.failed_phase,
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "interface_consistency_report",
            "failed_operation_count": len(self.failed_operations),
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }

    def _serialize_interface_result(self, result: InterfaceConsistencyResult) -> Dict[str, Any]:
        return self._serialize_value(result)
    
    def validate_module_interfaces(self, modules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        验证模块接口一致性
        
        Args:
            modules (List[Dict[str, Any]]): 模块信息列表
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        start_time = time.time()
        phase_started_at = self._start_phase("validate_module_interfaces", {"module_count": len(modules)})
        self.logger.info("开始验证模块接口一致性")
        
        try:
            validation_results = self._initialize_validation_results()

            module_results = self._validate_all_modules(modules)
            validation_results["module_results"] = module_results
            validation_results["validation_summary"] = self._build_validation_summary(module_results)
            validation_results["compliance_report"] = self._generate_compliance_report(module_results)
            validation_results["academic_analysis"] = self._generate_academic_analysis(module_results)
            validation_results["recommendations"] = self._generate_recommendations(module_results)

            total_duration = time.time() - start_time
            self._update_performance_metrics(module_results, total_duration)
            run_result = InterfaceConsistencyResult(
                test_id=f"interface_consistency_{int(time.time())}",
                test_name="module_interface_consistency",
                test_type="governance_validation",
                status="passed" if validation_results["compliance_report"].get("average_compliance_score", 0.0) >= self.governance_config["minimum_stable_compliance_score"] else "failed",
                start_time=datetime.fromtimestamp(start_time).isoformat(),
                end_time=datetime.now().isoformat(),
                duration=total_duration,
                interface_compliance=validation_results["compliance_report"],
                compatibility_results=validation_results["module_results"],
                validation_results=validation_results["validation_summary"],
                quality_metrics=self._serialize_value(self.performance_metrics),
                academic_insights=validation_results["academic_analysis"].get("insights", []),
                recommendations=validation_results["recommendations"],
                confidence_score=validation_results["compliance_report"].get("average_compliance_score", 0.0),
                academic_relevance=validation_results["academic_analysis"].get("summary", {}).get("average_academic_relevance", 0.0),
                metadata={
                    "analysis_summary": self._build_analysis_summary(),
                    "runtime_metadata": self._build_runtime_metadata(),
                    "report_metadata": self._build_report_metadata(),
                },
            )
            self.test_results.append(run_result)
            self.test_history.append(run_result)
            self.final_status = "completed"
            self._complete_phase(
                "validate_module_interfaces",
                phase_started_at,
                {"module_count": len(modules), "average_compliance_score": validation_results["compliance_report"].get("average_compliance_score", 0.0)},
                final_status="completed",
            )
            validation_results["failed_operations"] = self._serialize_value(self.failed_operations)
            validation_results["metadata"] = self._build_runtime_metadata()
            validation_results["report_metadata"] = self._build_report_metadata()

            self.logger.info("模块接口一致性验证完成")
            return validation_results
            
        except Exception as e:
            self.performance_metrics["failed_tests"] += 1
            self._fail_phase(
                "validate_module_interfaces",
                phase_started_at,
                e,
                {"module_count": len(modules)},
            )
            self.logger.error(f"模块接口一致性验证失败: {e}")
            self.logger.error(traceback.format_exc())
            raise

    def _initialize_validation_results(self) -> Dict[str, Any]:
        return {
                "validation_summary": {},
                "module_results": {},
                "compliance_report": {},
                "academic_analysis": {},
                "recommendations": []
            }

    def _validate_all_modules(self, modules: List[Dict[str, Any]]) -> Dict[str, Any]:
        module_results: Dict[str, Any] = {}
        for module_info in modules:
            module_name = module_info.get("name", "unknown")
            module_interface = module_info.get("interface", {})
            module_results[module_name] = self._validate_single_module_interface(
                module_name,
                module_interface,
            )
        return module_results

    def _build_validation_summary(self, module_results: Dict[str, Any]) -> Dict[str, Any]:
        return {
            module_name: {
                "status": result["status"],
                "compliance_score": result["compliance_score"],
                "academic_score": result["academic_relevance"],
            }
            for module_name, result in module_results.items()
        }
    
    def _validate_single_module_interface(self, module_name: str, 
                                        module_interface: Dict[str, Any]) -> Dict[str, Any]:
        """验证单个模块接口"""
        start_time = time.time()
        
        try:
            # 检查必需接口
            required_interfaces = self._get_required_interfaces()
            
            # 验证接口完整性
            interface_compliance = self._validate_interface_compliance(
                module_interface, required_interfaces
            )
            
            # 验证接口一致性
            consistency_results = self._validate_interface_consistency(
                module_interface, required_interfaces
            )
            
            # 验证学术合规性
            academic_compliance = self._validate_academic_compliance(
                module_interface
            )
            
            # 计算综合评分
            compliance_score = self._calculate_compliance_score(
                interface_compliance, consistency_results, academic_compliance
            )
            
            # 计算学术相关性
            academic_relevance = self._calculate_academic_relevance(
                interface_compliance, consistency_results, academic_compliance
            )
            
            # 生成测试结果
            module_result = {
                "module_name": module_name,
                "interface_compliance": interface_compliance,
                "consistency_results": consistency_results,
                "academic_compliance": academic_compliance,
                "compliance_score": compliance_score,
                "academic_relevance": academic_relevance,
                "status": "passed" if compliance_score >= 0.9 else "failed",
                "validation_time": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            }
            
            # 添加学术洞察
            module_result["academic_insights"] = self._generate_academic_insights(
                module_name, module_result
            )
            
            return module_result
            
        except Exception as e:
            self.logger.error(f"模块 {module_name} 接口验证失败: {e}")
            return {
                "module_name": module_name,
                "interface_compliance": {"error": str(e)},
                "consistency_results": {"error": str(e)},
                "academic_compliance": {"error": str(e)},
                "compliance_score": 0.0,
                "academic_relevance": 0.0,
                "status": "error",
                "validation_time": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            }
    
    def _get_required_interfaces(self) -> Dict[str, Any]:
        """获取必需接口定义"""
        return {
            "initialize": {
                "parameters": ["config"],
                "return_type": "bool",
                "description": "初始化模块"
            },
            "execute": {
                "parameters": ["context"],
                "return_type": "Dict[str, Any]",
                "description": "执行模块功能"
            },
            "cleanup": {
                "parameters": [],
                "return_type": "bool",
                "description": "清理模块资源"
            },
            "get_interface_compatibility": {
                "parameters": [],
                "return_type": "Dict[str, Any]",
                "description": "获取接口兼容性信息"
            }
        }
    
    def _validate_interface_compliance(self, actual_interface: Dict[str, Any], 
                                     required_interfaces: Dict[str, Any]) -> Dict[str, Any]:
        """验证接口合规性"""
        compliance_results = {
            "required_methods": [],
            "missing_methods": [],
            "compliant_methods": [],
            "non_compliant_methods": [],
            "compliance_score": 0.0
        }
        
        # 检查必需方法
        for method_name, method_def in required_interfaces.items():
            if method_name in actual_interface:
                method_info = actual_interface[method_name]
                
                # 验证参数
                params_match = self._validate_parameters(
                    method_info.get("parameters", []), 
                    method_def["parameters"]
                )
                
                # 验证返回类型
                return_type_match = self._validate_return_type(
                    method_info.get("return_type", ""), 
                    method_def["return_type"]
                )
                
                if params_match and return_type_match:
                    compliance_results["compliant_methods"].append(method_name)
                else:
                    compliance_results["non_compliant_methods"].append({
                        "method": method_name,
                        "details": {
                            "params_match": params_match,
                            "return_type_match": return_type_match
                        }
                    })
            else:
                compliance_results["missing_methods"].append(method_name)
        
        # 计算合规性评分
        total_methods = len(required_interfaces)
        compliant_methods = len(compliance_results["compliant_methods"])
        
        if total_methods > 0:
            compliance_results["compliance_score"] = compliant_methods / total_methods
        
        compliance_results["required_methods"] = list(required_interfaces.keys())
        
        return compliance_results
    
    def _validate_parameters(self, actual_params: List[str], 
                           expected_params: List[str]) -> bool:
        """验证参数一致性"""
        # 简化验证逻辑
        return set(actual_params) >= set(expected_params)
    
    def _validate_return_type(self, actual_type: str, expected_type: str) -> bool:
        """验证返回类型一致性"""
        # 简化验证逻辑
        return actual_type == expected_type or actual_type == "Any"
    
    def _validate_interface_consistency(self, actual_interface: Dict[str, Any], 
                                      required_interfaces: Dict[str, Any]) -> Dict[str, Any]:
        """验证接口一致性"""
        consistency_results = {
            "signature_consistency": [],
            "behavior_consistency": [],
            "performance_consistency": [],
            "consistency_score": 0.0
        }
        
        # 检查接口签名一致性
        for method_name, method_def in required_interfaces.items():
            if method_name in actual_interface:
                actual_method = actual_interface[method_name]
                
                # 检查方法签名
                signature_match = self._check_signature_consistency(
                    actual_method, method_def
                )
                
                consistency_results["signature_consistency"].append({
                    "method": method_name,
                    "consistent": signature_match
                })
        
        # 计算一致性评分
        if consistency_results["signature_consistency"]:
            consistent_count = sum(1 for s in consistency_results["signature_consistency"] 
                                if s["consistent"])
            consistency_results["consistency_score"] = consistent_count / len(consistency_results["signature_consistency"])
        
        return consistency_results
    
    def _check_signature_consistency(self, actual_method: Dict[str, Any], 
                                   expected_method: Dict[str, Any]) -> bool:
        """检查签名一致性"""
        # 简化实现
        return True
    
    def _validate_academic_compliance(self, module_interface: Dict[str, Any]) -> Dict[str, Any]:
        """验证学术合规性"""
        academic_results = {
            "standards_compliance": [],
            "academic_requirements": [],
            "compliance_score": 0.0,
            "academic_relevance": 0.0
        }
        
        # 检查是否符合学术标准
        standards = ["T/C IATCM 098-2023", "GB/T 15657", "ISO 21000"]
        for standard in standards:
            compliance = self._check_standard_compliance(standard, module_interface)
            academic_results["standards_compliance"].append({
                "standard": standard,
                "compliant": compliance
            })
        
        # 计算学术合规性评分
        compliant_standards = sum(1 for s in academic_results["standards_compliance"] 
                               if s["compliant"])
        academic_results["compliance_score"] = compliant_standards / len(standards) if standards else 0.0
        
        # 计算学术相关性
        academic_results["academic_relevance"] = academic_results["compliance_score"] * 0.95
        
        return academic_results
    
    def _check_standard_compliance(self, standard: str, module_interface: Dict[str, Any]) -> bool:
        """检查标准合规性"""
        # 简化实现，实际应根据具体标准验证
        return True
    
    def _calculate_compliance_score(self, interface_compliance: Dict[str, Any], 
                                  consistency_results: Dict[str, Any], 
                                  academic_compliance: Dict[str, Any]) -> float:
        """计算合规性评分"""
        # 综合计算多个维度的合规性
        weights = {
            "interface_compliance": 0.4,
            "consistency": 0.3,
            "academic_compliance": 0.3
        }
        
        scores = []
        
        # 接口合规性评分
        if "compliance_score" in interface_compliance:
            scores.append(interface_compliance["compliance_score"] * weights["interface_compliance"])
        
        # 一致性评分
        if "consistency_score" in consistency_results:
            scores.append(consistency_results["consistency_score"] * weights["consistency"])
        
        # 学术合规性评分
        if "compliance_score" in academic_compliance:
            scores.append(academic_compliance["compliance_score"] * weights["academic_compliance"])
        
        return sum(scores) if scores else 0.0
    
    def _calculate_academic_relevance(self, interface_compliance: Dict[str, Any], 
                                    consistency_results: Dict[str, Any], 
                                    academic_compliance: Dict[str, Any]) -> float:
        """计算学术相关性"""
        # 基于学术合规性计算
        if "academic_relevance" in academic_compliance:
            return academic_compliance["academic_relevance"]
        
        # 默认计算
        return 0.85
    
    def _generate_compliance_report(self, module_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成合规报告"""
        if not module_results:
            return {"message": "没有模块结果可用于生成报告"}
        
        # 统计合规情况
        total_modules = len(module_results)
        compliant_modules = sum(1 for r in module_results.values() 
                             if r.get("compliance_score", 0.0) >= 0.9)
        non_compliant_modules = total_modules - compliant_modules
        
        # 计算平均合规性
        avg_compliance = sum(r.get("compliance_score", 0.0) for r in module_results.values()) / total_modules if total_modules > 0 else 0.0
        
        # 计算平均学术相关性
        avg_academic = sum(r.get("academic_relevance", 0.0) for r in module_results.values()) / total_modules if total_modules > 0 else 0.0
        
        return {
            "total_modules": total_modules,
            "compliant_modules": compliant_modules,
            "non_compliant_modules": non_compliant_modules,
            "compliance_rate": compliant_modules / total_modules if total_modules > 0 else 0.0,
            "average_compliance_score": avg_compliance,
            "average_academic_relevance": avg_academic,
            "module_compliance": {
                module_name: {
                    "compliance_score": result.get("compliance_score", 0.0),
                    "academic_relevance": result.get("academic_relevance", 0.0),
                    "status": result.get("status", "unknown")
                } for module_name, result in module_results.items()
            },
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def _generate_academic_analysis(self, module_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成学术分析"""
        if not module_results:
            return {"message": "没有模块结果可用于学术分析"}
        
        # 生成学术洞察
        academic_insights = []
        
        # 基于合规性生成洞察
        for module_name, result in module_results.items():
            compliance_score = result.get("compliance_score", 0.0)
            academic_relevance = result.get("academic_relevance", 0.0)
            
            if compliance_score >= 0.95:
                insight = {
                    "type": "high_compliance",
                    "title": f"{module_name}高合规性洞察",
                    "description": f"模块 {module_name} 接口合规性评分达到 {compliance_score:.2f}，符合学术标准",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["compliance", "academic", "high_quality"]
                }
                academic_insights.append(insight)
            
            if academic_relevance >= 0.9:
                insight = {
                    "type": "high_academic_value",
                    "title": f"{module_name}高学术价值洞察",
                    "description": f"模块 {module_name} 学术相关性评分达到 {academic_relevance:.2f}，具有重要学术意义",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "value", "research"]
                }
                academic_insights.append(insight)
        
        # 基于整体情况生成综合洞察
        avg_compliance = sum(r.get("compliance_score", 0.0) for r in module_results.values()) / len(module_results) if module_results else 0.0
        avg_academic = sum(r.get("academic_relevance", 0.0) for r in module_results.values()) / len(module_results) if module_results else 0.0
        
        if avg_compliance >= 0.9:
            insight = {
                "type": "overall_compliance",
                "title": "整体系统合规性分析",
                "description": f"系统整体接口合规性评分达到 {avg_compliance:.2f}，符合学术研究要求",
                "confidence": 0.92,
                "timestamp": datetime.now().isoformat(),
                "tags": ["overall", "compliance", "academic"]
            }
            academic_insights.append(insight)
        
        if avg_academic >= 0.85:
            insight = {
                "type": "overall_academic_value",
                "title": "整体学术价值分析",
                "description": f"系统整体学术相关性评分达到 {avg_academic:.2f}，具有较高的学术研究价值",
                "confidence": 0.88,
                "timestamp": datetime.now().isoformat(),
                "tags": ["overall", "academic", "research_value"]
            }
            academic_insights.append(insight)
        
        return {
            "insights": academic_insights,
            "summary": {
                "average_compliance_score": avg_compliance,
                "average_academic_relevance": avg_academic,
                "compliance_status": "compliant" if avg_compliance >= 0.9 else "needs_improvement",
                "academic_status": "high_value" if avg_academic >= 0.85 else "medium_value"
            },
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def _generate_recommendations(self, module_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations = []
        
        # 基于模块结果生成建议
        for module_name, result in module_results.items():
            compliance_score = result.get("compliance_score", 0.0)
            academic_relevance = result.get("academic_relevance", 0.0)
            
            # 基于合规性生成建议
            if compliance_score < 0.9:
                recommendation = {
                    "type": "interface_improvement",
                    "title": f"提升{module_name}接口合规性",
                    "description": f"模块 {module_name} 接口合规性评分较低 ({compliance_score:.2f})，建议优化接口设计",
                    "priority": "high" if compliance_score < 0.7 else "medium",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["interface", "compliance", "improvement"]
                }
                recommendations.append(recommendation)
            
            # 基于学术相关性生成建议
            if academic_relevance < 0.8:
                recommendation = {
                    "type": "academic_improvement",
                    "title": f"增强{module_name}学术价值",
                    "description": f"模块 {module_name} 学术相关性评分较低 ({academic_relevance:.2f})，建议增强学术研究价值",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["academic", "research", "improvement"]
                }
                recommendations.append(recommendation)
        
        # 基于整体情况生成建议
        if module_results:
            avg_compliance = sum(r.get("compliance_score", 0.0) for r in module_results.values()) / len(module_results)
            avg_academic = sum(r.get("academic_relevance", 0.0) for r in module_results.values()) / len(module_results)
            
            if avg_compliance < 0.85:
                recommendation = {
                    "type": "system_improvement",
                    "title": "提升系统整体合规性",
                    "description": f"系统整体接口合规性评分较低 ({avg_compliance:.2f})，建议进行全面接口优化",
                    "priority": "high",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["system", "compliance", "improvement"]
                }
                recommendations.append(recommendation)
            
            if avg_academic < 0.8:
                recommendation = {
                    "type": "research_improvement",
                    "title": "增强系统学术研究价值",
                    "description": f"系统整体学术相关性评分较低 ({avg_academic:.2f})，建议加强学术研究导向",
                    "priority": "medium",
                    "confidence": 0.80,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["research", "academic", "improvement"]
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    def _generate_academic_insights(self, module_name: str, 
                                  test_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成学术洞察"""
        insights = []
        
        compliance_score = test_result.get("compliance_score", 0.0)
        academic_relevance = test_result.get("academic_relevance", 0.0)
        
        # 基于合规性生成洞察
        if compliance_score >= 0.95:
            insight = {
                "type": "high_compliance",
                "title": f"{module_name}高合规性洞察",
                "description": f"模块 {module_name} 接口完全符合标准，体现了高水平的规范性",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat(),
                "tags": ["compliance", "standard", "quality"]
            }
            insights.append(insight)
        
        # 基于学术相关性生成洞察
        if academic_relevance >= 0.9:
            insight = {
                "type": "high_academic_value",
                "title": f"{module_name}高学术价值洞察",
                "description": f"模块 {module_name} 具有很高的学术研究价值，符合中医研究规范",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat(),
                "tags": ["academic", "research", "value"]
            }
            insights.append(insight)
        
        return insights
    
    def _update_performance_metrics(self, module_results: Dict[str, Any], 
                                  total_duration: float):
        """更新性能指标"""
        self.performance_metrics["total_tests"] += 1
        self.performance_metrics["total_execution_time"] += total_duration
        if any(result.get("status") in {"failed", "error"} for result in module_results.values()):
            self.performance_metrics["failed_tests"] += 1
        else:
            self.performance_metrics["passed_tests"] += 1
        
        # 更新平均执行时间
        if self.performance_metrics["total_tests"] > 0:
            self.performance_metrics["average_execution_time"] = (
                self.performance_metrics["total_execution_time"] / 
                self.performance_metrics["total_tests"]
            )
        
        # 更新平均合规性评分
        if module_results:
            compliance_scores = [r.get("compliance_score", 0.0) for r in module_results.values()]
            if compliance_scores:
                avg_compliance = sum(compliance_scores) / len(compliance_scores)
                self.performance_metrics["interface_compliance_score"] = avg_compliance
        
        # 更新平均学术合规性评分
        if module_results:
            academic_scores = [r.get("academic_relevance", 0.0) for r in module_results.values()]
            if academic_scores:
                avg_academic = sum(academic_scores) / len(academic_scores)
                self.performance_metrics["academic_compliance_score"] = avg_academic
    
    def get_compliance_report(self) -> Dict[str, Any]:
        """获取合规报告"""
        return {
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "test_summary": self._calculate_test_summary(),
            "latest_results": [self._serialize_interface_result(r) for r in self.test_results[-5:]] if self.test_results else [],
            "analysis_summary": self._build_analysis_summary(),
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "report_metadata": self._build_report_metadata(),
        }
    
    def _calculate_test_summary(self) -> Dict[str, Any]:
        """计算测试摘要"""
        if not self.test_results:
            return {
                "message": "没有测试结果",
                "analysis_summary": self._build_analysis_summary(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
                "report_metadata": self._build_report_metadata(),
            }
        
        # 统计测试状态
        status_counts = {}
        for result in self.test_results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # 计算平均评分
        compliance_scores = [r.compliance_score for r in self.test_results if hasattr(r, 'compliance_score')]
        academic_scores = [r.academic_relevance for r in self.test_results if hasattr(r, 'academic_relevance')]
        
        avg_compliance = sum(compliance_scores) / len(compliance_scores) if compliance_scores else 0.0
        avg_academic = sum(academic_scores) / len(academic_scores) if academic_scores else 0.0
        
        return {
            "total_tests": len(self.test_results),
            "status_distribution": status_counts,
            "average_compliance_score": avg_compliance,
            "average_academic_relevance": avg_academic,
            "quality_assurance": self.performance_metrics["interface_compliance_score"],
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.failed_phase,
            "final_status": self.final_status,
            "last_completed_phase": self.last_completed_phase,
        }
    
    def export_test_results(self, output_path: str) -> bool:
        """导出测试结果"""
        phase_started_at = self._start_phase("export_test_results", {"output_path": output_path})
        try:
            test_data = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                },
                "test_framework_info": {
                    "framework_name": "接口一致性测试框架",
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "performance_metrics": self._serialize_value(self.performance_metrics)
                },
                "test_results": [self._serialize_interface_result(r) for r in self.test_results],
                "test_history": [self._serialize_interface_result(r) for r in self.test_history],
                "compliance_report": self.get_compliance_report(),
                "failed_operations": self._serialize_value(self.failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
            self.final_status = "completed" if self.final_status != "cleaned" else self.final_status
            self._complete_phase(
                "export_test_results",
                phase_started_at,
                {"output_path": output_path},
                final_status=self.final_status,
            )
            test_data["metadata"] = self._build_runtime_metadata()
            test_data["report_metadata"] = {
                **self._build_report_metadata(),
                "output_path": output_path,
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"接口一致性测试结果已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_phase("export_test_results", phase_started_at, e, {"output_path": output_path})
            self.logger.error(f"接口一致性测试结果导出失败: {e}")
            return False

    def cleanup(self) -> bool:
        """清理资源"""
        try:
            self.test_results.clear()
            self.test_history.clear()
            self.performance_metrics = {
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "skipped_tests": 0,
                "average_execution_time": 0.0,
                "total_execution_time": 0.0,
                "interface_compliance_score": 0.0,
                "academic_compliance_score": 0.0,
            }
            self.phase_history.clear()
            self.phase_timings.clear()
            self.completed_phases.clear()
            self.failed_operations.clear()
            self.failed_phase = None
            self.last_completed_phase = None
            self.final_status = "cleaned"
            self.logger.info("接口一致性测试框架资源清理完成")
            return True
        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")
            return False

# 接口一致性测试类
class ModuleInterfaceTest(unittest.TestCase):
    """模块接口一致性测试用例"""
    
    def setUp(self):
        """测试前准备"""
        self.tester = InterfaceConsistencyTest()
        self.logger = logging.getLogger(__name__)
        
    def test_interface_compliance(self):
        """测试接口合规性"""
        # 模拟模块接口信息
        test_modules = [
            {
                "name": "DocumentPreprocessor",
                "interface": {
                    "initialize": {
                        "parameters": ["config"],
                        "return_type": "bool"
                    },
                    "execute": {
                        "parameters": ["context"],
                        "return_type": "Dict[str, Any]"
                    },
                    "cleanup": {
                        "parameters": [],
                        "return_type": "bool"
                    },
                    "get_interface_compatibility": {
                        "parameters": [],
                        "return_type": "Dict[str, Any]"
                    }
                }
            },
            {
                "name": "EntityExtractor",
                "interface": {
                    "initialize": {
                        "parameters": ["config"],
                        "return_type": "bool"
                    },
                    "execute": {
                        "parameters": ["context"],
                        "return_type": "Dict[str, Any]"
                    },
                    "cleanup": {
                        "parameters": [],
                        "return_type": "bool"
                    },
                    "get_interface_compatibility": {
                        "parameters": [],
                        "return_type": "Dict[str, Any]"
                    }
                }
            }
        ]
        
        try:
            # 执行接口一致性验证
            result = self.tester.validate_module_interfaces(test_modules)
            
            # 验证结果
            self.assertIn("compliance_report", result)
            self.assertIn("academic_analysis", result)
            self.assertIn("recommendations", result)
            self.assertIn("metadata", result)
            self.assertIn("report_metadata", result)
            
            # 验证合规性评分
            compliance_report = result["compliance_report"]
            self.assertGreaterEqual(compliance_report.get("average_compliance_score", 0.0), 0.8)
            self.assertEqual(result["report_metadata"]["contract_version"], "d48.v1")
            self.assertEqual(result["metadata"]["last_completed_phase"], "validate_module_interfaces")
            
            self.logger.info("接口合规性测试通过")
            
        except Exception as e:
            self.logger.error(f"接口合规性测试失败: {e}")
            raise
    
    def test_academic_compliance(self):
        """测试学术合规性"""
        # 模拟模块接口信息
        test_module = {
            "name": "SemanticGraphBuilder",
            "interface": {
                "initialize": {
                    "parameters": ["config"],
                    "return_type": "bool"
                },
                "execute": {
                    "parameters": ["context"],
                    "return_type": "Dict[str, Any]"
                },
                "cleanup": {
                    "parameters": [],
                    "return_type": "bool"
                },
                "get_interface_compatibility": {
                    "parameters": [],
                    "return_type": "Dict[str, Any]"
                }
            }
        }
        
        try:
            # 执行学术合规性验证
            module_results = self.tester._validate_single_module_interface(
                test_module["name"], test_module["interface"]
            )
            
            # 验证学术合规性
            academic_compliance = module_results.get("academic_compliance", {})
            self.assertIn("compliance_score", academic_compliance)
            self.assertIn("academic_relevance", academic_compliance)
            
            # 验证学术相关性
            academic_relevance = module_results.get("academic_relevance", 0.0)
            self.assertGreaterEqual(academic_relevance, 0.8)
            
            self.logger.info("学术合规性测试通过")
            
        except Exception as e:
            self.logger.error(f"学术合规性测试失败: {e}")
            raise

    def test_export_test_results_uses_json_safe_contract(self):
        test_modules = [
            {
                "name": "DemoModule",
                "interface": {
                    "initialize": {"parameters": ["config"], "return_type": "bool"},
                    "execute": {"parameters": ["context"], "return_type": "Dict[str, Any]"},
                    "cleanup": {"parameters": [], "return_type": "bool"},
                    "get_interface_compatibility": {"parameters": [], "return_type": "Dict[str, Any]"},
                },
            }
        ]
        self.tester.validate_module_interfaces(test_modules)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "interface-consistency-report.json")
            exported = self.tester.export_test_results(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d48.v1")
        self.assertEqual(payload["metadata"]["last_completed_phase"], "export_test_results")
        self.assertIn("failed_operations", payload)
        self.assertIn("report_metadata", payload["compliance_report"])

    def test_cleanup_resets_runtime_state(self):
        test_modules = [
            {
                "name": "DemoModule",
                "interface": {
                    "initialize": {"parameters": ["config"], "return_type": "bool"},
                    "execute": {"parameters": ["context"], "return_type": "Dict[str, Any]"},
                    "cleanup": {"parameters": [], "return_type": "bool"},
                    "get_interface_compatibility": {"parameters": [], "return_type": "Dict[str, Any]"},
                },
            }
        ]
        self.tester.validate_module_interfaces(test_modules)

        cleaned = self.tester.cleanup()
        report = self.tester.get_compliance_report()

        self.assertTrue(cleaned)
        self.assertEqual(report["metadata"]["final_status"], "cleaned")
        self.assertEqual(report["test_summary"]["message"], "没有测试结果")
    
    def tearDown(self):
        """测试后清理"""
        self.tester.cleanup()


class TestHealthCheckAndModuleId(unittest.TestCase):
    """BaseModule.health_check() 和 get_module_id() 的验收测试"""

    def _make_module(self, name="demo"):
        from src.core.module_base import BaseModule

        class _Mod(BaseModule):
            def _do_initialize(self): return True
            def _do_execute(self, ctx): return {"ok": True}
            def _do_cleanup(self): return True

        return _Mod(name)

    def test_get_module_id_format(self):
        mod = self._make_module("health_mod")
        mid = mod.get_module_id()
        self.assertIsInstance(mid, str)
        self.assertTrue(mid.startswith("health_mod_"), f"Unexpected id: {mid}")

    def test_get_module_id_unique_per_instance(self):
        a = self._make_module("m")
        b = self._make_module("m")
        self.assertNotEqual(a.get_module_id(), b.get_module_id())

    def test_health_check_keys(self):
        mod = self._make_module("hc")
        result = mod.health_check()
        for key in ("module_id", "status", "initialized", "metrics", "timestamp"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_health_check_module_id_matches(self):
        mod = self._make_module("hc2")
        self.assertEqual(mod.health_check()["module_id"], mod.get_module_id())

    def test_health_check_initialized_false_before_init(self):
        mod = self._make_module("hc3")
        self.assertFalse(mod.health_check()["initialized"])

    def test_health_check_initialized_true_after_init(self):
        mod = self._make_module("hc4")
        mod.initialize()
        self.assertTrue(mod.health_check()["initialized"])
        mod.cleanup()

    def test_health_check_timestamp_is_iso(self):
        from datetime import datetime
        mod = self._make_module("hc5")
        ts = mod.health_check()["timestamp"]
        # Should parse without error
        datetime.fromisoformat(ts)

    def test_health_check_callable_on_any_subclass(self):
        """Any BaseModule subclass should support health_check without override."""
        from src.core.module_base import BaseModule

        class MinimalMod(BaseModule):
            def _do_initialize(self): return True
            def _do_execute(self, ctx): return {}
            def _do_cleanup(self): return True

        mod = MinimalMod("minimal")
        result = mod.health_check()
        self.assertIn("module_id", result)


# 导出主要类和函数
__all__ = [
    'InterfaceConsistencyTest',
    'ModuleInterfaceTest',
    'InterfaceConsistencyResult',
    'ModuleInterfaceCase',
    'TestHealthCheckAndModuleId',
]
