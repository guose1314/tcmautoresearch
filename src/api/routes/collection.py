"""Collection and document-standardization routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from src.api.dependencies import get_normalizer
from src.api.schemas import NormalizeDocumentRequest, NormalizeDocumentResponse
from src.collector.normalizer import Normalizer

router = APIRouter(tags=["collection"])


@router.post("/documents/normalize")
def normalize_document(
    payload: NormalizeDocumentRequest,
    normalizer: Normalizer = Depends(get_normalizer),
) -> NormalizeDocumentResponse:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    source_type = str(payload.source_type or "text").strip() or "text"
    document_payload = {
        "doc_id": str(payload.document_id or f"api-{datetime.now().strftime('%Y%m%d%H%M%S%f')}").strip(),
        "title": str(payload.title or "API 文本输入").strip(),
        "text": payload.text,
        "source_type": source_type,
        "source_ref": str(payload.source or "api").strip() or "api",
        "language": str(metadata.get("language") or "zh"),
        "metadata": metadata,
        "collected_at": datetime.now().isoformat(),
    }
    normalization_result, normalized_document = normalizer.normalize_document(
        document_payload,
        context={"source_type": source_type},
    )

    return {
        "standard_document": {
            "id": normalized_document.doc_id,
            "text": normalized_document.text,
            "metadata": normalized_document.metadata,
            "source": normalized_document.source_ref,
            "format_info": {
                "source_type": normalized_document.source_type,
                "language": normalized_document.language,
                "encoding": normalized_document.metadata.get("encoding"),
            },
        },
        "document": normalized_document.to_dict(),
        "normalization": normalization_result.to_dict(),
    }