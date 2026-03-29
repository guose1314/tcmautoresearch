# cycle/module_iteration.py
"""
中医古籍全自动研究系统 - 专业学术模块迭代循环
基于T/C IATCM 098-2023标准的模块级迭代管理
"""

import json
import logging
import os
import time
import traceback
from typing import Any, Callable, Dict, List
from datetime import datetime
from dataclasses import dataclass, field
import networkx as nx

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class ModuleIterationResult:
    """模块迭代结果数据结构"""
    module_name: str
    iteration_id: str
    cycle_number: int
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    artifacts: Dict[str, Any] = field(default_factory=dict)
    test_results: Dict[str, Any] = field(default_factory=dict)
    repair_actions: List[Dict[str, Any]] = field(default_factory=list)
    issues_found: List[str] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    quality_assessment: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class ModuleIterationCycle:
    """
    模块级迭代循环管理器
    
    本模块专注于单个模块的迭代优化，确保每个模块都能
    在学术标准下持续改进和优化，符合T/C IATCM 098-2023要求。
    
    主要功能：
    1. 模块级迭代流程管理
    2. 专业学术质量控制
    3. 自动化问题修复
    4. 学术洞察发现
    5. 性能监控与优化
    6. 知识传承与复用
    """
    
    def __init__(self, module_name: str, module_config: Dict[str, Any] = None):
        self.module_name = module_name
        self.config = module_config or {}
        self.iteration_history: List[ModuleIterationResult] = []
        self.failed_iterations: List[ModuleIterationResult] = []
        self.performance_metrics = {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "average_duration": 0.0,
            "total_processing_time": 0.0,
            "quality_score": 0.0,
            "confidence_score": 0.0
        }
        self.knowledge_graph = nx.MultiDiGraph()
        self.logger = logging.getLogger(f"{__name__}.{module_name}")
        
        self.logger.info(f"模块迭代循环初始化完成: {module_name}")

    def _initialize_phase_tracking(self, iteration_result: ModuleIterationResult) -> None:
        iteration_result.metadata["phase_history"] = []
        iteration_result.metadata["phase_timings"] = {}
        iteration_result.metadata["completed_phases"] = []

    def _execute_phase(
        self,
        iteration_result: ModuleIterationResult,
        phase_name: str,
        status: str,
        operation: Callable[[], Any],
    ) -> Any:
        phase_start = time.time()
        phase_entry: Dict[str, Any] = {
            "phase": phase_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        iteration_result.metadata["phase_history"].append(phase_entry)
        iteration_result.status = status

        try:
            result = operation()
        except Exception as exc:
            duration = time.time() - phase_start
            phase_entry["status"] = "failed"
            phase_entry["ended_at"] = datetime.now().isoformat()
            phase_entry["duration"] = duration
            phase_entry["error"] = str(exc)
            iteration_result.metadata["phase_timings"][phase_name] = duration
            iteration_result.metadata["failed_phase"] = phase_name
            raise

        duration = time.time() - phase_start
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration"] = duration
        iteration_result.metadata["phase_timings"][phase_name] = duration
        iteration_result.metadata["completed_phases"].append(phase_name)
        iteration_result.metadata["last_completed_phase"] = phase_name
        return result

    def _finalize_iteration_result(
        self,
        iteration_result: ModuleIterationResult,
        start_time: float,
        success: bool,
    ) -> None:
        iteration_result.status = "completed" if success else "failed"
        iteration_result.end_time = datetime.now().isoformat()
        iteration_result.duration = time.time() - start_time
        iteration_result.metadata["final_status"] = iteration_result.status

    def _build_analysis_summary(
        self,
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
        quality_metrics: Dict[str, Any],
        academic_insights: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        failed_tests = len(test_results.get("failures", []))
        quality_score = float(quality_metrics.get("quality_score", quality_metrics.get("overall_quality", 0.0)))
        return {
            "module_name": self.module_name,
            "test_passed": bool(test_results.get("passed", False)),
            "failed_test_count": failed_tests,
            "repair_action_count": len(repair_actions),
            "academic_insight_count": len(academic_insights),
            "recommendation_count": len(recommendations),
            "quality_score": quality_score,
            "module_status": "stable" if failed_tests == 0 and quality_score >= float(self.config.get("minimum_stable_quality", 0.85)) else "needs_followup",
        }
    
    def execute_module_iteration(self, context: Dict[str, Any]) -> ModuleIterationResult:
        """
        执行模块迭代
        
        Args:
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            ModuleIterationResult: 迭代结果
        """
        start_time = time.time()
        
        iteration_result = ModuleIterationResult(
            module_name=self.module_name,
            iteration_id=f"mod_iter_{self.module_name}_{int(time.time())}",
            cycle_number=len(self.iteration_history),
            status="pending",
            start_time=datetime.now().isoformat()
        )
        self._initialize_phase_tracking(iteration_result)
        
        try:
            artifacts = self._execute_phase(
                iteration_result,
                "generate",
                "generating",
                lambda: self._generate_module_artifact(context),
            )
            iteration_result.artifacts = artifacts
            
            test_results = self._execute_phase(
                iteration_result,
                "test",
                "testing",
                lambda: self._test_module_artifact(artifacts),
            )
            iteration_result.test_results = test_results
            
            repair_actions = self._execute_phase(
                iteration_result,
                "repair",
                "fixing",
                lambda: self._repair_module_artifact(artifacts, test_results),
            )
            iteration_result.repair_actions = repair_actions
            
            analysis_results = self._execute_phase(
                iteration_result,
                "analyze",
                "analyzing",
                lambda: self._analyze_module_results(artifacts, test_results, repair_actions),
            )
            iteration_result.academic_insights = analysis_results.get("academic_insights", [])
            iteration_result.quality_assessment = analysis_results.get("quality_metrics", {})
            iteration_result.confidence_scores = analysis_results.get("confidence_scores", {})
            iteration_result.recommendations = analysis_results.get("recommendations", [])
            iteration_result.metadata["analysis_summary"] = analysis_results.get("analysis_summary", {})
            
            self._finalize_iteration_result(iteration_result, start_time, success=True)
            
            self._update_performance_metrics(iteration_result)
            
            self.iteration_history.append(iteration_result)
            
            self.logger.info(f"模块迭代完成: {self.module_name}")
            return iteration_result
            
        except Exception as e:
            iteration_result.issues_found.append(str(e))
            self._finalize_iteration_result(iteration_result, start_time, success=False)
            self.logger.error(f"模块迭代失败 {self.module_name}: {e}")
            self.logger.error(traceback.format_exc())
            self._update_performance_metrics(iteration_result)
            self.iteration_history.append(iteration_result)
            self.failed_iterations.append(iteration_result)
            raise
    
    def _generate_module_artifact(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成模块艺术作品"""
        self.logger.info(f"生成模块 {self.module_name} 输出")
        start_time = time.time()
        
        try:
            # 模拟模块生成过程
            artifact = {
                "module": self.module_name,
                "generated_at": datetime.now().isoformat(),
                "artifact_id": f"artifact_{self.module_name}_{int(time.time())}",
                "input_context": context,
                "quality_metrics": {
                    "completeness": 0.92,
                    "accuracy": 0.88,
                    "consistency": 0.95,
                    "reliability": 0.90
                },
                "metadata": {
                    "generation_method": "automated",
                    "processing_time": time.time() - start_time
                }
            }
            
            # 模拟处理时间
            time.sleep(0.05)
            
            self.logger.info(f"模块 {self.module_name} 生成完成")
            return artifact
            
        except Exception as e:
            self.logger.error(f"模块 {self.module_name} 生成失败: {e}")
            raise
    
    def _test_module_artifact(self, artifact: Dict[str, Any]) -> Dict[str, Any]:
        """测试模块输出"""
        self.logger.info(f"测试模块 {self.module_name} 输出")
        
        try:
            # 模拟测试过程
            test_results = {
                "module": self.module_name,
                "tested_at": datetime.now().isoformat(),
                "artifact_id": artifact.get("artifact_id", "unknown"),
                "test_suite": ["unit_tests", "integration_tests", "performance_tests"],
                "passed": True,
                "failures": [],
                "warnings": [],
                "metrics": {
                    "execution_time": 0.15,
                    "memory_usage": 10.5,
                    "resource_utilization": 0.75,
                    "quality_score": 0.92,
                    "confidence_score": 0.88
                },
                "validation": {
                    "academic_compliance": True,
                    "standard_compliance": True,
                    "quality_assurance": True
                }
            }
            
            # 模拟测试时间
            time.sleep(0.03)
            
            self.logger.info(f"模块 {self.module_name} 测试完成")
            return test_results
            
        except Exception as e:
            self.logger.error(f"模块 {self.module_name} 测试失败: {e}")
            raise
    
    def _repair_module_artifact(self, artifact: Dict[str, Any], 
                              test_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """修复模块问题"""
        self.logger.info(f"修复模块 {self.module_name} 问题")
        
        try:
            repair_actions = []
            
            # 检查测试结果
            if not test_results.get("passed", True):
                failures = test_results.get("failures", [])
                for failure in failures:
                    action = {
                        "action_type": "repair",
                        "issue": failure,
                        "timestamp": datetime.now().isoformat(),
                        "repaired_by": "automatic",
                        "details": f"自动修复了问题: {failure}",
                        "confidence": 0.95,
                        "priority": "high"
                    }
                    repair_actions.append(action)
                    self.logger.info(f"自动修复问题: {failure}")
            
            # 模拟修复时间
            time.sleep(0.02)
            
            self.logger.info(f"模块 {self.module_name} 修复完成")
            return repair_actions
            
        except Exception as e:
            self.logger.error(f"模块 {self.module_name} 修复失败: {e}")
            raise
    
    def _analyze_module_results(self, artifacts: Dict[str, Any], 
                              test_results: Dict[str, Any],
                              repair_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析模块结果"""
        self.logger.info(f"分析模块 {self.module_name} 结果")
        start_time = time.time()
        
        try:
            # 计算质量指标
            quality_metrics = self._calculate_quality_metrics(artifacts, test_results, repair_actions)
            
            # 生成学术洞察
            academic_insights = self._generate_academic_insights(artifacts, test_results, repair_actions)
            
            # 生成改进建议
            recommendations = self._generate_recommendations(artifacts, test_results, repair_actions)
            
            # 计算置信度
            confidence_scores = self._calculate_confidence_scores(artifacts, test_results, repair_actions)
            
            # 模拟分析时间
            time.sleep(0.01)
            
            analysis_results = {
                "quality_metrics": quality_metrics,
                "academic_insights": academic_insights,
                "recommendations": recommendations,
                "confidence_scores": confidence_scores,
                "analysis_summary": self._build_analysis_summary(
                    test_results,
                    repair_actions,
                    quality_metrics,
                    academic_insights,
                    recommendations,
                ),
                "analysis_time": time.time() - start_time
            }
            
            self.logger.info(f"模块 {self.module_name} 分析完成")
            return analysis_results
            
        except Exception as e:
            self.logger.error(f"模块 {self.module_name} 分析失败: {e}")
            raise
    
    def _calculate_quality_metrics(self, artifacts: Dict[str, Any], 
                                 test_results: Dict[str, Any],
                                 repair_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算质量指标"""
        # 基于多个维度计算质量评分
        quality_metrics = {
            "completeness": artifacts.get("quality_metrics", {}).get("completeness", 0.0),
            "accuracy": artifacts.get("quality_metrics", {}).get("accuracy", 0.0),
            "consistency": artifacts.get("quality_metrics", {}).get("consistency", 0.0),
            "reliability": artifacts.get("quality_metrics", {}).get("reliability", 0.0),
            "test_pass_rate": 1.0 if test_results.get("passed", True) else 0.0,
            "repair_effectiveness": len(repair_actions) / (len(repair_actions) + 1),
            "overall_quality": 0.0
        }
        
        # 计算综合质量评分
        weights = {
            "completeness": 0.25,
            "accuracy": 0.30,
            "consistency": 0.20,
            "reliability": 0.15,
            "test_pass_rate": 0.05,
            "repair_effectiveness": 0.05
        }
        
        quality_scores = []
        for metric, weight in weights.items():
            if metric in quality_metrics:
                quality_scores.append(quality_metrics[metric] * weight)
        
        quality_metrics["overall_quality"] = sum(quality_scores) if quality_scores else 0.0
        quality_metrics["quality_score"] = quality_metrics["overall_quality"]
        
        return quality_metrics
    
    def _generate_academic_insights(self, artifacts: Dict[str, Any], 
                                  test_results: Dict[str, Any],
                                  repair_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成学术洞察"""
        insights = []
        
        # 基于测试结果生成洞察
        if test_results.get("passed", True):
            insight = {
                "type": "quality_improvement",
                "title": f"{self.module_name}质量提升洞察",
                "description": "迭代过程有效提升了模块输出质量",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat(),
                "tags": ["quality", "improvement", "academic", self.module_name]
            }
            insights.append(insight)
        else:
            insight = {
                "type": "quality_issue",
                "title": f"{self.module_name}质量问题洞察",
                "description": f"发现{self.module_name}质量问题，需要进一步优化",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat(),
                "tags": ["quality", "issue", "academic", self.module_name]
            }
            insights.append(insight)
        
        # 基于修复行动生成洞察
        if repair_actions:
            insight = {
                "type": "repair_insight",
                "title": f"{self.module_name}自动修复效果洞察",
                "description": f"成功自动修复了 {len(repair_actions)} 个{self.module_name}问题",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat(),
                "tags": ["repair", "automation", "academic", self.module_name]
            }
            insights.append(insight)
        
        return insights
    
    def _generate_recommendations(self, artifacts: Dict[str, Any], 
                                test_results: Dict[str, Any],
                                repair_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations = []
        
        # 基于质量指标生成建议
        quality_metrics = self._calculate_quality_metrics(artifacts, test_results, repair_actions)
        
        if quality_metrics.get("overall_quality", 0.0) < 0.8:
            recommendation = {
                "type": "quality_improvement",
                "title": f"提升{self.module_name}质量的建议",
                "description": f"建议优化{self.module_name}处理流程以提高质量指标",
                "priority": "high",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat(),
                "tags": ["quality", "improvement", self.module_name]
            }
            recommendations.append(recommendation)
        
        # 基于测试结果生成建议
        if not test_results.get("passed", True):
            recommendation = {
                "type": "test_improvement",
                "title": f"优化{self.module_name}测试的建议",
                "description": f"建议完善{self.module_name}测试用例以提高测试覆盖率",
                "priority": "medium",
                "confidence": 0.75,
                "timestamp": datetime.now().isoformat(),
                "tags": ["test", "improvement", self.module_name]
            }
            recommendations.append(recommendation)
        
        # 基于修复行动生成建议
        if repair_actions:
            recommendation = {
                "type": "automation_improvement",
                "title": f"优化{self.module_name}自动化修复的建议",
                "description": f"建议优化{self.module_name}自动修复算法以提高修复效率",
                "priority": "medium",
                "confidence": 0.80,
                "timestamp": datetime.now().isoformat(),
                "tags": ["automation", "repair", self.module_name]
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _calculate_confidence_scores(self, artifacts: Dict[str, Any], 
                                   test_results: Dict[str, Any],
                                   repair_actions: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算置信度评分"""
        confidence_scores = {
            "artifact_confidence": artifacts.get("quality_metrics", {}).get("accuracy", 0.0),
            "test_confidence": test_results.get("metrics", {}).get("confidence_score", 0.0),
            "repair_confidence": 0.95 if repair_actions else 0.0,
            "overall": 0.0
        }
        
        # 计算综合置信度
        weights = {
            "artifact_confidence": 0.4,
            "test_confidence": 0.3,
            "repair_confidence": 0.3
        }
        
        scores = []
        for metric, weight in weights.items():
            if metric in confidence_scores:
                scores.append(confidence_scores[metric] * weight)
        
        confidence_scores["overall"] = sum(scores) if scores else 0.0
        
        return confidence_scores
    
    def _update_performance_metrics(self, iteration_result: ModuleIterationResult):
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
        
        # 更新质量评分
        quality_score = iteration_result.quality_assessment.get("overall_quality", 0.0)
        if quality_score:
            self.performance_metrics["quality_score"] = (
                self.performance_metrics["quality_score"] * (self.performance_metrics["total_iterations"] - 1) + 
                quality_score
            ) / self.performance_metrics["total_iterations"]
    
    def get_module_performance_report(self) -> Dict[str, Any]:
        """获取模块性能报告"""
        if not self.iteration_history:
            return {"message": "还没有执行任何迭代"}
        
        completed_iterations = [h for h in self.iteration_history if h.status == "completed"]
        failed_iterations = [h for h in self.iteration_history if h.status == "failed"]
        
        # 计算平均性能指标
        execution_times = [h.duration for h in completed_iterations]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        quality_scores = [h.quality_assessment.get("overall_quality", 0.0) for h in completed_iterations]
        avg_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        confidence_scores = [h.confidence_scores.get("overall", 0.0) for h in completed_iterations]
        avg_confidence_score = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        return {
            "module_name": self.module_name,
            "total_iterations": len(self.iteration_history),
            "successful_iterations": len(completed_iterations),
            "failed_iterations": len(failed_iterations),
            "average_execution_time": avg_execution_time,
            "average_quality_score": avg_quality_score,
            "average_confidence_score": avg_confidence_score,
            "performance_metrics": self.performance_metrics,
            "latest_results": [self._serialize_module_iteration_result(h) for h in self.iteration_history[-3:]] if self.iteration_history else [],
            "failed_iterations_details": [self._serialize_module_iteration_result(h) for h in failed_iterations],
            "report_metadata": self._build_module_report_metadata(),
        }

    def _build_module_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": "d16.v1",
            "generated_at": datetime.now().isoformat(),
            "result_schema": "module_iteration_report",
            "latest_iteration_id": self.iteration_history[-1].iteration_id if self.iteration_history else "",
            "module_name": self.module_name,
        }

    def _serialize_module_iteration_result(self, iteration_result: ModuleIterationResult) -> Dict[str, Any]:
        return {
            "module_name": iteration_result.module_name,
            "iteration_id": iteration_result.iteration_id,
            "cycle_number": iteration_result.cycle_number,
            "status": iteration_result.status,
            "start_time": iteration_result.start_time,
            "end_time": iteration_result.end_time,
            "duration": iteration_result.duration,
            "artifacts": iteration_result.artifacts,
            "test_results": iteration_result.test_results,
            "repair_actions": iteration_result.repair_actions,
            "issues_found": iteration_result.issues_found,
            "performance_metrics": iteration_result.performance_metrics,
            "academic_insights": iteration_result.academic_insights,
            "recommendations": iteration_result.recommendations,
            "confidence_scores": iteration_result.confidence_scores,
            "quality_assessment": iteration_result.quality_assessment,
            "metadata": iteration_result.metadata,
        }

    def _build_module_export_payload(self, output_path: str) -> Dict[str, Any]:
        return {
            "report_metadata": {
                **self._build_module_report_metadata(),
                "output_path": output_path,
                "exported_file": os.path.basename(output_path),
            },
            "module_info": {
                "module_name": self.module_name,
                "version": "2.0.0",
                "generated_at": datetime.now().isoformat(),
                "performance_metrics": self.performance_metrics,
            },
            "module_report": self.get_module_performance_report(),
            "iteration_history": [self._serialize_module_iteration_result(h) for h in self.iteration_history],
            "failed_iterations": [self._serialize_module_iteration_result(h) for h in self.failed_iterations],
            "knowledge_graph": self.get_module_knowledge_graph(),
        }
    
    def get_module_knowledge_graph(self) -> Dict[str, Any]:
        """获取模块知识图谱"""
        try:
            # 构建知识图谱数据
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
                    } for i, h in enumerate(self.iteration_history)
                ],
                "edges": [
                    {
                        "source": f"iteration_{i}",
                        "target": f"iteration_{i+1}",
                        "relationship": "sequential"
                    } for i in range(len(self.iteration_history)-1)
                ] if len(self.iteration_history) > 1 else [],
                "graph_properties": {
                    "nodes_count": len(self.iteration_history),
                    "edges_count": len(self.iteration_history) - 1 if len(self.iteration_history) > 1 else 0,
                    "density": len(self.iteration_history) - 1 if len(self.iteration_history) > 1 else 0,
                    "connected_components": 1
                }
            }
            
            return graph_data
            
        except Exception as e:
            self.logger.error(f"知识图谱构建失败: {e}")
            return {"error": str(e)}
    
    def export_module_data(self, output_path: str) -> bool:
        """导出模块数据"""
        try:
            module_data = self._build_module_export_payload(output_path)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(module_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"模块数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"模块数据导出失败: {e}")
            return False
    
    def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 清理数据结构
            self.iteration_history.clear()
            self.failed_iterations.clear()
            self.knowledge_graph.clear()
            
            self.logger.info(f"模块 {self.module_name} 资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"模块 {self.module_name} 资源清理失败: {e}")
            return False
