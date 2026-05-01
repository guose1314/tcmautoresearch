from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from src.web.routes.analysis import _json_ready


def test_json_ready_converts_projection_payload_scalars() -> None:
    entity_id = uuid4()
    created_at = datetime(2026, 4, 28, 22, 45, tzinfo=timezone.utc)

    payload = _json_ready(
        {
            "entities": [
                {
                    "id": entity_id,
                    "props": {
                        "created_at": created_at,
                        "score": Decimal("0.75"),
                        "source_path": Path("data/example.txt"),
                    },
                }
            ]
        }
    )

    entity = payload["entities"][0]
    assert entity["id"] == str(entity_id)
    assert entity["props"]["created_at"] == created_at.isoformat()
    assert entity["props"]["score"] == 0.75
    assert entity["props"]["source_path"] == str(Path("data/example.txt"))
