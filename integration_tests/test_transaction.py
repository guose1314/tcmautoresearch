import unittest

from src.storage.transaction import TransactionCoordinator


class _RecordingPGSession:
    def __init__(self, *, flush_error=None, commit_error=None):
        self.flush_error = flush_error
        self.commit_error = commit_error
        self.added = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def add(self, instance):
        self.added.append(instance)

    def add_all(self, instances):
        self.added.extend(instances)

    def flush(self):
        self.flush_calls += 1
        if self.flush_error is not None:
            raise self.flush_error

    def commit(self):
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


class _RecordingNeo4jTx:
    def __init__(self, owner):
        self._owner = owner

    def run(self, query, **params):
        self._owner.executed_queries.append((query, params))
        if query in self._owner.fail_on_queries:
            raise RuntimeError(f"forced neo4j failure: {query}")
        return {"query": query, "params": params}


class _RecordingNeo4jSession:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback):
        self._owner.execute_write_calls += 1
        return callback(_RecordingNeo4jTx(self._owner))


class _RecordingNeo4jBackend:
    def __init__(self, owner):
        self._owner = owner

    def session(self, database=None):
        self._owner.session_databases.append(database)
        return _RecordingNeo4jSession(self._owner)


class _RecordingNeo4jDriver:
    def __init__(self, *, fail_on_queries=None):
        self.database = "neo4j"
        self.fail_on_queries = set(fail_on_queries or [])
        self.executed_queries = []
        self.execute_write_calls = 0
        self.session_databases = []
        self.driver = _RecordingNeo4jBackend(self)


class TransactionCoordinatorIntegrationTest(unittest.TestCase):
    def test_neo4j_failure_rolls_back_pg_and_compensates_prior_writes(self):
        pg_session = _RecordingPGSession()
        neo4j_driver = _RecordingNeo4jDriver(fail_on_queries={"CREATE second"})
        txn = TransactionCoordinator(pg_session, neo4j_driver, auto_commit=False)

        txn.pg_add({"id": 1})
        txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)
        txn.neo4j_write("CREATE second", compensate_cypher="DELETE second", id=2)

        result = txn.commit()

        self.assertFalse(result.success)
        self.assertFalse(result.pg_committed)
        self.assertFalse(result.neo4j_committed)
        self.assertEqual(result.compensations_applied, 1)
        self.assertIn("Neo4j 执行失败", result.error)
        self.assertEqual(pg_session.flush_calls, 1)
        self.assertEqual(pg_session.commit_calls, 0)
        self.assertEqual(pg_session.rollback_calls, 1)
        self.assertEqual(
            neo4j_driver.executed_queries,
            [
                ("CREATE first", {"id": 1}),
                ("CREATE second", {"id": 2}),
                ("DELETE first", {"id": 1}),
            ],
        )

    def test_pg_flush_failure_prevents_any_neo4j_execution(self):
        pg_session = _RecordingPGSession(flush_error=RuntimeError("flush blocked"))
        neo4j_driver = _RecordingNeo4jDriver()
        txn = TransactionCoordinator(pg_session, neo4j_driver, auto_commit=False)

        txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)

        result = txn.commit()

        self.assertFalse(result.success)
        self.assertFalse(result.pg_committed)
        self.assertFalse(result.neo4j_committed)
        self.assertIn("PostgreSQL flush 失败", result.error)
        self.assertEqual(pg_session.flush_calls, 1)
        self.assertEqual(pg_session.commit_calls, 0)
        self.assertEqual(pg_session.rollback_calls, 1)
        self.assertEqual(neo4j_driver.executed_queries, [])
        self.assertEqual(neo4j_driver.execute_write_calls, 0)

    def test_pg_commit_failure_compensates_executed_neo4j_writes(self):
        pg_session = _RecordingPGSession(commit_error=RuntimeError("commit blocked"))
        neo4j_driver = _RecordingNeo4jDriver()
        txn = TransactionCoordinator(pg_session, neo4j_driver, auto_commit=False)

        txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)

        result = txn.commit()

        self.assertFalse(result.success)
        self.assertFalse(result.pg_committed)
        self.assertFalse(result.neo4j_committed)
        self.assertEqual(result.compensations_applied, 1)
        self.assertIn("PostgreSQL commit 失败", result.error)
        self.assertEqual(pg_session.flush_calls, 1)
        self.assertEqual(pg_session.commit_calls, 1)
        self.assertEqual(
            neo4j_driver.executed_queries,
            [
                ("CREATE first", {"id": 1}),
                ("DELETE first", {"id": 1}),
            ],
        )


if __name__ == "__main__":
    unittest.main()