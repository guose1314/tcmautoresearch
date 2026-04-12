from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.diagnostics.rebuild_tcm_lexicon import (  # noqa: E402
    BuildAccumulator,
    build_audit_payload,
    normalize_efficacy,
    normalize_syndrome,
    write_audit_artifacts,
)


class TestRebuildLexiconNormalization(unittest.TestCase):
    def test_normalize_syndrome_keeps_structured_term(self):
        self.assertEqual(normalize_syndrome("气虚证"), "气虚证")

    def test_normalize_syndrome_rejects_prose_noise(self):
        self.assertEqual(normalize_syndrome("脾为后天之本"), "")
        self.assertEqual(normalize_syndrome("一切风痰之症"), "")
        self.assertEqual(normalize_syndrome("不结胸而少腹硬满"), "")
        self.assertEqual(normalize_syndrome("不发热"), "")
        self.assertEqual(normalize_syndrome("产后等见时发热"), "")
        self.assertEqual(normalize_syndrome("伤寒心腹胀满"), "")
        self.assertEqual(normalize_syndrome("其人但咽痛"), "")
        self.assertEqual(normalize_syndrome("经期腹痛属寒证"), "")
        self.assertEqual(normalize_syndrome("大便不解或协热"), "")
        self.assertEqual(normalize_syndrome("但发潮热"), "")

    def test_normalize_syndrome_keeps_pattern_prefix_terms(self):
        self.assertEqual(normalize_syndrome("气虚发热"), "气虚发热")
        self.assertEqual(normalize_syndrome("风寒束表"), "风寒束表")

    def test_normalize_efficacy_keeps_classical_term(self):
        self.assertEqual(normalize_efficacy("补气"), "补气")
        self.assertEqual(normalize_efficacy("活血化瘀"), "活血化瘀")
        self.assertEqual(normalize_efficacy("补气活血通络"), "补气活血通络")
        self.assertEqual(normalize_efficacy("温中涩肠止痢"), "温中涩肠止痢")

    def test_normalize_efficacy_rejects_marketing_term(self):
        self.assertEqual(normalize_efficacy("增强免疫力"), "")
        self.assertEqual(normalize_efficacy("改善睡眠"), "")
        self.assertEqual(normalize_efficacy("固其下焦"), "")
        self.assertEqual(normalize_efficacy("温散其风湿"), "")
        self.assertEqual(normalize_efficacy("清少阴客热"), "")
        self.assertEqual(normalize_efficacy("散胸中邪气"), "")


class TestRebuildLexiconAudit(unittest.TestCase):
    def test_build_audit_payload_keeps_source_provenance(self):
        acc = BuildAccumulator()
        acc.add_term("syndromes", "气虚证", "entry_syndrome")
        acc.add_term("syndromes", "气虚证", "formula_archive_indication")

        payload = build_audit_payload(acc)

        self.assertIn("syndrome", payload)
        self.assertEqual(payload["syndrome"][0]["term"], "气虚证")
        self.assertEqual(
            payload["syndrome"][0]["sources"],
            ["entry_syndrome", "formula_archive_indication"],
        )

    def test_write_audit_artifacts_writes_summary_and_category_files(self):
        acc = BuildAccumulator()
        acc.add_term("efficacy", "补气", "entry_efficacy")
        summary = {"counts": acc.summary(), "build_flags": {"include_micang_clinical_terms": False}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "audit"
            write_audit_artifacts(out_dir, acc, summary)

            self.assertTrue((out_dir / "summary.json").exists())
            self.assertTrue((out_dir / "efficacy.json").exists())
            efficacy_rows = json.loads((out_dir / "efficacy.json").read_text(encoding="utf-8"))
            self.assertEqual(efficacy_rows[0]["term"], "补气")
            self.assertEqual(efficacy_rows[0]["sources"], ["entry_efficacy"])


if __name__ == "__main__":
    unittest.main()