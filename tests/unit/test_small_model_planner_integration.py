from __future__ import annotations

from src.infra.llm_service import prepare_planned_llm_call


class _FakeLLM:
    def __init__(self) -> None:
        self.last_prompt = ""
        self.last_system_prompt = ""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return '{"ok": true}'


def test_prepare_planned_llm_call_wraps_prompt_with_context() -> None:
    llm = _FakeLLM()
    planned = prepare_planned_llm_call(
        phase="hypothesis",
        task_type="hypothesis_generation",
        purpose="hypothesis",
        dossier_sections={
            "objective": "提出黄芪相关假说",
            "evidence": "黄芪与补气证据充足",
        },
        llm_engine=llm,
    )

    assert planned.should_call_llm is True
    proxy = planned.create_proxy()
    proxy.generate("请输出假说 JSON", system_prompt="system")
    assert "规划上下文" in llm.last_prompt
    assert "请输出假说 JSON" in llm.last_prompt
    assert planned.prompt_application["task"] == "hypothesis_generation"


def test_prepare_planned_llm_call_respects_skip_decision() -> None:
    llm = _FakeLLM()
    planned = prepare_planned_llm_call(
        phase="reflect",
        task_type="reflection",
        purpose="reflect",
        dossier_sections={"phase_summary": "已有缓存"},
        llm_engine=llm,
        cache_hit_likelihood=0.95,
    )

    assert planned.should_call_llm is False
    assert planned.fallback_path == "rules_engine"


def test_prepare_planned_llm_call_disables_when_dossier_empty() -> None:
    llm = _FakeLLM()
    planned = prepare_planned_llm_call(
        phase="experiment",
        task_type="protocol_design",
        llm_engine=llm,
        dossier_sections={},
    )

    assert planned.should_call_llm is True
    assert planned.enabled is False