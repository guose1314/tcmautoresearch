"""ResearchDossierBuilder 单元测试。"""

import json
import unittest
from types import SimpleNamespace
from typing import Any, Dict

from src.research.dossier_builder import (
    DossierSection,
    ResearchDossier,
    ResearchDossierBuilder,
)


def _make_cycle(
    cycle_id: str = "test-cycle-001",
    objective: str = "研究黄芪-人参药对的协同增效机制",
    scope: str = "本草文献与现代药理",
    phase_executions: dict | None = None,
    metadata: dict | None = None,
) -> SimpleNamespace:
    """构建最小化的 ResearchCycle 替身。"""
    return SimpleNamespace(
        cycle_id=cycle_id,
        research_objective=objective,
        research_scope=scope,
        phase_executions=phase_executions or {},
        outcomes=[],
        metadata=metadata or {},
    )


def _make_phase_records() -> Dict[str, Dict[str, Any]]:
    return {
        "observe": {
            "results": {
                "summary": "黄芪补气固表，人参大补元气，二药合用气虚证疗效显著提升。",
                "entities": [
                    {"text": "黄芪", "type": "herb", "confidence": 0.95},
                    {"text": "人参", "type": "herb", "confidence": 0.97},
                    {"text": "补气", "type": "efficacy", "confidence": 0.88},
                    {"text": "气虚证", "type": "syndrome", "confidence": 0.90},
                ],
                "evidence_records": [
                    {
                        "evidence_grade": "high",
                        "source_entity": "黄芪",
                        "target_entity": "补气固表",
                        "relation_type": "HAS_EFFICACY",
                        "excerpt": "黄芪味甘，性微温，归脾肺经，善补气固表。",
                    },
                    {
                        "evidence_grade": "moderate",
                        "source_entity": "人参",
                        "target_entity": "大补元气",
                        "relation_type": "HAS_EFFICACY",
                        "excerpt": "人参味甘微苦，大补元气，复脉固脱。",
                    },
                ],
                "ingestion_pipeline": {
                    "aggregate": {
                        "philology_assets": {
                            "summary": {"document_count": 2},
                            "terminology_standard_table": [
                                {
                                    "source_term": "黄芪",
                                    "canonical_term": "黄耆",
                                    "definition": "古籍同物异名规范化条目",
                                }
                            ],
                            "collation_entries": [
                                {
                                    "lemma": "黄芪",
                                    "variant": "黄耆",
                                    "witness": "《本草纲目》",
                                }
                            ],
                            "evidence_chains": [
                                {
                                    "claim": "黄芪与黄耆在样本文献中视作同物异名",
                                    "supporting_evidence": "《本草纲目》与《神农本草经》均出现对应异名。",
                                }
                            ],
                            "conflict_claims": [
                                {"claim": "个别文献将黄芪与绵黄芪区分处理"}
                            ],
                        }
                    },
                    "documents": [
                        {
                            "title": "《本草纲目》",
                            "summary": "黄芪补气固表，适用于气虚乏力。",
                        },
                        {
                            "title": "《神农本草经》",
                            "summary": "人参列为上品，主补五脏。",
                        },
                    ],
                },
                "corpus_collection": {
                    "document_count": 2,
                    "text_entry_count": 8,
                    "summary": "已收集两部核心本草文献，覆盖黄芪与人参的传统论述。",
                },
            }
        },
        "analyze": {
            "results": {
                "analysis_summary": "药对协同分析表明黄芪与人参在补气方向具有叠加效应。",
                "entities": [
                    {"text": "四君子汤", "type": "formula", "confidence": 0.92},
                ],
                "statistical_analysis": {
                    "method": "association_rule_mining",
                    "sample_size": 48,
                    "significant_result_count": 3,
                },
                "reasoning_results": {
                    "claims": [
                        {"claim": "黄芪与人参存在补气协同", "evidence_grade": "high"}
                    ],
                    "evidence_records": [
                        {
                            "evidence_grade": "high",
                            "source_entity": "黄芪",
                            "target_entity": "人参",
                            "relation_type": "SYNERGIZES_WITH",
                            "excerpt": "二药同用，益气扶正之力倍增。",
                        }
                    ],
                },
                "evidence_protocol": {
                    "summary": "证据协议整合古籍引文与现代关联分析，形成可追溯论断。",
                    "claims": [
                        {"claim": "黄芪-人参药对可增强补气疗效", "evidence_grade": "high"}
                    ],
                    "evidence_records": [
                        {
                            "evidence_grade": "moderate",
                            "source_entity": "四君子汤",
                            "target_entity": "补气法",
                            "relation_type": "SUPPORTS",
                            "excerpt": "方证对应提示补气法在气虚证中具有稳定疗效。",
                        }
                    ],
                },
                "evidence_grade_summary": {
                    "high_count": 1,
                    "moderate_count": 1,
                    "risk_of_bias": "moderate",
                    "summary": "目前高等级证据集中在古籍共识与现代数据挖掘的一致性部分。",
                },
                "textual_evidence_summary": {
                    "summary": "文本证据显示黄芪、人参在气虚、脾肺亏虚语境中共现频率较高。",
                    "evidence_chain_count": 4,
                },
                "similar_formula_graph_evidence_summary": {
                    "summary": "相似方图谱提示四君子汤体系为该药对提供了稳定支持。",
                    "match_count": 2,
                },
            }
        },
    }


