# src/learning/adaptive_tuner.py
"""
自适应调整器 - 根据运行时性能指标自动调节系统参数。

核心策略：
- 指数移动平均（EMA）平滑历史指标，降低噪声干扰
- 梯度式更新：性能提升时向原方向小步前进；性能下降时回退
- 硬边界约束：每个参数均有 [min, max] 安全范围，防止参数漂移
- 冷却期：两次调整之间需满足最少调用次数，避免震荡
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParameterSpec:
    """单个可调参数的规格说明。"""
    name: str
    current: float
    min_val: float
    max_val: float
    step: float = 0.05          # 每次调整的最大步长
    ema_alpha: float = 0.2      # EMA 平滑系数（越大越激进）
    cooldown: int = 5           # 调整后需间隔的最少调用次数

    # ---------- 内部状态 ----------
    _ema: float = field(init=False)
    _calls_since_update: int = field(default=0, init=False)
    _last_direction: float = field(default=0.0, init=False)   # +1 / -1 / 0

    def __post_init__(self) -> None:
        self._ema = self.current

    @property
    def ema(self) -> float:
        return self._ema

    def update_ema(self, value: float) -> None:
        self._ema = self.ema_alpha * value + (1 - self.ema_alpha) * self._ema

    def clamp(self, value: float) -> float:
        return max(self.min_val, min(self.max_val, value))

    def ready_to_update(self) -> bool:
        return self._calls_since_update >= self.cooldown

    def mark_updated(self) -> None:
        self._calls_since_update = 0

    def tick(self) -> None:
        self._calls_since_update += 1


# ------------------------------------------------------------------
# 默认参数规格（可被外部配置覆盖）
# ------------------------------------------------------------------
_DEFAULT_SPECS: Dict[str, Dict[str, Any]] = {
    "confidence_threshold": dict(current=0.7, min_val=0.3, max_val=0.95, step=0.03),
    "quality_threshold":    dict(current=0.7, min_val=0.3, max_val=0.95, step=0.03),
    "learning_threshold":   dict(current=0.7, min_val=0.4, max_val=0.9,  step=0.02),
    "entity_weight":        dict(current=0.05, min_val=0.01, max_val=0.2, step=0.01),
    "max_concurrent_tasks": dict(current=4.0, min_val=1.0, max_val=16.0, step=1.0),
}


class AdaptiveTuner:
    """
    自适应参数调整器。

    使用示例
    --------
    >>> tuner = AdaptiveTuner()
    >>> # 每轮迭代后调用 step()
    >>> updated = tuner.step({"performance": 0.82, "quality": 0.75})
    >>> print(updated)   # {'confidence_threshold': 0.71, ...}
    """

    def __init__(
        self,
        specs: Optional[Dict[str, Dict[str, Any]]] = None,
        performance_target: float = 0.80,
    ):
        raw = specs if specs is not None else _DEFAULT_SPECS
        self._params: Dict[str, ParameterSpec] = {
            name: ParameterSpec(name=name, **kw) for name, kw in raw.items()
        }
        self._target = performance_target
        self._history: List[Dict[str, float]] = []   # 每轮 metrics 快照
        self._update_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 主接口
    # ------------------------------------------------------------------

    def step(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """
        接收当前轮次的性能指标，决策是否调整各参数，返回当前参数值快照。

        Parameters
        ----------
        metrics : dict
            至少包含 "performance" 键（0-1），可选 "quality"、"confidence" 等。
        """
        self._history.append(metrics)
        for spec in self._params.values():
            spec.tick()

        perf = float(metrics.get("performance", 0.5))
        self._tune_all(perf)
        return self.current_values()

    def current_values(self) -> Dict[str, float]:
        """返回所有参数的当前值快照。"""
        return {name: round(spec.current, 6) for name, spec in self._params.items()}

    def get_parameter(self, name: str) -> Optional[float]:
        spec = self._params.get(name)
        return spec.current if spec else None

    def set_parameter(self, name: str, value: float) -> None:
        """手动强制更新某参数，仍受硬边界约束。"""
        if name not in self._params:
            raise KeyError(f"未知参数：{name}")
        self._params[name].current = self._params[name].clamp(value)

    def get_update_log(self) -> List[Dict[str, Any]]:
        return list(self._update_log)

    def add_parameter(
        self,
        name: str,
        current: float,
        min_val: float,
        max_val: float,
        *legacy_args: Any,
        **parameter_options: Any,
    ) -> None:
        """动态注册新参数。"""
        step, ema_alpha, cooldown = self._resolve_parameter_options(legacy_args, parameter_options)
        self._params[name] = ParameterSpec(
            name=name, current=current, min_val=min_val, max_val=max_val,
            step=step, ema_alpha=ema_alpha, cooldown=cooldown,
        )

    def _resolve_parameter_options(
        self,
        legacy_args: Tuple[Any, ...],
        parameter_options: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        default_values = (0.05, 0.2, 5)
        normalized = list(default_values)
        for idx, value in enumerate(legacy_args[:3]):
            normalized[idx] = value

        step = float(parameter_options.get("step", normalized[0]))
        ema_alpha = float(parameter_options.get("ema_alpha", normalized[1]))
        cooldown = int(parameter_options.get("cooldown", normalized[2]))
        return step, ema_alpha, cooldown

    # ------------------------------------------------------------------
    # 内部调整逻辑
    # ------------------------------------------------------------------

    def _tune_all(self, perf: float) -> None:
        """根据当前性能对各参数做梯度式更新。"""
        delta = perf - self._target           # 正值=超标，负值=未达标
        for spec in self._params.values():
            if not spec.ready_to_update():
                continue
            new_val = self._compute_new(spec, delta)
            if abs(new_val - spec.current) > 1e-9:
                self._record_update(spec.name, spec.current, new_val, delta)
                spec.current = new_val
                spec.mark_updated()

    def _compute_new(self, spec: ParameterSpec, delta: float) -> float:
        """
        计算单参数的新目标值。

        策略：
        - 性能偏低（delta < 0）→ 提高阈值类参数（让系统更严格），
          降低步长步进；性能偏高时则反向松弛。
        - 使用 EMA 平滑 delta，缓冲噪声。
        """
        spec.update_ema(delta)
        smooth_delta = spec.ema            # 用 EMA 值而非原始 delta

        # 动量修正：若与上次方向相同则加速，相反则缩步
        direction = 1.0 if smooth_delta >= 0 else -1.0
        momentum = 1.2 if direction == spec._last_direction else 0.7
        spec._last_direction = direction

        adjustment = direction * spec.step * abs(smooth_delta) * momentum
        return spec.clamp(spec.current + adjustment)

    def _record_update(
        self, name: str, old: float, new: float, delta: float
    ) -> None:
        from datetime import datetime
        entry = {
            "timestamp": datetime.now().isoformat(),
            "parameter": name,
            "old_value": round(old, 6),
            "new_value": round(new, 6),
            "performance_delta": round(delta, 4),
        }
        self._update_log.append(entry)
        if len(self._update_log) > 1000:
            self._update_log.pop(0)
        logger.debug(
            "参数调整 '%s': %.4f → %.4f (Δperf=%.3f)",
            name, old, new, delta,
        )

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """返回调整器状态摘要，便于监控与调试。"""
        recent = self._history[-10:] if self._history else []
        avg_perf = (
            sum(m.get("performance", 0) for m in recent) / len(recent)
            if recent else 0.0
        )
        return {
            "parameter_count": len(self._params),
            "total_steps": len(self._history),
            "total_updates": len(self._update_log),
            "recent_avg_performance": round(avg_perf, 4),
            "performance_target": self._target,
            "current_values": self.current_values(),
        }
