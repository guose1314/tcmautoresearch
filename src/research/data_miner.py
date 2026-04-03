"""研究层数据挖掘模块。

目标：将 LDA/聚类、网络药理学与统计挖掘逻辑从 research_methods 渐进独立。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, List, Tuple

import numpy as np

try:
    from scipy.stats import chi2_contingency as _chi2_contingency

    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False
    _chi2_contingency = None

from src.analytics.data_miner import DataMiner as _AnalyticsDataMiner


class DataMiner(_AnalyticsDataMiner):
    """研究层 DataMiner 入口，复用 analytics 实现。"""


# 复用 semantic_modeling 中的实现，避免数据重复
from src.semantic_modeling.methods.network_pharmacology import (
    NetworkPharmacologySystemBiologyAnalyzer,
)


class StatisticalDataMiner:
    """统计挖掘工具（从 research_methods 抽离）。"""

    @classmethod
    def frequency_and_chi_square(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        herb_freq = cls._build_herb_frequency(records, herbs)
        syndrome_values = cls._collect_syndrome_values(records)

        chi_square_items: List[Dict[str, Any]] = []

        for herb in herbs:
            for syndrome in syndrome_values:
                a, b, c, d = cls._build_contingency_counts(records, herb, syndrome)
                chi2, p = cls._compute_chi_square(a, b, c, d)
                chi_square_items.append(
                    {
                        "herb": herb,
                        "syndrome": syndrome,
                        "chi2": round(float(chi2), 4),
                        "p_value": round(float(p), 6) if p is not None else None,
                    }
                )

        chi_square_items = sorted(chi_square_items, key=lambda x: x.get("chi2", 0), reverse=True)[:15]
        top_freq = sorted(herb_freq.items(), key=lambda x: x[1], reverse=True)[:15]

        return {
            "herb_frequency": [{"herb": h, "count": c} for h, c in top_freq],
            "chi_square_top": chi_square_items,
        }

    @classmethod
    def _build_herb_frequency(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, int]:
        """统计药物频次。"""
        herb_freq: Dict[str, int] = {h: 0 for h in herbs}
        for record in records:
            for herb in record.get("herbs", []):
                herb_freq[herb] = herb_freq.get(herb, 0) + 1
        return herb_freq

    @classmethod
    def _collect_syndrome_values(cls, records: List[Dict[str, Any]]) -> List[str]:
        """提取症候值集合。"""
        return sorted(list({record.get("syndrome", "unknown") for record in records}))

    @classmethod
    def _build_contingency_counts(
        cls,
        records: List[Dict[str, Any]],
        herb: str,
        syndrome: str,
    ) -> Tuple[int, int, int, int]:
        """构建 2x2 列联表计数。"""
        a = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") == syndrome)
        b = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") != syndrome)
        c = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") == syndrome)
        d = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") != syndrome)
        return a, b, c, d

    @classmethod
    def _compute_chi_square(cls, a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
        """计算卡方值，优先使用 scipy，失败时回退公式计算。"""
        if _HAS_SCIPY and _chi2_contingency is not None:
            try:
                chi2_result: Any = _chi2_contingency([[a, b], [c, d]])
                return float(chi2_result[0]), float(chi2_result[1])
            except Exception:
                return cls._chi2_fallback(a, b, c, d)
        return cls._chi2_fallback(a, b, c, d)

    @classmethod
    def _chi2_fallback(cls, a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
        """无 scipy 时的卡方近似回退。"""
        n = a + b + c + d
        num = n * (a * d - b * c) ** 2
        den = (a + b) * (c + d) * (a + c) * (b + d)
        return (float(num / den) if den > 0 else 0.0), None

    @classmethod
    def association_rules(cls, transactions: List[List[str]]) -> Dict[str, Any]:
        n = len(transactions)
        if n == 0:
            return {"rules": []}

        item_count: Dict[str, int] = {}
        pair_count: Dict[Tuple[str, str], int] = {}
        for tx in transactions:
            unique = sorted(set(tx))
            for i in unique:
                item_count[i] = item_count.get(i, 0) + 1
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    pair = (unique[i], unique[j])
                    pair_count[pair] = pair_count.get(pair, 0) + 1

        rules: List[Dict[str, Any]] = []
        for (a, b), c_ab in pair_count.items():
            support = c_ab / n
            conf_a_b = c_ab / item_count[a]
            conf_b_a = c_ab / item_count[b]
            lift_a_b = conf_a_b / (item_count[b] / n)
            lift_b_a = conf_b_a / (item_count[a] / n)
            rules.append(
                {
                    "antecedent": [a],
                    "consequent": [b],
                    "support": round(support, 4),
                    "confidence": round(conf_a_b, 4),
                    "lift": round(lift_a_b, 4),
                }
            )
            rules.append(
                {
                    "antecedent": [b],
                    "consequent": [a],
                    "support": round(support, 4),
                    "confidence": round(conf_b_a, 4),
                    "lift": round(lift_b_a, 4),
                }
            )

        rules = sorted(rules, key=lambda x: (x["lift"], x["confidence"]), reverse=True)[:20]
        return {"rules": rules}

    @classmethod
    def complex_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        nx = import_module("networkx")

        herb_graph = nx.Graph()
        for r in records:
            herbs = sorted(set(r.get("herbs", [])))
            for h in herbs:
                herb_graph.add_node(h)
            for i in range(len(herbs)):
                for j in range(i + 1, len(herbs)):
                    u, v = herbs[i], herbs[j]
                    if herb_graph.has_edge(u, v):
                        herb_graph[u][v]["weight"] += 1
                    else:
                        herb_graph.add_edge(u, v, weight=1)

        centrality = nx.degree_centrality(herb_graph) if herb_graph.number_of_nodes() > 0 else {}
        top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
        avg_clustering = nx.average_clustering(herb_graph) if herb_graph.number_of_nodes() > 1 else 0.0

        communities_out: List[List[str]] = []
        try:
            comms = nx.algorithms.community.greedy_modularity_communities(herb_graph)
            communities_out = [sorted(list(c)) for c in comms]
        except Exception:
            communities_out = []

        return {
            "nodes": herb_graph.number_of_nodes(),
            "edges": herb_graph.number_of_edges(),
            "density": round(nx.density(herb_graph), 4) if herb_graph.number_of_nodes() > 1 else 0.0,
            "avg_clustering": round(float(avg_clustering), 4),
            "top_central_nodes": [{"node": n, "degree_centrality": round(v, 4)} for n, v in top_nodes],
            "communities": communities_out,
        }

    @classmethod
    def time_series_and_dose_response(cls, records: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        years, values = cls._extract_time_series(records, context)
        slope, intercept = cls._fit_linear_trend(years, values)

        doses, responses = cls._extract_dose_response(records, context)
        dose_model = cls._fit_dose_response_model(doses, responses)

        return {
            "time_series_trend": {
                "slope": round(float(slope), 6),
                "intercept": round(float(intercept), 4),
                "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
            },
            "dose_response": dose_model,
        }

    @classmethod
    def _extract_time_series(
        cls,
        records: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """提取时间序列输入。"""
        ts_data = context.get("time_series_data")
        if ts_data:
            years = np.array([float(point.get("time")) for point in ts_data])
            values = np.array([float(point.get("value")) for point in ts_data])
            return years, values

        years = np.array([float(record.get("year") or 0.0) for record in records])
        values = np.array([float(record.get("response", 0.0)) for record in records])
        return years, values

    @classmethod
    def _fit_linear_trend(cls, years: np.ndarray, values: np.ndarray) -> Tuple[float, float]:
        """拟合线性趋势。"""
        if len(years) >= 2:
            coeff = np.polyfit(years, values, deg=1)
            return float(coeff[0]), float(coeff[1])
        return 0.0, float(values[0]) if len(values) else 0.0

    @classmethod
    def _extract_dose_response(
        cls,
        records: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """提取剂量-响应输入。"""
        dr_data = context.get("dose_response_data")
        if dr_data:
            doses = np.array([float(point.get("dose")) for point in dr_data])
            responses = np.array([float(point.get("response")) for point in dr_data])
            return doses, responses

        doses = np.array([float(record.get("dose_total", 0.0)) for record in records if record.get("dose_total") is not None])
        responses = np.array([float(record.get("response", 0.0)) for record in records if record.get("dose_total") is not None])
        return doses, responses

    @classmethod
    def _fit_dose_response_model(cls, doses: np.ndarray, responses: np.ndarray) -> Dict[str, Any]:
        """拟合剂量响应模型，优先 hill，失败时线性回退。"""
        if len(doses) < 3:
            return {"model": "insufficient_data"}

        hill_fit = cls._try_fit_hill(doses, responses)
        if hill_fit is not None:
            return hill_fit

        coeff = np.polyfit(doses, responses, deg=1)
        return {
            "model": "linear",
            "slope": round(float(coeff[0]), 4),
            "intercept": round(float(coeff[1]), 4),
        }

    @classmethod
    def _try_fit_hill(cls, doses: np.ndarray, responses: np.ndarray) -> Dict[str, Any] | None:
        """尝试 hill 曲线拟合，失败返回 None。"""
        try:
            from scipy.optimize import curve_fit

            def hill(x, emax, ec50, h):
                return emax * (x ** h) / (ec50 ** h + x ** h + 1e-9)

            popt, _ = curve_fit(hill, doses, responses, bounds=(0, [1.5, 200.0, 5.0]), maxfev=20000)
            return {
                "model": "hill",
                "emax": round(float(popt[0]), 4),
                "ec50": round(float(popt[1]), 4),
                "hill_coefficient": round(float(popt[2]), 4),
            }
        except Exception:
            return None

    @classmethod
    def bayesian_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        samples: List[Dict[str, int]] = []
        for r in records:
            syndrome = str(r.get("syndrome", ""))
            formula = str(r.get("formula", ""))
            response = float(r.get("response", 0.0))
            samples.append(
                {
                    "Q": 1 if "气虚" in syndrome else 0,
                    "F": 1 if formula == "补中益气汤" else 0,
                    "R": 1 if response >= 0.72 else 0,
                }
            )

        n = len(samples) or 1
        p_q = sum(s["Q"] for s in samples) / n

        def cond_prob(var: str, given: Dict[str, int]) -> float:
            matched = [s for s in samples if all(s[k] == v for k, v in given.items())]
            if not matched:
                return 0.5
            return sum(s[var] for s in matched) / len(matched)

        p_f_q1 = cond_prob("F", {"Q": 1})
        p_f_q0 = cond_prob("F", {"Q": 0})
        p_r_q1_f1 = cond_prob("R", {"Q": 1, "F": 1})
        p_r_q1_f0 = cond_prob("R", {"Q": 1, "F": 0})

        inference = p_r_q1_f1

        return {
            "structure": ["Q->F", "Q->R", "F->R"],
            "priors": {"P(Q=1)": round(float(p_q), 4)},
            "cpd": {
                "P(F=1|Q=1)": round(float(p_f_q1), 4),
                "P(F=1|Q=0)": round(float(p_f_q0), 4),
                "P(R=1|Q=1,F=1)": round(float(p_r_q1_f1), 4),
                "P(R=1|Q=1,F=0)": round(float(p_r_q1_f0), 4),
            },
            "inference_example": {
                "query": "P(R=1|Q=1,F=1)",
                "value": round(float(inference), 4),
            },
        }


__all__ = [
    "DataMiner",
    "NetworkPharmacologySystemBiologyAnalyzer",
    "StatisticalDataMiner",
]
