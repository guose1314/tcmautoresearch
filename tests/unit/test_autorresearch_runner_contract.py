import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.autorresearch import autorresearch_runner as runner


def _run_git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if check and completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed


def _write_autorresearch_fixture(root: Path, contract_version: str = "d61.v1") -> None:
    tool_dir = root / "tools" / "autorresearch"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "program.md").write_text("demo program", encoding="utf-8")
    (tool_dir / "train.py").write_text(
        "import argparse\n"
        "import json\n"
        "from pathlib import Path\n"
        "lr = 0.006\n"
        "dropout = 0.2\n"
        "weight_decay = 0.03\n"
        "grad_clip = 1.5\n"
        "batch_size = 96\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--max-seconds', type=int, default=1)\n"
        "parser.add_argument('--log-json', type=str, default='')\n"
        "args = parser.parse_args()\n"
        "val_bpb = 1.0 + abs(lr - 0.0025) * 40 + abs(dropout - 0.1) * 1.5 + abs(weight_decay - 0.015) * 10 + abs(grad_clip - 0.8) * 0.2 + abs(batch_size - 128) / 500\n"
        "vram_peak_mb = int(3500 + batch_size * 2)\n"
        "if args.log_json:\n"
        "    Path(args.log_json).write_text(json.dumps({'val_bpb': val_bpb, 'vram_peak_mb': vram_peak_mb}), encoding='utf-8')\n"
        "print(f'val_bpb={val_bpb:.6f}')\n"
        "print(f'vram_peak_mb={vram_peak_mb}')\n",
        encoding="utf-8",
    )
    (root / "config.yml").write_text(
        "governance:\n"
        "  autorresearch_runner:\n"
        "    minimum_stable_improvement_count: 1\n"
        f"    export_contract_version: \"{contract_version}\"\n",
        encoding="utf-8",
    )


def _init_git_repo(root: Path, *, valid_identity: bool) -> None:
    _run_git(root, "init")
    _run_git(root, "branch", "-M", "main")
    user_name = "AutoResearch Bot" if valid_identity else ""
    user_email = "autorresearch@example.com" if valid_identity else ""
    _run_git(root, "config", "user.name", user_name)
    _run_git(root, "config", "user.email", user_email)
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-m", "initial baseline")


@contextmanager
def _isolated_git_env(extra_env: dict | None = None):
    original = os.environ.copy()
    try:
        os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        os.environ.pop("GIT_AUTHOR_NAME", None)
        os.environ.pop("GIT_AUTHOR_EMAIL", None)
        os.environ.pop("GIT_COMMITTER_NAME", None)
        os.environ.pop("GIT_COMMITTER_EMAIL", None)
        if extra_env:
            os.environ.update(extra_env)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


