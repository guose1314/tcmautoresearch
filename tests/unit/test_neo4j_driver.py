import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.storage.neo4j_driver import Neo4jDriver, _get_neo4j_graph_database


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
                        "properties": {"confidence": 0.92, "source": f"{formula_name}->{similar_formula_name}"},
                    }
                ]
            )
        if "RETURN n" in query:
            return _FakeQueryResult([{"n": {"id": node_id, "name": "四君子汤", "label": "Formula"}}])
        if "collect(sovereign.name) as sovereign" in query:
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
            return _FakeQueryResult([{"name": "六君子汤", "properties": {"name": "六君子汤", "category": "补气方"}}])
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


class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth, **kwargs):
        del uri, auth, kwargs
        return _FakeDriver()


class _FailingDriver:
    def session(self, database=None):
        del database
        raise RuntimeError("connection failed")


class TestNeo4jDriverSimilarityEvidence(unittest.TestCase):
    def test_get_neo4j_graph_database_uses_lazy_import(self):
        with patch("src.storage.neo4j_driver.import_module", return_value=SimpleNamespace(GraphDatabase=_FakeGraphDatabase)) as mocked:
            graph_database = _get_neo4j_graph_database()

        self.assertIs(graph_database, _FakeGraphDatabase)
        mocked.assert_called_once_with("neo4j")

    def test_connect_uses_lazy_import_graphdatabase(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))

        with patch("src.storage.neo4j_driver._get_neo4j_graph_database", return_value=_FakeGraphDatabase) as mocked:
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
        self.assertEqual(payload["direct_relationships"][0]["relationship_type"], "SIMILAR_TO")
        self.assertAlmostEqual(payload["evidence_score"], 0.7, places=3)

    def test_collect_formula_similarity_evidence_returns_empty_dict_on_failure(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = _FailingDriver()

        payload = driver.collect_formula_similarity_evidence("四君子汤", "六君子汤")

        self.assertEqual(payload, {})

    def test_basic_query_methods_do_not_require_direct_neo4j_import(self):
        driver = Neo4jDriver("neo4j://example", ("neo4j", "password"))
        driver.driver = _FakeDriver()

        with patch("src.storage.neo4j_driver.import_module", side_effect=AssertionError("should not import neo4j during query")):
            node = driver.get_node("formula:四君子汤", "Formula")
            composition = driver.find_formula_composition("四君子汤")
            similar_formulas = driver.find_similar_formulas("四君子汤", limit=5)

        self.assertEqual(node["name"], "四君子汤")
        self.assertEqual(composition["sovereign"], ["人参"])
        self.assertEqual(similar_formulas[0]["name"], "六君子汤")


if __name__ == "__main__":
    unittest.main()