# research/research_pipeline.py
"""
中医古籍全自动研究系统 - 专业学术研究流程管理模块
基于AI的科研闭环流程管理系统
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.core.module_base import get_global_executor
from src.core.phase_tracker import PhaseTrackerMixin
from src.corpus.corpus_bundle import (
    CorpusBundle,
    extract_text_entries,
    is_corpus_bundle,
)
from src.corpus.local_collector import LocalCorpusCollector
from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor
from src.hypothesis import HypothesisEngine
from src.preprocessor.document_preprocessor import DocumentPreprocessor
from src.research.ctext_corpus_collector import CTextCorpusCollector
from src.research.gap_analyzer import GapAnalyzer
from src.research.literature_retriever import LiteratureRetriever
from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder

# 配置日志
logger = logging.getLogger(__name__)

# 供单测 patch 的符号；导入失败时在运行时再惰性加载。
try:
    from src.llm.llm_engine import LLMEngine as _ImportedLLMEngine
except Exception:
    _ImportedLLMEngine = None

LLMEngine = _ImportedLLMEngine

try:
    from src.llm.llm_service import CachedLLMService as _ImportedCachedLLMService
except Exception:
    _ImportedCachedLLMService = None

CachedLLMService = _ImportedCachedLLMService

try:
    from src.output.citation_manager import CitationManager as _ImportedCitationManager
except Exception:
    _ImportedCitationManager = None

CitationManager = _ImportedCitationManager


def _safe_researcher_key(researchers: List[str]) -> str:
    if not researchers:
        return "research"
    primary = str(researchers[0]).strip() or "research"
    compact = "".join(ch for ch in primary if ch.isalnum())
    return compact[:24] or "research"

class ResearchPhase(Enum):
    """
    研究阶段枚举
    """
    OBSERVE = "observe"          # 观察阶段
    HYPOTHESIS = "hypothesis"    # 假设阶段
    EXPERIMENT = "experiment"    # 实验阶段
    ANALYZE = "analyze"          # 分析阶段
    PUBLISH = "publish"          # 发布阶段
    REFLECT = "reflect"          # 反思阶段

class ResearchCycleStatus(Enum):
    """
    研究循环状态枚举
    """
    PENDING = "pending"      # 待处理
    ACTIVE = "active"        # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 已失败
    SUSPENDED = "suspended"  # 已暂停

@dataclass
class ResearchCycle:
    """
    研究循环数据结构
    """
    # 基础信息
    cycle_id: str
    cycle_name: str
    description: str
    
    # 状态信息
    status: ResearchCycleStatus = ResearchCycleStatus.PENDING
    current_phase: ResearchPhase = ResearchPhase.OBSERVE
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration: float = 0.0
    
    # 研究目标和范围
    research_objective: str = ""
    research_scope: str = ""
    target_audience: str = ""
    
    # 研究参与者
    researchers: List[str] = field(default_factory=list)
    advisors: List[str] = field(default_factory=list)
    
    # 资源配置
    resources: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    timeline: Dict[str, str] = field(default_factory=dict)
    
    # 阶段执行信息
    phase_executions: Dict[ResearchPhase, Dict[str, Any]] = field(default_factory=dict)
    
    # 研究成果
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    
    # 质量控制
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    
    # 专家评审
    expert_reviews: List[Dict[str, Any]] = field(default_factory=list)
    
    # 标签和分类
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class ResearchPipeline(PhaseTrackerMixin):
    """
    中医古籍全自动研究系统科研流程管理
    
    本模块实现了完整的科研闭环流程管理，包括：
    1. 研究循环设计与启动
    2. 多阶段任务执行与协调
    3. 质量控制与风险管理
    4. 成果产出与知识沉淀
    5. 反思改进与持续优化
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化研究流程管理器
        
        Args:
            config (Dict[str, Any]): 配置参数
        """
        self.config = config or {}
        self.research_cycles = {}
        self.active_cycles = {}
        self.failed_cycles: List[ResearchCycle] = []
        self.execution_history = []
        # 使用全局共享线程池，与 BaseModule 保持一致
        self.executor = get_global_executor(max_workers=4)
        self.logger = logging.getLogger(__name__)
        self._failed_operations: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self._governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get(
                "persist_failed_operations",
                self.config.get("persist_failed_cycles", True),
            ),
            "minimum_stable_completion_rate": float(
                self.config.get("minimum_stable_completion_rate", 0.8)
            ),
            "export_contract_version": self.config.get("export_contract_version", "d44.v1"),
        }
        self.hypothesis_engine = HypothesisEngine(self.config.get("hypothesis_engine_config") or {})
        self.hypothesis_engine.initialize()
        
        # 初始化质量控制指标
        self.quality_metrics = {
            "cycle_completion_rate": 0.0,
            "phase_efficiency": 0.0,
            "researcher_productivity": 0.0,
            "quality_assurance": 0.0
        }
        
        # 初始化资源监控
        self.resource_usage = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "storage_usage": 0.0,
            "network_usage": 0.0
        }
        
        self.logger.info("研究流程管理器初始化完成")

    def _initialize_cycle_tracking(self, cycle: ResearchCycle) -> None:
        cycle.metadata["phase_history"] = []
        cycle.metadata["phase_timings"] = {}
        cycle.metadata["completed_phases"] = []
        cycle.metadata["failed_phase"] = None
        cycle.metadata["final_status"] = cycle.status.value
        cycle.metadata["last_completed_phase"] = None
        cycle.metadata["failed_operations"] = []

    def _start_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self._governance_config.get("enable_phase_tracking", True):
            metadata.setdefault("phase_history", []).append(phase_entry)
        return phase_entry

    def _complete_phase(
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        if phase_name not in metadata.setdefault("completed_phases", []):
            metadata["completed_phases"].append(phase_name)
        metadata["last_completed_phase"] = phase_name
        metadata["final_status"] = "completed"

    def _fail_phase(
        self,
        metadata: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
        error: str,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        metadata["failed_phase"] = phase_name
        metadata["final_status"] = "failed"
        self._record_failed_operation(
            failed_operations,
            phase_name,
            error,
            duration,
            phase_entry.get("context", {}),
        )

    def _record_failed_operation(
        self,
        failed_operations: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._governance_config.get("persist_failed_operations", True):
            return
        failed_operations.append(
            {
                "operation": operation,
                "error": error,
                "details": self._serialize_value(details or {}),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration, 6),
            }
        )

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(self._metadata)

    def _mark_cycle_failed(self, cycle: ResearchCycle, phase_name: str, error: str) -> None:
        cycle.status = ResearchCycleStatus.FAILED
        cycle.metadata["failed_phase"] = phase_name
        cycle.metadata["error"] = error
        cycle.metadata["final_status"] = cycle.status.value
        cycle.completed_at = datetime.now().isoformat()
        if cycle.started_at:
            cycle.duration = (
                datetime.fromisoformat(cycle.completed_at) - datetime.fromisoformat(cycle.started_at)
            ).total_seconds()
        if cycle.cycle_id in self.active_cycles:
            del self.active_cycles[cycle.cycle_id]
        if all(existing.cycle_id != cycle.cycle_id for existing in self.failed_cycles):
            self.failed_cycles.append(cycle)
        self._record_failed_operation(
            cycle.metadata.setdefault("failed_operations", []),
            phase_name,
            error,
            cycle.duration,
            {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.cycle_name,
                "status": cycle.status.value,
                "failed_phase": phase_name,
            },
        )

    def _build_cycle_analysis_summary(self, cycle: ResearchCycle) -> Dict[str, Any]:
        completed_phases = cycle.metadata.get("completed_phases", [])
        total_outcomes = len(cycle.outcomes)
        total_deliverables = len(cycle.deliverables)
        summary_status = "pending"
        if cycle.status == ResearchCycleStatus.FAILED:
            summary_status = "needs_followup"
        elif cycle.status == ResearchCycleStatus.COMPLETED:
            summary_status = "stable"
        elif cycle.status == ResearchCycleStatus.SUSPENDED:
            summary_status = "paused"
        elif cycle.status == ResearchCycleStatus.ACTIVE:
            summary_status = "in_progress"

        return {
            "status": summary_status,
            "completed_phase_count": len(completed_phases),
            "completed_phases": completed_phases,
            "outcome_count": total_outcomes,
            "deliverable_count": total_deliverables,
            "last_phase": cycle.metadata.get("last_completed_phase", cycle.current_phase.value),
            "failed_phase": cycle.metadata.get("failed_phase", ""),
            "failed_operation_count": len(cycle.metadata.get("failed_operations", [])),
            "final_status": cycle.metadata.get("final_status", cycle.status.value),
        }

    def _build_pipeline_analysis_summary(self) -> Dict[str, Any]:
        total_cycles = len(self.research_cycles)
        completed_cycles = sum(
            1 for cycle in self.research_cycles.values() if cycle.status == ResearchCycleStatus.COMPLETED
        )
        failed_cycles = sum(
            1 for cycle in self.research_cycles.values() if cycle.status == ResearchCycleStatus.FAILED
        )
        completion_rate = (completed_cycles / total_cycles) if total_cycles else 0.0
        status = "idle"
        if self._failed_operations:
            status = "needs_followup"
        elif total_cycles > 0:
            status = (
                "stable"
                if completion_rate >= self._governance_config["minimum_stable_completion_rate"] and failed_cycles == 0
                else "degraded"
            )

        return {
            "total_cycles": total_cycles,
            "completed_cycles": completed_cycles,
            "failed_cycles": failed_cycles,
            "completion_rate": round(completion_rate, 4),
            "failed_operation_count": len(self._failed_operations),
            "status": status,
            "last_completed_phase": self._metadata.get("last_completed_phase"),
            "failed_phase": self._metadata.get("failed_phase"),
            "final_status": self._metadata.get("final_status", "initialized"),
        }

    def _serialize_phase_executions(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return {phase.value: self._serialize_value(execution) for phase, execution in cycle.phase_executions.items()}

    def _serialize_cycle(self, cycle: ResearchCycle) -> Dict[str, Any]:
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "description": cycle.description,
            "status": cycle.status.value,
            "current_phase": cycle.current_phase.value,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "duration": cycle.duration,
            "research_objective": cycle.research_objective,
            "research_scope": cycle.research_scope,
            "target_audience": cycle.target_audience,
            "researchers": cycle.researchers,
            "advisors": cycle.advisors,
            "resources": self._serialize_value(cycle.resources),
            "budget": cycle.budget,
            "timeline": self._serialize_value(cycle.timeline),
            "phase_executions": self._serialize_phase_executions(cycle),
            "outcomes": self._serialize_value(cycle.outcomes),
            "deliverables": self._serialize_value(cycle.deliverables),
            "quality_metrics": self._serialize_value(cycle.quality_metrics),
            "risk_assessment": self._serialize_value(cycle.risk_assessment),
            "expert_reviews": self._serialize_value(cycle.expert_reviews),
            "tags": self._serialize_value(cycle.tags),
            "categories": self._serialize_value(cycle.categories),
            "metadata": self._serialize_value(cycle.metadata),
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        runtime_metadata = self._build_runtime_metadata()
        return {
            "contract_version": self._governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "research_pipeline_report",
            "active_cycle_count": len(self.active_cycles),
            "completed_phases": list(runtime_metadata.get("completed_phases", [])),
            "failed_phase": runtime_metadata.get("failed_phase"),
            "failed_operation_count": len(self._failed_operations),
            "final_status": runtime_metadata.get("final_status", "initialized"),
            "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        }
    
    def create_research_cycle(
        self,
        cycle_name: str,
        description: str,
        objective: str,
        scope: str,
        researchers: Optional[List[str]] = None,
        **cycle_options: Any,
    ) -> ResearchCycle:
        """
        创建研究循环
        
        Args:
            cycle_name (str): 循环名称
            description (str): 循环描述
            objective (str): 研究目标
            scope (str): 研究范围
            researchers (List[str]): 研究人员
            advisors (List[str]): 指导专家
            resources (Dict[str, Any]): 资源配置
            
        Returns:
            ResearchCycle: 创建的研究循环
        """
        phase_entry = self._start_phase(
            self._metadata,
            "create_research_cycle",
            {"cycle_name": cycle_name, "scope": scope},
        )
        start_time = time.perf_counter()
        try:
            advisors = cycle_options.get("advisors") or []
            resources = cycle_options.get("resources") or {}

            # 生成循环ID
            cycle_id = f"cycle_{int(time.time())}_{hashlib.md5(cycle_name.encode()).hexdigest()[:8]}"
            
            # 创建研究循环
            research_cycle = ResearchCycle(
                cycle_id=cycle_id,
                cycle_name=cycle_name,
                description=description,
                research_objective=objective,
                research_scope=scope,
                researchers=researchers or [],
                advisors=advisors,
                resources=resources,
                tags=["created", "automated", "tcmautoresearch"]
            )
            self._initialize_cycle_tracking(research_cycle)
            research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
            
            # 存储循环
            self.research_cycles[cycle_id] = research_cycle
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "cycle_created",
                "cycle_id": cycle_id,
                "cycle_name": cycle_name
            })
            self._complete_phase(self._metadata, "create_research_cycle", phase_entry, start_time)
            
            self.logger.info(f"研究循环创建完成: {cycle_name}")
            return research_cycle
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "create_research_cycle", phase_entry, start_time, str(e))
            self.logger.error(f"研究循环创建失败: {e}")
            raise
    
    def start_research_cycle(self, cycle_id: str) -> bool:
        """
        启动研究循环
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            bool: 启动是否成功
        """
        phase_entry = self._start_phase(self._metadata, "start_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.research_cycles:
                self.logger.warning(f"研究循环 {cycle_id} 不存在")
                self._fail_phase(
                    self._metadata,
                    self._failed_operations,
                    "start_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False
            
            research_cycle = self.research_cycles[cycle_id]
            
            # 更新状态
            research_cycle.status = ResearchCycleStatus.ACTIVE
            research_cycle.started_at = datetime.now().isoformat()
            research_cycle.current_phase = ResearchPhase.OBSERVE
            research_cycle.metadata["final_status"] = research_cycle.status.value
            
            # 记录活动
            self.active_cycles[cycle_id] = research_cycle
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "cycle_started",
                "cycle_id": cycle_id,
                "phase": research_cycle.current_phase.value
            })
            self._complete_phase(self._metadata, "start_research_cycle", phase_entry, start_time)
            
            self.logger.info(f"研究循环启动: {research_cycle.cycle_name}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "start_research_cycle", phase_entry, start_time, str(e))
            self.logger.error(f"研究循环启动失败: {e}")
            return False
    
    def execute_research_phase(self, cycle_id: str, 
                              phase: ResearchPhase,
                              phase_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行研究阶段
        
        Args:
            cycle_id (str): 循环ID
            phase (ResearchPhase): 研究阶段
            phase_context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = time.time()
        
        try:
            if cycle_id not in self.research_cycles:
                self.logger.warning(f"研究循环 {cycle_id} 不存在")
                return {"error": "循环不存在"}
            
            research_cycle = self.research_cycles[cycle_id]
            
            # 检查循环状态
            if research_cycle.status != ResearchCycleStatus.ACTIVE:
                self.logger.warning(f"研究循环 {cycle_id} 不处于活跃状态")
                return {"error": "循环未激活"}

            phase_entry = self._start_phase(research_cycle.metadata, phase.value, phase_context or {})
            
            # 执行阶段
            phase_result = self._execute_phase_internal(phase, research_cycle, phase_context or {})
            
            # 更新循环状态
            if phase == ResearchPhase.OBSERVE:
                research_cycle.current_phase = ResearchPhase.HYPOTHESIS
            elif phase == ResearchPhase.HYPOTHESIS:
                research_cycle.current_phase = ResearchPhase.EXPERIMENT
            elif phase == ResearchPhase.EXPERIMENT:
                research_cycle.current_phase = ResearchPhase.ANALYZE
            elif phase == ResearchPhase.ANALYZE:
                research_cycle.current_phase = ResearchPhase.PUBLISH
            elif phase == ResearchPhase.PUBLISH:
                research_cycle.current_phase = ResearchPhase.REFLECT
            elif phase == ResearchPhase.REFLECT:
                research_cycle.current_phase = ResearchPhase.OBSERVE  # 循环回起点
            
            # 记录阶段执行信息
            phase_execution = {
                "phase": phase.value,
                "started_at": phase_entry["started_at"],
                "completed_at": datetime.now().isoformat(),
                "duration": time.time() - start_time,
                "context": phase_context or {},
                "result": phase_result
            }
            
            research_cycle.phase_executions[phase] = phase_execution
            self._complete_phase(research_cycle.metadata, phase.value, phase_entry, start_time)
            phase_entry["completed_at"] = phase_execution["completed_at"]
            phase_entry["duration"] = phase_execution["duration"]
            phase_entry["result"] = self._serialize_value(phase_result)
            research_cycle.metadata["final_status"] = research_cycle.status.value

            if isinstance(phase_result, dict):
                research_cycle.outcomes.append({"phase": phase.value, "result": phase_result})
                if phase == ResearchPhase.PUBLISH:
                    research_cycle.deliverables = phase_result.get("deliverables", [])
                if phase == ResearchPhase.ANALYZE:
                    research_cycle.quality_metrics = phase_result.get("results", {})

            research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "phase_executed",
                "cycle_id": cycle_id,
                "phase": phase.value,
                "duration": time.time() - start_time
            })
            
            self.logger.info(f"研究阶段执行完成: {phase.value}")
            return phase_result
            
        except Exception as e:
            self.logger.error(f"研究阶段执行失败: {e}")
            if cycle_id in self.research_cycles:
                research_cycle = self.research_cycles[cycle_id]
                history = research_cycle.metadata.get("phase_history", [])
                if history and history[-1].get("phase") == phase.value:
                    failure_details = {
                        "cycle_id": research_cycle.cycle_id,
                        "cycle_name": research_cycle.cycle_name,
                        "status": research_cycle.status.value,
                        "phase": phase.value,
                    }
                    history[-1]["context"] = self._serialize_value(
                        {
                            **(history[-1].get("context") or {}),
                            **failure_details,
                        }
                    )
                    self._fail_phase(
                        research_cycle.metadata,
                        research_cycle.metadata.setdefault("failed_operations", []),
                        phase.value,
                        history[-1],
                        start_time,
                        str(e),
                    )
                    history[-1]["completed_at"] = datetime.now().isoformat()
                    history[-1]["duration"] = time.time() - start_time
                    self._record_failed_operation(
                        self._failed_operations,
                        phase.value,
                        str(e),
                        time.time() - start_time,
                        failure_details,
                    )
                self._mark_cycle_failed(research_cycle, phase.value, str(e))
                research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
                self.execution_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "phase_failed",
                    "cycle_id": cycle_id,
                    "phase": phase.value,
                    "error": str(e),
                })
            return {"error": str(e)}
    
    def _execute_phase_internal(self, phase: ResearchPhase, 
                              cycle: ResearchCycle,
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """
        内部执行阶段逻辑
        
        Args:
            phase (ResearchPhase): 研究阶段
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        # 根据阶段执行不同的逻辑
        if phase == ResearchPhase.OBSERVE:
            return self._execute_observe_phase(cycle, context)
        elif phase == ResearchPhase.HYPOTHESIS:
            return self._execute_hypothesis_phase(cycle, context)
        elif phase == ResearchPhase.EXPERIMENT:
            return self._execute_experiment_phase(cycle, context)
        elif phase == ResearchPhase.ANALYZE:
            return self._execute_analyze_phase(cycle, context)
        elif phase == ResearchPhase.PUBLISH:
            return self._execute_publish_phase(cycle, context)
        elif phase == ResearchPhase.REFLECT:
            return self._execute_reflect_phase(cycle, context)
        else:
            return {"error": f"未知阶段: {phase.value}"}
    
    def _execute_observe_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行观察阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        context = context or {}

        corpus_result = self._collect_observe_corpus_if_enabled(context)
        literature_result = self._run_observe_literature_if_enabled(context)

        observations, findings = self._build_observe_seed_lists()
        self._append_corpus_observe_updates(corpus_result, observations, findings)

        ingestion_result = self._run_observe_ingestion_if_enabled(corpus_result, context)
        self._append_ingestion_observe_updates(ingestion_result, observations, findings)

        self._append_literature_observe_updates(literature_result, observations, findings)

        return {
            "phase": "observe",
            "observations": observations,
            "findings": findings,
            "corpus_collection": corpus_result,
            "ingestion_pipeline": ingestion_result,
            "literature_pipeline": literature_result,
            "metadata": self._build_observe_metadata(
                context,
                observations,
                findings,
                corpus_result,
                ingestion_result,
                literature_result,
            )
        }

    def _build_observe_seed_lists(self) -> Tuple[List[str], List[str]]:
        observations = [
            "收集到原始中医古籍文本数据",
            "识别出多个方剂实例",
            "发现不同朝代的用药规律",
            "提取出关键症候信息"
        ]
        findings = [
            "方剂组成存在地域差异",
            "药材使用呈现时代演变特征",
            "症候分类具有系统性规律"
        ]
        return observations, findings

    def _collect_observe_corpus_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collect_ctext = self._should_collect_ctext_corpus(context)
        collect_local = self._should_collect_local_corpus(context)

        if not collect_ctext and not collect_local:
            return None

        bundles: List[CorpusBundle] = []
        fallback_error: Optional[Dict[str, Any]] = None

        ctext_result = self._collect_ctext_observation_corpus(context) if collect_ctext else None
        fallback_error = self._register_observe_collection_result(
            ctext_result,
            "ctext",
            bundles,
            fallback_error,
        )

        local_result = self._collect_local_observation_corpus(context) if collect_local else None
        fallback_error = self._register_observe_collection_result(
            local_result,
            "local",
            bundles,
            fallback_error,
        )

        if bundles:
            merged = CorpusBundle.merge(bundles) if len(bundles) > 1 else bundles[0]
            return merged.to_dict()
        return fallback_error

    def _register_observe_collection_result(
        self,
        source_result: Optional[Dict[str, Any]],
        source_type: str,
        bundles: List[CorpusBundle],
        fallback_error: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not source_result:
            return fallback_error
        if source_result.get("error"):
            return fallback_error or source_result

        bundle = self._to_observe_corpus_bundle(source_result, source_type)
        if bundle:
            bundles.append(bundle)
        return fallback_error

    def _to_observe_corpus_bundle(
        self,
        source_result: Dict[str, Any],
        source_type: str,
    ) -> Optional[CorpusBundle]:
        if source_type == "ctext":
            return CorpusBundle.from_ctext_result(source_result)
        if source_type == "local" and is_corpus_bundle(source_result):
            return CorpusBundle.from_dict(source_result)
        return None

    def _run_observe_literature_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._should_run_observe_literature(context):
            return None
        return self._run_observe_literature_pipeline(context)

    def _run_observe_ingestion_if_enabled(
        self,
        corpus_result: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not corpus_result or corpus_result.get("error"):
            return None
        if not self._should_run_observe_ingestion(context):
            return None
        return self._run_observe_ingestion_pipeline(corpus_result, context)

    def _append_corpus_observe_updates(
        self,
        corpus_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        if not corpus_result:
            return
        if corpus_result.get("error"):
            findings.append(f"语料采集失败: {corpus_result['error']}")
            return

        # 新格式（CorpusBundle）
        if is_corpus_bundle(corpus_result):
            stats = corpus_result.get("stats", {})
            sources = corpus_result.get("sources", [])
            total = stats.get("total_documents", 0)
            # 单 CText 来源：沿用旧提示语保持向后兼容
            if sources == ["ctext"]:
                observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get('document_count', total)} 个根文献")
                findings.insert(0, "观察阶段已接入标准语料白名单，可直接进入后续假设生成")
            else:
                source_label = "+".join(sources) if sources else "多来源"
                observations.insert(0, f"已从 {source_label} 自动采集 {total} 篇文档（CorpusBundle）")
                findings.insert(0, "观察阶段已输出统一 CorpusBundle，多来源文档可直接进入后续假设生成")
            return

        # 旧格式（CText raw dict）
        stats = corpus_result.get("stats", {})
        observations.insert(0, f"已从 ctext 白名单自动采集 {stats.get('document_count', 0)} 个根文献")
        findings.insert(0, "观察阶段已接入标准语料白名单，可直接进入后续假设生成")

    def _append_ingestion_observe_updates(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        if not ingestion_result:
            return
        if ingestion_result.get("error"):
            findings.append(f"预处理、实体抽取与语义建模链路失败: {ingestion_result['error']}")
            return

        aggregate = ingestion_result.get("aggregate", {})
        observations.append(
            f"已完成 {ingestion_result.get('processed_document_count', 0)} 篇文本的预处理、实体抽取与语义建模"
        )
        findings.append(
            f"首段主流程累计识别 {aggregate.get('total_entities', 0)} 个实体"
        )
        findings.append(
            f"累计构建 {aggregate.get('semantic_graph_nodes', 0)} 个语义节点与 {aggregate.get('semantic_graph_edges', 0)} 条关系"
        )

    def _append_literature_observe_updates(
        self,
        literature_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        if not literature_result:
            return
        if literature_result.get("error"):
            findings.append(f"文献检索链路失败: {literature_result['error']}")
            return

        clinical_gap = (literature_result.get("clinical_gap_analysis") or {})
        evidence_matrix = literature_result.get("evidence_matrix", {})
        observations.append(
            f"已完成 {literature_result.get('record_count', 0)} 条医学文献检索并抽取摘要证据"
        )
        findings.append(
            f"证据矩阵覆盖 {evidence_matrix.get('dimension_count', 0)} 个维度"
        )
        findings.append(
            f"文献来源统计: {', '.join(literature_result.get('source_counts_summary', [])) or '无'}"
        )
        if clinical_gap.get("report"):
            findings.append("已完成 Qwen 临床关联 Gap Analysis，可直接用于选题与方案设计")

    def _build_observe_metadata(
        self,
        context: Dict[str, Any],
        observations: List[str],
        findings: List[str],
        corpus_result: Optional[Dict[str, Any]],
        ingestion_result: Optional[Dict[str, Any]],
        literature_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        clinical_gap = ((literature_result or {}).get("clinical_gap_analysis") or {})
        ingestion_ok = bool(ingestion_result and not ingestion_result.get("error"))
        literature_ok = bool(literature_result and not literature_result.get("error"))
        downstream_processing, semantic_modeling = self._build_observe_ingestion_flags(
            ingestion_result,
            ingestion_ok,
        )

        return {
            "data_source": self._resolve_observe_data_source(context),
            "observation_count": len(observations),
            "finding_count": len(findings),
            "auto_collected_ctext": self._is_ctext_corpus_collected(corpus_result),
            "auto_collected_corpus": bool(corpus_result),
            "corpus_schema": "bundle" if is_corpus_bundle(corpus_result) else ("ctext_raw" if corpus_result else None),
            "ctext_groups": self._resolve_whitelist_groups(context),
            "downstream_processing": downstream_processing,
            "semantic_modeling": semantic_modeling,
            "literature_retrieval": literature_ok,
            "evidence_matrix": self._has_observe_evidence_matrix(literature_result, literature_ok),
            "clinical_gap_analysis": bool(literature_ok and clinical_gap.get("report"))
        }

    def _is_ctext_corpus_collected(self, corpus_result: Optional[Dict[str, Any]]) -> bool:
        if not corpus_result:
            return False
        if not is_corpus_bundle(corpus_result):
            return True
        return "ctext" in (corpus_result.get("sources") or [])

    def _build_observe_ingestion_flags(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        ingestion_ok: bool,
    ) -> Tuple[bool, bool]:
        if not ingestion_ok or not ingestion_result:
            return False, False

        downstream_processing = ingestion_result.get("processed_document_count", 0) > 0
        semantic_modeling = ingestion_result.get("aggregate", {}).get("semantic_graph_nodes", 0) > 0
        return bool(downstream_processing), bool(semantic_modeling)

    def _has_observe_evidence_matrix(
        self,
        literature_result: Optional[Dict[str, Any]],
        literature_ok: bool,
    ) -> bool:
        if not literature_ok or not literature_result:
            return False
        return bool(literature_result.get("evidence_matrix", {}).get("record_count", 0) > 0)

    def _should_run_observe_ingestion(self, context: Dict[str, Any]) -> bool:
        if "run_preprocess_and_extract" in context:
            return bool(context.get("run_preprocess_and_extract"))

        observe_pipeline_config = self.config.get("observe_pipeline", {})
        return bool(observe_pipeline_config.get("enabled", True))

    def _should_run_observe_literature(self, context: Dict[str, Any]) -> bool:
        if "run_literature_retrieval" in context:
            return bool(context.get("run_literature_retrieval"))

        literature_config = self.config.get("literature_retrieval", {})
        return bool(literature_config.get("enabled", False))

    def _run_observe_literature_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        literature_config = self.config.get("literature_retrieval", {})
        sources = context.get("literature_sources") or literature_config.get(
            "default_sources",
            ["pubmed", "semantic_scholar", "plos_one", "arxiv"]
        )
        query = context.get("literature_query") or context.get("query") or "traditional chinese medicine"
        raw_max_results = context.get("literature_max_results", literature_config.get("max_results_per_source", 5))
        max_results = max(1, min(int(raw_max_results), 50))
        offline_plan_only = bool(
            context.get(
                "literature_offline_plan_only",
                literature_config.get("offline_plan_only", False)
            )
        )

        retriever = LiteratureRetriever(
            {
                "timeout_sec": literature_config.get("timeout_sec", 20),
                "retry_count": literature_config.get("retry_count", 2),
                "request_interval_sec": literature_config.get("request_interval_sec", 0.2),
                "user_agent": literature_config.get("user_agent", "TCM-AutoResearch-Observe/1.0")
            }
        )

        try:
            retrieval_result = retriever.search(
                query=query,
                sources=sources,
                max_results_per_source=max_results,
                pubmed_email=context.get("pubmed_email", literature_config.get("pubmed_email", "")),
                pubmed_api_key=context.get("pubmed_api_key", literature_config.get("pubmed_api_key", "")),
                offline_plan_only=offline_plan_only,
            )
        except Exception as e:
            self.logger.error(f"观察阶段文献检索失败: {e}")
            return {"error": str(e)}
        finally:
            retriever.close()

        summaries = self._extract_literature_summaries(retrieval_result.get("records", []))
        evidence_matrix = self._build_evidence_matrix(summaries, context)
        clinical_gap_result = None
        if self._should_run_clinical_gap_analysis(context):
            clinical_gap_result = self._run_clinical_gap_analysis(evidence_matrix, summaries, context)

        source_counts = retrieval_result.get("source_stats", {})
        source_counts_summary = [
            f"{source}:{(stats or {}).get('count', 0)}"
            for source, stats in source_counts.items()
        ]

        return {
            "query": retrieval_result.get("query", query),
            "sources": retrieval_result.get("sources", sources),
            "record_count": len(retrieval_result.get("records", [])),
            "abstract_summary_count": len(summaries),
            "records": retrieval_result.get("records", []),
            "query_plans": retrieval_result.get("query_plans", []),
            "errors": retrieval_result.get("errors", []),
            "source_stats": source_counts,
            "source_counts_summary": source_counts_summary,
            "summaries": summaries,
            "evidence_matrix": evidence_matrix,
            "clinical_gap_analysis": clinical_gap_result,
        }

    def _should_run_clinical_gap_analysis(self, context: Dict[str, Any]) -> bool:
        if "run_clinical_gap_analysis" in context:
            return bool(context.get("run_clinical_gap_analysis"))

        gap_config = self.config.get("clinical_gap_analysis", {})
        return bool(gap_config.get("enabled", False))

    def _run_clinical_gap_analysis(
        self,
        evidence_matrix: Dict[str, Any],
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        # 延迟导入：CachedLLMService 依赖 llama-cpp-python（重量级），只在实际调用时加载
        global CachedLLMService
        if CachedLLMService is None:
            from src.llm.llm_service import CachedLLMService as _CLS

            CachedLLMService = _CLS

        gap_config = self.config.get("clinical_gap_analysis", {})
        llm_config = self.config.get("models", {}).get("llm", {})
        clinical_question = (
            context.get("clinical_question")
            or context.get("literature_query")
            or "中医干预在目标人群中的临床有效性与安全性证据缺口是什么？"
        )
        output_language = context.get("gap_output_language", gap_config.get("output_language", "zh"))

        # CachedLLMService 磁盘缓存：相同请求直接从 SQLite 返回，跳过 GPU 推理
        engine = CachedLLMService.from_gap_config(gap_config, llm_config)
        analyzer = GapAnalyzer(gap_config, llm_service=engine)

        try:
            engine.load()
            analyzer.initialize()
            report = analyzer.analyze(
                clinical_question=clinical_question,
                evidence_matrix=evidence_matrix,
                literature_summaries=summaries,
                output_language=output_language,
            )
            stats = engine.cache_stats()
            self.logger.debug(
                "LLM 缓存统计: hits=%d misses=%d total_entries=%s",
                stats.get("session_hits", 0),
                stats.get("session_misses", 0),
                stats.get("total_entries", "n/a"),
            )
            return {
                "clinical_question": clinical_question,
                "output_language": output_language,
                "report": report,
            }
        except Exception as e:
            self.logger.error(f"Qwen 临床 Gap Analysis 失败: {e}")
            return {
                "clinical_question": clinical_question,
                "output_language": output_language,
                "error": str(e),
            }
        finally:
            analyzer.cleanup()
            engine.unload()

    def _extract_literature_summaries(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for item in records:
            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()
            text = abstract or title
            if not text:
                continue

            summaries.append(
                {
                    "source": item.get("source", ""),
                    "title": title,
                    "year": item.get("year"),
                    "doi": item.get("doi", ""),
                    "url": item.get("url", ""),
                    "summary_text": text[:1200],
                    "has_abstract": bool(abstract),
                }
            )
        return summaries

    def _build_evidence_matrix(
        self,
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        default_dimensions: Dict[str, List[str]] = {
            "condition_terms": ["covid", "diabetes", "cancer", "depression", "inflammation", "pain"],
            "intervention_terms": ["traditional chinese medicine", "tcm", "herb", "formula", "decoction", "acupuncture"],
            "outcome_terms": ["efficacy", "effectiveness", "safety", "survival", "risk", "response"],
            "method_terms": ["randomized", "meta-analysis", "cohort", "case-control", "network", "machine learning"],
        }

        dimension_keywords = context.get("evidence_dimensions") or default_dimensions
        records: List[Dict[str, Any]] = []
        dimension_hit_counts = {key: 0 for key in dimension_keywords.keys()}

        for item in summaries:
            text = f"{item.get('title', '')} {item.get('summary_text', '')}".lower()
            row_hits: Dict[str, List[str]] = {}

            for dimension, keywords in dimension_keywords.items():
                hits = [kw for kw in keywords if kw.lower() in text]
                row_hits[dimension] = hits
                if hits:
                    dimension_hit_counts[dimension] += 1

            coverage_score = sum(1 for hits in row_hits.values() if hits)
            records.append(
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "year": item.get("year"),
                    "coverage_score": coverage_score,
                    "dimension_hits": row_hits,
                }
            )

        records.sort(key=lambda r: r.get("coverage_score", 0), reverse=True)
        return {
            "dimension_count": len(dimension_keywords),
            "dimension_keywords": dimension_keywords,
            "dimension_hit_counts": dimension_hit_counts,
            "record_count": len(records),
            "records": records,
        }

    def _should_collect_ctext_corpus(self, context: Dict[str, Any]) -> bool:
        ctext_config = self.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})

        if "use_ctext_whitelist" in context:
            return bool(context.get("use_ctext_whitelist"))

        if context.get("data_source") == "ctext_whitelist":
            return True

        return bool(ctext_config.get("enabled") and whitelist_config.get("enabled"))

    def _should_collect_local_corpus(self, context: Dict[str, Any]) -> bool:
        if "use_local_corpus" in context:
            return bool(context.get("use_local_corpus"))

        if context.get("data_source") == "local":
            return True

        local_config = self.config.get("local_corpus", {})
        return bool(local_config.get("enabled"))

    def _collect_local_observation_corpus(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        local_config = self.config.get("local_corpus", {})
        collector = LocalCorpusCollector(
            {
                "data_dir": context.get("local_data_dir", local_config.get("data_dir", "data")),
                "file_glob": context.get("file_glob", local_config.get("file_glob", "*.txt")),
                "max_files": context.get("local_max_files", local_config.get("max_files", 50)),
                "recursive": context.get("local_recursive", local_config.get("recursive", False)),
                "encoding_fallbacks": local_config.get("encoding_fallbacks"),
                "min_text_length": local_config.get("min_text_length", 50),
            }
        )
        initialized = collector.initialize()
        if not initialized:
            return {"error": "本地语料采集器初始化失败"}
        try:
            return collector.execute(context)
        except Exception as e:
            self.logger.error("观察阶段本地语料采集失败: %s", e)
            return {"error": str(e)}
        finally:
            collector.cleanup()

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        if self._should_collect_ctext_corpus(context) and self._should_collect_local_corpus(context):
            return "ctext_whitelist+local"
        if self._should_collect_ctext_corpus(context):
            return "ctext_whitelist"
        if self._should_collect_local_corpus(context):
            return "local"
        return context.get("data_source", "unknown")

    def _resolve_whitelist_groups(self, context: Dict[str, Any]) -> List[str]:
        ctext_config = self.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})
        return context.get("whitelist_groups") or whitelist_config.get("default_groups", [])

    def _collect_ctext_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctext_config = self.config.get("ctext_corpus", {})
        whitelist_config = ctext_config.get("whitelist", {})

        collector = CTextCorpusCollector(
            {
                "api_base": context.get("api_base", ctext_config.get("api_base", "https://api.ctext.org")),
                "request_interval_sec": context.get("request_interval_sec", ctext_config.get("request_interval_sec", 0.2)),
                "retry_count": context.get("retry_count", ctext_config.get("retry_count", 2)),
                "timeout_sec": context.get("timeout_sec", ctext_config.get("timeout_sec", 20)),
                "output_dir": context.get("output_dir", os.path.join("data", "ctext"))
            }
        )

        initialized = collector.initialize()
        if not initialized:
            return {"error": "ctext 采集器初始化失败"}

        try:
            return collector.execute(
                {
                    "use_whitelist": True,
                    "whitelist_path": context.get("whitelist_path", whitelist_config.get("path")),
                    "whitelist_groups": self._resolve_whitelist_groups(context),
                    "recurse": context.get("recurse", True),
                    "max_depth": context.get("max_depth", 3),
                    "save_to_disk": context.get("save_to_disk", True),
                    "output_dir": context.get("output_dir", os.path.join("data", "ctext"))
                }
            )
        except Exception as e:
            self.logger.error(f"观察阶段 ctext 采集失败: {e}")
            return {"error": str(e)}
        finally:
            collector.cleanup()

    def _run_observe_ingestion_pipeline(self, corpus_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        text_entries = self._extract_corpus_text_entries(corpus_result)
        max_texts = max(1, min(int(context.get("max_texts", 3)), 20))
        max_chars_per_text = max(200, min(int(context.get("max_chars_per_text", 1200)), 4000))
        selected_entries = text_entries[:max_texts]

        if not selected_entries:
            return {
                "processed_document_count": 0,
                "documents": [],
                "aggregate": {
                    "total_entities": 0,
                    "entity_type_counts": {},
                    "average_confidence": 0.0
                }
            }

        preprocessor = DocumentPreprocessor(context.get("preprocessor_config") or {})
        extractor = AdvancedEntityExtractor(context.get("extractor_config") or {})
        semantic_builder = SemanticGraphBuilder(context.get("semantic_builder_config") or {})

        if not preprocessor.initialize():
            return {"error": "文档预处理器初始化失败"}
        if not extractor.initialize():
            preprocessor.cleanup()
            return {"error": "实体抽取器初始化失败"}
        if not semantic_builder.initialize():
            extractor.cleanup()
            preprocessor.cleanup()
            return {"error": "语义图构建器初始化失败"}

        document_results: List[Dict[str, Any]] = []
        entity_type_counts: Dict[str, int] = {}
        total_entities = 0
        confidence_values: List[float] = []
        total_semantic_nodes = 0
        total_semantic_edges = 0

        try:
            for entry in selected_entries:
                raw_text = entry.get("text", "")[:max_chars_per_text]
                preprocess_result = preprocessor.execute(
                    {
                        "raw_text": raw_text,
                        "source_file": entry.get("urn", "unknown"),
                        "metadata": {
                            "title": entry.get("title", ""),
                            "source": "ctext",
                            "collection_stage": "observe"
                        }
                    }
                )
                extraction_result = extractor.execute(preprocess_result)
                semantic_result = semantic_builder.execute(extraction_result)

                entities = extraction_result.get("entities", [])
                total_entities += len(entities)
                confidence_values.extend(entity.get("confidence", 0.0) for entity in entities)
                graph_stats = semantic_result.get("graph_statistics", {})
                total_semantic_nodes += graph_stats.get("nodes_count", 0)
                total_semantic_edges += graph_stats.get("edges_count", 0)

                for entity_type, count in extraction_result.get("statistics", {}).get("by_type", {}).items():
                    entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + count

                document_results.append(
                    {
                        "urn": entry.get("urn", ""),
                        "title": entry.get("title", ""),
                        "raw_text_preview": raw_text[:120],
                        "processed_text_preview": preprocess_result.get("processed_text", "")[:120],
                        "entity_count": len(entities),
                        "entity_types": extraction_result.get("statistics", {}).get("by_type", {}),
                        "average_confidence": extraction_result.get("confidence_scores", {}).get("average_confidence", 0.0),
                        "semantic_graph_nodes": graph_stats.get("nodes_count", 0),
                        "semantic_graph_edges": graph_stats.get("edges_count", 0),
                        "relationship_types": graph_stats.get("relationships_by_type", {})
                    }
                )

            average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
            return {
                "processed_document_count": len(document_results),
                "documents": document_results,
                "aggregate": {
                    "total_entities": total_entities,
                    "entity_type_counts": entity_type_counts,
                    "average_confidence": average_confidence,
                    "semantic_graph_nodes": total_semantic_nodes,
                    "semantic_graph_edges": total_semantic_edges
                }
            }
        except Exception as e:
            self.logger.error(f"观察阶段预处理/抽取/建模链路失败: {e}")
            return {"error": str(e)}
        finally:
            semantic_builder.cleanup()
            extractor.cleanup()
            preprocessor.cleanup()

    def _extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """统一文本条目提取 — 兼容新 CorpusBundle 格式与旧 CText dict 格式。"""
        return extract_text_entries(corpus_result)
    
    def _execute_hypothesis_phase(self, cycle: ResearchCycle, 
                                context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行假设阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        hypothesis_context = self._build_hypothesis_context(cycle, context or {})
        result = self.hypothesis_engine.execute(hypothesis_context)
        result.setdefault("phase", "hypothesis")
        return result

    def _build_hypothesis_context(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(ResearchPhase.OBSERVE, {}).get("result", {})
        existing_hypotheses = cycle.phase_executions.get(ResearchPhase.HYPOTHESIS, {}).get("result", {}).get("hypotheses", [])

        observations = observe_result.get("observations", [])
        findings = observe_result.get("findings", [])
        literature_pipeline = observe_result.get("literature_pipeline") or {}
        corpus_collection = observe_result.get("corpus_collection") or {}
        ingestion_pipeline = observe_result.get("ingestion_pipeline") or {}

        entities = context.get("entities") or ingestion_pipeline.get("entities") or corpus_collection.get("entities") or []
        contradictions = context.get("contradictions") or observe_result.get("contradictions") or []

        return {
            "research_objective": cycle.research_objective or context.get("research_objective") or cycle.description,
            "research_scope": cycle.research_scope or context.get("research_scope") or "",
            "research_domain": context.get("research_domain") or self._infer_hypothesis_domain(cycle, observations, findings),
            "observations": observations,
            "findings": findings,
            "entities": entities,
            "literature_pipeline": literature_pipeline,
            "contradictions": contradictions,
            "existing_hypotheses": existing_hypotheses,
            "use_llm_generation": context.get("use_llm_generation", False),
            "llm_service": context.get("llm_service"),
        }

    def _infer_hypothesis_domain(
        self,
        cycle: ResearchCycle,
        observations: List[str],
        findings: List[str],
    ) -> str:
        text_blob = " ".join(
            [
                cycle.research_scope or "",
                cycle.research_objective or "",
                cycle.description or "",
                *observations,
                *findings,
            ]
        )
        if any(token in text_blob for token in ["历史", "古籍", "朝代", "演变"]):
            return "historical_research"
        if any(token in text_blob for token in ["方剂", "配伍", "处方"]):
            return "formula_research"
        if any(token in text_blob for token in ["药物", "药材", "本草"]):
            return "herb_research"
        return "integrative_research"
    
    def _execute_experiment_phase(self, cycle: ResearchCycle, 
                                context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行实验阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        # 模拟实验阶段的执行
        experiment_results = {
            "study_design": "对照实验设计",
            "sample_size": 100,
            "duration_days": 30,
            "methodology": "数据挖掘与统计分析",
            "validation_metrics": {
                "accuracy": 0.92,
                "precision": 0.89,
                "recall": 0.87,
                "f1_score": 0.88
            },
            "data_sources": ["古籍文本", "现代数据库", "专家知识"]
        }
        
        return {
            "phase": "experiment",
            "results": experiment_results,
            "metadata": {
                "study_type": "quantitative_analysis",
                "validation_status": "approved"
            }
        }
    
    def _execute_analyze_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行分析阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        # 模拟分析阶段的执行
        analysis_results = {
            "statistical_significance": True,
            "confidence_level": 0.95,
            "effect_size": 0.75,
            "p_value": 0.003,
            "interpretation": "发现方剂剂量与疗效存在显著相关性，符合中医理论预期",
            "limitations": ["样本规模有限", "数据来源单一", "时间跨度较短"]
        }
        
        return {
            "phase": "analyze",
            "results": analysis_results,
            "metadata": {
                "analysis_type": "statistical_analysis",
                "significance_level": 0.05
            }
        }
    
    def _execute_publish_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行发布阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        observe_result = cycle.phase_executions.get(ResearchPhase.OBSERVE, {}).get("result", {})
        literature_pipeline = observe_result.get("literature_pipeline") or {}
        citation_records = self._collect_citation_records(cycle, context, literature_pipeline)
        citation_manager = CitationManager(self.config.get("citation_management") or {})
        citation_manager.initialize()
        citation_result = citation_manager.execute({"records": citation_records})
        citation_manager.cleanup()

        publications = [
            {
                "title": "基于AI的中医古籍方剂分析研究",
                "journal": "中医研究学报",
                "authors": cycle.researchers,
                "keywords": ["AI", "中医", "古籍", "方剂", "数据分析"],
                "status": "submitted",
                "citation_key": f"{_safe_researcher_key(cycle.researchers)}2026AI",
            },
            {
                "title": "古代方剂剂量演变规律研究",
                "journal": "中医药学报",
                "authors": cycle.researchers,
                "keywords": ["剂量", "历史", "演变", "中医"],
                "status": "accepted",
                "citation_key": f"{_safe_researcher_key(cycle.researchers)}2026Dose",
            }
        ]
        
        deliverables = [
            "研究报告",
            "数据集",
            "分析工具包",
            "可视化图表",
        ]
        if citation_result.get("bibtex"):
            deliverables.append("BibTeX 参考文献")
        if citation_result.get("gbt7714"):
            deliverables.append("GB/T 7714 参考文献")
        
        return {
            "phase": "publish",
            "publications": publications,
            "deliverables": deliverables,
            "citations": citation_result.get("entries", []),
            "bibtex": citation_result.get("bibtex", ""),
            "gbt7714": citation_result.get("gbt7714", ""),
            "metadata": {
                "publication_count": len(publications),
                "deliverable_count": len(deliverables),
                "citation_count": citation_result.get("citation_count", 0),
            }
        }

    def _collect_citation_records(
        self,
        cycle: ResearchCycle,
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        context_records = context.get("citation_records")
        if isinstance(context_records, list):
            return [dict(item) for item in context_records if isinstance(item, dict)]

        literature_records = literature_pipeline.get("records")
        if isinstance(literature_records, list) and literature_records:
            return [dict(item) for item in literature_records if isinstance(item, dict)]

        publications = [
            {
                "title": outcome.get("result", {}).get("title", "") or outcome.get("result", {}).get("phase", ""),
                "authors": cycle.researchers,
                "year": datetime.now().year,
                "journal": "中医古籍全自动研究系统",
                "source": "pipeline",
                "note": outcome.get("phase", ""),
            }
            for outcome in cycle.outcomes
            if isinstance(outcome, dict) and isinstance(outcome.get("result"), dict)
        ]
        return [item for item in publications if item.get("title")]
    
    def _execute_reflect_phase(self, cycle: ResearchCycle, 
                              context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行反思阶段
        
        Args:
            cycle (ResearchCycle): 研究循环
            context (Dict[str, Any]): 阶段上下文
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        # 模拟反思阶段的执行
        reflections = [
            {
                "topic": "方法论改进",
                "reflection": "实验设计可以更加多样化，增加跨学科方法的应用",
                "action": "在下一轮研究中引入更多样化的实验方法"
            },
            {
                "topic": "数据质量",
                "reflection": "古籍文本的标准化处理仍有改进空间",
                "action": "开发更完善的文本预处理工具"
            },
            {
                "topic": "技术应用",
                "reflection": "AI模型在中医领域应用效果显著，但需要持续优化",
                "action": "加强模型训练和调优"
            }
        ]
        
        improvement_plan = [
            "优化数据预处理流程",
            "增强模型泛化能力",
            "完善质量控制体系",
            "建立长期跟踪机制"
        ]
        
        return {
            "phase": "reflect",
            "reflections": reflections,
            "improvement_plan": improvement_plan,
            "metadata": {
                "reflection_count": len(reflections),
                "plan_items": len(improvement_plan)
            }
        }
    
    def complete_research_cycle(self, cycle_id: str) -> bool:
        """
        完成研究循环
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            bool: 完成是否成功
        """
        phase_entry = self._start_phase(self._metadata, "complete_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.research_cycles:
                self.logger.warning(f"研究循环 {cycle_id} 不存在")
                self._fail_phase(
                    self._metadata,
                    self._failed_operations,
                    "complete_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False
            
            research_cycle = self.research_cycles[cycle_id]
            
            # 更新状态
            research_cycle.status = ResearchCycleStatus.COMPLETED
            research_cycle.completed_at = datetime.now().isoformat()
            research_cycle.duration = (
                datetime.fromisoformat(research_cycle.completed_at) - 
                datetime.fromisoformat(research_cycle.started_at)
            ).total_seconds()
            
            # 从活跃循环中移除
            if cycle_id in self.active_cycles:
                del self.active_cycles[cycle_id]
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "cycle_completed",
                "cycle_id": cycle_id,
                "duration": research_cycle.duration
            })
            self._complete_phase(self._metadata, "complete_research_cycle", phase_entry, start_time)
            self._persist_result(research_cycle)

            self.logger.info(f"研究循环完成: {research_cycle.cycle_name}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "complete_research_cycle", phase_entry, start_time, str(e))
            self.logger.error(f"研究循环完成失败: {e}")
            return False
    
    def suspend_research_cycle(self, cycle_id: str) -> bool:
        """
        暂停研究循环
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            bool: 暂停是否成功
        """
        phase_entry = self._start_phase(self._metadata, "suspend_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.research_cycles:
                self.logger.warning(f"研究循环 {cycle_id} 不存在")
                self._fail_phase(
                    self._metadata,
                    self._failed_operations,
                    "suspend_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False
            
            research_cycle = self.research_cycles[cycle_id]
            
            # 更新状态
            research_cycle.status = ResearchCycleStatus.SUSPENDED
            
            # 从活跃循环中移除
            if cycle_id in self.active_cycles:
                del self.active_cycles[cycle_id]
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "cycle_suspended",
                "cycle_id": cycle_id
            })
            self._complete_phase(self._metadata, "suspend_research_cycle", phase_entry, start_time)
            
            self.logger.info(f"研究循环暂停: {research_cycle.cycle_name}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "suspend_research_cycle", phase_entry, start_time, str(e))
            self.logger.error(f"研究循环暂停失败: {e}")
            return False
    
    def resume_research_cycle(self, cycle_id: str) -> bool:
        """
        恢复研究循环
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            bool: 恢复是否成功
        """
        phase_entry = self._start_phase(self._metadata, "resume_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.research_cycles:
                self.logger.warning(f"研究循环 {cycle_id} 不存在")
                self._fail_phase(
                    self._metadata,
                    self._failed_operations,
                    "resume_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False
            
            research_cycle = self.research_cycles[cycle_id]
            
            # 更新状态
            research_cycle.status = ResearchCycleStatus.ACTIVE
            
            # 添加到活跃循环
            self.active_cycles[cycle_id] = research_cycle
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self._build_cycle_analysis_summary(research_cycle)
            
            # 记录历史
            self.execution_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "cycle_resumed",
                "cycle_id": cycle_id
            })
            self._complete_phase(self._metadata, "resume_research_cycle", phase_entry, start_time)
            
            self.logger.info(f"研究循环恢复: {research_cycle.cycle_name}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "resume_research_cycle", phase_entry, start_time, str(e))
            self.logger.error(f"研究循环恢复失败: {e}")
            return False
    
    def get_cycle_status(self, cycle_id: str) -> Dict[str, Any]:
        """
        获取研究循环状态
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            Dict[str, Any]: 状态信息
        """
        if cycle_id not in self.research_cycles:
            return {"error": "循环不存在"}
        
        cycle = self.research_cycles[cycle_id]
        
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "status": cycle.status.value,
            "current_phase": cycle.current_phase.value,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "duration": cycle.duration,
            "research_objective": cycle.research_objective,
            "research_scope": cycle.research_scope,
            "phase_executions": self._serialize_phase_executions(cycle),
            "metadata": self._serialize_value(cycle.metadata),
        }
    
    def get_all_cycles(self) -> List[Dict[str, Any]]:
        """
        获取所有研究循环
        
        Returns:
            List[Dict[str, Any]]: 循环列表
        """
        return [
            {
                "cycle_id": cycle.cycle_id,
                "cycle_name": cycle.cycle_name,
                "status": cycle.status.value,
                "current_phase": cycle.current_phase.value,
                "started_at": cycle.started_at,
                "research_objective": cycle.research_objective,
                "analysis_summary": self._serialize_value(cycle.metadata.get("analysis_summary", {})),
            } for cycle in self.research_cycles.values()
        ]
    
    def get_cycle_history(self, cycle_id: str) -> List[Dict[str, Any]]:
        """
        获取研究循环历史
        
        Args:
            cycle_id (str): 循环ID
            
        Returns:
            List[Dict[str, Any]]: 历史记录
        """
        return [entry for entry in self.execution_history 
                if entry.get("cycle_id") == cycle_id]
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """
        获取流程管理摘要
        
        Returns:
            Dict[str, Any]: 摘要信息
        """
        total_cycles = len(self.research_cycles)
        active_cycles = len(self.active_cycles)
        completed_cycles = sum(1 for c in self.research_cycles.values() 
                             if c.status == ResearchCycleStatus.COMPLETED)
        failed_cycles = sum(1 for c in self.research_cycles.values() if c.status == ResearchCycleStatus.FAILED)
        
        # 计算质量指标
        if total_cycles > 0:
            completion_rate = completed_cycles / total_cycles
        else:
            completion_rate = 0.0
        
        return {
            "pipeline_summary": {
                "total_cycles": total_cycles,
                "active_cycles": active_cycles,
                "completed_cycles": completed_cycles,
                "failed_cycles": failed_cycles,
                "completion_rate": round(completion_rate, 4),
                "quality_metrics": self._serialize_value(self.quality_metrics),
                "resource_usage": self._serialize_value(self.resource_usage),
                "recent_activities": self._serialize_value(self.execution_history[-10:] if self.execution_history else []),
                "analysis_summary": self._build_pipeline_analysis_summary(),
                "report_metadata": self._build_report_metadata(),
                "failed_operations": self._serialize_value(self._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
        }
    
    def export_pipeline_data(self, output_path: str) -> bool:
        """
        导出流程数据
        
        Args:
            output_path (str): 输出路径
            
        Returns:
            bool: 导出是否成功
        """
        phase_entry = self._start_phase(self._metadata, "export_pipeline_data", {"output_path": output_path})
        start_time = time.perf_counter()
        try:
            pipeline_data = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                    "exported_file": os.path.basename(output_path),
                },
                "pipeline_info": {
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "pipeline_summary": self.get_pipeline_summary()
                },
                "research_cycles": [self._serialize_cycle(cycle) for cycle in self.research_cycles.values()],
                "failed_cycles": [self._serialize_cycle(cycle) for cycle in self.failed_cycles],
                "execution_history": self._serialize_value(self.execution_history),
                "quality_metrics": self._serialize_value(self.quality_metrics),
                "resource_usage": self._serialize_value(self.resource_usage),
                "failed_operations": self._serialize_value(self._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(pipeline_data, f, ensure_ascii=False, indent=2)
            self._complete_phase(self._metadata, "export_pipeline_data", phase_entry, start_time)
            
            self.logger.info(f"流程数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self._fail_phase(self._metadata, self._failed_operations, "export_pipeline_data", phase_entry, start_time, str(e))
            self.logger.error(f"流程数据导出失败: {e}")
            return False
    
    def _persist_result(self, cycle: ResearchCycle) -> bool:
        """
        将研究循环结果持久化到 SQLite 数据库。

        Args:
            cycle: 已完成（或失败）的研究循环对象

        Returns:
            bool: True 表示写入成功，False 表示写入失败（不阻断主链）
        """
        db_path = self.config.get(
            "result_store_path",
            os.path.join("output", "research_results.db"),
        )
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        ddl = """
        CREATE TABLE IF NOT EXISTS research_results (
            cycle_id          TEXT PRIMARY KEY,
            cycle_name        TEXT NOT NULL,
            status            TEXT NOT NULL,
            started_at        TEXT,
            completed_at      TEXT,
            duration          REAL,
            research_objective TEXT,
            outcomes_json     TEXT,
            metadata_json     TEXT,
            persisted_at      TEXT NOT NULL
        )
        """
        row = (
            cycle.cycle_id,
            cycle.cycle_name,
            cycle.status.value,
            cycle.started_at,
            cycle.completed_at,
            cycle.duration,
            cycle.research_objective,
            json.dumps(self._serialize_value(cycle.outcomes), ensure_ascii=False),
            json.dumps(self._serialize_value(cycle.metadata), ensure_ascii=False),
            datetime.now().isoformat(),
        )
        upsert = """
        INSERT OR REPLACE INTO research_results
            (cycle_id, cycle_name, status, started_at, completed_at, duration,
             research_objective, outcomes_json, metadata_json, persisted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(ddl)
                conn.execute(upsert, row)
            finally:
                conn.close()
            self.logger.info(f"研究结果已持久化: {cycle.cycle_id} → {db_path}")
            return True
        except Exception as exc:  # pragma: no cover
            self.logger.warning(f"研究结果持久化失败，已跳过: {exc}")
            return False

    def cleanup(self) -> bool:
        """
        清理资源
        
        Returns:
            bool: 清理是否成功
        """
        try:
            self.hypothesis_engine.cleanup()
            # 清空数据结构
            self.research_cycles.clear()
            self.active_cycles.clear()
            self.failed_cycles.clear()
            self.execution_history.clear()
            self._failed_operations.clear()
            self._metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "cleaned",
                "last_completed_phase": None,
            }
            self.quality_metrics = {
                "cycle_completion_rate": 0.0,
                "phase_efficiency": 0.0,
                "researcher_productivity": 0.0,
                "quality_assurance": 0.0
            }
            self.resource_usage = {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "storage_usage": 0.0,
                "network_usage": 0.0
            }
            
            self.logger.info("研究流程管理器资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")
            return False

# 导出主要类和函数
__all__ = [
    'ResearchPipeline',
    'ResearchCycle',
    'ResearchPhase',
    'ResearchCycleStatus',
    'LLMEngine'
]
