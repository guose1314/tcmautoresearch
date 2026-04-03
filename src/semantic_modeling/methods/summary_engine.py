"""总结分析引擎 - Summary Analysis Engine"""

import copy
import json
from typing import Any, Dict, List, Tuple

import networkx as nx
import numpy as np

from .formula_structure import FormulaStructureAnalyzer
from .pharmacology import ModernPharmacologyDatabase


class SummaryAnalysisEngine:
    """总结分析：频率/卡方、关联规则、复杂网络、聚类与因子、强化剂量、隐结构、时间序列剂量反应、贝叶斯网络"""

    _freq_chi_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _association_cache: Dict[str, Dict[str, Any]] = {}
    _network_cache: Dict[str, Dict[str, Any]] = {}
    _cluster_factor_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _reinforced_dosage_cache: Dict[str, Dict[str, Any]] = {}
    _latent_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _time_dose_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    _bayes_cache: Dict[str, Dict[str, Any]] = {}

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

    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        """稳定序列化签名，用于细粒度缓存键。"""
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return repr(value)

    @classmethod
    def analyze(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        records = context.get("summary_formula_records") or cls.DEFAULT_FORMULA_RECORDS
        transactions = [r.get("herbs", []) for r in records]
        herbs = sorted(list({h for t in transactions for h in t}))

        records_fp = cls._fingerprint(records)
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

        return {
            "frequency_chi_square": copy.deepcopy(cls._freq_chi_cache[freq_key]),
            "association_rules": copy.deepcopy(cls._association_cache[assoc_key]),
            "complex_network": copy.deepcopy(cls._network_cache[network_key]),
            "clustering_factor": copy.deepcopy(cls._cluster_factor_cache[cluster_key]),
            "reinforced_dosage": copy.deepcopy(cls._reinforced_dosage_cache[reinforced_key]),
            "latent_structure": copy.deepcopy(cls._latent_cache[latent_key]),
            "time_series_dose_response": copy.deepcopy(cls._time_dose_cache[time_dose_key]),
            "bayesian_network": copy.deepcopy(cls._bayes_cache[bayes_key]),
        }

    @classmethod
    def _frequency_and_chi_square(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        herb_freq: Dict[str, int] = {h: 0 for h in herbs}
        syndrome_values = sorted(list({r.get("syndrome", "unknown") for r in records}))

        for r in records:
            for h in r.get("herbs", []):
                herb_freq[h] = herb_freq.get(h, 0) + 1

        chi_square_items: List[Dict[str, Any]] = []
        try:
            from scipy.stats import chi2_contingency

            def calc(a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
                chi2, p, _, _ = chi2_contingency([[a, b], [c, d]])
                return float(chi2), float(p)

        except Exception:
            def calc(a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
                n = a + b + c + d
                num = n * (a * d - b * c) ** 2
                den = (a + b) * (c + d) * (a + c) * (b + d)
                chi2 = float(num / den) if den > 0 else 0.0
                return chi2, None

        for herb in herbs:
            for syndrome in syndrome_values:
                a = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") == syndrome)
                b = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") != syndrome)
                c = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") == syndrome)
                d = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") != syndrome)
                try:
                    chi2, p = calc(a, b, c, d)
                except Exception:
                    n = a + b + c + d
                    num = n * (a * d - b * c) ** 2
                    den = (a + b) * (c + d) * (a + c) * (b + d)
                    chi2 = float(num / den) if den > 0 else 0.0
                    p = None
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
    def _association_rules(cls, transactions: List[List[str]]) -> Dict[str, Any]:
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
    def _complex_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            from networkx.algorithms.community import greedy_modularity_communities
            comms = greedy_modularity_communities(herb_graph)
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
    def _clustering_and_factor_analysis(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        if not records or not herbs:
            return {"clusters": [], "factors": []}

        X = np.array([[1.0 if h in r.get("herbs", []) else 0.0 for h in herbs] for r in records])
        clusters_out: List[Dict[str, Any]] = []
        factors_out: List[Dict[str, Any]] = []

        try:
            from sklearn.cluster import KMeans
            n_clusters = min(3, len(records))
            model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
            labels = model.fit_predict(X)
            for i, label in enumerate(labels):
                clusters_out.append(
                    {
                        "formula": records[i].get("formula"),
                        "cluster": int(label),
                    }
                )
        except Exception:
            clusters_out = [{"formula": r.get("formula"), "cluster": 0} for r in records]

        try:
            from sklearn.decomposition import FactorAnalysis
            n_components = min(2, X.shape[1], X.shape[0])
            fa = FactorAnalysis(n_components=n_components, random_state=42)
            fa.fit(X)
            loadings = fa.components_
            for idx, comp in enumerate(loadings):
                pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                factors_out.append(
                    {
                        "factor": idx,
                        "top_herbs": [{"herb": h, "loading": round(v, 4)} for h, v in pairs[:5]],
                    }
                )
        except Exception:
            _, _, vt = np.linalg.svd(X, full_matrices=False)
            if vt.size > 0:
                for idx in range(min(2, vt.shape[0])):
                    comp = vt[idx]
                    pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                    factors_out.append(
                        {
                            "factor": idx,
                            "top_herbs": [{"herb": h, "loading": round(v, 4)} for h, v in pairs[:5]],
                        }
                    )

        return {"clusters": clusters_out, "factors": factors_out}

    @classmethod
    def _reinforced_dosage_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """基于强化更新策略的剂量分析（轻量近似）"""
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
        if not records or not herbs:
            return {"topics": []}
        X = np.array([[1.0 if h in r.get("herbs", []) else 0.0 for h in herbs] for r in records])

        topics: List[Dict[str, Any]] = []
        try:
            from sklearn.decomposition import LatentDirichletAllocation
            n_comp = min(2, max(1, X.shape[0]))
            lda = LatentDirichletAllocation(n_components=n_comp, random_state=42)
            lda.fit(X)
            comps = lda.components_
            for i, comp in enumerate(comps):
                pairs = sorted([(herbs[j], float(comp[j])) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                topics.append(
                    {
                        "topic": i,
                        "top_herbs": [{"herb": h, "weight": round(w, 4)} for h, w in pairs[:5]],
                    }
                )
        except Exception:
            _, _, vt = np.linalg.svd(X, full_matrices=False)
            for i in range(min(2, vt.shape[0])):
                comp = vt[i]
                pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                topics.append(
                    {
                        "topic": i,
                        "top_herbs": [{"herb": h, "weight": round(w, 4)} for h, w in pairs[:5]],
                    }
                )

        return {"topics": topics}

    @classmethod
    def _time_series_and_dose_response(cls, records: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        ts_data = context.get("time_series_data")
        if ts_data:
            years = np.array([float(p.get("time")) for p in ts_data])
            values = np.array([float(p.get("value")) for p in ts_data])
        else:
            years = np.array([float(r.get("year")) for r in records])
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
    def _bayesian_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
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
