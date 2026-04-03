import unittest

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.reasoning_engine import ReasoningEngine
from src.analysis.semantic_graph import SemanticGraphBuilder
from src.generation.output_formatter import OutputGenerator


class TestMainFlowSmoke(unittest.TestCase):
    def test_core_pipeline_modules_run_end_to_end(self):
        raw_text = "四君子汤由人参、白术、茯苓、甘草组成，主治脾气虚证，具有补气健脾之功。"

        preprocessor = DocumentPreprocessor({"max_input_chars": 20000})
        self.assertTrue(preprocessor.initialize())
        preprocessed = preprocessor.execute({"raw_text": raw_text})
        self.assertIn("processed_text", preprocessed)
        self.assertIsInstance(preprocessed["processed_text"], str)

        extractor = AdvancedEntityExtractor()
        self.assertTrue(extractor.initialize())
        extracted = extractor.execute({"processed_text": preprocessed["processed_text"]})
        self.assertIn("entities", extracted)
        self.assertIsInstance(extracted["entities"], list)

        builder = SemanticGraphBuilder()
        self.assertTrue(builder.initialize())
        graph_result = builder.execute({"entities": extracted["entities"]})
        self.assertIn("semantic_graph", graph_result)
        self.assertIn("graph_statistics", graph_result)
        self.assertIn("nodes", graph_result["semantic_graph"])
        self.assertIn("edges", graph_result["semantic_graph"])

        reasoning = ReasoningEngine()
        self.assertTrue(reasoning.initialize())
        reasoning_result = reasoning.execute(
            {
                "entities": extracted["entities"],
                "semantic_graph": graph_result["semantic_graph"],
            }
        )
        self.assertIn("reasoning_results", reasoning_result)
        self.assertIn("temporal_analysis", reasoning_result)
        self.assertIn("pattern_recognition", reasoning_result)

        output = OutputGenerator({"max_entities": 200})
        self.assertTrue(output.initialize())
        output_result = output.execute(
            {
                "source_file": "./data/smoke_input.txt",
                "objective": "验证主流程可运行",
                "entities": extracted["entities"],
                "semantic_graph": graph_result["semantic_graph"],
                "reasoning_results": reasoning_result["reasoning_results"],
                "statistics": extracted.get("statistics", {}),
                "confidence_score": extracted.get("confidence_scores", {}).get("average_confidence", 0.5),
            }
        )
        self.assertEqual(output_result.get("output_format"), "structured_json")
        self.assertIn("output_data", output_result)
        self.assertIn("analysis_results", output_result["output_data"])
        self.assertIn("quality_metrics", output_result["output_data"])

        # 资源清理不应抛错
        self.assertTrue(output.cleanup())
        self.assertTrue(reasoning.cleanup())
        self.assertTrue(builder.cleanup())
        self.assertTrue(extractor.cleanup())
        self.assertTrue(preprocessor.cleanup())


if __name__ == "__main__":
    unittest.main()
