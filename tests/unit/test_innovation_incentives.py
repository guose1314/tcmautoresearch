import json
import tempfile
import unittest
from pathlib import Path

from tools.innovation_incentives import (
    AdaptiveLearningState,
    ContributionProfile,
    apply_adaptive_learning,
    evaluate_profile,
    load_learning_state,
    load_profile,
    save_learning_state,
    save_report,
)


class TestInnovationIncentives(unittest.TestCase):
    def test_evaluate_profile_assigns_high_tier(self):
        profile = ContributionProfile(
            title="依赖图自动化",
            owner="tester",
            summary="建立自动依赖图与 CI 更新机制",
            novelty=5,
            impact=5,
            validation=4,
            reuse=5,
            knowledge_sharing=4,
            has_tests=True,
            has_docs=True,
            has_artifact=True,
            quality_gate_passed=True,
            linked_files=["tools/generate_dependency_graph.py"],
        )
        report = evaluate_profile(profile)
        self.assertGreaterEqual(report.score, 85)
        self.assertEqual(report.tier, "Pioneer")

    def test_evaluate_profile_generates_improvement_actions(self):
        profile = ContributionProfile(
            title="想法草案",
            owner="tester",
            summary="只有初步设想",
            novelty=3,
            impact=2,
            validation=1,
            reuse=1,
            knowledge_sharing=1,
        )
        report = evaluate_profile(profile)
        self.assertTrue(len(report.improvement_actions) >= 3)
        self.assertEqual(report.tier, "Incubator")

    def test_load_and_save_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "profile.json"
            output_path = root / "report.json"
            input_path.write_text(
                json.dumps(
                    {
                        "title": "质量门增强",
                        "owner": "tester",
                        "summary": "建立统一质量门",
                        "novelty": 4,
                        "impact": 4,
                        "validation": 4,
                        "reuse": 4,
                        "knowledge_sharing": 4,
                        "has_tests": True,
                        "has_docs": True,
                        "has_artifact": False,
                        "quality_gate_passed": True,
                        "linked_files": ["tools/quality_gate.py"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            profile = load_profile(input_path)
            report = evaluate_profile(profile)
            save_report(report, output_path)
            self.assertTrue(output_path.exists())
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["owner"], "tester")

    def test_adaptive_learning_updates_state_weights(self):
        profile = ContributionProfile(
            title="创新尝试",
            owner="tester",
            summary="验证自适应学习闭环",
            novelty=5,
            impact=4,
            validation=2,
            reuse=3,
            knowledge_sharing=2,
        )
        state = AdaptiveLearningState(
            dimension_weights={
                "novelty": 30,
                "impact": 25,
                "validation": 20,
                "reuse": 15,
                "knowledge_sharing": 10,
            },
            learning_rate=0.2,
            samples=0,
        )
        report = evaluate_profile(profile, active_weights=state.dimension_weights)
        info = apply_adaptive_learning(state, profile, report, feedback=2.0)

        self.assertTrue(info["state_updated"])
        self.assertEqual(state.samples, 1)
        self.assertEqual(sum(state.dimension_weights.values()), 100)
        self.assertIn("weights_before", info)
        self.assertIn("weights_after", info)

    def test_load_and_save_learning_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state = AdaptiveLearningState(
                dimension_weights={
                    "novelty": 40,
                    "impact": 25,
                    "validation": 15,
                    "reuse": 10,
                    "knowledge_sharing": 10,
                },
                learning_rate=0.15,
                samples=3,
            )
            save_learning_state(state, state_path)
            loaded = load_learning_state(state_path)

            self.assertEqual(loaded.samples, 3)
            self.assertAlmostEqual(loaded.learning_rate, 0.15)
            self.assertEqual(sum(loaded.dimension_weights.values()), 100)


if __name__ == "__main__":
    unittest.main()