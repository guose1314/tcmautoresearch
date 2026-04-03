"""向量检索服务：为方剂/证候提供相似项检索。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
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
        persist_directory: Optional[str] = None,
        index_name: str = "embedding_index",
        auto_persist: bool = True,
        auto_load: bool = True,
        corpus_version: str = "default",
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
        self._persist_directory = Path(persist_directory).resolve() if persist_directory else None
        self._index_name = str(index_name or "embedding_index").strip() or "embedding_index"
        self._auto_persist = bool(auto_persist)
        self._index_signature: str = ""
        self._corpus_version = str(corpus_version or "default").strip() or "default"

        if auto_load and self._persist_directory is not None:
            self.load_index()

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
        if self._reuse_or_replace_items("formula", items):
            return len(items)
        self.build_index()
        return len(items)

    def build_syndrome_index(self, syndromes: Iterable[Dict[str, Any]]) -> int:
        items = [self._coerce_syndrome_item(item) for item in syndromes]
        if self._reuse_or_replace_items("syndrome", items):
            return len(items)
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

        self._index_signature = self._compute_signature(self._items)
        if self._auto_persist and self._persist_directory is not None:
            self.save_index()

    def search(
        self,
        query: str,
        top_k: int = 5,
        item_type: Optional[str] = None,
        min_score: float = 0.0,
        exclude_item_id: Optional[str] = None,
    ) -> List[SearchResult]:
        normalized_item_type = self._validate_search_request(query, top_k, item_type)
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

        query_vector = self._prepare_query_vector(query)
        ranked_pairs = self._rank_candidates(query_vector, top_k)

        return self._build_search_results(ranked_pairs, candidate_indexes, min_score, top_k)

    def _validate_search_request(
        self,
        query: str,
        top_k: int,
        item_type: Optional[str],
    ) -> Optional[str]:
        """校验 search 输入并返回标准化 item_type。"""
        if not query or not str(query).strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        normalized_item_type = self._ontology.normalize_node_type(item_type, strict=True) if item_type else None
        if normalized_item_type and not self._ontology.validate_embedding_item_type(normalized_item_type):
            raise ValueError(f"不支持的 item_type: {item_type}")
        return normalized_item_type

    def _prepare_query_vector(self, query: str) -> np.ndarray:
        """编码并标准化查询向量。"""
        query_vector = np.asarray(self._encode([query]), dtype=np.float32)
        if self.normalize_embeddings:
            query_vector = self._normalize(query_vector)
        return query_vector

    def _rank_candidates(self, query_vector: np.ndarray, top_k: int) -> List[tuple[int, float]]:
        """按相似度生成候选排序。"""
        assert self._embeddings is not None

        if self._faiss_enabled and self._index is not None:
            limit = min(max(top_k * 4, top_k), len(self._items))
            scores, indices = self._index.search(query_vector, limit)
            return [
                (int(index), float(score))
                for index, score in zip(indices[0].tolist(), scores[0].tolist())
                if index >= 0
            ]

        similarities = np.dot(self._embeddings, query_vector[0])
        ranked_indexes = np.argsort(-similarities)
        return [(int(index), float(similarities[index])) for index in ranked_indexes.tolist()]

    def _build_search_results(
        self,
        ranked_pairs: List[tuple[int, float]],
        candidate_indexes: List[int],
        min_score: float,
        top_k: int,
    ) -> List[SearchResult]:
        """将候选分数转换为 SearchResult 列表。"""
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
        self._index_signature = ""

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
            "persist_directory": str(self._persist_directory) if self._persist_directory is not None else "",
            "index_name": self._index_name,
            "index_signature": self._index_signature,
            "corpus_version": self._corpus_version,
        }

    def save_index(self, directory: Optional[str] = None) -> bool:
        target_dir = Path(directory).resolve() if directory else self._persist_directory
        if target_dir is None or self._embeddings is None:
            return False

        target_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self._metadata_path(target_dir)
        embeddings_path = self._embeddings_path(target_dir)
        metadata = {
            "model_name": self.model_name,
            "normalize_embeddings": self.normalize_embeddings,
            "faiss_enabled": bool(self._faiss_enabled and faiss is not None),
            "dimension": self._dimension,
            "corpus_version": self._corpus_version,
            "index_signature": self._index_signature or self._compute_signature(self._items),
            "items": [
                {
                    "item_id": item.item_id,
                    "text": item.text,
                    "item_type": item.item_type,
                    "metadata": item.metadata,
                }
                for item in self._items
            ],
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        np.save(embeddings_path, self._embeddings)

        if metadata["faiss_enabled"] and self._index is not None and faiss is not None:
            faiss.write_index(self._index, str(self._faiss_path(target_dir)))
        return True

    def load_index(self, directory: Optional[str] = None) -> bool:
        target_dir = Path(directory).resolve() if directory else self._persist_directory
        if target_dir is None:
            return False

        metadata_path = self._metadata_path(target_dir)
        embeddings_path = self._embeddings_path(target_dir)
        if not metadata_path.exists() or not embeddings_path.exists():
            return False

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        if not self._is_compatible_persisted_metadata(metadata):
            return False

        try:
            embeddings = np.load(embeddings_path, allow_pickle=False)
        except Exception:
            return False

        items_payload = metadata.get("items") or []
        items = [
            EmbeddingItem(
                item_id=str(item.get("item_id") or ""),
                text=str(item.get("text") or ""),
                item_type=str(item.get("item_type") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in items_payload
            if isinstance(item, dict)
        ]
        if not items or embeddings.ndim != 2 or embeddings.shape[0] != len(items):
            return False

        self._items = items
        self._embeddings = np.asarray(embeddings, dtype=np.float32)
        self._dimension = int(self._embeddings.shape[1])
        self._index_signature = str(metadata.get("index_signature") or self._compute_signature(items))
        self._faiss_enabled = bool(self._requested_use_faiss and metadata.get("faiss_enabled") and faiss is not None)

        if self._faiss_enabled and self._faiss_path(target_dir).exists() and faiss is not None:
            self._index = faiss.read_index(str(self._faiss_path(target_dir)))
        else:
            self._index = self._embeddings
            self._faiss_enabled = False
        return True

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

    def _reuse_or_replace_items(self, item_type: str, new_items: Sequence[EmbeddingItem]) -> bool:
        normalized_item_type = self._ontology.normalize_node_type(item_type, strict=True)
        remaining = [item for item in self._items if item.item_type != normalized_item_type]
        candidate_items = remaining + list(new_items)
        candidate_signature = self._compute_signature(candidate_items)
        self._items = candidate_items
        if self._embeddings is not None and self._index_signature == candidate_signature:
            self._dimension = int(self._embeddings.shape[1])
            return True
        self._index_signature = candidate_signature
        return False

    def _coerce_formula_item(self, item: Dict[str, Any]) -> EmbeddingItem:
        formula_id, name = self._extract_formula_identity(item)
        text_parts = self._build_formula_text_parts(item, name)
        return EmbeddingItem(
            item_id=formula_id,
            text="；".join(part for part in text_parts if part),
            item_type="formula",
            metadata={k: v for k, v in item.items() if k not in {"text"}},
        )

    def _extract_formula_identity(self, item: Dict[str, Any]) -> tuple[str, str]:
        """提取并校验 formula 的 id 与 name。"""
        formula_id = str(item.get("formula_id") or item.get("id") or item.get("name") or "").strip()
        name = str(item.get("name") or item.get("formula") or "").strip()
        if not formula_id or not name:
            raise ValueError("formula 项必须包含 id/name")
        return formula_id, name

    def _build_formula_text_parts(self, item: Dict[str, Any], name: str) -> List[str]:
        """构建 formula 向量化文本片段。"""
        text_parts = [name]
        text_parts.extend(self._optional_list_text(item.get("herbs"), "药物:"))
        text_parts.extend(self._optional_list_text(item.get("indications") or item.get("syndromes"), "证候:"))

        description = str(item.get("description") or "").strip()
        if description:
            text_parts.append(description)
        return text_parts

    def _optional_list_text(self, value: Any, prefix: str) -> List[str]:
        """将可选列表字段转换为文本片段。"""
        if isinstance(value, list) and value:
            text = " ".join(str(part) for part in value if part)
            if text:
                return [f"{prefix}{text}"]
        return []

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

    def _compute_signature(self, items: Sequence[EmbeddingItem]) -> str:
        payload = [
            {
                "item_id": item.item_id,
                "text": item.text,
                "item_type": item.item_type,
                "metadata": item.metadata,
            }
            for item in items
        ]
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _is_compatible_persisted_metadata(self, metadata: Dict[str, Any]) -> bool:
        return (
            str(metadata.get("model_name") or "") == self.model_name
            and bool(metadata.get("normalize_embeddings")) == self.normalize_embeddings
            and str(metadata.get("corpus_version") or "default") == self._corpus_version
        )

    def _metadata_path(self, directory: Path) -> Path:
        return directory / f"{self._index_name}.metadata.json"

    def _embeddings_path(self, directory: Path) -> Path:
        return directory / f"{self._index_name}.embeddings.npy"

    def _faiss_path(self, directory: Path) -> Path:
        return directory / f"{self._index_name}.faiss.index"
