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
from typing import Any, Dict, FrozenSet, Mapping, Optional

# ═══════════════════════════════════════════════════════════════════════
# Schema version — bump on every breaking label/relationship/property change
# ═══════════════════════════════════════════════════════════════════════

GRAPH_SCHEMA_VERSION = "1.2.0"

_SCHEMA_META_LABEL = "GraphSchemaMeta"
_SCHEMA_META_NODE_ID = "graph_schema_meta::singleton"

# 严格模式环境变量：当为真值时，drift 触发启动期 RuntimeError
GRAPH_SCHEMA_STRICT_ENV = "TCM__GRAPH_SCHEMA_STRICT"


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
    EXEGESIS_ENTRY = "ExegesisEntry"
    EXEGESIS_TERM = "ExegesisTerm"
    FRAGMENT_CANDIDATE = "FragmentCandidate"
    TEXTUAL_EVIDENCE_CHAIN = "TextualEvidenceChain"
    RHYME_WITNESS = "RhymeWitness"
    SCHOOL = "School"

    # ── TCM 领域 ──
    FORMULA = "Formula"
    HERB = "Herb"
    SYNDROME = "Syndrome"
    SYMPTOM = "Symptom"
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
    HAS_HYPOTHESIS = "HAS_HYPOTHESIS"
    EVIDENCE_FOR = "EVIDENCE_FOR"
    DERIVED_FROM_PHASE = "DERIVED_FROM_PHASE"
    PROPOSED_BY = "PROPOSED_BY"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    CONTRADICTS = "CONTRADICTS"
    CLAIMS = "CLAIMS"
    EVIDENCED_BY = "EVIDENCED_BY"

    # ── 文献学 ──
    WITNESSED_BY = "WITNESSED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    CATALOGED_IN = "CATALOGED_IN"
    OBSERVED_WITNESS = "OBSERVED_WITNESS"
    BELONGS_TO_LINEAGE = "BELONGS_TO_LINEAGE"
    HAS_VERSION = "HAS_VERSION"
    HAS_EXEGESIS = "HAS_EXEGESIS"
    HAS_FRAGMENT_CANDIDATE = "HAS_FRAGMENT_CANDIDATE"
    ATTESTS_TO = "ATTESTS_TO"
    INTERPRETS = "INTERPRETS"
    RECONSTRUCTS = "RECONSTRUCTS"
    CITES_FRAGMENT = "CITES_FRAGMENT"
    EXPLAINS_HERB = "EXPLAINS_HERB"
    EXPLAINS_FORMULA = "EXPLAINS_FORMULA"
    EXPLAINS_SYNDROME = "EXPLAINS_SYNDROME"
    EXPLAINS_EFFICACY = "EXPLAINS_EFFICACY"
    EXPLAINS_FORMULA_COMPONENT = "EXPLAINS_FORMULA_COMPONENT"
    EXPLAINS_PATHOGENESIS = "EXPLAINS_PATHOGENESIS"
    EXPLAINS_SYMPTOM = "EXPLAINS_SYMPTOM"

    # ── TCM 领域 ──
    SOVEREIGN = "SOVEREIGN"
    MINISTER = "MINISTER"
    ASSISTANT = "ASSISTANT"
    ENVOY = "ENVOY"
    TREATS = "TREATS"
    HAS_EFFICACY = "HAS_EFFICACY"
    SYMPTOM_OF = "SYMPTOM_OF"
    SIMILAR_TO = "SIMILAR_TO"
    ASSOCIATED_TARGET = "ASSOCIATED_TARGET"
    PARTICIPATES_IN = "PARTICIPATES_IN"

    # ── 音韵 / 学派 ──
    RHYMES_WITH = "RHYMES_WITH"
    BELONGS_TO_SCHOOL = "BELONGS_TO_SCHOOL"
    MENTORSHIP = "MENTORSHIP"

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
        "source_type", "source_ref", "relation_type",
        "source_entity", "target_entity", "excerpt",
        "document_title", "work_title", "version_lineage_key",
        "witness_key",
    }),
    NodeLabel.EVIDENCE_CLAIM: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "claim_id", "claim_text", "confidence", "evidence_grade",
        "evidence_ids", "source_entity", "target_entity",
        "relation_type", "support_count", "review_status",
        "needs_manual_review", "reviewer", "reviewed_at",
        "decision_basis", "work_title", "document_title",
        "version_lineage_key", "witness_key",
    }),
    NodeLabel.CATALOG: frozenset({
        "catalog_id", "title", "source", "classification",
        "review_status", "needs_manual_review", "reviewer",
        "reviewed_at", "decision_basis",
    }),
    NodeLabel.VERSION_LINEAGE: frozenset({
        "version_lineage_key", "work_fragment_key", "work_title",
        "fragment_title", "dynasty", "author", "edition",
        "lineage_id_source", "review_status", "needs_manual_review",
        "reviewer", "reviewed_at", "decision_basis",
    }),
    NodeLabel.VERSION_WITNESS: _COMMON_TEMPORAL_PROPS | frozenset({
        "witness_key", "version_lineage_key", "work_fragment_key",
        "catalog_id", "work_title", "fragment_title",
        "dynasty", "author", "edition", "source_type", "source_ref",
        "document_id", "document_urn", "document_title",
        "cycle_id", "phase_execution_id", "review_status",
        "needs_manual_review", "reviewer", "reviewed_at", "decision_basis",
    }),
    NodeLabel.EXEGESIS_ENTRY: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "exegesis_id", "canonical", "label", "definition", "definition_source",
        "semantic_scope", "observed_forms", "configured_variants", "sources",
        "source_refs", "notes", "dynasty_usage", "disambiguation_basis",
        "review_status", "needs_manual_review", "reviewer", "reviewed_at",
        "decision_basis",
        "exegesis_notes", "document_urn", "document_title", "work_title",
        "version_lineage_key", "witness_key",
    }),
    NodeLabel.EXEGESIS_TERM: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "exegesis_id", "canonical", "label", "definition", "definition_source",
        "semantic_scope", "observed_forms", "configured_variants", "sources",
        "source_refs", "notes", "dynasty_usage", "disambiguation_basis",
        "review_status", "needs_manual_review", "reviewer", "reviewed_at",
        "decision_basis", "exegesis_notes", "document_urn", "document_title",
        "work_title", "version_lineage_key", "witness_key",
    }),
    NodeLabel.FRAGMENT_CANDIDATE: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "candidate_id", "candidate_kind", "fragment_title", "document_title",
        "document_urn", "source_type", "witness_title", "witness_urn",
        "work_title", "version_lineage_key", "witness_key", "match_score",
        "confidence", "review_status", "needs_manual_review", "reviewer",
        "reviewed_at", "decision_basis", "reconstruction_basis", "source_refs", "asset_key",
        "text_preview",
    }),
    NodeLabel.TEXTUAL_EVIDENCE_CHAIN: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "claim_id", "claim_text", "claim_type", "confidence", "evidence_grade",
        "evidence_ids", "source_entity", "target_entity", "relation_type",
        "support_count", "review_status", "needs_manual_review", "reviewer",
        "reviewed_at", "decision_basis", "work_title", "document_title",
        "version_lineage_key", "witness_key",
    }),
    NodeLabel.FORMULA: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.HERB: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json", "formula_canonical",
        "source_formula", "source_exegesis_id", "formula_role",
    }),
    NodeLabel.SYNDROME: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json",
    }),
    NodeLabel.SYMPTOM: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json", "symptom_category",
        "manifestation_source", "syndrome_canonical", "source_syndrome",
        "source_exegesis_id",
    }),
    NodeLabel.EFFICACY: frozenset({
        "name", "type", "confidence", "alternative_names",
        "description", "entity_metadata_json", "herb_canonical",
        "source_herb", "source_exegesis_id",
    }),
    NodeLabel.TARGET: frozenset({
        "name", "type", "confidence", "description",
    }),
    NodeLabel.PATHWAY: frozenset({
        "name", "type", "confidence", "description",
    }),
    NodeLabel.PROPERTY: frozenset({
        "name", "type", "confidence", "description", "entity_metadata_json",
        "source_exegesis_id", "syndrome_canonical", "source_syndrome",
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
    NodeLabel.RHYME_WITNESS: _COMMON_TEMPORAL_PROPS | _COMMON_CYCLE_PROPS | frozenset({
        "rhyme_id", "canonical", "label", "fanqie", "middle_chinese",
        "old_chinese", "rhyme_group", "tone", "initial", "final",
        "source_refs", "witness_refs", "notes", "exegesis_id",
        "work_title", "document_title", "version_lineage_key", "witness_key",
        "review_status", "needs_manual_review", "reviewer",
        "reviewed_at", "decision_basis",
    }),
    NodeLabel.SCHOOL: _COMMON_TEMPORAL_PROPS | frozenset({
        "school_id", "name", "alternative_names", "description",
        "founding_dynasty", "core_doctrine", "representative_figures",
        "representative_works", "lineage_summary", "source_refs",
        "review_status", "needs_manual_review", "reviewer",
        "reviewed_at", "decision_basis",
    }),
}

_COMMON_REL_PROPS: FrozenSet[str] = frozenset({
    "cycle_id", "phase",
})

_ALLOWED_REL_PROPERTIES: Dict[RelType, FrozenSet[str]] = {
    RelType.EXPLAINS_HERB: _COMMON_REL_PROPS | frozenset({
        "herb_canonical", "source_herb", "source_exegesis_id", "semantic_scope", "provenance_kind",
    }),
    RelType.EXPLAINS_FORMULA: _COMMON_REL_PROPS | frozenset({
        "formula_canonical", "source_formula", "source_exegesis_id", "semantic_scope", "provenance_kind",
    }),
    RelType.RHYMES_WITH: _COMMON_REL_PROPS | frozenset({
        "rhyme_group", "phonetic_basis", "source_refs", "confidence",
    }),
    RelType.BELONGS_TO_SCHOOL: _COMMON_REL_PROPS | frozenset({
        "role", "period", "source_refs", "confidence",
    }),
    RelType.MENTORSHIP: _COMMON_REL_PROPS | frozenset({
        "mentor_role", "apprentice_role", "period", "source_refs", "confidence",
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


def get_allowed_rel_properties(rel_type: str) -> FrozenSet[str]:
    """返回给定关系类型的允许属性集合。"""
    try:
        rel_enum = RelType(rel_type)
    except ValueError:
        return frozenset()
    return _ALLOWED_REL_PROPERTIES.get(rel_enum, frozenset())


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


class GraphSchemaDriftError(RuntimeError):
    """Raised when ``assert_schema_consistent(strict=True)`` detects drift."""

    def __init__(self, drift_report: Dict[str, Any]):
        super().__init__(drift_report.get("detail", "graph schema drift detected"))
        self.drift_report = dict(drift_report)


def is_strict_mode_enabled(env_value: Optional[str] = None) -> bool:
    """Return True iff ``TCM__GRAPH_SCHEMA_STRICT`` env var (or *env_value*) is truthy."""
    import os
    raw = env_value if env_value is not None else os.environ.get(GRAPH_SCHEMA_STRICT_ENV, "")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on", "strict"}


def assert_schema_consistent(
    stored_version: Optional[str],
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    """Run drift detection and optionally raise when drift is detected.

    Parameters
    ----------
    stored_version
        Version string read from the live Neo4j ``GraphSchemaMeta`` node.
    strict
        When True (or env ``TCM__GRAPH_SCHEMA_STRICT`` is truthy) raises
        :class:`GraphSchemaDriftError` on drift; otherwise returns the report
        and lets the caller decide.
    """
    report = detect_schema_drift(stored_version)
    if report.get("drift_detected") and (strict or is_strict_mode_enabled()):
        raise GraphSchemaDriftError(report)
    return report


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


# ── Entity type → NodeLabel 映射 ──────────────────────────────────────

ENTITY_TYPE_TO_LABEL: Mapping[str, str] = {
    "formula": NodeLabel.FORMULA.value,
    "herb": NodeLabel.HERB.value,
    "syndrome": NodeLabel.SYNDROME.value,
    "symptom": NodeLabel.SYMPTOM.value,
    "target": NodeLabel.TARGET.value,
    "pathway": NodeLabel.PATHWAY.value,
    "efficacy": NodeLabel.EFFICACY.value,
    "property": NodeLabel.PROPERTY.value,
    "taste": NodeLabel.TASTE.value,
    "meridian": NodeLabel.MERIDIAN.value,
    "generic": NodeLabel.ENTITY.value,
}
"""从实体 type 字符串到 Neo4j 标签的规范映射。"""
