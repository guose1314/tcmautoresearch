import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.storage.neo4j_driver import (
    Neo4jDriver,
    _build_unique_constraint_cypher,
    _get_neo4j_graph_database,
    create_knowledge_graph,
)


class _FakeQueryResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._rows[0] if self._rows else None

    def consume(self):
        return None


class _FakeTransaction:
    def run(self, query, **params):
        formula_name = params.get("formula_name")
        similar_formula_name = params.get("similar_formula_name")
        node_id = params.get("id")
        if "RETURN h.name AS herb_name" in query:
            return _FakeQueryResult(
                [
                    {
                        "herb_name": "人参",
                        "formula_role": "SOVEREIGN",
                        "similar_formula_role": "MINISTER",
                    },
                    {
                        "herb_name": "白术",
                        "formula_role": "MINISTER",
                        "similar_formula_role": "ASSISTANT",
                    },
                ]
            )
        if "RETURN collect(DISTINCT s.name) AS syndromes" in query:
            return _FakeQueryResult([{"syndromes": ["脾气虚证"]}])
        if "RETURN type(r) AS relationship_type" in query:
            return _FakeQueryResult(
                [
                    {
                        "relationship_type": "SIMILAR_TO",
                        "properties": {
                            "confidence": 0.92,
                            "source": f"{formula_name}->{similar_formula_name}",
                        },
                    }
                ]
            )
        if "RETURN n" in query:
            return _FakeQueryResult(
                [{"n": {"id": node_id, "name": "四君子汤", "label": "Formula"}}]
            )
        if "WHERE type(r) IN $composition_roles" in query and "AS sovereign" in query:
            return _FakeQueryResult(
                [
                    {
                        "sovereign": ["人参"],
                        "minister": ["白术"],
                        "assistant": ["茯苓"],
                        "envoy": ["甘草"],
                    }
                ]
            )
        if "RETURN f2.name as name, f2 as properties" in query:
            return _FakeQueryResult(
                [
                    {
                        "name": "六君子汤",
                        "properties": {"name": "六君子汤", "category": "补气方"},
                    }
                ]
            )
        if "RETURN 1" in query:
            return _FakeQueryResult([{"ok": 1}])
        raise AssertionError(f"unexpected query: {query}")


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_read(self, callback):
        return callback(_FakeTransaction())

    def run(self, query, **params):
        return _FakeTransaction().run(query, **params)


class _FakeDriver:
    def session(self, database=None):
        del database
        return _FakeSession()


class _RecordingTransaction:
    def __init__(self, backend):
        self._backend = backend

    def run(self, query, **params):
        self._backend.calls.append((query, params))
        if "AS sovereign" in query and "composition_roles" in params:
            return _FakeQueryResult(
                [
                    {
                        "sovereign": ["人参"],
                        "minister": ["白术"],
                        "assistant": ["茯苓"],
                        "envoy": [],
                    }
                ]
            )
        if "CALL (start)" in query:
            return _FakeQueryResult([{"nodes": [], "edges": []}])
        if "RETURN 1" in query:
            return _FakeQueryResult([{"ok": 1}])
        raise AssertionError(f"unexpected query: {query}")


class _RecordingSession:
    def __init__(self, backend):
        self._backend = backend

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_read(self, callback):
        return callback(_RecordingTransaction(self._backend))

    def run(self, query, **params):
        self._backend.calls.append((query, params))
        return _FakeQueryResult([])


class _RecordingDriver:
    def __init__(self):
        self.calls = []

    def session(self, database=None):
        del database
        return _RecordingSession(self)


class _FakeDiGraph:
    def add_node(self, *_args, **_kwargs):
        return None

    def add_edge(self, *_args, **_kwargs):
        return None


class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth, **kwargs):
        del uri, auth, kwargs
        return _FakeDriver()


class _FailingDriver:
    def session(self, database=None):
        del database
        raise RuntimeError("connection failed")


