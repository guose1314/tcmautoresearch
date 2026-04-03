"""古典文献数字化与知识考古分析。"""

from typing import Any, Dict, List

from src.data.knowledge_base import load_formula_archive


class ClassicalLiteratureArchaeologyAnalyzer:
    """古典文献数字化与知识考古分析器。"""

    FORMULA_ARCHIVE: Dict[str, Dict[str, Any]] = load_formula_archive()

    @classmethod
    def analyze_formula_knowledge_archaeology(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        archive = cls.FORMULA_ARCHIVE.get(formula_name, {})
        if not archive:
            return {
                "formula_name": formula_name,
                "available": False,
                "digitization_status": "待补充文献语料",
            }

        citation_nodes = [archive.get("first_source")] + archive.get("variant_names", [])
        citation_edges = [
            {"from": archive.get("first_source"), "to": variant, "type": "name_evolution"}
            for variant in archive.get("variant_names", [])
        ]

        return {
            "formula_name": formula_name,
            "available": True,
            "origin": {
                "source": archive.get("first_source"),
                "dynasty": archive.get("dynasty"),
                "author": archive.get("author"),
            },
            "indications": archive.get("core_indications", []),
            "evolution_notes": archive.get("evolution_notes", []),
            "knowledge_graph": {"nodes": citation_nodes, "edges": citation_edges},
            "herb_mention_count": len(herbs),
        }
