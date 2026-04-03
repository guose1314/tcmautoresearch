import unittest

from src.collector.literature_retriever import LiteratureRecord
from src.quality.evidence_grader import (
    BIAS_HIGH,
    BIAS_LOW,
    EvidenceGrader,
    StudyRecord,
)
from src.quality.quality_assessor import (
    GRADE_HIGH,
    GRADE_LOW,
    GRADE_MODERATE,
    GRADE_VERY_LOW,
)


def _build_records():
    return [
        LiteratureRecord(
            source="pubmed",
            title="Systematic review and meta-analysis of randomized controlled trials for 黄芪治疗慢性胃炎",
            authors=["A", "B"],
            year=2025,
            doi="10.1000/meta-1",
            url="https://pubmed.ncbi.nlm.nih.gov/meta-1",
            abstract=(
                "This systematic review and meta-analysis included 18 randomized controlled trials "
                "and 1820 patients. The pooled effect was consistent across studies with low heterogeneity "
                "and stable results."
            ),
            citation_count=120,
            external_id="meta-1",
        ),
        LiteratureRecord(
            source="pubmed",
            title="Randomized controlled trial of 桂枝汤 for functional dyspepsia",
            authors=["C", "D"],
            year=2024,
            doi="10.1000/rct-1",
            url="https://pubmed.ncbi.nlm.nih.gov/rct-1",
            abstract=(
                "A randomized controlled trial enrolled N=320 patients with functional dyspepsia. "
                "Outcomes were consistent between centers and measurement methods were clearly defined."
            ),
            citation_count=48,
            external_id="rct-1",
        ),
        LiteratureRecord(
            source="semantic_scholar",
            title="Prospective cohort study of 补中益气汤 in chronic fatigue",
            authors=["E"],
            year=2023,
            doi="10.1000/cohort-1",
            url="https://example.com/cohort-1",
            abstract=(
                "This prospective cohort study included 210 patients and followed them for 12 months. "
                "The effect estimates were generally consistent and most outcomes remained stable."
            ),
            citation_count=25,
            external_id="cohort-1",
        ),
        LiteratureRecord(
            source="google_scholar",
            title="Case-control study of 当归 use in perioperative recovery",
            authors=["F"],
            year=2022,
            doi="",
            url="https://scholar.google.com/case-control-1",
            abstract=(
                "A case-control study included 46 patients. Findings were mixed, with substantial heterogeneity "
                "between outcome measures and wider uncertainty around the estimates."
            ),
            citation_count=4,
            external_id="case-control-1",
        ),
        LiteratureRecord(
            source="arxiv",
            title="Case series report of a novel TCM intervention",
            authors=["G"],
            year=2026,
            doi="",
            url="https://arxiv.org/abs/2604.00001",
            abstract=(
                "This case series included 12 patients and reported short-term symptom improvement without a control group."
            ),
            citation_count=0,
            external_id="arxiv-1",
        ),
    ]


class TestStudyRecordCompatibility(unittest.TestCase):
    def test_from_literature_record_preserves_core_fields(self):
        record = _build_records()[0]

        study = StudyRecord.from_literature_record(record)

        self.assertEqual(study.title, record.title)
        self.assertEqual(study.doi, record.doi)
        self.assertEqual(study.source, record.source)

    def test_from_literature_record_infers_design_and_sample_size(self):
        record = _build_records()[1]
        grader = EvidenceGrader()
        study = StudyRecord.from_literature_record(record)

        self.assertEqual(grader._resolve_study_design(study), "randomized_controlled_trial")
        self.assertEqual(grader._resolve_sample_size(study), 320)


class TestEvidenceGrader(unittest.TestCase):
    def setUp(self):
        self.grader = EvidenceGrader()
        self.records = _build_records()

    def test_assess_bias_risk_distinguishes_low_and_high_bias(self):
        low_risk = self.grader.assess_bias_risk(self.records[0])
        high_risk = self.grader.assess_bias_risk(self.records[-1])

        self.assertEqual(low_risk.overall_risk, BIAS_LOW)
        self.assertEqual(high_risk.overall_risk, BIAS_HIGH)
        self.assertGreater(low_risk.score, high_risk.score)

    def test_grade_evidence_distinguishes_high_and_low_quality_studies(self):
        result = self.grader.grade_evidence(self.records)
        by_title = {item.title: item for item in result.study_results}

        self.assertEqual(
            by_title[self.records[0].title].grade_level,
            GRADE_HIGH,
        )
        self.assertIn(
            by_title[self.records[2].title].grade_level,
            {GRADE_MODERATE, GRADE_LOW},
        )
        self.assertIn(
            by_title[self.records[3].title].grade_level,
            {GRADE_LOW, GRADE_VERY_LOW},
        )
        self.assertEqual(
            by_title[self.records[4].title].grade_level,
            GRADE_VERY_LOW,
        )

    def test_grade_evidence_returns_overall_result(self):
        result = self.grader.grade_evidence(self.records)

        self.assertEqual(result.study_count, 5)
        self.assertIn(result.overall_grade, {GRADE_HIGH, GRADE_MODERATE, GRADE_LOW, GRADE_VERY_LOW})
        self.assertIn("design", result.factor_averages)
        self.assertIn("publication_bias", result.factor_averages)
        self.assertTrue(result.summary)

    def test_grade_evidence_prefers_explicit_quality_overrides(self):
        study = StudyRecord.from_literature_record(self.records[2])
        study.study_design = "cohort"
        study.sample_size = 850
        study.consistency_score = 0.92
        study.precision_score = 0.9
        study.publication_bias_score = 0.88
        study.peer_reviewed = True

        result = self.grader.grade_evidence([study])

        self.assertGreaterEqual(result.overall_score, 0.7)
        self.assertIn(result.overall_grade, {GRADE_HIGH, GRADE_MODERATE})

    def test_grade_evidence_handles_empty_input(self):
        result = self.grader.grade_evidence([])

        self.assertEqual(result.study_count, 0)
        self.assertEqual(result.overall_grade, GRADE_VERY_LOW)
        self.assertEqual(result.overall_score, 0.0)


if __name__ == "__main__":
    unittest.main()