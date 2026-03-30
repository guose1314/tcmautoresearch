import unittest

from src.hypothesis.hypothesis_engine import HypothesisEngine
from src.research.research_pipeline import ResearchPhase, ResearchPipeline

SAMPLE_CONTEXT = {
    "research_objective": "验证方剂配伍与脾气虚证之间的稳定关联",
    "research_scope": "中医古籍方剂研究",
    "research_domain": "formula_research",
    "observations": [
        "收集到多个涉及脾气虚证的方剂案例",
        "观察到补气相关功效反复出现",
    ],
    "findings": [
        "四君子汤与脾气虚证的关联在线索中重复出现",
        "人参与补气功效的关系较为稳定",
    ],
    "entities": [
        {"name": "四君子汤", "type": "formula", "confidence": 0.95},
        {"name": "人参", "type": "herb", "confidence": 0.93},
        {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
        {"name": "补气", "type": "efficacy", "confidence": 0.84},
    ],
    "literature_titles": [
        "补气方剂治疗脾气虚证的文献分析",
        "人参功效机制与临床证据回顾",
    ],
    "contradictions": ["部分案例中剂量记录不完整"],
}


class TestHypothesisEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HypothesisEngine({"max_hypotheses": 3, "max_validation_iterations": 2})
        self.engine.initialize()

    def tearDown(self):
        self.engine.cleanup()

    def test_execute_generates_scored_hypotheses(self):
        result = self.engine.execute(SAMPLE_CONTEXT)

        self.assertEqual(result["phase"], "hypothesis")
        self.assertGreaterEqual(len(result["hypotheses"]), 1)
        first = result["hypotheses"][0]
        self.assertIn("scores", first)
        self.assertIn("final_score", first)
        self.assertIn("validation_plan", first)
        self.assertGreater(first["final_score"], 0.0)

    def test_validation_iterations_cover_generated_hypotheses(self):
        result = self.engine.execute(SAMPLE_CONTEXT)

        hypothesis_ids = {item["hypothesis_id"] for item in result["hypotheses"]}
        iteration_ids = {item["hypothesis_id"] for item in result["validation_iterations"]}
        self.assertEqual(hypothesis_ids, iteration_ids)
        self.assertEqual(
            len(result["validation_iterations"]),
            len(result["hypotheses"]) * 2,
        )

    def test_existing_hypotheses_reduce_novelty_score(self):
        prepared = self.engine._prepare_context(SAMPLE_CONTEXT)
        baseline = self.engine._score_hypothesis(
            self.engine._generate_heuristic_hypotheses(prepared)[0],
            prepared,
        )

        prepared_with_existing = self.engine._prepare_context(
            {
                **SAMPLE_CONTEXT,
                "existing_hypotheses": [
                    {"title": baseline.title, "statement": baseline.statement},
                ],
            }
        )
        with_existing = self.engine._score_hypothesis(
            self.engine._generate_heuristic_hypotheses(prepared_with_existing)[0],
            prepared_with_existing,
        )

        self.assertLess(with_existing.scores["novelty"], baseline.scores["novelty"])

    def test_llm_closed_loop_generates_scores_and_revisions(self):
        class FakeLLM:
            def __init__(self):
                self.review_calls = 0

            def generate_research_hypothesis(self, domain, corpus_summary, existing_research=""):
                return "1. 四君子汤可稳定改善脾气虚证\n2. 人参在补气方中的角色与剂量相关"

            def generate(self, prompt, system_prompt=""):
                self.review_calls += 1
                if self.review_calls == 1:
                    return (
                        "verification_score: 0.59\n"
                        "action: revise\n"
                        "note: 证据链还需收敛\n"
                        "revised_statement: 修订后假设：四君子汤核心配伍与脾气虚证存在稳定对应\n"
                        "revised_plan: 先做方剂-证候-功效三元组交叉验证\n"
                    )
                return (
                    "verification_score: 0.83\n"
                    "action: retain\n"
                    "note: 假设达到进入实验阶段标准\n"
                    "revised_statement:\n"
                    "revised_plan:\n"
                )

        result = self.engine.execute(
            {
                **SAMPLE_CONTEXT,
                "use_llm_generation": True,
                "llm_service": FakeLLM(),
            }
        )

        self.assertTrue(result["metadata"]["used_llm_generation"])
        self.assertTrue(result["metadata"]["used_llm_closed_loop"])
        self.assertGreater(result["metadata"]["llm_iteration_count"], 0)
        self.assertTrue(
            any(item["action"] == "revise" for item in result["validation_iterations"])
        )
        self.assertTrue(
            any("修订后假设" in item["statement"] for item in result["hypotheses"])
        )

    def test_parse_llm_feedback_response_normalizes_cn_action_and_score(self):
        payload = self.engine._parse_llm_feedback_response(
            "verification_score: 评分约 0.76\n"
            "action: 降低优先级\n"
            "revised_statement:  修订语句  \n"
            "revised_plan:  修订计划  \n"
        )

        self.assertEqual(payload["action"], "deprioritize")
        self.assertAlmostEqual(payload["verification_score"], 0.76)
        self.assertEqual(payload["revised_statement"], "修订语句")
        self.assertEqual(payload["revised_plan"], "修订计划")

    def test_parse_llm_feedback_response_keeps_invalid_score_text(self):
        payload = self.engine._parse_llm_feedback_response(
            "verification_score: not-a-number\n"
            "action: retain\n"
        )

        self.assertEqual(payload["verification_score"], "not-a-number")
        self.assertEqual(payload["action"], "retain")

    def test_run_llm_closed_loop_skips_when_llm_generation_disabled(self):
        prepared = self.engine._prepare_context(SAMPLE_CONTEXT)
        hypotheses = self.engine._generate_heuristic_hypotheses(prepared)

        iterations = self.engine._run_llm_closed_loop(hypotheses, prepared)

        self.assertEqual(iterations, [])
        self.assertFalse(prepared["used_llm_closed_loop"])


class TestHypothesisEnginePipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.pipeline = ResearchPipeline(
            {
                "hypothesis_engine_config": {
                    "max_hypotheses": 2,
                    "max_validation_iterations": 2,
                }
            }
        )

    def tearDown(self):
        self.pipeline.cleanup()

    def test_pipeline_hypothesis_phase_uses_hypothesis_engine(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="hypothesis-cycle",
            description="hypothesis integration",
            objective=SAMPLE_CONTEXT["research_objective"],
            scope=SAMPLE_CONTEXT["research_scope"],
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": False,
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
                "data_source": "manual",
            },
        )
        result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": SAMPLE_CONTEXT["entities"],
                "literature_titles": SAMPLE_CONTEXT["literature_titles"],
                "contradictions": SAMPLE_CONTEXT["contradictions"],
            },
        )

        self.assertEqual(result["phase"], "hypothesis")
        self.assertIn("validation_iterations", result)
        self.assertEqual(result["metadata"]["hypothesis_count"], len(result["hypotheses"]))
        self.assertGreaterEqual(len(result["hypotheses"]), 1)


if __name__ == "__main__":
    unittest.main()