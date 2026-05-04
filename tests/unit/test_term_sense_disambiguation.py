from src.contexts.philology.term_sense_disambiguation import TermSenseDisambiguator


def test_disambiguator_resolves_clear_external_wind_context():
    disambiguator = TermSenseDisambiguator()

    result = disambiguator.disambiguate(
        "风",
        "风寒外感，恶风头痛，脉浮，桂枝汤主之。",
        dynasty="东汉",
        cooccurring_terms=["寒", "桂枝汤"],
    )

    assert result["sense_id"] == "tcm.wind.external_pathogen"
    assert result["status"] == "resolved"
    assert result["sense_candidates"]
    assert result["basis"]


def test_disambiguator_keeps_weak_context_as_candidates_only():
    disambiguator = TermSenseDisambiguator()

    result = disambiguator.disambiguate("风", "风。")

    assert "sense_id" not in result
    assert result["status"] == "candidate"
    assert result["sense_candidates"]
    assert all("basis" in item for item in result["sense_candidates"])


def test_annotate_entity_mirrors_candidates_into_metadata():
    disambiguator = TermSenseDisambiguator()

    entity = disambiguator.annotate_entity(
        {"name": "经", "type": "theory", "metadata": {}},
        "足太阳经气循行，经脉络属。",
        cooccurring_terms=["太阳", "络", "气"],
    )

    assert entity["sense_id"] == "tcm.channel.meridian"
    assert entity["metadata"]["sense_id"] == "tcm.channel.meridian"
    assert entity["metadata"]["sense_candidates"]
