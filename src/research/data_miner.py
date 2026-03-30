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


class NetworkPharmacologySystemBiologyAnalyzer:
    """网络药理学与系统生物学分析器（从 research_methods 抽离）。"""

    HERB_TARGET_MAP: Dict[str, List[str]] = {
        "黄芪": ["IL6", "TNF", "AKT1", "VEGFA"],
        "人参": ["AKT1", "MAPK1", "CASP3", "SIRT1"],
        "白术": ["IL1B", "PPARG", "STAT3"],
        "茯苓": ["HIF1A", "NFKB1", "JUN"],
        "甘草": ["PTGS2", "RELA", "TP53", "IL6"],
        "丹参": ["NOS3", "MMP9", "AKT1", "VEGFA"],
    }

    TARGET_PATHWAY_MAP: Dict[str, List[str]] = {
        "AKT1": ["PI3K-Akt", "Insulin signaling"],
        "IL6": ["JAK-STAT", "NF-kB signaling"],
        "TNF": ["TNF signaling", "NF-kB signaling"],
        "VEGFA": ["Angiogenesis", "HIF-1 signaling"],
        "MAPK1": ["MAPK signaling"],
        "PTGS2": ["Arachidonic acid metabolism"],
    }

    @classmethod
    def analyze_formula_network(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        herb_target_edges: List[Dict[str, str]] = []
        target_counter: Dict[str, int] = {}
        pathways: Dict[str, int] = {}

        for herb in herbs:
            targets = cls.HERB_TARGET_MAP.get(herb, [])
            for target in targets:
                herb_target_edges.append({"herb": herb, "target": target})
                target_counter[target] = target_counter.get(target, 0) + 1
                for pathway in cls.TARGET_PATHWAY_MAP.get(target, []):
                    pathways[pathway] = pathways.get(pathway, 0) + 1

        key_targets = sorted(target_counter.items(), key=lambda x: x[1], reverse=True)[:8]
        enriched_pathways = sorted(pathways.items(), key=lambda x: x[1], reverse=True)[:8]

        return {
            "formula_name": formula_name,
            "herb_target_edges": herb_target_edges,
            "target_count": len(target_counter),
            "key_targets": [{"target": t, "degree": d} for t, d in key_targets],
            "enriched_pathways": [{"pathway": p, "score": s} for p, s in enriched_pathways],
            "systems_biology_hypothesis": "多成分-多靶点-多通路协同调控炎症与能量代谢网络",
        }


class StatisticalDataMiner:
    """统计挖掘工具（从 research_methods 抽离）。"""

    @classmethod
    def frequency_and_chi_square(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        herb_freq: Dict[str, int] = {h: 0 for h in herbs}
        syndrome_values = sorted(list({r.get("syndrome", "unknown") for r in records}))

        for r in records:
            for h in r.get("herbs", []):
                herb_freq[h] = herb_freq.get(h, 0) + 1

        chi_square_items: List[Dict[str, Any]] = []

        def _chi2_fallback(a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
            n = a + b + c + d
            num = n * (a * d - b * c) ** 2
            den = (a + b) * (c + d) * (a + c) * (b + d)
            return (float(num / den) if den > 0 else 0.0), None

        for herb in herbs:
            for syndrome in syndrome_values:
                a = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") == syndrome)
                b = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") != syndrome)
                c = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") == syndrome)
                d = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") != syndrome)
                if _HAS_SCIPY and _chi2_contingency is not None:
                    try:
                        chi2_result: Any = _chi2_contingency([[a, b], [c, d]])
                        chi2, p = float(chi2_result[0]), float(chi2_result[1])
                    except Exception:
                        chi2, p = _chi2_fallback(a, b, c, d)
                else:
                    chi2, p = _chi2_fallback(a, b, c, d)
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
        ts_data = context.get("time_series_data")
        if ts_data:
            years = np.array([float(p.get("time")) for p in ts_data])
            values = np.array([float(p.get("value")) for p in ts_data])
        else:
            years = np.array([float(r.get("year") or 0.0) for r in records])
            values = np.array([float(r.get("response", 0.0)) for r in records])

        if len(years) >= 2:
            coeff = np.polyfit(years, values, deg=1)
            slope, intercept = float(coeff[0]), float(coeff[1])
        else:
            slope, intercept = 0.0, float(values[0]) if len(values) else 0.0

        dr_data = context.get("dose_response_data")
        if dr_data:
            doses = np.array([float(p.get("dose")) for p in dr_data])
            responses = np.array([float(p.get("response")) for p in dr_data])
        else:
            doses = np.array([float(r.get("dose_total", 0.0)) for r in records if r.get("dose_total") is not None])
            responses = np.array([float(r.get("response", 0.0)) for r in records if r.get("dose_total") is not None])

        dose_model: Dict[str, Any] = {}
        if len(doses) >= 3:
            try:
                from scipy.optimize import curve_fit

                def hill(x, emax, ec50, h):
                    return emax * (x ** h) / (ec50 ** h + x ** h + 1e-9)

                popt, _ = curve_fit(hill, doses, responses, bounds=(0, [1.5, 200.0, 5.0]), maxfev=20000)
                dose_model = {
                    "model": "hill",
                    "emax": round(float(popt[0]), 4),
                    "ec50": round(float(popt[1]), 4),
                    "hill_coefficient": round(float(popt[2]), 4),
                }
            except Exception:
                c = np.polyfit(doses, responses, deg=1)
                dose_model = {"model": "linear", "slope": round(float(c[0]), 4), "intercept": round(float(c[1]), 4)}
        else:
            dose_model = {"model": "insufficient_data"}

        return {
            "time_series_trend": {
                "slope": round(float(slope), 6),
                "intercept": round(float(intercept), 4),
                "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
            },
            "dose_response": dose_model,
        }

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
