import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestAnalyzePhaseDegradedStatus(unittest.TestCase):

    def setUp(self):
        self.pipeline = ResearchPipeline({})

    def tearDown(self):
        self.pipeline.cleanup()

    def test_analyze_zero_findings_marks_degraded(self):
        """analyze 阶段 findings==0 时 phase_entry.status 应为 degraded。"""
        cycle = self.pipeline.create_research_cycle(
            cycle_name="degrade-cycle",
            description="degraded test",
            objective="verify degraded status",
            scope="src/research",
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
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT)

        empty_analyze_result = {
            "phase": "analyze",
            "results": {},
            "reasoning_results": {},
            "data_mining_result": {},
            "metadata": {"record_count": 0},
        }
        with patch.object(
            self.pipeline, "_execute_phase_internal", return_value=empty_analyze_result
        ):
            analyze_result = self.pipeline.execute_research_phase(
                cycle.cycle_id, ResearchPhase.ANALYZE
            )

        self.assertEqual(analyze_result["phase"], "analyze")
        self.assertEqual(analyze_result["metadata"]["record_count"], 0)
        self.assertEqual(analyze_result["metadata"]["status"], "degraded")

        phase_history = cycle.metadata["phase_history"]
        analyze_entry = [e for e in phase_history if e["phase"] == "analyze"][-1]
        self.assertEqual(analyze_entry["status"], "degraded")
        self.assertEqual(cycle.metadata["final_status"], "degraded")

    def test_analyze_nonzero_findings_stays_completed(self):
        """analyze 阶段 findings>0 时 phase_entry.status 应保持 completed。"""
        cycle = self.pipeline.create_research_cycle(
            cycle_name="normal-cycle",
            description="normal analyze",
            objective="verify completed status",
            scope="src/research",
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
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT)

        analyze_result = self.pipeline.execute_research_phase(
            cycle.cycle_id, ResearchPhase.ANALYZE
        )

        self.assertEqual(analyze_result["phase"], "analyze")
        self.assertGreater(analyze_result["metadata"]["record_count"], 0)
        self.assertNotIn("status", analyze_result["metadata"])

        phase_history = cycle.metadata["phase_history"]
        analyze_entry = [e for e in phase_history if e["phase"] == "analyze"][-1]
        self.assertEqual(analyze_entry["status"], "completed")


if __name__ == "__main__":
    unittest.main()
