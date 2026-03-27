import unittest

from src.cycle.fixing_stage import FixingStage


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


if __name__ == "__main__":
    unittest.main()
