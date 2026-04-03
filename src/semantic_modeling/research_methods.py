"""高级研究方法模块（架构3.0兼容层）。

.. deprecated::
    本模块已废弃，请直接从 ``src.analysis`` 导入。
    例如::

        from src.analysis import FormulaStructureAnalyzer, SummaryAnalysisEngine

说明：
- 研究方法已按独立文件拆分至 src/semantic_modeling/methods/ 及 src/analysis/。
- 本文件仅保留兼容性重导出，避免现有调用方回归。
"""

import copy
import json
import warnings
from typing import Any, Dict, List, Tuple

warnings.warn(
    "src.semantic_modeling.research_methods is deprecated, "
    "import from src.analysis directly",
    DeprecationWarning,
    stacklevel=2,
)

from src.semantic_modeling import methods as _methods
from src.semantic_modeling.methods.integrated_analyzer import (
    ResearchScoringPanel as _ResearchScoringPanel,
)

ClassicalLiteratureArchaeologyAnalyzer = _methods.ClassicalLiteratureArchaeologyAnalyzer
ComplexityNonlinearDynamicsAnalyzer = _methods.ComplexityNonlinearDynamicsAnalyzer
FormulaComparator = _methods.FormulaComparator
FormulaDosageForm = _methods.FormulaDosageForm
FormulaStructureAnalyzer = _methods.FormulaStructureAnalyzer
HerbPropertyDatabase = _methods.HerbPropertyDatabase
HerbTemperature = _methods.HerbTemperature
IntegratedResearchAnalyzer = _methods.IntegratedResearchAnalyzer
MeridianType = _methods.MeridianType
ModernPharmacologyDatabase = _methods.ModernPharmacologyDatabase
NetworkPharmacologySystemBiologyAnalyzer = _methods.NetworkPharmacologySystemBiologyAnalyzer
SupramolecularPhysicochemicalAnalyzer = _methods.SupramolecularPhysicochemicalAnalyzer
ResearchScoringPanel = _ResearchScoringPanel


