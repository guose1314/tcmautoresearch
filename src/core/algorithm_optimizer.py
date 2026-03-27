# src/core/algorithm_optimizer.py
"""
算法优化器 - 基于 UCB1 的自适应算法选择与性能剖析。

职责：
- 注册多种候选算法实现
- 剖析每种算法的历史耗时和质量得分
- 使用 Upper Confidence Bound (UCB1) 策略在探索与利用之间取得平衡
- 提供基准测试接口以同台对比候选算法
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AlgorithmProfile:
    """单个算法的运行时画像。"""
    name: str
    tags: List[str] = field(default_factory=list)
    call_count: int = 0
    total_time: float = 0.0          # 秒
    total_quality: float = 0.0       # 累计质量分 (0-1)
    last_called: Optional[str] = None

    # ---------- 派生指标 ----------
    @property
    def avg_time(self) -> float:
        return self.total_time / self.call_count if self.call_count else float("inf")

    @property
    def avg_quality(self) -> float:
        return self.total_quality / self.call_count if self.call_count else 0.0

    def ucb1_score(self, total_calls: int, exploration_c: float = 1.4) -> float:
        """
        UCB1 得分 = avg_quality + C * sqrt(ln(N) / n_i)

        - avg_quality  利用项：历史平均质量
        - sqrt(...)    探索项：调用次数越少得分越高（促进均衡尝试）
        - exploration_c 探索强度系数，默认 sqrt(2) ≈ 1.414
        """
        if self.call_count == 0:
            return float("inf")          # 未调用过的算法优先探索
        exploit = self.avg_quality
        explore = exploration_c * math.sqrt(math.log(total_calls + 1) / self.call_count)
        return exploit + explore


class AlgorithmOptimizer:
    """
    算法优化器：持续跟踪多个候选算法的性能，并以 UCB1 决策选最优候选。

    使用示例
    --------
    >>> opt = AlgorithmOptimizer()
    >>> opt.register("fast_algo", my_fast_fn, tags=["text", "entity"])
    >>> opt.register("accurate_algo", my_accurate_fn, tags=["text"])
    >>> result = opt.run_best(context, candidate_tags=["text"])
    """

    def __init__(self, exploration_c: float = 1.4):
        self._algorithms: Dict[str, Callable] = {}
        self._profiles: Dict[str, AlgorithmProfile] = {}
        self._exploration_c = exploration_c
        self._total_calls = 0

    # ------------------------------------------------------------------
    # 注册 / 查询
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        func: Callable[[Dict[str, Any]], Dict[str, Any]],
        tags: Optional[List[str]] = None,
    ) -> None:
        """注册一个候选算法。func 签名：(context: dict) -> dict，需含 quality_score 键。"""
        if name in self._algorithms:
            logger.warning("算法 '%s' 已注册，将覆盖旧实现", name)
        self._algorithms[name] = func
        if name not in self._profiles:
            self._profiles[name] = AlgorithmProfile(name=name, tags=tags or [])
        else:
            self._profiles[name].tags = tags or self._profiles[name].tags

    def list_algorithms(self) -> List[str]:
        return list(self._algorithms.keys())

    def get_profile(self, name: str) -> Optional[AlgorithmProfile]:
        return self._profiles.get(name)

    def get_all_profiles(self) -> Dict[str, AlgorithmProfile]:
        return dict(self._profiles)

    # ------------------------------------------------------------------
    # 核心执行
    # ------------------------------------------------------------------

    def run_best(
        self,
        context: Dict[str, Any],
        candidate_tags: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        选出 UCB1 最优算法并执行，返回 (chosen_name, result)。

        Parameters
        ----------
        context : dict
            传入算法的上下文数据。
        candidate_tags : list[str], optional
            若指定，仅在含任意这些标签的算法中选择。
        """
        candidates = self._filter_candidates(candidate_tags)
        if not candidates:
            raise ValueError("无可用算法，请先调用 register() 注册实现")

        chosen = self._ucb1_select(candidates)
        result = self._invoke(chosen, context)
        return chosen, result

    def benchmark(
        self,
        context: Dict[str, Any],
        candidate_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        对所有（过滤后的）候选算法执行一次基准测试，返回对比报告。

        返回格式
        --------
        {
          "results":  { name: result_dict, ... },
          "profiles": { name: { avg_time, avg_quality, call_count }, ... },
          "winner":   best_name
        }
        """
        candidates = self._filter_candidates(candidate_tags)
        if not candidates:
            raise ValueError("无可用候选算法")

        results: Dict[str, Dict[str, Any]] = {}
        for name in candidates:
            results[name] = self._invoke(name, context)

        winner = max(candidates, key=lambda n: self._profiles[n].avg_quality)
        profiles_snapshot = {
            n: {
                "avg_time_ms": round(self._profiles[n].avg_time * 1000, 2),
                "avg_quality": round(self._profiles[n].avg_quality, 4),
                "call_count": self._profiles[n].call_count,
            }
            for n in candidates
        }
        logger.info("基准测试完成，最优算法: '%s'", winner)
        return {"results": results, "profiles": profiles_snapshot, "winner": winner}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _filter_candidates(self, tags: Optional[List[str]]) -> List[str]:
        if not tags:
            return list(self._algorithms.keys())
        return [
            n for n, p in self._profiles.items()
            if any(t in p.tags for t in tags)
        ]

    def _ucb1_select(self, candidates: List[str]) -> str:
        scores = {
            n: self._profiles[n].ucb1_score(self._total_calls, self._exploration_c)
            for n in candidates
        }
        chosen = max(scores, key=scores.__getitem__)
        logger.debug(
            "UCB1 选择算法 '%s'，得分=%.4f（候选共 %d 个）",
            chosen, scores[chosen], len(candidates),
        )
        return chosen

    def _invoke(self, name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        func = self._algorithms[name]
        t0 = time.perf_counter()
        try:
            result: Dict[str, Any] = func(context)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._update_profile(name, elapsed, quality=0.0)
            logger.error("算法 '%s' 执行异常: %s", name, exc)
            raise
        elapsed = time.perf_counter() - t0
        quality = float(result.get("quality_score", 0.5))
        self._update_profile(name, elapsed, quality)
        return result

    def _update_profile(self, name: str, elapsed: float, quality: float) -> None:
        from datetime import datetime
        p = self._profiles[name]
        p.call_count += 1
        p.total_time += elapsed
        p.total_quality += max(0.0, min(1.0, quality))
        p.last_called = datetime.now().isoformat()
        self._total_calls += 1
