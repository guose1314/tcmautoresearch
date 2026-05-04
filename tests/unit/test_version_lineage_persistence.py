from src.infrastructure.persistence import PersistenceService


def test_persist_document_graph_imports_editions_and_variant_readings(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'version_lineage.db'}"
    service = PersistenceService({"connection_string": database_url})
    assert service.initialize()
    try:
        snapshot = service.persist_document_graph(
            {
                "document": {
                    "source_file": "jin_gui湿病.txt",
                    "canonical_document_key": "jingui-shibing",
                    "canonical_title": "金匮要略湿病",
                    "version_lineage_key": "jingui-shibing-lineage",
                },
                "edition_lineages": [
                    {
                        "witness_key": "song-edition",
                        "version_lineage_key": "jingui-shibing-lineage",
                        "edition": "宋本",
                        "source_ref": "宋本卷二",
                    },
                    {
                        "witness_key": "ming-edition",
                        "version_lineage_key": "jingui-shibing-lineage",
                        "edition": "明本",
                        "base_witness_key": "song-edition",
                        "source_ref": "明本卷二",
                    },
                ],
                "variant_readings": [
                    {
                        "witness_key": "ming-edition",
                        "base_witness_key": "song-edition",
                        "segment_id": "wet-001",
                        "position": "卷二湿病条",
                        "base_text": "湿家之为病",
                        "variant_text": "湿病之为病",
                        "annotation": "明本异文，改变主语指向。",
                        "source_ref": "明本卷二",
                        "evidence_ref": "edition:ming-edition#wet-001",
                    }
                ],
            }
        )

        assert snapshot["edition_lineage_count"] == 2
        assert snapshot["variant_reading_count"] == 1
        assert {item["witness_key"] for item in snapshot["edition_lineages"]} == {
            "song-edition",
            "ming-edition",
        }
        variant = snapshot["variant_readings"][0]
        assert variant["witness_key"] == "ming-edition"
        assert variant["edition_lineage_id"]
        assert variant["evidence_ref"] == "edition:ming-edition#wet-001"
    finally:
        service.cleanup()
