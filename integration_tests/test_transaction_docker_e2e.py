import os
import socket
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yaml

from src.infrastructure.config_loader import load_secret_section
from src.infrastructure.persistence import Document
from src.storage.backend_factory import StorageBackendFactory

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_password(env_name, secret_section):
    password = os.environ.get(env_name)
    if password:
        return password

    secret_config = load_secret_section(
        secret_section,
        root_path=_REPO_ROOT,
        environment="production",
        default={},
    )
    value = str(secret_config.get("password") or "").strip()
    if value:
        return value

    secrets_file = _REPO_ROOT / "secrets.yml"
    if not secrets_file.exists():
        return ""

    payload = yaml.safe_load(secrets_file.read_text(encoding="utf-8")) or {}
    section = payload.get(secret_section)
    if not isinstance(section, dict):
        return ""
    return str(section.get("password") or "").strip()


def _port_open(host, port):
    with socket.socket() as sock:
        sock.settimeout(2)
        try:
            sock.connect((host, int(port)))
        except OSError:
            return False
    return True


@unittest.skipUnless(
    os.environ.get("TCM_RUN_DOCKER_E2E") == "1",
    "设置 TCM_RUN_DOCKER_E2E=1 后运行真实容器事务集成测试",
)
class TransactionDockerE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        pg_password = _resolve_password("TCM_DB_PASSWORD", "database")
        neo4j_password = _resolve_password("TCM_NEO4J_PASSWORD", "neo4j")

        if not pg_password:
            raise RuntimeError("缺少 PostgreSQL 密码，请设置 TCM_DB_PASSWORD 或在 secrets.yml 中配置 database.password")
        if not neo4j_password:
            raise RuntimeError("缺少 Neo4j 密码，请设置 TCM_NEO4J_PASSWORD 或在 secrets.yml 中配置 neo4j.password")

        pg_host = os.environ.get("TCM_DOCKER_PG_HOST", "127.0.0.1")
        pg_port = int(os.environ.get("TCM_DOCKER_PG_PORT", "5432"))
        neo4j_uri = os.environ.get("TCM_DOCKER_NEO4J_URI", "bolt://127.0.0.1:7687")
        parsed_neo4j = urlparse(neo4j_uri)
        neo4j_host = parsed_neo4j.hostname or "127.0.0.1"
        neo4j_port = parsed_neo4j.port or 7687

        if not _port_open(pg_host, pg_port):
            raise RuntimeError(f"PostgreSQL 不可达: {pg_host}:{pg_port}")
        if not _port_open(neo4j_host, neo4j_port):
            raise RuntimeError(f"Neo4j 不可达: {neo4j_host}:{neo4j_port}")

        cls._node_label = "TransactionE2ENode"
        cls._factory = StorageBackendFactory(
            {
                "database": {
                    "type": "postgresql",
                    "host": pg_host,
                    "port": pg_port,
                    "name": os.environ.get("TCM_DOCKER_PG_DB", "tcmautoresearch"),
                    "user": os.environ.get("TCM_DOCKER_PG_USER", "tcm"),
                    "password": pg_password,
                    "ssl_mode": os.environ.get("TCM_DOCKER_PG_SSLMODE", "prefer"),
                },
                "neo4j": {
                    "enabled": True,
                    "uri": neo4j_uri,
                    "user": os.environ.get("TCM_DOCKER_NEO4J_USER", "neo4j"),
                    "password": neo4j_password,
                    "database": os.environ.get("TCM_DOCKER_NEO4J_DATABASE", "neo4j"),
                },
            }
        )
        report = cls._factory.initialize()
        if report.get("pg_status") != "active":
            raise RuntimeError(f"PostgreSQL 初始化失败: {report.get('pg_status')}")
        if report.get("neo4j_status") != "active":
            raise RuntimeError(f"Neo4j 初始化失败: {report.get('neo4j_status')}")

    @classmethod
    def tearDownClass(cls):
        factory = getattr(cls, "_factory", None)
        if factory is not None:
            factory.close()
        super().tearDownClass()

    def _cleanup_document(self, source_file):
        with self._factory.db_manager.session_scope() as session:
            session.query(Document).filter(Document.source_file == source_file).delete(synchronize_session=False)

    def _cleanup_node(self, node_id):
        self._factory.neo4j_driver.delete_node(node_id, self._node_label)

    def test_commit_persists_pg_and_neo4j(self):
        source_file = f"docker-e2e-{uuid.uuid4().hex}.txt"
        node_id = f"txn-{uuid.uuid4().hex}"

        try:
            with self._factory.transaction() as txn:
                document = Document(
                    source_file=source_file,
                    objective="验证真实容器事务提交流程",
                    raw_text_size=128,
                )
                txn.pg_add(document)
                txn.pg_flush()
                txn.neo4j_write(
                    f"MERGE (n:{self._node_label} {{id: $id}}) "
                    "SET n.document_id = $document_id, n.source_file = $source_file, n.objective = $objective",
                    compensate_cypher=f"MATCH (n:{self._node_label} {{id: $id}}) DETACH DELETE n",
                    id=node_id,
                    document_id=str(document.id),
                    source_file=source_file,
                    objective=document.objective,
                )

            with self._factory.db_manager.session_scope() as session:
                persisted = session.query(Document).filter(Document.source_file == source_file).one_or_none()

            node = self._factory.neo4j_driver.get_node(node_id, self._node_label)

            self.assertIsNotNone(persisted)
            self.assertIsNotNone(node)
            self.assertEqual(node["source_file"], source_file)
            self.assertEqual(node["document_id"], str(persisted.id))
        finally:
            self._cleanup_document(source_file)
            self._cleanup_node(node_id)

    def test_exception_rolls_back_pg_and_skips_neo4j_commit(self):
        source_file = f"docker-e2e-rollback-{uuid.uuid4().hex}.txt"
        node_id = f"txn-rollback-{uuid.uuid4().hex}"

        with self.assertRaisesRegex(RuntimeError, "force rollback"):
            with self._factory.transaction() as txn:
                document = Document(
                    source_file=source_file,
                    objective="验证真实容器事务回滚流程",
                    raw_text_size=256,
                )
                txn.pg_add(document)
                txn.pg_flush()
                txn.neo4j_write(
                    f"MERGE (n:{self._node_label} {{id: $id}}) "
                    "SET n.document_id = $document_id, n.source_file = $source_file",
                    compensate_cypher=f"MATCH (n:{self._node_label} {{id: $id}}) DETACH DELETE n",
                    id=node_id,
                    document_id=str(document.id),
                    source_file=source_file,
                )
                raise RuntimeError("force rollback")

        with self._factory.db_manager.session_scope() as session:
            persisted = session.query(Document).filter(Document.source_file == source_file).one_or_none()

        node = self._factory.neo4j_driver.get_node(node_id, self._node_label)

        self.assertIsNone(persisted)
        self.assertIsNone(node)


if __name__ == "__main__":
    unittest.main()