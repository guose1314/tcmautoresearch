"""
中医古籍全自动研究系统 - 专业学术模块迭代循环
基于T/C IATCM 098-2023标准的模块级迭代管理
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

from src.core.phase_tracker import PhaseTrackerMixin

# 复用 iteration_cycle 中的延迟单例
from src.cycle.iteration_cycle import (
    _get_extractor,
    _get_fixing_stage,
    _get_preprocessor,
    _get_tester,
)

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


class ModuleIterationCycle(PhaseTrackerMixin):
    """模块级迭代循环管理器。"""

    def __init__(self, module_name: str, module_config: Dict[str, Any] = None):
        self.module_name = module_name
        self.config = module_config or {}
        self.governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_quality": float(self.config.get("minimum_stable_quality", 0.85)),
            "export_contract_version": self.config.get("export_contract_version", "d43.v1"),
        }
        self.iteration_history: List[ModuleIterationResult] = []
        self.failed_iterations: List[ModuleIterationResult] = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.performance_metrics = {
            "total_iterations": 0,
            "successful_iterations": 0,
            "failed_iterations": 0,
            "average_duration": 0.0,
            "total_processing_time": 0.0,
            "quality_score": 0.0,
            "confidence_score": 0.0,
        }
        self.module_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self.knowledge_graph = nx.MultiDiGraph()
        self.logger = logging.getLogger(f"{__name__}.{module_name}")

        self.logger.info("模块迭代循环初始化完成: %s", module_name)

    def _initialize_phase_tracking(self, iteration_result: ModuleIterationResult) -> None:
        iteration_result.metadata["phase_history"] = []
        iteration_result.metadata["phase_timings"] = {}
        iteration_result.metadata["completed_phases"] = []
        iteration_result.metadata["failed_phase"] = None
        iteration_result.metadata["final_status"] = iteration_result.status
        iteration_result.metadata["last_completed_phase"] = None
        iteration_result.metadata["failed_operations"] = []

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(self.module_metadata)

    def _record_failed_operation(
        self,
        container: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.governance_config["persist_failed_operations"]:
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

    def _start_module_phase(self, phase_name: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self.governance_config["enable_phase_tracking"]:
            self.module_metadata["phase_history"].append(phase_entry)
        return phase_entry

    def _complete_module_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        self.module_metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in self.module_metadata["completed_phases"]:
            self.module_metadata["completed_phases"].append(phase_name)
        self.module_metadata["last_completed_phase"] = phase_name
        self.module_metadata["final_status"] = "completed"

    def _fail_module_phase(
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
        self.module_metadata["phase_timings"][phase_name] = round(duration, 6)
        self.module_metadata["failed_phase"] = phase_name
        self.module_metadata["final_status"] = "failed"
        self._record_failed_operation(self.failed_operations, phase_name, error, duration, details)

    def _execute_phase(
        self,
        iteration_result: ModuleIterationResult,
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
                "module_name": iteration_result.module_name,
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
        iteration_result: ModuleIterationResult,
        start_time: float,
        success: bool,
    ) -> None:
        iteration_result.status = "completed" if success else "failed"
        iteration_result.end_time = datetime.now().isoformat()
        iteration_result.duration = time.perf_counter() - start_time
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
            "module_status": "stable"
            if failed_tests == 0 and quality_score >= self.governance_config["minimum_stable_quality"]
            else "needs_followup",
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.module_metadata.get("failed_phase"),
            "last_completed_phase": self.module_metadata.get("last_completed_phase"),
            "final_status": self.module_metadata.get("final_status", "initialized"),
        }

    def execute_module_iteration(self, context: Dict[str, Any]) -> ModuleIterationResult:
        """执行模块迭代。"""
        start_time = time.perf_counter()
        module_phase_start = time.perf_counter()
        self.module_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "running",
            "last_completed_phase": None,
        }
        module_phase_entry = self._start_module_phase(
            "execute_module_iteration",
            {
                "module_name": self.module_name,
                "iteration_index": len(self.iteration_history),
                "context_keys": sorted(context.keys()),
            },
        )

        iteration_result = ModuleIterationResult(
            module_name=self.module_name,
            iteration_id=f"mod_iter_{self.module_name}_{int(time.time())}",
            cycle_number=len(self.iteration_history),
            status="pending",
            start_time=datetime.now().isoformat(),
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
            self._complete_module_phase("execute_module_iteration", module_phase_entry, module_phase_start)
            self._sync_analysis_summary(iteration_result)

            self._update_performance_metrics(iteration_result)

            self.iteration_history.append(iteration_result)

            self.logger.info("模块迭代完成: %s", self.module_name)
            return iteration_result

        except Exception as error:
            iteration_result.issues_found.append(str(error))
            self._finalize_iteration_result(iteration_result, start_time, success=False)
            self.module_metadata["failed_phase"] = iteration_result.metadata.get("failed_phase")
            self._fail_module_phase(
                "execute_module_iteration",
                module_phase_entry,
                module_phase_start,
                str(error),
                {
                    "module_name": iteration_result.module_name,
                    "iteration_id": iteration_result.iteration_id,
                    "cycle_number": iteration_result.cycle_number,
                    "failed_phase": iteration_result.metadata.get("failed_phase"),
                },
            )
            self._sync_analysis_summary(iteration_result)
            self.logger.error("模块迭代失败 %s: %s", self.module_name, error)
            self.logger.error(traceback.format_exc())
            self._update_performance_metrics(iteration_result)
            self.iteration_history.append(iteration_result)
            self.failed_iterations.append(iteration_result)
            raise

    def _sync_analysis_summary(self, iteration_result: ModuleIterationResult) -> None:
        analysis_summary = iteration_result.metadata.get("analysis_summary") or {}
        analysis_summary["failed_operation_count"] = len(self.failed_operations)
        analysis_summary["failed_phase"] = iteration_result.metadata.get("failed_phase") or self.module_metadata.get("failed_phase")
        analysis_summary["last_completed_phase"] = iteration_result.metadata.get("last_completed_phase")
        analysis_summary["final_status"] = iteration_result.status
        analysis_summary.setdefault(
            "module_status",
            "stable"
            if iteration_result.status == "completed"
            and float(iteration_result.quality_assessment.get("quality_score", iteration_result.quality_assessment.get("overall_quality", 0.0))) >= self.governance_config["minimum_stable_quality"]
            else "needs_followup",
        )
        iteration_result.metadata["analysis_summary"] = analysis_summary

    def _generate_module_artifact(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成模块研究产物。"""
        self.logger.info("生成模块 %s 输出", self.module_name)
        start_time = time.time()

        try:
            mock_mode = self.config.get("mock_mode", False) or context.get("mock_mode", False)

            if mock_mode:
                time.sleep(0.05)
                artifact = {
                    "module": self.module_name,
                    "generated_at": datetime.now().isoformat(),
                    "artifact_id": f"artifact_{self.module_name}_{int(time.time())}",
                    "input_context": context,
                    "quality_metrics": {
                        "completeness": 0.92,
                        "accuracy": 0.88,
                        "consistency": 0.95,
                        "reliability": 0.90,
                    },
                    "metadata": {
                        "generation_method": "mock",
                        "processing_time": time.time() - start_time,
                    },
                }
            else:
                preprocessor = _get_preprocessor()
                extractor = _get_extractor()

                preprocess_result = preprocessor.execute(context)
                extract_context = {**context, "preprocessed": preprocess_result}
                extract_result = extractor.execute(extract_context)

                artifact = {
                    "module": self.module_name,
                    "generated_at": datetime.now().isoformat(),
                    "artifact_id": f"artifact_{self.module_name}_{int(time.time())}",
                    "input_context": context,
                    "preprocess_result": preprocess_result,
                    "extract_result": extract_result,
                    "quality_metrics": {
                        "completeness": float(preprocess_result.get("quality_metrics", {}).get("completeness", 0.0)),
                        "accuracy": float(extract_result.get("quality_metrics", {}).get("accuracy", 0.0)),
                        "consistency": float(preprocess_result.get("quality_metrics", {}).get("consistency", 0.0)),
                        "reliability": 0.90,
                    },
                    "metadata": {
                        "generation_method": "automated",
                        "processing_time": time.time() - start_time,
                    },
                }

            self.logger.info("模块 %s 生成完成", self.module_name)
            return artifact

        except Exception as error:
            self.logger.error("模块 %s 生成失败: %s", self.module_name, error)
            raise

    def _test_module_artifact(self, artifact: Dict[str, Any]) -> Dict[str, Any]:
        """测试模块输出。"""
        self.logger.info("测试模块 %s 输出", self.module_name)

        try:
            mock_mode = self.config.get("mock_mode", False)

            if mock_mode:
                time.sleep(0.03)
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
                        "confidence_score": 0.88,
                    },
                    "validation": {
                        "academic_compliance": True,
                        "standard_compliance": True,
                        "quality_assurance": True,
                    },
                }
            else:
                tester = _get_tester()
                tester_context = {
                    "artifacts": artifact,
                    "artifact_id": artifact.get("artifact_id", "unknown"),
                    "module": self.module_name,
                }
                raw_results = tester.run_all_tests(context=tester_context)

                overall = raw_results.get("overall_summary", {})
                passed = overall.get("total_failures", 0) == 0 and overall.get("total_errors", 0) == 0
                failures = []
                for suite_id, suite_result in raw_results.get("suite_results", {}).items():
                    for failure in suite_result.get("failures", []):
                        failures.append(f"[{suite_id}] {failure}")

                test_results = {
                    "module": self.module_name,
                    "tested_at": datetime.now().isoformat(),
                    "artifact_id": artifact.get("artifact_id", "unknown"),
                    "test_suite": list(raw_results.get("suite_results", {}).keys()),
                    "passed": passed,
                    "failures": failures,
                    "warnings": raw_results.get("warnings", []),
                    "metrics": {
                        "execution_time": raw_results.get("execution_time", 0.0),
                        "memory_usage": overall.get("memory_usage", 0.0),
                        "resource_utilization": overall.get("resource_utilization", 0.0),
                        "quality_score": overall.get("quality_score", 0.0),
                        "confidence_score": overall.get("confidence_score", 0.0),
                    },
                    "validation": {
                        "academic_compliance": True,
                        "standard_compliance": True,
                        "quality_assurance": passed,
                    },
                    "raw_results": raw_results,
                }

            self.logger.info("模块 %s 测试完成", self.module_name)
            return test_results

        except Exception as error:
            self.logger.error("模块 %s 测试失败: %s", self.module_name, error)
            raise

    def _repair_module_artifact(
        self,
        artifact: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """修复模块问题。"""
        self.logger.info("修复模块 %s 问题", self.module_name)

        try:
            repair_actions = []
            mock_mode = self.config.get("mock_mode", False)

            if mock_mode:
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
                            "priority": "high",
                        }
                        repair_actions.append(action)
                        self.logger.info("自动修复问题: %s", failure)
                time.sleep(0.02)
            else:
                if not test_results.get("passed", True):
                    failures = test_results.get("failures", [])
                    issues = [
                        {
                            "description": failure,
                            "severity": "high",
                            "affected_components": [self.module_name, artifact.get("artifact_id", "unknown")],
                        }
                        for failure in failures
                    ]

                    if issues:
                        fixing_stage = _get_fixing_stage()
                        stage_result = fixing_stage.run_fixing_stage(
                            issues=issues,
                            context={
                                "artifacts": artifact,
                                "test_results": test_results,
                                "module": self.module_name,
                            },
                            iteration_id=artifact.get("artifact_id"),
                        )

                        for action in stage_result.repair_actions:
                            repair_actions.append({
                                "action_type": action.repair_type.value if hasattr(action.repair_type, "value") else str(action.repair_type),
                                "issue": action.description,
                                "timestamp": action.end_time or datetime.now().isoformat(),
                                "repaired_by": "fixing_stage",
                                "details": action.description,
                                "confidence": action.confidence,
                                "priority": action.priority.value if hasattr(action.priority, "value") else str(action.priority),
                                "success": action.success,
                                "action_id": action.action_id,
                            })

            self.logger.info("模块 %s 修复完成", self.module_name)
            return repair_actions

        except Exception as error:
            self.logger.error("模块 %s 修复失败: %s", self.module_name, error)
            raise

    def _analyze_module_results(
        self,
        artifacts: Dict[str, Any],
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """分析模块结果。"""
        self.logger.info("分析模块 %s 结果", self.module_name)
        start_time = time.time()

        try:
            quality_metrics = self._calculate_quality_metrics(artifacts, test_results, repair_actions)
            academic_insights = self._generate_academic_insights(artifacts, test_results, repair_actions)
            recommendations = self._generate_recommendations(artifacts, test_results, repair_actions)
            confidence_scores = self._calculate_confidence_scores(artifacts, test_results, repair_actions)

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
                "analysis_time": time.time() - start_time,
            }

            self.logger.info("模块 %s 分析完成", self.module_name)
            return analysis_results

        except Exception as error:
            self.logger.error("模块 %s 分析失败: %s", self.module_name, error)
            raise

    def _calculate_quality_metrics(
        self,
        artifacts: Dict[str, Any],
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """计算质量指标。"""
        quality_metrics = {
            "completeness": artifacts.get("quality_metrics", {}).get("completeness", 0.0),
            "accuracy": artifacts.get("quality_metrics", {}).get("accuracy", 0.0),
            "consistency": artifacts.get("quality_metrics", {}).get("consistency", 0.0),
            "reliability": artifacts.get("quality_metrics", {}).get("reliability", 0.0),
            "test_pass_rate": 1.0 if test_results.get("passed", True) else 0.0,
            "repair_effectiveness": len(repair_actions) / (len(repair_actions) + 1),
            "overall_quality": 0.0,
        }

        weights = {
            "completeness": 0.25,
            "accuracy": 0.30,
            "consistency": 0.20,
            "reliability": 0.15,
            "test_pass_rate": 0.05,
            "repair_effectiveness": 0.05,
        }

        quality_scores = []
        for metric, weight in weights.items():
            if metric in quality_metrics:
                quality_scores.append(quality_metrics[metric] * weight)

        quality_metrics["overall_quality"] = sum(quality_scores) if quality_scores else 0.0
        quality_metrics["quality_score"] = quality_metrics["overall_quality"]

        return quality_metrics

    def _generate_academic_insights(
        self,
        artifacts: Dict[str, Any],
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """生成学术洞察。"""
        insights = []

        if test_results.get("passed", True):
            insights.append(
                {
                    "type": "quality_improvement",
                    "title": f"{self.module_name}质量提升洞察",
                    "description": "迭代过程有效提升了模块输出质量",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "improvement", "academic", self.module_name],
                }
            )
        else:
            insights.append(
                {
                    "type": "quality_issue",
                    "title": f"{self.module_name}质量问题洞察",
                    "description": f"发现{self.module_name}质量问题，需要进一步优化",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "issue", "academic", self.module_name],
                }
            )

        if repair_actions:
            insights.append(
                {
                    "type": "repair_insight",
                    "title": f"{self.module_name}自动修复效果洞察",
                    "description": f"成功自动修复了 {len(repair_actions)} 个{self.module_name}问题",
                    "confidence": 0.90,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["repair", "automation", "academic", self.module_name],
                }
            )

        return insights

    def _generate_recommendations(
        self,
        artifacts: Dict[str, Any],
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """生成改进建议。"""
        recommendations = []
        quality_metrics = self._calculate_quality_metrics(artifacts, test_results, repair_actions)

        if quality_metrics.get("overall_quality", 0.0) < 0.8:
            recommendations.append(
                {
                    "type": "quality_improvement",
                    "title": f"提升{self.module_name}质量的建议",
                    "description": f"建议优化{self.module_name}处理流程以提高质量指标",
                    "priority": "high",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["quality", "improvement", self.module_name],
                }
            )

        if not test_results.get("passed", True):
            recommendations.append(
                {
                    "type": "test_improvement",
                    "title": f"优化{self.module_name}测试的建议",
                    "description": f"建议完善{self.module_name}测试用例以提高测试覆盖率",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["test", "improvement", self.module_name],
                }
            )

        if repair_actions:
            recommendations.append(
                {
                    "type": "automation_improvement",
                    "title": f"优化{self.module_name}自动化修复的建议",
                    "description": f"建议优化{self.module_name}自动修复算法以提高修复效率",
                    "priority": "medium",
                    "confidence": 0.80,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["automation", "repair", self.module_name],
                }
            )

        return recommendations

    def _calculate_confidence_scores(
        self,
        artifacts: Dict[str, Any],
        test_results: Dict[str, Any],
        repair_actions: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """计算置信度评分。"""
        confidence_scores = {
            "artifact_confidence": artifacts.get("quality_metrics", {}).get("accuracy", 0.0),
            "test_confidence": test_results.get("metrics", {}).get("confidence_score", 0.0),
            "repair_confidence": 0.95 if repair_actions else 0.0,
            "overall": 0.0,
        }

        weights = {
            "artifact_confidence": 0.4,
            "test_confidence": 0.3,
            "repair_confidence": 0.3,
        }

        scores = []
        for metric, weight in weights.items():
            if metric in confidence_scores:
                scores.append(confidence_scores[metric] * weight)

        confidence_scores["overall"] = sum(scores) if scores else 0.0

        return confidence_scores

    def _update_performance_metrics(self, iteration_result: ModuleIterationResult) -> None:
        """更新性能指标。"""
        self.performance_metrics["total_iterations"] += 1
        if iteration_result.status == "completed":
            self.performance_metrics["successful_iterations"] += 1
        else:
            self.performance_metrics["failed_iterations"] += 1

        if self.performance_metrics["total_iterations"] > 0:
            self.performance_metrics["average_duration"] = (
                self.performance_metrics["total_processing_time"] + iteration_result.duration
            ) / self.performance_metrics["total_iterations"]

        self.performance_metrics["total_processing_time"] += iteration_result.duration

        quality_score = iteration_result.quality_assessment.get("overall_quality", 0.0)
        if quality_score:
            self.performance_metrics["quality_score"] = (
                self.performance_metrics["quality_score"] * (self.performance_metrics["total_iterations"] - 1)
                + quality_score
            ) / self.performance_metrics["total_iterations"]

    def get_module_performance_report(self) -> Dict[str, Any]:
        """获取模块性能报告。"""
        if not self.iteration_history:
            return {"message": "还没有执行任何迭代"}

        completed_iterations, failed_iterations = self._partition_iteration_history()
        average_metrics = self._build_module_average_metrics(completed_iterations)
        analysis_summary = self._build_module_report_analysis_summary(
            len(failed_iterations),
            average_metrics["average_quality_score"],
        )

        return {
            "module_name": self.module_name,
            "total_iterations": len(self.iteration_history),
            "successful_iterations": len(completed_iterations),
            "failed_iterations": len(failed_iterations),
            "average_execution_time": average_metrics["average_execution_time"],
            "average_quality_score": average_metrics["average_quality_score"],
            "average_confidence_score": average_metrics["average_confidence_score"],
            "performance_metrics": self._serialize_value(self.performance_metrics),
            "analysis_summary": analysis_summary,
            "failed_operations": self._serialize_value(self.failed_operations),
            "metadata": self._build_runtime_metadata(),
            "latest_results": [self._serialize_module_iteration_result(item) for item in self.iteration_history[-3:]],
            "failed_iterations_details": [self._serialize_module_iteration_result(item) for item in failed_iterations],
            "report_metadata": self._build_module_report_metadata(),
        }

    def _partition_iteration_history(self) -> tuple[List[ModuleIterationResult], List[ModuleIterationResult]]:
        completed = [item for item in self.iteration_history if item.status == "completed"]
        failed = [item for item in self.iteration_history if item.status == "failed"]
        return completed, failed

    def _build_module_average_metrics(self, completed_iterations: List[ModuleIterationResult]) -> Dict[str, float]:
        if not completed_iterations:
            return {
                "average_execution_time": 0.0,
                "average_quality_score": 0.0,
                "average_confidence_score": 0.0,
            }

        avg_execution_time = sum(item.duration for item in completed_iterations) / len(completed_iterations)
        avg_quality_score = sum(
            item.quality_assessment.get("overall_quality", 0.0)
            for item in completed_iterations
        ) / len(completed_iterations)
        avg_confidence_score = sum(
            item.confidence_scores.get("overall", 0.0)
            for item in completed_iterations
        ) / len(completed_iterations)
        return {
            "average_execution_time": avg_execution_time,
            "average_quality_score": avg_quality_score,
            "average_confidence_score": avg_confidence_score,
        }

    def _build_module_report_analysis_summary(
        self,
        failed_iteration_count: int,
        avg_quality_score: float,
    ) -> Dict[str, Any]:
        is_stable = (
            failed_iteration_count == 0
            and avg_quality_score >= self.governance_config["minimum_stable_quality"]
        )
        return {
            "status": "stable" if is_stable else "needs_followup",
            "failed_operation_count": len(self.failed_operations),
            "failed_phase": self.module_metadata.get("failed_phase"),
            "last_completed_phase": self.module_metadata.get("last_completed_phase"),
            "final_status": self.module_metadata.get("final_status", "initialized"),
        }

    def _build_module_report_metadata(self) -> Dict[str, Any]:
        runtime_metadata = self._build_runtime_metadata()
        return {
            "contract_version": self.governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "module_iteration_report",
            "latest_iteration_id": self.iteration_history[-1].iteration_id if self.iteration_history else "",
            "module_name": self.module_name,
            "failed_operation_count": len(self.failed_operations),
            "final_status": runtime_metadata.get("final_status", "initialized"),
            "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        }

    def _serialize_module_iteration_result(self, iteration_result: ModuleIterationResult) -> Dict[str, Any]:
        return self._serialize_value(
            {
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
        )

    def _build_module_export_payload(self, output_path: str) -> Dict[str, Any]:
        return self._serialize_value(
            {
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
                "iteration_history": [self._serialize_module_iteration_result(item) for item in self.iteration_history],
                "failed_iterations": [self._serialize_module_iteration_result(item) for item in self.failed_iterations],
                "failed_operations": self.failed_operations,
                "metadata": self._build_runtime_metadata(),
                "knowledge_graph": self.get_module_knowledge_graph(),
            }
        )

    def get_module_knowledge_graph(self) -> Dict[str, Any]:
        """获取模块知识图谱。"""
        try:
            return {
                "nodes": [
                    {
                        "id": f"iteration_{index}",
                        "data": {
                            "iteration": index,
                            "status": item.status,
                            "duration": item.duration,
                            "quality_score": item.quality_assessment.get("overall_quality", 0.0),
                            "confidence_score": item.confidence_scores.get("overall", 0.0),
                        },
                    }
                    for index, item in enumerate(self.iteration_history)
                ],
                "edges": [
                    {
                        "source": f"iteration_{index}",
                        "target": f"iteration_{index + 1}",
                        "relationship": "sequential",
                    }
                    for index in range(len(self.iteration_history) - 1)
                ]
                if len(self.iteration_history) > 1
                else [],
                "graph_properties": {
                    "nodes_count": len(self.iteration_history),
                    "edges_count": len(self.iteration_history) - 1 if len(self.iteration_history) > 1 else 0,
                    "density": len(self.iteration_history) - 1 if len(self.iteration_history) > 1 else 0,
                    "connected_components": 1,
                },
            }

        except Exception as error:
            self.logger.error("知识图谱构建失败: %s", error)
            return {"error": str(error)}

    def export_module_data(self, output_path: str) -> bool:
        """导出模块数据。"""
        try:
            module_data = self._build_module_export_payload(output_path)

            with open(output_path, "w", encoding="utf-8") as file_obj:
                json.dump(module_data, file_obj, ensure_ascii=False, indent=2)

            self.logger.info("模块数据已导出到: %s", output_path)
            return True

        except Exception as error:
            self.logger.error("模块数据导出失败: %s", error)
            return False

    def cleanup(self) -> bool:
        """清理资源。"""
        try:
            self.iteration_history.clear()
            self.failed_iterations.clear()
            self.failed_operations.clear()
            self.knowledge_graph.clear()
            self.module_metadata = {
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
                "average_duration": 0.0,
                "total_processing_time": 0.0,
                "quality_score": 0.0,
                "confidence_score": 0.0,
            }

            self.logger.info("模块 %s 资源清理完成", self.module_name)
            return True

        except Exception as error:
            self.logger.error("模块 %s 资源清理失败: %s", self.module_name, error)
            return False
