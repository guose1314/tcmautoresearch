# research/theoretical_framework.py
"""
中医古籍全自动研究系统 - 专业学术理论框架模块
基于中医理论体系的智能研究框架
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np

# 配置日志
logger = logging.getLogger(__name__)

class ResearchDomain(Enum):
    """
    研究领域枚举
    """
    FORMULA_RESEARCH = "formula_research"          # 方剂研究
    HERB_RESEARCH = "herb_research"               # 药物研究  
    SYNDROME_RESEARCH = "syndrome_research"       # 症候研究
    PATHOGENESIS_RESEARCH = "pathogenesis_research" # 病机研究
    CLINICAL_RESEARCH = "clinical_research"       # 临床研究
    HISTORICAL_RESEARCH = "historical_research"   # 历史研究
    INTEGRATIVE_RESEARCH = "integrative_research" # 综合研究

class HypothesisStatus(Enum):
    """
    假设状态枚举
    """
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 活跃
    TESTED = "tested"         # 已测试
    VALIDATED = "validated"   # 已验证
    REJECTED = "rejected"     # 已拒绝
    SUSPENDED = "suspended"   # 暂停

class InsightCategory(Enum):
    """
    研究洞察分类枚举
    """
    THEORETICAL = "theoretical"      # 理论洞察
    APPLICATION = "application"      # 应用洞察
    VALIDATION = "validation"        # 验证洞察
    SYNTHESIS = "synthesis"          # 综合洞察
    PREDICTION = "prediction"        # 预测洞察
    OPTIMIZATION = "optimization"    # 优化洞察

@dataclass
class ResearchHypothesis:
    """
    研究假设数据结构
    符合中医理论研究规范的假设定义
    """
    # 基础信息
    hypothesis_id: str
    title: str
    description: str
    research_domain: ResearchDomain
    hypothesis_type: str = "scientific"
    
    # 状态和时间信息
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    validated_at: Optional[str] = None
    rejected_at: Optional[str] = None
    
    # 研究质量指标
    confidence: float = 0.0
    complexity: int = 0  # 0-100，复杂度评分
    testability: float = 0.0  # 可测试性评分
    
    # 研究目标和预期
    research_objective: str = ""
    expected_outcome: str = ""
    validation_method: str = ""
    
    # 相关性指标
    relevance_to_tcm: float = 0.0  # 与中医理论的相关性
    novelty_score: float = 0.0     # 创新性评分
    practical_value: float = 0.0   # 实用性评分
    
    # 专家评审信息
    expert_reviews: List[Dict[str, Any]] = field(default_factory=list)
    review_comments: List[str] = field(default_factory=list)
    
    # 知识关联
    related_hypotheses: List[str] = field(default_factory=list)
    supporting_evidence: List[Dict[str, Any]] = field(default_factory=list)
    contradicting_evidence: List[Dict[str, Any]] = field(default_factory=list)
    
    # 语义标签
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "description": self.description,
            "research_domain": self.research_domain.value,
            "hypothesis_type": self.hypothesis_type,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "validated_at": self.validated_at,
            "rejected_at": self.rejected_at,
            "confidence": self.confidence,
            "complexity": self.complexity,
            "testability": self.testability,
            "research_objective": self.research_objective,
            "expected_outcome": self.expected_outcome,
            "validation_method": self.validation_method,
            "relevance_to_tcm": self.relevance_to_tcm,
            "novelty_score": self.novelty_score,
            "practical_value": self.practical_value,
            "expert_reviews": self.expert_reviews,
            "review_comments": self.review_comments,
            "related_hypotheses": self.related_hypotheses,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "tags": self.tags,
            "keywords": self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchHypothesis':
        """从字典创建对象"""
        return cls(
            hypothesis_id=data["hypothesis_id"],
            title=data["title"],
            description=data["description"],
            research_domain=ResearchDomain(data["research_domain"]),
            hypothesis_type=data.get("hypothesis_type", "scientific"),
            status=HypothesisStatus(data.get("status", "draft")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            validated_at=data.get("validated_at", None),
            rejected_at=data.get("rejected_at", None),
            confidence=data.get("confidence", 0.0),
            complexity=data.get("complexity", 0),
            testability=data.get("testability", 0.0),
            research_objective=data.get("research_objective", ""),
            expected_outcome=data.get("expected_outcome", ""),
            validation_method=data.get("validation_method", ""),
            relevance_to_tcm=data.get("relevance_to_tcm", 0.0),
            novelty_score=data.get("novelty_score", 0.0),
            practical_value=data.get("practical_value", 0.0),
            expert_reviews=data.get("expert_reviews", []),
            review_comments=data.get("review_comments", []),
            related_hypotheses=data.get("related_hypotheses", []),
            supporting_evidence=data.get("supporting_evidence", []),
            contradicting_evidence=data.get("contradicting_evidence", []),
            tags=data.get("tags", []),
            keywords=data.get("keywords", [])
        )

@dataclass
class ResearchExperiment:
    """
    研究实验数据结构
    符合中医研究规范的实验设计
    """
    # 基础信息
    experiment_id: str
    hypothesis_id: str
    title: str
    description: str
    
    # 实验设计
    experimental_design: str  # 实验设计类型
    methodology: str  # 研究方法
    sample_size: int = 0
    duration: int = 0  # 实验持续时间（天）
    
    # 实验阶段
    phase: str = "planning"  # planning, executing, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 实验条件
    conditions: Dict[str, Any] = field(default_factory=dict)
    controls: List[str] = field(default_factory=list)
    
    # 数据收集
    data_collection_methods: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    
    # 预期结果
    expected_results: str = ""
    validation_criteria: str = ""
    
    # 实验质量
    quality_score: float = 0.0
    reproducibility_score: float = 0.0
    scientific_validity: float = 0.0
    
    # 实验结果
    actual_results: Dict[str, Any] = field(default_factory=dict)
    analysis_results: Dict[str, Any] = field(default_factory=dict)
    conclusions: List[str] = field(default_factory=list)
    
    # 专家评价
    expert_evaluations: List[Dict[str, Any]] = field(default_factory=list)
    
    # 标签和分类
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "description": self.description,
            "experimental_design": self.experimental_design,
            "methodology": self.methodology,
            "sample_size": self.sample_size,
            "duration": self.duration,
            "phase": self.phase,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "conditions": self.conditions,
            "controls": self.controls,
            "data_collection_methods": self.data_collection_methods,
            "data_sources": self.data_sources,
            "expected_results": self.expected_results,
            "validation_criteria": self.validation_criteria,
            "quality_score": self.quality_score,
            "reproducibility_score": self.reproducibility_score,
            "scientific_validity": self.scientific_validity,
            "actual_results": self.actual_results,
            "analysis_results": self.analysis_results,
            "conclusions": self.conclusions,
            "expert_evaluations": self.expert_evaluations,
            "tags": self.tags,
            "categories": self.categories
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchExperiment':
        """从字典创建对象"""
        return cls(
            experiment_id=data["experiment_id"],
            hypothesis_id=data["hypothesis_id"],
            title=data["title"],
            description=data["description"],
            experimental_design=data["experimental_design"],
            methodology=data["methodology"],
            sample_size=data.get("sample_size", 0),
            duration=data.get("duration", 0),
            phase=data.get("phase", "planning"),
            started_at=data.get("started_at", None),
            completed_at=data.get("completed_at", None),
            conditions=data.get("conditions", {}),
            controls=data.get("controls", []),
            data_collection_methods=data.get("data_collection_methods", []),
            data_sources=data.get("data_sources", []),
            expected_results=data.get("expected_results", ""),
            validation_criteria=data.get("validation_criteria", ""),
            quality_score=data.get("quality_score", 0.0),
            reproducibility_score=data.get("reproducibility_score", 0.0),
            scientific_validity=data.get("scientific_validity", 0.0),
            actual_results=data.get("actual_results", {}),
            analysis_results=data.get("analysis_results", {}),
            conclusions=data.get("conclusions", []),
            expert_evaluations=data.get("expert_evaluations", []),
            tags=data.get("tags", []),
            categories=data.get("categories", [])
        )

@dataclass
class ResearchInsight:
    """
    研究洞察数据结构
    基于中医理论和实证研究的洞察发现
    """
    # 基础信息
    insight_id: str
    hypothesis_id: str
    title: str
    description: str
    category: InsightCategory
    
    # 洞察内容
    evidence: List[str] = field(default_factory=list)
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    conflicting_data: List[str] = field(default_factory=list)
    
    # 质量评估
    confidence: float = 0.0
    validity_score: float = 0.0
    novelty_score: float = 0.0
    practical_application: float = 0.0
    
    # 时间信息
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 知识关联
    related_insights: List[str] = field(default_factory=list)
    related_hypotheses: List[str] = field(default_factory=list)
    related_experiments: List[str] = field(default_factory=list)
    
    # 专家评价
    expert_opinions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 应用场景
    application_scenarios: List[str] = field(default_factory=list)
    implementation_steps: List[str] = field(default_factory=list)
    
    # 标签和分类
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "insight_id": self.insight_id,
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "evidence": self.evidence,
            "supporting_data": self.supporting_data,
            "conflicting_data": self.conflicting_data,
            "confidence": self.confidence,
            "validity_score": self.validity_score,
            "novelty_score": self.novelty_score,
            "practical_application": self.practical_application,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "related_insights": self.related_insights,
            "related_hypotheses": self.related_hypotheses,
            "related_experiments": self.related_experiments,
            "expert_opinions": self.expert_opinions,
            "application_scenarios": self.application_scenarios,
            "implementation_steps": self.implementation_steps,
            "tags": self.tags,
            "keywords": self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchInsight':
        """从字典创建对象"""
        return cls(
            insight_id=data["insight_id"],
            hypothesis_id=data["hypothesis_id"],
            title=data["title"],
            description=data["description"],
            category=InsightCategory(data["category"]),
            evidence=data.get("evidence", []),
            supporting_data=data.get("supporting_data", {}),
            conflicting_data=data.get("conflicting_data", []),
            confidence=data.get("confidence", 0.0),
            validity_score=data.get("validity_score", 0.0),
            novelty_score=data.get("novelty_score", 0.0),
            practical_application=data.get("practical_application", 0.0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            related_insights=data.get("related_insights", []),
            related_hypotheses=data.get("related_hypotheses", []),
            related_experiments=data.get("related_experiments", []),
            expert_opinions=data.get("expert_opinions", []),
            application_scenarios=data.get("application_scenarios", []),
            implementation_steps=data.get("implementation_steps", []),
            tags=data.get("tags", []),
            keywords=data.get("keywords", [])
        )

class TheoreticalFramework:
    """
    中医古籍全自动研究系统的理论框架
    
    本模块基于中医理论体系，结合现代AI技术，
    构建了一套完整的智能研究理论框架，支持：
    1. 假设生成与验证
    2. 实验设计与执行
    3. 研究洞察发现
    4. 知识体系构建
    5. 学术成果产出
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化理论框架
        
        Args:
            config (Dict[str, Any]): 配置参数
        """
        self.config = config or {}
        self.hypotheses = {}
        self.experiments = {}
        self.insights = {}
        self.research_history = []
        self.failed_operations: List[Dict[str, Any]] = []
        self.framework_metadata = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
        }
        self.knowledge_graph = nx.MultiDiGraph()
        self.logger = logging.getLogger(__name__)
        
        # 初始化研究指标
        self.research_metrics = {
            "hypotheses_count": 0,
            "experiments_count": 0,
            "insights_count": 0,
            "validation_rate": 0.0,
            "novation_score": 0.0,
            "practical_impact": 0.0
        }
        
        # 初始化专业术语词典
        self.terminology_dict = self._load_terminology_dict()
        
        self.logger.info("中医研究理论框架初始化完成")

    def _start_operation(self, phase_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "context": context or {},
        }
        self.framework_metadata["phase_history"].append(phase_entry)
        return phase_entry

    def _complete_operation(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float) -> None:
        duration = time.time() - start_time
        phase_entry["status"] = "completed"
        phase_entry["completed_at"] = datetime.now().isoformat()
        phase_entry["duration"] = duration
        self.framework_metadata["phase_timings"][phase_name] = duration
        self.framework_metadata["completed_phases"].append(phase_name)
        self.framework_metadata["last_completed_phase"] = phase_name
        self.framework_metadata["final_status"] = "completed"

    def _fail_operation(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float, error: str) -> None:
        duration = time.time() - start_time
        phase_entry["status"] = "failed"
        phase_entry["completed_at"] = datetime.now().isoformat()
        phase_entry["duration"] = duration
        phase_entry["error"] = error
        self.framework_metadata["phase_timings"][phase_name] = duration
        self.framework_metadata["failed_phase"] = phase_name
        self.framework_metadata["final_status"] = "failed"
        self.failed_operations.append(
            {
                "phase": phase_name,
                "error": error,
                "timestamp": datetime.now().isoformat(),
                "duration": duration,
            }
        )

    def _build_analysis_summary(self) -> Dict[str, Any]:
        validated_hypotheses = sum(1 for h in self.hypotheses.values() if h.status == HypothesisStatus.VALIDATED)
        active_hypotheses = sum(1 for h in self.hypotheses.values() if h.status == HypothesisStatus.ACTIVE)
        minimum_validation_rate = float(self.config.get("minimum_validation_rate", 0.5))
        validation_rate = float(self.research_metrics.get("validation_rate", 0.0))
        stable = validation_rate >= minimum_validation_rate or validated_hypotheses > 0
        if not self.hypotheses and not self.experiments and not self.insights:
            status = "idle"
        elif self.failed_operations:
            status = "needs_followup"
        else:
            status = "stable" if stable else "in_progress"

        return {
            "status": status,
            "hypotheses_count": len(self.hypotheses),
            "experiments_count": len(self.experiments),
            "insights_count": len(self.insights),
            "active_hypotheses": active_hypotheses,
            "validated_hypotheses": validated_hypotheses,
            "validation_rate": validation_rate,
            "knowledge_graph_ready": self.knowledge_graph.number_of_nodes() > 0,
            "failed_operation_count": len(self.failed_operations),
            "last_completed_phase": self.framework_metadata.get("last_completed_phase", ""),
            "failed_phase": self.framework_metadata.get("failed_phase", ""),
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self.config.get("export_contract_version", "d20.v1"),
            "generated_at": datetime.now().isoformat(),
            "result_schema": "theoretical_framework_report",
            "history_entries": len(self.research_history),
        }
    
    def _load_terminology_dict(self) -> Dict[str, Any]:
        """
        加载专业术语词典
        """
        return {
            # 方剂相关
            "方剂": ["方剂", "汤剂", "散剂", "丸剂", "膏剂", "丹剂", "片剂", "口服液"],
            # 药物相关
            "药物": ["中药", "药材", "草药", "植物药", "动物药", "矿物药", "制剂", "饮片"],
            # 症候相关
            "症候": ["证候", "症状", "体征", "症型", "病型", "证型", "病证", "辨证"],
            # 理论相关
            "理论": ["理论", "学说", "观点", "认识", "规律", "法则", "原则", "方法"],
            # 临床相关
            "临床": ["临床", "治疗", "诊断", "预防", "康复", "护理", "养生", "保健"],
            # 历史相关
            "历史": ["历史", "古代", "现代", "演变", "发展", "传承", "创新", "变革"]
        }
    
    def generate_hypothesis(self, context: Dict[str, Any]) -> ResearchHypothesis:
        """
        生成研究假设
        
        Args:
            context (Dict[str, Any]): 研究上下文
            
        Returns:
            ResearchHypothesis: 生成的研究假设
        """
        start_time = time.time()
        phase_entry = self._start_operation("generate_hypothesis", {"has_text": bool(context.get("text_content")), "domain": str(context.get("domain", ResearchDomain.FORMULA_RESEARCH))})
        
        try:
            # 从上下文中提取信息
            text_content = context.get("text_content", "")
            research_objective = context.get("research_objective", "")
            domain = context.get("domain", ResearchDomain.FORMULA_RESEARCH)
            
            # 生成假设ID
            hypothesis_id = f"hypothesis_{int(time.time())}_{hashlib.md5(text_content.encode()).hexdigest()[:8]}"
            
            # 基于内容和领域生成假设标题和描述
            title, description = self._generate_hypothesis_content(text_content, domain)
            
            # 创建假设
            hypothesis = ResearchHypothesis(
                hypothesis_id=hypothesis_id,
                title=title,
                description=description,
                research_domain=domain,
                research_objective=research_objective,
                hypothesis_type="scientific",
                status=HypothesisStatus.ACTIVE,
                confidence=0.75,
                complexity=50,
                testability=0.8,
                relevance_to_tcm=0.9,
                novelty_score=0.85,
                practical_value=0.75,
                tags=["generated", "automated", "tcmautoresearch"],
                keywords=self._extract_keywords(text_content)
            )
            
            # 存储假设
            self.hypotheses[hypothesis_id] = hypothesis
            
            # 更新指标
            self._update_research_metrics()
            
            # 记录历史
            self.research_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "hypothesis_generated",
                "hypothesis_id": hypothesis_id,
                "duration": time.time() - start_time
            })
            self._complete_operation("generate_hypothesis", phase_entry, start_time)
            
            self.logger.info(f"假设生成完成: {hypothesis.title}")
            return hypothesis
            
        except Exception as e:
            self.logger.error(f"假设生成失败: {e}")
            self._fail_operation("generate_hypothesis", phase_entry, start_time, str(e))
            raise
    
    def _generate_hypothesis_content(self, text_content: str, domain: ResearchDomain) -> tuple:
        """
        生成假设内容
        
        Args:
            text_content (str): 文本内容
            domain (ResearchDomain): 研究领域
            
        Returns:
            tuple: (标题, 描述)
        """
        # 基于领域和文本内容生成假设
        domain_name = domain.name.replace("_", " ").title()
        
        if domain == ResearchDomain.FORMULA_RESEARCH:
            title = f"{domain_name}研究假设"
            description = f"基于文本内容分析，提出关于{domain_name}的科学假设，旨在探索其理论基础和应用价值。"
        elif domain == ResearchDomain.HERB_RESEARCH:
            title = f"{domain_name}研究假设"
            description = f"基于文本内容分析，提出关于{domain_name}的科学假设，旨在揭示其药理作用和临床应用。"
        elif domain == ResearchDomain.SYNDROME_RESEARCH:
            title = f"{domain_name}研究假设"
            description = f"基于文本内容分析，提出关于{domain_name}的科学假设，旨在阐明其发病机制和治疗规律。"
        else:
            title = f"{domain_name}研究假设"
            description = f"基于文本内容分析，提出关于{domain_name}的科学假设，旨在深化对该领域的认知。"
        
        return title, description
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        Args:
            text (str): 文本内容
            
        Returns:
            List[str]: 关键词列表
        """
        keywords = []
        
        # 基于专业术语词典提取关键词
        for terms in self.terminology_dict.values():
            for term in terms:
                if term in text:
                    keywords.append(term)
        
        # 去重并返回
        return list(set(keywords))
    
    def design_experiment(self, hypothesis: ResearchHypothesis, 
                         context: Dict[str, Any]) -> ResearchExperiment:
        """
        设计研究实验
        
        Args:
            hypothesis (ResearchHypothesis): 研究假设
            context (Dict[str, Any]): 实验上下文
            
        Returns:
            ResearchExperiment: 实验设计
        """
        start_time = time.time()
        phase_entry = self._start_operation("design_experiment", {"hypothesis_id": hypothesis.hypothesis_id, "context_keys": sorted((context or {}).keys())})
        
        try:
            # 生成实验ID
            experiment_id = f"experiment_{int(time.time())}_{hashlib.md5(hypothesis.hypothesis_id.encode()).hexdigest()[:8]}"
            
            # 基于假设生成实验设计
            experiment_title, experiment_description = self._generate_experiment_content(hypothesis)
            
            # 创建实验
            experiment = ResearchExperiment(
                experiment_id=experiment_id,
                hypothesis_id=hypothesis.hypothesis_id,
                title=experiment_title,
                description=experiment_description,
                experimental_design="controlled_study",
                methodology="data_analysis",
                sample_size=100,
                duration=30,
                phase="planning",
                expected_results="验证假设的有效性",
                validation_criteria="统计显著性(p<0.05)",
                quality_score=0.85,
                reproducibility_score=0.9,
                scientific_validity=0.95,
                tags=["designed", "automated", "tcmautoresearch"],
                categories=["formal", "scientific"]
            )
            
            # 存储实验
            self.experiments[experiment_id] = experiment
            
            # 更新指标
            self._update_research_metrics()
            
            # 记录历史
            self.research_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "experiment_designed",
                "experiment_id": experiment_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "duration": time.time() - start_time
            })
            self._complete_operation("design_experiment", phase_entry, start_time)
            
            self.logger.info(f"实验设计完成: {experiment.title}")
            return experiment
            
        except Exception as e:
            self.logger.error(f"实验设计失败: {e}")
            self._fail_operation("design_experiment", phase_entry, start_time, str(e))
            raise
    
    def _generate_experiment_content(self, hypothesis: ResearchHypothesis) -> tuple:
        """
        生成实验内容
        
        Args:
            hypothesis (ResearchHypothesis): 研究假设
            
        Returns:
            tuple: (标题, 描述)
        """
        title = f"验证{hypothesis.title}的实验设计"
        description = f"为验证{hypothesis.title}而设计的实验，采用{hypothesis.research_domain.value}研究方法，通过{hypothesis.research_objective}来检验假设的有效性。"
        
        return title, description
    
    def generate_insight(self, hypothesis: ResearchHypothesis, 
                        experiment: ResearchExperiment,
                        results: Dict[str, Any]) -> ResearchInsight:
        """
        生成研究洞察
        
        Args:
            hypothesis (ResearchHypothesis): 研究假设
            experiment (ResearchExperiment): 实验设计
            results (Dict[str, Any]): 实验结果
            
        Returns:
            ResearchInsight: 研究洞察
        """
        start_time = time.time()
        phase_entry = self._start_operation("generate_insight", {"hypothesis_id": hypothesis.hypothesis_id, "experiment_id": experiment.experiment_id})
        
        try:
            # 生成洞察ID
            insight_id = f"insight_{int(time.time())}_{hashlib.md5(hypothesis.hypothesis_id.encode()).hexdigest()[:8]}"
            
            # 基于结果生成洞察
            insight_title, insight_description = self._generate_insight_content(hypothesis, experiment, results)
            
            # 创建洞察
            insight = ResearchInsight(
                insight_id=insight_id,
                hypothesis_id=hypothesis.hypothesis_id,
                title=insight_title,
                description=insight_description,
                category=InsightCategory.SYNTHESIS,
                evidence=["实验结果验证", "理论分析支持"],
                supporting_data=results,
                confidence=0.9,
                validity_score=0.92,
                novelty_score=0.8,
                practical_application=0.85,
                tags=["insight", "automated", "tcmautoresearch"],
                keywords=hypothesis.keywords
            )
            
            # 存储洞察
            self.insights[insight_id] = insight
            
            # 更新指标
            self._update_research_metrics()
            
            # 记录历史
            self.research_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "insight_generated",
                "insight_id": insight_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "duration": time.time() - start_time
            })
            self._complete_operation("generate_insight", phase_entry, start_time)
            
            self.logger.info(f"研究洞察生成完成: {insight.title}")
            return insight
            
        except Exception as e:
            self.logger.error(f"研究洞察生成失败: {e}")
            self._fail_operation("generate_insight", phase_entry, start_time, str(e))
            raise
    
    def _generate_insight_content(self, hypothesis: ResearchHypothesis, 
                                experiment: ResearchExperiment,
                                results: Dict[str, Any]) -> tuple:
        """
        生成洞察内容
        
        Args:
            hypothesis (ResearchHypothesis): 研究假设
            experiment (ResearchExperiment): 实验设计
            results (Dict[str, Any]): 实验结果
            
        Returns:
            tuple: (标题, 描述)
        """
        title = f"关于{hypothesis.title}的重要洞察"
        description = f"基于{experiment.title}的实验结果，得出关于{hypothesis.title}的重要洞察，为{hypothesis.research_objective}提供了理论支持和实践指导。"
        
        return title, description
    
    def validate_hypothesis(self, hypothesis_id: str, 
                           validation_result: bool, 
                           feedback: str = "") -> bool:
        """
        验证研究假设
        
        Args:
            hypothesis_id (str): 假设ID
            validation_result (bool): 验证结果
            feedback (str): 专家反馈
            
        Returns:
            bool: 验证是否成功
        """
        start_time = time.time()
        try:
            phase_entry = self._start_operation("validate_hypothesis", {"hypothesis_id": hypothesis_id, "validation_result": validation_result})
            if hypothesis_id not in self.hypotheses:
                self.logger.warning(f"假设 {hypothesis_id} 不存在")
                self._fail_operation("validate_hypothesis", phase_entry, start_time, f"假设 {hypothesis_id} 不存在")
                return False
            
            hypothesis = self.hypotheses[hypothesis_id]
            
            # 更新假设状态
            if validation_result:
                hypothesis.status = HypothesisStatus.VALIDATED
                hypothesis.validated_at = datetime.now().isoformat()
                hypothesis.confidence = 0.95
                self.logger.info(f"假设 {hypothesis.title} 验证通过")
            else:
                hypothesis.status = HypothesisStatus.REJECTED
                hypothesis.rejected_at = datetime.now().isoformat()
                hypothesis.confidence = 0.2
                self.logger.info(f"假设 {hypothesis.title} 验证失败")
            
            # 添加专家反馈
            if feedback:
                hypothesis.review_comments.append(feedback)
            
            # 更新指标
            self._update_research_metrics()
            
            # 记录历史
            self.research_history.append({
                "timestamp": datetime.now().isoformat(),
                "action": "hypothesis_validated",
                "hypothesis_id": hypothesis_id,
                "result": validation_result,
                "feedback": feedback
            })
            self._complete_operation("validate_hypothesis", phase_entry, start_time)
            
            return True
            
        except Exception as e:
            self.logger.error(f"假设验证失败: {e}")
            if 'phase_entry' in locals():
                self._fail_operation("validate_hypothesis", phase_entry, start_time, str(e))
            return False
    
    def _update_research_metrics(self):
        """
        更新研究指标
        """
        self.research_metrics["hypotheses_count"] = len(self.hypotheses)
        self.research_metrics["experiments_count"] = len(self.experiments)
        self.research_metrics["insights_count"] = len(self.insights)
        
        # 计算验证率
        if self.research_metrics["hypotheses_count"] > 0:
            validated_count = sum(1 for h in self.hypotheses.values() 
                                if h.status == HypothesisStatus.VALIDATED)
            self.research_metrics["validation_rate"] = validated_count / self.research_metrics["hypotheses_count"]
        
        # 计算创新性评分
        if self.insights:
            novelty_scores = [i.novelty_score for i in self.insights.values()]
            self.research_metrics["novation_score"] = np.mean(novelty_scores)
        
        # 计算实用性评分
        if self.insights:
            practical_scores = [i.practical_application for i in self.insights.values()]
            self.research_metrics["practical_impact"] = np.mean(practical_scores)
    
    def get_research_summary(self) -> Dict[str, Any]:
        """
        获取研究摘要
        
        Returns:
            Dict[str, Any]: 研究摘要信息
        """
        return {
            "research_metrics": self.research_metrics,
            "hypotheses_count": len(self.hypotheses),
            "experiments_count": len(self.experiments),
            "insights_count": len(self.insights),
            "active_hypotheses": len([h for h in self.hypotheses.values() 
                                    if h.status == HypothesisStatus.ACTIVE]),
            "validated_hypotheses": len([h for h in self.hypotheses.values() 
                                       if h.status == HypothesisStatus.VALIDATED]),
            "recent_activity": self.research_history[-10:] if self.research_history else [],
            "failed_operations": self.failed_operations,
            "analysis_summary": self._build_analysis_summary(),
            "report_metadata": self._build_report_metadata(),
            "framework_metadata": self.framework_metadata,
        }
    
    def get_hypothesis_by_id(self, hypothesis_id: str) -> Optional[ResearchHypothesis]:
        """
        根据ID获取假设
        
        Args:
            hypothesis_id (str): 假设ID
            
        Returns:
            Optional[ResearchHypothesis]: 假设对象或None
        """
        return self.hypotheses.get(hypothesis_id)
    
    def get_all_hypotheses(self) -> List[Dict[str, Any]]:
        """
        获取所有假设
        
        Returns:
            List[Dict[str, Any]]: 假设列表
        """
        return [h.to_dict() for h in self.hypotheses.values()]
    
    def get_experiments_by_hypothesis(self, hypothesis_id: str) -> List[Dict[str, Any]]:
        """
        根据假设ID获取实验
        
        Args:
            hypothesis_id (str): 假设ID
            
        Returns:
            List[Dict[str, Any]]: 实验列表
        """
        return [e.to_dict() for e in self.experiments.values() 
                if e.hypothesis_id == hypothesis_id]
    
    def get_insights_by_hypothesis(self, hypothesis_id: str) -> List[Dict[str, Any]]:
        """
        根据假设ID获取洞察
        
        Args:
            hypothesis_id (str): 假设ID
            
        Returns:
            List[Dict[str, Any]]: 洞察列表
        """
        return [i.to_dict() for i in self.insights.values() 
                if i.hypothesis_id == hypothesis_id]
    
    def build_knowledge_graph(self) -> Dict[str, Any]:
        """
        构建知识图谱
        
        Returns:
            Dict[str, Any]: 知识图谱数据
        """
        try:
            start_time = time.time()
            phase_entry = self._start_operation("build_knowledge_graph")
            # 清空现有图
            self.knowledge_graph.clear()
            
            # 添加节点
            for hypothesis_id, hypothesis in self.hypotheses.items():
                self.knowledge_graph.add_node(
                    hypothesis_id,
                    type="hypothesis",
                    data=hypothesis.to_dict()
                )
            
            for experiment_id, experiment in self.experiments.items():
                self.knowledge_graph.add_node(
                    experiment_id,
                    type="experiment",
                    data=experiment.to_dict()
                )
            
            for insight_id, insight in self.insights.items():
                self.knowledge_graph.add_node(
                    insight_id,
                    type="insight",
                    data=insight.to_dict()
                )
            
            # 添加边
            for experiment_id, experiment in self.experiments.items():
                # 假设-实验关系
                hypothesis_id = experiment.hypothesis_id
                if hypothesis_id in self.hypotheses:
                    self.knowledge_graph.add_edge(
                        hypothesis_id,
                        experiment_id,
                        relationship="hypothesis_experiment",
                        weight=0.9
                    )
            
            for insight_id, insight in self.insights.items():
                # 假设-洞察关系
                hypothesis_id = insight.hypothesis_id
                if hypothesis_id in self.hypotheses:
                    self.knowledge_graph.add_edge(
                        hypothesis_id,
                        insight_id,
                        relationship="hypothesis_insight",
                        weight=0.8
                    )
                
                # 实验-洞察关系
                for exp_id in insight.related_experiments:
                    if exp_id in self.experiments:
                        self.knowledge_graph.add_edge(
                            exp_id,
                            insight_id,
                            relationship="experiment_insight",
                            weight=0.7
                        )
            
            # 构造返回数据
            graph_data = {
                "nodes": [
                    {
                        "id": node,
                        "type": data.get("type", "unknown"),
                        "data": data
                    } for node, data in self.knowledge_graph.nodes(data=True)
                ],
                "edges": [
                    {
                        "source": edge[0],
                        "target": edge[1],
                        "attributes": edge[2]
                    } for edge in self.knowledge_graph.edges(data=True)
                ],
                "graph_properties": {
                    "nodes_count": self.knowledge_graph.number_of_nodes(),
                    "edges_count": self.knowledge_graph.number_of_edges(),
                    "density": nx.density(self.knowledge_graph),
                    "connected_components": nx.number_connected_components(self.knowledge_graph.to_undirected()),
                    "clustering_coefficient": (
                        nx.average_clustering(nx.Graph(self.knowledge_graph))
                        if self.knowledge_graph.number_of_nodes() > 0
                        else 0.0
                    )
                }
            }
            
            self._complete_operation("build_knowledge_graph", phase_entry, start_time)
            self.logger.info("知识图谱构建完成")
            return graph_data
            
        except Exception as e:
            self.logger.error(f"知识图谱构建失败: {e}")
            if 'phase_entry' in locals():
                self._fail_operation("build_knowledge_graph", phase_entry, start_time, str(e))
            raise
    
    def export_research_data(self, output_path: str) -> bool:
        """
        导出研究数据
        
        Args:
            output_path (str): 输出路径
            
        Returns:
            bool: 导出是否成功
        """
        try:
            research_data = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                },
                "framework_info": {
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "research_metrics": self.research_metrics
                },
                "hypotheses": [h.to_dict() for h in self.hypotheses.values()],
                "experiments": [e.to_dict() for e in self.experiments.values()],
                "insights": [i.to_dict() for i in self.insights.values()],
                "research_history": self.research_history,
                "failed_operations": self.failed_operations,
                "research_summary": self.get_research_summary(),
                "knowledge_graph": self.build_knowledge_graph()
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(research_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"研究数据已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"研究数据导出失败: {e}")
            return False

# 导出主要类和函数
__all__ = [
    'TheoreticalFramework',
    'ResearchHypothesis',
    'ResearchExperiment',
    'ResearchInsight',
    'ResearchDomain',
    'HypothesisStatus',
    'InsightCategory'
]
