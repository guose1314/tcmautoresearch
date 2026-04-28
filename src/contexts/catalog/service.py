"""CatalogContext —— 主题 / 学科 / 朝代 三视图编排服务。

T3.1 第一阶段实现：
- 与 ``src.research`` 平级，作为独立 bounded context。
- 接受任意符合 Neo4j 驱动协议的对象（持有 ``.driver`` + ``.database``，
  或仅暴露 ``.session(database=...)`` 上下文管理器），便于注入真实
  ``Neo4jDriver`` 与单元测试 mock。
- ``rebuild_*_view()`` 负责保证约束、MERGE 节点并连接 Document。
- ``query(view, criteria)`` 提供统一查询入口，返回 dict 列表。

后续 T3.2/T3.3 会接入 Document 端的属性提取（topic_key / subject_code /
dynasty）来源；本阶段保持 source-of-truth 由调用方传入，便于测试覆盖。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence

from src.contexts.catalog import cypher as catalog_cypher
from src.contexts.catalog.views import VALID_VIEWS

logger = logging.getLogger(__name__)


class CatalogContextError(RuntimeError):
    """CatalogContext 通用异常。"""


class CatalogContext:
    """目录视图编排服务。

    Parameters
    ----------
    driver : Any
        Neo4j 驱动适配对象。优先使用 ``driver.driver.session(database=...)``
        访问会话；若对象本身带 ``.session(...)`` 也可直接使用。
        ``database`` 取自 ``driver.database`` 或 ``database`` 参数。
    database : str | None
        覆盖 ``driver.database`` 的可选数据库名。
    """

    def __init__(self, driver: Any, *, database: Optional[str] = None) -> None:
        if driver is None:
            raise CatalogContextError("CatalogContext requires a non-null driver")
        self._driver = driver
        self._database = database or getattr(driver, "database", None)
        self._constraints_ensured = False

    # ------------------------------------------------------------------ #
    # 约束 / Schema
    # ------------------------------------------------------------------ #

    def ensure_constraints(self) -> None:
        """幂等创建 Topic / SubjectClass / DynastySlice 唯一约束。"""
        with self._session() as session:
            for ddl in catalog_cypher.CATALOG_CONSTRAINTS:
                session.run(ddl)
        self._constraints_ensured = True
        logger.info("CatalogContext: constraints ensured (%d)", len(catalog_cypher.CATALOG_CONSTRAINTS))

    # ------------------------------------------------------------------ #
    # 视图重建
    # ------------------------------------------------------------------ #

    def rebuild_topic_view(self, topics: Sequence[Mapping[str, Any]]) -> int:
        """重建 Topic 视图。

        ``topics`` 项格式::

            {
                "key": "spleen_qi_deficiency",
                "label": "脾气虚",
                "description": "...",
                "documents": [
                    {"document_id": "<uuid>", "weight": 0.8},
                    ...
                ],
            }

        返回写入的 Topic 节点数。
        """
        self._ensure_constraints_once()
        written = 0
        with self._session() as session:
            for topic in topics or ():
                key = self._require(topic, "key")
                session.run(
                    catalog_cypher.MERGE_TOPIC,
                    key=key,
                    label=topic.get("label"),
                    description=topic.get("description"),
                )
                for doc in topic.get("documents") or ():
                    document_id = self._require(doc, "document_id")
                    session.run(
                        catalog_cypher.LINK_DOCUMENT_TO_TOPIC,
                        document_id=document_id,
                        key=key,
                        weight=doc.get("weight"),
                    )
                written += 1
        return written

    def rebuild_subject_view(self, subjects: Sequence[Mapping[str, Any]]) -> int:
        """重建 SubjectClass 视图。

        ``subjects`` 项格式::

            {
                "code": "R29",
                "name": "中医基础理论",
                "scheme": "CLC",
                "documents": [{"document_id": "<uuid>"}, ...],
            }
        """
        self._ensure_constraints_once()
        written = 0
        with self._session() as session:
            for subject in subjects or ():
                code = self._require(subject, "code")
                session.run(
                    catalog_cypher.MERGE_SUBJECT_CLASS,
                    code=code,
                    name=subject.get("name"),
                    scheme=subject.get("scheme") or "CLC",
                )
                for doc in subject.get("documents") or ():
                    document_id = self._require(doc, "document_id")
                    session.run(
                        catalog_cypher.LINK_DOCUMENT_TO_SUBJECT,
                        document_id=document_id,
                        code=code,
                    )
                written += 1
        return written

    def rebuild_dynasty_view(self, slices: Sequence[Mapping[str, Any]]) -> int:
        """重建 DynastySlice 视图。

        ``slices`` 项格式::

            {
                "dynasty": "Tang",
                "start_year": 618,
                "end_year": 907,
                "documents": [{"document_id": "<uuid>"}, ...],
            }
        """
        self._ensure_constraints_once()
        written = 0
        with self._session() as session:
            for slice_ in slices or ():
                dynasty = self._require(slice_, "dynasty")
                session.run(
                    catalog_cypher.MERGE_DYNASTY_SLICE,
                    dynasty=dynasty,
                    start_year=slice_.get("start_year"),
                    end_year=slice_.get("end_year"),
                )
                for doc in slice_.get("documents") or ():
                    document_id = self._require(doc, "document_id")
                    session.run(
                        catalog_cypher.LINK_DOCUMENT_TO_DYNASTY,
                        document_id=document_id,
                        dynasty=dynasty,
                    )
                written += 1
        return written

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def query(self, view: str, criteria: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """跨三视图统一查询入口。

        ``view`` 取值：``topic`` | ``subject`` | ``dynasty``。
        ``criteria`` 必须包含对应视图的主键 (``key`` / ``code`` / ``dynasty``)，
        ``limit`` 可选（默认 100）。
        """
        view_key = (view or "").strip().lower()
        if view_key not in VALID_VIEWS:
            raise CatalogContextError(
                f"unsupported view={view!r}; allowed={VALID_VIEWS}"
            )
        criteria = dict(criteria or {})
        limit = int(criteria.get("limit") or 100)

        if view_key == "topic":
            key = self._require(criteria, "key")
            query, params = catalog_cypher.QUERY_TOPIC_DOCUMENTS, {"key": key, "limit": limit}
        elif view_key == "subject":
            code = self._require(criteria, "code")
            query, params = catalog_cypher.QUERY_SUBJECT_DOCUMENTS, {"code": code, "limit": limit}
        else:  # dynasty
            dynasty = self._require(criteria, "dynasty")
            query, params = catalog_cypher.QUERY_DYNASTY_DOCUMENTS, {"dynasty": dynasty, "limit": limit}

        with self._session() as session:
            result = session.run(query, **params)
            return [self._record_to_dict(record) for record in result]

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    @contextmanager
    def _session(self) -> Iterator[Any]:
        """统一 session 获取，兼容 Neo4jDriver 包装与原始 driver。"""
        opener = self._resolve_session_opener()
        ctx = opener(database=self._database) if self._database else opener()
        try:
            session = ctx.__enter__()
        except AttributeError as exc:  # pragma: no cover - defensive
            raise CatalogContextError(f"driver.session() did not return a context manager: {exc}") from exc
        try:
            yield session
        finally:
            ctx.__exit__(None, None, None)

    def _resolve_session_opener(self):
        inner = getattr(self._driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(self._driver, "session"):
            return self._driver.session
        raise CatalogContextError(
            "driver does not expose .session() or .driver.session()"
        )

    def _ensure_constraints_once(self) -> None:
        if self._constraints_ensured:
            return
        try:
            self.ensure_constraints()
        except Exception as exc:  # pragma: no cover - logged for diagnostics
            logger.warning("CatalogContext: ensure_constraints failed: %s", exc)
            self._constraints_ensured = True  # 避免反复重试阻塞重建

    @staticmethod
    def _require(payload: Mapping[str, Any], field: str) -> Any:
        value = payload.get(field) if isinstance(payload, Mapping) else None
        if value is None or value == "":
            raise CatalogContextError(f"missing required field {field!r} in {payload!r}")
        return value

    @staticmethod
    def _record_to_dict(record: Any) -> Dict[str, Any]:
        if hasattr(record, "data") and callable(record.data):
            try:
                return dict(record.data())
            except Exception:
                pass
        if isinstance(record, Mapping):
            return dict(record)
        try:
            return dict(record)
        except Exception:
            return {"value": record}
