"""Neo4j 图谱 schema 注册表与版本管理。

集中定义所有合法的节点标签、关系类型和允许属性，
为 schema versioning 和 drift 检测提供 single source of truth。

用法::

    from src.storage.graph_schema import (
        GRAPH_SCHEMA_VERSION,
        NodeLabel,
        RelType,
        get_allowed_properties,
        get_schema_summary,
    )
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════
# Schema version — bump on every breaking label/relationship/property change
# ═══════════════════════════════════════════════════════════════════════

GRAPH_SCHEMA_VERSION = "1.0.0"

_SCHEMA_META_LABEL = "GraphSchemaMeta"
_SCHEMA_META_NODE_ID = "graph_schema_meta::singleton"


# ═══════════════════════════════════════════════════════════════════════
# Node labels
# ═══════════════════════════════════════════════════════════════════════


class NodeLabel(str, Enum):
    """注册的图谱节点标签。"""

    # ── 研究流程 ──
    RESEARCH_SESSION = "ResearchSession"
    RESEARCH_PHASE_EXECUTION = "ResearchPhaseExecution"
    RESEARCH_ARTIFACT = "ResearchArtifact"

    # ── 假说 / 证据 ──
    HYPOTHESIS = "Hypothesis"
    EVIDENCE = "Evidence"
    EVIDENCE_CLAIM = "EvidenceClaim"

    # ── 文献学 ──
    CATALOG = "Catalog"
    VERSION_LINEAGE = "VersionLineage"
    VERSION_WITNESS = "VersionWitness"

    # ── TCM 领域 ──
    FORMULA = "Formula"
    HERB = "Herb"
    SYNDROME = "Syndrome"
    EFFICACY = "Efficacy"
    TARGET = "Target"
    PATHWAY = "Pathway"
    PROPERTY = "Property"
    TASTE = "Taste"
    MERIDIAN = "Meridian"

    # ── 通用 ──
    ENTITY = "Entity"

    # ── Schema 元数据 ──
    GRAPH_SCHEMA_META = "GraphSchemaMeta"


# ═══════════════════════════════════════════════════════════════════════
# Relationship types
# ═══════════════════════════════════════════════════════════════════════


class RelType(str, Enum):
    """注册的图谱关系类型。"""

    # ── 研究流程 ──
    HAS_PHASE = "HAS_PHASE"
    GENERATED = "GENERATED"
    HAS_ARTIFACT = "HAS_ARTIFACT"
    CAPTURED = "CAPTURED"

    # ── 假说 / 证据 ──
    PROPOSED_BY = "PROPOSED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    CLAIMS = "CLAIMS"
    EVIDENCED_BY = "EVIDENCED_BY"

    # ── 文献学 ──
    WITNESSED_BY = "WITNESSED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    CATALOGED_IN = "CATALOGED_IN"
    OBSERVED_WITNESS = "OBSERVED_WITNESS"
    BELONGS_TO_LINEAGE = "BELONGS_TO_LINEAGE"

    # ── TCM 领域 ──
    SOVEREIGN = "SOVEREIGN"
    MINISTER = "MINISTER"
    ASSISTANT = "ASSISTANT"
    ENVOY = "ENVOY"
    TREATS = "TREATS"
    HAS_EFFICACY = "HAS_EFFICACY"
    SIMILAR_TO = "SIMILAR_TO"
    ASSOCIATED_TARGET = "ASSOCIATED_TARGET"
    PARTICIPATES_IN = "PARTICIPATES_IN"

    # ── 通用 ──
    RELATED_TO = "RELATED_TO"


# ═══════════════════════════════════════════════════════════════════════
# Property whitelist per label
# ═══════════════════════════════════════════════════════════════════════

_COMMON_TEMPORAL_PROPS: FrozenSet[str] = frozenset({
    "created_at", "updated_at", "started_at", "completed_at",
})

_COMMON_CYCLE_PROPS: FrozenSet[str] = frozenset({
    "cycle_id", "phase", "phase_execution_id",
})

_ALLOWED_PROPERTIES: Dict[NodeLabel, FrozenSet[str]] = {
    NodeLabel.RESEARCH_SESSION: _COMMON_TEMPORAL_PROPS | frozenset({
        "cycle_id", "cycle_name", "status", "current_phase",
        "research_objective", "research_scope", "duration",
    }),
    NodeLabel.RESEARCH_PHASE_EXECUTION: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "status", "duration", "error_detail",
    }),
    NodeLabel.RESEARCH_ARTIFACT: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "name", "artifact_type", "description", "file_path",
        "mime_type", "size_bytes",
    }),
    NodeLabel.HYPOTHESIS: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "hypothesis_id", "title", "description", "domain",
        "confidence", "status", "validation_plan",
        "supporting_signal_count", "contradiction_signal_count",
    }),
    NodeLabel.EVIDENCE: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "evidence_id", "title", "source", "evidence_grade",
        "confidence", "provenance_type", "document_id",
    }),
    NodeLabel.EVIDENCE_CLAIM: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "claim_id", "claim_text", "confidence", "evidence_grade",
        "evidence_ids",
    }),
    NodeLabel.CATALOG: frozenset({
        "catalog_id", "title", "source", "classification",
    }),
    NodeLabel.VERSION_LINEAGE: frozenset({
        "version_lineage_key", "work_fragment_key", "work_title",
        "fragment_title", "dynasty", "author", "edition",
        "lineage_id_source",
    }),
    NodeLabel.VERSION_WITNESS: _COMMON_TEMPORAL_PROPS | frozenset({
        "witness_key", "version_lineage_key", "work_fragment_key",
        "catalog_id", "work_title", "fragment_title",
        "dynasty", "author", "edition", "source_type", "source_ref",
        "document_id", "document_urn", "document_title",
        "cycle_id", "phase_execution_id",
    }),
    NodeLabel.FORMULA: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.HERB: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.SYNDROME: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.EFFICACY: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.TARGET: frozenset({
        "name", "type", "confidence", "description",
    }),
    NodeLabel.PATHWAY: frozenset({
        "name", "type", "confidence", "description",
    }),
    NodeLabel.PROPERTY: frozenset({
        "name", "type", "confidence", "description", "entity_metadata_json",
    }),
    NodeLabel.TASTE: frozenset({
        "name", "type", "confidence", "description", "entity_metadata_json",
    }),
    NodeLabel.MERIDIAN: frozenset({
        "name", "type", "confidence", "description", "entity_metadata_json",
    }),
    NodeLabel.ENTITY: frozenset({
        "name", "entity_type", "confidence", "position", "length",
        "alternative_names", "description",
        "cycle_id", "phase_execution_id",
        "document_id", "document_urn", "document_title",
        "created_at", "updated_at",
    }),
    NodeLabel.GRAPH_SCHEMA_META: frozenset({
        "schema_version", "bootstrapped_at", "updated_at",
        "node_label_count", "rel_type_count",
    }),
}


# ═══════════════════════════════════════════════════════════════════════
# Public helpers
# ═══════════════════════════════════════════════════════════════════════


def get_allowed_properties(label: str) -> FrozenSet[str]:
    """返回给定节点标签的允许属性集合。"""
    try:
        node_label = NodeLabel(label)
    except ValueError:
        return frozenset()
    return _ALLOWED_PROPERTIES.get(node_label, frozenset())


def get_registered_labels() -> FrozenSet[str]:
    """返回所有注册的节点标签。"""
    return frozenset(member.value for member in NodeLabel)


def get_registered_rel_types() -> FrozenSet[str]:
    """返回所有注册的关系类型。"""
    return frozenset(member.value for member in RelType)


def get_schema_summary() -> Dict[str, Any]:
    """返回 schema 摘要（版本、标签数、关系类型数等）。"""
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "node_label_count": len(NodeLabel),
        "rel_type_count": len(RelType),
        "node_labels": sorted(member.value for member in NodeLabel),
        "rel_types": sorted(member.value for member in RelType),
    }


def build_schema_meta_node_properties() -> Dict[str, Any]:
    """构造 GraphSchemaMeta 节点属性。"""
    from datetime import datetime
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "bootstrapped_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "node_label_count": len(NodeLabel),
        "rel_type_count": len(RelType),
    }


def detect_schema_drift(
    stored_version: Optional[str],
) -> Dict[str, Any]:
    """比对存储中的 schema version 与当前代码中的 GRAPH_SCHEMA_VERSION。

    Returns
    -------
    dict
        - ``drift_detected``: bool
        - ``stored_version``: str | None
        - ``expected_version``: str
        - ``detail``: str
    """
    if stored_version is None:
        return {
            "drift_detected": True,
            "stored_version": None,
            "expected_version": GRAPH_SCHEMA_VERSION,
            "detail": "graph 中无 schema version 元数据节点",
        }
    if stored_version != GRAPH_SCHEMA_VERSION:
        return {
            "drift_detected": True,
            "stored_version": stored_version,
            "expected_version": GRAPH_SCHEMA_VERSION,
            "detail": f"版本不一致: stored={stored_version}, expected={GRAPH_SCHEMA_VERSION}",
        }
    return {
        "drift_detected": False,
        "stored_version": stored_version,
        "expected_version": GRAPH_SCHEMA_VERSION,
        "detail": "schema version 一致",
    }


# ── Label / RelType lookup helpers ────────────────────────────────────

_LABEL_LOOKUP: Dict[str, NodeLabel] = {m.value: m for m in NodeLabel}
_REL_TYPE_LOOKUP: Dict[str, RelType] = {m.value: m for m in RelType}


def resolve_node_label(raw_label: str, default: str = "Entity") -> str:
    """将原始标签字符串解析为注册的 NodeLabel 值。

    若未注册则返回 *default*。
    """
    if raw_label in _LABEL_LOOKUP:
        return raw_label
    return default


def resolve_rel_type(raw_type: str, default: str = "RELATED_TO") -> str:
    """将原始关系类型字符串解析为注册的 RelType 值。

    若未注册则返回 *default*。
    """
    if raw_type in _REL_TYPE_LOOKUP:
        return raw_type
    return default
