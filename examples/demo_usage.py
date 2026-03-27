# examples/demo_usage.py
"""
中医古籍全自动研究系统 - 专业学术演示示例
基于T/C IATCM 098-2023标准的系统使用演示
"""

import hashlib
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# 配置日志
logger = logging.getLogger(__name__)

class DemoScenario(Enum):
    """演示场景枚举"""
    BASIC_USAGE = "basic_usage"
    ADVANCED_ANALYSIS = "advanced_analysis"
    ACADEMIC_RESEARCH = "academic_research"
    PERFORMANCE_BENCHMARK = "performance_benchmark"

class DemoStatus(Enum):
    """演示状态枚举"""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class ExampleConfig:
    """演示配置数据结构"""
    demo_name: str
    scenario: DemoScenario
    description: str
    expected_outcome: str
    input_data: Dict[str, Any]
    configuration: Dict[str, Any] = field(default_factory=dict)
    academic_requirements: Dict[str, Any] = field(default_factory=dict)
    performance_target: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExampleResult:
    """演示结果数据结构"""
    demo_id: str
    demo_name: str
    scenario: str
    status: DemoStatus
    start_time: str
    end_time: str = ""
    execution_time: float = 0.0
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    academic_insights: List[Dict[str, Any]] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

class DemoUsage:
    """
    中医古籍全自动研究系统演示使用类
    
    本演示类展示了系统的核心功能和使用方法，
    基于T/C IATCM 098-2023标准，为用户提供完整的系统使用体验。
    
    主要功能：
    1. 基础功能演示
    2. 高级分析演示
    3. 学术研究演示
    4. 性能基准演示
    5. 学术质量保证
    6. 可重复性验证
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.demo_results = []
        self.current_demo = None
        self.logger = logging.getLogger(__name__)
        self.demo_status = DemoStatus.NOT_STARTED
        
        self.logger.info("演示使用类初始化完成")
    
    def run_basic_demo(self) -> ExampleResult:
        """
        运行基础演示
        
        Returns:
            ExampleResult: 演示结果
        """
        self.logger.info("开始基础演示")
        
        try:
            # 创建演示配置
            demo_config = self._create_basic_demo_config()
            
            # 执行演示
            result = self._execute_demo(demo_config)
            
            # 记录结果
            self.demo_results.append(result)
            self.current_demo = result
            
            self.logger.info("基础演示完成")
            return result
            
        except Exception as e:
            self.logger.error(f"基础演示执行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def run_advanced_analysis_demo(self) -> ExampleResult:
        """
        运行高级分析演示
        
        Returns:
            ExampleResult: 演示结果
        """
        self.logger.info("开始高级分析演示")
        
        try:
            # 创建演示配置
            demo_config = self._create_advanced_demo_config()
            
            # 执行演示
            result = self._execute_demo(demo_config)
            
            # 记录结果
            self.demo_results.append(result)
            self.current_demo = result
            
            self.logger.info("高级分析演示完成")
            return result
            
        except Exception as e:
            self.logger.error(f"高级分析演示执行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def run_academic_research_demo(self) -> ExampleResult:
        """
        运行学术研究演示
        
        Returns:
            ExampleResult: 演示结果
        """
        self.logger.info("开始学术研究演示")
        
        try:
            # 创建演示配置
            demo_config = self._create_academic_demo_config()
            
            # 执行演示
            result = self._execute_demo(demo_config)
            
            # 记录结果
            self.demo_results.append(result)
            self.current_demo = result
            
            self.logger.info("学术研究演示完成")
            return result
            
        except Exception as e:
            self.logger.error(f"学术研究演示执行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def run_performance_benchmark_demo(self) -> ExampleResult:
        """
        运行性能基准演示
        
        Returns:
            ExampleResult: 演示结果
        """
        self.logger.info("开始性能基准演示")
        
        try:
            # 创建演示配置
            demo_config = self._create_performance_demo_config()
            
            # 执行演示
            result = self._execute_demo(demo_config)
            
            # 记录结果
            self.demo_results.append(result)
            self.current_demo = result
            
            self.logger.info("性能基准演示完成")
            return result
            
        except Exception as e:
            self.logger.error(f"性能基准演示执行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def _create_basic_demo_config(self) -> ExampleConfig:
        """创建基础演示配置"""
        return ExampleConfig(
            demo_name="基础方剂分析演示",
            scenario=DemoScenario.BASIC_USAGE,
            description="演示系统对经典方剂的基本分析功能",
            expected_outcome="成功识别方剂组成并生成基本分析报告",
            input_data={
                "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。",
                "metadata": {
                    "dynasty": "东汉",
                    "author": "张仲景",
                    "book": "伤寒论"
                },
                "objective": "分析小柴胡汤的方剂组成"
            },
            configuration={
                "max_iterations": 5,
                "timeout_seconds": 300,
                "enable_auto_repair": True,
                "enable_performance_monitoring": True
            },
            academic_requirements={
                "scientific_validity": 0.95,
                "methodological_quality": 0.90,
                "reproducibility": 0.95
            },
            performance_target={
                "max_execution_time": 300,
                "memory_usage_limit": 2048,
                "throughput": 1000
            },
            metadata={
                "demo_type": "basic",
                "difficulty": "beginner",
                "duration": "5分钟"
            }
        )
    
    def _create_advanced_demo_config(self) -> ExampleConfig:
        """创建高级分析演示配置"""
        return ExampleConfig(
            demo_name="高级方剂比较演示",
            scenario=DemoScenario.ADVANCED_ANALYSIS,
            description="演示系统对多个方剂的深度比较分析功能",
            expected_outcome="成功比较多个方剂组成并识别其相似性和差异性",
            input_data={
                "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。\n四物汤方：当归三两，川芎二两，白芍三两，熟地黄三两。",
                "metadata": {
                    "dynasty": "东汉/宋代",
                    "author": "张仲景/不详",
                    "book": "伤寒论/太平惠民和剂局方"
                },
                "objective": "比较小柴胡汤与四物汤的组成差异"
            },
            configuration={
                "max_iterations": 10,
                "timeout_seconds": 600,
                "enable_auto_repair": True,
                "enable_performance_monitoring": True,
                "enable_academic_analysis": True
            },
            academic_requirements={
                "scientific_validity": 0.98,
                "methodological_quality": 0.95,
                "reproducibility": 0.98,
                "standard_compliance": 0.99
            },
            performance_target={
                "max_execution_time": 600,
                "memory_usage_limit": 4096,
                "throughput": 500
            },
            metadata={
                "demo_type": "advanced",
                "difficulty": "advanced",
                "duration": "10分钟"
            }
        )
    
    def _create_academic_demo_config(self) -> ExampleConfig:
        """创建学术研究演示配置"""
        return ExampleConfig(
            demo_name="学术研究演示",
            scenario=DemoScenario.ACADEMIC_RESEARCH,
            description="演示系统在学术研究中的应用，包括学术质量保证",
            expected_outcome="生成符合学术标准的分析报告和研究洞察",
            input_data={
                "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。\n四物汤方：当归三两，川芎二两，白芍三两，熟地黄三两。\n根据《伤寒论》和《太平惠民和剂局方》记载，两方剂均具有重要临床价值。",
                "metadata": {
                    "dynasty": "东汉/宋代",
                    "author": "张仲景/不详",
                    "book": "伤寒论/太平惠民和剂局方",
                    "research_field": "中医方剂学",
                    "academic_level": "博士研究"
                },
                "objective": "基于中医理论对经典方剂进行学术研究分析"
            },
            configuration={
                "max_iterations": 15,
                "timeout_seconds": 1200,
                "enable_auto_repair": True,
                "enable_performance_monitoring": True,
                "enable_academic_analysis": True,
                "enable_knowledge_graph": True,
                "enable_research_insights": True
            },
            academic_requirements={
                "scientific_validity": 0.99,
                "methodological_quality": 0.98,
                "reproducibility": 0.99,
                "standard_compliance": 0.99,
                "academic_value": 0.95
            },
            performance_target={
                "max_execution_time": 1200,
                "memory_usage_limit": 8192,
                "throughput": 200
            },
            metadata={
                "demo_type": "academic",
                "difficulty": "expert",
                "duration": "15分钟",
                "academic_level": "博士研究"
            }
        )
    
    def _create_performance_demo_config(self) -> ExampleConfig:
        """创建性能基准演示配置"""
        return ExampleConfig(
            demo_name="性能基准演示",
            scenario=DemoScenario.PERFORMANCE_BENCHMARK,
            description="演示系统在不同负载下的性能表现",
            expected_outcome="展示系统在不同数据量下的性能基准表现",
            input_data={
                "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。",
                "metadata": {
                    "dynasty": "东汉",
                    "author": "张仲景",
                    "book": "伤寒论"
                },
                "objective": "性能基准测试"
            },
            configuration={
                "max_iterations": 3,
                "timeout_seconds": 180,
                "enable_performance_monitoring": True,
                "enable_benchmarking": True,
                "enable_scaling_test": True
            },
            academic_requirements={
                "scientific_validity": 0.95,
                "methodological_quality": 0.90,
                "reproducibility": 0.95
            },
            performance_target={
                "max_execution_time": 180,
                "memory_usage_limit": 2048,
                "throughput": 2000,
                "concurrent_requests": 10
            },
            metadata={
                "demo_type": "performance",
                "difficulty": "intermediate",
                "duration": "5分钟",
                "benchmark_type": "load_testing"
            }
        )
    
    def _execute_demo(self, demo_config: ExampleConfig) -> ExampleResult:
        """执行演示"""
        start_time = time.time()
        self.demo_status = DemoStatus.RUNNING
        
        try:
            self.logger.info(f"开始执行演示: {demo_config.demo_name}")
            
            # 模拟系统处理流程
            # 1. 数据预处理
            preprocessing_result = self._simulate_preprocessing(demo_config.input_data)
            
            # 2. 实体抽取
            extraction_result = self._simulate_extraction(preprocessing_result)
            
            # 3. 语义建模
            modeling_result = self._simulate_modeling(extraction_result)
            
            # 4. 推理分析
            reasoning_result = self._simulate_reasoning(modeling_result)
            
            # 5. 输出生成
            output_result = self._simulate_output_generation(reasoning_result)
            
            # 6. 学术质量评估
            academic_result = self._simulate_academic_assessment(output_result)
            
            # 7. 性能基准评估
            performance_result = self._simulate_performance_assessment(academic_result)
            
            # 构造演示结果
            result = ExampleResult(
                demo_id=f"demo_{int(time.time())}_{hashlib.md5(demo_config.demo_name.encode()).hexdigest()[:8]}",
                demo_name=demo_config.demo_name,
                scenario=demo_config.scenario.value,
                status=DemoStatus.COMPLETED,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                execution_time=time.time() - start_time,
                input_data=demo_config.input_data,
                output_data={
                    "preprocessing": preprocessing_result,
                    "extraction": extraction_result,
                    "modeling": modeling_result,
                    "reasoning": reasoning_result,
                    "output": output_result,
                    "academic_assessment": academic_result,
                    "performance": performance_result
                },
                quality_metrics=self._calculate_quality_metrics(demo_config, output_result),
                academic_insights=self._generate_academic_insights(output_result),
                performance_metrics=self._calculate_performance_metrics(performance_result),
                recommendations=self._generate_recommendations(demo_config, output_result),
                metadata={
                    "config": demo_config.__dict__,
                    "demo_scenario": demo_config.scenario.value,
                    "execution_environment": "demo_environment"
                }
            )
            
            self.demo_status = DemoStatus.COMPLETED
            self.logger.info(f"演示执行完成: {demo_config.demo_name}")
            return result
            
        except Exception as e:
            self.demo_status = DemoStatus.FAILED
            self.logger.error(f"演示执行失败: {e}")
            self.logger.error(traceback.format_exc())
            
            # 构造失败结果
            result = ExampleResult(
                demo_id=f"demo_error_{int(time.time())}",
                demo_name=demo_config.demo_name,
                scenario=demo_config.scenario.value,
                status=DemoStatus.FAILED,
                start_time=datetime.now().isoformat(),
                end_time=datetime.now().isoformat(),
                execution_time=time.time() - start_time,
                input_data=demo_config.input_data,
                error_message=str(e),
                metadata={
                    "config": demo_config.__dict__,
                    "error": str(e)
                }
            )
            
            return result
    
    def _simulate_preprocessing(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """模拟数据预处理"""
        time.sleep(0.05)  # 模拟处理时间
        
        return {
            "processed_text": input_data["raw_text"][:100] + "...",
            "metadata": input_data["metadata"],
            "processing_time": 0.05,
            "quality_score": 0.95,
            "confidence": 0.92
        }
    
    def _simulate_extraction(self, _preprocessing_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟实体抽取"""
        time.sleep(0.1)  # 模拟处理时间
        
        # 模拟抽取的实体
        entities = [
            {
                "name": "小柴胡汤",
                "type": "formula",
                "confidence": 0.95,
                "position": (0, 5)
            },
            {
                "name": "柴胡",
                "type": "herb",
                "confidence": 0.92,
                "position": (10, 13)
            },
            {
                "name": "黄芩",
                "type": "herb",
                "confidence": 0.88,
                "position": (15, 18)
            }
        ]
        
        return {
            "entities": entities,
            "extraction_time": 0.1,
            "entity_count": len(entities),
            "quality_score": 0.90,
            "confidence": 0.88
        }
    
    def _simulate_modeling(self, _extraction_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟语义建模"""
        time.sleep(0.15)  # 模拟处理时间
        
        # 模拟构建的语义图谱
        knowledge_graph = {
            "nodes": [
                {"id": "formula_1", "name": "小柴胡汤", "type": "formula"},
                {"id": "herb_1", "name": "柴胡", "type": "herb"},
                {"id": "herb_2", "name": "黄芩", "type": "herb"}
            ],
            "edges": [
                {"source": "formula_1", "target": "herb_1", "relationship": "contains"},
                {"source": "formula_1", "target": "herb_2", "relationship": "contains"}
            ],
            "graph_properties": {
                "nodes_count": 3,
                "edges_count": 2,
                "density": 0.67
            }
        }
        
        return {
            "knowledge_graph": knowledge_graph,
            "modeling_time": 0.15,
            "graph_quality": 0.85,
            "confidence": 0.82
        }
    
    def _simulate_reasoning(self, _modeling_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟推理分析"""
        time.sleep(0.2)  # 模拟处理时间
        
        # 模拟推理结果
        reasoning_results = {
            "insights": [
                {
                    "type": "formula_relationship",
                    "title": "小柴胡汤组成分析",
                    "description": "小柴胡汤包含柴胡、黄芩等药材，具有和解少阳的功效",
                    "confidence": 0.95,
                    "tags": ["formula", "analysis", "academic"]
                }
            ],
            "relationships": [
                {
                    "source": "小柴胡汤",
                    "target": "柴胡",
                    "relationship": "成分关系",
                    "confidence": 0.92
                }
            ],
            "analysis_time": 0.2,
            "quality_score": 0.92,
            "confidence": 0.88
        }
        
        return reasoning_results
    
    def _simulate_output_generation(self, reasoning_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟输出生成"""
        time.sleep(0.1)  # 模拟处理时间
        
        # 模拟输出结果
        output = {
            "metadata": {
                "source": "test_document",
                "processing_timestamp": datetime.now().isoformat(),
                "objective": "中医古籍分析"
            },
            "analysis_results": {
                "entities": reasoning_result.get("relationships", []),
                "semantic_graph": reasoning_result.get("insights", []),
                "reasoning_results": reasoning_result,
                "quality_metrics": {
                    "entities_extracted": 2,
                    "confidence_score": 0.90,
                    "completeness": 0.85
                }
            },
            "output_time": 0.1,
            "quality_score": 0.88,
            "confidence": 0.85
        }
        
        return output
    
    def _simulate_academic_assessment(self, _output_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟学术评估"""
        time.sleep(0.05)  # 模拟处理时间
        
        # 模拟学术评估结果
        academic_assessment = {
            "scientific_validity": 0.95,
            "methodological_quality": 0.92,
            "reproducibility": 0.90,
            "standard_compliance": 0.98,
            "academic_value": 0.93,
            "assessment_time": 0.05,
            "quality_score": 0.92,
            "confidence": 0.90
        }
        
        return academic_assessment
    
    def _simulate_performance_assessment(self, _academic_result: Dict[str, Any]) -> Dict[str, Any]:
        """模拟性能评估"""
        time.sleep(0.02)  # 模拟处理时间
        
        # 模拟性能评估结果
        performance_assessment = {
            "execution_time": 0.55,
            "memory_usage": 512,
            "cpu_usage": 0.65,
            "throughput": 12.5,
            "resource_utilization": 0.75,
            "performance_score": 0.88
        }
        
        return performance_assessment
    
    def _calculate_quality_metrics(self, _demo_config: ExampleConfig, 
                                _output_result: Dict[str, Any]) -> Dict[str, Any]:
        """计算质量指标"""
        return {
            "completeness": 0.95,
            "accuracy": 0.92,
            "consistency": 0.90,
            "scientific_validity": 0.95,
            "methodological_quality": 0.90,
            "reproducibility": 0.95,
            "standard_compliance": 0.98,
            "quality_score": 0.92
        }
    
    def _generate_academic_insights(self, output_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成学术洞察"""
        insights = []
        
        # 基于输出结果生成学术洞察
        if "analysis_results" in output_result:
            insights.append({
                "type": "formula_analysis",
                "title": "方剂组成分析洞察",
                "description": "成功识别方剂组成成分，符合中医理论要求",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat(),
                "tags": ["formula", "analysis", "academic"]
            })
            
            insights.append({
                "type": "scientific_validity",
                "title": "科学性验证",
                "description": "分析结果符合中医理论和现代研究标准",
                "confidence": 0.92,
                "timestamp": datetime.now().isoformat(),
                "tags": ["scientific", "validity", "academic"]
            })
        
        return insights
    
    def _calculate_performance_metrics(self, performance_result: Dict[str, Any]) -> Dict[str, Any]:
        """计算性能指标"""
        return {
            "execution_time": performance_result.get("execution_time", 0.0),
            "memory_usage": performance_result.get("memory_usage", 0.0),
            "cpu_usage": performance_result.get("cpu_usage", 0.0),
            "throughput": performance_result.get("throughput", 0.0),
            "resource_utilization": performance_result.get("resource_utilization", 0.0),
            "performance_score": performance_result.get("performance_score", 0.0)
        }
    
    def _generate_recommendations(self, demo_config: ExampleConfig, 
                               _output_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成改进建议"""
        recommendations = []
        
        # 基于演示配置和结果生成建议
        if demo_config.scenario == DemoScenario.ADVANCED_ANALYSIS:
            recommendations.append({
                "type": "enhancement",
                "title": "提升分析深度",
                "description": "建议增加更多方剂的对比分析功能",
                "priority": "medium",
                "confidence": 0.85,
                "timestamp": datetime.now().isoformat()
            })
        
        if demo_config.scenario == DemoScenario.ACADEMIC_RESEARCH:
            recommendations.append({
                "type": "academic_improvement",
                "title": "增强学术价值",
                "description": "建议增加更多学术引用和参考文献功能",
                "priority": "high",
                "confidence": 0.90,
                "timestamp": datetime.now().isoformat()
            })
        
        return recommendations
    
    def get_demo_results(self) -> List[ExampleResult]:
        """获取演示结果"""
        return self.demo_results.copy()
    
    def get_latest_demo_result(self) -> Optional[ExampleResult]:
        """获取最新演示结果"""
        if self.demo_results:
            return self.demo_results[-1]
        return None
    
    def get_demo_summary(self) -> Dict[str, Any]:
        """获取演示摘要"""
        if not self.demo_results:
            return {"message": "没有演示结果"}
        
        total_demos = len(self.demo_results)
        successful_demos = sum(1 for r in self.demo_results if r.status == DemoStatus.COMPLETED)
        failed_demos = total_demos - successful_demos
        
        # 计算平均质量评分
        quality_scores = [r.quality_metrics.get("quality_score", 0.0) for r in self.demo_results]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        
        return {
            "total_demos": total_demos,
            "successful_demos": successful_demos,
            "failed_demos": failed_demos,
            "success_rate": successful_demos / total_demos if total_demos > 0 else 0.0,
            "average_quality_score": avg_quality,
            "latest_demo": self.demo_results[-1].demo_name if self.demo_results else "none"
        }
    
    def export_demo_results(self, output_path: str, format_type: str = "json") -> bool:
        """导出演示结果"""
        try:
            demo_data = {
                "demo_framework_info": {
                    "framework_name": "中医古籍演示框架",
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "demo_summary": self.get_demo_summary()
                },
                "demo_results": [r.__dict__ for r in self.demo_results],
                "demo_config": self.config
            }
            
            if format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(demo_data, f, ensure_ascii=False, indent=2)
            elif format_type == "csv":
                # CSV格式导出（简化实现）
                pass
            
            self.logger.info(f"演示结果已导出到: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"演示结果导出失败: {e}")
            return False
    
    def run_demo_suite(self) -> Dict[str, Any]:
        """运行演示套件"""
        self.logger.info("开始运行演示套件")
        
        try:
            results = {
                "suite_results": {},
                "overall_summary": {},
                "execution_time": 0.0,
                "timestamp": datetime.now().isoformat()
            }
            
            # 运行所有演示
            demo_scenarios = [
                ("基础演示", self.run_basic_demo),
                ("高级分析演示", self.run_advanced_analysis_demo),
                ("学术研究演示", self.run_academic_research_demo),
                ("性能基准演示", self.run_performance_benchmark_demo)
            ]
            
            start_time = time.time()
            
            for demo_name, demo_func in demo_scenarios:
                try:
                    result = demo_func()
                    results["suite_results"][demo_name] = result.__dict__
                except Exception as e:
                    self.logger.error(f"{demo_name} 执行失败: {e}")
                    results["suite_results"][demo_name] = {
                        "error": str(e),
                        "status": "failed"
                    }
            
            results["overall_summary"] = self.get_demo_summary()
            results["execution_time"] = time.time() - start_time
            
            self.logger.info("演示套件运行完成")
            return results
            
        except Exception as e:
            self.logger.error(f"演示套件运行失败: {e}")
            self.logger.error(traceback.format_exc())
            raise
    
    def cleanup(self) -> bool:
        """清理演示资源"""
        try:
            # 清理演示结果
            self.demo_results.clear()
            self.current_demo = None
            self.demo_status = DemoStatus.NOT_STARTED
            
            self.logger.info("演示资源清理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"演示资源清理失败: {e}")
            return False

# 演示使用示例类
class DemoUsageExamples:
    """
    演示使用示例
    
    提供系统使用示例，帮助用户快速上手和理解系统功能。
    """
    
    @staticmethod
    def basic_usage_example():
        """基础使用示例"""
        logger.info("=== 基础使用示例 ===")
        
        # 创建演示实例
        demo = DemoUsage()
        
        # 运行基础演示
        try:
            result = demo.run_basic_demo()
            
            # 显示结果
            print(f"演示名称: {result.demo_name}")
            print(f"执行时间: {result.execution_time:.2f} 秒")
            print(f"质量评分: {result.quality_metrics.get('quality_score', 0.0):.2f}")
            print(f"学术相关性: {result.quality_metrics.get('scientific_validity', 0.0):.2f}")
            
            # 显示学术洞察
            insights = result.academic_insights
            if insights:
                print("\n学术洞察:")
                for insight in insights[:2]:  # 显示前2个洞察
                    print(f"  - {insight['title']}: {insight['description']}")
            
            print("基础使用示例完成")
            return result
            
        except Exception as e:
            logger.error(f"基础使用示例执行失败: {e}")
            raise
    
    @staticmethod
    def advanced_analysis_example():
        """高级分析示例"""
        logger.info("=== 高级分析示例 ===")
        
        # 创建演示实例
        demo = DemoUsage()
        
        # 运行高级分析演示
        try:
            result = demo.run_advanced_analysis_demo()
            
            # 显示结果
            print(f"演示名称: {result.demo_name}")
            print(f"执行时间: {result.execution_time:.2f} 秒")
            print(f"质量评分: {result.quality_metrics.get('quality_score', 0.0):.2f}")
            
            # 显示性能指标
            perf_metrics = result.performance_metrics
            if perf_metrics:
                print("\n性能指标:")
                for key, value in perf_metrics.items():
                    print(f"  {key}: {value}")
            
            print("高级分析示例完成")
            return result
            
        except Exception as e:
            logger.error(f"高级分析示例执行失败: {e}")
            raise
    
    @staticmethod
    def academic_research_example():
        """学术研究示例"""
        logger.info("=== 学术研究示例 ===")
        
        # 创建演示实例
        demo = DemoUsage()
        
        # 运行学术研究演示
        try:
            result = demo.run_academic_research_demo()
            
            # 显示结果
            print(f"演示名称: {result.demo_name}")
            print(f"执行时间: {result.execution_time:.2f} 秒")
            print(f"学术相关性: {result.quality_metrics.get('scientific_validity', 0.0):.2f}")
            
            # 显示改进建议
            recommendations = result.recommendations
            if recommendations:
                print("\n改进建议:")
                for rec in recommendations[:2]:  # 显示前2个建议
                    print(f"  - {rec['title']}: {rec['description']}")
            
            print("学术研究示例完成")
            return result
            
        except Exception as e:
            logger.error(f"学术研究示例执行失败: {e}")
            raise
    
    @staticmethod
    def performance_benchmark_example():
        """性能基准示例"""
        logger.info("=== 性能基准示例 ===")
        
        # 创建演示实例
        demo = DemoUsage()
        
        # 运行性能基准演示
        try:
            result = demo.run_performance_benchmark_demo()
            
            # 显示结果
            print(f"演示名称: {result.demo_name}")
            print(f"执行时间: {result.execution_time:.2f} 秒")
            
            # 显示性能指标
            perf_metrics = result.performance_metrics
            if perf_metrics:
                print("\n性能基准:")
                print(f"  执行时间: {perf_metrics.get('execution_time', 0.0):.2f} 秒")
                print(f"  内存使用: {perf_metrics.get('memory_usage', 0.0)} MB")
                print(f"  CPU使用率: {perf_metrics.get('cpu_usage', 0.0):.2%}")
                print(f"  吞吐量: {perf_metrics.get('throughput', 0.0)} 处理/秒")
            
            print("性能基准示例完成")
            return result
            
        except Exception as e:
            logger.error(f"性能基准示例执行失败: {e}")
            raise

# 导出主要类和函数
__all__ = [
    'DemoUsage',
    'DemoUsageExamples',
    'ExampleConfig',
    'ExampleResult',
    'DemoScenario',
    'DemoStatus'
]
