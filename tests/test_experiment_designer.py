"""ExperimentDesigner 单元测试。"""

import unittest

from src.research.experiment_designer import (
    PICO,
    EligibilityCriteria,
    ExperimentDesigner,
    SampleSizeEstimation,
    StudyProtocol,
    StudyType,
    _estimate_sample_size,
)


class TestStudyTypeEnum(unittest.TestCase):
    """StudyType 枚举基本行为。"""

    def test_all_six_types_exist(self):
        expected = {"rct", "systematic_review", "meta_analysis", "cohort",
                    "case_control", "network_pharmacology"}
        self.assertEqual({t.value for t in StudyType}, expected)

    def test_str_value(self):
        self.assertEqual(StudyType.RCT.value, "rct")
        self.assertEqual(StudyType.META_ANALYSIS.value, "meta_analysis")


class TestSampleSizeEstimation(unittest.TestCase):
    """样本量简化估算。"""

    def test_positive_effect_returns_positive(self):
        n = _estimate_sample_size(alpha=0.05, power=0.80, effect_size=0.5)
        self.assertGreater(n, 0)

    def test_zero_effect_returns_zero(self):
        self.assertEqual(_estimate_sample_size(effect_size=0), 0)

    def test_smaller_effect_needs_larger_sample(self):
        n_large = _estimate_sample_size(effect_size=0.8)
        n_small = _estimate_sample_size(effect_size=0.3)
        self.assertGreater(n_small, n_large)


class TestPICO(unittest.TestCase):

    def test_to_dict(self):
        p = PICO(population="高血压患者", intervention="天麻钩藤饮",
                 comparison="氨氯地平", outcome="收缩压变化")
        d = p.to_dict()
        self.assertEqual(d["population"], "高血压患者")
        self.assertEqual(len(d), 4)


class TestEligibilityCriteria(unittest.TestCase):

    def test_to_dict_round_trip(self):
        ec = EligibilityCriteria(inclusion=["a", "b"], exclusion=["c"])
        d = ec.to_dict()
        self.assertEqual(d["inclusion"], ["a", "b"])
        self.assertEqual(d["exclusion"], ["c"])


class TestStudyProtocol(unittest.TestCase):

    def test_filled_required_count_empty(self):
        sp = StudyProtocol()
        self.assertEqual(sp.filled_required_count(), 0)

    def test_filled_required_count_complete(self):
        sp = StudyProtocol(
            study_type="rct",
            hypothesis="某假设",
            pico=PICO(population="人群"),
            sample_size=SampleSizeEstimation(estimated_n=100),
            eligibility=EligibilityCriteria(inclusion=["a"]),
            primary_outcome="主要结局",
            statistical_plan="t 检验",
        )
        self.assertEqual(sp.filled_required_count(), 7)

    def test_to_dict_keys(self):
        sp = StudyProtocol(study_type="rct", hypothesis="H1")
        d = sp.to_dict()
        self.assertIn("study_type", d)
        self.assertIn("pico", d)
        self.assertIn("sample_size", d)
        self.assertIn("eligibility", d)


class TestExperimentDesigner(unittest.TestCase):
    """ExperimentDesigner 核心设计方法。"""

    def setUp(self):
        self.designer = ExperimentDesigner()

    # -- 基本功能 ----------------------------------------------------------

    def test_design_rct_returns_protocol(self):
        proto = self.designer.design_study("清热解毒法治疗社区获得性肺炎有效",
                                           StudyType.RCT)
        self.assertIsInstance(proto, StudyProtocol)
        self.assertEqual(proto.study_type, "rct")

    def test_rct_has_at_least_5_filled_required(self):
        proto = self.designer.design_study(
            "银翘散治疗流感症状缓解时间短于奥司他韦",
            StudyType.RCT,
            population="流感患者",
            outcome="症状缓解时间",
        )
        self.assertGreaterEqual(proto.filled_required_count(), 5)

    def test_systematic_review_protocol(self):
        proto = self.designer.design_study("针灸治疗慢性疼痛效果优于假针刺",
                                           StudyType.SYSTEMATIC_REVIEW)
        self.assertEqual(proto.study_type, "systematic_review")
        self.assertIn("PRISMA", proto.statistical_plan)

    def test_meta_analysis_protocol(self):
        proto = self.designer.design_study("中药复方降低 2 型糖尿病 HbA1c",
                                           StudyType.META_ANALYSIS)
        self.assertEqual(proto.study_type, "meta_analysis")
        self.assertIn("异质性", proto.statistical_plan)

    def test_cohort_protocol(self):
        proto = self.designer.design_study("长期服用补中益气汤降低反复感染风险",
                                           StudyType.COHORT)
        self.assertEqual(proto.study_type, "cohort")
        self.assertIn("Cox", proto.statistical_plan)

    def test_case_control_protocol(self):
        proto = self.designer.design_study("脾虚证与肠道菌群失调的关联",
                                           StudyType.CASE_CONTROL)
        self.assertEqual(proto.study_type, "case_control")
        self.assertIn("Logistic", proto.statistical_plan)

    def test_network_pharmacology_protocol(self):
        proto = self.designer.design_study("六味地黄丸治疗肾阴虚的网络药理学机制",
                                           StudyType.NETWORK_PHARMACOLOGY)
        self.assertEqual(proto.study_type, "network_pharmacology")
        self.assertIn("KEGG", proto.statistical_plan)

    # -- PICO 自定义 -------------------------------------------------------

    def test_custom_pico(self):
        proto = self.designer.design_study(
            "H1",
            "rct",
            population="2 型糖尿病患者",
            intervention="黄芪多糖胶囊",
            comparison="安慰剂",
            outcome="HbA1c",
        )
        self.assertEqual(proto.pico.population, "2 型糖尿病患者")
        self.assertEqual(proto.pico.intervention, "黄芪多糖胶囊")

    # -- 类型解析 -----------------------------------------------------------

    def test_string_type_resolution(self):
        proto = self.designer.design_study("H2", "RCT")
        self.assertEqual(proto.study_type, "rct")

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            self.designer.design_study("H", "unknown_design")

    # -- 辅助方法 -----------------------------------------------------------

    def test_list_study_types(self):
        types = self.designer.list_study_types()
        self.assertEqual(len(types), 6)
        self.assertIn("rct", types)

    # -- to_dict 完整性 -----------------------------------------------------

    def test_protocol_to_dict_contains_all_keys(self):
        proto = self.designer.design_study("H3", StudyType.RCT)
        d = proto.to_dict()
        for key in ("study_type", "hypothesis", "pico", "sample_size",
                     "eligibility", "primary_outcome", "statistical_plan",
                     "blinding", "randomization", "duration",
                     "ethical_considerations", "design_notes"):
            self.assertIn(key, d)

    # -- 样本量参数 ---------------------------------------------------------

    def test_custom_effect_size(self):
        proto = self.designer.design_study("H4", StudyType.RCT, effect_size=0.3)
        self.assertGreater(proto.sample_size.estimated_n, 0)
        self.assertAlmostEqual(proto.sample_size.effect_size, 0.3)

    # -- 每种类型至少5个必填字段 ----------------------------------------------

    def test_all_types_have_at_least_5_filled(self):
        for st in StudyType:
            with self.subTest(study_type=st):
                proto = self.designer.design_study(
                    f"测试假设-{st.value}",
                    st,
                    population="测试人群",
                    outcome="测试结局",
                )
                self.assertGreaterEqual(
                    proto.filled_required_count(), 5,
                    f"{st.value} 的必填字段不足 5 个",
                )


if __name__ == "__main__":
    unittest.main()
