"""复杂性科学与非线性动力学分析。"""

from typing import Any, Dict, List


class ComplexityNonlinearDynamicsAnalyzer:
    """复杂性科学与非线性动力学分析器。"""

    FORMULA_DYNAMIC_PRIOR: Dict[str, Dict[str, float]] = {
        "补中益气汤": {"stability": 0.79, "adaptivity": 0.74, "feedback_gain": 0.63},
        "四君子汤": {"stability": 0.72, "adaptivity": 0.61, "feedback_gain": 0.52},
        "六君子汤": {"stability": 0.75, "adaptivity": 0.66, "feedback_gain": 0.57},
    }

    @classmethod
    def analyze_formula_complexity_dynamics(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        prior = cls.FORMULA_DYNAMIC_PRIOR.get(
            formula_name,
            {"stability": 0.60, "adaptivity": 0.58, "feedback_gain": 0.50},
        )
        herb_factor = min(1.0, 0.08 * len(herbs))
        resilience_index = round(0.6 * prior["stability"] + 0.4 * herb_factor, 4)
        nonlinear_response = round(prior["adaptivity"] * (1 + 0.2 * prior["feedback_gain"]), 4)
        complexity_score = round((resilience_index + nonlinear_response + prior["feedback_gain"]) / 3, 4)

        regime = "稳定吸引子"
        if complexity_score >= 0.78:
            regime = "高鲁棒吸引子"
        elif complexity_score < 0.58:
            regime = "临界波动区"

        return {
            "formula_name": formula_name,
            "stability": prior["stability"],
            "adaptivity": prior["adaptivity"],
            "feedback_gain": prior["feedback_gain"],
            "resilience_index": resilience_index,
            "nonlinear_response": nonlinear_response,
            "complexity_score": complexity_score,
            "dynamic_regime": regime,
            "interpretation": "复方通过多节点反馈抑制波动并促进稳态恢复",
        }
