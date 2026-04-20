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
from unittest.mock import MagicMock, patch

from src.storage.graph_schema import (
    _SCHEMA_META_LABEL,
    _SCHEMA_META_NODE_ID,
    GRAPH_SCHEMA_VERSION,
    NodeLabel,
    RelType,
    build_schema_meta_node_properties,
    detect_schema_drift,
    get_allowed_properties,
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


if __name__ == "__main__":
    unittest.main()
