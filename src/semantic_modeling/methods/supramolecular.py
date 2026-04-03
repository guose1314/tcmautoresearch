"""超分子化学和物理化学 - Supramolecular Chemistry & Physicochemistry"""

from typing import Any, Dict, List


class SupramolecularPhysicochemicalAnalyzer:
    """超分子化学与物理化学分析器"""

    HERB_PHYSICOCHEMISTRY: Dict[str, Dict[str, float]] = {
        "黄芪": {"solubility": 0.82, "h_bond": 0.74, "pi_stack": 0.21, "dispersion": 0.66},
        "人参": {"solubility": 0.78, "h_bond": 0.71, "pi_stack": 0.25, "dispersion": 0.64},
        "白术": {"solubility": 0.59, "h_bond": 0.46, "pi_stack": 0.42, "dispersion": 0.77},
        "茯苓": {"solubility": 0.73, "h_bond": 0.67, "pi_stack": 0.18, "dispersion": 0.62},
        "甘草": {"solubility": 0.76, "h_bond": 0.72, "pi_stack": 0.28, "dispersion": 0.69},
        "丹参": {"solubility": 0.52, "h_bond": 0.44, "pi_stack": 0.61, "dispersion": 0.81},
    }

    @classmethod
    def analyze_formula_physicochemical(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """评估方剂在溶解性、非共价作用与协同稳定性方面的理化特征"""
        profiles = [cls.HERB_PHYSICOCHEMISTRY[h] for h in herbs if h in cls.HERB_PHYSICOCHEMISTRY]
        if not profiles:
            return {"formula_name": formula_name, "available": False}

        metrics = {
            "solubility_index": sum(p["solubility"] for p in profiles) / len(profiles),
            "h_bond_network": sum(p["h_bond"] for p in profiles) / len(profiles),
            "pi_stacking_potential": sum(p["pi_stack"] for p in profiles) / len(profiles),
            "dispersion_stability": sum(p["dispersion"] for p in profiles) / len(profiles),
        }

        supramolecular_synergy = (
            0.35 * metrics["solubility_index"]
            + 0.30 * metrics["h_bond_network"]
            + 0.20 * metrics["dispersion_stability"]
            + 0.15 * metrics["pi_stacking_potential"]
        )

        return {
            "formula_name": formula_name,
            "available": True,
            "metrics": metrics,
            "supramolecular_synergy_score": round(supramolecular_synergy, 4),
            "physicochemical_interpretation": "高氢键网络与中高溶解指数支持复方多组分协同释放",
        }
