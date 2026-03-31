"""网络药理学与系统生物学分析。"""

from typing import Any, Dict, List


class NetworkPharmacologySystemBiologyAnalyzer:
    """网络药理学与系统生物学分析器。"""

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