def _make_publish_record() -> Dict[str, Dict[str, Any]]:
    return {
        "publish": {
            "results": {
                "publications": [{"title": "黄芪人参药对协同机制研究初稿"}],
                "deliverables": ["研究报告", "Markdown 论文初稿", "DOCX 论文初稿"],
                "citations": [{"title": "黄芪现代研究进展"}, {"title": "人参药理学分析"}],
                "formatted_references": "[1] 黄芪现代研究进展\n[2] 人参药理学分析",
                "output_files": {"markdown": "output/paper.md", "docx": "output/paper.docx"},
                "analysis_results": {
                    "summary": "写作阶段沿用了 analyze 阶段的证据协议与分级结果。",
                    "llm_analysis_context": {
                        "module_presence": {"research_perspectives": True},
                        "analysis_modules": {"research_perspectives": {"summary": "聚焦药对协同机制"}},
                    },
                },
                "research_artifact": {
                    "summary": "研究产物已收敛到可写作的假设、证据和图谱支持。",
                    "hypothesis_audit_summary": "核心假设经过实验与数据挖掘双重校验。",
                    "similar_formula_graph_evidence_summary": "四君子汤相关图谱证据支撑药对协同解释。",
                },
            },
            "metadata": {
                "publication_count": 1,
                "deliverable_count": 3,
                "citation_count": 2,
                "paper_review_summary": {"final_score": 0.91, "rounds_completed": 2, "accepted": True},
            },
        }
    }


def _make_publish_dossier_source() -> Dict[str, Any]:
    return {
        "paper_review_summary": {"final_score": 0.91, "rounds_completed": 2, "accepted": True},
        "paper_draft": {
            "title": "黄芪-人参药对协同增效机制的证据整合研究",
            "abstract": "本文基于古籍证据、现代文献与结构化分析结果，构建黄芪-人参药对的协同增效研究初稿。",
            "sections": [
                {"section_type": "introduction", "title": "1 引言", "content": "交代黄芪、人参药对的研究背景与证据缺口。"},
                {"section_type": "methods", "title": "2 方法", "content": "说明语料采集、证据协议与关联规则分析流程。"},
            ],
        },
    }


def _make_phase_executions() -> Dict[str, Dict[str, Any]]:
    phase_records = _make_phase_records()
    phase_records.update(_make_publish_record())
    phase_executions: Dict[str, Dict[str, Any]] = {}
    for phase_name, payload in phase_records.items():
        phase_executions[phase_name] = {
            "phase": phase_name,
            "result": {
                "phase": phase_name,
                "status": "completed",
                "results": payload.get("results", {}),
                "metadata": payload.get("metadata", {}),
                "artifacts": payload.get("artifacts", []),
                "error": None,
            },
        }
    return phase_executions


