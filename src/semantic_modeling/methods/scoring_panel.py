"""统一评分面板 - Unified Scoring Panel (8 Dimensions)"""

from typing import Any, Dict, List


class ResearchScoringPanel:
    """将8个研究维度映射为0-1标准化评分并给出总分/置信区间"""

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "structure": 0.12,
        "properties": 0.12,
        "comparison": 0.10,
        "pharmacology": 0.14,
        "network": 0.14,
        "supramolecular": 0.12,
        "archaeology": 0.13,
        "complexity": 0.13,
    }

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @classmethod
    def _score_structure(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        herb_count = min(1.0, data.get("herb_count", 0) / 10.0)
        role = data.get("role_distribution", {})
        nonzero_roles = sum(1 for k in ["sovereign_ratio", "minister_ratio", "assistant_ratio", "envoy_ratio"] if role.get(k, 0) > 0)
        role_coverage = nonzero_roles / 4.0
        pairing = min(1.0, len(data.get("pairing_rules", [])) / 4.0)
        return cls._clamp01(0.45 * herb_count + 0.30 * role_coverage + 0.25 * pairing)

    @classmethod
    def _score_properties(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        n = len(data)
        if n == 0:
            return 0.0
        complete = 0
        for item in data.values():
            if item.get("temperature") and item.get("flavors") and item.get("meridians"):
                complete += 1
        return cls._clamp01(complete / n)

    @classmethod
    def _score_comparison(cls, data: List[Any], similar_formulas: List[str]) -> float:
        c1 = min(1.0, len(data or []) / 3.0)
        c2 = min(1.0, len(similar_formulas or []) / 3.0)
        return cls._clamp01(0.6 * c1 + 0.4 * c2)

    @classmethod
    def _score_pharmacology(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        herb_scores: List[float] = []
        for _, item in data.items():
            comp = min(1.0, len(item.get("components", {})) / 4.0)
            eff = min(1.0, len(item.get("efficacy", {})) / 4.0)
            safety = 1.0 if item.get("safety", {}).get("adverse_effects") is not None else 0.0
            herb_scores.append(0.45 * comp + 0.40 * eff + 0.15 * safety)
        return cls._clamp01(sum(herb_scores) / len(herb_scores)) if herb_scores else 0.0

    @classmethod
    def _score_network(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        target = min(1.0, data.get("target_count", 0) / 20.0)
        key_t = min(1.0, len(data.get("key_targets", [])) / 8.0)
        path = min(1.0, len(data.get("enriched_pathways", [])) / 8.0)
        return cls._clamp01(0.4 * target + 0.3 * key_t + 0.3 * path)

    @classmethod
    def _score_supramolecular(cls, data: Dict[str, Any]) -> float:
        if not data or not data.get("available"):
            return 0.0
        score = data.get("supramolecular_synergy_score", 0.0)
        return cls._clamp01(score)

    @classmethod
    def _score_archaeology(cls, data: Dict[str, Any]) -> float:
        if not data or not data.get("available"):
            return 0.0
        origin = 1.0 if data.get("origin", {}).get("source") else 0.0
        evo = min(1.0, len(data.get("evolution_notes", [])) / 3.0)
        nodes = min(1.0, len(data.get("knowledge_graph", {}).get("nodes", [])) / 4.0)
        return cls._clamp01(0.35 * origin + 0.35 * evo + 0.30 * nodes)

    @classmethod
    def _score_complexity(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        return cls._clamp01(data.get("complexity_score", 0.0))

    @classmethod
    def _ci95_from_dimension_scores(cls, scores: Dict[str, float]) -> Dict[str, float]:
        values = list(scores.values())
        n = len(values)
        if n == 0:
            return {"mean": 0.0, "lower": 0.0, "upper": 0.0, "margin": 0.0}
        mean = sum(values) / n
        if n == 1:
            return {"mean": round(mean, 4), "lower": round(mean, 4), "upper": round(mean, 4), "margin": 0.0}
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        se = (var ** 0.5) / (n ** 0.5)
        margin = 1.96 * se
        lower = cls._clamp01(mean - margin)
        upper = cls._clamp01(mean + margin)
        return {
            "mean": round(mean, 4),
            "lower": round(lower, 4),
            "upper": round(upper, 4),
            "margin": round(margin, 4),
        }

    @classmethod
    def score_research_perspective(
        cls,
        perspective: Dict[str, Any],
        formula_comparisons: List[Dict[str, Any]] | None = None,
        weights: Dict[str, float] | None = None,
    ) -> Dict[str, Any]:
        """对单个方剂研究视角进行统一评分"""
        weights = weights or cls.DEFAULT_WEIGHTS

        dim_scores = {
            "structure": cls._score_structure(perspective.get("structure_analysis", {})),
            "properties": cls._score_properties(perspective.get("component_properties", {})),
            "comparison": cls._score_comparison(formula_comparisons or [], perspective.get("similar_formulas", [])),
            "pharmacology": cls._score_pharmacology(perspective.get("pharmacological_profile", {})),
            "network": cls._score_network(perspective.get("network_pharmacology", {})),
            "supramolecular": cls._score_supramolecular(perspective.get("supramolecular_physicochemical", {})),
            "archaeology": cls._score_archaeology(perspective.get("knowledge_archaeology", {})),
            "complexity": cls._score_complexity(perspective.get("complexity_dynamics", {})),
        }

        weighted_total = 0.0
        weight_sum = 0.0
        for key, score in dim_scores.items():
            w = weights.get(key, 0.0)
            weighted_total += w * score
            weight_sum += w
        total_score = cls._clamp01(weighted_total / weight_sum) if weight_sum > 0 else 0.0

        ci95 = cls._ci95_from_dimension_scores(dim_scores)
        ranked = sorted(dim_scores.items(), key=lambda x: x[1], reverse=True)

        return {
            "formula_name": perspective.get("formula_name"),
            "dimension_scores": {k: round(v, 4) for k, v in dim_scores.items()},
            "weights": weights,
            "total_score": round(total_score, 4),
            "confidence_interval_95": ci95,
            "strengths": [name for name, _ in ranked[:3]],
            "gaps": [name for name, _ in ranked[-3:]],
            "paper_paragraph_inputs": {
                "headline": f"该方多维研究综合评分为 {round(total_score, 3)}（95%CI {ci95['lower']}-{ci95['upper']}）",
                "method_summary": [
                    f"结构维度={round(dim_scores['structure'],3)}",
                    f"网络药理维度={round(dim_scores['network'],3)}",
                    f"复杂动力学维度={round(dim_scores['complexity'],3)}",
                ],
                "evidence_summary": [
                    f"关键靶点数={perspective.get('network_pharmacology', {}).get('target_count', 0)}",
                    f"文献源流可追溯={bool(perspective.get('knowledge_archaeology', {}).get('origin'))}",
                    f"超分子协同分={perspective.get('supramolecular_physicochemical', {}).get('supramolecular_synergy_score', 0)}",
                ],
            },
        }
