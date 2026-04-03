"""古典文献数字化与知识考古 - Classical Literature Archaeology"""

from typing import Any, Dict, List


class ClassicalLiteratureArchaeologyAnalyzer:
    """古典文献数字化与知识考古分析器"""

    FORMULA_ARCHIVE: Dict[str, Dict[str, Any]] = {
        "补中益气汤": {
            "first_source": "脾胃论",
            "dynasty": "金元",
            "author": "李东垣",
            "variant_names": ["补中汤", "益气升阳汤"],
            "core_indications": ["中气下陷", "气虚发热", "体倦乏力"],
            "evolution_notes": [
                "明清时期强化升阳举陷用于久泻脱肛",
                "近现代扩展至免疫低下与术后康复场景",
            ],
        },
        "四君子汤": {
            "first_source": "太平惠民和剂局方",
            "dynasty": "宋",
            "author": "官修",
            "variant_names": ["四味健脾汤"],
            "core_indications": ["脾胃气虚", "纳呆便溏"],
            "evolution_notes": [
                "作为补气基础方衍生六君子汤、香砂六君子汤",
            ],
        },
    }

    @classmethod
    def analyze_formula_knowledge_archaeology(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """输出方剂在古典文献中的源流、异名与知识演化信息"""
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
            "knowledge_graph": {
                "nodes": citation_nodes,
                "edges": citation_edges,
            },
            "herb_mention_count": len(herbs),
        }
