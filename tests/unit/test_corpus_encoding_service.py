from __future__ import annotations

import time

from src.ingestion.corpus_encoding_service import CorpusEncodingService


def test_gb18030_text_is_decoded_and_newlines_are_normalized(tmp_path):
    path = tmp_path / "医案.txt"
    path.write_bytes("桂枝汤\r\n主治风寒".encode("gb18030"))

    result = CorpusEncodingService().standardize_file(path)

    assert result.text == "桂枝汤\n主治风寒"
    assert result.encoding_report.decoder_encoding in {"gb18030", "gbk"}
    assert result.encoding_report.normalized_newlines is True
    assert result.encoding_report.anomalous_character_ratio == 0.0


def test_big5_traditional_text_is_decoded(tmp_path):
    path = tmp_path / "繁體古籍.txt"
    expected = "陰陽表裡\n醫方證治"
    path.write_bytes(expected.encode("big5"))

    result = CorpusEncodingService().standardize_file(path)

    assert result.text == expected
    assert result.encoding_report.decoder_encoding in {"big5", "gb18030"}
    assert "陰陽" in result.text


def test_mojibake_filename_gets_repair_suggestion():
    service = CorpusEncodingService()
    expected = "家传女科经验摘奇.txt"
    mojibake = expected.encode("utf-8").decode("gb18030")

    repaired, strategy = service.suggest_filename_repair(mojibake)

    assert repaired == expected
    assert strategy in {"gb18030->utf-8", "gbk->utf-8"}


def test_empty_file_reports_empty_text(tmp_path):
    path = tmp_path / "空文献.txt"
    path.write_bytes(b"")

    result = CorpusEncodingService().standardize_file(path)

    assert result.text == ""
    assert result.encoding_report.empty is True
    assert result.encoding_report.detected_encoding == "empty"
    assert result.encoding_report.confidence == 1.0


def test_large_file_keeps_full_text_and_builds_identity(tmp_path):
    path = tmp_path / "173-家传女科经验摘奇-清-王氏.txt"
    text = "桂枝汤主治营卫不和。\n" * 6000
    path.write_bytes(text.encode("utf-8"))

    result = CorpusEncodingService().standardize_file(path)

    assert result.text == text
    assert result.canonical_identity.canonical_title == "家传女科经验摘奇"
    assert result.canonical_identity.normalized_title == "家传女科经验摘奇"
    assert result.canonical_identity.dynasty == "清"
    assert result.canonical_identity.author == "王氏"
    assert result.canonical_identity.canonical_document_key


def test_batch_distill_payload_contains_encoding_metadata(tmp_path, monkeypatch):
    import tools.batch_distill_corpus as batch

    path = tmp_path / "医案.txt"
    path.write_bytes("桂枝汤主治营卫不和".encode("gb18030"))
    captured = {}

    class Response:
        status_code = 200
        headers = {}
        text = ""

        def json(self):
            return {
                "llm_extracted": {},
                "rule_extracted": {},
                "merged": {},
                "knowledge_accumulation": {},
                "research_enhancement": {},
                "graph_rag": {
                    "trace_id": "graphrag-trace:test-batch",
                    "retrieval_trace": {"trace_id": "graphrag-trace:test-batch"},
                },
            }

    def fake_post(url, json, headers, timeout):
        captured["payload"] = json
        return Response()

    monkeypatch.setattr(batch.requests, "post", fake_post)
    result = batch.distill_one(
        "http://127.0.0.1:8765",
        {"access_token": "token", "expires_at": time.time() + 3600},
        path,
        max_bytes=0,
        timeout=30,
        timeout_per_kchar=1,
        timeout_cap=30,
    )

    assert result["ok"] is True
    assert result["encoding_report"]["decoder_encoding"] in {"gb18030", "gbk"}
    assert captured["payload"]["metadata"]["encoding_report"]
    assert captured["payload"]["metadata"]["canonical_document_identity"]
    assert result["research"]["graph_rag_trace_id"] == "graphrag-trace:test-batch"