class _CapturedNeo4jDriver:
    instances = []

    def __init__(self, uri, auth, database="neo4j", **kwargs):
        self.uri = uri
        self.auth = auth
        self.database = database
        self.kwargs = kwargs
        self.connected = False
        type(self).instances.append(self)

    def connect(self):
        self.connected = True


class TestNeo4jDriverSimilarityEvidence(unittest.TestCase):
    def setUp(self):
        self.original_password = os.environ.get("TCM_NEO4J_PASSWORD")
        _CapturedNeo4jDriver.instances.clear()

    def tearDown(self):
        if self.original_password is None:
            os.environ.pop("TCM_NEO4J_PASSWORD", None)
        else:
            os.environ["TCM_NEO4J_PASSWORD"] = self.original_password

    def test_get_neo4j_graph_database_uses_lazy_import(self):
        with patch(
            "src.storage.neo4j_driver.import_module",
            return_value=SimpleNamespace(GraphDatabase=_FakeGraphDatabase),
        ) as mocked:
            graph_database = _get_neo4j_graph_database()

        self.assertIs(graph_database, _FakeGraphDatabase)
        mocked.assert_called_once_with("neo4j")

    def test_connect_uses_lazy_import_graphdatabase(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))

        with patch(
            "src.storage.neo4j_driver._get_neo4j_graph_database",
            return_value=_FakeGraphDatabase,
        ) as mocked:
            driver.connect()

        self.assertIsNotNone(driver.driver)
        mocked.assert_called_once()

    def test_collect_formula_similarity_evidence_returns_structured_contract(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = _FakeDriver()

        payload = driver.collect_formula_similarity_evidence("四君子汤", "六君子汤")

        self.assertEqual(payload["source"], "neo4j")
        self.assertEqual(payload["shared_syndromes"], ["脾气虚证"])
        self.assertEqual(len(payload["shared_herbs"]), 2)
        self.assertEqual(payload["shared_herbs"][0]["herb"], "人参")
        self.assertEqual(payload["shared_herbs"][0]["formula_role"], "sovereign")
        self.assertEqual(payload["shared_herbs"][0]["similar_formula_role"], "minister")
        self.assertEqual(
            payload["direct_relationships"][0]["relationship_type"], "SIMILAR_TO"
        )
        self.assertAlmostEqual(payload["evidence_score"], 0.7, places=3)

    def test_collect_formula_similarity_evidence_returns_empty_dict_on_failure(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = _FailingDriver()

        payload = driver.collect_formula_similarity_evidence("四君子汤", "六君子汤")

        self.assertEqual(payload, {})

    def test_basic_query_methods_do_not_require_direct_neo4j_import(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = _FakeDriver()

        with patch(
            "src.storage.neo4j_driver.import_module",
            side_effect=AssertionError("should not import neo4j during query"),
        ):
            node = driver.get_node("formula:四君子汤", "Formula")
            composition = driver.find_formula_composition("四君子汤")
            similar_formulas = driver.find_similar_formulas("四君子汤", limit=5)

        self.assertEqual(node["name"], "四君子汤")
        self.assertEqual(composition["sovereign"], ["人参"])
        self.assertEqual(similar_formulas[0]["name"], "六君子汤")

    def test_find_formula_composition_avoids_optional_missing_reltype_noise(self):
        backend = _RecordingDriver()
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = backend

        payload = driver.find_formula_composition("四君子汤")

        self.assertEqual(payload["sovereign"], ["人参"])
        query, params = backend.calls[0]
        self.assertIn("OPTIONAL MATCH (f)-[r]->(h:Herb)", query)
        self.assertIn("WHERE type(r) IN $composition_roles", query)
        self.assertNotIn("[:ENVOY]", query)
        self.assertEqual(
            params,
            {
                "formula_name": "四君子汤",
                "composition_roles": ["SOVEREIGN", "MINISTER", "ASSISTANT", "ENVOY"],
            },
        )

    def test_get_subgraph_uses_scoped_call_subquery(self):
        backend = _RecordingDriver()
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = backend
        graph = create_knowledge_graph(
            {"neo4j": {"enabled": False}}, preload_formulas=False
        )
        del graph

        from src.storage.neo4j_driver import Neo4jKnowledgeGraph

        with patch(
            "src.storage.neo4j_driver.import_module",
            return_value=SimpleNamespace(DiGraph=_FakeDiGraph),
        ):
            kg = Neo4jKnowledgeGraph(driver, preload_formulas=False)
            kg.get_subgraph("entity::四君子汤", depth=2)

        query, params = backend.calls[0]
        self.assertIn("CALL (start)", query)
        self.assertNotIn("CALL {", query)
        self.assertEqual(params, {"entity_id": "entity::四君子汤"})

    def test_create_knowledge_graph_prefers_explicit_password_over_env(self):
        os.environ["TCM_NEO4J_PASSWORD"] = "stale-env-password"

        with (
            patch("src.storage.neo4j_driver.Neo4jDriver", _CapturedNeo4jDriver),
            patch(
                "src.storage.neo4j_driver.Neo4jKnowledgeGraph",
                side_effect=lambda driver, preload_formulas=False: {
                    "driver": driver,
                    "preload_formulas": preload_formulas,
                },
            ),
        ):
            graph = create_knowledge_graph(
                {
                    "neo4j": {
                        "enabled": True,
                        "uri": "bolt://localhost:7687",
                        "user": "neo4j",
                        "password": "explicit-neo4j-password",
                        "password_env": "TCM_NEO4J_PASSWORD",
                        "database": "neo4j",
                    }
                },
                preload_formulas=True,
            )

        self.assertEqual(len(_CapturedNeo4jDriver.instances), 1)
        self.assertEqual(
            _CapturedNeo4jDriver.instances[0].auth,
            ("neo4j", "explicit-neo4j-password"),
        )
        self.assertTrue(graph["preload_formulas"])

    def test_setup_constraints_uses_ontology_registry_specs(self):
        backend = _RecordingDriver()
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = backend

        driver._setup_constraints_and_indexes()

        statements = [query for query, _params in backend.calls]
        self.assertTrue(
            any(
                "FOR (n:Herb) REQUIRE n.id IS UNIQUE" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "FOR (n:Literature) REQUIRE n.id IS UNIQUE" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "FOR (n:Formula) REQUIRE n.id IS UNIQUE" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "FOR (n:EvidenceClaim) REQUIRE n.id IS UNIQUE" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "CREATE FULLTEXT INDEX ontology_herb_fulltext" in statement
                and "FOR (n:Herb)" in statement
                and "n.name" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "CREATE FULLTEXT INDEX ontology_literature_fulltext" in statement
                and "FOR (n:Literature)" in statement
                and "n.title" in statement
                for statement in statements
            )
        )

    def test_setup_constraints_falls_back_to_legacy_ddl_on_registry_failure(self):
        backend = _RecordingDriver()
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = backend

        with patch(
            "src.storage.ontology.registry.load_ontology_registry",
            side_effect=RuntimeError("registry down"),
        ):
            driver._setup_constraints_and_indexes()

        statements = [query for query, _params in backend.calls]
        self.assertTrue(
            any(
                "FOR (p:Prescription) REQUIRE p.name IS UNIQUE" in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "CREATE FULLTEXT INDEX entity_text_index" in statement
                for statement in statements
            )
        )

    def test_ontology_constraint_builder_rejects_illegal_label(self):
        with self.assertRaises(ValueError):
            _build_unique_constraint_cypher(
                {
                    "name": "ontology_bad_unique",
                    "label": "Bad Label",
                    "property": "id",
                }
            )


if __name__ == "__main__":
    unittest.main()
