from src.extraction.rule_relation_quality import (
    is_promotable_rule_edge,
    rule_quality_tier_counts,
    tier_rule_edges,
)


def test_tier_rule_edges_outputs_all_rule_quality_layers() -> None:
    raw_text = "桂枝汤主治营卫不和。"
    entities = [
        {"name": "桂枝汤", "type": "formula", "position": 0},
        {"name": "营卫不和", "type": "syndrome", "position": 6},
        {"name": "甘草", "type": "herb", "position": 0},
    ]
    edges = [
        {
            "source": "桂枝汤",
            "target": "营卫不和",
            "relation": "treats",
            "attributes": {"confidence": 0.95},
        },
        {
            "source": "桂枝汤",
            "target": "营卫不和",
            "relation": "treats",
            "attributes": {"confidence": 0.45},
        },
        {
            "source": "四君子汤",
            "target": "脾虚",
            "relation": "treats",
            "attributes": {"confidence": 0.95},
        },
        {
            "source": "未知方",
            "target": "未知药",
            "relation": "related",
            "attributes": {"confidence": 0.0},
        },
    ]

    scored, counts = tier_rule_edges(edges, entities, raw_text)

    assert counts == {
        "strong_rule": 1,
        "weak_rule": 1,
        "candidate_rule": 1,
        "rejected_rule": 1,
    }
    assert rule_quality_tier_counts(scored) == counts
    assert scored[0]["rule_quality"]["cooccurrence_distance"] is not None
    assert scored[0]["rule_quality"]["trigger_word_type"] == "treats"
    assert scored[0]["rule_quality"]["entity_type_compatibility"] == "compatible"
    assert scored[0]["rule_quality"]["source_section"] in {"title", "body"}
    assert is_promotable_rule_edge(scored[0]) is True
    assert is_promotable_rule_edge(scored[2]) is False