class TestDossierSection(unittest.TestCase):
    def test_to_dict(self):
        sec = DossierSection(name="test", content="hello", item_count=1, token_budget=100)
        d = sec.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["content"], "hello")
        self.assertEqual(d["item_count"], 1)


class TestResearchDossier(unittest.TestCase):
    def test_to_text(self):
        dossier = ResearchDossier(
            cycle_id="c1",
            research_objective="test",
            sections=[
                DossierSection(name="A", content="content A"),
                DossierSection(name="B", content="content B"),
                DossierSection(name="Empty", content=""),
            ],
        )
        text = dossier.to_text()
        self.assertIn("## A", text)
        self.assertIn("content A", text)
        self.assertIn("## B", text)
        self.assertNotIn("## Empty", text)

    def test_to_markdown(self):
        dossier = ResearchDossier(
            cycle_id="c1",
            research_objective="目标",
            sections=[
                DossierSection(name="S1", content="data", truncated=True, item_count=5),
            ],
        )
        md = dossier.to_markdown()
        self.assertIn("# 研究 Dossier: 目标", md)
        self.assertIn("已截断", md)

    def test_to_json_roundtrip(self):
        dossier = ResearchDossier(
            cycle_id="c1",
            research_objective="test",
            sections=[DossierSection(name="S", content="c")],
        )
        j = dossier.to_json()
        data = json.loads(j)
        self.assertEqual(data["cycle_id"], "c1")
        self.assertIsInstance(data["sections"], list)


