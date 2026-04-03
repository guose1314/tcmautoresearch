import unittest

from src.analysis import DataMiningService

RECORDS = [
    {"formula": "补中益气汤", "herbs": ["黄芪", "党参", "白术", "甘草"], "syndrome": "气虚"},
    {"formula": "四君子汤", "herbs": ["党参", "白术", "茯苓", "甘草"], "syndrome": "脾虚"},
    {"formula": "参苓白术散", "herbs": ["党参", "白术", "茯苓", "甘草"], "syndrome": "脾虚"},
    {"formula": "六君子汤", "herbs": ["党参", "白术", "茯苓", "甘草", "黄芪"], "syndrome": "痰湿"},
    {"formula": "归脾汤", "herbs": ["黄芪", "党参", "白术", "茯苓"], "syndrome": "心脾两虚"},
]


class TestDataMiningService(unittest.TestCase):
    def setUp(self):
        self.service = DataMiningService(
            {
                "min_support": 0.4,
                "min_confidence": 0.7,
                "max_itemset_size": 3,
            }
        )
        self.assertTrue(self.service.initialize())

    def tearDown(self):
        self.service.cleanup()

    def test_execute_default_methods_from_records(self):
        result = self.service.execute({"records": RECORDS})

        self.assertEqual(result["record_count"], len(RECORDS))
        self.assertIn("association_rules", result)
        self.assertIn("frequent_itemsets", result)
        self.assertIn("clustering", result)
        self.assertGreater(len(result["association_rules"]["rules"]), 0)
        self.assertGreater(len(result["frequent_itemsets"]["itemsets"]), 0)
        self.assertEqual(
            sum(cluster["size"] for cluster in result["clustering"]["cluster_summary"]),
            len(RECORDS),
        )

    def test_frequent_itemsets_contain_high_support_pair(self):
        result = self.service.execute({"records": RECORDS, "methods": ["frequent_itemsets"]})

        itemsets = result["frequent_itemsets"]["itemsets"]
        pair = next((entry for entry in itemsets if entry["items"] == ["党参", "白术"]), None)
        self.assertIsNotNone(pair)
        self.assertGreaterEqual(pair["support"], 0.8)

    def test_association_rule_thresholds_are_applied(self):
        result = self.service.execute(
            {
                "records": RECORDS,
                "methods": ["association_rules"],
                "min_confidence": 0.8,
                "min_lift": 1.0,
            }
        )

        for rule in result["association_rules"]["rules"]:
            self.assertGreaterEqual(rule["confidence"], 0.8)
            self.assertGreaterEqual(rule["lift"], 1.0)

    def test_predictive_modeling_uses_time_series_payload(self):
        result = self.service.execute(
            {
                "records": RECORDS,
                "methods": ["predictive_modeling"],
                "time_series_data": [
                    {"time": 2020, "value": 0.42},
                    {"time": 2021, "value": 0.51},
                    {"time": 2022, "value": 0.66},
                ],
                "dose_response_data": [
                    {"dose": 6, "response": 0.30},
                    {"dose": 9, "response": 0.44},
                    {"dose": 12, "response": 0.58},
                ],
            }
        )

        self.assertIn("predictive_modeling", result)
        self.assertIn("time_series_trend", result["predictive_modeling"])
        self.assertIn("dose_response", result["predictive_modeling"])

    def test_execute_raises_for_missing_input(self):
        with self.assertRaises(ValueError):
            self.service.execute({})


if __name__ == "__main__":
    unittest.main()