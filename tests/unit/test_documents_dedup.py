"""T2.3 documents dedup 单元测试。

覆盖：
  - 同 source_file + 同内容 → upsert 同一行（行数不增）
  - 同 source_file + 不同内容 → 新增一行（视为版本演化）
  - 旧 source_file 时间戳后缀剥离 + ingest_run_id 回填
"""

from __future__ import annotations

import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.persistence import (
    Base,
    Document,
    PersistenceService,
    ProcessStatusEnum,
    _split_legacy_source_file_suffix,
)


class SplitLegacySuffixTests(unittest.TestCase):
    def test_strips_legacy_timestamp_suffix(self) -> None:
        sf, run_id = _split_legacy_source_file_suffix("foo_20240101_123456_abcdef01")
        self.assertEqual(sf, "foo")
        self.assertEqual(run_id, "20240101_123456_abcdef01")

    def test_passthrough_when_no_suffix(self) -> None:
        sf, run_id = _split_legacy_source_file_suffix("data/golden_corpus.txt")
        self.assertEqual(sf, "data/golden_corpus.txt")
        self.assertIsNone(run_id)

    def test_passthrough_when_partial_match(self) -> None:
        sf, run_id = _split_legacy_source_file_suffix("foo_20240101")
        self.assertEqual(sf, "foo_20240101")
        self.assertIsNone(run_id)


class DocumentDedupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _new_doc(self, *, source_file: str, content_hash: str | None) -> Document:
        return Document(
            source_file=source_file,
            content_hash=content_hash,
            raw_text_size=0,
            entities_extracted_count=0,
            process_status=ProcessStatusEnum.COMPLETED,
        )

    def test_same_source_same_hash_collides(self) -> None:
        with self.Session() as session:
            session.add(
                self._new_doc(source_file="data/foo.txt", content_hash="a" * 64)
            )
            session.commit()
            session.add(
                self._new_doc(source_file="data/foo.txt", content_hash="a" * 64)
            )
            from sqlalchemy.exc import IntegrityError

            with self.assertRaises(IntegrityError):
                session.commit()

    def test_same_source_different_hash_allowed(self) -> None:
        with self.Session() as session:
            session.add(
                self._new_doc(source_file="data/foo.txt", content_hash="a" * 64)
            )
            session.add(
                self._new_doc(source_file="data/foo.txt", content_hash="b" * 64)
            )
            session.commit()
            count = (
                session.query(Document).filter_by(source_file="data/foo.txt").count()
            )
            self.assertEqual(count, 2)


class UpsertDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        from src.infrastructure.persistence import DatabaseManager

        self.db = DatabaseManager("sqlite:///:memory:")
        self.db.init_db()
        self.svc = PersistenceService()
        self.svc.connection_string = "sqlite:///:memory:"
        self.svc.engine = self.db.engine
        self.svc.database_manager = self.db

    def test_upsert_dedup_round_trip(self) -> None:
        payload = {
            "document": {
                "source_file": "data/foo.txt",
                "content_hash": "c" * 64,
            },
            "entities": [],
            "relationships": [],
        }
        first = self.svc.persist_document_graph(payload)
        second = self.svc.persist_document_graph(payload)
        self.assertEqual(first["document"]["id"], second["document"]["id"])
        with self.db.session_scope() as session:
            self.assertEqual(session.query(Document).count(), 1)

    def test_upsert_legacy_suffix_normalized(self) -> None:
        payload = {
            "document": {
                "source_file": "data/foo.txt_20240101_123456_abcdef01",
                "content_hash": "d" * 64,
            },
            "entities": [],
            "relationships": [],
        }
        result = self.svc.persist_document_graph(payload)
        with self.db.session_scope() as session:
            doc = (
                session.query(Document)
                .filter_by(id=uuid.UUID(result["document"]["id"]))
                .one()
            )
            self.assertEqual(doc.source_file, "data/foo.txt")
            self.assertEqual(doc.ingest_run_id, "20240101_123456_abcdef01")

    def test_upsert_dedup_by_canonical_document_key_across_filenames(self) -> None:
        first = self.svc.persist_document_graph(
            {
                "document": {
                    "source_file": "data/医方.txt",
                    "content_hash": "e" * 64,
                    "canonical_document_key": "f" * 64,
                    "canonical_title": "医方",
                    "normalized_title": "医方",
                    "source_file_hash": "a" * 64,
                    "document_key_version": "canonical-document-v1",
                },
                "entities": [],
                "relationships": [],
            }
        )
        second = self.svc.persist_document_graph(
            {
                "document": {
                    "source_file": "data/醫方.txt",
                    "content_hash": "e" * 64,
                    "canonical_document_key": "f" * 64,
                    "canonical_title": "医方",
                    "normalized_title": "医方",
                    "source_file_hash": "b" * 64,
                    "document_key_version": "canonical-document-v1",
                },
                "entities": [],
                "relationships": [],
            }
        )

        self.assertEqual(first["document"]["id"], second["document"]["id"])
        with self.db.session_scope() as session:
            self.assertEqual(session.query(Document).count(), 1)
            doc = session.query(Document).one()
            self.assertEqual(doc.canonical_document_key, "f" * 64)
            self.assertEqual(doc.canonical_title, "医方")


if __name__ == "__main__":
    unittest.main()
