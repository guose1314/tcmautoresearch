"""DataMiner — 独立数据挖掘模块。

从 SummaryAnalysisEngine 提取出 KMeans 聚类（含纯 numpy 实现）、
因子分析（sklearn / SVD 兜底）与 LDA 主题建模（sklearn / SVD 兜底）等算法，
以便独立测试和复用。

SummaryAnalysisEngine 渐进迁移至委托调用本模块 (2.2 DataMiner 独立模块)。
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

try:
    from sklearn.decomposition import FactorAnalysis as _FactorAnalysis
    from sklearn.decomposition import LatentDirichletAllocation as _LDA

    _HAS_SKLEARN = True
except ImportError:  # pragma: no cover
    _HAS_SKLEARN = False
    _FactorAnalysis = _LDA = None


class DataMiner:
    """聚类、因子分析与 LDA 主题建模的独立封装。

    所有方法均为 classmethod，与原 SummaryAnalysisEngine 保持相同调用约定。
    输出数据结构与原实现完全一致，方便渐进迁移（老类直接委托本类）。
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def cluster(
        cls, records: List[Dict[str, Any]], herbs: List[str]
    ) -> Dict[str, Any]:
        """KMeans 聚类 + 因子分析。

        Returns:
            {"clusters": [...], "factors": [...]}
        """
        if not records or not herbs:
            return {"clusters": [], "factors": []}

        X = cls._build_binary_matrix(records, herbs)
        n_clusters = min(3, len(records))

        clusters_out = cls._cluster_records(records, X, n_clusters)
        factors_out = cls._analyze_factors(X, herbs)

        return {"clusters": clusters_out, "factors": factors_out}

    @classmethod
    def _build_binary_matrix(cls, records: List[Dict[str, Any]], herbs: List[str]) -> np.ndarray:
        """构建方剂-药物二值矩阵。"""
        return np.array(
            [[1.0 if herb in record.get("herbs", []) else 0.0 for herb in herbs] for record in records]
        )

    @classmethod
    def _cluster_records(
        cls,
        records: List[Dict[str, Any]],
        matrix: np.ndarray,
        n_clusters: int,
    ) -> List[Dict[str, Any]]:
        """执行 KMeans 聚类并封装输出。"""
        try:
            labels = cls._numpy_kmeans(matrix, k=n_clusters)
            return [
                {"formula": records[index].get("formula"), "cluster": int(label)}
                for index, label in enumerate(labels)
            ]
        except Exception:
            return [{"formula": record.get("formula"), "cluster": 0} for record in records]

    @classmethod
    def _analyze_factors(cls, matrix: np.ndarray, herbs: List[str]) -> List[Dict[str, Any]]:
        """执行因子分析，失败时回退 SVD。"""
        if _HAS_SKLEARN and _FactorAnalysis is not None:
            try:
                n_components = min(2, matrix.shape[1], matrix.shape[0])
                fa = _FactorAnalysis(n_components=n_components, random_state=42)
                fa.fit(matrix)
                return cls._format_factor_loadings(fa.components_, herbs)
            except Exception:
                return cls._svd_fallback_factors(matrix, herbs)
        return cls._svd_fallback_factors(matrix, herbs)

    @classmethod
    def _format_factor_loadings(cls, loadings: Any, herbs: List[str]) -> List[Dict[str, Any]]:
        """将因子载荷矩阵转换为统一输出结构。"""
        factors_out: List[Dict[str, Any]] = []
        for idx, comp in enumerate(loadings):
            pairs = sorted(
                [(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))],
                key=lambda x: x[1],
                reverse=True,
            )
            factors_out.append(
                {
                    "factor": idx,
                    "top_herbs": [{"herb": herb, "loading": round(value, 4)} for herb, value in pairs[:5]],
                }
            )
        return factors_out

    @classmethod
    def latent_topics(
        cls, records: List[Dict[str, Any]], herbs: List[str]
    ) -> Dict[str, Any]:
        """LDA 主题建模。

        Returns:
            {"topics": [...]}
        """
        if not records or not herbs:
            return {"topics": []}

        X = np.array(
            [[1.0 if h in r.get("herbs", []) else 0.0 for h in herbs] for r in records]
        )

        topics: List[Dict[str, Any]] = []
        if _HAS_SKLEARN and _LDA is not None:
            try:
                n_comp = min(2, max(1, X.shape[0]))
                lda = _LDA(n_components=n_comp, random_state=42)
                lda.fit(X)
                comps = lda.components_
                for i, comp in enumerate(comps):
                    pairs = sorted(
                        [(herbs[j], float(comp[j])) for j in range(len(herbs))],
                        key=lambda x: x[1],
                        reverse=True,
                    )
                    topics.append(
                        {
                            "topic": i,
                            "top_herbs": [
                                {"herb": h, "weight": round(w, 4)}
                                for h, w in pairs[:5]
                            ],
                        }
                    )
            except Exception:
                topics = cls._svd_latent_topics(X, herbs)
        else:
            topics = cls._svd_latent_topics(X, herbs)

        return {"topics": topics}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _numpy_kmeans(cls, X: Any, k: int, max_iter: int = 100) -> List[int]:
        """纯 numpy KMeans，避免触发 sklearn 线程池初始化。

        使用固定随机种子（42）保证结果可重现。
        当 k >= 样本数时直接返回顺序标签（每个样本独占一个簇）。
        """
        arr = np.asarray(X, dtype=float)
        n = arr.shape[0]
        if k >= n:
            return list(range(n))

        rng = np.random.default_rng(42)
        init_idx = rng.choice(n, size=k, replace=False)
        centers = arr[init_idx].copy()
        labels = np.zeros(n, dtype=int)

        for _ in range(max_iter):
            # (n, k) 距离矩阵
            dists = np.linalg.norm(arr[:, None, :] - centers[None, :, :], axis=2)
            new_labels = np.argmin(dists, axis=1)
            if np.array_equal(new_labels, labels):
                break
            labels = new_labels
            for c in range(k):
                mask = labels == c
                if mask.any():
                    centers[c] = arr[mask].mean(axis=0)

        return labels.tolist()

    @classmethod
    def _svd_fallback_factors(
        cls, X: Any, herbs: List[str]
    ) -> List[Dict[str, Any]]:
        """SVD 兜底因子分析（sklearn 不可用或抛异常时使用）。"""
        factors_out: List[Dict[str, Any]] = []
        _, _, vt = np.linalg.svd(X, full_matrices=False)
        if vt.size > 0:
            for idx in range(min(2, vt.shape[0])):
                comp = vt[idx]
                pairs = sorted(
                    [(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))],
                    key=lambda x: x[1],
                    reverse=True,
                )
                factors_out.append(
                    {
                        "factor": idx,
                        "top_herbs": [
                            {"herb": h, "loading": round(v, 4)}
                            for h, v in pairs[:5]
                        ],
                    }
                )
        return factors_out

    @classmethod
    def _svd_latent_topics(
        cls, X: Any, herbs: List[str]
    ) -> List[Dict[str, Any]]:
        """SVD 兜底隐结构（LDA 不可用或抛异常时使用）。"""
        _, _, vt = np.linalg.svd(X, full_matrices=False)
        topics: List[Dict[str, Any]] = []
        for i in range(min(2, vt.shape[0])):
            comp = vt[i]
            pairs = sorted(
                [(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))],
                key=lambda x: x[1],
                reverse=True,
            )
            topics.append(
                {
                    "topic": i,
                    "top_herbs": [
                        {"herb": h, "weight": round(w, 4)} for h, w in pairs[:5]
                    ],
                }
            )
        return topics
