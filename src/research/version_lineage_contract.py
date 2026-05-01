"""Version lineage diff and variant reading contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

VERSION_LINEAGE_DIFF_NODE_LABEL = "VersionLineageDiff"
VARIANT_READING_NODE_LABEL = "VariantReading"
VERSION_WITNESS_NODE_LABEL = "VersionWitness"
REL_COMPARES_WITNESS = "COMPARES_WITNESS"
REL_HAS_VARIANT_READING = "HAS_VARIANT_READING"
REL_DERIVED_FROM = "DERIVED_FROM"

_KNOWN_IMPACT_LEVELS = {"unknown", "low", "medium", "high", "critical"}
_HIGH_IMPACT_LEVELS = {"high", "critical"}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_texts(values: Any) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return []
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _as_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _slugify(value: Any) -> str:
    text = _as_text(value).lower().replace(" ", "_")
    chars: List[str] = []
    for char in text:
        if char.isalnum() or char in {"_", "-", ":", "|"}:
            chars.append(char)
    return "".join(chars)[:96] or "item"


def _stable_id(*parts: Any) -> str:
    normalized = "||".join(_as_text(part) for part in parts if _as_text(part))
    if not normalized:
        normalized = "empty"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{_slugify(normalized)[:48]}::{digest}"


def _normalize_impact_level(value: Any) -> str:
    normalized = _as_text(value).lower()
    return normalized if normalized in _KNOWN_IMPACT_LEVELS else "unknown"


@dataclass(frozen=True)
class VariantReading:
    base_witness: str
    target_witness: str
    variant_text: str
    normalized_meaning: str
    impact_level: str
    evidence_ref: str
    reading_id: str = ""
    base_text: str = ""
    position: str = ""
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        base_witness = _as_text(self.base_witness)
        target_witness = _as_text(self.target_witness)
        variant_text = _as_text(self.variant_text)
        normalized_meaning = _as_text(self.normalized_meaning)
        impact_level = _normalize_impact_level(self.impact_level)
        evidence_ref = _as_text(self.evidence_ref)
        base_text = _as_text(self.base_text)
        position = _as_text(self.position)
        notes = tuple(_as_texts(self.notes))
        reading_id = _as_text(self.reading_id) or _stable_id(
            base_witness,
            target_witness,
            position,
            base_text,
            variant_text,
            normalized_meaning,
            evidence_ref,
        )
        object.__setattr__(self, "base_witness", base_witness)
        object.__setattr__(self, "target_witness", target_witness)
        object.__setattr__(self, "variant_text", variant_text)
        object.__setattr__(self, "normalized_meaning", normalized_meaning)
        object.__setattr__(self, "impact_level", impact_level)
        object.__setattr__(self, "evidence_ref", evidence_ref)
        object.__setattr__(self, "reading_id", reading_id)
        object.__setattr__(self, "base_text", base_text)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "notes", notes)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        default_base_witness: str = "",
        default_target_witness: str = "",
    ) -> "VariantReading":
        payload = _as_mapping(value)
        evidence_refs = _as_texts(
            payload.get("evidence_ref")
            or payload.get("source_ref")
            or payload.get("source_refs")
        )
        return cls(
            base_witness=payload.get("base_witness") or default_base_witness,
            target_witness=payload.get("target_witness") or default_target_witness,
            variant_text=payload.get("variant_text")
            or payload.get("target_text")
            or payload.get("witness_text"),
            normalized_meaning=payload.get("normalized_meaning")
            or payload.get("meaning")
            or payload.get("semantic_delta"),
            impact_level=payload.get("impact_level")
            or payload.get("impact")
            or "unknown",
            evidence_ref=evidence_refs[0] if evidence_refs else "",
            reading_id=payload.get("reading_id")
            or payload.get("variant_id")
            or payload.get("id"),
            base_text=payload.get("base_text"),
            position=payload.get("position") or payload.get("location"),
            notes=tuple(_as_texts(payload.get("notes"))),
        )

    def is_empty(self) -> bool:
        return not any((self.variant_text, self.normalized_meaning, self.evidence_ref))

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "reading_id": self.reading_id,
            "base_witness": self.base_witness,
            "target_witness": self.target_witness,
            "variant_text": self.variant_text,
            "normalized_meaning": self.normalized_meaning,
            "impact_level": self.impact_level,
            "evidence_ref": self.evidence_ref,
        }
        if self.base_text:
            payload["base_text"] = self.base_text
        if self.position:
            payload["position"] = self.position
        if self.notes:
            payload["notes"] = list(self.notes)
        return payload


@dataclass(frozen=True)
class LineageDiff:
    base_witness: str
    target_witness: str
    variant_readings: Tuple[VariantReading, ...] = field(default_factory=tuple)
    version_lineage_key: str = ""
    diff_id: str = ""
    summary_note: str = ""

    def __post_init__(self) -> None:
        base_witness = _as_text(self.base_witness)
        target_witness = _as_text(self.target_witness)
        variant_readings = tuple(
            reading
            for reading in normalize_variant_readings(
                self.variant_readings,
                default_base_witness=base_witness,
                default_target_witness=target_witness,
            )
            if not reading.is_empty()
        )
        if not base_witness and variant_readings:
            base_witness = variant_readings[0].base_witness
        if not target_witness and variant_readings:
            target_witness = variant_readings[0].target_witness
        version_lineage_key = _as_text(self.version_lineage_key)
        summary_note = _as_text(self.summary_note)
        diff_id = _as_text(self.diff_id) or _stable_id(
            version_lineage_key,
            base_witness,
            target_witness,
            *[reading.reading_id for reading in variant_readings],
        )
        object.__setattr__(self, "base_witness", base_witness)
        object.__setattr__(self, "target_witness", target_witness)
        object.__setattr__(self, "variant_readings", variant_readings)
        object.__setattr__(self, "version_lineage_key", version_lineage_key)
        object.__setattr__(self, "diff_id", diff_id)
        object.__setattr__(self, "summary_note", summary_note)

    @classmethod
    def from_variant_readings(
        cls,
        variant_readings: Sequence[Any],
        *,
        base_witness: str = "",
        target_witness: str = "",
        version_lineage_key: str = "",
        diff_id: str = "",
        summary_note: str = "",
    ) -> "LineageDiff":
        readings = normalize_variant_readings(
            variant_readings,
            default_base_witness=base_witness,
            default_target_witness=target_witness,
        )
        return cls(
            base_witness=base_witness or (readings[0].base_witness if readings else ""),
            target_witness=target_witness
            or (readings[0].target_witness if readings else ""),
            variant_readings=tuple(readings),
            version_lineage_key=version_lineage_key,
            diff_id=diff_id,
            summary_note=summary_note,
        )

    def impact_distribution(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for reading in self.variant_readings:
            counts[reading.impact_level] = counts.get(reading.impact_level, 0) + 1
        return {key: counts[key] for key in sorted(counts)}

    def evidence_refs(self) -> Tuple[str, ...]:
        return tuple(
            _as_texts([reading.evidence_ref for reading in self.variant_readings])
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "diff_id": self.diff_id,
            "base_witness": self.base_witness,
            "target_witness": self.target_witness,
            "variant_reading_count": len(self.variant_readings),
            "variant_readings": [
                reading.to_dict() for reading in self.variant_readings
            ],
            "impact_distribution": self.impact_distribution(),
            "evidence_refs": list(self.evidence_refs()),
        }
        if self.version_lineage_key:
            payload["version_lineage_key"] = self.version_lineage_key
        if self.summary_note:
            payload["summary_note"] = self.summary_note
        return payload

    def summary(self) -> "LineageDiffSummary":
        return LineageDiffSummary.from_diffs([self])


@dataclass(frozen=True)
class LineageDiffSummary:
    diff_count: int
    variant_reading_count: int
    witness_pair_count: int
    impact_distribution: Dict[str, int]
    evidence_refs: Tuple[str, ...]
    high_impact_count: int = 0
    diffs: Tuple[LineageDiff, ...] = field(default_factory=tuple)

    @classmethod
    def from_diffs(cls, diffs: Sequence[Any]) -> "LineageDiffSummary":
        normalized = tuple(normalize_lineage_diffs(diffs))
        impact_counts: Dict[str, int] = {}
        evidence_refs: List[str] = []
        witness_pairs: set[tuple[str, str]] = set()
        high_impact_count = 0
        variant_count = 0
        for diff in normalized:
            if diff.base_witness or diff.target_witness:
                witness_pairs.add((diff.base_witness, diff.target_witness))
            for reading in diff.variant_readings:
                variant_count += 1
                impact_counts[reading.impact_level] = (
                    impact_counts.get(reading.impact_level, 0) + 1
                )
                if reading.impact_level in _HIGH_IMPACT_LEVELS:
                    high_impact_count += 1
                if reading.evidence_ref and reading.evidence_ref not in evidence_refs:
                    evidence_refs.append(reading.evidence_ref)
        return cls(
            diff_count=len(normalized),
            variant_reading_count=variant_count,
            witness_pair_count=len(witness_pairs),
            impact_distribution={
                key: impact_counts[key] for key in sorted(impact_counts)
            },
            evidence_refs=tuple(evidence_refs),
            high_impact_count=high_impact_count,
            diffs=normalized,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diff_count": self.diff_count,
            "variant_reading_count": self.variant_reading_count,
            "witness_pair_count": self.witness_pair_count,
            "impact_distribution": dict(self.impact_distribution),
            "evidence_refs": list(self.evidence_refs),
            "high_impact_count": self.high_impact_count,
            "diffs": [diff.to_dict() for diff in self.diffs],
        }

    def to_neo4j_payload(
        self, cycle_id: str, *, phase: str = "observe"
    ) -> Dict[str, Any]:
        return build_lineage_diff_graph_payload(cycle_id, self.diffs, phase=phase)


def normalize_variant_readings(
    raw_readings: Any,
    *,
    default_base_witness: str = "",
    default_target_witness: str = "",
) -> List[VariantReading]:
    if isinstance(raw_readings, VariantReading):
        raw_items = [raw_readings]
    elif isinstance(raw_readings, Mapping):
        raw_items = [raw_readings]
    elif isinstance(raw_readings, Sequence) and not isinstance(
        raw_readings, (str, bytes)
    ):
        raw_items = list(raw_readings)
    else:
        raw_items = []

    readings: List[VariantReading] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, VariantReading):
            reading = item
        elif isinstance(item, Mapping):
            reading = VariantReading.from_mapping(
                item,
                default_base_witness=default_base_witness,
                default_target_witness=default_target_witness,
            )
        else:
            continue
        if reading.is_empty() or reading.reading_id in seen:
            continue
        seen.add(reading.reading_id)
        readings.append(reading)
    return readings


def normalize_lineage_diffs(raw_diffs: Any) -> List[LineageDiff]:
    if isinstance(raw_diffs, LineageDiff):
        return [raw_diffs]
    if isinstance(raw_diffs, Mapping):
        payload = _as_mapping(raw_diffs)
        if "diffs" in payload:
            return normalize_lineage_diffs(payload.get("diffs"))
        readings = (
            payload.get("variant_readings")
            or payload.get("readings")
            or payload.get("variants")
        )
        if readings is not None:
            return [
                LineageDiff.from_variant_readings(
                    readings,
                    base_witness=payload.get("base_witness") or "",
                    target_witness=payload.get("target_witness") or "",
                    version_lineage_key=payload.get("version_lineage_key") or "",
                    diff_id=payload.get("diff_id") or payload.get("id") or "",
                    summary_note=payload.get("summary_note") or "",
                )
            ]
        if payload.get("variant_text") or payload.get("normalized_meaning"):
            return [LineageDiff.from_variant_readings([payload])]
        return []
    if not isinstance(raw_diffs, Sequence) or isinstance(raw_diffs, (str, bytes)):
        return []

    diffs: List[LineageDiff] = []
    loose_readings: List[Any] = []
    seen: set[str] = set()
    for item in raw_diffs:
        if isinstance(item, LineageDiff):
            diff = item
        elif isinstance(item, Mapping) and any(
            key in item for key in ("variant_readings", "readings", "variants")
        ):
            nested_diffs = normalize_lineage_diffs(item)
            if not nested_diffs:
                continue
            diff = nested_diffs[0]
        elif isinstance(item, Mapping):
            loose_readings.append(item)
            continue
        else:
            continue
        if diff.diff_id not in seen:
            seen.add(diff.diff_id)
            diffs.append(diff)
    if loose_readings:
        diff = LineageDiff.from_variant_readings(loose_readings)
        if diff.diff_id not in seen:
            diffs.append(diff)
    return diffs


def build_lineage_diff_from_variant_readings(
    base_witness: str,
    target_witness: str,
    variant_readings: Sequence[Any],
    *,
    version_lineage_key: str = "",
) -> LineageDiff:
    return LineageDiff.from_variant_readings(
        variant_readings,
        base_witness=base_witness,
        target_witness=target_witness,
        version_lineage_key=version_lineage_key,
    )


def build_lineage_diff_summary(
    diffs_or_readings: Any,
    *,
    base_witness: str = "",
    target_witness: str = "",
    version_lineage_key: str = "",
) -> LineageDiffSummary:
    diffs = normalize_lineage_diffs(diffs_or_readings)
    if not diffs and diffs_or_readings:
        diffs = [
            LineageDiff.from_variant_readings(
                diffs_or_readings,
                base_witness=base_witness,
                target_witness=target_witness,
                version_lineage_key=version_lineage_key,
            )
        ]
    if base_witness or target_witness or version_lineage_key:
        diffs = [
            LineageDiff.from_variant_readings(
                diff.variant_readings,
                base_witness=diff.base_witness or base_witness,
                target_witness=diff.target_witness or target_witness,
                version_lineage_key=diff.version_lineage_key or version_lineage_key,
                diff_id=diff.diff_id,
                summary_note=diff.summary_note,
            )
            for diff in diffs
        ]
    return LineageDiffSummary.from_diffs(diffs)


def build_lineage_diff_graph_payload(
    cycle_id: str,
    lineage_diffs: Any,
    *,
    phase: str = "observe",
) -> Dict[str, Any]:
    diffs = normalize_lineage_diffs(lineage_diffs)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_keys: set[tuple[str, str]] = set()
    edge_keys: set[tuple[str, str, str, str, str]] = set()

    def add_node(label: str, node_id: str, properties: Mapping[str, Any]) -> None:
        key = (label, node_id)
        if key in node_keys:
            return
        node_keys.add(key)
        nodes.append({"id": node_id, "label": label, "properties": dict(properties)})

    def add_edge(
        source_id: str,
        target_id: str,
        relationship_type: str,
        source_label: str,
        target_label: str,
        properties: Mapping[str, Any] | None = None,
    ) -> None:
        key = (source_label, source_id, relationship_type, target_label, target_id)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relationship_type": relationship_type,
                "source_label": source_label,
                "target_label": target_label,
                "properties": dict(properties or {}),
            }
        )

    for diff in diffs:
        if (
            not diff.base_witness
            and not diff.target_witness
            and not diff.variant_readings
        ):
            continue
        diff_node_id = f"lineage_diff::{cycle_id}::{_slugify(diff.diff_id)}"
        summary = diff.summary()
        add_node(
            VERSION_LINEAGE_DIFF_NODE_LABEL,
            diff_node_id,
            {
                "cycle_id": cycle_id,
                "phase": phase,
                "diff_id": diff.diff_id,
                "version_lineage_key": diff.version_lineage_key,
                "base_witness": diff.base_witness,
                "target_witness": diff.target_witness,
                "variant_reading_count": len(diff.variant_readings),
                "high_impact_count": summary.high_impact_count,
                "impact_distribution_json": json.dumps(
                    diff.impact_distribution(), ensure_ascii=False, sort_keys=True
                ),
                "evidence_refs": list(diff.evidence_refs()),
                "summary_note": diff.summary_note,
            },
        )

        witness_nodes: List[tuple[str, str]] = []
        for role, witness_key in (
            ("base", diff.base_witness),
            ("target", diff.target_witness),
        ):
            if not witness_key:
                continue
            witness_node_id = f"witness::{witness_key}"
            witness_nodes.append((role, witness_node_id))
            add_node(
                VERSION_WITNESS_NODE_LABEL,
                witness_node_id,
                {
                    "cycle_id": cycle_id,
                    "witness_key": witness_key,
                    "version_lineage_key": diff.version_lineage_key,
                },
            )
            add_edge(
                diff_node_id,
                witness_node_id,
                REL_COMPARES_WITNESS,
                VERSION_LINEAGE_DIFF_NODE_LABEL,
                VERSION_WITNESS_NODE_LABEL,
                {
                    "cycle_id": cycle_id,
                    "phase": phase,
                    "role": role,
                    "diff_id": diff.diff_id,
                    "version_lineage_key": diff.version_lineage_key,
                },
            )

        for index, reading in enumerate(diff.variant_readings, start=1):
            reading_node_id = (
                f"variant_reading::{cycle_id}::{_slugify(diff.diff_id)}::{index}"
            )
            add_node(
                VARIANT_READING_NODE_LABEL,
                reading_node_id,
                {
                    "cycle_id": cycle_id,
                    "phase": phase,
                    "reading_id": reading.reading_id,
                    "diff_id": diff.diff_id,
                    "version_lineage_key": diff.version_lineage_key,
                    "base_witness": reading.base_witness or diff.base_witness,
                    "target_witness": reading.target_witness or diff.target_witness,
                    "base_text": reading.base_text,
                    "variant_text": reading.variant_text,
                    "normalized_meaning": reading.normalized_meaning,
                    "impact_level": reading.impact_level,
                    "evidence_ref": reading.evidence_ref,
                    "position": reading.position,
                    "notes": list(reading.notes),
                },
            )
            add_edge(
                diff_node_id,
                reading_node_id,
                REL_HAS_VARIANT_READING,
                VERSION_LINEAGE_DIFF_NODE_LABEL,
                VARIANT_READING_NODE_LABEL,
                {
                    "cycle_id": cycle_id,
                    "phase": phase,
                    "diff_id": diff.diff_id,
                    "reading_id": reading.reading_id,
                    "impact_level": reading.impact_level,
                },
            )
            for role, witness_node_id in witness_nodes:
                add_edge(
                    reading_node_id,
                    witness_node_id,
                    REL_DERIVED_FROM,
                    VARIANT_READING_NODE_LABEL,
                    VERSION_WITNESS_NODE_LABEL,
                    {
                        "cycle_id": cycle_id,
                        "phase": phase,
                        "role": f"{role}_witness",
                        "diff_id": diff.diff_id,
                        "reading_id": reading.reading_id,
                    },
                )

    summary = LineageDiffSummary.from_diffs(diffs)
    return {
        "graph_type": "version_lineage_diff_subgraph",
        "asset_family": "philology",
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "summary": summary.to_dict()
        | {
            "diff_node_count": sum(
                1 for node in nodes if node["label"] == VERSION_LINEAGE_DIFF_NODE_LABEL
            )
        },
    }
