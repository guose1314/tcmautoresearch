"""Catalog 视图模型 — Topic / SubjectClass / DynastySlice。

视图节点对应到 Neo4j 的三类目录节点；同一个 Document 可被多视图引用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

VALID_VIEWS = ("topic", "subject", "dynasty")


@dataclass
class TopicView:
    """主题视图 (:Topic {key})。"""

    key: str
    label: str = ""
    description: str = ""
    document_ids: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SubjectClassView:
    """学科分类视图 (:SubjectClass {code}). scheme 默认 CLC（中图法）。"""

    code: str
    name: str = ""
    scheme: str = "CLC"
    document_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DynastySliceView:
    """朝代时间切片视图 (:DynastySlice {dynasty})."""

    dynasty: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    document_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
