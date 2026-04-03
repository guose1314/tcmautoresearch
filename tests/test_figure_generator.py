import os
import tempfile
import unittest

from src.generation import FigureGenerator


class TestFigureGenerator(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.generator = FigureGenerator({"output_dir": self.tempdir.name, "dpi": 120})
        self.assertTrue(self.generator.initialize())

    def tearDown(self):
        self.generator.cleanup()
        self.tempdir.cleanup()

    def test_generate_network_figure(self):
        result = self.generator.execute(
            {
                "figure_type": "network",
                "title": "药物靶点网络图",
                "data": {
                    "nodes": ["黄芪", "AKT1", "IL6"],
                    "edges": [
                        {"source": "黄芪", "target": "AKT1", "weight": 2},
                        {"source": "黄芪", "target": "IL6", "weight": 1},
                    ],
                },
            }
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["generated_count"], 1)
        self.assertTrue(os.path.exists(result["figure_paths"][0]))
        self.assertEqual(result["figures"][0]["metadata"]["node_count"], 3)

    def test_generate_heatmap_figure(self):
        result = self.generator.execute(
            {
                "figure_type": "heatmap",
                "title": "证据维度热图",
                "data": {
                    "matrix": [[2, 1, 0], [0, 3, 1]],
                    "row_labels": ["文献A", "文献B"],
                    "col_labels": ["干预", "结局", "方法"],
                },
            }
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(result["figure_paths"][0]))
        self.assertEqual(result["figures"][0]["metadata"]["shape"], [2, 3])

    def test_generate_forest_figure(self):
        result = self.generator.execute(
            {
                "figure_type": "forest",
                "title": "疗效森林图",
                "data": {
                    "effects": [
                        {"label": "研究1", "effect": 1.22, "lower": 1.05, "upper": 1.41},
                        {"label": "研究2", "effect": 0.95, "lower": 0.82, "upper": 1.12},
                    ]
                },
            }
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(result["figure_paths"][0]))
        self.assertEqual(result["figures"][0]["metadata"]["effect_count"], 2)

    def test_generate_venn_figure(self):
        result = self.generator.execute(
            {
                "figure_type": "venn",
                "title": "来源交集图",
                "data": {
                    "sets": {
                        "PubMed": ["黄芪", "党参", "白术"],
                        "古籍": ["黄芪", "白术", "茯苓"],
                        "临床": ["黄芪", "甘草"],
                    }
                },
            }
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(result["figure_paths"][0]))
        self.assertEqual(result["figures"][0]["metadata"]["set_count"], 3)

    def test_generate_multiple_figures_in_batch(self):
        result = self.generator.execute(
            {
                "figure_specs": [
                    {
                        "figure_type": "bar",
                        "title": "高频药物分布",
                        "data": {"labels": ["黄芪", "党参"], "values": [5, 4]},
                    },
                    {
                        "figure_type": "scatter",
                        "title": "剂量响应散点图",
                        "data": {"x": [6, 9, 12], "y": [0.32, 0.48, 0.61], "labels": ["低", "中", "高"]},
                    },
                ]
            }
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["generated_count"], 2)
        self.assertEqual(len(result["figure_paths"]), 2)
        for path in result["figure_paths"]:
            self.assertTrue(os.path.exists(path))

    def test_unsupported_figure_type_returns_error_row(self):
        result = self.generator.execute(
            {
                "figure_type": "unknown",
                "title": "未知图",
                "data": {},
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["generated_count"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("不支持的 figure_type", result["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()