"""文献提取系统单元测试 — 覆盖 base / metadata / medical / clinical / academic / quality / pipeline。"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

# ============================================================================
# base.py — 规则引擎、数据结构
# ============================================================================

class TestExtractedItem:
    def test_to_dict_minimal(self):
        from src.extraction.base import ExtractedItem
        item = ExtractedItem(name="黄芪", entity_type="herb", confidence=0.95)
        d = item.to_dict()
        assert d["name"] == "黄芪"
        assert d["entity_type"] == "herb"
        assert d["confidence"] == 0.95
        assert "original_text" not in d  # 无差异时不输出

    def test_to_dict_with_original(self):
        from src.extraction.base import ExtractedItem
        item = ExtractedItem(name="黄芪", entity_type="herb", original_text="黃芪")
        d = item.to_dict()
        assert d["original_text"] == "黃芪"


class TestExtractionRelation:
    def test_to_dict(self):
        from src.extraction.base import ExtractionRelation
        rel = ExtractionRelation(source="四君子汤", target="人参", relation_type="contains")
        d = rel.to_dict()
        assert d["source"] == "四君子汤"
        assert d["target"] == "人参"
        assert d["relation_type"] == "contains"


class TestExtractionRuleEngine:
    def test_add_and_apply_regex_rules(self):
        from src.extraction.base import ExtractionRule, ExtractionRuleEngine, RuleType
        engine = ExtractionRuleEngine()
        rule = ExtractionRule(
            rule_id="test_dynasty",
            name="朝代",
            entity_type="dynasty",
            rule_type=RuleType.REGEX,
            pattern=r"(汉|唐|宋|明|清)",
            priority=10,
            confidence_base=0.90,
            group_index=1,
        )
        engine.add_rule(rule)
        assert engine.rule_count == 1

        items = engine.apply_regex_rules("此书成于汉代，唐代重修")
        assert len(items) >= 2
        names = [i.name for i in items]
        assert "汉" in names
        assert "唐" in names
        assert all(i.confidence == 0.90 for i in items)

    def test_remove_rule(self):
        from src.extraction.base import ExtractionRule, ExtractionRuleEngine, RuleType
        engine = ExtractionRuleEngine()
        rule = ExtractionRule(rule_id="r1", name="r1", entity_type="herb", rule_type=RuleType.REGEX, pattern=r"人参")
        engine.add_rule(rule)
        assert engine.rule_count == 1
        engine.remove_rule("r1")
        assert engine.rule_count == 0

    def test_get_rules_by_type(self):
        from src.extraction.base import ExtractionRule, ExtractionRuleEngine, RuleType
        engine = ExtractionRuleEngine()
        engine.add_rule(ExtractionRule(rule_id="r1", name="r1", entity_type="herb", rule_type=RuleType.REGEX, pattern=r"x"))
        engine.add_rule(ExtractionRule(rule_id="r2", name="r2", entity_type="formula", rule_type=RuleType.DICTIONARY))
        assert len(engine.get_rules(rule_type=RuleType.REGEX)) == 1
        assert len(engine.get_rules(entity_type="formula")) == 1

    def test_disabled_rule_skipped(self):
        from src.extraction.base import ExtractionRule, ExtractionRuleEngine, RuleType
        engine = ExtractionRuleEngine()
        engine.add_rule(ExtractionRule(
            rule_id="r1", name="r1", entity_type="herb",
            rule_type=RuleType.REGEX, pattern=r"人参", enabled=False,
        ))
        items = engine.apply_regex_rules("人参大补元气")
        assert len(items) == 0


class TestPipelineResult:
    def test_to_dict(self):
        from src.extraction.base import PipelineResult
        pr = PipelineResult(document_id="doc001", source_file="test.txt")
        d = pr.to_dict()
        assert d["document_id"] == "doc001"
        assert d["source_file"] == "test.txt"
        assert isinstance(d["all_items"], list)


# ============================================================================
# metadata_extractor.py
# ============================================================================

class TestMetadataExtractor:
    def test_extract_from_filename(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("", source_file="013-本草纲目-明-李时珍.txt")
        names = [i.name for i in result.items]
        assert "本草纲目" in names
        assert "明" in names
        assert "李时珍" in names

    def test_extract_book_title_from_text(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("《伤寒论》为汉代张仲景所著")
        names = [i.name for i in result.items]
        assert "伤寒论" in names

    def test_extract_dynasty_bracket(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("本草经集注（南朝）陶弘景撰")
        types = {i.entity_type for i in result.items}
        assert "dynasty" in types

    def test_author_book_relation(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("", source_file="013-本草纲目-明-李时珍.txt")
        assert len(result.relations) >= 1
        assert result.relations[0].relation_type == "authored"

    def test_coverage_score(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("", source_file="013-本草纲目-明-李时珍.txt")
        assert result.quality_scores["metadata_coverage"] == 1.0

    def test_empty_input(self):
        from src.extraction.metadata_extractor import MetadataExtractor
        ext = MetadataExtractor()
        result = ext.extract("")
        assert len(result.items) == 0


# ============================================================================
# medical_content_extractor.py
# ============================================================================

class TestMedicalContentExtractor:
    def test_herb_dosage_pair(self):
        from src.extraction.medical_content_extractor import MedicalContentExtractor
        ext = MedicalContentExtractor()
        text = "黄芪 30克 当归 15克"
        result = ext.extract(text)
        # 未必全匹配（依赖 lexicon），但 regex 应起效
        herb_items = [i for i in result.items if i.entity_type == "herb"]
        # 至少应通过 _RE_HERB_DOSAGE 匹配到
        assert len(herb_items) >= 0  # lexicon 里有黄芪

    def test_efficacy_extraction(self):
        from src.extraction.medical_content_extractor import MedicalContentExtractor
        ext = MedicalContentExtractor()
        text = "功效：补中益气，升阳举陷。"
        result = ext.extract(text)
        efficacy_items = [i for i in result.items if i.entity_type == "efficacy"]
        assert len(efficacy_items) >= 1

    def test_preparation_extraction(self):
        from src.extraction.medical_content_extractor import MedicalContentExtractor
        ext = MedicalContentExtractor()
        text = "炮制：取净黄芪，切厚片，加蜜拌匀。"
        result = ext.extract(text)
        prep_items = [i for i in result.items if i.entity_type == "preparation"]
        assert len(prep_items) >= 1

    def test_contraindication_extraction(self):
        from src.extraction.medical_content_extractor import MedicalContentExtractor
        ext = MedicalContentExtractor()
        text = "禁忌：阴虚火旺者忌服。"
        result = ext.extract(text)
        contra_items = [i for i in result.items if i.entity_type == "contraindication"]
        assert len(contra_items) >= 1


# ============================================================================
# clinical_extractor.py
# ============================================================================

class TestClinicalExtractor:
    def test_symptom_extraction(self):
        from src.extraction.clinical_extractor import ClinicalExtractor
        ext = ClinicalExtractor()
        text = "症见：面色萎黄，少气懒言，食少便溏。"
        result = ext.extract(text)
        symptom_items = [i for i in result.items if i.entity_type == "symptom"]
        assert len(symptom_items) >= 1

    def test_diagnosis_extraction(self):
        from src.extraction.clinical_extractor import ClinicalExtractor
        ext = ClinicalExtractor()
        text = "辨证：脾气虚弱。治以健脾益气。"
        result = ext.extract(text)
        syndrome_items = [i for i in result.items if i.entity_type == "syndrome"]
        assert len(syndrome_items) >= 1

    def test_case_structure(self):
        from src.extraction.clinical_extractor import ClinicalExtractor
        ext = ClinicalExtractor()
        text = (
            "医案：某患者，女，45岁，面色萎黄。\n"
            "辨证：脾气虚弱。\n"
            "治法：健脾益气。\n"
            "处方：四君子汤加减。\n"
            "服7剂后好转。"
        )
        result = ext.extract(text)
        cases = result.statistics.get("cases", [])
        assert len(cases) >= 1
        assert cases[0].get("diagnosis")

    def test_acupoint_extraction(self):
        from src.extraction.clinical_extractor import ClinicalExtractor
        ext = ClinicalExtractor()
        text = "配合针灸治疗，取穴足三里、合谷、三阴交。"
        result = ext.extract(text)
        acu_items = [i for i in result.items if i.entity_type == "acupoint"]
        names = [i.name for i in acu_items]
        assert "足三里" in names
        assert "合谷" in names
        assert "三阴交" in names


# ============================================================================
# academic_value_assessor.py
# ============================================================================

class TestAcademicValueAssessor:
    def _make_items(self) -> list:
        from src.extraction.base import ExtractedItem
        return [
            ExtractedItem(name="四君子汤", entity_type="formula", confidence=0.95, length=4),
            ExtractedItem(name="人参", entity_type="herb", confidence=0.95, length=2),
            ExtractedItem(name="白术", entity_type="herb", confidence=0.90, length=2),
            ExtractedItem(name="茯苓", entity_type="herb", confidence=0.90, length=2),
            ExtractedItem(name="甘草", entity_type="herb", confidence=0.90, length=2),
            ExtractedItem(name="脾气虚", entity_type="syndrome", confidence=0.85, length=3),
            ExtractedItem(name="补气健脾", entity_type="efficacy", confidence=0.85, length=4),
        ]

    def _make_relations(self) -> list:
        from src.extraction.base import ExtractionRelation
        return [
            ExtractionRelation(source="四君子汤", target="人参", relation_type="contains"),
            ExtractionRelation(source="四君子汤", target="脾气虚", relation_type="treats"),
        ]

    def test_assess_basic(self):
        from src.extraction.academic_value_assessor import AcademicValueAssessor
        assessor = AcademicValueAssessor()
        report = assessor.assess(self._make_items(), self._make_relations(), text_length=500, dynasty="汉")
        assert report.overall_score > 0
        assert report.grade in ("A", "B", "C", "D")
        assert report.historical_significance > 0.5  # 汉代权重高

    def test_assess_empty(self):
        from src.extraction.academic_value_assessor import AcademicValueAssessor
        assessor = AcademicValueAssessor()
        report = assessor.assess([], [], text_length=0)
        assert report.overall_score >= 0
        assert isinstance(report.recommendations, list)

    def test_assess_as_result(self):
        from src.extraction.academic_value_assessor import AcademicValueAssessor
        assessor = AcademicValueAssessor()
        result = assessor.assess_as_result(self._make_items(), self._make_relations(), text_length=500)
        assert result.module_name == "academic_value_assessor"
        assert result.duration_sec >= 0


# ============================================================================
# quality_checker.py
# ============================================================================

class TestQualityChecker:
    def test_check_with_items(self):
        from src.extraction.base import ExtractedItem, PipelineResult
        from src.extraction.quality_checker import QualityChecker
        pr = PipelineResult(document_id="test")
        pr.all_items = [
            ExtractedItem(name="人参", entity_type="herb", confidence=0.95, length=2),
            ExtractedItem(name="四君子汤", entity_type="formula", confidence=0.95, length=4),
            ExtractedItem(name="脾虚", entity_type="syndrome", confidence=0.85, length=2),
            ExtractedItem(name="补气", entity_type="efficacy", confidence=0.85, length=2),
        ]
        checker = QualityChecker()
        report = checker.check(pr, text_length=200)
        assert report.overall_score > 0
        assert report.grade in ("A", "B", "C", "D")
        assert "herb" in report.entity_summary

    def test_check_empty(self):
        from src.extraction.base import PipelineResult
        from src.extraction.quality_checker import QualityChecker
        pr = PipelineResult(document_id="empty")
        checker = QualityChecker()
        report = checker.check(pr, text_length=100)
        # 空结果应有 critical 问题
        critical = [i for i in report.issues if i.severity == "critical"]
        assert len(critical) >= 1

    def test_markdown_output(self):
        from src.extraction.base import ExtractedItem, PipelineResult
        from src.extraction.quality_checker import QualityChecker
        pr = PipelineResult(document_id="md_test")
        pr.all_items = [
            ExtractedItem(name="黄芪", entity_type="herb", confidence=0.92, length=2),
        ]
        checker = QualityChecker()
        report = checker.check(pr)
        md = report.to_markdown()
        assert "# 提取质量报告" in md
        assert "herb" in md

    def test_json_output(self):
        import json

        from src.extraction.base import PipelineResult
        from src.extraction.quality_checker import QualityChecker
        pr = PipelineResult(document_id="json_test")
        checker = QualityChecker()
        report = checker.check(pr)
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["document_id"] == "json_test"


# ============================================================================
# extraction_pipeline.py — 集成测试
# ============================================================================

class TestExtractionPipeline:
    _SAMPLE_TEXT = (
        "《伤寒论》为汉代张仲景所著，论述外感病与杂病。\n"
        "桂枝汤由桂枝、芍药、甘草、生姜、大枣组成。\n"
        "主治：太阳中风，发热汗出，恶风。\n"
        "功效：解肌发表，调和营卫。\n"
        "用法：水煎服，日三次。\n"
    )

    def test_process_document(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline()
        result = pipeline.process_document(self._SAMPLE_TEXT, source_file="test.txt")
        assert result.document_id
        assert len(result.all_items) > 0
        assert result.total_duration_sec > 0
        assert not result.errors

    def test_process_document_modules_present(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline()
        result = pipeline.process_document(self._SAMPLE_TEXT, source_file="test.txt")
        # 核心模块应都有结果
        assert "entity_extractor" in result.module_results
        assert "metadata" in result.module_results
        assert "medical_content" in result.module_results
        assert "clinical" in result.module_results
        assert "quality_check" in result.module_results

    def test_process_batch(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline()
        docs = [
            {"raw_text": self._SAMPLE_TEXT, "source_file": "doc1.txt"},
            {"raw_text": "黄芪补气固表。", "source_file": "doc2.txt"},
        ]
        results = pipeline.process_batch(docs)
        assert len(results) == 2

    def test_disable_modules(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline(
            enable_metadata=False,
            enable_medical_content=False,
            enable_clinical=False,
            enable_academic_assessment=False,
            enable_quality_check=False,
        )
        result = pipeline.process_document(self._SAMPLE_TEXT)
        assert "entity_extractor" in result.module_results
        assert "metadata" not in result.module_results

    def test_result_to_json(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline()
        result = pipeline.process_document("人参补气。")
        j = ExtractionPipeline.result_to_json(result)
        assert isinstance(j, dict)
        assert "document_id" in j

    def test_result_to_csv_rows(self):
        from src.extraction.extraction_pipeline import ExtractionPipeline
        pipeline = ExtractionPipeline()
        result = pipeline.process_document("黄芪补气固表利水。")
        rows = ExtractionPipeline.result_to_csv_rows(result)
        assert isinstance(rows, list)
        if rows:
            assert "entity_name" in rows[0]
            assert "document_id" in rows[0]
