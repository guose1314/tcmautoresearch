"""网络药理学与系统生物学分析。"""

from typing import Any, Dict, List

from src.data.knowledge_base import load_herb_targets, load_target_pathways


class NetworkPharmacologySystemBiologyAnalyzer:
    """网络药理学与系统生物学分析器。"""

    HERB_TARGET_MAP: Dict[str, List[str]] = load_herb_targets()

    TARGET_PATHWAY_MAP: Dict[str, List[str]] = load_target_pathways()

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
