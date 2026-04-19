"""
tests/test_output_generator.py
测试 OutputGenerator 的 JSON / Markdown / DOCX 清晰输出及初始化
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.generation.output_formatter import OutputGenerator
from src.generation.report_generator import Report, ReportFormat, ReportGenerator
from src.infra.layered_cache import LayeredTaskCache


def _phase_result(phase, results=None, metadata=None):
    return {
        "phase": phase,
        "status": "completed",
        "results": results or {},
        "artifacts": [],
        "metadata": metadata or {},
        "error": None,
    }


@pytest.fixture
def generator():
    og = OutputGenerator()
    og.initialize()
    return og


class TestOutputGeneratorInit:
    def test_initialize_success(self):
        og = OutputGenerator()
        result = og.initialize()
        assert result is True
        assert og.initialized is True
        og.cleanup()

    def test_module_name(self):
        og = OutputGenerator()
        assert og.module_name == "output_generator"


class TestToJson:
    def test_dict_to_json(self, generator):
        result = generator.to_json({"key": "value", "num": 42})
        parsed = json.loads(result)
        assert parsed["key"] == "value"
        assert parsed["num"] == 42

    def test_list_to_json(self, generator):
        result = generator.to_json(["甘草", "人参", "黄芪"])
        parsed = json.loads(result)
        assert "甘草" in parsed

    def test_nested_dict_to_json(self, generator):
        data = {"entities": [{"name": "人参", "type": "herb"}], "count": 1}
        result = generator.to_json(data)
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["entities"][0]["name"] == "人参"

    def test_json_is_valid_string(self, generator):
        result = generator.to_json({"a": 1})
        assert isinstance(result, str)
        # Must be valid JSON
        json.loads(result)


class TestToMarkdown:
    def test_dict_produces_markdown(self, generator):
        result = generator.to_markdown({"标题": "人参研究", "摘要": "补气要药"})
        assert "# 中医研究报告" in result
        assert "标题" in result
        assert "人参研究" in result

    def test_nested_dict_markdown(self, generator):
        result = generator.to_markdown({
            "metadata": {"source": "本草纲目", "year": "1596"},
            "entities": ["人参", "黄芪"],
        })
        assert "## metadata" in result
        assert "本草纲目" in result
        assert "人参" in result

    def test_returns_string(self, generator):
        result = generator.to_markdown({"x": 1})
        assert isinstance(result, str)

    def test_contains_timestamp(self, generator):
        result = generator.to_markdown({"a": "b"})
        assert "生成时间" in result


class TestToDict:
    def test_dict_passthrough(self, generator):
        data = {"key": "val"}
        result = generator.to_dict(data)
        assert result == data

    def test_none_returns_empty_dict(self, generator):
        result = generator.to_dict(None)
        assert result == {}

    def test_non_dict_wrapped(self, generator):
        result = generator.to_dict("plain string")
        assert isinstance(result, dict)
        assert "data" in result

    def test_list_wrapped(self, generator):
        result = generator.to_dict([1, 2, 3])
        assert isinstance(result, dict)


class TestEmptyInput:
    def test_to_json_empty_dict(self, generator):
        result = generator.to_json({})
        assert json.loads(result) == {}

    def test_to_json_none(self, generator):
        result = generator.to_json(None)
        parsed = json.loads(result)
        assert parsed is None

    def test_to_markdown_empty_dict(self, generator):
        result = generator.to_markdown({})
        assert isinstance(result, str)
        assert "# 中医研究报告" in result

    def test_to_dict_empty_dict(self, generator):
        result = generator.to_dict({})
        assert result == {}


class TestOutputGeneratorArtifactCache:
    def test_execute_reuses_cached_artifact(self, tmp_path):
        og = OutputGenerator({"max_entities": 10})
        assert og.initialize() is True
        context = {
            "source_file": "input.txt",
            "objective": "验证 artifact cache",
            "entities": [{"name": "黄芪", "type": "herb"}],
            "reasoning_results": {
                "evidence_records": [
                    {
                        "source_entity": "黄芪",
                        "target_entity": "补气",
                        "relation_type": "功效",
                        "confidence": 0.88,
                        "excerpt": "黄芪补气固表",
                        "title": "本草纲目",
                        "source_type": "classic_text",
                        "source_ref": "bencao:013",
                    }
                ]
            },
            "statistics": {"herbs_count": 1},
            "confidence_score": 0.82,
        }

        cache = LayeredTaskCache(
            settings={
                "enabled": True,
                "cache_dir": str(tmp_path),
                "prompt": {"enabled": False},
                "evidence": {"enabled": False},
                "artifact": {"enabled": True, "namespace": "artifact", "ttl_seconds": None},
            }
        )

        try:
            with patch("src.generation.output_formatter.get_layered_task_cache", return_value=cache):
                with patch.object(og, "_generate_output_format", wraps=og._generate_output_format) as wrapped:
                    first = og._do_execute(context)
                    second = og._do_execute(context)
        finally:
            cache.close()
            og.cleanup()

        assert first == second
        assert wrapped.call_count == 1


# ===================================================================
# ReportGenerator — Markdown / DOCX 输出
# ===================================================================

_SESSION_RESULT = {
    "question": "黄芪补气机制研究",
    "metadata": {"research_question": "黄芪补气机制"},
    "phase_results": {
        "observe": _phase_result("observe", {
            "observations": ["黄芪含皂苷类成分", "补气药物长期使用安全性高"],
            "findings": ["黄芪多糖具有免疫调节作用"],
        }),
        "experiment": _phase_result("experiment", {}),
        "analyze": _phase_result("analyze", {}),
    },
}


@pytest.fixture
def report_gen(tmp_path):
    rg = ReportGenerator({"output_dir": str(tmp_path)})
    rg.initialize()
    yield rg
    rg.cleanup()


class TestReportGeneratorMarkdown:
    def test_generate_markdown_report(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, ReportFormat.MARKDOWN)
        assert isinstance(report, Report)
        assert report.format == "markdown"
        assert len(report.content) > 0
        assert "黄芪" in report.content

    def test_report_has_all_imrd_sections(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, "markdown")
        for section in ("introduction", "methods", "results", "discussion"):
            assert section in report.sections
            assert isinstance(report.sections[section], str)

    def test_report_to_dict(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, "markdown")
        d = report.to_dict()
        assert d["title"]
        assert d["format"] == "markdown"
        assert "generated_at" in d["metadata"]

    def test_report_metadata_fields(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, "markdown")
        m = report.metadata
        assert "generated_at" in m
        assert m["research_question"] == "黄芪补气机制研究"
        assert m["section_count"] == 4


class TestReportGeneratorDocx:
    def test_generate_docx_report(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, ReportFormat.DOCX)
        assert report.format == "docx"
        assert report.content  # markdown content still populated

    def test_docx_output_path_exists(self, report_gen):
        report = report_gen.generate_report(_SESSION_RESULT, "docx")
        if report.output_path:
            assert Path(report.output_path).exists()

    def test_invalid_format_raises(self, report_gen):
        with pytest.raises(ValueError, match="不支持的报告格式"):
            report_gen.generate_report(_SESSION_RESULT, "pdf")
