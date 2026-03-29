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

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tags": self.tags,
            "call_count": self.call_count,
            "total_time": self.total_time,
            "total_quality": self.total_quality,
            "avg_time_ms": round(self.avg_time * 1000, 2) if self.call_count else None,
            "avg_quality": round(self.avg_quality, 4),
            "last_called": self.last_called,
        }


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

    def __init__(self, exploration_c: float = 1.4, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._algorithms: Dict[str, Callable] = {}
        self._profiles: Dict[str, AlgorithmProfile] = {}
        self._exploration_c = exploration_c
        self._total_calls = 0
        self._failed_operations: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {
            "phase_history": [],
            "phase_timings": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "initialized",
            "last_completed_phase": None,
        }
        self._governance_config = {
            "enable_phase_tracking": self.config.get("enable_phase_tracking", True),
            "persist_failed_operations": self.config.get("persist_failed_operations", True),
            "minimum_stable_quality": float(self.config.get("minimum_stable_quality", 0.8)),
            "export_contract_version": self.config.get("export_contract_version", "d25.v1"),
        }

    def _start_phase(self, phase_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self._governance_config.get("enable_phase_tracking", True):
            self._metadata["phase_history"].append(phase_entry)
        return phase_entry

    def _complete_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        self._metadata["phase_timings"][phase_name] = round(duration, 6)
        if phase_name not in self._metadata["completed_phases"]:
            self._metadata["completed_phases"].append(phase_name)
        self._metadata["last_completed_phase"] = phase_name
        self._metadata["final_status"] = "completed"

    def _fail_phase(self, phase_name: str, phase_entry: Dict[str, Any], start_time: float, error: str) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        self._metadata["phase_timings"][phase_name] = round(duration, 6)
        self._metadata["failed_phase"] = phase_name
        self._metadata["final_status"] = "failed"
        if self._governance_config.get("persist_failed_operations", True):
            self._failed_operations.append(
                {
                    "operation": phase_name,
                    "error": error,
                    "timestamp": datetime.now().isoformat(),
                    "duration_seconds": round(duration, 6),
                }
            )

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_value(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return {
                field_name: self._serialize_value(getattr(value, field_name))
                for field_name in value.__dataclass_fields__
            }
        if callable(value):
            return getattr(value, "__name__", "callable")
        return value

    def _build_analysis_summary(self) -> Dict[str, Any]:
        profiled = list(self._profiles.values())
        called_profiles = [profile for profile in profiled if profile.call_count > 0]
        best_profile = max(called_profiles, key=lambda profile: profile.avg_quality, default=None)
        status = "idle"
        if self._failed_operations:
            status = "needs_followup"
        elif self._total_calls > 0:
            status = "stable" if (best_profile.avg_quality if best_profile else 0.0) >= self._governance_config["minimum_stable_quality"] else "degraded"
        return {
            "registered_algorithm_count": len(self._algorithms),
            "profiled_algorithm_count": len(called_profiles),
            "total_calls": self._total_calls,
            "failed_operation_count": len(self._failed_operations),
            "best_algorithm": best_profile.name if best_profile else "",
            "best_quality": round(best_profile.avg_quality, 4) if best_profile else 0.0,
            "status": status,
            "last_completed_phase": self._metadata.get("last_completed_phase", ""),
            "failed_phase": self._metadata.get("failed_phase", ""),
            "final_status": self._metadata.get("final_status", "initialized"),
        }

    def _build_report_metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": self._governance_config["export_contract_version"],
            "generated_at": datetime.now().isoformat(),
            "result_schema": "algorithm_optimizer_report",
            "registered_algorithm_count": len(self._algorithms),
            "completed_phases": list(self._metadata.get("completed_phases", [])),
            "failed_phase": self._metadata.get("failed_phase"),
            "failed_operation_count": len(self._failed_operations),
            "last_completed_phase": self._metadata.get("last_completed_phase"),
        }

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

    def get_optimization_summary(self) -> Dict[str, Any]:
        return {
            "profiles": {name: self._serialize_value(profile.to_dict()) for name, profile in self._profiles.items()},
            "failed_operations": self._serialize_value(self._failed_operations),
            "analysis_summary": self._build_analysis_summary(),
            "report_metadata": self._build_report_metadata(),
            "metadata": self._serialize_value(self._metadata),
        }

    def export_optimization_data(self, output_path: str) -> bool:
        phase_entry = self._start_phase("export_optimization_data", {"output_path": output_path})
        start_time = time.perf_counter()
        try:
            payload = {
                "report_metadata": {
                    **self._build_report_metadata(),
                    "output_path": output_path,
                    "exported_file": os.path.basename(output_path),
                },
                "optimizer_summary": self.get_optimization_summary(),
                "algorithms": list(self._algorithms.keys()),
            }
            with open(output_path, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)
            self._metadata["failed_phase"] = None
            self._complete_phase("export_optimization_data", phase_entry, start_time)
            return True
        except Exception as exc:
            self._fail_phase("export_optimization_data", phase_entry, start_time, str(exc))
            logger.error("导出算法优化数据失败: %s", exc)
            return False

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

        start_time = time.perf_counter()
        phase_entry = self._start_phase("run_best", {"candidate_tags": candidate_tags or []})
        try:
            chosen = self._ucb1_select(candidates)
            result = self._invoke(chosen, context)
            self._metadata["failed_phase"] = None if not self._failed_operations else self._metadata.get("failed_phase")
            self._complete_phase("run_best", phase_entry, start_time)
            return chosen, result
        except Exception as exc:
            self._fail_phase("run_best", phase_entry, start_time, str(exc))
            raise

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

        start_time = time.perf_counter()
        phase_entry = self._start_phase("benchmark", {"candidate_tags": candidate_tags or [], "candidate_count": len(candidates)})
        try:
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
            self._metadata["failed_phase"] = None if not self._failed_operations else self._metadata.get("failed_phase")
            self._complete_phase("benchmark", phase_entry, start_time)
            logger.info("基准测试完成，最优算法: '%s'", winner)
            return {
                "results": results,
                "profiles": profiles_snapshot,
                "winner": winner,
                "analysis_summary": self._build_analysis_summary(),
                "report_metadata": self._build_report_metadata(),
            }
        except Exception as exc:
            self._fail_phase("benchmark", phase_entry, start_time, str(exc))
            raise

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
        phase_entry = self._start_phase("invoke_algorithm", {"algorithm": name})
        try:
            result: Dict[str, Any] = func(context)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            self._update_profile(name, elapsed, quality=0.0)
            self._fail_phase("invoke_algorithm", phase_entry, t0, str(exc))
            logger.error("算法 '%s' 执行异常: %s", name, exc)
            raise
        elapsed = time.perf_counter() - t0
        quality = float(result.get("quality_score", 0.5))
        self._update_profile(name, elapsed, quality)
        self._complete_phase("invoke_algorithm", phase_entry, t0)
        return result

    def _update_profile(self, name: str, elapsed: float, quality: float) -> None:
        p = self._profiles[name]
        p.call_count += 1
        p.total_time += elapsed
        p.total_quality += max(0.0, min(1.0, quality))
        p.last_called = datetime.now().isoformat()
        self._total_calls += 1

    def cleanup(self) -> bool:
        try:
            self._algorithms.clear()
            self._profiles.clear()
            self._failed_operations.clear()
            self._total_calls = 0
            self._metadata = {
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "terminated",
                "last_completed_phase": None,
            }
            return True
        except Exception as exc:
            logger.error("清理算法优化器失败: %s", exc)
            return False
