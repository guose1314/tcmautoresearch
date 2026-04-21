"""Graph schema versioning 单元测试（G-1 验收）。

覆盖:
- NodeLabel / RelType 枚举完整性
- get_allowed_properties / get_registered_labels / get_registered_rel_types
- get_schema_summary / build_schema_meta_node_properties
- detect_schema_drift 三种分支
- resolve_node_label / resolve_rel_type 边界
- Neo4jDriver._bootstrap_schema / get_schema_version / ensure_schema_version (mock)
- entity_to_neo4j_node 使用 registry
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.storage.graph_schema import (
    GRAPH_SCHEMA_VERSION,
    NodeLabel,
    RelType,
    build_schema_meta_node_properties,
    detect_schema_drift,
    get_allowed_properties,
    get_allowed_rel_properties,
    get_registered_labels,
    get_registered_rel_types,
    get_schema_summary,
    resolve_node_label,
    resolve_rel_type,
)


class TestNodeLabelEnum(unittest.TestCase):
    """NodeLabel 枚举完整性。"""

    def test_minimum_label_count(self):
        """至少有 20 个注册标签。"""
        self.assertGreaterEqual(len(NodeLabel), 20)

    def test_all_values_are_pascal_case(self):
        for member in NodeLabel:
            self.assertTrue(member.value[0].isupper(), f"{member.name} 的值应以大写字母开头")

    def test_graph_schema_meta_present(self):
        self.assertIn(NodeLabel.GRAPH_SCHEMA_META, NodeLabel)
        self.assertEqual(NodeLabel.GRAPH_SCHEMA_META.value, "GraphSchemaMeta")

    def test_hypothesis_evidence_labels_present(self):
        self.assertIn(NodeLabel.HYPOTHESIS, NodeLabel)
        self.assertIn(NodeLabel.EVIDENCE, NodeLabel)
        self.assertIn(NodeLabel.EVIDENCE_CLAIM, NodeLabel)

    def test_philology_detail_labels_present(self):
        self.assertIn(NodeLabel.EXEGESIS_ENTRY, NodeLabel)
        self.assertIn(NodeLabel.EXEGESIS_TERM, NodeLabel)
        self.assertIn(NodeLabel.FRAGMENT_CANDIDATE, NodeLabel)
        self.assertIn(NodeLabel.TEXTUAL_EVIDENCE_CHAIN, NodeLabel)
        self.assertIn(NodeLabel.SYMPTOM, NodeLabel)


class TestRelTypeEnum(unittest.TestCase):
    """RelType 枚举完整性。"""

    def test_minimum_rel_type_count(self):
        self.assertGreaterEqual(len(RelType), 20)

    def test_all_values_are_upper_snake(self):
        for member in RelType:
            self.assertEqual(member.value, member.value.upper(), f"{member.name} 的值应全大写")

    def test_hypothesis_evidence_rel_types(self):
        self.assertIn(RelType.PROPOSED_BY, RelType)
        self.assertIn(RelType.SUPPORTED_BY, RelType)
        self.assertIn(RelType.CONTRADICTED_BY, RelType)
        self.assertIn(RelType.CLAIMS, RelType)
        self.assertIn(RelType.EVIDENCED_BY, RelType)

    def test_philology_detail_rel_types(self):
        self.assertIn(RelType.HAS_VERSION, RelType)
        self.assertIn(RelType.HAS_EXEGESIS, RelType)
        self.assertIn(RelType.HAS_FRAGMENT_CANDIDATE, RelType)
        self.assertIn(RelType.ATTESTS_TO, RelType)
        self.assertIn(RelType.INTERPRETS, RelType)
        self.assertIn(RelType.RECONSTRUCTS, RelType)
        self.assertIn(RelType.CITES_FRAGMENT, RelType)
        self.assertIn(RelType.EXPLAINS_HERB, RelType)
        self.assertIn(RelType.EXPLAINS_FORMULA, RelType)
        self.assertIn(RelType.EXPLAINS_SYNDROME, RelType)
        self.assertIn(RelType.EXPLAINS_EFFICACY, RelType)
        self.assertIn(RelType.EXPLAINS_FORMULA_COMPONENT, RelType)
        self.assertIn(RelType.EXPLAINS_PATHOGENESIS, RelType)
        self.assertIn(RelType.EXPLAINS_SYMPTOM, RelType)
        self.assertIn(RelType.SYMPTOM_OF, RelType)


class TestAllowedProperties(unittest.TestCase):
    """Property whitelist 查询。"""

    def test_known_label_returns_nonempty(self):
        props = get_allowed_properties("ResearchSession")
        self.assertIsInstance(props, frozenset)
        self.assertIn("cycle_id", props)

    def test_unknown_label_returns_empty(self):
        props = get_allowed_properties("NonExistentLabel")
        self.assertEqual(props, frozenset())

    def test_graph_schema_meta_properties(self):
        props = get_allowed_properties("GraphSchemaMeta")
        self.assertIn("schema_version", props)
        self.assertIn("bootstrapped_at", props)

    def test_philology_detail_properties(self):
        exegesis_props = get_allowed_properties("ExegesisEntry")
        self.assertIn("canonical", exegesis_props)
        self.assertIn("definition", exegesis_props)
        self.assertIn("decision_basis", exegesis_props)
        exegesis_term_props = get_allowed_properties("ExegesisTerm")
        self.assertIn("canonical", exegesis_term_props)
        self.assertIn("decision_basis", exegesis_term_props)
        fragment_props = get_allowed_properties("FragmentCandidate")
        self.assertIn("candidate_kind", fragment_props)
        self.assertIn("reconstruction_basis", fragment_props)
        self.assertIn("decision_basis", fragment_props)
        textual_chain_props = get_allowed_properties("TextualEvidenceChain")
        self.assertIn("claim_id", textual_chain_props)
        self.assertIn("claim_type", textual_chain_props)
        self.assertIn("decision_basis", textual_chain_props)
        symptom_props = get_allowed_properties("Symptom")
        self.assertIn("name", symptom_props)
        self.assertIn("description", symptom_props)
        self.assertIn("symptom_category", symptom_props)
        self.assertIn("manifestation_source", symptom_props)
        self.assertIn("syndrome_canonical", symptom_props)
        self.assertIn("source_syndrome", symptom_props)
        self.assertIn("source_exegesis_id", symptom_props)
        property_props = get_allowed_properties("Property")
        self.assertIn("source_exegesis_id", property_props)
        self.assertIn("syndrome_canonical", property_props)
        self.assertIn("source_syndrome", property_props)
        herb_props = get_allowed_properties("Herb")
        self.assertIn("formula_canonical", herb_props)
        self.assertIn("source_formula", herb_props)
        self.assertIn("formula_role", herb_props)
        efficacy_props = get_allowed_properties("Efficacy")
        self.assertIn("herb_canonical", efficacy_props)
        self.assertIn("source_herb", efficacy_props)
        self.assertIn("source_exegesis_id", efficacy_props)
        herb_rel_props = get_allowed_rel_properties("EXPLAINS_HERB")
        self.assertIn("herb_canonical", herb_rel_props)
        self.assertIn("source_herb", herb_rel_props)
        self.assertIn("source_exegesis_id", herb_rel_props)
        self.assertIn("provenance_kind", herb_rel_props)
        formula_rel_props = get_allowed_rel_properties("EXPLAINS_FORMULA")
        self.assertIn("formula_canonical", formula_rel_props)
        self.assertIn("source_formula", formula_rel_props)
        self.assertIn("source_exegesis_id", formula_rel_props)
        self.assertIn("provenance_kind", formula_rel_props)


class TestRegistryHelpers(unittest.TestCase):
    """注册表查询函数。"""

    def test_get_registered_labels(self):
        labels = get_registered_labels()
        self.assertIn("Formula", labels)
        self.assertIn("GraphSchemaMeta", labels)

    def test_get_registered_rel_types(self):
        types = get_registered_rel_types()
        self.assertIn("HAS_PHASE", types)
        self.assertIn("CAPTURED", types)


class TestSchemaSummary(unittest.TestCase):
    """Schema 摘要函数。"""

    def test_summary_contains_version(self):
        summary = get_schema_summary()
        self.assertEqual(summary["schema_version"], GRAPH_SCHEMA_VERSION)

    def test_summary_counts_match_enums(self):
        summary = get_schema_summary()
        self.assertEqual(summary["node_label_count"], len(NodeLabel))
        self.assertEqual(summary["rel_type_count"], len(RelType))

    def test_summary_lists_sorted(self):
        summary = get_schema_summary()
        self.assertEqual(summary["node_labels"], sorted(summary["node_labels"]))
        self.assertEqual(summary["rel_types"], sorted(summary["rel_types"]))


class TestBuildSchemaMetaNodeProperties(unittest.TestCase):
    """GraphSchemaMeta 节点属性构造。"""

    def test_contains_version_and_counts(self):
        props = build_schema_meta_node_properties()
        self.assertEqual(props["schema_version"], GRAPH_SCHEMA_VERSION)
        self.assertIn("bootstrapped_at", props)
        self.assertIn("node_label_count", props)
        self.assertIn("rel_type_count", props)


class TestDetectSchemaDrift(unittest.TestCase):
    """Schema drift 检测三种分支。"""

    def test_no_stored_version(self):
        result = detect_schema_drift(None)
        self.assertTrue(result["drift_detected"])
        self.assertIsNone(result["stored_version"])
        self.assertIn("无 schema version", result["detail"])

    def test_version_match(self):
        result = detect_schema_drift(GRAPH_SCHEMA_VERSION)
        self.assertFalse(result["drift_detected"])
        self.assertEqual(result["stored_version"], GRAPH_SCHEMA_VERSION)

    def test_version_mismatch(self):
        result = detect_schema_drift("0.0.0")
        self.assertTrue(result["drift_detected"])
        self.assertEqual(result["stored_version"], "0.0.0")
        self.assertIn("不一致", result["detail"])


class TestResolveNodeLabel(unittest.TestCase):
    """Label 解析边界。"""

    def test_known_label(self):
        self.assertEqual(resolve_node_label("Formula"), "Formula")

    def test_unknown_label_returns_default(self):
        self.assertEqual(resolve_node_label("UnknownXyz"), "Entity")

    def test_custom_default(self):
        self.assertEqual(resolve_node_label("UnknownXyz", "Fallback"), "Fallback")


class TestResolveRelType(unittest.TestCase):
    """RelType 解析边界。"""

    def test_known_type(self):
        self.assertEqual(resolve_rel_type("TREATS"), "TREATS")

    def test_unknown_type_returns_default(self):
        self.assertEqual(resolve_rel_type("FOOBAR"), "RELATED_TO")


class TestNeo4jDriverSchemaBootstrap(unittest.TestCase):
    """Neo4jDriver schema bootstrap / version / ensure (mock)。"""

    def _make_driver(self):
        from src.storage.neo4j_driver import Neo4jDriver
        d = Neo4jDriver(uri="bolt://localhost:7687", auth=("neo4j", "test"), database="testdb")
        d.driver = MagicMock()
        return d

    def test_bootstrap_schema_writes_meta_node(self):
        driver = self._make_driver()
        mock_session = MagicMock()
        driver.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        driver.driver.session.return_value.__exit__ = MagicMock(return_value=False)
        driver._bootstrap_schema()
        mock_session.execute_write.assert_called_once()

    def test_get_schema_version_returns_stored(self):
        driver = self._make_driver()
        mock_record = {"v": "1.0.0"}
        mock_session = MagicMock()
        mock_session.execute_read.return_value = [mock_record]
        driver.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        driver.driver.session.return_value.__exit__ = MagicMock(return_value=False)
        ver = driver.get_schema_version()
        self.assertEqual(ver, "1.0.0")

    def test_get_schema_version_returns_none_when_empty(self):
        driver = self._make_driver()
        mock_session = MagicMock()
        mock_session.execute_read.return_value = []
        driver.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        driver.driver.session.return_value.__exit__ = MagicMock(return_value=False)
        ver = driver.get_schema_version()
        self.assertIsNone(ver)

    def test_ensure_schema_version_no_drift(self):
        driver = self._make_driver()
        mock_record = {"v": GRAPH_SCHEMA_VERSION}
        mock_session = MagicMock()
        mock_session.execute_read.return_value = [mock_record]
        driver.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        driver.driver.session.return_value.__exit__ = MagicMock(return_value=False)
        result = driver.ensure_schema_version()
        self.assertFalse(result["drift_detected"])

    def test_ensure_schema_version_drift(self):
        driver = self._make_driver()
        mock_record = {"v": "0.0.0"}
        mock_session = MagicMock()
        mock_session.execute_read.return_value = [mock_record]
        driver.driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        driver.driver.session.return_value.__exit__ = MagicMock(return_value=False)
        result = driver.ensure_schema_version()
        self.assertTrue(result["drift_detected"])


class TestEntityToNeo4jNodeUsesRegistry(unittest.TestCase):
    """entity_to_neo4j_node 应通过 graph_schema 决定 label。"""

    def test_herb_label(self):
        from src.storage.neo4j_driver import entity_to_neo4j_node
        entity = MagicMock()
        entity.id = "e1"
        entity.type = MagicMock(value="herb")
        entity.name = "甘草"
        entity.confidence = 0.9
        entity.alternative_names = []
        entity.description = ""
        entity.entity_metadata = {}
        node = entity_to_neo4j_node(entity)
        self.assertEqual(node.label, "Herb")

    def test_unknown_type_fallback_entity(self):
        from src.storage.neo4j_driver import entity_to_neo4j_node
        entity = MagicMock()
        entity.id = "e2"
        entity.type = MagicMock(value="unknown_type")
        entity.name = "xxx"
        entity.confidence = 0.5
        entity.alternative_names = []
        entity.description = ""
        entity.entity_metadata = {}
        node = entity_to_neo4j_node(entity)
        self.assertEqual(node.label, "Entity")


class TestBackfillUsesRegistry(unittest.TestCase):
    """Backfill 构建函数应使用 NodeLabel / RelType。"""

    def test_session_node_label(self):
        from src.research.research_session_graph_backfill import (
            build_research_session_graph_nodes,
        )
        records = [{"cycle_id": "c1", "cycle_name": "test", "status": "active"}]
        nodes = build_research_session_graph_nodes(records)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].label, NodeLabel.RESEARCH_SESSION.value)

    def test_phase_node_label(self):
        from src.research.research_session_graph_backfill import (
            build_research_phase_execution_graph_nodes,
        )
        records = [{"id": "p1", "phase": "observe", "status": "active"}]
        nodes = build_research_phase_execution_graph_nodes("c1", records)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].label, NodeLabel.RESEARCH_PHASE_EXECUTION.value)

    def test_artifact_node_label(self):
        from src.research.research_session_graph_backfill import (
            build_research_artifact_graph_nodes,
        )
        records = [{"id": "a1", "name": "test.pdf", "artifact_type": "pdf"}]
        nodes = build_research_artifact_graph_nodes("c1", records)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].label, NodeLabel.RESEARCH_ARTIFACT.value)

    def test_research_edge_types(self):
        from src.research.research_session_graph_backfill import (
            build_research_graph_edges,
        )
        phases = [{"id": "p1", "phase": "observe"}]
        artifacts = [{"id": "a1", "phase_execution_id": "p1"}]
        edges = build_research_graph_edges("c1", phases, artifacts)
        rel_types = {e[0].relationship_type for e in edges}
        self.assertIn(RelType.HAS_PHASE.value, rel_types)
        self.assertIn(RelType.GENERATED.value, rel_types)


class TestEntityTypeToLabelMapping(unittest.TestCase):
    """ENTITY_TYPE_TO_LABEL 映射完整性与一致性。"""

    def test_all_values_are_registered_labels(self):
        from src.storage.graph_schema import ENTITY_TYPE_TO_LABEL
        labels = get_registered_labels()
        for etype, label in ENTITY_TYPE_TO_LABEL.items():
            self.assertIn(label, labels, f"'{label}' for type '{etype}' not registered")

    def test_covers_core_tcm_types(self):
        from src.storage.graph_schema import ENTITY_TYPE_TO_LABEL
        expected = {"formula", "herb", "syndrome", "efficacy", "target", "pathway"}
        self.assertTrue(expected.issubset(set(ENTITY_TYPE_TO_LABEL.keys())))

    def test_neo4j_driver_uses_same_mapping(self):
        from src.storage.graph_schema import ENTITY_TYPE_TO_LABEL
        from src.storage.neo4j_driver import _TYPE_TO_LABEL
        self.assertIs(_TYPE_TO_LABEL, ENTITY_TYPE_TO_LABEL)


class TestKgStatsEndpoint(unittest.TestCase):
    """GET /analysis/kg/stats 端点。"""

    def test_returns_schema_summary_without_neo4j(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.routes.analysis import router

        app = FastAPI()
        app.include_router(router, prefix="/analysis")
        client = TestClient(app)

        response = client.get("/analysis/kg/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("schema_version", data)
        self.assertEqual(data["schema_version"], GRAPH_SCHEMA_VERSION)
        self.assertIn("node_label_count", data)
        self.assertIn("rel_type_count", data)
        # Without live Neo4j, drift should be None
        self.assertIsNone(data.get("schema_drift_detected"))


class TestKgSubgraphEndpoint(unittest.TestCase):
    """GET /analysis/kg/subgraph 端点。"""

    def test_returns_template_without_cycle_id(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.routes.analysis import router

        app = FastAPI()
        app.include_router(router, prefix="/analysis")
        client = TestClient(app)

        response = client.get(
            "/analysis/kg/subgraph",
            params={
                "graph_type": "philology_asset_graph",
                "work_title": "本草纲目",
                "version_lineage_key": "lin-001",
                "witness_key": "wit-001",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["graph_type"], "philology_asset_graph")
        self.assertIn("template", data)
        self.assertIn("cypher", data["template"])
        self.assertEqual(data["record_count"], 0)
        self.assertEqual(data["params"]["work_title"], "本草纲目")
        self.assertEqual(data["params"]["version_lineage_key"], "lin-001")
        self.assertEqual(data["params"]["witness_key"], "wit-001")

    def test_rejects_unknown_graph_type(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.routes.analysis import router

        app = FastAPI()
        app.include_router(router, prefix="/analysis")
        client = TestClient(app)

        response = client.get("/analysis/kg/subgraph", params={"graph_type": "unknown_graph"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["error"], "unsupported_graph_type")


if __name__ == "__main__":
    unittest.main()