class TestAutoResearchRunnerContract(unittest.TestCase):
    def test_run_autorresearch_loop_real_git_improved_committed_keeps_contract_fields(self):
        with TemporaryDirectory() as tmp, _isolated_git_env():
            root = Path(tmp)
            _write_autorresearch_fixture(root)
            _init_git_repo(root, valid_identity=True)

            before_head = _run_git(root, "rev-parse", "HEAD").stdout.strip()
            report = runner.run_autorresearch_loop(
                repo=root,
                instruction="优化 val_bpb",
                max_iters=1,
                timeout_seconds=1,
                python_exe=sys.executable,
                strategy="heuristic",
                rollback_mode="restore",
                config_path=root / "config.yml",
                output_path=root / "output" / "autorresearch_report.json",
            )
            after_head = _run_git(root, "rev-parse", "HEAD").stdout.strip()

        self.assertNotEqual(before_head, after_head)
        self.assertEqual(report["history"][1]["status"], "improved_committed")
        self.assertEqual(report["report_metadata"]["contract_version"], "d61.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "export_autorresearch_report")
        self.assertEqual(report["analysis_summary"]["final_status"], "completed")
        self.assertEqual(report["analysis_summary"]["status"], "stable")
        self.assertEqual(report["failed_operations"], [])

    def test_run_autorresearch_loop_real_git_improved_no_commit_keeps_contract_fields(self):
        with TemporaryDirectory() as tmp, _isolated_git_env():
            root = Path(tmp)
            _write_autorresearch_fixture(root)
            _init_git_repo(root, valid_identity=True)
            _run_git(root, "config", "user.name", "")
            _run_git(root, "config", "user.email", "")

            before_head = _run_git(root, "rev-parse", "HEAD").stdout.strip()
            report = runner.run_autorresearch_loop(
                repo=root,
                instruction="优化 val_bpb",
                max_iters=1,
                timeout_seconds=1,
                python_exe=sys.executable,
                strategy="heuristic",
                rollback_mode="restore",
                config_path=root / "config.yml",
                output_path=root / "output" / "autorresearch_report.json",
            )
            after_head = _run_git(root, "rev-parse", "HEAD").stdout.strip()

        self.assertEqual(before_head, after_head)
        self.assertEqual(report["history"][1]["status"], "improved_no_commit")
        self.assertEqual(report["report_metadata"]["contract_version"], "d61.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "export_autorresearch_report")
        self.assertEqual(report["analysis_summary"]["improved_iteration_count"], 1)
        self.assertEqual(report["analysis_summary"]["status"], "stable")
        self.assertEqual(report["failed_operations"][0]["operation"], "git_commit_train")

    def test_cli_exports_report_with_stable_phase_metadata(self):
        source_runner = Path(__file__).resolve().parents[2] / "tools" / "autorresearch" / "autorresearch_runner.py"

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "tools" / "autorresearch"
            tool_dir.mkdir(parents=True)
            shutil.copy2(source_runner, tool_dir / "autorresearch_runner.py")
            _write_autorresearch_fixture(root)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(tool_dir / "autorresearch_runner.py"),
                    "--instruction",
                    "优化 val_bpb",
                    "--max-iters",
                    "1",
                    "--timeout-seconds",
                    "1",
                    "--python-exe",
                    sys.executable,
                    "--config",
                    "config.yml",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            self.assertIn("best_val_bpb=", completed.stdout)
            self.assertIn("report=", completed.stdout)

            output_path = root / "output" / "autorresearch_report.json"
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["report_metadata"]["contract_version"], "d61.v1")
        self.assertEqual(payload["metadata"]["last_completed_phase"], "export_autorresearch_report")
        self.assertEqual(payload["analysis_summary"]["status"], "stable")
        self.assertGreaterEqual(payload["analysis_summary"]["improved_iteration_count"], 1)

    def test_run_autorresearch_loop_exports_governed_report(self):
        original_run_training = runner.run_training
        original_patch_train = runner.patch_train
        original_git_commit = runner.git_commit_train
        original_git_rollback = runner.git_rollback_train
        original_run_cmd = runner.run_cmd
        try:
            def fake_run_training(repo, python_exe, timeout_s, trial_idx):
                if trial_idx == 0:
                    return runner.TrialResult(True, 1.25, 4096, "baseline", "", 0.1, False)
                return runner.TrialResult(True, 1.1, 4000, "trial", "", 0.2, False)

            runner.run_training = fake_run_training
            runner.patch_train = lambda train_path, hp: None
            runner.git_commit_train = lambda repo, msg: True
            runner.git_rollback_train = lambda repo, mode: None
            runner.run_cmd = lambda cmd, cwd: (0, "", "")

            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                tool_dir = root / "tools" / "autorresearch"
                tool_dir.mkdir(parents=True)
                (tool_dir / "program.md").write_text("demo program", encoding="utf-8")
                (tool_dir / "train.py").write_text("lr = 0.001\ndropout = 0.1\nweight_decay = 0.01\ngrad_clip = 1.0\nbatch_size = 64\n", encoding="utf-8")
                config_path = root / "config.yml"
                config_path.write_text(
                    "governance:\n"
                    "  autorresearch_runner:\n"
                    "    minimum_stable_improvement_count: 1\n"
                    "    export_contract_version: \"d61.v1\"\n",
                    encoding="utf-8",
                )
                output_path = root / "output" / "autorresearch_report.json"

                report = runner.run_autorresearch_loop(
                    repo=root,
                    instruction="优化 val_bpb",
                    max_iters=1,
                    timeout_seconds=1,
                    python_exe="python",
                    strategy="heuristic",
                    rollback_mode="restore",
                    config_path=config_path,
                    output_path=output_path,
                )

                self.assertTrue(output_path.exists())
                payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(report["report_metadata"]["contract_version"], "d61.v1")
            self.assertEqual(payload["report_metadata"]["contract_version"], "d61.v1")
            self.assertEqual(payload["metadata"]["last_completed_phase"], "export_autorresearch_report")
            self.assertEqual(payload["analysis_summary"]["improved_iteration_count"], 1)
            self.assertEqual(payload["analysis_summary"]["status"], "stable")
            self.assertIn("failed_operations", payload)
        finally:
            runner.run_training = original_run_training
            runner.patch_train = original_patch_train
            runner.git_commit_train = original_git_commit
            runner.git_rollback_train = original_git_rollback
            runner.run_cmd = original_run_cmd

    def test_syntax_fail_is_recorded_in_failed_operations(self):
        original_run_training = runner.run_training
        original_patch_train = runner.patch_train
        original_git_commit = runner.git_commit_train
        original_git_rollback = runner.git_rollback_train
        original_run_cmd = runner.run_cmd
        try:
            rollback_calls = []

            def fake_run_training(repo, python_exe, timeout_s, trial_idx):
                return runner.TrialResult(True, 1.25, 4096, "baseline", "", 0.1, False)

            runner.run_training = fake_run_training
            runner.patch_train = lambda train_path, hp: None
            runner.git_commit_train = lambda repo, msg: True
            runner.git_rollback_train = lambda repo, mode: rollback_calls.append((str(repo), mode))
            runner.run_cmd = lambda cmd, cwd: (1, "", "syntax error")

            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                tool_dir = root / "tools" / "autorresearch"
                tool_dir.mkdir(parents=True)
                (tool_dir / "program.md").write_text("demo program", encoding="utf-8")
                (tool_dir / "train.py").write_text("lr = 0.001\n", encoding="utf-8")
                config_path = root / "config.yml"
                config_path.write_text(
                    "governance:\n"
                    "  autorresearch_runner:\n"
                    "    minimum_stable_improvement_count: 1\n"
                    "    export_contract_version: \"d61.v1\"\n",
                    encoding="utf-8",
                )

                report = runner.run_autorresearch_loop(
                    repo=root,
                    instruction="优化 val_bpb",
                    max_iters=1,
                    timeout_seconds=1,
                    python_exe="python",
                    strategy="heuristic",
                    rollback_mode="restore",
                    config_path=config_path,
                    output_path=root / "output" / "autorresearch_report.json",
                )

            self.assertEqual(report["history"][-1]["status"], "syntax_fail")
            self.assertEqual(report["failed_operations"][0]["operation"], "syntax_check")
            self.assertEqual(report["analysis_summary"]["syntax_failure_count"], 1)
            self.assertEqual(report["analysis_summary"]["status"], "needs_followup")
            self.assertEqual(len(rollback_calls), 1)
        finally:
            runner.run_training = original_run_training
            runner.patch_train = original_patch_train
            runner.git_commit_train = original_git_commit
            runner.git_rollback_train = original_git_rollback
            runner.run_cmd = original_run_cmd


if __name__ == "__main__":
    unittest.main()