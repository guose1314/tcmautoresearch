from src.research.evidence.text_segment_provenance import (
    TextSegmentIndex,
    attach_provenance_to_edges,
    attach_provenance_to_entities,
    attach_provenance_to_research_view,
)


def test_text_segment_index_attaches_required_provenance_fields() -> None:
    raw_text = "伤寒论\n桂枝汤主治营卫不和。\n\n甘草补中。"
    index = TextSegmentIndex(raw_text, document_id="doc-1")
    segment = index.find_for_terms("桂枝汤", "营卫不和")

    assert segment is not None
    payload = segment.to_dict()
    assert payload["document_id"] == "doc-1"
    assert payload["segment_id"].startswith("seg_")
    assert payload["char_start"] < payload["char_end"]
    assert payload["line_start"] <= payload["line_end"]
    assert "桂枝汤主治营卫不和。" in payload["quote_text"]
    assert len(payload["normalization_hash"]) == 64


def test_attach_provenance_to_entities_edges_topics_and_hypotheses() -> None:
    raw_text = "桂枝汤主治营卫不和。\n甘草补中。"
    index = TextSegmentIndex(raw_text, document_id="doc-2")

    entities = attach_provenance_to_entities(
        [{"name": "桂枝汤", "type": "formula", "position": 0}], index
    )
    edges = attach_provenance_to_edges(
        [{"source": "桂枝汤", "target": "营卫不和", "relation": "treats"}], index
    )
    research_view = attach_provenance_to_research_view(
        {
            "community_topics": [{"label": "桂枝汤方证", "member_names": ["桂枝汤"]}],
            "novelty_candidates": [
                {"source": "桂枝汤", "target": "营卫不和", "relation": "treats"}
            ],
            "hypotheses": [
                {"source": "桂枝汤", "target": "营卫不和", "claim": "方证相关"}
            ],
        },
        index,
    )

    assert "桂枝汤主治营卫不和。" in entities[0]["provenance"][0]["quote_text"]
    assert edges[0]["provenance"][0]["document_id"] == "doc-2"
    assert "桂枝汤主治营卫不和。" in edges[0]["evidence"]
    assert research_view["community_topics"][0]["provenance"]
    assert research_view["novelty_candidates"][0]["provenance"]
    assert research_view["hypotheses"][0]["provenance"]
