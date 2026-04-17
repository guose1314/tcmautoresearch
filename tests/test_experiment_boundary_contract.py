"""实验边界契约测试。

验证 experiment = 方案设计（protocol design only）、
experiment_execution = 外部结果导入（external result import only）
在标签、元数据和运行时守卫中保持一致。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict


# ---------------------------------------------------------------------------
# 1. 标签 / 显示名一致性
# ---------------------------------------------------------------------------

class TestExperimentBoundaryLabels(unittest.TestCase):
    """experiment / experiment_execution 阶段标签必须体现边界语义。"""

    def test_experiment_execution_display_name(self):
        from src.research.phases.experiment_execution_phase import _EXECUTION_DISPLAY_NAME
        self.assertIn("外部", _EXECUTION_DISPLAY_NAME)
        self.assertIn("导入", _EXECUTION_DISPLAY_NAME)
        self.assertNotIn("执行阶段", _EXECUTION_DISPLAY_NAME.replace("结果导入阶段", ""))

    def test_experiment_execution_boundary_notice(self):
        from src.research.phases.experiment_execution_phase import _EXECUTION_BOUNDARY_NOTICE
        self.assertIn("仅接收外部", _EXECUTION_BOUNDARY_NOTICE)
        self.assertIn("不在系统内自动开展真实实验", _EXECUTION_BOUNDARY_NOTICE)

    def test_experiment_phase_display_name(self):
        from src.research.phases.experiment_phase import _PROTOCOL_DESIGN_DISPLAY_NAME
        self.assertIn("方案", _PROTOCOL_DESIGN_DISPLAY_NAME)

    def test_experiment_phase_boundary_notice(self):
        from src.research.phases.experiment_phase import _PROTOCOL_DESIGN_BOUNDARY_NOTICE
        self.assertIn("仅生成研究协议", _PROTOCOL_DESIGN_BOUNDARY_NOTICE)
        self.assertIn("不执行真实实验", _PROTOCOL_DESIGN_BOUNDARY_NOTICE)

    def test_phase_labels_contain_boundary_info(self):
        from src.api.research_utils import PHASE_LABELS
        self.assertIn("方案", PHASE_LABELS["experiment"])
        self.assertIn("外部", PHASE_LABELS["experiment_execution"])
        self.assertIn("导入", PHASE_LABELS["experiment_execution"])

    def test_study_session_enum_comments(self):
        """ResearchPhase 枚举值正确。"""
        from src.research.study_session_manager import ResearchPhase
        self.assertEqual(ResearchPhase.EXPERIMENT.value, "experiment")
        self.assertEqual(ResearchPhase.EXPERIMENT_EXECUTION.value, "experiment_execution")


# ---------------------------------------------------------------------------
# 2. 仪表板 PHASES 列表
# ---------------------------------------------------------------------------

class TestDashboardPhases(unittest.TestCase):
    """仪表板流程卡片应包含 experiment 和 experiment_execution。"""

    def _get_phases(self):
        """从 dashboard 源码提取 PHASES 定义需要 import 整个模块，
        此处直接验证 reference_constants 中的 research_phases 列表。"""
        import yaml
        from pathlib import Path

        constants_path = Path(__file__).resolve().parents[1] / "config" / "reference_constants.yml"
        with open(constants_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data["research_system_config"]["research_phases"]

    def test_phases_include_experiment_design(self):
        phases = self._get_phases()
        self.assertTrue(
            any("实验方案" in p for p in phases),
            f"research_phases 缺少实验方案设计: {phases}",
        )

    def test_phases_include_external_import(self):
        phases = self._get_phases()
        self.assertTrue(
            any("导入" in p for p in phases),
            f"research_phases 缺少外部实验结果导入: {phases}",
        )

    def test_phases_no_bare_experiment(self):
        """不应出现单独的 '实验' 标签（歧义，容易高估平台能力）。"""
        phases = self._get_phases()
        for p in phases:
            if p == "实验":
                self.fail(f"research_phases 包含歧义标签 '实验'，应改为更明确的表述")


# ---------------------------------------------------------------------------
# 3. 理论框架数据结构
# ---------------------------------------------------------------------------

class TestTheoreticalFrameworkBoundary(unittest.TestCase):
    """ResearchExperiment 数据类必须明确仅为方案模板。"""

    def test_experiment_dataclass_docstring(self):
        from src.research.theoretical_framework import ResearchExperiment
        doc = ResearchExperiment.__doc__ or ""
        self.assertIn("方案", doc)
        self.assertNotIn("真实执行", doc.replace("不代表系统内真实执行", ""))

    def test_phase_field_no_executing(self):
        """phase 字段的有效值不应暗示系统内执行。"""
        from src.research.theoretical_framework import ResearchExperiment
        import inspect
        src = inspect.getsource(ResearchExperiment)
        self.assertNotIn("executing", src)


# ---------------------------------------------------------------------------
# 4. phase_orchestrator 工件类型
# ---------------------------------------------------------------------------

class TestPhaseOrchestratorArtifact(unittest.TestCase):
    """experiment 阶段产物类型应为 protocol 而非 dataset。"""

    def test_experiment_artifact_type_is_protocol(self):
        from src.research.phase_orchestrator import PhaseOrchestrator

        orch = PhaseOrchestrator.__new__(PhaseOrchestrator)
        result = orch._infer_artifact_type("experiment", "study_protocol", "protocol.json")
        self.assertEqual(result, "protocol")

    def test_experiment_artifact_not_dataset(self):
        from src.research.phase_orchestrator import PhaseOrchestrator

        orch = PhaseOrchestrator.__new__(PhaseOrchestrator)
        result = orch._infer_artifact_type("experiment", "study_protocol", "protocol.json")
        self.assertNotEqual(result, "dataset")


# ---------------------------------------------------------------------------
# 5. 运行时边界守卫
# ---------------------------------------------------------------------------

class TestExperimentExecutionBoundaryGuard(unittest.TestCase):
    """experiment_execution 阶段必须拒绝自动执行请求。"""

    _VIOLATION_KEYS = ["auto_execute", "run_experiment", "execute_internally", "auto_run"]

    def _make_mixin(self):
        from src.research.phases.experiment_execution_phase import ExperimentExecutionPhaseMixin
        from src.research.study_session_manager import ResearchPhase

        class FakePipeline:
            config = {}

        FakePipeline.ResearchPhase = ResearchPhase

        mixin = ExperimentExecutionPhaseMixin()
        mixin.pipeline = FakePipeline()
        return mixin

    def _make_cycle(self):
        from unittest.mock import MagicMock

        cycle = MagicMock()
        cycle.phases = {}
        return cycle

    def test_auto_execute_rejected(self):
        mixin = self._make_mixin()
        cycle = self._make_cycle()
        for key in self._VIOLATION_KEYS:
            result = mixin.execute_experiment_execution_phase(cycle, {key: True})
            self.assertEqual(result["status"], "error", f"key={key} 应触发边界拒绝")
            meta = result.get("metadata", {})
            self.assertTrue(meta.get("boundary_violation"), f"key={key}")
            self.assertIn(key, meta.get("rejected_keys", []))

    def test_normal_context_not_rejected(self):
        mixin = self._make_mixin()
        cycle = self._make_cycle()
        result = mixin.execute_experiment_execution_phase(cycle, {})
        self.assertNotEqual(result.get("status"), "error")
        meta = result.get("metadata", {})
        self.assertFalse(meta.get("boundary_violation", False))


# ---------------------------------------------------------------------------
# 6. API 阶段枚举
# ---------------------------------------------------------------------------

class TestResearchApiPhaseEnum(unittest.TestCase):
    """API 阶段枚举应包含 experiment_execution。"""

    def test_execute_phase_request_allows_experiment_execution(self):
        from src.web.routes.research import ExecutePhaseRequest
        req = ExecutePhaseRequest(phase="experiment_execution")
        self.assertEqual(req.phase, "experiment_execution")


if __name__ == "__main__":
    unittest.main()
