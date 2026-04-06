import logging
import unittest

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_core_demo_handler import execute_core_demo_workflow_handler


class TestCycleCoreDemoHandler(unittest.TestCase):
    def test_basic_demo_runs_full_cycle(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--demo-type", "basic", "--iterations", "5"])
        calls = []

        def fake_full(**kwargs):
            calls.append(("full", kwargs))
            return {"status": "completed"}

        rc = execute_core_demo_workflow_handler(
            args=args,
            logger=logging.getLogger("test.cycle.core"),
            run_full_cycle_demo_fn=fake_full,
            run_academic_demo_fn=lambda *_args, **_kwargs: {"status": "completed"},
            run_performance_demo_fn=lambda *_args, **_kwargs: {"status": "completed"},
        )

        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("full", {"max_iterations": 5})])

    def test_full_demo_runs_three_core_demos(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--demo-type", "full"])
        order = []

        def fake_full(**_kwargs):
            order.append("full")
            return {"status": "completed"}

        def fake_academic(*_args, **_kwargs):
            order.append("academic")
            return {"status": "completed"}

        def fake_performance(*_args, **_kwargs):
            order.append("performance")
            return {"status": "completed"}

        rc = execute_core_demo_workflow_handler(
            args=args,
            logger=logging.getLogger("test.cycle.core"),
            run_full_cycle_demo_fn=fake_full,
            run_academic_demo_fn=fake_academic,
            run_performance_demo_fn=fake_performance,
        )

        self.assertEqual(rc, 0)
        self.assertEqual(order, ["full", "academic", "performance"])


if __name__ == "__main__":
    unittest.main()