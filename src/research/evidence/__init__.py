"""Evidence location helpers for research assets."""

from .citation_evidence_synthesizer import (
    CITATION_EVIDENCE_SYNTHESIZER_VERSION,
    CitationEvidencePackage,
    CitationEvidenceSynthesizer,
    synthesize_citation_evidence_package,
)
from .text_segment_provenance import (
    TEXT_SEGMENT_PROVENANCE_VERSION,
    TextSegmentIndex,
    TextSegmentProvenance,
    attach_provenance_to_edges,
    attach_provenance_to_entities,
    attach_provenance_to_research_view,
)

__all__ = [
    "CITATION_EVIDENCE_SYNTHESIZER_VERSION",
    "TEXT_SEGMENT_PROVENANCE_VERSION",
    "CitationEvidencePackage",
    "CitationEvidenceSynthesizer",
    "TextSegmentIndex",
    "TextSegmentProvenance",
    "attach_provenance_to_entities",
    "attach_provenance_to_edges",
    "attach_provenance_to_research_view",
    "synthesize_citation_evidence_package",
]