class SummaryAnalysisEngine:
    """总结分析：频率/卡方、关联规则、复杂网络、聚类与因子、强化剂量、隐结构、时间序列剂量反应、贝叶斯网络。"""

    _freq_chi_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _association_cache: Dict[str, Dict[str, Any]] = {}
    _network_cache: Dict[str, Dict[str, Any]] = {}
    _cluster_factor_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _reinforced_dosage_cache: Dict[str, Dict[str, Any]] = {}
    _latent_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _time_dose_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    _bayes_cache: Dict[str, Dict[str, Any]] = {}
    _full_result_cache: Dict[str, Dict[str, Any]] = {}

    DEFAULT_FORMULA_RECORDS: List[Dict[str, Any]] = [
        {
            "formula": "补中益气汤",
            "herbs": ["黄芪", "人参", "白术", "茯苓", "甘草", "升麻", "柴胡", "大枣"],
            "syndrome": "气虚证",
            "year": 2019,
            "dose_total": 50,
            "response": 0.72,
        },
        {
            "formula": "四君子汤",
            "herbs": ["人参", "白术", "茯苓", "甘草"],
            "syndrome": "脾胃气虚",
            "year": 2020,
            "dose_total": 40,
            "response": 0.68,
        },
        {
            "formula": "六君子汤",
            "herbs": ["人参", "白术", "茯苓", "甘草", "半夏", "陈皮"],
            "syndrome": "痰湿气虚",
            "year": 2021,
            "dose_total": 46,
            "response": 0.70,
        },
        {
            "formula": "补中益气汤",
            "herbs": ["黄芪", "党参", "白术", "茯苓", "甘草", "升麻", "柴胡"],
            "syndrome": "中气下陷",
            "year": 2022,
            "dose_total": 48,
            "response": 0.74,
        },
        {
            "formula": "四君子汤",
            "herbs": ["党参", "白术", "茯苓", "甘草"],
            "syndrome": "气虚证",
            "year": 2023,
            "dose_total": 42,
            "response": 0.69,
        },
    ]

    _DEFAULT_RECORDS_FP: str = ""

    @classmethod
    def _get_default_fp(cls) -> str:
        if not cls._DEFAULT_RECORDS_FP:
            cls._DEFAULT_RECORDS_FP = cls._fingerprint(cls.DEFAULT_FORMULA_RECORDS)
        return cls._DEFAULT_RECORDS_FP

    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return repr(value)

    @classmethod
    def analyze(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        records = context.get("summary_formula_records") or cls.DEFAULT_FORMULA_RECORDS
        using_default = records is cls.DEFAULT_FORMULA_RECORDS

        if using_default and not context.get("time_series_data") and not context.get("dose_response_data"):
            cached = cls._full_result_cache.get("__default__")
            if cached is not None:
                return copy.copy(cached)

        transactions = [r.get("herbs", []) for r in records]
        herbs = sorted(list({h for t in transactions for h in t}))

        records_fp = cls._get_default_fp() if using_default else cls._fingerprint(records)
        herbs_fp = cls._fingerprint(herbs)
        tx_fp = cls._fingerprint(transactions)
        ts_fp = cls._fingerprint(context.get("time_series_data"))
        dr_fp = cls._fingerprint(context.get("dose_response_data"))

        freq_key = (records_fp, herbs_fp)
        assoc_key = tx_fp
        network_key = records_fp
        cluster_key = (records_fp, herbs_fp)
        reinforced_key = "default"
        latent_key = (records_fp, herbs_fp)
        time_dose_key = (records_fp, ts_fp, dr_fp)
        bayes_key = records_fp

        if freq_key not in cls._freq_chi_cache:
            cls._freq_chi_cache[freq_key] = cls._frequency_and_chi_square(records, herbs)
        if assoc_key not in cls._association_cache:
            cls._association_cache[assoc_key] = cls._association_rules(transactions)
        if network_key not in cls._network_cache:
            cls._network_cache[network_key] = cls._complex_network_analysis(records)
        if cluster_key not in cls._cluster_factor_cache:
            cls._cluster_factor_cache[cluster_key] = cls._clustering_and_factor_analysis(records, herbs)
        if reinforced_key not in cls._reinforced_dosage_cache:
            cls._reinforced_dosage_cache[reinforced_key] = cls._reinforced_dosage_analysis(records)
        if latent_key not in cls._latent_cache:
            cls._latent_cache[latent_key] = cls._latent_structure_model(records, herbs)
        if time_dose_key not in cls._time_dose_cache:
            cls._time_dose_cache[time_dose_key] = cls._time_series_and_dose_response(records, context)
        if bayes_key not in cls._bayes_cache:
            cls._bayes_cache[bayes_key] = cls._bayesian_network_analysis(records)

        result = {
            "frequency_chi_square": cls._freq_chi_cache[freq_key],
            "association_rules": cls._association_cache[assoc_key],
            "complex_network": cls._network_cache[network_key],
            "clustering_factor": cls._cluster_factor_cache[cluster_key],
            "reinforced_dosage": cls._reinforced_dosage_cache[reinforced_key],
            "latent_structure": cls._latent_cache[latent_key],
            "time_series_dose_response": cls._time_dose_cache[time_dose_key],
            "bayesian_network": cls._bayes_cache[bayes_key],
        }

        if using_default and not context.get("time_series_data") and not context.get("dose_response_data"):
            cls._full_result_cache["__default__"] = result

        return result

    @classmethod
    def _frequency_and_chi_square(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        from src.research.data_miner import StatisticalDataMiner

        return StatisticalDataMiner.frequency_and_chi_square(records, herbs)

    @classmethod
    def _association_rules(cls, transactions: List[List[str]]) -> Dict[str, Any]:
        from src.research.data_miner import StatisticalDataMiner

        return StatisticalDataMiner.association_rules(transactions)

    @classmethod
    def _complex_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        from src.research.data_miner import StatisticalDataMiner

        return StatisticalDataMiner.complex_network_analysis(records)

    @classmethod
    def _clustering_and_factor_analysis(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        from src.research.data_miner import DataMiner

        return DataMiner.cluster(records, herbs)

    @classmethod
    def _svd_fallback_factors(cls, X: Any, herbs: List[str]) -> List[Dict[str, Any]]:
        from src.research.data_miner import DataMiner

        return DataMiner._svd_fallback_factors(X, herbs)

    @classmethod
    def _reinforced_dosage_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        formula_structures = FormulaStructureAnalyzer.FORMULA_STRUCTURES
        optimized: Dict[str, Any] = {}
        for fname, data in formula_structures.items():
            herbs: List[Dict[str, Any]] = []
            for role in ["sovereign", "minister", "assistant", "envoy"]:
                herbs.extend(data.get(role, []))
            if not herbs:
                continue

            scores = []
            for h in herbs:
                name = h.get("name")
                if not isinstance(name, str) or not name:
                    continue
                base_ratio = float(h.get("ratio", 0.0))
                clin = ModernPharmacologyDatabase.get_clinical_efficacy(name)
                comp = ModernPharmacologyDatabase.get_active_components(name)
                reward = 0.55 * min(1.0, len(clin) / 4.0) + 0.45 * min(1.0, len(comp) / 4.0)
                new_score = 0.7 * base_ratio + 0.3 * reward
                scores.append((name, new_score))

            total = sum(v for _, v in scores) or 1.0
            optimized[fname] = [
                {"herb": n, "recommended_ratio": round(v / total, 4)}
                for n, v in sorted(scores, key=lambda x: x[1], reverse=True)
            ]

        return {"optimized_ratios": optimized}

    @classmethod
    def _latent_structure_model(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        from src.research.data_miner import DataMiner

        return DataMiner.latent_topics(records, herbs)

    @classmethod
    def _svd_latent_topics(cls, X: Any, herbs: List[str]) -> List[Dict[str, Any]]:
        from src.research.data_miner import DataMiner

        return DataMiner._svd_latent_topics(X, herbs)

    @classmethod
    def _time_series_and_dose_response(cls, records: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        from src.research.data_miner import StatisticalDataMiner

        return StatisticalDataMiner.time_series_and_dose_response(records, context)

    @classmethod
    def _bayesian_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        from src.research.data_miner import StatisticalDataMiner

        return StatisticalDataMiner.bayesian_network_analysis(records)


__all__ = [
    "FormulaStructureAnalyzer",
    "HerbPropertyDatabase",
    "FormulaComparator",
    "ModernPharmacologyDatabase",
    "IntegratedResearchAnalyzer",
    "ResearchScoringPanel",
    "SummaryAnalysisEngine",
    "NetworkPharmacologySystemBiologyAnalyzer",
    "SupramolecularPhysicochemicalAnalyzer",
    "ClassicalLiteratureArchaeologyAnalyzer",
    "ComplexityNonlinearDynamicsAnalyzer",
    "FormulaDosageForm",
    "HerbTemperature",
    "MeridianType",
]
