# cycle/fixing_stage.py
"""
中医古籍全自动研究系统 - 专业学术修复阶段
基于T/C IATCM 098-2023标准的智能修复管理
"""

import hashlib
import json
import logging
import os
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import networkx as nx

# 配置日志
logger = logging.getLogger(__name__)

ISSUE_MESSAGE_RULES = [
    (("input", "parameter"), "input_validation"),
    (("memory", "resource"), "memory_leak"),
    (("slow", "timeout"), "performance_issue"),
    (("dependency", "module"), "dependency_error"),
    (("security", "vulnerability"), "security_vulnerability"),
    (("data", "quality"), "data_quality"),
]

ISSUE_CATEGORY_RULES = [
    ("performance", "performance_issue"),
    ("security", "security_vulnerability"),
]

class RepairPriority(Enum):
    """修复优先级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RepairType(Enum):
    """修复类型枚举"""
    CODE_FIX = "code_fix"
    DATA_CLEANUP = "data_cleanup"
    CONFIGURATION = "configuration"
    PERFORMANCE = "performance"
    SECURITY = "security"
    QUALITY = "quality"
    COMPLIANCE = "compliance"

@dataclass
class RepairAction:
    """修复行动数据结构"""
    action_id: str
    repair_type: RepairType
    priority: RepairPriority
    description: str
    affected_components: List[str]
    estimated_effort: float  # 工作量估算（小时）
    confidence: float  # 修复置信度
    status: str = "pending"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: float = 0.0
    success: bool = False
    error_message: str = ""
    impact_analysis: Dict[str, Any] = field(default_factory=dict)
    academic_impact: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FixingStageResult:
    """修复阶段结果数据结构"""
    stage_id: str
    iteration_id: str
    status: str
    start_time: str
    end_time: str = ""
    duration: float = 0.0
    repair_actions: List[RepairAction] = field(default_factory=list)
    resolved_issues: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_issues: List[Dict[str, Any]] = field(default_factory=list)
    quality_improvement: Dict[str, Any] = field(default_factory=dict)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class FixingStage:
    """
    修复阶段管理器
    
    本模块专注于系统问题的智能识别和修复，
    确保每次迭代都能有效解决发现的问题，
    符合T/C IATCM 098-2023学术标准要求。
    
    主要功能：
    1. 智能问题识别与分类
    2. 自动化修复行动生成
    3. 修复优先级评估
    4. 修复效果验证
    5. 学术影响分析
    6. 知识沉淀与传承
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.repair_actions: List[RepairAction] = []
        self.repair_history: List[FixingStageResult] = []
        self.failed_stages: List[FixingStageResult] = []
        self.performance_metrics = {
            "total_repairs": 0,
            "successful_repairs": 0,
            "failed_repairs": 0,
            "average_repair_time": 0.0,
            "total_repair_time": 0.0,
            "quality_improvement": 0.0,
            "confidence_improvement": 0.0
        }
        self.knowledge_graph = nx.MultiDiGraph()
        self.repair_rules = self._load_repair_rules()
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("修复阶段管理器初始化完成")

    def _initialize_phase_tracking(self, stage_result: FixingStageResult) -> None:
        stage_result.metadata["phase_history"] = []
        stage_result.metadata["phase_timings"] = {}
        stage_result.metadata["completed_phases"] = []

    def _execute_phase(
        self,
        stage_result: FixingStageResult,
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
        stage_result.metadata["phase_history"].append(phase_entry)
        stage_result.status = status

        try:
            result = operation()
        except Exception as exc:
            duration = time.time() - phase_start
            phase_entry["status"] = "failed"
            phase_entry["ended_at"] = datetime.now().isoformat()
            phase_entry["duration"] = duration
            phase_entry["error"] = str(exc)
            stage_result.metadata["phase_timings"][phase_name] = duration
            stage_result.metadata["failed_phase"] = phase_name
            raise

        duration = time.time() - phase_start
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration"] = duration
        stage_result.metadata["phase_timings"][phase_name] = duration
        stage_result.metadata["completed_phases"].append(phase_name)
        stage_result.metadata["last_completed_phase"] = phase_name
        return result

    def _finalize_stage_result(
        self,
        stage_result: FixingStageResult,
        start_time: float,
        success: bool,
    ) -> None:
        stage_result.status = "completed" if success else "failed"
        stage_result.end_time = datetime.now().isoformat()
        stage_result.duration = time.time() - start_time
        stage_result.metadata["final_status"] = stage_result.status

    def _build_analysis_summary(
        self,
        repair_actions: List[RepairAction],
        validation_results: Dict[str, Any],
        academic_insights: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        confidence_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        successful_repairs = sum(1 for action in repair_actions if action.success)
        total_repairs = len(repair_actions)
        success_rate = successful_repairs / total_repairs if total_repairs else 0.0
        minimum_success_rate = float(self.config.get("minimum_stable_success_rate", 0.8))
        return {
            "total_repairs": total_repairs,
            "successful_repairs": successful_repairs,
            "failed_repairs": total_repairs - successful_repairs,
            "success_rate": success_rate,
            "quality_improvement": float(validation_results.get("quality_improvement", 0.0)),
            "overall_confidence": float(confidence_scores.get("overall", 0.0)),
            "academic_insight_count": len(academic_insights),
            "recommendation_count": len(recommendations),
            "stage_status": "stable" if success_rate >= minimum_success_rate else "needs_followup",
        }

    def _serialize_repair_action(self, action: RepairAction) -> Dict[str, Any]:
        return {
            "action_id": action.action_id,
            "repair_type": action.repair_type.value,
            "priority": action.priority.value,
            "description": action.description,
            "affected_components": action.affected_components,
            "estimated_effort": action.estimated_effort,
            "confidence": action.confidence,
            "status": action.status,
            "start_time": action.start_time,
            "end_time": action.end_time,
            "duration": action.duration,
            "success": action.success,
            "error_message": action.error_message,
            "impact_analysis": action.impact_analysis,
            "academic_impact": action.academic_impact,
            "metadata": action.metadata,
        }

    def _serialize_stage_result(self, stage_result: FixingStageResult) -> Dict[str, Any]:
        return {
            "stage_id": stage_result.stage_id,
            "iteration_id": stage_result.iteration_id,
            "status": stage_result.status,
            "start_time": stage_result.start_time,
            "end_time": stage_result.end_time,
            "duration": stage_result.duration,
            "repair_actions": [self._serialize_repair_action(action) for action in stage_result.repair_actions],
            "resolved_issues": stage_result.resolved_issues,
            "unresolved_issues": stage_result.unresolved_issues,
            "quality_improvement": stage_result.quality_improvement,
            "academic_insights": stage_result.academic_insights,
            "recommendations": stage_result.recommendations,
            "confidence_scores": stage_result.confidence_scores,
            "metadata": stage_result.metadata,
        }

    def _serialize_repair_rules(self) -> Dict[str, Any]:
        serialized_rules: Dict[str, Any] = {}
        for issue_type, rule in self.repair_rules.items():
            serialized_rules[issue_type] = {
                **rule,
                "priority": rule.get("priority").value if isinstance(rule.get("priority"), RepairPriority) else rule.get("priority"),
                "type": rule.get("type").value if isinstance(rule.get("type"), RepairType) else rule.get("type"),
            }
        return serialized_rules

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.config.get("export_contract_version", "d18.v1"),
            "generated_at": datetime.now().isoformat(),
            "result_schema": "fixing_stage_report",
            "latest_stage_id": self.repair_history[-1].stage_id if self.repair_history else "",
        }
    
    def _load_repair_rules(self) -> Dict[str, Any]:
        """加载修复规则"""
        return {
            "input_validation": {
                "patterns": ["invalid parameter", "input error", "parameter mismatch"],
                "priority": RepairPriority.HIGH,
                "action_template": "修复输入参数验证问题",
                "type": RepairType.CODE_FIX,
                "effort_estimate": 1.0,
                "confidence": 0.95
            },
            "memory_leak": {
                "patterns": ["memory error", "resource leak", "out of memory"],
                "priority": RepairPriority.CRITICAL,
                "action_template": "修复内存泄漏问题",
                "type": RepairType.DATA_CLEANUP,
                "effort_estimate": 2.0,
                "confidence": 0.90
            },
            "performance_issue": {
                "patterns": ["slow execution", "timeout", "high latency"],
                "priority": RepairPriority.MEDIUM,
                "action_template": "优化性能瓶颈",
                "type": RepairType.PERFORMANCE,
                "effort_estimate": 1.5,
                "confidence": 0.85
            },
            "dependency_error": {
                "patterns": ["dependency missing", "module not found", "import error"],
                "priority": RepairPriority.HIGH,
                "action_template": "修复依赖问题",
                "type": RepairType.CONFIGURATION,
                "effort_estimate": 0.5,
                "confidence": 0.80
            },
            "security_vulnerability": {
                "patterns": ["security breach", "vulnerability", "security issue"],
                "priority": RepairPriority.CRITICAL,
                "action_template": "修复安全漏洞",
                "type": RepairType.SECURITY,
                "effort_estimate": 3.0,
                "confidence": 0.98
            },
            "data_quality": {
                "patterns": ["data inconsistency", "quality issue", "incomplete data"],
                "priority": RepairPriority.MEDIUM,
                "action_template": "提升数据质量",
                "type": RepairType.DATA_CLEANUP,
                "effort_estimate": 1.0,
                "confidence": 0.85
            }
        }
    
    def identify_and_generate_repairs(self, issues: List[Dict[str, Any]], 
                                    context: Dict[str, Any]) -> List[RepairAction]:
        """
        识别问题并生成修复行动
        
        Args:
            issues (List[Dict[str, Any]]): 问题列表
            context (Dict[str, Any]): 执行上下文
            
        Returns:
            List[RepairAction]: 修复行动列表
        """
        self.logger.info("开始识别问题并生成修复行动")
        
        try:
            repair_actions = []
            
            # 遍历所有问题
            for i, issue in enumerate(issues):
                # 生成修复行动
                repair_action = self._generate_single_repair_action(issue, context, i)
                if repair_action:
                    repair_actions.append(repair_action)
            
            self.logger.info(f"问题识别和修复行动生成完成，共生成 {len(repair_actions)} 个修复行动")
            return repair_actions
            
        except Exception as e:
            self.logger.error(f"问题识别和修复行动生成失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def _generate_single_repair_action(self, issue: Dict[str, Any], 
                                     context: Dict[str, Any], 
                                     index: int) -> Optional[RepairAction]:
        """生成单个修复行动"""
        try:
            # 生成修复行动ID
            action_id = f"repair_{int(time.time())}_{index}_{hashlib.md5(str(issue).encode()).hexdigest()[:8]}"
            
            # 识别问题类型
            issue_type = self._identify_issue_type(issue)
            
            # 根据问题类型选择修复规则
            repair_rule = self._select_repair_rule(issue_type)
            
            # 生成修复行动
            repair_action = RepairAction(
                action_id=action_id,
                repair_type=repair_rule.get("type", RepairType.CODE_FIX),
                priority=repair_rule.get("priority", RepairPriority.MEDIUM),
                description=repair_rule.get("action_template", "修复问题"),
                affected_components=issue.get("affected_components", []),
                estimated_effort=repair_rule.get("effort_estimate", 1.0),
                confidence=repair_rule.get("confidence", 0.8),
                status="pending",
                metadata={
                    "issue": issue,
                    "context": context,
                    "rule_used": repair_rule.get("pattern", "unknown")
                }
            )
            
            return repair_action
            
        except Exception as e:
            self.logger.error(f"单个修复行动生成失败: {e}")
            return None
    
    def _identify_issue_type(self, issue: Dict[str, Any]) -> str:
        """识别问题类型"""
        issue_message = issue.get("message", "").lower()
        issue_category = issue.get("category", "unknown").lower()

        for keywords, issue_type in ISSUE_MESSAGE_RULES:
            if any(keyword in issue_message for keyword in keywords):
                return issue_type

        for keyword, issue_type in ISSUE_CATEGORY_RULES:
            if keyword in issue_category:
                return issue_type

        return "general_issue"
    
    def _select_repair_rule(self, issue_type: str) -> Dict[str, Any]:
        """选择修复规则"""
        # 从预定义规则中选择匹配的规则
        if issue_type in self.repair_rules:
            return self.repair_rules[issue_type]
        else:
            # 返回默认规则
            return {
                "type": RepairType.CODE_FIX,
                "priority": RepairPriority.MEDIUM,
                "action_template": "修复一般问题",
                "effort_estimate": 1.0,
                "confidence": 0.75
            }
    
    def execute_repair_actions(self, repair_actions: List[RepairAction]) -> List[RepairAction]:
        """
        执行修复行动
        
        Args:
            repair_actions (List[RepairAction]): 修复行动列表
            
        Returns:
            List[RepairAction]: 执行后的修复行动列表
        """
        start_time = time.time()
        self.logger.info(f"开始执行 {len(repair_actions)} 个修复行动")
        
        try:
            executed_actions = []
            
            # 依次执行每个修复行动
            for action in repair_actions:
                executed_action = self._execute_single_repair_action(action)
                executed_actions.append(executed_action)
            
            successful_repairs = sum(1 for a in executed_actions if a.success)
            self._update_performance_metrics(len(executed_actions), successful_repairs, time.time() - start_time)
            
            self.logger.info(f"修复行动执行完成，成功 {successful_repairs} 个")
            return executed_actions
            
        except Exception as e:
            self.logger.error(f"修复行动执行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def _execute_single_repair_action(self, action: RepairAction) -> RepairAction:
        """执行单个修复行动"""
        start_time = time.time()
        
        try:
            # 更新行动状态
            action.status = "executing"
            action.start_time = datetime.now().isoformat()
            
            # 模拟修复过程
            # 在实际应用中，这里应该调用具体的修复逻辑
            self._simulate_repair_process(action)
            
            # 更新行动状态
            action.status = "completed"
            action.end_time = datetime.now().isoformat()
            action.duration = time.time() - start_time
            action.success = True
            
            # 生成影响分析
            action.impact_analysis = self._generate_impact_analysis(action)
            
            # 生成学术影响分析
            action.academic_impact = self._generate_academic_impact(action)
            
            self.logger.info(f"修复行动 {action.action_id} 执行成功")
            return action
            
        except Exception as e:
            action.status = "failed"
            action.end_time = datetime.now().isoformat()
            action.duration = time.time() - start_time
            action.success = False
            action.error_message = str(e)
            
            self.logger.error(f"修复行动 {action.action_id} 执行失败: {e}")
            return action
    
    def _simulate_repair_process(self, action: RepairAction):
        """模拟修复过程"""
        # 模拟不同类型的修复需要的时间
        time_multiplier = 1.0
        if action.priority == RepairPriority.CRITICAL:
            time_multiplier = 2.0
        elif action.priority == RepairPriority.HIGH:
            time_multiplier = 1.5
        elif action.priority == RepairPriority.LOW:
            time_multiplier = 0.5
        
        # 模拟执行时间
        simulated_time = action.estimated_effort * time_multiplier
        time.sleep(simulated_time * 0.1)  # 乘以0.1作为模拟延迟
    
    def _generate_impact_analysis(self, action: RepairAction) -> Dict[str, Any]:
        """生成影响分析"""
        return {
            "components_affected": action.affected_components,
            "estimated_time_saved": action.estimated_effort * 0.8,  # 假设节省20%时间
            "risk_reduction": 0.75,  # 假设风险降低75%
            "quality_improvement": 0.8,  # 假设质量提升80%
            "impact_score": 0.0
        }
    
    def _generate_academic_impact(self, action: RepairAction) -> Dict[str, Any]:
        """生成学术影响分析"""
        return {
            "scientific_value": 0.85,  # 学术价值评分
            "compliance_improvement": 0.9,  # 合规性提升
            "knowledge_contribution": 0.75,  # 知识贡献度
            "research_impact": 0.8,  # 研究影响力
            "documentation_quality": 0.9  # 文档质量
        }
    
    def validate_repair_effects(self, repair_actions: List[RepairAction]) -> Dict[str, Any]:
        """
        验证修复效果
        
        Args:
            repair_actions (List[RepairAction]): 修复行动列表
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        start_time = time.time()
        self.logger.info("开始验证修复效果")
        
        try:
            validation_results = self._initialize_validation_results(len(repair_actions))

            # 统计修复结果
            self._update_repair_statistics(validation_results, repair_actions)

            # 计算质量提升
            self._calculate_quality_improvement(validation_results)

            # 计算置信度提升
            self._calculate_confidence_improvement(validation_results, repair_actions)

            validation_results["validation_time"] = time.time() - start_time

            self.logger.info("修复效果验证完成")
            return validation_results
            
        except Exception as e:
            self.logger.error(f"修复效果验证失败: {e}")
            raise

    def run_fixing_stage(
        self,
        issues: List[Dict[str, Any]],
        context: Dict[str, Any],
        iteration_id: str | None = None,
    ) -> FixingStageResult:
        start_time = time.time()
        stage_result = FixingStageResult(
            stage_id=f"fix_stage_{int(time.time())}",
            iteration_id=iteration_id or f"fix_iter_{int(time.time())}",
            status="pending",
            start_time=datetime.now().isoformat(),
        )
        self._initialize_phase_tracking(stage_result)

        try:
            generated_actions = self._execute_phase(
                stage_result,
                "identify_repairs",
                "identifying_repairs",
                lambda: self.identify_and_generate_repairs(issues, context),
            )
            executed_actions = self._execute_phase(
                stage_result,
                "execute_repairs",
                "executing_repairs",
                lambda: self.execute_repair_actions(generated_actions),
            )
            stage_result.repair_actions = executed_actions
            self.repair_actions.extend(executed_actions)

            validation_results = self._execute_phase(
                stage_result,
                "validate_repairs",
                "validating_repairs",
                lambda: self.validate_repair_effects(executed_actions),
            )
            stage_result.quality_improvement = validation_results
            stage_result.resolved_issues = [action.metadata.get("issue", {}) for action in executed_actions if action.success]
            stage_result.unresolved_issues = [action.metadata.get("issue", {}) for action in executed_actions if not action.success]

            analysis_results = self._execute_phase(
                stage_result,
                "analyze_repairs",
                "analyzing_repairs",
                lambda: self.analyze_repair_outcomes(executed_actions, validation_results),
            )
            stage_result.academic_insights = analysis_results.get("academic_insights", [])
            stage_result.recommendations = analysis_results.get("recommendations", [])
            stage_result.confidence_scores = analysis_results.get("confidence_scores", {})
            stage_result.metadata["analysis_summary"] = analysis_results.get("analysis_summary", {})

            self._finalize_stage_result(stage_result, start_time, success=True)
            self.repair_history.append(stage_result)
            return stage_result

        except Exception as exc:
            stage_result.metadata["error"] = str(exc)
            self._finalize_stage_result(stage_result, start_time, success=False)
            self.repair_history.append(stage_result)
            self.failed_stages.append(stage_result)
            self.logger.error(f"修复阶段执行失败: {exc}")
            self.logger.error(traceback.format_exc())
            raise

    def _initialize_validation_results(self, total_repairs: int) -> Dict[str, Any]:
        return {
            "total_repairs": total_repairs,
            "successful_repairs": 0,
            "failed_repairs": 0,
            "quality_improvement": 0.0,
            "confidence_improvement": 0.0,
            "validation_time": 0.0
        }

    def _update_repair_statistics(
        self,
        validation_results: Dict[str, Any],
        repair_actions: List[RepairAction],
    ) -> None:
        for action in repair_actions:
            if action.success:
                validation_results["successful_repairs"] += 1
            else:
                validation_results["failed_repairs"] += 1

    def _calculate_quality_improvement(self, validation_results: Dict[str, Any]) -> None:
        if validation_results["successful_repairs"] > 0:
            validation_results["quality_improvement"] = (
                validation_results["successful_repairs"] / validation_results["total_repairs"]
            )

    def _calculate_confidence_improvement(
        self,
        validation_results: Dict[str, Any],
        repair_actions: List[RepairAction],
    ) -> None:
        successful_actions = [a for a in repair_actions if a.success]
        if successful_actions:
            avg_confidence = sum(a.confidence for a in successful_actions) / len(successful_actions)
            validation_results["confidence_improvement"] = avg_confidence
    
    def analyze_repair_outcomes(
        self,
        repair_actions: List[RepairAction],
        validation_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        分析修复结果
        
        Args:
            repair_actions (List[RepairAction]): 修复行动列表
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        start_time = time.time()
        self.logger.info("开始分析修复结果")
        
        try:
            # 统计各类修复
            repair_counts = defaultdict(int)
            priority_counts = defaultdict(int)
            type_counts = defaultdict(int)
            
            for action in repair_actions:
                repair_counts[action.status] += 1
                priority_counts[action.priority.value] += 1
                type_counts[action.repair_type.value] += 1
            
            # 生成学术洞察
            academic_insights = self._generate_academic_insights(repair_actions)
            
            # 生成改进建议
            recommendations = self._generate_recommendations(repair_actions)
            
            # 计算综合置信度
            confidence_scores = self._calculate_comprehensive_confidence(repair_actions)
            effective_validation_results = validation_results or self.validate_repair_effects(repair_actions)
            
            analysis_results = {
                "repair_statistics": {
                    "total_repairs": len(repair_actions),
                    "status_distribution": dict(repair_counts),
                    "priority_distribution": dict(priority_counts),
                    "type_distribution": dict(type_counts)
                },
                "academic_insights": academic_insights,
                "recommendations": recommendations,
                "confidence_scores": confidence_scores,
                "analysis_summary": self._build_analysis_summary(
                    repair_actions,
                    effective_validation_results,
                    academic_insights,
                    recommendations,
                    confidence_scores,
                ),
                "analysis_time": time.time() - start_time
            }
            
            self.logger.info("修复结果分析完成")
            return analysis_results
            
        except Exception as e:
            self.logger.error(f"修复结果分析失败: {e}")
            raise
    
    def _generate_academic_insights(self, repair_actions: List[RepairAction]) -> List[Dict[str, Any]]:
        """生成学术洞察"""
        insights = []
        
        # 基于修复类型生成洞察
        repair_types = [a.repair_type.value for a in repair_actions]
        type_counts = defaultdict(int)
        for rt in repair_types:
            type_counts[rt] += 1
        
        for repair_type, count in type_counts.items():
            if count > 0:
                insight = {
                    "type": "repair_type_analysis",
                    "title": f"{repair_type}修复洞察",
                    "description": f"共执行了 {count} 次 {repair_type} 修复",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["repair", "analysis", "academic", repair_type]
                }
                insights.append(insight)
        
        # 基于优先级生成洞察
        priorities = [a.priority.value for a in repair_actions]
        priority_counts = defaultdict(int)
        for p in priorities:
            priority_counts[p] += 1
        
        high_priority_count = priority_counts.get("high", 0) + priority_counts.get("critical", 0)
        if high_priority_count > 0:
            insight = {
                "type": "priority_analysis",
                "title": "高优先级修复洞察",
                "description": f"执行了 {high_priority_count} 个高优先级修复任务",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat(),
                "tags": ["priority", "analysis", "academic"]
            }
            insights.append(insight)
        
        return insights
    
    def _generate_recommendations(self, repair_actions: List[RepairAction]) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations = []
        
        # 基于修复成功率生成建议
        total_repairs = len(repair_actions)
        successful_repairs = sum(1 for a in repair_actions if a.success)
        
        if total_repairs > 0:
            success_rate = successful_repairs / total_repairs
            if success_rate < 0.8:
                recommendation = {
                    "type": "repair_improvement",
                    "title": "提升修复成功率的建议",
                    "description": "当前修复成功率较低，建议优化修复流程和工具",
                    "priority": "high",
                    "confidence": 0.85,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["repair", "improvement", "academic"]
                }
                recommendations.append(recommendation)
        
        # 基于修复类型生成建议
        repair_types = [a.repair_type.value for a in repair_actions]
        type_counts = defaultdict(int)
        for rt in repair_types:
            type_counts[rt] += 1
        
        # 识别需要重点优化的修复类型
        for repair_type, count in type_counts.items():
            if count > 3:  # 如果某种类型修复次数较多
                recommendation = {
                    "type": "type_optimization",
                    "title": f"优化{repair_type}修复流程的建议",
                    "description": f"在{repair_type}修复方面有较多实践，建议建立标准化流程",
                    "priority": "medium",
                    "confidence": 0.75,
                    "timestamp": datetime.now().isoformat(),
                    "tags": ["optimization", "process", "academic", repair_type]
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    def _calculate_comprehensive_confidence(self, repair_actions: List[RepairAction]) -> Dict[str, float]:
        """计算综合置信度"""
        confidence_scores = {
            "repair_confidence": 0.0,
            "quality_confidence": 0.0,
            "academic_confidence": 0.0,
            "overall": 0.0
        }
        
        # 计算修复置信度
        if repair_actions:
            repair_confidences = [a.confidence for a in repair_actions if a.success]
            if repair_confidences:
                confidence_scores["repair_confidence"] = sum(repair_confidences) / len(repair_confidences)
        
        # 计算质量置信度（基于修复成功率）
        if repair_actions:
            success_rate = sum(1 for a in repair_actions if a.success) / len(repair_actions)
            confidence_scores["quality_confidence"] = success_rate
        
        # 计算学术置信度（基于修复质量）
        if repair_actions:
            # 假设高质量修复具有更高的学术价值
            quality_scores = []
            for action in repair_actions:
                if action.success:
                    # 基于修复类型和优先级计算质量得分
                    quality = 0.0
                    if action.priority == RepairPriority.CRITICAL:
                        quality = 0.9
                    elif action.priority == RepairPriority.HIGH:
                        quality = 0.8
                    elif action.priority == RepairPriority.MEDIUM:
                        quality = 0.7
                    else:
                        quality = 0.6
                    quality_scores.append(quality)
            
            if quality_scores:
                confidence_scores["academic_confidence"] = sum(quality_scores) / len(quality_scores)
        
        # 计算综合置信度
        weights = {
            "repair_confidence": 0.4,
            "quality_confidence": 0.3,
            "academic_confidence": 0.3
        }
        
        scores = []
        for metric, weight in weights.items():
            if metric in confidence_scores:
                scores.append(confidence_scores[metric] * weight)
        
        confidence_scores["overall"] = sum(scores) if scores else 0.0
        
        return confidence_scores
    
    def _update_performance_metrics(self, total_repairs: int, successful_repairs: int, duration: float):
        """更新性能指标"""
        self.performance_metrics["total_repairs"] += total_repairs
        self.performance_metrics["successful_repairs"] += successful_repairs
        self.performance_metrics["failed_repairs"] += total_repairs - successful_repairs
        self.performance_metrics["total_repair_time"] += duration
        
        # 更新平均修复时间
        if self.performance_metrics["total_repairs"] > 0:
            self.performance_metrics["average_repair_time"] = (
                self.performance_metrics["total_repair_time"] / self.performance_metrics["total_repairs"]
            )
    
    def get_repair_performance_report(self) -> Dict[str, Any]:
        """获取修复性能报告"""
        if not self.repair_actions:
            return {
                "message": "还没有执行任何修复行动",
                "performance_metrics": self.performance_metrics,
                "failed_stages": [self._serialize_stage_result(stage) for stage in self.failed_stages],
                "report_metadata": self._build_report_metadata(),
            }
        
        return {
            "performance_metrics": self.performance_metrics,
            "total_repairs": self.performance_metrics["total_repairs"],
            "successful_repairs": self.performance_metrics["successful_repairs"],
            "failed_repairs": self.performance_metrics["failed_repairs"],
            "average_repair_time": self.performance_metrics["average_repair_time"],
            "total_repair_time": self.performance_metrics["total_repair_time"],
            "success_rate": self.performance_metrics["successful_repairs"] / max(1, self.performance_metrics["total_repairs"]),
            "latest_repair_actions": [self._serialize_repair_action(a) for a in self.repair_actions[-5:]] if self.repair_actions else [],
            "failed_stages": [self._serialize_stage_result(stage) for stage in self.failed_stages],
            "report_metadata": self._build_report_metadata(),
        }
    
    def export_repair_data(self, output_path: str) -> bool:
        """导出修复数据"""
        try:
            repair_data = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                    "exported_file": os.path.basename(output_path),
                },
                "repair_framework_info": {
                    "framework_name": "智能修复框架",
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "performance_metrics": self.performance_metrics
                },
                "repair_actions": [self._serialize_repair_action(a) for a in self.repair_actions],
                "repair_history": [self._serialize_stage_result(stage) for stage in self.repair_history],
                "failed_stages": [self._serialize_stage_result(stage) for stage in self.failed_stages],
                "repair_rules": self._serialize_repair_rules(),
                "repair_performance_report": self.get_repair_performance_report(),
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(repair_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"修复数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"修复数据导出失败: {e}")
            return False
    
    def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 清理数据结构
            self.repair_actions.clear()
            self.repair_history.clear()
            self.failed_stages.clear()
            self.knowledge_graph.clear()
            
            self.logger.info("修复阶段管理器资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"修复阶段管理器资源清理失败: {e}")
            return False