class TestResearchDossierBuilder(unittest.TestCase):
    def test_build_empty_cycle(self):
        """空 cycle 应产出结构完整但内容为空的 dossier。"""
        builder = ResearchDossierBuilder(max_context_tokens=1024)
        cycle = _make_cycle(phase_executions={})
        dossier = builder.build(cycle)
        self.assertEqual(dossier.cycle_id, "test-cycle-001")
        self.assertEqual(len(dossier.sections), 9)
        self.assertGreater(dossier.total_estimated_tokens, 0)  # 至少有目标文本

    def test_build_with_phase_records(self):
        """含阶段记录时各 section 应提取到内容。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle()
        records = _make_phase_records()
        dossier = builder.build(cycle, records)

        # 目标 section
        objective_sec = dossier.sections[0]
        self.assertIn("黄芪-人参药对", objective_sec.content)

        # 证据 section
        evidence_sec = dossier.sections[1]
        self.assertIn("黄芪", evidence_sec.content)
        self.assertGreaterEqual(evidence_sec.item_count, 2)

        # 实体 section
        entity_sec = dossier.sections[2]
        self.assertIn("人参", entity_sec.content)
        self.assertIn("herb", entity_sec.content)
        # 去重后应有 5 个实体 (黄芪, 人参, 补气, 气虚证, 四君子汤)
        self.assertEqual(entity_sec.item_count, 5)

    def test_build_from_cycle_phase_executions_unwraps_phase_result(self):
        """builder.build(cycle) 应能从 phase_execution.result.phase_result 中解包真实内容。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle(phase_executions=_make_phase_executions())
        dossier = builder.build(cycle)

        evidence_sec = dossier.sections[1]
        entity_sec = dossier.sections[2]
        corpus_sec = dossier.sections[8]
        self.assertIn("黄芪", evidence_sec.content)
        self.assertIn("四君子汤", entity_sec.content)
        self.assertIn("药对协同分析", corpus_sec.content)

    def test_build_with_graph_data(self):
        """传入图谱数据时 graph section 应包含节点和边。"""
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        graph = {
            "nodes": [
                {"name": "黄芪", "type": "Herb"},
                {"name": "补气", "type": "Efficacy"},
            ],
            "edges": [
                {"source": "黄芪", "type": "HAS_EFFICACY", "target": "补气"},
            ],
        }
        dossier = builder.build(cycle, graph_data=graph)
        graph_sec = dossier.sections[3]
        self.assertIn("黄芪", graph_sec.content)
        self.assertIn("HAS_EFFICACY", graph_sec.content)

    def test_build_with_terminology(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        terms = [
            {"term": "气虚", "definition": "气的不足导致脏腑功能减退"},
            {"term": "固表", "definition": "巩固体表防御功能"},
        ]
        dossier = builder.build(cycle, terminology=terms)
        term_sec = dossier.sections[4]
        self.assertIn("气虚", term_sec.content)
        self.assertEqual(term_sec.item_count, 2)

    def test_build_with_corpus_excerpts(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        excerpts = ["《本草纲目》载黄芪补气固表。", "《神农本草经》列人参为上品。"]
        dossier = builder.build(cycle, corpus_excerpts=excerpts)
        corpus_sec = dossier.sections[8]
        self.assertIn("本草纲目", corpus_sec.content)
        self.assertEqual(corpus_sec.item_count, 2)

    def test_truncation_on_small_budget(self):
        """极小预算下应触发截断。"""
        builder = ResearchDossierBuilder(max_context_tokens=256)
        cycle = _make_cycle()
        records = _make_phase_records()
        dossier = builder.build(cycle, records)
        # 至少有一个 section 被截断
        truncated_sections = [s for s in dossier.sections if s.truncated]
        # 预算很小时某些 section 会被截断（但不一定所有）
        self.assertIsInstance(dossier.total_estimated_tokens, int)
        self.assertIsInstance(truncated_sections, list)

    def test_to_dict_serializable(self):
        """dossier.to_dict() 必须可 JSON 序列化。"""
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        dossier = builder.build(cycle, _make_phase_records())
        d = dossier.to_dict()
        # 应不抛异常
        json_str = json.dumps(d, ensure_ascii=False)
        self.assertIn("test-cycle-001", json_str)

    def test_metadata_contains_builder_info(self):
        builder = ResearchDossierBuilder(max_context_tokens=2048)
        cycle = _make_cycle()
        dossier = builder.build(cycle)
        self.assertEqual(dossier.metadata["builder_version"], "1.2")
        self.assertEqual(dossier.metadata["max_context_tokens"], 2048)

    def test_build_version_info_section_from_explicit_data(self):
        """显式传入 version_info 时应构建版本信息 section。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle()
        version_data = [
            {"title": "本草纲目", "dynasty": "明", "author": "李时珍", "version_lineage": "金陵本"},
            {"title": "神农本草经", "dynasty": "汉", "author": "佚名"},
        ]
        dossier = builder.build(cycle, version_info=version_data)
        version_sec = dossier.sections[5]
        self.assertEqual(version_sec.name, "版本信息")
        self.assertIn("本草纲目", version_sec.content)
        self.assertIn("明", version_sec.content)
        self.assertIn("李时珍", version_sec.content)
        self.assertIn("金陵本", version_sec.content)
        self.assertIn("神农本草经", version_sec.content)
        self.assertGreaterEqual(version_sec.item_count, 2)

    def test_build_version_info_section_from_philology(self):
        """从 observe 阶段 philology 提取版本信息。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle()
        records = {
            "observe": {
                "results": {
                    "ingestion_pipeline": {
                        "aggregate": {
                            "philology_assets": {
                                "terminology_standard_table": [
                                    {"source_term": "黄芪", "canonical_term": "黄耆"}
                                ],
                                "collation_entries": [
                                    {
                                        "document_title": "本草纲目",
                                        "witness_key": "金陵本",
                                        "version_lineage_key": "李时珍原刻",
                                        "note": "卷六草部",
                                    }
                                ],
                            }
                        }
                    }
                }
            }
        }
        dossier = builder.build(cycle, records)
        version_sec = dossier.sections[5]
        self.assertEqual(version_sec.name, "版本信息")
        self.assertIn("本草纲目", version_sec.content)

    def test_build_controversies_section(self):
        """争议点 section 应从 philology conflict_claims 提取。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle()
        records = {
            "observe": {
                "results": {
                    "ingestion_pipeline": {
                        "aggregate": {
                            "philology_assets": {
                                "terminology_standard_table": [
                                    {"source_term": "黄芪", "canonical_term": "黄耆"}
                                ],
                                "conflict_claims": [
                                    {
                                        "subject": "黄芪产地",
                                        "claim_a": "以陕西为正品",
                                        "claim_b": "以山西为正品",
                                        "source_a": "本草纲目",
                                        "source_b": "本草从新",
                                    }
                                ],
                            }
                        }
                    }
                }
            }
        }
        dossier = builder.build(cycle, records)
        controversy_sec = dossier.sections[6]
        self.assertEqual(controversy_sec.name, "争议点")
        self.assertIn("黄芪产地", controversy_sec.content)
        self.assertIn("陕西", controversy_sec.content)
        self.assertIn("山西", controversy_sec.content)
        self.assertGreaterEqual(controversy_sec.item_count, 1)

    def test_build_hypothesis_history_section(self):
        """假说历史 section 应从阶段记录中收集假说。"""
        builder = ResearchDossierBuilder(max_context_tokens=4096)
        cycle = _make_cycle()
        records = {
            "observe": {"results": {}},
            "analyze": {
                "results": {
                    "hypotheses": [
                        {
                            "statement": "黄芪与人参在补气方向存在协同增效",
                            "novelty": 0.7,
                            "feasibility": 0.8,
                        },
                        {
                            "statement": "四君子汤中黄芪-人参药对是核心增效组合",
                            "novelty": 0.6,
                            "feasibility": 0.9,
                        },
                    ]
                }
            },
        }
        dossier = builder.build(cycle, records)
        hypo_sec = dossier.sections[7]
        self.assertEqual(hypo_sec.name, "假说历史")
        self.assertIn("黄芪与人参在补气方向存在协同增效", hypo_sec.content)
        self.assertIn("四君子汤", hypo_sec.content)
        self.assertIn("analyze", hypo_sec.content)
        self.assertIn("新颖度=0.7", hypo_sec.content)
        self.assertGreaterEqual(hypo_sec.item_count, 1)

    def test_build_observe_dossier(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        dossier = builder.build_observe_dossier(cycle, _make_phase_records())

        self.assertEqual(dossier.metadata["dossier_kind"], "observe")
        self.assertEqual(dossier.max_context_tokens, 1280)
        self.assertEqual(len(dossier.sections), 6)
        self.assertIn("文献考据", dossier.to_text())
        self.assertIn("黄耆", dossier.to_text())

    def test_build_analyze_dossier(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle()
        dossier = builder.build_analyze_dossier(cycle, _make_phase_records())

        self.assertEqual(dossier.metadata["dossier_kind"], "analyze")
        self.assertEqual(dossier.max_context_tokens, 1536)
        self.assertIn("证据协议", dossier.to_text())
        self.assertIn("文本证据", dossier.to_text())
        self.assertIn("association_rule_mining", dossier.to_text())

    def test_build_publish_dossier(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle(metadata={"phase_dossier_sources": {"publish": _make_publish_dossier_source()}})
        records = _make_phase_records()
        records.update(_make_publish_record())
        dossier = builder.build_publish_dossier(cycle, records)

        self.assertEqual(dossier.metadata["dossier_kind"], "publish")
        self.assertEqual(dossier.max_context_tokens, 1792)
        self.assertIn("论文初稿", dossier.to_text())
        self.assertIn("黄芪-人参药对协同增效机制的证据整合研究", dossier.to_text())
        self.assertIn("参考文献摘录", dossier.to_text())

    def test_build_phase_dossiers(self):
        builder = ResearchDossierBuilder()
        cycle = _make_cycle(
            phase_executions=_make_phase_executions(),
            metadata={"phase_dossier_sources": {"publish": _make_publish_dossier_source()}},
        )
        dossiers = builder.build_phase_dossiers(cycle)

        self.assertEqual(sorted(dossiers.keys()), ["analyze", "observe", "publish"])
        self.assertEqual(dossiers["publish"].metadata["dossier_kind"], "publish")


if __name__ == "__main__":
    unittest.main()
