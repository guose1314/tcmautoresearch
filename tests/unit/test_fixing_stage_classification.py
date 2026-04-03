import unittest

from src.cycle.fixing_stage import FixingStage, RepairAction, RepairPriority, RepairType


class TestFixingStageClassification(unittest.TestCase):
    def setUp(self):
        self.stage = FixingStage({})

    def test_identify_issue_type_by_message_keyword(self):
        issue_type = self.stage._identify_issue_type(
            {"message": "Input parameter mismatch detected", "category": "runtime"}
        )
        self.assertEqual(issue_type, "input_validation")

    def test_identify_issue_type_by_category_fallback(self):
        issue_type = self.stage._identify_issue_type(
            {"message": "Unhandled exception observed", "category": "security_control"}
        )
        self.assertEqual(issue_type, "security_vulnerability")

    def test_identify_issue_type_defaults_to_general(self):
        issue_type = self.stage._identify_issue_type(
            {"message": "Unknown anomaly", "category": "misc"}
        )
        self.assertEqual(issue_type, "general_issue")

    def test_calculate_comprehensive_confidence(self):
        actions = [
            RepairAction(
                action_id="a1",
                repair_type=RepairType.CODE_FIX,
                priority=RepairPriority.CRITICAL,
                description="d1",
                affected_components=["x"],
                estimated_effort=1.0,
                confidence=0.9,
                success=True,
            ),
            RepairAction(
                action_id="a2",
                repair_type=RepairType.QUALITY,
                priority=RepairPriority.MEDIUM,
                description="d2",
                affected_components=["y"],
                estimated_effort=1.0,
                confidence=0.7,
                success=True,
            ),
            RepairAction(
                action_id="a3",
                repair_type=RepairType.CONFIGURATION,
                priority=RepairPriority.LOW,
                description="d3",
                affected_components=["z"],
                estimated_effort=1.0,
                confidence=0.4,
                success=False,
            ),
        ]

        result = self.stage._calculate_comprehensive_confidence(actions)

        self.assertAlmostEqual(result["repair_confidence"], 0.8)
        self.assertAlmostEqual(result["quality_confidence"], 2 / 3)
        self.assertAlmostEqual(result["academic_confidence"], 0.8)
        self.assertAlmostEqual(result["overall"], 0.8 * 0.4 + (2 / 3) * 0.3 + 0.8 * 0.3)


if __name__ == "__main__":
    unittest.main()
