import unittest
from unittest.mock import patch

from src.analysis.preprocessor import DocumentPreprocessor
from src.generation.output_formatter import OutputGenerator


class TestDocumentPreprocessorQuality(unittest.TestCase):
    def test_preprocessor_sanitizes_and_normalizes_text(self):
        module = DocumentPreprocessor({"max_input_chars": 1000})
        self.assertTrue(module.initialize())

        result = module.execute({"raw_text": "小柴胡\x00汤  \n\n\n 主治"})
        text = result["processed_text"]

        self.assertNotIn("\x00", text)
        self.assertNotIn("\n\n\n", text)
        self.assertIn("小柴胡", text)
        self.assertIn("主治", text)

    def test_preprocessor_rejects_non_string_input(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())

        with self.assertRaises(ValueError):
            module.execute({"raw_text": 12345})

    def test_preprocessor_rejects_oversized_input(self):
        module = DocumentPreprocessor({"max_input_chars": 5})
        self.assertTrue(module.initialize())

        with self.assertRaises(ValueError):
            module.execute({"raw_text": "123456"})

    def test_internal_text_helpers(self):
        module = DocumentPreprocessor()
        self.assertEqual(module._sanitize_text("a\x00b\x01c"), "abc")
        self.assertEqual(module._clean_line_breaks("ab\ncd\n\n\nxy"), "abcd\n\nxy")
        self.assertEqual(module._normalize_whitespace("a   b\n c"), "a b c")

    def test_segment_and_ancient_punctuation(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())

        words = module.segment_text("小柴胡汤")
        self.assertGreater(len(words), 0)

        words_pos = module.segment_text("小柴胡汤", use_pos=True)
        self.assertGreater(len(words_pos), 0)

        sentences = module.segment_with_ancient_punctuation("主治寒热往来。功效和解少阳")
        self.assertGreater(len(sentences), 0)
        self.assertTrue(all(isinstance(sentence, list) for sentence in sentences))

    def test_estimate_token_count_fallback(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())
        with patch.object(module, "segment_text", side_effect=RuntimeError("segment fail")):
            count = module._estimate_token_count("a b c")
        self.assertEqual(count, 3)

    def test_extract_metadata_and_cleanup(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())

        md = module._extract_metadata(
            {
                "source_file": "demo.txt",
                "raw_text": "abc",
                "metadata": {"dynasty": "东汉"},
            }
        )
        self.assertEqual(md["source_file"], "demo.txt")
        self.assertEqual(md["dynasty"], "东汉")
        self.assertEqual(md["encoding_detected"], "utf-8")
        self.assertTrue(module.cleanup())

    def test_missing_raw_text_raises(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())
        with self.assertRaises(ValueError):
            module.execute({})

    def test_convert_text_fallback_on_converter_error(self):
        class BrokenOpenCC:
            def convert(self, _text):
                raise RuntimeError("boom")

        module = DocumentPreprocessor()
        module._opencc = BrokenOpenCC()
        self.assertEqual(module._convert_text("abc"), "abc")

    def test_segment_text_fallback_when_no_jieba(self):
        module = DocumentPreprocessor()
        with patch("src.analysis.preprocessor.HAS_JIEBA", False):
            out = module.segment_text("a b c")
        self.assertEqual(out, ["a", "b", "c"])

    def test_segment_text_fallback_on_cut_error(self):
        module = DocumentPreprocessor()
        self.assertTrue(module.initialize())
        with patch("src.analysis.preprocessor.jieba.cut", side_effect=RuntimeError("bad cut")):
            out = module.segment_text("a b c")
        self.assertEqual(out, ["a", "b", "c"])

    def test_detect_encoding_fallback_branch(self):
        module = DocumentPreprocessor()

        class BadText:
            def encode(self, _enc):
                raise RuntimeError("encode failed")

        self.assertEqual(module._detect_encoding(BadText()), "utf-8")

    def test_initialize_with_disabled_optional_dependencies(self):
        module = DocumentPreprocessor({"convert_mode": "t2s"})
        with patch("src.analysis.preprocessor.HAS_JIEBA", False), patch(
            "src.analysis.preprocessor.HAS_OPENCC", False
        ):
            self.assertTrue(module.initialize())

    def test_cleanup_exception_path(self):
        module = DocumentPreprocessor()
        with patch.object(module.logger, "info", side_effect=RuntimeError("logger fail")):
            self.assertFalse(module._do_cleanup())


