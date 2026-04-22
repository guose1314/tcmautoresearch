"""Phase K / K-1 + K-4 tests: graph_schema 扩展与严格模式校验。"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.storage.graph_schema import (
    GRAPH_SCHEMA_STRICT_ENV,
    GRAPH_SCHEMA_VERSION,
    GraphSchemaDriftError,
    NodeLabel,
    RelType,
    assert_schema_consistent,
    detect_schema_drift,
    get_allowed_properties,
    get_allowed_rel_properties,
    is_strict_mode_enabled,
)


class TestPhaseKNodeLabels(unittest.TestCase):
    def test_rhyme_witness_present(self):
        self.assertIn(NodeLabel.RHYME_WITNESS, NodeLabel)
        self.assertEqual(NodeLabel.RHYME_WITNESS.value, "RhymeWitness")

    def test_school_present(self):
        self.assertIn(NodeLabel.SCHOOL, NodeLabel)
        self.assertEqual(NodeLabel.SCHOOL.value, "School")

    def test_rhyme_witness_properties(self):
        props = get_allowed_properties("RhymeWitness")
        for key in ("rhyme_id", "fanqie", "middle_chinese", "rhyme_group", "tone", "initial", "final"):
            self.assertIn(key, props)

    def test_school_properties(self):
        props = get_allowed_properties("School")
        for key in ("school_id", "name", "founding_dynasty", "core_doctrine", "representative_figures"):
            self.assertIn(key, props)


class TestPhaseKRelTypes(unittest.TestCase):
    def test_mentorship_present(self):
        self.assertIn(RelType.MENTORSHIP, RelType)
        self.assertEqual(RelType.MENTORSHIP.value, "MENTORSHIP")

    def test_belongs_to_school_present(self):
        self.assertIn(RelType.BELONGS_TO_SCHOOL, RelType)

    def test_rhymes_with_present(self):
        self.assertIn(RelType.RHYMES_WITH, RelType)

    def test_rhymes_with_rel_properties(self):
        props = get_allowed_rel_properties("RHYMES_WITH")
        for key in ("rhyme_group", "phonetic_basis", "source_refs", "confidence"):
            self.assertIn(key, props)

    def test_belongs_to_school_rel_properties(self):
        props = get_allowed_rel_properties("BELONGS_TO_SCHOOL")
        for key in ("role", "period", "source_refs", "confidence"):
            self.assertIn(key, props)

    def test_mentorship_rel_properties(self):
        props = get_allowed_rel_properties("MENTORSHIP")
        for key in ("mentor_role", "apprentice_role", "period"):
            self.assertIn(key, props)


class TestPhaseKVersionBump(unittest.TestCase):
    def test_version_at_least_1_2_0(self):
        # Version comparison via tuple
        parts = tuple(int(p) for p in GRAPH_SCHEMA_VERSION.split("."))
        self.assertGreaterEqual(parts, (1, 2, 0))


class TestPhaseKStrictMode(unittest.TestCase):
    def test_is_strict_mode_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(GRAPH_SCHEMA_STRICT_ENV, None)
            self.assertFalse(is_strict_mode_enabled())

    def test_is_strict_mode_truthy_values(self):
        for value in ("1", "true", "yes", "on", "STRICT"):
            self.assertTrue(is_strict_mode_enabled(value), f"value={value!r} should be truthy")

    def test_is_strict_mode_falsy_values(self):
        for value in ("", "0", "false", "no", "off", "anything-else"):
            self.assertFalse(is_strict_mode_enabled(value))

    def test_assert_consistent_returns_report_when_match(self):
        report = assert_schema_consistent(GRAPH_SCHEMA_VERSION, strict=True)
        self.assertFalse(report["drift_detected"])

    def test_assert_consistent_raises_in_strict_mode(self):
        with self.assertRaises(GraphSchemaDriftError) as ctx:
            assert_schema_consistent(None, strict=True)
        self.assertTrue(ctx.exception.drift_report["drift_detected"])
        self.assertIn("expected_version", ctx.exception.drift_report)

    def test_assert_consistent_no_raise_when_not_strict_and_no_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(GRAPH_SCHEMA_STRICT_ENV, None)
            report = assert_schema_consistent("0.0.0", strict=False)
            self.assertTrue(report["drift_detected"])

    def test_assert_consistent_raises_when_env_truthy(self):
        with patch.dict(os.environ, {GRAPH_SCHEMA_STRICT_ENV: "true"}):
            with self.assertRaises(GraphSchemaDriftError):
                assert_schema_consistent("0.0.0", strict=False)

    def test_drift_error_carries_detail(self):
        try:
            assert_schema_consistent("9.9.9", strict=True)
        except GraphSchemaDriftError as exc:
            self.assertEqual(exc.drift_report["stored_version"], "9.9.9")
            self.assertEqual(exc.drift_report["expected_version"], GRAPH_SCHEMA_VERSION)
        else:
            self.fail("expected GraphSchemaDriftError")


class TestPhaseKDetectDrift(unittest.TestCase):
    def test_detect_drift_match(self):
        result = detect_schema_drift(GRAPH_SCHEMA_VERSION)
        self.assertFalse(result["drift_detected"])

    def test_detect_drift_mismatch(self):
        result = detect_schema_drift("0.0.1")
        self.assertTrue(result["drift_detected"])


if __name__ == "__main__":
    unittest.main()
