"""T2.4: 验证 Hypothesis / Analyze 输出 methodology_tag + evidence_grade 契约。"""

from __future__ import annotations

import unittest

from src.research.hypothesis_engine import (
    DEFAULT_HYPOTHESIS_EVIDENCE_GRADE,
    HYPOTHESIS_EVIDENCE_GRADES,
    METHODOLOGY_TAGS,
    Hypothesis,
    infer_methodology_tag,
)
from src.research.phases.hypothesis_phase import (
    _validate_hypothesis_methodology_contract,
)
from src.research.phases.analyze_phase import (
    _resolve_analyze_methodology,
    _validate_analyze_methodology_contract,
)


class _StubCycle:
    def __init__(self, objective: str = "") -> None:
        self.research_objective = objective
        self.cycle_id = "cyc-test"


class TestMethodologyVocabulary(unittest.TestCase):
    def test_default_grade_is_C(self) -> None:
        self.assertEqual(DEFAULT_HYPOTHESIS_EVIDENCE_GRADE, "C")
        self.assertIn(DEFAULT_HYPOTHESIS_EVIDENCE_GRADE, HYPOTHESIS_EVIDENCE_GRADES)

    def test_methodology_tags_complete(self) -> None:
        self.assertEqual(set(METHODOLOGY_TAGS), {"philology", "classification", "evidence_based"})

    def test_grades_complete(self) -> None:
        self.assertEqual(set(HYPOTHESIS_EVIDENCE_GRADES), {"A", "B", "C", "D"})


class TestInferMethodologyTag(unittest.TestCase):
    def test_philology_keywords(self) -> None:
        self.assertEqual(infer_methodology_tag("version_lineage_gap"), "philology")
        self.assertEqual(infer_methodology_tag("missing_witness"), "philology")

    def test_classification_keywords(self) -> None:
        self.assertEqual(infer_methodology_tag("incomplete_composition"), "classification")
        self.assertEqual(infer_methodology_tag("herb_taxonomy_gap"), "classification")

    def test_default_evidence_based(self) -> None:
        self.assertEqual(infer_methodology_tag("orphan_entity"), "evidence_based")
        self.assertEqual(infer_methodology_tag(""), "evidence_based")
        self.assertEqual(infer_methodology_tag("missing_downstream"), "evidence_based")


class TestHypothesisDataclass(unittest.TestCase):
    def test_to_dict_includes_methodology_fields(self) -> None:
        h = Hypothesis(
            hypothesis_id="abc",
            title="t",
            statement="s",
            rationale="r",
            novelty=0.5,
            feasibility=0.5,
            evidence_support=0.5,
            confidence=0.5,
            source_gap_type="orphan_entity",
        )
        d = h.to_dict()
        self.assertEqual(d["methodology_tag"], "evidence_based")
        self.assertEqual(d["evidence_grade"], "C")


class TestHypothesisContractValidation(unittest.TestCase):
    def _valid_hypothesis(self, **overrides) -> dict:
        base = {
            "hypothesis_id": "h1",
            "statement": "x",
            "methodology_tag": "evidence_based",
            "evidence_grade": "C",
        }
        base.update(overrides)
        return base

    def test_passes_when_valid(self) -> None:
        _validate_hypothesis_methodology_contract([self._valid_hypothesis()])

    def test_passes_when_grade_none(self) -> None:
        _validate_hypothesis_methodology_contract([self._valid_hypothesis(evidence_grade=None)])

    def test_passes_with_empty_list(self) -> None:
        _validate_hypothesis_methodology_contract([])

    def test_fails_missing_methodology_tag(self) -> None:
        bad = self._valid_hypothesis()
        bad.pop("methodology_tag")
        with self.assertRaises(ValueError):
            _validate_hypothesis_methodology_contract([bad])

    def test_fails_invalid_methodology_tag(self) -> None:
        with self.assertRaises(ValueError):
            _validate_hypothesis_methodology_contract(
                [self._valid_hypothesis(methodology_tag="bogus")]
            )

    def test_fails_invalid_grade(self) -> None:
        with self.assertRaises(ValueError):
            _validate_hypothesis_methodology_contract(
                [self._valid_hypothesis(evidence_grade="E")]
            )


class TestAnalyzeMethodologyResolution(unittest.TestCase):
    def test_explicit_context_wins(self) -> None:
        m = _resolve_analyze_methodology(
            {"methodology_tag": "philology", "methodology_evidence_grade": "B"},
            _StubCycle("证据合成研究"),
        )
        self.assertEqual(m, {"methodology_tag": "philology", "evidence_grade": "B"})

    def test_objective_heuristic_philology(self) -> None:
        m = _resolve_analyze_methodology({}, _StubCycle("敦煌写本校勘研究"))
        self.assertEqual(m["methodology_tag"], "philology")
        self.assertEqual(m["evidence_grade"], "C")

    def test_objective_heuristic_classification(self) -> None:
        m = _resolve_analyze_methodology({}, _StubCycle("本草分类整理"))
        self.assertEqual(m["methodology_tag"], "classification")

    def test_default_evidence_based(self) -> None:
        m = _resolve_analyze_methodology({}, _StubCycle("某临床方剂的疗效"))
        self.assertEqual(m["methodology_tag"], "evidence_based")
        self.assertEqual(m["evidence_grade"], "C")


class TestAnalyzeContractValidation(unittest.TestCase):
    def test_passes(self) -> None:
        _validate_analyze_methodology_contract({"methodology_tag": "philology", "evidence_grade": "A"})

    def test_passes_grade_none(self) -> None:
        _validate_analyze_methodology_contract({"methodology_tag": "philology", "evidence_grade": None})

    def test_fails_invalid_tag(self) -> None:
        with self.assertRaises(ValueError):
            _validate_analyze_methodology_contract({"methodology_tag": "bogus", "evidence_grade": "C"})

    def test_fails_invalid_grade(self) -> None:
        with self.assertRaises(ValueError):
            _validate_analyze_methodology_contract({"methodology_tag": "philology", "evidence_grade": "Z"})

    def test_fails_non_dict(self) -> None:
        with self.assertRaises(ValueError):
            _validate_analyze_methodology_contract("not-a-dict")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