class TestOutputGeneratorQuality(unittest.TestCase):
    def test_output_generator_sanitizes_source_and_limits_entities(self):
        module = OutputGenerator({"max_entities": 2, "max_string_length": 32})
        self.assertTrue(module.initialize())

        result = module.execute(
            {
                "source_file": "../secret/path/input.txt",
                "objective": "A" * 100,
                "entities": [1, 2, 3, 4],
                "statistics": {"formulas_count": -1, "herbs_count": -2, "syndromes_count": -3},
                "reasoning_results": {"unsafe": object()},
            }
        )

        output_data = result["output_data"]
        metadata = output_data["metadata"]
        analysis = output_data["analysis_results"]
        quality = output_data["quality_metrics"]

        self.assertEqual(metadata["source"], "input.txt")
        self.assertEqual(len(analysis["entities"]), 2)
        self.assertGreaterEqual(quality["formulas_found"], 0)
        self.assertGreaterEqual(quality["herbs_identified"], 0)
        self.assertGreaterEqual(quality["syndromes_recognized"], 0)

    def test_output_generator_returns_json_safe_payload(self):
        module = OutputGenerator({"max_entities": 10, "max_string_length": 16})
        self.assertTrue(module.initialize())

        result = module.execute(
            {
                "entities": ["a"],
                "reasoning_results": {"nested": {"obj": object()}},
            }
        )

        output_data = result["output_data"]
        unsafe_value = output_data["analysis_results"]["reasoning_results"]["nested"]["obj"]

        self.assertIsInstance(unsafe_value, str)
        self.assertLessEqual(len(unsafe_value), 16)

    def test_output_recommendations_and_cleanup(self):
        module = OutputGenerator({"max_recommendations": 1})
        self.assertTrue(module.initialize())

        recs = module._build_recommendations({"entities": [1, 2], "confidence_score": 0.6})
        self.assertEqual(len(recs), 1)

        recs_many = module._build_recommendations({"entities": list(range(80)), "confidence_score": 0.99})
        self.assertEqual(len(recs_many), 1)
        self.assertTrue(module.cleanup())

    def test_output_recommendations_handles_bad_confidence(self):
        module = OutputGenerator({"max_recommendations": 5})
        self.assertTrue(module.initialize())

        recs = module._build_recommendations({"entities": [1, 2], "confidence_score": "bad"})
        self.assertIn("置信度较低，建议人工复核", recs)

    def test_output_quality_metrics_handles_non_numeric_statistics(self):
        module = OutputGenerator()
        self.assertTrue(module.initialize())

        metrics = module._calculate_quality_metrics(
            {
                "entities": [1],
                "statistics": {
                    "formulas_count": "x",
                    "herbs_count": None,
                    "syndromes_count": "-2",
                },
            }
        )
        self.assertEqual(metrics["formulas_found"], 0)
        self.assertEqual(metrics["herbs_identified"], 0)
        self.assertEqual(metrics["syndromes_recognized"], 0)

    def test_output_generator_includes_research_artifact_contract_v30(self):
        module = OutputGenerator({"max_entities": 5})
        self.assertTrue(module.initialize())

        result = module.execute(
            {
                "entities": [{"name": "桂枝"}],
                "analysis_results": {
                    "evidence_grade_summary": {
                        "overall_grade": "moderate",
                        "overall_score": 0.67,
                        "study_count": 3,
                        "bias_risk_distribution": {"low": 1, "moderate": 2},
                        "summary": ["纳入 3 项研究进行 GRADE 评估"],
                    }
                },
                "hypothesis": [{
                    "title": "桂枝汤调和营卫",
                    "mechanism_completeness": 0.84,
                    "audit": {
                        "relationship_count": 2,
                        "merged_sources": ["observe_reasoning_engine", "observe_semantic_graph"],
                    },
                }],
                "reasoning_results": {
                    "evidence_records": [{"evidence_id": "ev-1", "source_entity": "桂枝", "target_entity": "营卫"}]
                },
                "data_mining_result": {"clusters": [{"label": "方剂A"}]},
            }
        )

        payload = result["output_data"]
        self.assertEqual(payload["metadata"]["architecture_version"], "3.0-draft")
        self.assertIn("ResearchArtifact", payload["generation_contract"]["name"])
        self.assertIn("hypothesis", payload["research_artifact"])
        self.assertIn("hypothesis_audit_summary", payload["research_artifact"])
        self.assertIn("evidence_grade_summary", payload["research_artifact"])
        self.assertIn("evidence", payload["research_artifact"])
        self.assertIn("data_mining_result", payload["research_artifact"])
        self.assertIn("similar_formula_graph_evidence_summary", payload["research_artifact"])
        self.assertEqual(payload["research_artifact"]["hypothesis"][0]["title"], "桂枝汤调和营卫")
        self.assertEqual(payload["research_artifact"]["hypothesis_audit_summary"]["selected_mechanism_completeness"], 0.84)
        self.assertIn("observe_reasoning_engine", payload["research_artifact"]["hypothesis_audit_summary"]["merged_sources"])
        self.assertEqual(payload["research_artifact"]["evidence_grade_summary"]["overall_grade"], "moderate")
        self.assertEqual(payload["research_artifact"]["evidence"][0]["evidence_id"], "ev-1")

    def test_output_generator_summarizes_similar_formula_graph_evidence(self):
        module = OutputGenerator({"max_entities": 5})
        self.assertTrue(module.initialize())

        result = module.execute(
            {
                "research_perspectives": {
                    "四君子汤": {
                        "integrated": {
                            "similar_formula_matches": [
                                {
                                    "formula_name": "六君子汤",
                                    "similarity_score": 0.91,
                                    "retrieval_sources": ["embedding", "relationship_reasoning"],
                                    "graph_evidence": {
                                        "source": "neo4j+relationship_reasoning",
                                        "evidence_score": 0.92,
                                        "shared_herbs": [
                                            {"herb": "人参"},
                                            {"herb": "白术"},
                                        ],
                                        "shared_syndromes": ["脾气虚证"],
                                        "shared_herb_count": 2,
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        )

        summary = result["output_data"]["research_artifact"]["similar_formula_graph_evidence_summary"]
        self.assertEqual(summary["formula_count"], 1)
        self.assertEqual(summary["match_count"], 1)
        self.assertEqual(summary["matches"][0]["formula_name"], "四君子汤")
        self.assertEqual(summary["matches"][0]["similar_formula_name"], "六君子汤")
        self.assertEqual(summary["matches"][0]["graph_evidence_source"], "neo4j+relationship_reasoning")
        self.assertEqual(summary["matches"][0]["shared_herbs"], ["人参", "白术"])
        self.assertEqual(summary["matches"][0]["shared_syndromes"], ["脾气虚证"])

    def test_make_json_safe_depth_limit(self):
        module = OutputGenerator({"max_string_length": 8})
        self.assertTrue(module.initialize())

        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": "too deep"}}}}}}}}}
        safe = module._make_json_safe(deep)
        # 深度超过限制时会被截断为标记字符串
        self.assertIn("a", safe)

    def test_execute_exception_path(self):
        class BrokenOutput(OutputGenerator):
            def _generate_output_format(self, context):
                raise RuntimeError("broken")

        module = BrokenOutput()
        self.assertTrue(module.initialize())
        with self.assertRaises(RuntimeError):
            module.execute({"entities": []})

    def test_initialize_and_cleanup_exception_paths(self):
        module = OutputGenerator()
        with patch.object(module.logger, "info", side_effect=RuntimeError("logger fail")):
            self.assertFalse(module._do_initialize())
            self.assertFalse(module._do_cleanup())


if __name__ == "__main__":
    unittest.main()
