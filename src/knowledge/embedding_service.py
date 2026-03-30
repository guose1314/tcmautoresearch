"""向量检索服务：为方剂/证候提供相似项检索。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from src.knowledge.ontology_manager import OntologyManager

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - 环境不完整时在运行期报错
    SentenceTransformer = None

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - 测试覆盖回退路径
    faiss = None


@dataclass(slots=True)
class EmbeddingItem:
    """向量索引中的单条知识项。"""

    item_id: str
    text: str
    item_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    """相似检索结果。"""

    item_id: str
    text: str
    item_type: str
    score: float
    rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "text": self.text,
            "item_type": self.item_type,
            "score": self.score,
            "rank": self.rank,
            "metadata": self.metadata,
        }


class EmbeddingService:
    """基于 SentenceTransformer + FAISS 的向量检索服务。"""

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        normalize_embeddings: bool = True,
        use_faiss: bool = True,
        encoder: Optional[Any] = None,
    ):
        self.model_name = model_name
        self.normalize_embeddings = normalize_embeddings
        self._requested_use_faiss = use_faiss
        self._encoder = encoder
        self._items: List[EmbeddingItem] = []
        self._embeddings: Optional[np.ndarray] = None
        self._dimension: Optional[int] = None
        self._index: Any = None
        self._faiss_enabled = bool(use_faiss and faiss is not None)
        self._ontology = OntologyManager()

    @property
    def faiss_enabled(self) -> bool:
        return self._faiss_enabled

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    def add_items(self, items: Iterable[EmbeddingItem], rebuild: bool = True) -> int:
        added = 0
        for item in items:
            self._validate_item(item)
            self._items.append(item)
            added += 1
        if rebuild and added:
            self.build_index()
        return added

    def build_formula_index(self, formulas: Iterable[Dict[str, Any]]) -> int:
        items = [self._coerce_formula_item(item) for item in formulas]
        self._replace_items_by_type("formula", items)
        self.build_index()
        return len(items)

    def build_syndrome_index(self, syndromes: Iterable[Dict[str, Any]]) -> int:
        items = [self._coerce_syndrome_item(item) for item in syndromes]
        self._replace_items_by_type("syndrome", items)
        self.build_index()
        return len(items)

    def build_index(self) -> None:
        if not self._items:
            self._embeddings = None
            self._dimension = None
            self._index = None
            return

        texts = [item.text for item in self._items]
        embeddings = self._encode(texts)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(self._items):
            raise ValueError("编码器返回的向量形状不合法")

        vectors = np.asarray(embeddings, dtype=np.float32)
        if self.normalize_embeddings:
            vectors = self._normalize(vectors)

        self._embeddings = vectors
        self._dimension = int(vectors.shape[1])

        if self._faiss_enabled:
            if faiss is None:
                raise RuntimeError("faiss 未安装，无法构建 FAISS 索引")
            index = faiss.IndexFlatIP(self._dimension)
            index.add(vectors)
            self._index = index
        else:
            self._index = vectors

    def search(
        self,
        query: str,
        top_k: int = 5,
        item_type: Optional[str] = None,
        min_score: float = 0.0,
        exclude_item_id: Optional[str] = None,
    ) -> List[SearchResult]:
        if not query or not str(query).strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        normalized_item_type = (
            self._ontology.normalize_node_type(item_type, strict=True) if item_type else None
        )
        if normalized_item_type and not self._ontology.validate_embedding_item_type(normalized_item_type):
            raise ValueError(f"不支持的 item_type: {item_type}")
        if not self._items:
            return []
        if self._embeddings is None:
            self.build_index()
        assert self._embeddings is not None

        candidate_indexes = self._candidate_indexes(
            item_type=normalized_item_type,
            exclude_item_id=exclude_item_id,
        )
        if not candidate_indexes:
            return []

        query_vector = self._encode([query])
        query_vector = np.asarray(query_vector, dtype=np.float32)
        if self.normalize_embeddings:
            query_vector = self._normalize(query_vector)

        if self._faiss_enabled and self._index is not None:
            limit = min(max(top_k * 4, top_k), len(self._items))
            scores, indices = self._index.search(query_vector, limit)
            ranked_pairs = [
                (int(index), float(score))
                for index, score in zip(indices[0].tolist(), scores[0].tolist())
                if index >= 0
            ]
        else:
            similarities = np.dot(self._embeddings, query_vector[0])
            ranked_indexes = np.argsort(-similarities)
            ranked_pairs = [(int(index), float(similarities[index])) for index in ranked_indexes.tolist()]

        allowed = set(candidate_indexes)
        results: List[SearchResult] = []
        for index, score in ranked_pairs:
            if index not in allowed or score < min_score:
                continue
            item = self._items[index]
            results.append(
                SearchResult(
                    item_id=item.item_id,
                    text=item.text,
                    item_type=item.item_type,
                    score=round(score, 6),
                    rank=len(results) + 1,
                    metadata=dict(item.metadata),
                )
            )
            if len(results) >= top_k:
                break
        return results

    def search_similar_formulas(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        exclude_formula_id: Optional[str] = None,
    ) -> List[SearchResult]:
        return self.search(
            query=query,
            top_k=top_k,
            item_type="formula",
            min_score=min_score,
            exclude_item_id=exclude_formula_id,
        )

    def search_similar_syndromes(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        exclude_syndrome_id: Optional[str] = None,
    ) -> List[SearchResult]:
        return self.search(
            query=query,
            top_k=top_k,
            item_type="syndrome",
            min_score=min_score,
            exclude_item_id=exclude_syndrome_id,
        )

    def clear(self) -> None:
        self._items.clear()
        self._embeddings = None
        self._dimension = None
        self._index = None

    def stats(self) -> Dict[str, Any]:
        type_counts: Dict[str, int] = {}
        for item in self._items:
            type_counts[item.item_type] = type_counts.get(item.item_type, 0) + 1
        return {
            "size": self.size,
            "dimension": self.dimension,
            "faiss_enabled": self.faiss_enabled,
            "types": type_counts,
            "model_name": self.model_name,
        }

    def _candidate_indexes(
        self,
        item_type: Optional[str],
        exclude_item_id: Optional[str],
    ) -> List[int]:
        indexes: List[int] = []
        for index, item in enumerate(self._items):
            if item_type and item.item_type != item_type:
                continue
            if exclude_item_id and item.item_id == exclude_item_id:
                continue
            indexes.append(index)
        return indexes

    def _get_encoder(self) -> Any:
        if self._encoder is None:
            if SentenceTransformer is None:
                raise RuntimeError(
                    "缺少 sentence-transformers 依赖，请先安装: pip install sentence-transformers"
                )
            self._encoder = SentenceTransformer(self.model_name)
        return self._encoder

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        encoder = self._get_encoder()
        vectors = encoder.encode(
            list(texts),
            normalize_embeddings=False,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    def _replace_items_by_type(self, item_type: str, new_items: Sequence[EmbeddingItem]) -> None:
        normalized_item_type = self._ontology.normalize_node_type(item_type, strict=True)
        remaining = [item for item in self._items if item.item_type != normalized_item_type]
        self._items = remaining + list(new_items)

    def _coerce_formula_item(self, item: Dict[str, Any]) -> EmbeddingItem:
        formula_id = str(item.get("formula_id") or item.get("id") or item.get("name") or "").strip()
        name = str(item.get("name") or item.get("formula") or "").strip()
        if not formula_id or not name:
            raise ValueError("formula 项必须包含 id/name")
        herbs = item.get("herbs") or []
        indications = item.get("indications") or item.get("syndromes") or []
        text_parts = [name]
        if isinstance(herbs, list) and herbs:
            text_parts.append("药物:" + " ".join(str(part) for part in herbs if part))
        if isinstance(indications, list) and indications:
            text_parts.append("证候:" + " ".join(str(part) for part in indications if part))
        if item.get("description"):
            text_parts.append(str(item.get("description")))
        return EmbeddingItem(
            item_id=formula_id,
            text="；".join(part for part in text_parts if part),
            item_type="formula",
            metadata={k: v for k, v in item.items() if k not in {"text"}},
        )

    def _coerce_syndrome_item(self, item: Dict[str, Any]) -> EmbeddingItem:
        syndrome_id = str(item.get("syndrome_id") or item.get("id") or item.get("name") or "").strip()
        name = str(item.get("name") or item.get("syndrome") or "").strip()
        if not syndrome_id or not name:
            raise ValueError("syndrome 项必须包含 id/name")
        manifestations = item.get("manifestations") or item.get("symptoms") or []
        text_parts = [name]
        if isinstance(manifestations, list) and manifestations:
            text_parts.append("表现:" + " ".join(str(part) for part in manifestations if part))
        if item.get("description"):
            text_parts.append(str(item.get("description")))
        return EmbeddingItem(
            item_id=syndrome_id,
            text="；".join(part for part in text_parts if part),
            item_type="syndrome",
            metadata={k: v for k, v in item.items() if k not in {"text"}},
        )

    def _validate_item(self, item: EmbeddingItem) -> None:
        if not item.item_id:
            raise ValueError("item_id 不能为空")
        if not item.text or not item.text.strip():
            raise ValueError("text 不能为空")
        normalized_item_type = self._ontology.normalize_node_type(item.item_type, strict=True)
        if not self._ontology.validate_embedding_item_type(normalized_item_type):
            raise ValueError(f"不支持的 item_type: {item.item_type}")
        item.item_type = normalized_item_type

    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return vectors / norms
