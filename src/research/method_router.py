# src/research/method_router.py
"""
研究方法路由器（ResearchMethodRouter）。

负责将分析任务路由到对应的研究方法 analyzer，实现指令05要求的
"让11个研究方法 sub-module 真正参与科研流程"。

支持的分析类型：
  - formula_structure          → FormulaStructureAnalyzer
  - network_pharmacology       → NetworkPharmacologySystemBiologyAnalyzer
  - classical_literature       → ClassicalLiteratureArchaeologyAnalyzer
  - complexity_dynamics        → ComplexityNonlinearDynamicsAnalyzer
  - supramolecular             → SupramolecularPhysicochemicalAnalyzer
  - integrated_research        → IntegratedResearchAnalyzer
  - summary_analysis           → SummaryAnalysisEngine
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ResearchMethodRouter:
    """
    研究方法路由器。

    将分析任务路由到对应的研究方法 analyzer，返回结构化分析结果。
    支持动态注册新的分析器，所有默认分析器均延迟初始化以避免启动开销。

    用法::

        router = ResearchMethodRouter()
        result = router.route("formula_structure", corpus_data)
    """

    def __init__(self) -> None:
        self._methods: Dict[str, Any] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """延迟注册所有默认研究方法分析器（按需实例化，失败则跳过）。"""
        default_mapping = {
            "formula_structure": "FormulaStructureAnalyzer",
            "formula_comparator": "FormulaComparator",
            "network_pharmacology": "NetworkPharmacologySystemBiologyAnalyzer",
            "classical_literature": "ClassicalLiteratureArchaeologyAnalyzer",
            "complexity_dynamics": "ComplexityNonlinearDynamicsAnalyzer",
            "supramolecular": "SupramolecularPhysicochemicalAnalyzer",
            "integrated_research": "IntegratedResearchAnalyzer",
            "summary_analysis": "SummaryAnalysisEngine",
            "meta_analysis": "MetaAnalysisEngine",  # I-05：新增 Meta 分析
        }
        try:
            from src.semantic_modeling.research_methods import (
                ClassicalLiteratureArchaeologyAnalyzer,
                ComplexityNonlinearDynamicsAnalyzer,
                FormulaComparator,
                FormulaStructureAnalyzer,
                IntegratedResearchAnalyzer,
                NetworkPharmacologySystemBiologyAnalyzer,
                SummaryAnalysisEngine,
                SupramolecularPhysicochemicalAnalyzer,
            )
            from src.semantic_modeling.methods.meta_analysis import MetaAnalysisEngine  # I-05

            class_map = {
                "FormulaStructureAnalyzer": FormulaStructureAnalyzer,
                "FormulaComparator": FormulaComparator,
                "NetworkPharmacologySystemBiologyAnalyzer": NetworkPharmacologySystemBiologyAnalyzer,
                "ClassicalLiteratureArchaeologyAnalyzer": ClassicalLiteratureArchaeologyAnalyzer,
                "ComplexityNonlinearDynamicsAnalyzer": ComplexityNonlinearDynamicsAnalyzer,
                "SupramolecularPhysicochemicalAnalyzer": SupramolecularPhysicochemicalAnalyzer,
                "IntegratedResearchAnalyzer": IntegratedResearchAnalyzer,
                "SummaryAnalysisEngine": SummaryAnalysisEngine,
                "MetaAnalysisEngine": MetaAnalysisEngine,
            }

            for key, class_name in default_mapping.items():
                cls = class_map.get(class_name)
                if cls is None:
                    continue
                try:
                    self._methods[key] = cls()
                    logger.debug("已注册研究方法分析器: %s → %s", key, class_name)
                except Exception as exc:
                    logger.warning("研究方法分析器 %s 初始化失败，跳过: %s", class_name, exc)

        except ImportError as exc:
            logger.warning("无法导入研究方法模块，部分分析器将不可用: %s", exc)

    def register(self, key: str, analyzer: Any) -> None:
        """
        动态注册研究方法分析器。

        Args:
            key: 分析类型标识（如 ``"formula_structure"``）。
            analyzer: 分析器实例，需提供 ``analyze()`` 或 ``execute()`` 方法。
        """
        self._methods[key] = analyzer
        logger.info("已注册自定义研究方法分析器: %s", key)

    def route(
        self,
        analysis_type: str,
        corpus: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        路由到对应研究方法分析器并执行，返回结构化结果。

        Args:
            analysis_type: 分析类型标识。
            corpus: 待分析的语料数据（字典或列表）。
            **kwargs: 传递给分析器的额外参数。

        Returns:
            包含 ``status``、``analysis_type``、``result`` 等键的字典。
            若分析类型未注册，返回 ``{"status": "unsupported", ...}``，不抛异常。
        """
        analyzer = self._methods.get(analysis_type)
        if analyzer is None:
            logger.warning("研究方法 '%s' 未注册，跳过分析", analysis_type)
            return {
                "status": "unsupported",
                "analysis_type": analysis_type,
                "result": {},
                "message": f"分析类型 '{analysis_type}' 未注册，请先调用 register() 方法注册对应分析器。",
            }

        try:
            # 优先尝试 analyze()，其次 execute()
            if hasattr(analyzer, "analyze"):
                raw = analyzer.analyze(corpus, **kwargs)
            elif hasattr(analyzer, "execute"):
                raw = analyzer.execute(corpus if isinstance(corpus, dict) else {"corpus": corpus})
            else:
                raise AttributeError(f"分析器 {type(analyzer).__name__} 既无 analyze() 也无 execute() 方法")

            result = raw if isinstance(raw, dict) else {"data": raw}
            logger.info("研究方法 '%s' 分析完成", analysis_type)
            return {
                "status": "success",
                "analysis_type": analysis_type,
                "result": result,
            }
        except Exception as exc:
            logger.error("研究方法 '%s' 分析失败: %s", analysis_type, exc)
            return {
                "status": "error",
                "analysis_type": analysis_type,
                "result": {},
                "error": str(exc),
            }

    def available_methods(self) -> list[str]:
        """返回已注册的所有分析类型标识列表。"""
        return list(self._methods.keys())
