from __future__ import annotations

import json

from src.contexts.llm_reasoning import (
    PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION,
    SUPPORTED_PHILOLOGY_TEMPLATE_TASKS,
    render_philology_reasoning_prompt,
    select_philology_reasoning_template,
)
from src.research.research_pipeline import ResearchPipeline


def test_philology_templates_cover_required_tasks() -> None:
    assert SUPPORTED_PHILOLOGY_TEMPLATE_TASKS == (
        "entity_extraction",
        "relation_judgement",
        "variant_comparison",
        "evidence_grading",
        "hypothesis_generation",
        "counter_evidence_retrieval",
    )
    for task_type in SUPPORTED_PHILOLOGY_TEMPLATE_TASKS:
        template = select_philology_reasoning_template(task_type)
        payload = template.to_dict()
        assert (
            payload["contract_version"] == PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION
        )
        assert payload["role"]
        assert payload["input_schema"]
        assert payload["output_schema"]
        assert payload["forbidden_items"]
        assert payload["evidence_requirements"]
        assert payload["version"]
        json.dumps(payload, ensure_ascii=False)


def test_rendered_template_records_version_and_schema() -> None:
    rendered = render_philology_reasoning_prompt(
        "entity_extraction",
        payload={"text": "桂枝汤主治营卫不和。"},
        context={"route": "analysis.distill"},
    )

    assert "桂枝汤主治营卫不和" in rendered.user_prompt
    assert "输出 schema" in rendered.user_prompt
    assert rendered.system_prompt
    assert rendered.metadata["task_type"] == "entity_extraction"
    assert rendered.metadata["template_version"] == "1.0.0"


def test_unknown_template_task_falls_back_to_entity_extraction() -> None:
    template = select_philology_reasoning_template("unknown-task")

    assert template.task_type == "entity_extraction"


def test_research_pipeline_can_select_and_render_template() -> None:
    pipeline = ResearchPipeline.__new__(ResearchPipeline)

    template = pipeline.select_llm_reasoning_template("hypothesis_generation", {})
    rendered = pipeline.render_llm_reasoning_template(
        "hypothesis_generation",
        payload={"research_objective": "桂枝汤方证研究", "knowledge_gap": {}},
        context={"phase": "hypothesis"},
    )

    assert template["task_type"] == "hypothesis_generation"
    assert template["version"] == "1.0.0"
    assert rendered["metadata"]["template_version"] == "1.0.0"
    assert "桂枝汤方证研究" in rendered["user_prompt"]
